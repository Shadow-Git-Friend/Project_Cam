# Projector Goal Detection Log - 2026-05-28

## Summary

This update adds the static 3x3 projector goal detection pipeline from
`proxiball_3d-main/projector/` and wires it to the post-remount calibration in
`Remounted_West_East/`.

The active runtime entrypoint is:

```bash
./proxiball_3d-main/projector/run_goal_target_multicam.sh
```

## What Changed

- Added a multicam projector game that renders the 3x3 target grid and scores
  hits/misses from ball detections.
- Fixed south-wall pixel-to-wall mapping for the remounted calibration bundle,
  including calibration bundles where visible points use negative camera-space
  depth.
- Switched hit logic to per-camera south-wall projection with consensus voting;
  3D triangulation is retained for diagnostics only.
- Added temporal consensus over recent camera votes to tolerate async camera
  timing during fast shots.
- Added debug output and optional JSONL logging for detections, wall projections,
  zone votes, consensus source, and no-hit reasons.
- Removed automatic/borderless fullscreen behavior from the multicam launcher so
  the projector game opens as a normal resizable window. The operator can drag it
  to the projector and maximize it manually.

## Display Notes

Current detected display layout:

```text
HDMI-1-0  1920x1200+0+0     PC monitor
DP-1-2    1920x1080+1920+0  projector
```

The launcher defaults to `PROJECTOR_OUTPUT=DP-1-2`, but the pygame projector
window is now decorated/resizable so it can be moved manually if the window
manager places it on the wrong screen.

If the projector output name changes:

```bash
PROJECTOR_OUTPUT=<xrandr-output-name> ./proxiball_3d-main/projector/run_goal_target_multicam.sh
```

## Detection And Scoring Notes

- YOLO model: `models/ball/yolo26m-672.engine`
- Default multicam ball threshold: `--ball-conf 0.20`
- Default max ball box side: `--max-box-side-px 220`
- Default consensus requirement: `--min-consensus-cams 2`
- Default temporal vote window: `--consensus-window-s 0.25`
- Grid bounds are derived from `proxiball_3d-main/projector/homography.json`.
- `homography.json` metadata still reports `1920x1200`; current projector output
  is `1920x1080`, so a future projector recalibration is recommended if the
  projected rectangles do not line up physically.

## Runtime Logs

Raw runtime JSONL logs were intentionally left outside git:

```text
/tmp/goal_debug.jsonl
/tmp/goal_debug2.jsonl
```

Observed from `/tmp/goal_debug.jsonl`:

- Ball detections were present across all cameras.
- Wall projection did not fail.
- The dominant failure reason was `no-consensus`, which led to the temporal
  consensus change.

## Verification

Focused verification commands:

```bash
./venv/bin/python tests/test_static_grid_goal_detector.py
./venv/bin/python proxiball_3d-main/projector/goal_target_game_multicam.py --help
```

Expected live smoke test:

```bash
./proxiball_3d-main/projector/run_goal_target_multicam.sh \
  --debug-log-jsonl /tmp/goal_debug_next.jsonl
```

During a live run, the terminal should print periodic `[DBG]` and `[VOTE]`
lines. The operator window should show per-camera wall `U/V`, zone votes, and
the current no-hit reason.
