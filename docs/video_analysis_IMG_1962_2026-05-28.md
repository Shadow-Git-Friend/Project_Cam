# Video Analysis — `IMG_1962.MOV` (projector goal game) — 2026-05-28

Analysis of the phone recording of `./proxiball_3d-main/projector/run_goal_target_multicam.sh`,
cross-referenced against the system's own per-frame telemetry logs.

> **Headline:** The user's instinct ("fast/hard shots blur and don't get detected") is
> real, but it is **not the main reason almost nothing scores.** Per-camera ball
> detection is actually *good* (median YOLO confidence **0.87–0.88**). The system fails
> because the **multi-camera geometry never agrees**: in ~32,000 logged frames, **0%**
> triangulated to a geometrically consistent point and consensus was reached in **~0.05%**
> of frames. That signature points to a **broken/uncalibrated multi-view setup** (the
> recent `Remounted_West_East/` bundle at 1920×1080 + the `homography.json` 1920×1200→1080
> mismatch), layered on top of the known **rolling-shutter + no-hardware-sync** camera
> limits. **New cameras are justified — but a recalibration is the immediate blocker, and
> it is free.**

---

## 1. What was analysed

| Source | Detail |
|---|---|
| Phone video | `/home/hanush/Downloads/IMG_1962.MOV` — 720×1280 portrait, H.264, **30 FPS, 282 s, 8462 frames**, 104 MB |
| System telemetry | `/tmp/goal_debug.jsonl` (22,622 frames, 690 s) and `/tmp/goal_debug2.jsonl` (9,595 frames, 330 s) — per-frame detections, wall projections, zone votes, consensus, `no_hit_reason`, triangulation reproj error |

**Method (the "check every frame" pass):**
1. Sampled the phone video (overview contact sheets at 1/15 s and 1/5 s; full-res frames at key timestamps; full-30-FPS bursts around the highest-motion moments found by a frame-difference scan over all 8462 frames).
2. Parsed **all 32,217 telemetry frames** from the two debug logs and computed per-camera detection rates, consensus rate, `no_hit_reason` distribution, and triangulation reprojection-error statistics.

> **Caveat:** the two JSONL logs are from goal-game runs on the **same day and same setup**
> as the recording (timestamps ~16:14 and ~16:32; the video was transferred ~17:06). They may
> not be the exact recorded session, and the recording shows a slightly *better* outcome
> (SCORE 4 / MISS 21 ≈ 25 registered crossings) than the logs (9 consensus frames each) —
> consistent with the temporal-consensus fix being added between the logged runs and the
> recording. The per-camera detection, in-grid mapping, and reprojection numbers describe the
> geometry and are unaffected by that fix.

---

## 2. What the video shows

- A real **garage**, projecting the 3×3 target grid onto the sectional **garage door** (the projection surface). Grid zones are labelled **A1–A3 / B1–B3 / C1–C3**; the **green box** marks the active target (it stays on **B1** for essentially the whole clip).
- The projector also shows the operator's **desktop** (taskbar/dock visible on the left of the projection) and a live HUD: **`SCORE n  MISS n  TARGET → B1`** plus a frame-rate readout.
- **AprilTag/ChArUco markers** are taped across the door (calibration fiducials). One **arena camera** is visible mounted mid-wall.
- The **player is also the operator** (handheld phone). At close range the player **stands inside the projection cone** (grid labels land on his shirt at `0:22`), occluding both the projector and the camera sightlines.
- Floor is green turf with a workout bench, a yoga mat, and clutter on the right; a "ROCKET" soccer ball is visible near the end.

**HUD score progression (read from the projection):**

| Time | SCORE | MISS | FPS shown | Target |
|---|---|---|---|---|
| 0:40 | 1 | 5 | — | B1 |
| 2:30 | 4 | 11 | 27.5 | B1 |
| 4:35 (end) | 4 | 21 | 24.5 | B1 |

