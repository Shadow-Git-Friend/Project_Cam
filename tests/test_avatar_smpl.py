"""Optional SMPL avatar fitting and mesh rendering helpers."""

from types import SimpleNamespace

import numpy as np
import pytest

from project_cam.avatar.coco_smpl_map import (
    COCO_TO_SMPL,
    SMPL_JOINT_NAMES,
    extract_smpl_targets,
)
from project_cam.avatar.mesh_renderer import draw_mesh_cv2, mesh_triangles
from project_cam.avatar.smpl_fit import (
    SmplFitConfig,
    SmplFitResult,
    SmplFitter,
    SmplSessionFitter,
)

torch = pytest.importorskip("torch")


def _coco(points_by_idx):
    joints = np.full((17, 3), np.nan, dtype=np.float64)
    for idx, point in points_by_idx.items():
        joints[idx] = np.asarray(point, dtype=np.float64)
    return joints


def test_extract_smpl_targets_maps_coco_torso_and_limbs():
    joints = _coco({
        5: [-200.0, 0.0, 1500.0],
        6: [200.0, 0.0, 1500.0],
        11: [-150.0, 0.0, 950.0],
        12: [150.0, 0.0, 950.0],
        15: [-150.0, 0.0, 50.0],
    })
    conf = np.ones(17, dtype=np.float64)
    conf[15] = 0.1

    targets = extract_smpl_targets(joints, conf, min_confidence=0.25)

    assert COCO_TO_SMPL[5] == SMPL_JOINT_NAMES.index("left_shoulder")
    assert "left_shoulder" in targets.names
    assert "right_hip" in targets.names
    assert "left_ankle" not in targets.names
    assert targets.points_mm.shape == (4, 3)
    assert targets.weights.tolist() == [1.0, 1.0, 1.0, 1.0]


