import importlib.util
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_script(relative_path):
    path = PROJECT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Usb6CaptureGateHelperTests(unittest.TestCase):
    def setUp(self):
        self.module = load_script("scripts/usb6_capture_gate.py")

    def test_extract_usb_controller_from_v4l2_bus_info(self):
        self.assertEqual(
            self.module.extract_usb_controller("usb-0000:00:14.0-6.1.1.1"),
            "0000:00:14.0",
        )

    def test_evaluate_usb_split_flags_single_controller(self):
        info = {
            "camA": {"controller": "0000:00:14.0", "card": "HD Pro Webcam C920"},
            "camB": {"controller": "0000:00:14.0", "card": "1080P USB Camera"},
        }
        result = self.module.evaluate_usb_split(info)

        self.assertTrue(result["all_on_one_controller"])
        self.assertEqual(result["controller_count"], 1)

    def test_evaluate_usb_split_passes_multiple_controllers(self):
        info = {
            "camA": {"controller": "0000:00:14.0", "card": "HD Pro Webcam C920"},
            "camB": {"controller": "0000:06:00.0", "card": "1080P USB Camera"},
        }
        result = self.module.evaluate_usb_split(info)

        self.assertFalse(result["all_on_one_controller"])
        self.assertEqual(result["controller_count"], 2)

    def test_capture_pass_requires_open_fps_and_gap(self):
        capture = {
            "camA": {"opened": True, "fresh_fps": 18.0, "max_gap_ms": 80.0},
            "camB": {"opened": True, "fresh_fps": 22.0, "max_gap_ms": 60.0},
        }
        self.assertTrue(self.module.capture_passed(capture, min_fps=15.0, max_gap_ms=100.0))

        capture["camB"]["max_gap_ms"] = 140.0
        self.assertFalse(self.module.capture_passed(capture, min_fps=15.0, max_gap_ms=100.0))


class IntrinsicsGateHelperTests(unittest.TestCase):
    def setUp(self):
        self.module = load_script("scripts/validate_intrinsics_gate.py")

    def test_check_intrinsics_payload_accepts_matching_resolution(self):
        payload = {
            "camera_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "distortion_coefficients": [0, 0, 0, 0, 0],
            "image_width": 1280,
            "image_height": 720,
            "reprojection_error": 0.8,
            "frames_used": 20,
        }

        ok, reasons = self.module.check_intrinsics_payload(payload, 1280, 720, 2.0)

        self.assertTrue(ok)
        self.assertEqual(reasons, [])

    def test_check_intrinsics_payload_rejects_resolution_mismatch(self):
        payload = {
            "camera_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "dist_coeffs": [0, 0, 0, 0, 0],
            "image_width": 1920,
            "image_height": 1080,
            "reprojection_error": 0.8,
            "frames_used": 20,
        }

        ok, reasons = self.module.check_intrinsics_payload(payload, 1280, 720, 2.0)

        self.assertFalse(ok)
        self.assertIn("resolution mismatch: got 1920x1080, expected 1280x720", reasons)

    def test_check_intrinsics_payload_rejects_high_reprojection(self):
        payload = {
            "camera_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "distortion_coefficients": [0, 0, 0, 0, 0],
            "image_width": 1280,
            "image_height": 720,
            "reprojection_error": 4.2,
            "frames_used": 20,
        }

        ok, reasons = self.module.check_intrinsics_payload(payload, 1280, 720, 2.0)

        self.assertFalse(ok)
        self.assertIn("reprojection too high: 4.200px > 2.000px", reasons)


if __name__ == "__main__":
    unittest.main()
