# Adaptive Weakness Arena — 5-min Football Biomech Game (Design Spec)

**Date:** 2026-05-14
**Status:** Brainstorm complete, awaiting user review before implementation plan
**Scope:** New module `src/project_cam/training_session/` + extensions to
`configs/exercises/football_academy_u10.yaml`, `garage_lab_combined/scripts/blm_follow.py`,
and `Parallel_working/scripts/live_4cam_arena_view_parallel.py` (decouple compute from UI).
**Audience:** FC Kairat U10–U14 youth academy + thesis defense follow-on + investor demo.

---

## Problem

Three pressures need one answer:

1. **FC Kairat / youth academies** want measurable injury-risk screening (knee valgus,
   asymmetry — top predictors of ACL injury at academy level) but currently buy clinical
   tools (Vald ForceDecks, $20k+) that are unengaging for 10-14 year olds and don't
   integrate with on-pitch training.
2. **Investors / scout demos** need a 5-minute experience that's both visually
   memorable and credibly scientific — not just a tech demo.
3. **Thesis defense feedback** indicated the engineering panel wants hardware/system
   integration narrative, and a PhD CV examiner expects stratified diagnostic output.

The existing Project_Cam stack has all the heavy biomech infrastructure
(`src/project_cam/assessment/`, `src/project_cam/closed_loop/`, EventLogger, C3D export,
maturity offset, joint-angle kinematics with tuned thresholds, ball+pose+launcher
closed loop) but **no orchestrated demo experience** that exposes this capability
to a coach or a child in a 5-minute session.

## Differentiation (what makes this defensible)

| | SoccerBot360 | skills.lab | Vald ForceDecks | **Project_Cam AWA** |
|---|---|---|---|---|
| Cognitive training | ✓ | ✓ | — | ✓ (voice override) |
| Biomechanics screening | — | (basic) | ✓ gold-standard | ✓ pose-based (±5°) |
| **Adaptive launcher (closed loop)** | — | — | — | **✓** |
| **Robot-as-character UX** | — | — | — | **✓** |
| Engaging for U10–U14 | ✓ | ✓ | — | ✓ |
| C3D / biomech-lab partnership | — | — | ✓ | ✓ (already shipping) |
| Price | $$$$ | $$$$$ | $$$$ | $$ |

The defensible moat is the **closed loop**: camera observes weakness → BLM
adapts target → camera re-measures → score reflects both reaction and form.
No public competitor closes this loop in real time.

## Concept

> **«Biomech screening as a video game in which a robot opponent learns your
> weaknesses in 5 minutes.»**

The athlete walks in, plays a 5-minute Boss Battle, and walks out with:

- A **kid-facing experience**: RPG character sheet, score + combo, badges, ghost replay,
  position-fit suggestion.
- A **coach-facing PDF**: ACL risk score, asymmetry index, scan rate vs cohort,
  recommended 3-week drill plan, C3D-compatible session file for any biomech lab.

The session is structured as **Hybrid: silent diagnose → explicit reveal** —
the first 45 seconds of gameplay silently profile the athlete; then the system
dramatically announces the detected weakness, and the launcher's next 2:30 of
shots are biased to attack that weakness. This produces a measurable
**within-session improvement delta** ("L valgus 18° → 11° over 90 seconds"),
which is the killer demo moment for academy partnerships.

## Arena & Hardware Context