→ **Score froze at 4 while misses kept climbing (+10 in the final ~2 minutes).** A hit re-picks
the target ([goal_target_game_multicam.py:498](../proxiball_3d-main/projector/goal_target_game_multicam.py#L498));
target stayed on B1, consistent with almost no real hits late in the session.

---

## 3. Scoring semantics (so the numbers mean something)

From [goal_target_game_multicam.py:479-501](../proxiball_3d-main/projector/goal_target_game_multicam.py#L479-L501):

- **SCORE +1** — a ball is detected *crossing the wall in the active target zone* (B1).
- **MISS +1** — a ball is detected *crossing in a different zone*.
- **No count at all** — **no consensus** → the shot is invisible to the system.

So three outcomes are possible per shot: scored, missed (wrong zone), or **not registered**.
The user's "fast shots aren't detected" maps to the third bucket — and the telemetry shows that
bucket dominates.

---

## 4. System telemetry — the core finding

Aggregates over both logs (`goal_debug.jsonl` / `goal_debug2.jsonl`):

**Per-camera ball detection is frequent and confident:**

| Metric | goal_debug | goal_debug2 |
|---|---|---|
| Mean loop FPS | 32.8 | 29.0 |
| camNorth detection rate | 49.7% | 49.5% |
| camEast | 24.3% | 33.3% |
| camSouth | 47.4% | 49.7% |
| camWest | 15.7% | 25.9% |
| Frames with ≥2 cams detecting | **42.5%** | **52.0%** |
| Detection confidence (median) | **0.88** | **0.87** |

→ The cameras *see the ball* a lot, at high confidence. **Raw detection is not the bottleneck.**

**…but the geometry essentially never agrees:**

| Metric | goal_debug | goal_debug2 | Should be |
|---|---|---|---|
| Frames where **any** detection maps into a grid zone | **2.0%** | **4.9%** | high when ball is at wall |
| camSouth detections that map in-grid | **0 / 10,716 (0.0%)** | **0 / 4,770 (0.0%)** | non-zero |
| **Consensus reached** (a scorable crossing) | **9 / 22,622 (0.04%)** | **9 / 9,595 (0.09%)** | many |
| Dominant `no_hit_reason` | `no-consensus` **73.6%** | `no-consensus` **80.2%** | — |
| `no-ball-detections` | 26.4% | 19.7% | — |
| Triangulation reproj error (median) | **1,416 px** | **1,418 px** | **< 25 px** |
| Frames within 25 px (geometrically consistent) | **0 / 9,617** | **0 / 4,987** | most |
| Frames below **200 px** | **0** | **0** | most |
| camEast+camNorth pair reproj (median) | **48,601 px** | 48,615 px | < 25 px |

**Read that again:** out of **14,604** frames where two or more cameras detected a ball,
**not one** triangulated below 200 px, and the median was ~1,400 px on a 1920-px-wide image.
The camEast+camNorth pair is off by ~48,600 px — a flagrant extrinsic/axis error.

---

## 5. Root cause — three layered problems (most → least dominant)

**(1) Broken / unvalidated multi-view calibration — the immediate blocker (FREE to fix).**
If this were *only* motion blur or *only* lack of sync, a **static** ball lying on the turf seen
by two cameras would still triangulate to < 25 px in *some* frames. The complete absence of any
low-error frame (0 below 200 px in 14,604 attempts), plus **camSouth never mapping into the grid**
and the camEast+camNorth pair at ~48,600 px, is the signature of **inconsistent camera geometry**:
- The projector game runs on the **`Remounted_West_East/` post-remount bundle at 1920×1080**, which
  is a recent *candidate* calibration (lateral cams remounted 2026-05-25) — not yet fully validated
  for live geometry.
- `proxiball_3d-main/projector/homography.json` is calibrated at **1920×1200** but the projector
  runs at **1920×1080** (the app prints this warning) — the wall→zone mapping is skewed.
- Intrinsics/extrinsics must match the **runtime resolution** (project rule: K must be scaled per
  resolution). A mismatch here makes *all* triangulation systematically wrong — exactly this pattern.

**(2) No hardware synchronization + fast motion — the hardware ceiling.**
The 4 cameras free-run with up to ±33 ms inter-camera offset (`cameras.md`). A ball at ~10 m/s moves
~330 mm between 30 FPS frames; across unsynced cameras the "same" detection is actually a *different*
3D position in each view, so even with perfect calibration a fast ball cannot triangulate. This is
why the user's bounce-first workaround helps: the slow rebound minimises inter-frame travel.

**(3) Rolling-shutter motion blur — real, secondary here.**
Confirmed limitation of the Hikvision DS-E12 rolling-shutter sensors (`cameras.md`). It degrades
*bbox-center accuracy* on fast balls (a blurred streak's center is ambiguous), feeding the geometry
inconsistency, and it does occasionally drop detections (`no-ball-detections` 20–26%). But median
confidence stays 0.87, so blur is not why scoring fails — it is an accuracy/edge tax.

Additional contributor seen in the video: the **player stands in the projection/camera cone** at
close range, occluding sightlines and casting shadow on the grid.

---

## 6. What this means for the camera purchase

- The professor's plan to buy **global-shutter, hardware-synchronised** cameras is the correct
  strategic upgrade: it removes problems **(2)** and **(3)** — the hard ceilings that no software
  can fix — and is required for real-game (fast, direct-shot) play.
- **But new cameras alone will not make the goal game work**, because the *current* dominant failure
  is **(1) calibration**, which is independent of the sensor. Buying cameras and expecting the game
  to start scoring would disappoint. Sequence it:
  1. **Recalibrate first (free):** regenerate intrinsics at 1920×1080, recompute/validate the
     `Remounted_West_East/` extrinsics, and re-shoot `homography.json` at the real 1920×1080
     projector output. Acceptance gate: triangulation reproj **< 25 px** on a static ball, and
     camSouth detections actually mapping into the grid. Re-run `--debug-log-jsonl` and confirm
     `no-consensus` drops sharply.
  2. **Then upgrade cameras** to global-shutter + hardware trigger sync (see
     `docs/camera_procurement_research_2026-05-28.md`) to unlock fast direct shots.

---

## 7. Reproducible references

- Telemetry analysis scripts: `/tmp/analyze_goal_logs.py`, `/tmp/analyze2.py` (read-only over the JSONL).
- Phone-video frames for scrubbing: setup/HUD at `0:40`, `2:30`, `4:35`; player-in-cone at `0:22`;
  highest-motion bursts at `~22 s`, `~61 s`, `~123 s`, `~277 s`, `~281 s`. Stills extracted to
  `/tmp/img1962_analysis/`.
- Scoring logic: [goal_target_game_multicam.py:479-501](../proxiball_3d-main/projector/goal_target_game_multicam.py#L479-L501).
- Camera limitations baseline: `cameras.md`.

> **One-line summary for the professor:** *"The cameras see the ball fine; the system can't place
> it in 3D because the multi-camera calibration is currently off — that's a free re-calibration fix.
> Global-shutter synced cameras are still the right purchase, because they're the only way to track
> fast, direct shots once the calibration is fixed."*
