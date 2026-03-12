#!/usr/bin/env python3
"""Detect a ball with YOLO and triangulate its 3-D position across cameras."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np
import torch.nn as nn
from ultralytics import YOLO

from calibration_utils import Intrinsics, load_all_intrinsics, load_extrinsics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run YOLO ball detection on synchronized captures and triangulate the ball."
    )
    parser.add_argument(
        "--pairs-file",
        type=Path,
        required=True,
        help="JSON describing synchronized captures (same format as extrinsics_pairs_template.json).",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        required=True,
        help="Path to the YOLO weights file (e.g., weights/ball/best.pt).",
    )
    parser.add_argument(
        "--intrinsics-dir",
        type=Path,
        default=Path("calibration_results"),
        help="Directory containing <camera>_intrinsics.json files.",
    )
    parser.add_argument(
        "--extrinsics",
        type=Path,
        default=Path("calibration_results/extrinsics.json"),
        help="Path to extrinsics.json.",
    )
    parser.add_argument(
        "--reference-camera",
        default=None,
        help="Reference camera name (defaults to the one stored in extrinsics.json).",
    )
    parser.add_argument(
        "--class-id",
        type=int,
        default=None,
        help="YOLO class id filter (default: use class name or all classes).",
    )
    parser.add_argument(
        "--class-name",
        type=str,
        default=None,
        help="Comma-separated class name(s) (case-insensitive) to keep, e.g. 'sports ball'.",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Confidence threshold passed to YOLO.",
    )
    parser.add_argument(
        "--iou",
        type=float,
        default=0.45,
        help="IoU threshold passed to YOLO.",
    )
    parser.add_argument(
        "--min-views",
        type=int,
        default=2,
        help="Minimum number of cameras that must detect the ball to triangulate.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("calibration_results/ball_triangulation.json"),
        help="Where to store detection + 3-D results.",
    )
    parser.add_argument(
        "--save-debug",
        type=Path,
        default=None,
        help="Optional directory to store detection overlays per camera.",
    )
    return parser.parse_args()


def ensure_custom_layers():
    """Register custom YOLO layers expected by the checkpoint."""
    try:
        import ultralytics.nn.modules.block as block
    except ImportError:
        return

    if not hasattr(block, "A2C2f"):
        block.A2C2f = block.C2f
    if not hasattr(block, "ABlock"):
        block.ABlock = block.C2f
    if not hasattr(block, "AAttn"):
        class AAttn(nn.Module):
            def __init__(self, *args, **kwargs):
                super().__init__()

            def forward(self, x):  # type: ignore[override]
                return x

        block.AAttn = AAttn


def resolve_class_ids(model, class_id: int | None, class_name: str | None):
    """Return list of class IDs to filter or None for all classes."""
    names = getattr(getattr(model, "model", None), "names", None)
    if names is None:
        names = getattr(model, "names", None)

    if class_name and names is not None:
        if isinstance(names, dict):
            lookup = {str(v).lower(): k for k, v in names.items()}
        else:
            lookup = {str(name).lower(): idx for idx, name in enumerate(names)}
        ids = []
        for token in class_name.split(","):
            token = token.strip().lower()
            if not token:
                continue
            if token not in lookup:
                raise ValueError(f"Class name '{token}' not found in model names {names}.")
            ids.append(int(lookup[token]))
        return ids if ids else None

    if class_id is not None:
        return [int(class_id)]

    return None


def load_captures(path: Path) -> List[Dict]:
    data = json.loads(path.read_text())
    return data.get("captures", [])


def build_projection_matrices(
    intrinsics: Dict[str, Intrinsics],
    extrinsics,
    reference_camera: str,
) -> Dict[str, np.ndarray]:
    projections = {}
    for cam_name, intr in intrinsics.items():
        if cam_name == reference_camera:
            world_to_cam = np.eye(4, dtype=np.float64)
        else:
            T_cam_to_ref = extrinsics[cam_name].matrix  # camera -> reference
            world_to_cam = np.linalg.inv(T_cam_to_ref)  # reference -> camera
        Rt = world_to_cam[:3, :]
        projections[cam_name] = intr.matrix @ Rt
    return projections


def triangulate_point(projections: List[Tuple[np.ndarray, float, float]]) -> np.ndarray:
    A = []
    for P, u, v in projections:
        A.append(u * P[2, :] - P[0, :])
        A.append(v * P[2, :] - P[1, :])
    A = np.asarray(A)
    _, _, Vt = np.linalg.svd(A)
    X = Vt[-1]
    X /= X[3]
    return X[:3]


def reprojection_error(
    point_world: np.ndarray,
    measurements: Dict[str, Tuple[np.ndarray, float, float]],
) -> float:
    errs = []
    homog = np.append(point_world, 1.0)
    for cam, (P, u, v) in measurements.items():
        proj = P @ homog
        proj /= proj[2]
        diff = np.array([u, v]) - proj[:2]
        errs.append(np.linalg.norm(diff))
    return float(np.mean(errs))


def draw_detection(frame: np.ndarray, box: np.ndarray, conf: float):
    x1, y1, x2, y2 = box.astype(int)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    label = f"ball {conf:.2f}"
    cv2.putText(frame, label, (x1, max(0, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)


def main() -> int:
    args = parse_args()
    ensure_custom_layers()

    captures = load_captures(args.pairs_file)
    if not captures:
        raise RuntimeError("Pairs file contains no captures.")

    intrinsics_map = load_all_intrinsics(args.intrinsics_dir)
    extrinsics = load_extrinsics(args.extrinsics)

    reference_camera = args.reference_camera or extrinsics[next(iter(extrinsics))].reference
    if reference_camera not in intrinsics_map:
        raise KeyError(f"Reference camera '{reference_camera}' missing from intrinsics.")

    projections = build_projection_matrices(intrinsics_map, extrinsics, reference_camera)

    model = YOLO(str(args.weights))
    class_filter = resolve_class_ids(model, args.class_id, args.class_name)

    debug_dir = args.save_debug
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)

    report = {"reference_camera": reference_camera, "captures": []}

    for capture in captures:
        cap_id = capture.get("id", "capture")
        measurements: Dict[str, Tuple[np.ndarray, float, float]] = {}
        capture_entry = {"id": cap_id, "detections": {}, "triangulated": None}

        for cam_name, image_path_str in capture.get("images", {}).items():
            image_path = Path(image_path_str)
            if cam_name not in intrinsics_map:
                capture_entry["detections"][cam_name] = {"error": "missing intrinsics"}
                continue
            if not image_path.exists():
                capture_entry["detections"][cam_name] = {"error": f"missing file {image_path}"}
                continue

            results = model.predict(
                source=str(image_path),
                conf=args.conf,
                iou=args.iou,
                classes=class_filter,
                verbose=False,
            )
            if not results:
                capture_entry["detections"][cam_name] = {"error": "no inference result"}
                continue
            boxes = results[0].boxes
            if boxes is None or boxes.shape[0] == 0:
                capture_entry["detections"][cam_name] = {"error": "no detections"}
                continue

            # Pick highest-confidence detection
            confs = boxes.conf.cpu().numpy()
            best_idx = int(np.argmax(confs))
            bbox = boxes.xyxy[best_idx].cpu().numpy()
            conf = float(confs[best_idx])
            cx = float((bbox[0] + bbox[2]) / 2.0)
            cy = float((bbox[1] + bbox[3]) / 2.0)

            measurements[cam_name] = (projections[cam_name], cx, cy)
            capture_entry["detections"][cam_name] = {
                "bbox": bbox.tolist(),
                "center": [cx, cy],
                "confidence": conf,
            }

            if debug_dir:
                frame = cv2.imread(str(image_path))
                draw_detection(frame, bbox, conf)
                out_path = debug_dir / f"{cap_id}_{cam_name}.jpg"
                cv2.imwrite(str(out_path), frame)

        if len(measurements) >= args.min_views:
            point_world = triangulate_point(list(measurements.values()))
            reproj = reprojection_error(point_world, measurements)
            capture_entry["triangulated"] = {
                "world_xyz_m": point_world.tolist(),
                "reproj_rms_px": reproj,
                "num_views": len(measurements),
            }
        else:
            capture_entry["triangulated"] = {
                "error": f"insufficient detections ({len(measurements)}/{args.min_views})"
            }

        report["captures"].append(capture_entry)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(f"Ball triangulation results saved to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
