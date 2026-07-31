"""SMPL fitting from Project_Cam COCO-17 3D joints."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

import numpy as np

from .coco_smpl_map import extract_smpl_targets


class OptionalAvatarDependencyError(RuntimeError):
    """Raised when optional SMPL fitting dependencies are unavailable."""


@dataclass(frozen=True)
class SmplFitConfig:
    """Configuration for one-frame SMPL fitting."""

    model_path: str | None = None
    model_type: str = "smpl"
    gender: str = "neutral"
    device: str = "cpu"
    dtype: str = "float32"
    num_betas: int = 10
    max_iters: int = 25
    learning_rate: float = 0.05
    min_confidence: float = 0.25
    include_head: bool = False
    optimize_betas: bool = False
    pose_reg_weight: float = 1e-4
    shape_reg_weight: float = 1e-3
    temporal_weight: float = 0.0
    floor_z_mm: float | None = None
    floor_penalty_weight: float = 0.0
    model_units_to_mm: float = 1000.0


@dataclass(frozen=True)
class SmplFitResult:
    """SMPL fit output in Project_Cam world millimetres."""

    vertices_mm: np.ndarray
    joints_mm: np.ndarray
    faces: np.ndarray
    translation_mm: np.ndarray
    global_orient: np.ndarray
    body_pose: np.ndarray
    betas: np.ndarray
    loss: float
    target_count: int


class SmplFitter:
    """Small SMPL optimizer driven by existing triangulated 3D joints."""

    def __init__(
        self,
        config: Optional[SmplFitConfig] = None,
        *,
        body_model=None,
    ):
        self.config = config or SmplFitConfig()
        self.torch = _load_torch()
        self.device = self.torch.device(self.config.device)
        self.dtype = getattr(self.torch, self.config.dtype)
        self.body_model = body_model if body_model is not None else self._load_body_model()
        if hasattr(self.body_model, "to"):
            self.body_model = self.body_model.to(device=self.device)
        self.faces = np.asarray(getattr(self.body_model, "faces", []), dtype=np.int32)

    def fit(
        self,
        coco_joints_mm,
        confidences=None,
        *,
        previous_result: Optional[SmplFitResult] = None,
        betas: np.ndarray | None = None,
    ) -> SmplFitResult:
        targets = extract_smpl_targets(
            coco_joints_mm,
            confidences,
            min_confidence=self.config.min_confidence,
            include_head=self.config.include_head,
        )
        if len(targets.smpl_indices) < 4:
            raise ValueError("SMPL fitting needs at least 4 reliable COCO joints")

        torch = self.torch
        scale = float(self.config.model_units_to_mm)
        target = torch.as_tensor(targets.points_mm, dtype=self.dtype, device=self.device)
        weights = torch.as_tensor(targets.weights, dtype=self.dtype, device=self.device).view(1, -1, 1)
        smpl_indices = torch.as_tensor(targets.smpl_indices, dtype=torch.long, device=self.device)

        global_init = _fixed_vector(
            previous_result.global_orient if previous_result is not None else None,
            3,
        )
        body_pose_init = _fixed_vector(
            previous_result.body_pose if previous_result is not None else None,
            69,
        )
        global_orient = torch.as_tensor(
            global_init.reshape(1, 3),
            dtype=self.dtype,
            device=self.device,
        ).clone().detach().requires_grad_(True)
        body_pose = torch.as_tensor(
            body_pose_init.reshape(1, 69),
            dtype=self.dtype,
            device=self.device,
        ).clone().detach().requires_grad_(True)
        if betas is not None:
            beta_init = _fixed_vector(betas, int(self.config.num_betas)).reshape(1, -1)
        elif previous_result is not None:
            beta_init = _fixed_vector(previous_result.betas, int(self.config.num_betas)).reshape(1, -1)
        else:
            beta_init = np.zeros((1, self.config.num_betas), dtype=np.float32)
        beta_tensor = torch.as_tensor(beta_init, dtype=self.dtype, device=self.device).clone().detach()
        beta_tensor.requires_grad_(bool(self.config.optimize_betas))

        with torch.no_grad():
            zero_transl = torch.zeros((1, 3), dtype=self.dtype, device=self.device)
            base_output = self._forward(global_orient, body_pose, beta_tensor, zero_transl)
            base_joints_mm = base_output.joints[:, smpl_indices, :] * scale
            weight_sum = torch.clamp(weights.sum(), min=1.0)
            target_center = (target.view(1, -1, 3) * weights).sum(dim=1) / weight_sum
            base_center = (base_joints_mm * weights).sum(dim=1) / weight_sum
            initial_trans_mm = (target_center - base_center).detach().cpu().numpy()[0]
        transl = torch.as_tensor(
            (initial_trans_mm / scale).reshape(1, 3),
            dtype=self.dtype,
            device=self.device,
        ).clone().detach().requires_grad_(True)

        params = [global_orient, body_pose, transl]
        if beta_tensor.requires_grad:
            params.append(beta_tensor)
        optimizer = torch.optim.Adam(params, lr=float(self.config.learning_rate))

        last_loss = None
        for _ in range(max(1, int(self.config.max_iters))):
            optimizer.zero_grad()
            output = self._forward(global_orient, body_pose, beta_tensor, transl)
            joints_mm = output.joints[:, smpl_indices, :] * scale
            joint_loss = ((joints_mm - target.view(1, -1, 3)) ** 2 * weights).sum()
            joint_loss = joint_loss / torch.clamp(weights.sum(), min=1.0)
            loss = joint_loss
            loss = loss + float(self.config.pose_reg_weight) * (body_pose ** 2).mean()
            loss = loss + float(self.config.shape_reg_weight) * (beta_tensor ** 2).mean()
            if previous_result is not None and float(self.config.temporal_weight) > 0:
                prev_pose = torch.as_tensor(
                    previous_result.body_pose.reshape(1, -1),
                    dtype=self.dtype,
                    device=self.device,
                )
                loss = loss + float(self.config.temporal_weight) * ((body_pose - prev_pose) ** 2).mean()
            if (
                self.config.floor_z_mm is not None
                and float(self.config.floor_penalty_weight) > 0
                and hasattr(output, "vertices")
            ):
                vertices_mm = output.vertices * scale
                below = torch.relu(float(self.config.floor_z_mm) - vertices_mm[:, :, 2])
                loss = loss + float(self.config.floor_penalty_weight) * (below ** 2).mean()
            loss.backward()
            optimizer.step()
            last_loss = float(loss.detach().cpu().item())

        with torch.no_grad():
            output = self._forward(global_orient, body_pose, beta_tensor, transl)
            vertices_mm = output.vertices.detach().cpu().numpy()[0] * scale
            joints_mm_all = output.joints.detach().cpu().numpy()[0] * scale
        return SmplFitResult(
            vertices_mm=np.asarray(vertices_mm, dtype=np.float64),
            joints_mm=np.asarray(joints_mm_all, dtype=np.float64),
            faces=self.faces.copy(),
            translation_mm=transl.detach().cpu().numpy()[0] * scale,
            global_orient=global_orient.detach().cpu().numpy()[0],
            body_pose=body_pose.detach().cpu().numpy()[0],
            betas=beta_tensor.detach().cpu().numpy()[0],
            loss=float(last_loss if last_loss is not None else np.nan),
            target_count=int(len(targets.smpl_indices)),
        )

    def _forward(self, global_orient, body_pose, betas, transl):
        return self.body_model(
            global_orient=global_orient,
            body_pose=body_pose,
            betas=betas,
            transl=transl,
            return_verts=True,
        )

    def _load_body_model(self):
        if not self.config.model_path:
            raise ValueError("SmplFitter requires model_path when body_model is not injected")
        model_path = Path(self.config.model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"SMPL model path does not exist: {model_path}")
        try:
            import smplx  # type: ignore
        except Exception as exc:  # pragma: no cover - environment dependent
            raise OptionalAvatarDependencyError(
                "Install optional avatar dependencies, including smplx, to load SMPL models"
            ) from exc
        return smplx.create(
            str(model_path),
            model_type=self.config.model_type,
            gender=self.config.gender,
            num_betas=int(self.config.num_betas),
            batch_size=1,
        )


class SmplSessionFitter:
    """Session-level fitter that calibrates shape once, then locks betas."""

    def __init__(
        self,
        config: Optional[SmplFitConfig] = None,
        *,
        body_model=None,
        shape_calibration_frames: int = 30,
    ):
        self.config = config or SmplFitConfig()
        self.shape_calibration_frames = max(0, int(shape_calibration_frames))
        shape_config = replace(self.config, optimize_betas=True)
        pose_config = replace(self.config, optimize_betas=False)
        self._shape_fitter = SmplFitter(shape_config, body_model=body_model)
        self._pose_fitter = SmplFitter(pose_config, body_model=self._shape_fitter.body_model)
        self.stable_betas: np.ndarray | None = None
        self.calibration_count = 0
        self.last_result: SmplFitResult | None = None

    @property
    def shape_locked(self) -> bool:
        return self.calibration_count >= self.shape_calibration_frames

    def reset(self) -> None:
        self.stable_betas = None
        self.calibration_count = 0
        self.last_result = None

    def fit(self, coco_joints_mm, confidences=None) -> SmplFitResult:
        if not self.shape_locked:
            result = self._shape_fitter.fit(
                coco_joints_mm,
                confidences,
                previous_result=self.last_result,
                betas=self.stable_betas,
            )
            self._update_stable_betas(result.betas)
            self.calibration_count += 1
            result = replace(result, betas=self.stable_betas.copy())
        else:
            result = self._pose_fitter.fit(
                coco_joints_mm,
                confidences,
                previous_result=self.last_result,
                betas=self.stable_betas,
            )
        self.last_result = result
        return result

    def _update_stable_betas(self, betas) -> None:
        beta_arr = _fixed_vector(betas, int(self.config.num_betas)).astype(np.float64)
        if self.stable_betas is None:
            self.stable_betas = beta_arr
            return
        n = float(max(0, self.calibration_count))
        self.stable_betas = ((self.stable_betas * n) + beta_arr) / (n + 1.0)


def _load_torch():
    try:
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise OptionalAvatarDependencyError(
            "Install torch to use SMPL avatar fitting"
        ) from exc
    return torch


def _fixed_vector(values, length: int) -> np.ndarray:
    out = np.zeros((int(length),), dtype=np.float32)
    if values is None:
        return out
    arr = np.asarray(values, dtype=np.float32).reshape(-1)
    n = min(len(out), len(arr))
    out[:n] = arr[:n]
    out[~np.isfinite(out)] = 0.0
    return out
