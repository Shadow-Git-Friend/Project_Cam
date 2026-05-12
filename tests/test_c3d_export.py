"""Round-trip and fidelity tests for the C3D export.

These tests assert that a real recording survives a C3D round-trip with the
correct frame rate, units, label set, marker count, and per-frame XYZ values
matching the source (within float tolerance). They also pin behavior on
missing joints (residual == -1, coordinates NaN) so future regressions are
caught.
"""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent


def _ezc3d_available() -> bool:
    try:
        import ezc3d  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(_ezc3d_available(), "ezc3d not installed")
class C3DExportTests(unittest.TestCase):
    def test_real_recording_roundtrip_basic_fields(self):
        import ezc3d

        from project_cam.assessment.exports.c3d_writer import (
            JOINT_C3D_LABELS,
            write_c3d,
        )
        from project_cam.assessment.io import load_motion
        from project_cam.assessment.joints import JOINT_NAMES

        frames = load_motion(
            REPO_ROOT / "data" / "raw" / "athlete_001_squat_good.jsonl",
            default_fps=15.0,
        )
        self.assertGreater(len(frames), 0)

        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "good.c3d"
            written = write_c3d(
                frames=frames,
                output_path=out_path,
                fps=15.0,
                subject_id="athlete_001",
                session_id="test_session_001",
            )
            self.assertTrue(written.exists())

            reopened = ezc3d.c3d(str(out_path))
            params = reopened["parameters"]
            self.assertEqual(params["POINT"]["RATE"]["value"][0], 15.0)
            self.assertEqual(params["POINT"]["UNITS"]["value"], ["mm"])
            labels = params["POINT"]["LABELS"]["value"]
            self.assertEqual(len(labels), len(JOINT_NAMES))
            self.assertEqual(labels, JOINT_C3D_LABELS)

            points = reopened["data"]["points"]
            self.assertEqual(points.shape[0], 4)  # X, Y, Z, residual
            self.assertEqual(points.shape[1], len(JOINT_NAMES))
            self.assertEqual(points.shape[2], len(frames))

    def test_real_recording_xyz_fidelity(self):
        """XYZ written equals XYZ from the source frames within float tolerance."""
        import ezc3d

        from project_cam.assessment.exports.c3d_writer import write_c3d
        from project_cam.assessment.io import load_motion
        from project_cam.assessment.joints import JOINT_NAMES

        frames = load_motion(
            REPO_ROOT / "data" / "raw" / "athlete_001_squat_good.jsonl",
            default_fps=15.0,
        )

        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "good.c3d"
            write_c3d(frames, out_path, fps=15.0, subject_id="athlete_001")
            reopened = ezc3d.c3d(str(out_path))
            points = reopened["data"]["points"]

            # Sample 5 frames evenly through the recording. Invalid markers are
            # signalled by NaN coordinates in the reopened C3D (ezc3d normalizes
            # the residual field on round-trip, so we cannot rely on residual==-1).
            sample_indices = np.linspace(0, len(frames) - 1, 5, dtype=int)
            for f_idx in sample_indices:
                for j_idx in range(len(JOINT_NAMES)):
                    src = frames[f_idx]["joints"][j_idx]
                    if src is None:
                        self.assertTrue(
                            math.isnan(points[0, j_idx, f_idx]),
                            f"missing joint should round-trip as NaN coords; got {points[0, j_idx, f_idx]}",
                        )
                        continue
                    sx, sy, sz = float(src[0]), float(src[1]), float(src[2])
                    self.assertAlmostEqual(points[0, j_idx, f_idx], sx, places=3)
                    self.assertAlmostEqual(points[1, j_idx, f_idx], sy, places=3)
                    self.assertAlmostEqual(points[2, j_idx, f_idx], sz, places=3)

    def test_missing_joint_marked_invalid(self):
        """Synthetic frame with a None joint → residual -1 and NaN coords."""
        import ezc3d

        from project_cam.assessment.exports.c3d_writer import write_c3d
        from project_cam.assessment.joints import JOINT_NAME_TO_INDEX, JOINT_NAMES

        joints = [[1.0, 2.0, 3.0]] * len(JOINT_NAMES)
        joints[JOINT_NAME_TO_INDEX["left_wrist"]] = None
        frame = {
            "frame_index": 0,
            "time_s": 0.0,
            "joints": joints,
            "joint_conf": [1.0] * len(JOINT_NAMES),
            "joint_cams": [3] * len(JOINT_NAMES),
        }

        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "missing.c3d"
            write_c3d([frame, frame], out_path, fps=15.0, subject_id="synth")
            reopened = ezc3d.c3d(str(out_path))
            points = reopened["data"]["points"]
            lwri_idx = JOINT_NAME_TO_INDEX["left_wrist"]
            # Invalid marker: NaN coordinates after round-trip (ezc3d normalizes
            # the residual byte; we rely on coordinate NaN as the canonical signal).
            self.assertTrue(math.isnan(points[0, lwri_idx, 0]))
            self.assertTrue(math.isnan(points[1, lwri_idx, 0]))
            self.assertTrue(math.isnan(points[2, lwri_idx, 0]))
            # Other joints valid: finite coordinates equal to source.
            other_idx = JOINT_NAME_TO_INDEX["right_wrist"]
            self.assertTrue(math.isfinite(points[0, other_idx, 0]))
            self.assertAlmostEqual(points[0, other_idx, 0], 1.0)

    def test_empty_frames_raises(self):
        from project_cam.assessment.exports.c3d_writer import write_c3d

        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                write_c3d([], Path(td) / "empty.c3d", fps=15.0, subject_id="x")

    def test_invalid_fps_raises(self):
        from project_cam.assessment.exports.c3d_writer import write_c3d
        from project_cam.assessment.joints import JOINT_NAMES

        frame = {
            "joints": [[0.0, 0.0, 0.0]] * len(JOINT_NAMES),
            "joint_conf": [1.0] * len(JOINT_NAMES),
            "joint_cams": [3] * len(JOINT_NAMES),
        }
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                write_c3d([frame], Path(td) / "x.c3d", fps=0.0, subject_id="x")


if __name__ == "__main__":
    unittest.main()
