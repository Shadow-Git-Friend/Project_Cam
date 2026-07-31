# Runtime Safety Hardening — Design Spec

**Date:** 2026-07-13  
**Status:** Approved by the user's explicit `DO IT` request  
**Scope:** desktop child lifecycle, corrupt Face ID assets, and pose-driven launcher firing clearance

## Goal

Close the confirmed failure modes without changing protected triangulation,
world-axis, EMA, or legacy joint payload semantics. The desktop must remain
responsive while a pipeline stops, corrupt local biometric/model files must
disable Face ID cleanly, and no pose-driven path may transmit `shoot` unless a
fresh all-person snapshot proves that the commanded ballistic corridor is clear.

No camera, serial port, launcher, or other hardware is exercised as part of the
implementation. Aim-only remains the default mode.

## Chosen Architecture

### Desktop process lifecycle

The Control Center owns one child process group and one monotonically increasing
process generation. Child stdout is decoded explicitly as UTF-8 with replacement
for malformed bytes, so the reader cannot die and leave a full pipe blocking the
viewer.

Shutdown is a state machine:

1. first STOP sends `SIGINT` and starts a 10-second grace period;
2. a second STOP, or expiry, sends `SIGTERM` and starts a 3-second grace period;
3. a third STOP, or expiry, uses `SIGKILL` as the final containment action;
4. the window remains alive and continues draining output until the child exits;
5. closing the window enters the same shutdown state machine and destroys Tk only
   after process exit (or final containment).

Every timer and queued exit message carries the process object/generation. A stale
callback from an earlier launch cannot signal or clear a newer child.

The people-count widget uses a string value plus a pure parser. Disabled
multi-person mode resolves to one person; enabled values must be integers from 2
through 6. Invalid input is reported in the mission log instead of surfacing as a
Tk callback exception.

### Corrupt Face ID assets

`FaceGallery.load()` translates known archive/data failures (`OSError`, `EOFError`,
`ValueError`, and `zipfile.BadZipFile`) into an informative chained `ValueError`.
It does not silently convert a corrupt gallery into an empty gallery, because that
would hide biometric data loss.

YuNet and SFace construction are guarded separately. An OpenCV model-parse error
becomes a `ValueError` that names the failed model and path. The live viewer's
existing Face ID initialization boundary catches these expected errors and disables
only Face ID. Enrollment list/remove/save operations report a concise `[ERROR]` and
return a non-zero code rather than printing a traceback.

### All-person safety snapshot

The live viewer keeps the existing top-level `type: "joints"` packet and its
primary `joints` object unchanged. It adds a `safety` object to the same datagram:

```text
safety:
  schema: project_cam.firing_line.v1
  snapshot_ts: unix seconds
  frame: pose frame index
  geometry_id: world_mm
  y_mirrored: boolean
  mode: single_person | multi_person
  primary_track_id: integer
  primary_epoch: integer, incremented on every primary switch
  observed_person_count: integer
  people:
    - track_id: integer
      primary: boolean
      track_last_seen_frame: integer
      joints:
        <COCO name>:
          x_mm, y_mm, z_mm, conf, cams, last_seen_frame
```

All safety coordinates use the same UDP Y-mirror transform as the primary payload.
Names and face embeddings are deliberately absent: recognition is a label, never
fire authorization. Active tracks with no usable geometry are still represented,
so the launcher fails closed instead of treating an unlocalized person as absent.

### Shared firing-line evaluator

`src/project_cam/closed_loop/firing_line.py` is hardware-free and pure. It:

- validates schema, coordinate frame, timestamps, primary ID/epoch, and person
  geometry;
- samples the commanded ballistic path using launcher position/yaw, horizontal and
  vertical aim angles, exit speed, gravity, and a conservative post-target extension;
- models visible human bones as line segments (and isolated usable joints as points);
- computes the minimum 3D segment-to-segment distance between the swept trajectory
  and every non-primary body segment;
- returns a structured allow/block decision and diagnostic closest distance/track;
- blocks on missing, stale, malformed, wrong-frame, primary-changed, unlocalized
  secondary, or intersecting data.

The default corridor radius is deliberately conservative and configurable only
within launcher-side CLI limits. A clear result is valid for one immediate fire
decision; it is never cached as a long-lived authorization.

### Enforcement boundary

The four pose-driven serial fire sites re-evaluate the shared gate immediately
before sending `shoot`:

- `launcher_runtime_from_udp.py` operator and automatic paths;
- `live_aim_test.py` interactive path;
- `blm_follow.py` follow/voice path.

Each aim captures the current primary track ID and epoch. A primary change before
fire blocks the command, sends `stop`, invalidates the stored aim/armed state, and
requires a new aim. Missing safety telemetry blocks `--shoot-enabled`; aim-only
operation remains available. Raw supervised `blm_interactive.py` is not changed in
this phase.

## Alternatives Considered

1. **Chosen: additive safety snapshot plus launcher-side interlock.** It preserves
   the legacy joint consumer contract, synchronizes occupancy and pose in one UDP
   packet, and lets the component that owns the actual aim command decide safety.
2. **Viewer-computed `clearance_ok`.** Rejected as an authorization source because
   the viewer does not own the final corrected angles/speed, and a boolean can be
   stale after a primary switch. It may later be useful for UI only.
3. **Separate safety UDP port.** Rejected for this phase because two independent
   datagrams create synchronization, configuration, and packet-loss ambiguity.
4. **Single hardware-owner launcher daemon.** This is the preferred end-state, but
   migrating every current script to intent messages is a larger architectural
   change. The shared pure gate introduced here is reusable by that daemon.

## Failure Policy And Logging

Every uncertainty is a block, never an implicit allow. A blocked fire sends no
`shoot`; if wheels may be active it sends `stop` and clears the stored aim. Logs
contain the source, reason code, primary ID/epoch, safety age, person count, closest
track/distance, angles/speed, and whether a serial shoot was actually transmitted.
No biometric name or embedding is written to safety logs.

## Verification

- Desktop unit/integration tests inject malformed bytes, invalid spinbox values,
  hung children, repeated STOP, stale timers, and close-during-recording behavior.
- Face tests use zero-byte/truncated galleries and monkeypatched OpenCV constructors;
  no ONNX inference is required.
- Geometry tests cover clear paths, crossing limbs, isolated points, stale/missing
  snapshots, primary epoch changes, unlocalized people, mirrored metadata, and
  degenerate/malformed inputs.
- Script contract tests prove every pose-driven `shoot` site calls the shared gate
  and remains disabled without a fresh safety snapshot.
- Focused and full regression suites run without cameras or launcher hardware.

## Out Of Scope

- Face liveness or biometric access control.
- Re-identification after long occlusion.
- Tracker sprint-duplication/performance work (confirmed, but separate from this
  P0 patch so the safety boundary lands first).
- Automatic hardware validation or enabling `--shoot-enabled` by default.
- Migration to a sole launcher daemon.
