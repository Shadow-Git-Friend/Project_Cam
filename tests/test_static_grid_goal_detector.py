import math
import sys
import unittest
from pathlib import Path

import numpy as np

PROJECTOR_DIR = Path(__file__).resolve().parents[1] / "proxiball_3d-main" / "projector"
sys.path.insert(0, str(PROJECTOR_DIR))

from static_grid_goal_logic import (  # noqa: E402
    SOUTH_WALL_U_MAX_MM,
    SOUTH_WALL_V_MAX_MM,
    SouthWallMapper,
    StaticGridGoalLogic,
    consensus_zone_from_wall_uv,
    find_rect_for_uv,
    intersect_ray_with_world_x,
    target_grid_rectangles,
    temporal_consensus_zone,
    wall_bounds_from_homography,
)


class StaticGridGoalDetectorTests(unittest.TestCase):
    def test_remounted_south_wall_mapper_roundtrips_projected_grid_points(self):
        project_root = Path(__file__).resolve().parents[1]
        intrinsics_dir = project_root / "Remounted_West_East/cal/intrinsics"
        extrinsics = project_root / "Remounted_West_East/cal/extrinsics/extrinsics_fixed.json"
        if not intrinsics_dir.exists() or not extrinsics.exists():
            self.skipTest("Remounted_West_East calibration bundle is not present")

        rects = {r.label: r for r in target_grid_rectangles(
            SOUTH_WALL_U_MAX_MM,
            SOUTH_WALL_V_MAX_MM,
        )}
        for cam in ("camNorth", "camEast", "camWest"):
            mapper = SouthWallMapper.from_files(
                intrinsics_dir / f"{cam}_intrinsics.json",
                extrinsics,
                cam_role=cam,
            )
            for label in ("A1", "B2", "C3"):
                with self.subTest(cam=cam, label=label):
                    expected_u, expected_v = rects[label].center
                    px = mapper.wall_to_pixel(expected_u, expected_v)
                    mapped = mapper.pixel_to_wall(px)
                    self.assertIsNotNone(mapped)
                    got_u, got_v, _ = mapped
                    self.assertAlmostEqual(got_u, expected_u, delta=5.0)
                    self.assertAlmostEqual(got_v, expected_v, delta=5.0)

    def test_consensus_zone_requires_two_cameras_in_same_zone(self):
        rects = target_grid_rectangles()
        a1 = next(r for r in rects if r.label == "A1")
        b2 = next(r for r in rects if r.label == "B2")

        result = consensus_zone_from_wall_uv(
            rects,
            {
                "camNorth": a1.center,
                "camEast": (a1.center[0] + 30.0, a1.center[1] + 20.0),
                "camWest": b2.center,
            },
            min_cams=2,
            pad_mm=100.0,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.zone_label, "A1")
        self.assertEqual(result.voting_cams, ("camEast", "camNorth"))
        self.assertAlmostEqual(result.u_mm, a1.center[0] + 15.0, delta=0.1)
        self.assertAlmostEqual(result.v_mm, a1.center[1] + 10.0, delta=0.1)

        one_cam = consensus_zone_from_wall_uv(
            rects,
            {"camNorth": a1.center},
            min_cams=2,
            pad_mm=100.0,
        )
        self.assertIsNone(one_cam)

        split_votes = consensus_zone_from_wall_uv(
            rects,
            {
                "camNorth": a1.center,
                "camEast": b2.center,
            },
            min_cams=2,
            pad_mm=100.0,
        )
        self.assertIsNone(split_votes)

    def test_temporal_consensus_combines_recent_distinct_camera_votes(self):
        result = temporal_consensus_zone(
            [
                (10.00, "camNorth", "A1", 800.0, 900.0),
                (10.09, "camEast", "A1", 860.0, 930.0),
                (10.12, "camNorth", "A2", 1400.0, 900.0),
            ],
            now=10.12,
            window_s=0.15,
            min_cams=2,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.zone_label, "A1")
        self.assertEqual(result.voting_cams, ("camEast", "camNorth"))
        self.assertAlmostEqual(result.u_mm, 830.0, delta=0.1)
        self.assertAlmostEqual(result.v_mm, 915.0, delta=0.1)

        stale = temporal_consensus_zone(
            [
                (9.80, "camNorth", "A1", 800.0, 900.0),
                (10.09, "camEast", "A1", 860.0, 930.0),
            ],
            now=10.12,
            window_s=0.15,
            min_cams=2,
        )
        self.assertIsNone(stale)

    def test_target_grid_rectangles_match_projector_sim_geometry(self):
        rects = target_grid_rectangles(u_max=3050.0, v_max=2950.0)

        self.assertEqual(
            [r.label for r in rects],
            [
                "A1", "A2", "A3",
                "B1", "B2", "B3",
                "C1", "C2", "C3",
            ],
        )
        self.assertEqual(len(rects), 9)

        first = rects[0]
        self.assertEqual(first.label, "A1")
        self.assertTrue(math.isclose(first.u_min, 286.7, abs_tol=0.1))
        self.assertTrue(math.isclose(first.u_max, 1055.3, abs_tol=0.1))
        self.assertTrue(math.isclose(first.v_min, 214.3667, abs_tol=0.1))
        self.assertTrue(math.isclose(first.v_max, 886.9667, abs_tol=0.1))

        self.assertEqual(find_rect_for_uv(rects, 600.0, 500.0).label, "A1")
        self.assertIsNone(find_rect_for_uv(rects, 50.0, 50.0))

    def test_projector_bounds_keep_grid_inside_calibrated_wall_area(self):
        project_root = Path(__file__).resolve().parents[1]
        bounds = wall_bounds_from_homography(
            project_root / "proxiball_3d-main/projector/homography.json"
        )
        self.assertIsNotNone(bounds)

        rects = target_grid_rectangles(
            u_min=bounds.u_min,
            u_max=bounds.u_max,
            v_min=bounds.v_min,
            v_max=bounds.v_max,
        )

        for rect in rects:
            self.assertGreaterEqual(rect.u_min, bounds.u_min)
            self.assertLessEqual(rect.u_max, bounds.u_max)
            self.assertGreaterEqual(rect.v_min, bounds.v_min)
            self.assertLessEqual(rect.v_max, bounds.v_max)

    def test_intersect_ray_with_world_x_plane_uses_world_to_camera_extrinsics(self):
        point = intersect_ray_with_world_x(
            normalized_uv=(1.0, 0.0),
            R=np.eye(3),
            tvec=np.zeros((3, 1)),
            x_mm=10.0,
        )

        np.testing.assert_allclose(point, np.array([10.0, 0.0, 10.0]))

    def test_goal_triggers_on_sudden_deceleration_inside_grid_cell(self):
        logic = StaticGridGoalLogic(
            rects=target_grid_rectangles(),
            min_flight_speed_mm_s=1500.0,
            decel_ratio=0.40,
            cooldown_s=0.5,
        )

        self.assertIsNone(logic.update(t_sec=0.0, u_mm=80.0, v_mm=250.0))
        self.assertIsNone(logic.update(t_sec=0.10, u_mm=600.0, v_mm=500.0))

        event = logic.update(t_sec=0.20, u_mm=620.0, v_mm=510.0)

        self.assertIsNotNone(event)
        self.assertEqual(event.zone_label, "A1")
        self.assertEqual(event.u_mm, 620.0)
        self.assertEqual(event.v_mm, 510.0)
        self.assertGreater(event.peak_speed_mm_s, 1500.0)
        self.assertLess(event.speed_mm_s, 0.40 * event.peak_speed_mm_s)

    def test_goal_logic_requires_grid_overlap_and_cooldown(self):
        logic = StaticGridGoalLogic(
            rects=target_grid_rectangles(),
            min_flight_speed_mm_s=1000.0,
            decel_ratio=0.50,
            cooldown_s=0.8,
        )

        self.assertIsNone(logic.update(t_sec=0.00, u_mm=10.0, v_mm=10.0))
        self.assertIsNone(logic.update(t_sec=0.10, u_mm=80.0, v_mm=20.0))
        self.assertIsNone(logic.update(t_sec=0.20, u_mm=85.0, v_mm=22.0))

        self.assertIsNone(logic.update(t_sec=1.00, u_mm=80.0, v_mm=250.0))
        self.assertIsNone(logic.update(t_sec=1.10, u_mm=600.0, v_mm=500.0))
        first = logic.update(t_sec=1.20, u_mm=620.0, v_mm=510.0)
        self.assertIsNotNone(first)

        duplicate = logic.update(t_sec=1.30, u_mm=621.0, v_mm=511.0)
        self.assertIsNone(duplicate)


if __name__ == "__main__":
    unittest.main()