**Garage arena** (`arena_fixed/cal/extrinsics/Dimensions_fixed.txt`):
- 6.23 m × 3.05 m × 2.95 m (X × Y × Z), origin at North-East corner
- 4× USB UVC cameras at Z=212–227 cm (all in one high band)
- BLM (`control_12_full.ino`) at X≈30, Y≈150, h≈120 cm
- Voice bridge UDP 5006 (Vosk, colleague's venv)
- Live viewer UDP 5005 producer (joints + ball)

**Constraints from `.claude/rules/`:**
- Pitch clamp **[0°, 30°]** → all BLM targets must be at chest-height-or-above.
  Floor zones can be used only as voice-cued redirect targets.
- Yaw clamp **±30°** → fits arena geometry (max 15.5° to corners).
- Firmware RPM gate **≥ 400 RPM** → ball speed floor ≈ 4–5 m/s on foam (measured by
  `calibrate_ball_rpm.py`); cannot use ultra-slow shots without firmware change.
- Sacred (do not modify): `triangulate_multi`, `transform_world_point_y`,
  `ema_update`, UDP axis semantics, BLM firmware safety.

**Hardware perf baseline** (measured 2026-05-14 — see
[`docs/session_handoff_2026-05-14_gpu_camera_perf.txt`](../../session_handoff_2026-05-14_gpu_camera_perf.txt)):
- 4× FullHD@30 raw capture: PASS (CPU 7.3% of 20 threads)
- TRT pose + ball compute (light UI, single perf run):
  - `total_ms` mean ≈ 28.3 ms
  - `total_ms` p95 ≈ 31–32 ms
  - Frame budget at 30 FPS = 33.3 ms → **mean ~5 ms headroom, p95 only 1–2 ms**
- Full operator UI: drops to 18 FPS (UI bottleneck, not compute)
- **Caveat from handoff:** the perf loop ran faster than the cameras' physical
  30 FPS, so some iterations may have reprocessed the latest camera frame.
  This is a compute ceiling, not a production sustained run.
- **Implication:** a headless compute profile at 30 FPS is **likely achievable**
  after the decoupling refactor, but **not yet production-proven**. Must be
  validated in Phase 0 (P0.3 + P0.4) on a 60–120 s sustained run with unique
  fresh frames, drop counters, latency p95, and `live_metrics` added inside
  the loop. **If P0.4 fails the 30 FPS budget, the design falls back to a 15 FPS
  metrics window** — most components survive; scan_rate detection has lower
  precision but football scans (~200–300 ms) are still observable.

## Velocity-Based BLM Abstraction

Drills are configured in terms of physical ball speed (m/s), not motor RPM.
The session manager translates `target_velocity_mps` → RPM via the calibration
model built by `calibrate_ball_rpm.py`. Minimum velocity is the floor at
RPM=400 (~4 m/s for foam), age-grading:

| Age cohort | target_velocity_mps | RPM (foam, approx) |
|---|---|---|
| U10 | 4.0 | ≈400 |
| U12 | 5.5 | ≈500 |
| U14 | 7.0 | ≈640 |

Adaptive logic also varies velocity within a session: harder reps go faster.

---

## Session Flow (5:00)

```
T+0:00  Onboarding (5s)
        Voice: "Welcome to the pitch, [name]. Boss is loading."
        Browser: avatar appears, skeleton outline.
        BLM: idle "alive" rotation.

T+0:05  Phase 1 — Baseline Scan (55s)
        Five movements, each gated by completion + voice:
          (1) Athletic stance hold 5s    → posture, weight distribution
          (2) 3 bodyweight squats         → knee valgus signed ratio, depth
          (3) Lateral shuffle L+R (8s)    → cut quality, valgus on cut
          (4) 5 reactive starts (1–1.5m)  → first-step quickness, side asymmetry
          (5) Single-leg balance 5s L+R   → SL stability, ankle control
        Live skeleton + per-metric ticker render in browser.
        BLM idle, "observing".

T+1:00  Player Card Reveal (10s)
        Browser: animated card flies in (FIFA Career Mode style):
          PLAYER_007 · Age 12 · 145 cm · cohort=U12
          ⚡ Reaction       47/100
          ⚖ Symmetry L/R   71/100  ⚠
          🦵 Knee Stability 63/100  ⚠
          🧘 Single-leg    82/100
          🦘 First step    58/100
          👀 Scan rate    4.2/min (pro: 8-12)
          Position fit: "Defender / Midfielder"
        Voice: "Player card locked. Drills incoming."

T+1:10  Phase 2A — Recon Drills (45s, 5 drills × 9s each)
        Silent profiling. BLM picks targets, foam @ target_velocity_mps:
          Drill 1: First Touch     (lobs to chest zone)
          Drill 2: Y-Pattern Scan  (voice cue, throw to indicated side)
          Drill 3: Lateral Slide   (BLM cues attack lane L/R)
          Drill 4: Reactive Redirect (control then redirect to voice-cued cone)
          Drill 5: Cognitive Overlay (BLM aims R, voice says "BLOCK LEFT")
        System silently builds weakness profile across:
          valgus_L, valgus_R, asymmetry, reaction_L, reaction_R, scan_rate,
          lateral_com_excursion, cognitive_override_success_rate.
        Voice: occasional "+50 combo!", "good react!"
        Browser: score ticking, combo counter, level meter filling.

T+1:55  Weakness Reveal (15s)
        BLM: scanning rotation L↔R↔L (telegraph "I see you")
        Voice + SFX: "Boss has read your game.
                      Left knee collapses 18° on lateral cuts.
                      Scan rate 4.2 — below pro level.
                      Boss is exploiting both. Brace."
        Browser: skeleton with red-highlighted L-knee, attack arrow to L,
                 reasoning panel showing detected metrics.
        Coach laptop: full decision-tree log visible.

T+2:10  Phase 2B — Hunt (Adaptive Drills, 2:30, 10 reps)
        70% bias to L-lateral attacks + forced-scan setups.
        30% other (avoid frustration, control variable).
        target_velocity_mps increases with each successful reaction.
          Reps 1–4:  Repeated lateral slide with L bias
                     → each rep measures valgus, asymmetry
          Reps 5–7:  Y-pattern with forced-scan gate
                     (BLM won't fire until head_yaw > 30° both sides)
                     → metric: time-to-scan + scan-then-orient quality
          Reps 8–10: Cognitive lateral on weak side
                     → trains override under L-side stress
        Voice tracks progress live:
          "L valgus dropped to 14°. Progress."
          "Scan rate up: 4.2 → 6.1/min."
          "Combo x4!"

T+4:40  Verdict + Replay (20s)
        BLM: "bow" gesture (small pitch dip + back to home).
        Voice: "Round over.
                L valgus: 18° → 11° (-7°). Knee Whisperer badge unlocked.
                Scan rate: 4.2 → 7.8/min (+85%). Eyes Up badge unlocked.
                Position re-suggested: Box-to-Box Midfielder.
                Final score: 2,340 — new personal best."
        Browser:
          - Player Card v2 with before/after deltas
          - Ghost-replay clip (worst valgus moment → best, side-by-side)
          - Earned badges
          - Position fit suggestion v2
          - "Coach has details" tile with QR to PDF.

T+5:00  Coach Report ready (async, in background)
        PDF auto-generated + JSONL events + C3D file saved to
        data/sessions/<session_id>/.
```

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│ NEW: src/project_cam/training_session/                             │
│                                                                     │
│   session_manager.py                                                │
│     • State machine: onboarding → baseline → card →                │
│       recon → reveal → hunt → verdict → done                       │
│     • Owns EventLogger session_id                                   │
│     • Reads drill_library, drives BLM, dispatches voice/UI events  │
│                                                                     │
│   live_metrics.py                                                   │
│     • Calls assessment.kinematics.frame_kinematics() per UDP frame │
│     • Sliding 3-second windows: valgus_p95, asymmetry, scan_rate   │
│     • New: scan_rate from head yaw (nose/ears keypoints)           │
│     • New: lateral_com_excursion from pelvis XY range              │
│     • New: reaction_latency from BLM aim event → CoM displacement  │
│                                                                     │
│   weakness_detector.py                                              │
│     • After recon window: rank metrics by deviation-from-threshold │
│     • Thresholds: assessment.maturity-adjusted from yaml           │
│     • Output: WeaknessProfile {primary, secondary, confidence}     │
│                                                                     │
│   adaptive_targeter.py                                              │
│     • Maps WeaknessProfile → BLM aim plan:                          │
│       L-knee valgus → bias lateral attacks to athlete's LEFT       │
│       Slow R-side reaction → fast surprise to athlete's RIGHT      │
│       Low scan rate → forced-scan gate before firing               │
│       Poor cognitive override → voice-misdirect more frequently    │
│     • Applies pitch [0,30°] / yaw [±30°] clamps BEFORE UDP send    │
│                                                                     │
│   blm_character.py                                                  │
│     • Choreography sequences (composed of `set` commands):         │
│       - idle_alive: tiny ±2° drift every 4s ("breathing")          │
│       - telegraph: yaw L→R→L over 0.8s before locking aim          │
│       - scanning: smooth side-to-side rotation 1.2s                │
│       - bow: pitch 0° → 12° → 0° over 0.6s                         │
│       - power_up: pitch sweep 0→25→0° with voice cue               │
│     • All sequences cancellable instantly by stop/center/estop     │
│                                                                     │
│   drill_library.py + drill defs in yaml                            │
│     • Per-drill: name, target_velocity_mps, body_zone,             │
│       voice_cue, success_criterion, biomech_metric_focus           │
│                                                                     │
│   tts.py                                                            │
│     • Piper offline TTS (small model, ~50 MB, <100 ms synthesis)   │
│     • Output via aplay/sounddevice → arena speaker                 │
│     • Pre-rendered cue cache for fixed phrases (level 1 ready, etc)│
│                                                                     │
│   game_ui_server.py                                                 │
│     • Flask :8080 + Server-Sent Events                             │
│     • Endpoints:                                                    │
│         GET  /            → main game UI (HTML+JS+three.js)        │
│         GET  /coach       → coach dashboard view                   │
│         GET  /events      → SSE stream of session state            │
│         GET  /api/state   → current state snapshot                 │
│         GET  /static/*    → CSS/JS assets                          │
│     • Pushes state diffs from session_manager (no polling)         │
│                                                                     │
│   game_ui_static/                                                   │
│     • index.html: stats card, live score, level meter, skeleton    │
│     • three.js for 3D skeleton with joint-angle arcs               │
│     • Chart.js for metric mini-charts (reused from assessment)     │
│     • coach.html: full dashboard view                              │
│                                                                     │
│   badges.py                                                         │
│     • Rule-based: KneeWhisperer (valgus<10° all reps),             │
│       Lightning (reaction P50<300ms), EyesUp (scan>7/min),         │
│       Symmetry (asymmetry>0.9), Composure (no fail under cog)      │
│                                                                     │
│   position_fit.py                                                   │
│     • Heuristic:                                                    │
│       high SL + low valgus → "Center Back / Defender"              │
│       high reaction + high asymmetry to dominant side → "Winger"   │
│       high scan rate + balanced symmetry → "Midfielder"            │
│       fast first step + good first touch → "Striker"               │
│                                                                     │
│   coach_report.py                                                   │
│     • Renders session JSONL → assessment.render.HTML               │
│     • Converts HTML → PDF via weasyprint                           │
│     • Embeds: ACL risk badge, asymmetry chart, scan trend,         │
│       per-drill table, recommended 3-week plan, video QR           │
└────────────────────────────────────────────────────────────────────┘

REUSED (read-only or extended; never modify internals):
  ✓ assessment.kinematics.frame_kinematics()       → live valgus/asymmetry
  ✓ assessment.maturity.calculate_maturity_offset()          → age-adjusted thresholds
  ✓ assessment.reports / render / templates        → final coach HTML
  ✓ assessment.exports.c3d_writer                  → biomech-lab artifact
  ✓ closed_loop.event_log.EventLogger              → session timeline JSONL
  ✓ closed_loop.safety_gates                       → input filtering
  ✓ assessment.udp_record                          → raw joints JSONL

ORCHESTRATED via existing IPC (no changes to producers):
  • UDP 5005 inbound   ← Parallel_working/scripts/live_4cam_arena_view_parallel.py
  • Serial outbound    → garage_lab_combined/scripts/blm_follow.py (wrapped, see below)
  • UDP 5006 inbound   ← garage_lab_combined/scripts/voice_bridge.py (existing)
  • UDP 5015 inbound   ← live viewer (predicted targets) — optional, for Kalman use
  • Audio out (new)    → speakers (aplay or pygame.mixer)
  • HTTP :8080 (new)   → browser game UI

EXTENDED in place (small, additive):
  • configs/exercises/football_academy_u10.yaml
      + first_touch, y_pattern_scan, lateral_slide,
        cognitive_overlay, reactive_start, athletic_stance,
        single_leg_balance_hold drill defs
  • garage_lab_combined/scripts/blm_follow.py
      + accepts plan packets on a new UDP port (e.g. 5007)
        from session_manager, with target_velocity_mps + voice cue
      + new --plan-port flag (off by default; existing behaviour preserved)
  • Parallel_working/scripts/live_4cam_arena_view_parallel.py
      DECOUPLE: ball detector no longer gated by --show-2d/--show-3d
      (handoff Priority 1 — Phase 0 prerequisite)
      ADD: --headless flag that disables all cv2 windows but keeps compute
      (handoff Priority 2 — Phase 0 prerequisite)

SACRED — not touched:
  ✗ triangulate_multi, transform_world_point_y, ema_update
  ✗ UDP packet axis semantics on 5005
  ✗ control_12_full.ino firmware
  ✗ launcher_runtime safety gates
  ✗ arena_fixed/ extrinsics
```

---

## Live Metrics (computed in `live_metrics.py`)

All metrics derived from `assessment.kinematics.frame_kinematics()` over a
sliding 3-second window at 30 FPS = 90 samples (or 45 samples at 15 FPS fallback).

`frame_kinematics()` is already in `assessment/offline_assess.py` and is
cheap per call, but its additive cost **inside** the live compute loop
(alongside ball + pose + triangulation + UDP) **must be measured in Phase 0
(P0.4)**. Given current p95 of 31–32 ms inside a 33.3 ms budget, the headroom
for `live_metrics` is only ~1–2 ms p95, not the ~5 ms mean. Acceptance gate:
P0.4 shows `total_ms` p95 ≤ 33 ms with `live_metrics` enabled, over a 60 s run.
If P0.4 fails, fall back to 15 FPS metrics window.

| Metric | Source | Computation |
|---|---|---|
| `valgus_L_p95`, `valgus_R_p95` | kinematics | `knee_valgus_signed_ratio()` p95 over window |
| `asymmetry_deg` | kinematics | `abs(left_angle - right_angle)` p95 |
| `scan_rate_per_min` | **new** | head_yaw from `atan2(nose - ear_mid, …)`; count zero-crossings ×60/window_s |
| `lateral_com_excursion_mm` | new | `max(pelvis_y) - min(pelvis_y)` over window |
| `reaction_latency_ms` | new | `t(first CoM displacement > 50mm)` − `t(BLM aim_command_sent)` |
| `first_step_velocity_mps` | new | pelvis CoM velocity in first 300 ms post-reaction |
| `cognitive_override_pct` | new | per-rep boolean: did athlete react to voice cue (not visual)? |

Thresholds use `assessment.maturity.calculate_maturity_offset()` for age-adjustment
(or `maybe_calculate_maturity()` when anthropometry inputs are partial):
late_maturer → valgus threshold × 1.30, early_maturer → × 0.85.

## Scoring

Per-rep score computed at `outcome_scored` event:

```
base       = 100 if reaction_ok else 30
v_penalty  = clamp(valgus_observed / threshold, 1.0, 2.0) - 1.0   # 0..1
r_bonus    = clamp((600 - reaction_ms) / 200, 0, 1) * 30          # 0..30
combo_mult = 1 + 0.2 * combo_count                                  # capped 3x
final      = round((base * (1 - v_penalty) + r_bonus) * combo_mult)
```

Range ~0–390. Athlete sees `final` + combo; coach sees the components.

---

## Drill Library (initial 7 drills)

Stored in `configs/exercises/football_academy_u10.yaml`, extending the existing
`exercises:` block:

| Drill | target_mps | body_zone | voice_cue | Primary metric | Phase |
|---|---|---|---|---|---|
| `athletic_stance` | — | — | "athletic stance, hold 5s" | weight distribution | baseline |
| `bodyweight_squat` | — | — | "three squats" | valgus, depth | baseline (existing) |
| `lateral_shuffle` | — | — | "side to side" | cut speed, valgus | baseline |
| `reactive_start` | — | — | "go!" (random side) | first step, asymmetry | baseline |
| `single_leg_balance` | — | — | "left/right leg, 5s" | SL stability | baseline (single_leg_squat exists, reuse) |
| `first_touch` | 4–6 | chest/thigh | "control" | balance after control, foot dominance | recon/hunt |
| `y_pattern_scan` | 4–6 | chest L or R | "check shoulders! ... LEFT!" | scan rate, body orientation | recon/hunt |
| `lateral_defensive_slide` | 4–6 | chest L or R | "close the lane" | valgus on cut, lateral COM | recon/hunt (weakness target) |
| `cognitive_overlay` | 4–6 | chest (visible aim R), voice says L | "block LEFT!" | override success | recon/hunt |
| `reactive_redirect` | 4–6 | chest center | "redirect yellow!" | redirect accuracy, body shape | recon/hunt |

Deferred from launcher-fired drills (pitch < 0 needed): drop_landing, low_pass_receive,
volley. May enable later with firmware change or BLM mount adjustment.

---

## Data Outputs

Per session, in `data/sessions/<session_id>/`:

| File | Format | Source | Consumer |
|---|---|---|---|
| `events.jsonl` | JSONL | `closed_loop.event_log.EventLogger` | post-session analysis, coach report |
| `joints.jsonl` | JSONL | `assessment.udp_record` (existing) | offline re-assessment, C3D regenerate |
| `metrics_live.jsonl` | JSONL | new — `live_metrics` dump per frame | research, debug, training data |
| `targets.jsonl` | JSONL | new — adaptive plan decisions with reasoning | coach reasoning panel + audit |
| `report.json` | JSON | `assessment.offline_assess` (re-run post-session) | structured data |
| `report.html` | HTML | `assessment.render` + AWA-flavoured template | shareable interactive |
| `report.c3d` | C3D | `assessment.exports.c3d_writer` | Visual3D / OpenSim / NU lab |
| `replay_3d.mp4` | MP4 | extension of `run_record_3d.sh` with angle-arc overlay | coach review |
| `game_ui.mp4` | MP4 (Phase 2) | OBS / ffmpeg headless capture of browser UI | demo video, social |
| `coach_report.pdf` | PDF | new — weasyprint over `report.html` | parent / coach handout |

All persistence reuses existing modules. New code only writes
`metrics_live.jsonl`, `targets.jsonl`, the angle-arc overlay extension, and the
PDF.

---

## Implementation Phases

```
Existing roadmap (jaunty-toasting-melody.md)   |   AWA delivery
────────────────────────────────────────────────|──────────────────────────────
Month 0 — Software credibility sprint (now)     |  Phase 0 — Prerequisites
  • C3D, EventLogger, BLM audit log             |    Parallel, ~5 dev-days:
  • Safety gates, threshold honesty             |    P0.1 RPM→m/s cal complete
  • 23 tests                                    |        (`calibrate_ball_rpm.py`)
                                                |    P0.2 Decouple ball detector
                                                |        from --show-2d/--show-3d
                                                |        in live viewer
                                                |    P0.3 Add --headless flag to
                                                |        live viewer (compute-only)
                                                |    P0.4 Perf-test live_metrics
                                                |        inside compute loop
                                                |        (confirm 30 FPS stable)
                                                |    P0.5 Extend yaml with new
                                                |        drill defs (no behavior
                                                |        change yet)
                                                |    P0.6 Fix TRT/OpenCV cleanup
                                                |        segfault on exit
────────────────────────────────────────────────|──────────────────────────────
[NEW] Pre-Path B Bridge Experiment              |  Phase 0 may overlap here
(before Month 1 commits $4k on FLIR — ~1 week)  |
  • Buy 2× cheap USB3 2MP global-shutter @      |
    120 FPS cameras (~$200–300 / pair, e.g.     |
    Innomaker, Arducam, ELP)                    |
  • Validate before committing to FLIR:         |
    - Linux UVC / vendor SDK support            |
    - Manual exposure + gain lock               |
    - Hardware trigger pin (sync candidate)     |
    - Sustained 120 FPS at target resolution    |
    - Frame timestamps                          |
    - OpenCV / pylon / spinnaker integration    |
    - Lens / FOV suitability for arena          |
    - USB topology behaviour under load         |
  • Decision gate: proceed with $2.8k FLIR      |
    order only after pair test passes.          |
  • If pair fails: revise hardware budget,      |
    consider GigE Vision or different vendor.   |
────────────────────────────────────────────────|──────────────────────────────
Month 1 — Hardware install (FLIR Path B)        |  Phase 0 may continue here
  • Mount cameras, sync wiring                  |  if calibration retake
  • Re-record fixtures                          |  pushes deadlines
  • Re-validate valgus thresholds               |
  • Recalibrate intrinsics + extrinsics         |
────────────────────────────────────────────────|──────────────────────────────
Month 2 — Validation study + figures            |  Phase 1 — Core MVP
  • 12-20 participants                          |  (~3 weeks)
  • Investor-demo overlay polish ←──── REPLACED BY AWA
                                                |    Module skeleton:
                                                |    • session_manager state
                                                |      machine (8 states)
                                                |    • live_metrics with all 7
                                                |      metrics
                                                |    • weakness_detector
                                                |    • adaptive_targeter
                                                |      (phantom-aim only)
                                                |    • tts.py (Piper, English)
                                                |    • game_ui_server (Flask+SSE)
                                                |    • Basic game UI: stats card,
                                                |      score, level meter,
                                                |      three.js skeleton +
                                                |      angle arcs
                                                |    • EventLogger integration
                                                |    ONE drill end-to-end:
                                                |      lateral_defensive_slide
                                                |      phantom-aim (no fire)
                                                |    Test: 5-min session on self
                                                |    with full state machine,
                                                |    no live BLM fire
────────────────────────────────────────────────|──────────────────────────────
Month 3 — Pilot kickoff + demo (Kairat ready)   |  Phase 2 — Full session
  • v1.0-pilot-ready                            |  (~3 weeks)
  • 90-sec demo video                           |    • All 7 drills wired
  • Kairat pilot session #1                     |    • BLM character anims
  • Investor one-pager                          |      (telegraph/scan/bow)
                                                |    • Foam @ 400 RPM live fire
                                                |      (re-run S4 cycle)
                                                |    • Ghost replay (matplotlib
                                                |      MP4 with angle overlays)
                                                |    • Badges system
                                                |    • Position fit suggestion
                                                |    • Coach PDF (weasyprint)
                                                |    • Demo script + dress
                                                |      rehearsal
                                                |    Test: 3-5 youth athletes
                                                |    end-to-end recorded
────────────────────────────────────────────────|──────────────────────────────
Month 4+ (post-pilot)                           |  Phase 3 — Polish (optional)
                                                |    • Multi-athlete leaderboard
                                                |    • Longitudinal passport
                                                |      (multi-session compare)
                                                |    • three.js animation polish
                                                |    • Advanced cognitive layer
                                                |    • Possibly firmware foam
                                                |      preset (RPM gate 200)
                                                |      for U8 expansion
```

**Critical path Phase 1:**
1. P0.4 must pass first (live_metrics fits in 30 FPS budget) or design needs
   revision down to 15 FPS metrics window.
2. `tts.py` with Piper — small isolated task, ~1 day.
3. `live_metrics` + `weakness_detector` — uses existing kinematics, ~3 days.
4. `game_ui_server` + three.js skeleton + Chart.js — largest single piece, ~7 days.
5. End-to-end test of ONE drill with phantom-aim BLM character.

---

## Demo Script for Kairat Scout (10 min total)

```
T+0:00 — Pre-session (1 min)
        Operator: brief intro + arena context
        One-line pitch: "5-min scan, biomech screening, academy-ready report"
        Athlete (age 12) steps in for T-pose calibration (~15s)
        Operator confirms: "Calibration OK, all 4 cams locked,
                            RPM cal verified at 400-500 RPM"

T+1:30 — The session (5 min) — runs as designed
        Scout sees on coach laptop:
          • Live 3D skeleton with valgus highlights
          • Detected weakness reasoning panel
          • Adaptive decision log (targets.jsonl tail)
          • EventLogger timeline
        Scout sees on kid's monitor (browser game UI):
          • RPG stats card animation
          • Score ticking up
          • Ghost replay between rounds
          • Badges popping
        Scout hears:
          • Voice cues / BOSS narration
          • Sound FX (impact, level up, badge)
          • BLM physical movement (telegraph rotations)
          • Foam balls firing during hunt phase

T+6:30 — Verdict & coach handoff (3 min)
        Player Card v2 (final) shown
        Operator opens HTML report on laptop, side-by-side with
          C3D file opened in Mokka (proves biomech-lab credibility)
        One-page PDF auto-generated:
          - ACL risk score (front + back)
          - Asymmetry index
          - Scan rate vs age cohort
          - Recommended 3-week drill plan
          - Position fit suggestion
        Operator pitch: "One athlete, 5 min. Your academy has 200 youth
                         players. This file goes to your physiotherapist
                         directly."

T+9:30 — Q&A
```

**Wow-moments** (what the scout remembers):
1. *Stats Card reveal* (T+1:00) — feels like a video game character sheet
2. *BOSS detected weakness* (T+1:55) — the closed loop is visible, audible
3. *Live valgus angle on screen during play* — "you can SEE my knee collapse"
4. *Foam ball physically firing* during hunt phase — real stakes, not a sim
5. *PDF on tablet 30s after session end* — production-ready output
6. *C3D file in Mokka* — biomech-lab tier, not a toy

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **P0.4 shows 30 FPS compute unsustainable with live_metrics** | Whole metrics-window design needs re-budgeting | Pre-committed fallback: switch to 15 FPS metrics window. Most components survive: 3 s window = 45 samples (still robust p95 statistics); scan_rate detection precision drops but football scans (200–300 ms) still observable. Adaptive_targeter and weakness_detector unaffected. |
| **GS bridge experiment fails** (cheap 2 cams don't pass Linux/sync/120 FPS validation) | $4k FLIR order is unsafe | Hard decision gate before Path B commit. Revise hardware plan: GigE Vision option, different vendor, or accept current USB2 cameras with stronger software-sync compensation |
| Foam @ 400 RPM still too fast for U8 | Cannot demo to youngest kids | Phase 1 demo targets U10+ only; defer firmware change until pilot demand |
| Pitch clamp prevents low-target drills | Cannot test landing valgus directly | All drills target chest+. Compensate with `single_leg_squat` baseline rep |
| Inter-camera sync 20-40 ms drift | Slight noise in fast metrics | Tolerable for screening; resolved by Path B hardware sync |
| Athlete consent / IRB for academy youth | Cannot record minors without parent consent | Required: signed parent waiver per session, displayed on coach laptop pre-session, logged into events.jsonl |
| Privacy: video of minors | Data protection issues | Default opt-out for `replay_3d.mp4`; only joints.jsonl + C3D auto-saved (anonymous markers) |
| TRT cleanup segfault on exit | Looks unprofessional in demo | P0.6 prerequisite; ensure graceful TRT engine destruction before cv2.destroyAllWindows() |
| Voice TTS unintelligible over BLM noise | Athlete misses cues | Test TTS volume in arena before pilot; pre-render fixed phrases to cache for max clarity |
| Browser UI lag > 200 ms | Score feels detached from action | SSE flush per event, no buffering; benchmark in Phase 1 |
| Athlete refuses / freezes during session | Session aborts | Operator has manual override on coach laptop: pause/resume/abort buttons; session_manager handles abort cleanly |
| Network/HTTP failure between session and browser | Game UI blank | Browser opens local URL; no network dependency. Operator restarts Flask if dead. |
| BLM serial disconnect mid-session | Hardware fault | Existing safety: launcher_runtime auto-`stop` + `set 0 0 0 0` on link loss. session_manager catches → graceful abort + show "TECHNICAL — coach restart" overlay |

---

## Non-Goals (explicit deferrals)

- **Not competing with Vald on absolute accuracy** — we're screening-grade
  (±5° joint angles, ~150-180 mm spatial). Validation study (Month 2) will
  state this honestly.
- **Not replacing coaches** — system surfaces signals; coach makes decisions.
- **Not full SoccerBot-style cognitive arena** — they have projectors; we have
  biomech. Don't try to win their game.
- **Not real-time C3D streaming** — C3D is a session file format, written post-session.
- **Not multi-athlete simultaneous play** at MVP — single athlete, single session.
- **Not heading drills** — concussion risk for U14 (FIFA 11+ Kids guidance).
- **Not low-pitch / floor drills** — firmware pitch clamp [0, 30°].
- **Not free-form gameplay** — fixed 5-min structure for MVP; freeform = Phase 3.

---

## Acceptance Criteria (Phase 2 Kairat pilot ready)

1. ✓ 5-min session runs end-to-end on self (operator) with zero manual
   intervention except the initial Start press.
2. ✓ TTS audible and clear over BLM servo noise at standard arena distance.
3. ✓ Browser game UI renders state at < 100 ms event-to-paint latency.
4. ✓ EventLogger writes a complete timeline from `session_start` to
   `session_end` with no gaps.
5. ✓ `targets.jsonl` shows the reasoning behind every BLM aim decision,
   including weakness used and confidence.
6. ✓ Coach PDF generated within 5 s after `session_end`.
7. ✓ C3D file opens in Mokka with 17 markers @ session FPS.
8. ✓ Position-fit suggestion produces a sensible label for a sample of 5
   different movement profiles.
9. ✓ Phase 0 prerequisites passing: `--headless` runs at ≥ 30 FPS compute
   for ≥ 60 s without dropped frames.
10. ✓ Existing 23+ tests still pass (no regression).
11. ✓ Three end-to-end demo runs recorded with three different operators
    playing the athlete role (smoke test for robustness).

---

## Notes on Sacred Boundaries

This design lives in a new module (`src/project_cam/training_session/`)
plus additive extensions. **The hot-path live viewer is touched only twice:**

1. P0.2 — ball detector independence from UI flags (mechanical change, isolated)
2. P0.3 — `--headless` flag (additive, default off)

Both are flagged Phase 0 prerequisites and tested with regression fixtures
before any AWA-specific code lands.

The launcher runtime (`launcher_runtime_from_udp.py`) is also untouched. AWA's
`adaptive_targeter` produces aim plans that are sent to a wrapping `blm_follow.py`
extension (`--plan-port`), which still defers all safety-critical decisions
to the existing launcher_runtime logic.

Firmware (`control_12_full.ino`) is not modified. Velocity-based abstraction
operates on top of the existing RPM gate; the floor is the physical minimum at
RPM=400.

UDP packet axis semantics, calibration files, and the 5005/5006 schemas are
read-only contracts.

---

## Open Questions (revisit before writing the implementation plan)

1. **Audio output device:** dedicated arena speaker, or laptop speakers? Affects
   TTS configuration. Default plan: laptop speakers for MVP, document the upgrade.
2. **TTS engine:** Piper (offline, ~50 MB, English models well-supported) vs gTTS
   (online, free, multi-lingual, but requires internet). Phase 1 plan: Piper for
   reliability.
3. **Reference athlete clips:** ghost-comparison to Modrić / Messi requires
   licensed footage. Phase 2 may use generic professional reference movements
   from open dataset, not real player clips.
4. **Consent form template:** does Kairat / NU have a youth-research consent
   template, or do we draft one?
5. **Demo recording:** Phase 2 includes `game_ui.mp4` via OBS/ffmpeg. Do we
   record on the workstation (CPU cost), or pipe browser to a separate
   capture machine? Defer to Phase 2 planning.
6. **GS bridge camera candidates:** which 2 specific cheap USB3 global-shutter
   2 MP @ 120 FPS cameras do we test first? Candidates to evaluate:
   Innomaker IMX296 (~$120), Arducam IMX296 (~$130), ELP USB3-OV2710 (~$80).
   Decide before Pre-Path B Bridge Experiment kickoff.

---

## Next Action

**This spec is the contract for the Adaptive Weakness Arena feature.** It is
NOT an implementation plan and should not be executed directly.

The correct next step is to **write the Phase 0 prerequisites implementation
plan** before any AWA-specific code. Phase 0 is six bounded, low-risk
infrastructure tasks (~5 dev-days) that:

- Strengthen the existing system regardless of AWA going ahead
- Produce measured perf data needed to validate the 30 FPS assumption
- Unblock the AWA design path with no wasted effort if the design needs revision

Phase 0 tasks for the next plan:

| ID | Task | Touches | Risk |
|---|---|---|---|
| P0.1 | Complete `calibrate_ball_rpm.py` velocity→RPM mapping on **foam** ball | new helper, no production code | low |
| P0.2 | Decouple ball detector from `--show-2d`/`--show-3d` in live viewer | `Parallel_working/scripts/live_4cam_arena_view_parallel.py` (canonical hot path — careful, test with fixtures) | medium |
| P0.3 | Add `--headless` flag to live viewer (compute-only, no cv2 windows) | Same file as P0.2 | low |
| P0.4 | Add `live_metrics` module skeleton + perf-test inside compute loop | new `src/project_cam/training_session/live_metrics.py` | low |
| P0.5 | Extend `configs/exercises/football_academy_u10.yaml` with 7 new drill stubs (no behaviour change yet) | YAML only | very low |
| P0.6 | Investigate and fix TRT/OpenCV cleanup segfault on exit | live viewer + TRT engine teardown | medium |

After Phase 0 closes, this design becomes anchored in measured perf and
the AWA Phase 1 plan can be written with confidence.