def test_mesh_triangles_are_face_indexed_vertices():
    vertices = np.asarray([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    faces = np.asarray([[0, 1, 2], [0, 2, 3]], dtype=np.int32)

    triangles = mesh_triangles(vertices, faces)

    assert triangles.shape == (2, 3, 3)
    assert triangles[1, 2].tolist() == [0.0, 0.0, 1.0]


def test_draw_mesh_cv2_projects_and_fills_triangle():
    img = np.zeros((80, 80, 3), dtype=np.uint8)
    vertices = np.asarray([[10.0, 10.0, 1.0], [60.0, 10.0, 1.0], [20.0, 60.0, 1.0]])
    faces = np.asarray([[0, 1, 2]], dtype=np.int32)

    def project(points):
        pts = np.asarray(points, dtype=np.float64)
        return pts[:, :2], np.ones((len(pts),), dtype=bool)

    draw_mesh_cv2(img, vertices, faces, project, color_bgr=(10, 200, 240), alpha=1.0)

    assert int(img.sum()) > 0
    assert img[20, 20, 1] > 0


def test_export_mesh_writes_obj_file(tmp_path):
    pytest.importorskip("trimesh")
    from project_cam.avatar.mesh_renderer import export_mesh

    vertices = np.asarray([
        [0.0, 0.0, 0.0],
        [100.0, 0.0, 0.0],
        [0.0, 100.0, 0.0],
    ])
    faces = np.asarray([[0, 1, 2]], dtype=np.int32)
    out_path = tmp_path / "avatar.obj"

    returned = export_mesh(vertices, faces, out_path)

    assert returned == out_path
    text = out_path.read_text(encoding="utf-8")
    assert "v 0.00000000 0.00000000 0.00000000" in text
    assert "f 1 2 3" in text


class _FakeSmplBody(torch.nn.Module):
    def __init__(self):
        super().__init__()
        base = torch.zeros((24, 3), dtype=torch.float32)
        for idx, name in enumerate(SMPL_JOINT_NAMES):
            base[idx] = torch.tensor([float(idx) * 10.0, 0.0, 1000.0])
        self.register_buffer("base_joints", base)
        self.faces = np.asarray([[0, 1, 2]], dtype=np.int32)

    def forward(self, global_orient, body_pose, betas, transl, return_verts=True):
        joints = self.base_joints.unsqueeze(0) + transl.view(1, 1, 3)
        vertices = joints[:, :3, :]
        return SimpleNamespace(joints=joints, vertices=vertices)


def test_smpl_fitter_optimizes_translation_with_fake_model():
    body = _FakeSmplBody()
    shift = np.asarray([120.0, -50.0, 30.0], dtype=np.float64)
    joints = np.full((17, 3), np.nan, dtype=np.float64)
    for coco_idx, smpl_idx in COCO_TO_SMPL.items():
        joints[coco_idx] = body.base_joints[smpl_idx].numpy() + shift

    fitter = SmplFitter(
        SmplFitConfig(max_iters=80, learning_rate=0.08, model_units_to_mm=1.0),
        body_model=body,
    )
    result = fitter.fit(joints)

    assert result.vertices_mm.shape == (3, 3)
    assert result.faces.tolist() == [[0, 1, 2]]
    assert np.allclose(result.translation_mm, shift, atol=2.0)
    assert result.loss < 5.0


class _RecordingSmplBody(_FakeSmplBody):
    def __init__(self):
        super().__init__()
        self.first_global_orient = None
        self.first_body_pose = None
        self.first_betas = None

    def forward(self, global_orient, body_pose, betas, transl, return_verts=True):
        if self.first_body_pose is None:
            self.first_global_orient = global_orient.detach().cpu().numpy().copy()
            self.first_body_pose = body_pose.detach().cpu().numpy().copy()
            self.first_betas = betas.detach().cpu().numpy().copy()
        return super().forward(global_orient, body_pose, betas, transl, return_verts=return_verts)


def test_smpl_fitter_seeds_pose_from_previous_result():
    body = _RecordingSmplBody()
    joints = np.full((17, 3), np.nan, dtype=np.float64)
    for coco_idx, smpl_idx in COCO_TO_SMPL.items():
        joints[coco_idx] = body.base_joints[smpl_idx].numpy()
    previous = SmplFitResult(
        vertices_mm=np.zeros((3, 3), dtype=np.float64),
        joints_mm=np.zeros((24, 3), dtype=np.float64),
        faces=np.asarray([[0, 1, 2]], dtype=np.int32),
        translation_mm=np.asarray([50.0, 0.0, 0.0], dtype=np.float64),
        global_orient=np.asarray([0.1, -0.2, 0.3], dtype=np.float64),
        body_pose=np.linspace(-0.2, 0.2, 69, dtype=np.float64),
        betas=np.linspace(-0.05, 0.05, 10, dtype=np.float64),
        loss=0.0,
        target_count=12,
    )

    fitter = SmplFitter(
        SmplFitConfig(max_iters=1, learning_rate=0.01, model_units_to_mm=1.0),
        body_model=body,
    )
    fitter.fit(joints, previous_result=previous)

    assert np.allclose(body.first_global_orient.reshape(-1), previous.global_orient)
    assert np.allclose(body.first_body_pose.reshape(-1), previous.body_pose)
    assert np.allclose(body.first_betas.reshape(-1), previous.betas)


class _BetaAwareSmplBody(torch.nn.Module):
    def __init__(self):
        super().__init__()
        base = torch.zeros((24, 3), dtype=torch.float32)
        for idx, name in enumerate(SMPL_JOINT_NAMES):
            base[idx] = torch.tensor([float(idx) * 5.0, 0.0, 1000.0])
        self.register_buffer("base_joints", base)
        self.faces = np.asarray([[0, 1, 2]], dtype=np.int32)
        self.left = torch.tensor(
            [
                SMPL_JOINT_NAMES.index("left_shoulder"),
                SMPL_JOINT_NAMES.index("left_elbow"),
                SMPL_JOINT_NAMES.index("left_wrist"),
                SMPL_JOINT_NAMES.index("left_hip"),
                SMPL_JOINT_NAMES.index("left_knee"),
                SMPL_JOINT_NAMES.index("left_ankle"),
            ],
            dtype=torch.long,
        )
        self.right = torch.tensor(
            [
                SMPL_JOINT_NAMES.index("right_shoulder"),
                SMPL_JOINT_NAMES.index("right_elbow"),
                SMPL_JOINT_NAMES.index("right_wrist"),
                SMPL_JOINT_NAMES.index("right_hip"),
                SMPL_JOINT_NAMES.index("right_knee"),
                SMPL_JOINT_NAMES.index("right_ankle"),
            ],
            dtype=torch.long,
        )

    def forward(self, global_orient, body_pose, betas, transl, return_verts=True):
        joints = self.base_joints.unsqueeze(0).repeat(betas.shape[0], 1, 1).clone()
        width = betas[:, 0].view(-1, 1)
        left = self.left.to(joints.device)
        right = self.right.to(joints.device)
        joints[:, left, 0] = joints[:, left, 0] - width * 20.0
        joints[:, right, 0] = joints[:, right, 0] + width * 20.0
        joints = joints + transl.view(-1, 1, 3)
        vertices = joints[:, :3, :]
        return SimpleNamespace(joints=joints, vertices=vertices)


def test_smpl_session_fitter_calibrates_shape_once_then_locks_betas():
    body = _BetaAwareSmplBody()
    true_beta = 1.75
    with torch.no_grad():
        target_output = body(
            global_orient=torch.zeros((1, 3)),
            body_pose=torch.zeros((1, 69)),
            betas=torch.tensor([[true_beta] + [0.0] * 9], dtype=torch.float32),
            transl=torch.zeros((1, 3)),
        )
    joints = np.full((17, 3), np.nan, dtype=np.float64)
    for coco_idx, smpl_idx in COCO_TO_SMPL.items():
        joints[coco_idx] = target_output.joints[0, smpl_idx].numpy()

    session = SmplSessionFitter(
        SmplFitConfig(
            max_iters=120,
            learning_rate=0.08,
            model_units_to_mm=1.0,
            shape_reg_weight=0.0,
        ),
        body_model=body,
        shape_calibration_frames=1,
    )
    calibrated = session.fit(joints)
    shifted = session.fit(joints + np.asarray([50.0, -20.0, 10.0]))

    assert session.shape_locked
    assert session.calibration_count == 1
    assert np.isclose(session.stable_betas[0], true_beta, atol=0.15)
    assert np.allclose(calibrated.betas, session.stable_betas, atol=0.15)
    assert np.allclose(shifted.betas, session.stable_betas, atol=1e-6)
