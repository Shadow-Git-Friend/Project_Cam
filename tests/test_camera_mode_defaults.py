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


class CameraModeDefaultsTests(unittest.TestCase):
    def test_charuco_auto_capture_defaults_to_fullhd_30fps(self):
        module = load_script("garage_lab_combined/scripts/auto_capture_charuco_multi.py")

        args = module.build_arg_parser().parse_args([])

        self.assertEqual(args.width, 1920)
        self.assertEqual(args.height, 1080)
        self.assertEqual(args.fps, 30)
        self.assertEqual(args.fourcc, "MJPG")

    def test_short_clip_recorder_defaults_to_fullhd_30fps(self):
        module = load_script("garage_lab_combined/scripts/record_short_clips_multi.py")

        args = module.build_arg_parser().parse_args([])

        self.assertEqual(args.width, 1920)
        self.assertEqual(args.height, 1080)
        self.assertEqual(args.fps, 30)
        self.assertEqual(args.in_fourcc, "MJPG")

    def test_joint_trial_recorder_defaults_to_fullhd_30fps(self):
        module = load_script("garage_lab_combined/scripts/auto_record_joint_trials.py")

        args = module.build_arg_parser().parse_args([
            "--trials-csv",
            "trials.csv",
            "--out-dir",
            "clips",
        ])

        self.assertEqual(args.width, 1920)
        self.assertEqual(args.height, 1080)
        self.assertEqual(args.fps, 30)
        self.assertEqual(args.in_fourcc, "MJPG")


if __name__ == "__main__":
    unittest.main()
