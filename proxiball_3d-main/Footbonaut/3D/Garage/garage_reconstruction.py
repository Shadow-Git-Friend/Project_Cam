"""
garage_reconstruction.py
Multi-camera triangulation for the Garage 4-camera setup.

Camera coordinate system:
  - Intrinsics: unified_intrinsics.json  (shared K, D, 1920x1080)
  - Extrinsics: extrinsics_1.json        (per-cam rvec, tvec;  units = cm)

Public API:
    rec = GarageReconstructor(intrinsics_path, extrinsics_path)
    pt3d = rec.triangulate({
        "camEast":  (u, v),
        "camNorth": (u, v),
        ...
    })
    # Returns np.array([X, Y, Z]) in METERS, or None if < 2 cams.
"""
import json
import cv2
import numpy as np
from pathlib import Path


CM_TO_M = 0.01  # extrinsics tvec is in cm → convert to m


class GarageReconstructor:
    """Triangulate ball position from ≥2 cameras using DLT (linear LS)."""

    CAM_NAMES = ["camNorth", "camEast", "camSouth", "camWest"]

    def __init__(self, intrinsics_path: str, extrinsics_path: str):
        intr = json.loads(Path(intrinsics_path).read_text())
        extr = json.loads(Path(extrinsics_path).read_text())

        self.K    = np.array(intr["camera_matrix"], dtype=np.float64)
        self.dist = np.array(intr["dist_coeffs"],   dtype=np.float64).flatten()

        # Build projection matrices  P_i = K @ [R_i | t_i]
        # and store R, t per camera for undistortion
        # Sanity bounds: reject triangulation outside these world-coord extents (metres)
        # Arena is ~10x4x10 m; use generous ±25 m to catch genuine outliers only.
        self.x_bounds = (-25.0,  25.0)
        self.y_bounds = (-10.0,  15.0)
        self.z_bounds = (-25.0,  25.0)

        self.cameras = {}
        for name in self.CAM_NAMES:
            if name not in extr:
                continue
            d = extr[name]
            rvec = np.array(d["rvec"], dtype=np.float64).reshape(3, 1)
            tvec = np.array(d["tvec"], dtype=np.float64).reshape(3, 1) * CM_TO_M

            R, _  = cv2.Rodrigues(rvec)
            Rt    = np.hstack([R, tvec])           # 3×4
            P     = self.K @ Rt                    # 3×4

            self.cameras[name] = {"R": R, "t": tvec, "P": P, "Rt": Rt}

        print(f"[GarageReconstructor] Loaded {len(self.cameras)} cameras: "
              f"{list(self.cameras.keys())}")

    # ─────────────────────────────────────────────────────────────────────────
    def _undistort_point(self, u: float, v: float) -> np.ndarray:
        """Return normalised (un-distorted, un-projected) 2D point."""
        pt = np.array([[[u, v]]], dtype=np.float32)
        un = cv2.undistortPoints(pt, self.K, self.dist)  # → normalised coords
        return un[0, 0]   # (2,)

    # ─────────────────────────────────────────────────────────────────────────
    def triangulate(self, observations: dict) -> np.ndarray | None:
        """
        Triangulate 3D position from multiple 2D observations.

        Args:
            observations: { cam_name: (u, v) }  for all cameras that detected
                          the ball.  cam_name must be one of CAM_NAMES.

        Returns:
            np.ndarray shape (3,) in metres (world coords), or None if < 2 cams.
        """
        valid = {k: v for k, v in observations.items() if k in self.cameras}
        if len(valid) < 2:
            return None

        # Build DLT system  A x = 0  where x = [X,Y,Z,1]^T
        rows = []
        for cam_name, (u, v) in valid.items():
            P = self.cameras[cam_name]["P"]   # 3×4
            # Normalised observations (removes K & distortion)
            un = self._undistort_point(u, v)  # (x_n, y_n)
            # DLT equations:   x_n * P[2] - P[0]  and  y_n * P[2] - P[1]
            rows.append(un[0] * P[2] - P[0])
            rows.append(un[1] * P[2] - P[1])

        A = np.array(rows, dtype=np.float64)    # (2N, 4)
        _, _, Vt = np.linalg.svd(A)
        X4 = Vt[-1]                             # homogeneous solution
        if abs(X4[3]) < 1e-9:
            return None
        pt3d = X4[:3] / X4[3]                  # metres

        # Sanity check: reject points outside arena bounds
        if not (self.x_bounds[0] <= pt3d[0] <= self.x_bounds[1] and
                self.y_bounds[0] <= pt3d[1] <= self.y_bounds[1] and
                self.z_bounds[0] <= pt3d[2] <= self.z_bounds[1]):
            return None
        return pt3d

    # ─────────────────────────────────────────────────────────────────────────
    def reproject(self, pt3d: np.ndarray, cam_name: str) -> tuple:
        """
        Reproject a 3D point (metres) onto camera image.
        Returns (u, v) pixel coords.
        """
        cam  = self.cameras[cam_name]
        rvec, _  = cv2.Rodrigues(cam["R"])
        tvec = cam["t"]
        pts, _   = cv2.projectPoints(
            pt3d.reshape(1, 3).astype(np.float64),
            rvec, tvec, self.K, self.dist)
        return float(pts[0, 0, 0]), float(pts[0, 0, 1])

    # ─────────────────────────────────────────────────────────────────────────
    @property
    def camera_names(self):
        return list(self.cameras.keys())
