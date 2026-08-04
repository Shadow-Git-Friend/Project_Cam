# Performance Rules

## Scope
- All FPS/perf work is isolated in `Parallel_working/`
- Never modify `garage_lab_combined/scripts/` for performance without approval

## Latest-frame capture fix (2026-06-23, CRITICAL for multi-cam responsiveness)
- `ThreadedCapture.read_latest()` now returns each camera's MOST RECENT frame every call (returns `(ret, frame, ts, is_new)`); staleness is gated by the caller via `--max-frame-age-ms`. The main loop additionally `continue`s when no camera is new (`any_new_frame`), so pose isn't re-run on identical frames.
- Why: the old version returned a frame only if brand-new+unconsumed, so a multi-cam batch needed >=2 async cameras to deliver within the SAME loop iteration. Rare at low fps -> with 6 USB cameras the 3D skeleton updated ~1 Hz even though the renderer showed 40 FPS. The displayed FPS is now the real skeleton update rate (whenever ANY camera refreshes, ~aggregate fps). At 4 cams/15 fps the old code coincided often, which is why it felt instant before.

## Cinematic 3D renderer (2026-06-23, cv2 backend, display-only)
- `--render-theme cinematic` (DEFAULT) | `classic`. Cinematic = dark gradient stage, 1 m floor grid, dim arena/tag wireframe, floor shadow of the skeleton, glowing depth-shaded skeleton colour-coded by body side (orange=left, cyan=right, mint=head, white=torso), white joint cores sized by camera depth, and a top "● LIVE · MULTI-VIEW 3D POSE · <Hz> · <N> cams" HUD. `classic` = the old flat light-grey look.
- Motion trails for wrists+ankles (joints 9,10,15,16) reuse `--trail-len` (default 20). `--auto-orbit [--auto-orbit-speed deg/s]` slowly rotates the view for demos (off by default).
- All additions are inside `draw_live_scene_cv2` + a trail deque + orbit azimuth in the main loop. They do NOT touch `triangulate_multi`, `transform_world_point_y`, `ema_update`, or UDP. Palette/side constants: `LEFT_JOINTS/RIGHT_JOINTS/COL_* /_bone_color/_shade` near `CONNECTIONS`.

## Demo / startup feature set (2026-06-23, all display-only, cv2 backend)
- **One-Euro display filter** (`--display-filter oneeuro` DEFAULT | `ema`): `OneEuroVec` class, one per joint, applied at the joints_state->joints_display stage. Low lag on fast motion, smooth when still — strictly better than the fixed EMA lerp for live display. Tunables `--oneeuro-mincutoff` (1.2), `--oneeuro-beta` (0.3). Does NOT touch `ema_update` (which still smooths joints_state upstream).
- **Velocity heat-colouring** (`--limb-heat`): bones/joints coloured blue->red by per-joint speed (mm/s) via `_heat_color`; `--heat-vmax-mm-s` (2500) sets the hot end. Speed is computed from joints_state frame-deltas in the display block (`joint_speeds`), independent of the Kalman filters.
- **Live metrics HUD** (`--metrics-hud`, default on): height (joint z-extent), reach (wrist-to-wrist span), peak joint speed. Bottom-left panel in cinematic.
- **Squat + push-up rep counters** (`--count-reps`, on in both usb6 launchers): reuses the coach `make_counter`/`frame_kinematics`/`rep_state` (src/project_cam/assessment) but runs lightweight (no separate coach window), updated each frame from `joints_state`, shown in the ATHLETE panel (Squats / Push-ups). BOTH run simultaneously — do squats and the squat line ticks, push-ups and the push-up line ticks. Press **`c`** in the window to reset. Less rigorous than the full `--coach-overlay` window (no ROI/leg-prior cleanup) but good for live demos.
- **2D camera thumbnails** (`--show-thumbnails`): live per-cam feeds inset down the right edge — shows the multi-view behind the 3D.
- **MP4 record** of the 3D view: press `r` in the window to start/stop; writes `--record-dir/arena_demo_<ts>.mp4` (mp4v). Released cleanly on exit. Separate from `run_record_3d.sh`'s always-on `video_writer_3d`.
- **Multi-person IS implemented (2026-07-12, opt-in):** `--multi-person N` (1–8) cross-view association in `src/project_cam/tracking/multi_person.py` (pelvis/torso 2D anchors → project last 3D pelvis into each cam → bitmask one-to-one assignment; new tracks need ≥2-camera pairwise-triangulation consensus + `--mp-min-separation-mm`; stable never-reused IDs). Optional `--face-id` = local YuNet+SFace labels from a private gallery (`--primary-person NAME`, temporal NameVoter; NOT authentication/liveness). The primary person keeps the entire legacy EMA/Kalman/coach/reps/UDP/BLM/SMPL chain; secondaries are render-only colored skeletons (cv2 backend). `--multi-person 1` without `--face-id` = tracker not constructed, legacy path byte-identical. Desktop launcher: `desktop/arena_control_center.py` (Kairat-styled, CONTROL/ANALYTICS/MATCHES views).
- **Unicode name labels (2026-07-15, display-only):** identity pill + LOCAL FACE LABELS text goes through `project_cam.viz.text.put_text/text_size` (lazy `identity_text_helpers()` in the viewer): byte-exact `cv2.putText` for pure-ASCII, PIL+DejaVu cached rasters for non-ASCII (`cv2.putText` alone draws one `?` per non-ASCII UTF-8 byte → «Арлен» became `??????????`), `ascii_safe` translit fallback. Use these helpers for ANY overlay that can contain an athlete name; other HUD text stays plain cv2.

## BLM / ball-launcher live connection (2026-06-23)
- `Parallel_working/run_live_usb6_blm.sh` = cinematic 6-USB viewer + UDP target broadcast (127.0.0.1:5005) + `--demo-blm` aim overlay. The VIEWER NEVER actuates the launcher; it only triangulates + broadcasts the chosen joint + draws where the BLM would aim. Actuation is only ever via `garage_lab_combined/scripts/live_aim_test.py` in Terminal 2.
- **Geometry caveat (must validate before firing):** the 6-USB rig triangulates in the Y-MIRRORED frame and the launcher runs `--world-y-mirror` (so UDP is mirrored too). BLM aim was previously validated only on the canonical 4-cam frame. Do an aim-only S2 test first (`live_aim_test.py --no-shoot-enabled`): aim at a joint and confirm the launcher physically points at the person. If it points to the mirrored side, toggle `--udp-y-mirror/--no-udp-y-mirror` on the viewer. Only after aim is correct + RPM gate (S3) re-checked may `--shoot-enabled` be used (S4), per `.claude/rules/safety.md`.
- Set the real BLM mount position via `BLM_X_MM/BLM_Y_MM/BLM_Z_MM` env vars (mirrored-frame mm); the overlay default is a placeholder.

## Left/right relabeling: per-pair verdict, chain fallback (2026-07-16, corrected 2026-07-29)
- `fix_lr_swaps_for_cam` resolves each L/R pair against the 3D state with a THREE-way own verdict: swap / keep / **ambiguous**. A pair is ambiguous only when neither direction clears both the 0.75 ratio and the `min_advantage_px (6.0)` absolute floor — which is exactly what a collapsed pair does, since two coincident reprojections give `direct == cross`.
- A pair whose own evidence is CONCLUSIVE decides for itself. Only an ambiguous pair defers to the summed verdict of its conclusive siblings in the same chain (`COCO_LR_CHAINS`: face / arms / legs). A chain holding evidence but none of it conclusive stays put; a chain with no measured pairs at all follows the whole-body verdict (≥2 well-separated pairs required).
- Why the chain layer exists: in a single-leg stance the collapsed 3D ankle state reprojects to the same pixel for both sides, so the ankle pair is permanently ambiguous on its own — mixed labels kept triangulating and the legs stayed merged (the "ball of joints" skeleton). Healthy hips/knees carry the ankles.
- **Why it must NOT be a single summed chain vote** (regression found + fixed 2026-07-29): summing the whole chain broke it in both directions, verified numerically at rig scale. (a) A genuinely mirrored pair is OUTVOTED by correctly-labelled siblings — mirror only the wrists and the summed arm cost is dominated by correct shoulders/elbows, so the wrists never unswap and triangulate onto the opposite arm (374 px reprojection residual → ~1.36 m 3D error). (b) A mirrored MAJORITY over-applies and corrupts a clean sibling — mirror elbows+wrists and the chain vote swaps all three pairs, breaking the correct shoulders. The arms chain has no downstream backstop (`--pose-lr-split` guards only knees (13,14) and ankles (15,16)), so (a) reached `joints_state` — i.e. the UDP aim target and the firing-line snapshot. Not display-only.
- Regression tests: `tests/test_pose_lr_fix.py` (collapsed-ankle rescue, whole-body fallback, own-evidence anti-dither, **mirrored distal pair not outvoted**, **conclusive sibling not dragged by a mirrored majority**).
- The SMPL capsule (`--avatar-body`/`--avatar-markers`, opted-in by `run_live_usb6_mirrored_skeleton.sh`) MANGLES on one-leg/floor poses and replaces the raw skeleton — training drills run with `--no-avatar-body --no-avatar-markers`.
- **Chain relabeling is necessary but NOT sufficient** (proven live 2026-07-16): it is prior-based, so once the 3D state is wrong/mixed the labels keep poisoning triangulation. The structural companion is the geometric pair split `--pose-lr-split` (see geometry.md "Geometric L/R pair split") which distrusts labels at triangulation time; ~5.6 ms worst case, trigger-frames only.

## Display skeletal rigidity + rigid latency comp (2026-07-17, "liquid skeleton" fix)
The 07-16 drill profile made the rendered skeleton "liquid" (bones breathing tens of mm, rubbery joints). Root causes quantified by simulation (all display-side; state/UDP were fine):
- **Per-joint latency comp was the main regression**: `--pose-latency-comp-ms 120` rendered each joint at its OWN `kf.predict_ahead(0.12)` — two ends of a bone got independent noisy velocity leads (PN=500/MN=10 KF velocity gain ≈ 2.5 (mm/s)/mm of noise), refreshed at different instants on the async rig → bone-length P95 error doubled at rest, 3-4x during a leg swing (50-124 mm excursions). The uncertainty gate (500 mm) never trips — steady-state pred-unc is ~20 mm.
- **One-Euro beta was unit-mis-scaled ~1000x**: positions are mm so speeds are mm/s; beta 0.3 opened the filter (α>0.95) above ~100-140 mm/s — the NOISE floor — i.e. the display chain had no final smoothing at all. Default is now `--oneeuro-beta 0.015` (passthrough starts ~2 m/s, genuine fast motion).
Fixes (all display-only, flag-guarded; joints_state/UDP/scoring/safety snapshots untouched):
- **Rigid-core latency comp** (`compute_display_leads`): ONE common lead = component-wise median of shoulder/hip KF velocity leads (gates: initialized + fresh ≤3 frames + finite + ‖v‖ ≤ `max_vel_mm_s` + pred-unc<150 mm; ≥3 core joints else zero lead; ‖lead‖ capped 250 mm; EMA α=0.5 across frames). Bones keep their length exactly under the lead; sim showed it also beats per-joint on tracking lag.
- **The velocity gate is a GARBAGE filter, not a motion filter** (corrected 2026-07-29): it was `max_vel_mm_s=2000.0` compared per-component, i.e. 2 m/s = brisk walking. Because it also gates the CORE joints, any faster motion dropped the core quorum below 3 and zeroed the rigid lead for the whole body — so `--pose-latency-comp-ms` was inert for every running drill (the shuttle sprint reaches ~3 m/s), and each crossing translated the entire displayed skeleton ~113 mm in one frame: the exact artifact the rigid lead exists to prevent. Now `max_vel_mm_s=20000.0` (20 m/s, implausible for a human joint) compared as a NORM — the per-component form was anisotropic, rejecting (2100,0,0) while passing the faster (1900,1900,0). Bounding a large-but-real lead is `max_lead_mm`'s job (it clips by norm, preserving direction); the gate's only job is catching a diverged KF.
- `--pose-latency-comp-joint-frac` (default 0) blends per-joint leads back in. **1.0 is NOT a byte-exact legacy restoration** (clarified 2026-07-29): it leads from the EMA'd `joints_state` rather than the KF position (~84 mm behind on a walking ankle), and a joint gated out of the per-joint leads keeps the rigid lead instead of its own — so it under-states the pre-07-17 bone breathing by roughly 2x. Still usable as a directional A/B; just not a replica.
- **Bone-length consistency** (`--pose-bone-consistency`, default ON; `src/project_cam/viz/skeleton_stabilize.py`): learns per-athlete bone lengths (running median, window 150, locks at `--pose-bone-min-samples 45`, hard plausibility bounds per bone) from same-tick triangulations (skips L/R-split-rewritten joints and joints moving >50 mm/tick), then softly clamps displayed limb lengths into ±`--pose-bone-tol 0.13` (overflow compressed 0.45, so a genuinely wrong joint stays visibly wrong). Clamps only bones with both endpoints FRESH (stale EMA-held joints must not be re-fabricated); symmetric width clamp (shoulders/hips) never squeezes below the L/R-split merge threshold. Bank resets on primary identity switch.
- **Two display buffers**: filters write `joints_filtered`; `joints_display` = copy + bone clamp. The ema display branch interpolates against the UNCLAMPED buffer (no clamp feedback).
- **BLM demo overlay now reads joints_state** (was joints_display) — the drawn aim must match what UDP→live_aim_test actually receives, not the lead/clamped render.
- Verified: 649-test suite green (635 at the 07-17 freeze + 14 added by the 07-29 review fixes); before/after sim of the real chain (REST bone-err P95 59→42 mm, knee tracking err 14→7 mm, swing also improved).
- **Every one of these fixes ships as an argparse DEFAULT**, so the suite would have stayed green if any were reverted. `tests/test_display_fix_defaults.py` now pins them (`--pose-latency-comp-joint-frac 0.0`, `--oneeuro-beta 0.015`, `--pose-bone-consistency True`, `--pose-bone-tol 0.13`, `max_vel_mm_s ≥ 10000`). Changing a default must go through that file.
- **The same applies to every SIGNATURE default the live caller relies on** (found 2026-07-29): the viewer calls `fix_lr_swaps_for_cam(...)` overriding only `min_conf`, and `compute_display_leads(...)` positionally, so `margin=0.75`, `min_advantage_px=6.0`, `wholebody_min_sep_px=15.0`, the whole-body quorum `>=2`, `max_lead_mm=250.0` and `split_merged_lr_pair`'s `flip_margin=0.8` ARE the production behaviour. A test that passes these explicitly verifies nothing about production — exercise the defaults. All six are now behaviourally pinned, verified by a 10-mutation sweep (10/10 caught). `flip_margin` in particular had its branch reached 4 times and firing 0 times across the whole suite; genuine near-ties do occur (1334 reachable configs at small L/R separation + a few px of keypoint noise), so a seeded one is now pinned.
- **Bone-length restore gain is capped** (`max_restore_gain=2.5`, 2026-07-29): correcting a bone's length rescales its measured DIRECTION by `target/length`, so a nearly-collapsed bone — whose direction is almost pure triangulation noise — had its noise amplified without bound (2.0x at 132 mm of a learned 440 mm tibia, but 11x at 20 mm and 106x at 2 mm, i.e. 4 mm of noise rendering as 424 mm of jitter). The cap keeps a genuinely collapsed joint visibly collapsed, which is the module's stated intent, and still restores it over successive frames. Merged-legs recovery is unaffected (a 0.30L squeeze has gain 2.04, under the cap).

## Training-drill viewer profile (run_training_drill.sh, 2026-07-16, updated 07-17)
- Appended after the launcher's own args (argparse last-wins), all geometry-safe: `--no-avatar-body --no-avatar-markers`, `--max-frame-age-ms 250` (less cross-camera temporal smear), `--ema-alpha 0.65` (snappier state for mm-scale balance sway), `--kalman-measured-dt` (KF velocity correct on async-refresh rig), `--pose-latency-comp-ms 120` (display-only lead; since 07-17 RIGID whole-skeleton, see section above; UDP/scoring untouched). Per-joint KFs update regardless of `--predict-ahead-ms`, so latency comp works with prediction off.
- EMA snap-band note: with alpha 0.65 and `--ema-snap-thresh-mm 80`, alpha_eff saturates to 1.0 (raw passthrough into joints_state) at ~123 mm/frame ≈ 1.2 m/s at 10 Hz — intended snap behavior for genuine fast motion, but remember the state is nearly raw during it; the display bone clamp is what keeps the RENDER rigid.
- `PROJECT_CAM_FPS` defaults to 10 for drills (halves worst-case frame age vs the 5-fps demo default at 640×360). If cameras fail to open / starve on the USB2 hub: `PROJECT_CAM_FPS=5 ./Parallel_working/run_training_drill.sh ...`.
- Drill-side debounce (`BalanceDrill`): free-foot height is median-filtered over 0.35 s and a touch-down only counts after ≥0.4 s genuinely raised — a one-frame ankle L/R swap can no longer flip the state or count a touch-down.

## Tiled window layout: drill board + 3D arena (2026-07-31, display-only)
- `src/project_cam/viz/window.py` places the cv2 windows: `screen_workarea()` -> `pane_rect(pane, aspect)` -> `place_window(name, rect, pump=cv2.waitKey)`. Flags: `--window-pane {none,left,right,full}` on BOTH `training_drill.py` and `live_4cam_arena_view_parallel.py` (default `none`, so every other profile is unchanged); `run_training_drill.sh --layout split|swap|none` (default **split** = board left, arena right). Window geometry only — no render, triangulation, UDP or scoring change.
- **Use `_NET_WORKAREA`, never the raw screen size.** Measured here: `70, 27, 1850, 1053` on a 1920x1080 screen (GNOME dock 70 px + top panel 27 px). Panes computed from 1920 start at x=0, the WM shifts them clear of the dock, and the two "halves" then overlap by 70 px. Panes are `925x520` each on this rig. Override with `PROJECT_CAM_WORKAREA="x,y,w,h"`.
- **This OpenCV is a Qt build** (`getBuildInformation` -> `QT5`, GTK+ NO), which matters three ways: (1) `WINDOW_KEEPRATIO == 0` is the DEFAULT, so a window sized off-aspect letterboxes with a **light-grey** fill — ugly next to the dark board, which is why panes keep the content aspect exactly; (2) plain `WINDOW_NORMAL` gets `GUI_EXPANDED` chrome (a toolbar strip), and with chrome present `resizeWindow` sizes the FRAME, so a half-screen pane comes out short — pass `WINDOW_NORMAL | WINDOW_GUI_NORMAL` whenever placing a pane; (3) exiting fullscreen restores the previous geometry on this build, but `place_window` is re-asserted on the `f` toggle anyway because other builds collapse the window to a stub.
- **Pump the event loop BEFORE sizing, and re-apply against the readback.** Qt lays out asynchronously: sizing a window in the same tick as its first `imshow` is silently overridden and leaves a 400x250 stub in the corner (this is exactly what the arena window did on the first attempt, while the board — which happened to `waitKey` first — worked). `place_window` pumps, applies, reads `getWindowImageRect`, and corrects (title bar measured +37 px in y), capped at `MAX_CORRECTION_PX = 240` so a clamping WM cannot be chased off-screen.
- **Both windows open together.** The board's `--wait-for-arena S` (wrapper passes `PROJECT_CAM_ARENA_WAIT_S`, default 240) blocks window creation AND `drill.start()` until `UDPJointListener.viewer_alive()` — liveness, never tracking, so an empty arena cannot stall it. Measured on the live rig: arena window +5.7 s, board +8.3 s (was board at ~+1 s, arena +6 s, i.e. an empty scoreboard and a burning countdown through model load). The wrapper runs both children in the background with a watchdog: viewer death SIGINTs the board (fired on its first real run when one camera failed preflight). `run_live_usb6_mirrored_skeleton.sh` now `exec`s python so `$!` is the viewer, not the wrapper shell.

## Drill board render budget (training_drill.py, 2026-07-30)
- The board is the athlete-facing hero window and must not steal the loop from the viewer. Budget: **8 ms/frame**; current measured cost **3.30 ms** at 1280x720, pinned by `test_a_frame_fits_the_budget` in `tests/test_drill_board_render.py`.
- **Profile the renderer, never estimate it.** The first pass measured **8.22 ms** — already over budget — and the two costs were not where they looked: `glow r=206` was **2.31 ms** because the additive blend round-tripped ~170k px through float32, and `text()` was **0.46 ms per string** because the drop-shadow outline draws every string twice.
- Fixes that got 8.22 -> 3.30 ms, both cache-based: `_bg()` builds the gradient/grid background once into `_BG_CACHE` and returns `cached.copy()`; glow sprites are pre-rasterised as **uint8** patches (`_build_glow_sprite`, `_GLOW_PATCH`) and composited with `cv2.addWeighted(roi, 1.0, patch, gain, 0.0, dst=roi)` — SIMD, no float conversion, clipped to the ROI at the frame edges. `text()`/`text_c()` take `shadow=True|False`; the eight small labels that do not need separation pass `False`.
- `_bg()` MUST return a copy. Returning the cached array lets one frame's overlays persist into the next; `test_bg_returns_a_copy` pins it.
- **Presentation invariants that only rendered frames reveal:** a cue colour left over in the result state read as a result (yellow means "the system is asking for something", never "here is your outcome"). Tests passed; the eye caught it. Render states to PNG and look at them as part of any board change — then pin what you found (`test_a_cue_never_reads_as_a_result`).
- **Vacuous board tests are the default failure mode.** A drill's initial state is `idle`, where most drawers render nothing, so a naive "does it draw" test passes without drawing. Parametrise over real states and assert something was actually drawn.
## One layout grammar for all 9 drill boards (2026-07-31)
- Every board is built from the same shared components, so a coach reading any drill knows where to look: **`stat_rail`** (per-attempt breakdown, top-left) · **`note_right`** (the protocol fact the number must be read against, top-right) · **`hero`** (value + unit + caption + optional `tier_of` verdict, ~0.24-0.42 H) or **`prompt`**/**`countdown`** in that same slot · the spatial **stage** below (0.46-0.84 H) · a session strip at ~0.845 H (`history_bars` / `cadence_strip` / `ghost_split_bar` / `recovery_decay`) · then hints + `evidence_rail`. Two stage shapes are legitimate: a square stage flanked by values (`balance`'s sway reticle — the design the user signed off on) and hero-above / wide-stage-below (everything else).
- Shared primitives added with the redesign: `hero`, `prompt`, `countdown`, `stat_rail`, `note_right`, `history_bars`, `live_dot`, `height_column`, `goal_frame`. Reuse them rather than hand-placing a new board.
- **A colour that carries a CATEGORY must be duplicated in text** (2026-08-03). `hop_symmetry` encoded which limb hopped as GREEN left / AMBER right — a pair that collapses to indistinguishable olive under a Machado deuteranopia simulation, on a board an athlete reads from three metres, affecting roughly one man in twelve. `history_bars(tags=[...])` now stamps `L`/`R` on each bar and the legend names the letters, not the colours. Tier words (`PERFECT`/`LATE`) were already text-duplicated; this closes the same gap for categories. A colour carrying a *quality* (green good / amber late / red miss) is fine as long as the value and its verdict word are on screen.
- **`history_bars(colors=[...])` when the colour is a property of the ATTEMPT, not the value** (which limb hopped, which set). Colouring by value means looking the value back up, and two equal measurements — the normal case for a symmetric athlete — both take the first one's colour.
- **`height_column` has two modes and mixing them lies.** `fill_from="mid"` + `show_mid` = deviation from the athlete's own reference (cmj pelvis rise); `fill_from="bottom"` + `show_mid=False` = absolute height where the marked thresholds carry the meaning (gk_updown DOWN/SET). An arbitrary mid line in the absolute mode put a second rule beside DOWN and read as a threshold that does not exist. Draw the fill BEFORE the marks (a tall fill painted over the lines that give it meaning) and keep the tint at ~0.22 — the bright value edge plus its glow is what should read, not a slab.
- **The cue colour must not survive into a result — and that includes landmarks.** Only the live cue is YELLOW: `reactive_cut`'s resolved gate kept cue yellow (now the verdict colour), and its permanently-yellow CUE line now goes STEEL outside `approach`/`active` (the shuttle's START line was already white for this reason). `gk_save` previously tinted every corner by its miss rate, so a red slab from three rounds ago competed with the live cue — now the cued corner is the only thing that glows, and the per-corner record lives in the rail.
- Enforced in `tests/test_drill_board_render.py`: hero band never empty in a live state (measured 1380-12716 lit px, fails under 1200), ink-profile drift between 720 and 1080 under 0.30 (catches absolute-pixel geometry — `gk_save` was the last drawer with `gy0, gy1 = 130, 520`), no cue-yellow left in a result (masked as `r>200 & g>200 & b<80`, because AMBER is a legitimate result colour), plus the 4-size × 9-drill overflow sweep. **6/6 mutation-verified.**
- Frame cost after the redesign: worst board **3.89 ms** (reaction_zones set_wait), all nine between 2.06 and 3.89 ms against the 8 ms budget.

- **A guarded fault must be renderable, or the guard only half-works (2026-08-03).** The plausibility layer turned three silent faults into named outcomes, and each needed a place on the board: an anticipation renders `TOO EARLY - NOT SCORED` in AMBER (never cue-yellow, and never the `MISS` branch it would otherwise have fallen into), a void says what to do next, `balance` prints `NO MEASURED HOLD` plus the rejected-sample count where an empty panel would have read as "nothing happened", `cmj` carries a `FAULT` row. The same applies to `event_line` — a new event kind falls through to a raw `json.dumps` in the MISSION LOG, and worse, a new *result* value can silently match an older branch and be described as something it is not.
- Scale everything through `sc(H, s)` for font scales and **`px(H, value)` for layout offsets** (both normalised to 720), and derive positions from `cv2.getTextSize` rather than magic pixel constants — a hardcoded offset collided `1400 mm` with `stabilise 0.6 s` at one width.
- **A fixed pixel offset under text that scales with H is a fullscreen bug** (found 2026-07-31): the top-right progress+clock was pinned at `W - 330`, sized at 1280x720, so at 1920x1080 it ran **109 px past the right edge** on `ROUND 20/20` (36 px at 1600x900) — visible on exactly the two drills the desktop launched fullscreen. It is now right-aligned from the measured width, the top bar / key hints / evidence rail / `STAGE_BOTTOM_RESERVED` all go through `px(H, ...)`, and the athlete name is centred by `name_width()` (cv2 measures Cyrillic by BYTES, so a `getTextSize` centre puts «Арлен» far left — use `project_cam.viz.text.text_size`, which returns cv2's `((w,h), baseline)` shape). `px(720, ·)` is the identity, so the reviewed 720 layout is byte-identical.
- The board now runs at three real sizes — 1280x720 baseline, ~925x520 tiled pane, 1920x1080 fullscreen. `tests/test_drill_board_render.py` sweeps all 9 drills across all of them and fails if ANY label leaves the frame; keep new drills inside that sweep.
- Timing resolution shown on the board is **derived from the observed packet rate** (`±0.5/Hz`), never a constant. `evidence_rail()` goes green only on verified capture context and renders `UNAVAILABLE` when there is none.

## Third-party model throughput math (do this before evaluating any external model, 2026-07-30)
- Live budget on this rig: **6 cameras × 15 fps = 90 inferences/s on an 11 GB 2080 Ti**, sharing the GPU with the ball engine, the pose engine and the renderer. Any candidate model gets checked against that number first, before licence, before accuracy.
- Worked example (**LocateAnything-3B**, rejected 2026-07-30): 12.7 BPS on a single H100. An H100 is roughly 5-8x a 2080 Ti on transformer inference, so the shortfall is one to two orders of magnitude. A 3B-parameter VLM is an **offline labelling tool** at best, never a live detector here — no amount of quantisation closes 35-50x.
- Worked example (**ARDY**, candidate): text encoder ~14 GB bf16 > our 11 GB. The escape is architectural, not numeric — prompt embeddings are computed once and cached offline, so only the motion model needs the GPU. Check whether a stated VRAM figure belongs to a stage you can precompute before writing the model off.
- VRAM headroom on this box is the binding constraint more often than FLOPs: the ball and pose TRT contexts already pre-allocate ~880 + 794 MB (see TensorRT Export above), and an 11 GB card running two engines plus a display GPU has no room for a second large model.

## Robust per-joint pose triangulation (2026-06-23)
- `robust_triangulate_joint(...)` (`--pose-max-reproj-px`, default 40) rejects outlier camera rays per joint, mirroring `robust_triangulate_ball`. Stops a bad camera pose / transient 2D mis-detection from flinging a joint to a random point. See `.claude/rules/geometry.md`.

## Profiles (Parallel_working/)
- quality: baseline behavior, no forced optimizations
- balanced: best current skeleton placement + moderate speedup
- smooth: 30fps capture, EMA 0.40, stale-frames 12, render-worker-process
- smooth_v2: cv2 renderer, adaptive EMA, display interpolation (~2ms 3D render)
- predictive: smooth_v2 + Kalman filter prediction + ghost skeleton (RECOMMENDED)
- maxfps: 960x540 + aggressive skip — KNOWN to cause skeleton drift

## Rules
- Never trade geometric correctness for FPS without explicit approval
- Resolution changes require intrinsics scaling verification
- `--render-worker-process` is safe (offloads matplotlib to child process)
- `--max-frame-age-ms` is safe (drops stale frames, does not alter geometry)
- `--pose-every N` / `--ball-every N` / `--viz-every N` are safe skip params
- Monitor perf with `--perf-log-every` and `--perf-jsonl` flags

## Kalman Prediction
- `--predict-ahead-ms` controls prediction horizon (0 = disabled, 400 = recommended)
- `--kalman-process-noise` and `--kalman-measurement-noise` tune filter responsiveness
- `--show-ghost-skeleton` renders predicted position as translucent skeleton in cv2 view
- `--predict-max-uncertainty-mm` discards predictions with too much uncertainty
- Kalman filter is geometry-safe: operates on post-triangulation 3D points only
- UDP packets include both `joints` (current) and `predicted` (future) when active

## YOLO-Pose Backend
- `--pose-backend yolopose` — YOLO11m-Pose, single-model (no separate detector)
- `--yolopose-model yolo11m-pose.pt` or `.engine` for TRT
- 3.6x faster offline (25 vs 7 fps for 4-cam sequential), 6.2x faster live with TRT
- Matches MMPose 3D accuracy within 5mm jitter — validated 2026-04-06 ablation
- Slightly lower detection rate on oblique views (94% vs 100%) — acceptable trade-off

## Evaluation Tools
- `record_test_sequence.py` — threaded 4-cam recording, saves frames + timestamps
- `ablation_ema_adaptive.py` — 3-phase (cache poses → triangulate → sweep EMA variants)
- Both support `--pose-backend yolopose|mmpose`
- Results in `Parallel_working/output/ablation_results/`

## BLM-Integrated Live Run
- `Parallel_working/run_live_blm.sh` combines live yolopose viewer + Kalman prediction + UDP target broadcast + `--demo-blm` overlay
- Pair with `garage_lab_combined/scripts/live_aim_test.py` in Terminal 2 for interactive aiming
- UDP target joints (13): nose, shoulders, elbows, wrists, hips, knees, ankles
- Default Kalman: PN=500, MN=10, predict-ahead 400ms (best for walk/jog)
- This run script lives in `Parallel_working/` but its serial counterpart in `garage_lab_combined/` is the only path that touches BLM hardware

## TensorRT Export (mandatory)
- Always export YOLO engines with `dynamic=True` and `--yolo-batch` = camera count (4-cam rig → 4, 6-USB rig → 6). `export_models_tensorrt.py` takes `--yolo-batch` since 2026-07-02.
- Static batch=1 engines segfault (ball) or silently fail (pose) when viewer passes multi-frame batch; a batch-4 engine crashes ultralytics (`setInputShape` error → IndexError) on a 6-frame batch. The viewer chunks via `--ball-max-batch`/`--pose-max-batch` as the runtime guard.
- **Size the profile to the real operating point** (2026-07-02): ultralytics sets profile max = 2×imgsz, and the TRT execution context pre-allocates activation memory for batch×max². `--yolo-imgsz 1280` at batch 6 → 2560² max → ~6 GB per context → ball+pose cannot coexist on the 11 GB 2080 Ti. Export ball with `--yolo-imgsz 672` (max 1344, still covers imgsz 960) and pose with `--yolo-imgsz 640` (max 1280); contexts shrink ~3.6× and opt-shape tactics match actual inference sizes.
- ONNX input `[1, 3, H, W]` = broken; `['batch', 3, 'height', 'width']` = correct
- **Inference imgsz is LOCKED to the engine's export imgsz** (proven on real frames 2026-07-02): the dynamic profile covers BATCH, not the spatial decode. `yolo11m-pose.engine` exported @640 gave bit-exact results @640 but ~300 garbage detections/frame @960/@1280 ("NMS time limit exceeded", empty arena; under concurrent load it escalated to CUDA illegal-memory-access). Same for the ball engine (@672 exact, @960 garbage). Current export sizes: pose **960**, ball **672**. To run another size, re-export at that size.
- **Verify every new engine on a REAL frame with a person/ball, never blank frames** — zeros produce zero detections at any size and pass trivially. Gate: detections/frame == the `.pt` model's at the same imgsz, keypoint/box coords match within a pixel (`garage_lab_combined/test_clips/` has 6-cam clips).
- `--parallel-inference` (ball in a worker thread) is EXPERIMENTAL and known-unsafe on torch 2.1 + TRT 10.16 — keep off until the ball worker gets its own CUDA stream/process.
- After any `.pt` swap, rebuild the `.engine` from scratch (delete old `.onnx` + `.engine` first)
- Never run the live viewer (or any GPU process) during an engine build — the builder needs headroom for tactic search and OOMs otherwise (transient `virtualMemoryBuffer OutOfMemory` lines during a build with free GPU are just oversized tactics being skipped, harmless)

## Ball Tracking Robustness (2026-04-13, extended 2026-04-20)
- Live viewer uses `robust_triangulate_ball`: iteratively rejects cameras with reprojection error > `--ball-max-reproj-px` (default 25 px as of 2026-04-17)
- Dedicated ball `JointKalmanFilter` (CV model): defaults `--ball-kalman-process-noise 800 --ball-kalman-measurement-noise 25`
- Max-speed gate: `--ball-max-speed-mps 40` discards physically impossible jumps
- Coast-through-drop: `--ball-coast-frames 6` lets KF predict during brief detection failures (~400 ms at 15 FPS)
- Replaces naive ball EMA. Do not reintroduce `ema_update(ball_state, ...)` — the KF owns ball smoothing now
- Tune reproj threshold down if false positives persist, up if edge-of-frame balls get dropped

### Ball Detection Levers (2026-04-20, measured on real bounce/fast/slow recordings)
- `--ball-imgsz` (default 672) — engine exported with `dynamic=True` so inference-time resize works. **Bumping to 960 moves camNorth bounce detection from 58% → 98%.** +8 ms per 4-cam batch, fits 15 FPS budget.
- `--ball-conf` (default 0.40) — lowering to 0.15 recovers +4–6 pp detection rate on fast/bounce but adds false-positive risk on empty frames. Consider 0.25 as conservative middle ground.
- Motion-blur streak presence: real (aspect > 1.5 seen at low conf on fast/bounce). Fixing via top-K + multi-hypothesis association is Tier 2 (requires regression fixtures).
- **Structural bounce limit:** at bounce moment only camNorth reliably sees the ball (other 3 cams are 10–17% regardless of detector tuning). No threshold/model change fixes it — the ball is genuinely outside East/South/West frustums or occluded. The fix is the single-cam fallback (below) or camera-placement changes (hardware).

### Single-camera fallback (2026-04-20)
- `project_ray_to_z_plane(obs_norm, R, tvec, target_z)` — new helper in `live_4cam_arena_view_parallel.py`. Intersects one camera's undistorted ray with a world Z-plane. Pure geometry, no iteration.
- Flag-guarded, off by default:
  - `--ball-single-cam-fallback` — enable
  - `--ball-single-cam-max-frames 15` — cap before forcing coast-through (prevents KF depth drift without geometric constraint)
  - `--ball-single-cam-floor-mm 0.0` — cold-start Z-plane if KF has no depth yet
- When ≥2 cams: unchanged SVD path (`robust_triangulate_ball`). When exactly 1 cam + flag on + within max-frames: ray→Z-plane; Z taken from `ball_kf.predict_ahead(1/fps)`, else floor. When 0 cams: unchanged coast-through.
- Does **not** modify `triangulate_multi`, `transform_world_point_y`, `ema_update`, or UDP schema.
- Recommended live flags for bounce-heavy sessions: `--ball-imgsz 960 --ball-single-cam-fallback`.

### Candidate selection gates (2026-04-21)
- `--ball-max-box-side-px 220` (default on) — rejects any YOLO candidate whose larger bbox side exceeds 220 px. Primary defense against "person curled around ball" being labelled as a ball. A tennis ball at arena distance is <~120 px; 220 keeps close-range legit detections, rejects body/cone-sized blobs.
- `--ball-min-box-side-px 0` (default off) — lower bound on bbox side; enable (e.g. 6) to filter detector-noise micro-boxes.
- `--ball-kf-gate-px 150` (default on) — when the ball KF is locked, per-cam selection prefers the candidate whose center is within 150 px of the KF-predicted reprojection. Falls back to highest-conf candidate if no candidate is within gate (so re-acquisitions after long drops still work). Primary defense against markers/cones/bodies when the real ball is currently being tracked.
- Both gates operate on raw YOLO candidates *before* `robust_triangulate_ball`. They only filter the per-cam "winner" choice; they do not change triangulation, KF dynamics, or UDP schema.
- Enabling `--ball-kf-gate-px` makes it safe to lower `--ball-conf` 0.40 → 0.25 (the gate filters the extra noise).
- Set either gate to `0` to disable. Use `0 0 0` trio to A/B test old selection behavior: `--ball-max-box-side-px 0 --ball-min-box-side-px 0 --ball-kf-gate-px 0`.

### Offline diagnosis tool
- `Parallel_working/scripts/ball_detection_analyzer.py` — read-only sweep of conf thresholds + top-K over a sequence. Accepts either per-cam frame directories (`--sequence`) or `mosaic2d_*.mp4` 2×2 tiled videos (`--mosaic`). Reports per-cam detection rate, multi-box frequency, bbox aspect ratio histogram, and recovered-vs-0.40 delta.

## Recording (run_record_3d.sh)
- Writes `Parallel_working/output/recordings/arena3d_<ts>.mp4` + `mosaic2d_<ts>.mp4`
- Uses `mp4v` fourcc — MP4s only playable after clean `VideoWriter.release()`
- SIGTERM/SIGINT handler in `live_4cam_arena_view_parallel.py` breaks the loop cleanly so moov atom is written
- Never stop recording with `timeout`/`kill -9` — resulting MP4 is unrecoverable (no moov atom, ffmpeg cannot remux)
- Stop with `q` in the cv2 window or a single Ctrl+C

## Camera hardware upgrade path (2026-05-29)
- **PC (HP Z4 G4, measured):** i9-7900X 10C/20T (44 PCIe3 lanes), 32 GB RAM, RTX 2080 Ti 11 GB (inference) + Quadro P400 2 GB (display), Ubuntu 22.04/k6.8, single 238 GB SATA SSD (60 GB free). The PC is NOT the bottleneck for a 4× global-shutter @ 60 fps upgrade — CPU/RAM/GPU/PCIe all have large headroom (GigE even *drops* CPU vs MJPG decode). Only TWO additions needed: a **NIC** and (for raw recording) an **NVMe SSD**.
- **Plan:** replace all 4 webcams with **4× global-shutter GigE cameras** (HikRobot MV-CS016-10GC IMX296 ~65 fps, or FLIR BFS-PGE-16S2C-CS IMX273 78 fps) + hardware trigger from ESP32. Count stays 4 (1:1; never mix shutter types). Connection = **Intel I350-T4 quad-port GigE NIC** (one dedicated lane/cam), power + trigger via each cam's Hirose I/O cable (12 V + ESP32 opto fan-out), skip PoE. Raw 60 fps record = 373 MB/s → add **2 TB NVMe** (board M.2). Lenses ~3.5–4 mm (NOT 6 mm — too narrow vs current ~81–86° HFOV).
- **Do NOT "just add 4 more DS-E12 webcams" to get 8.** Helps pose coverage only IF split across USB controllers (all 4 current ones share one Bus-001 USB-2 controller → ~15 fps ceiling; 8 on one controller = bandwidth failure). It does NOT fix the goal/fast-ball blocker: rolling shutter stays and **no-sync gets worse** (more unsynced views of a moving ball). Also halves inference fps (8-cam batches) and doubles calibration burden. USB-2 webcams don't scale; GigE does.
- The global-shutter + hardware-sync upgrade is orthogonal to the (free) goal-game software fix — buy fixes fast-ball tracking, software fix makes scoring work. See `.claude/rules/geometry.md` triangulation-pairing + camSouth notes.

## Face enrollment camera handling (2026-07-14)
- Desktop SCAN MY FACE runs `Parallel_working/scripts/face_enroll.py --arena-config garage_lab_combined/config/cameras_6usb_test.yaml --replace` — opens ALL arena cameras and captures face embeddings while the athlete walks a full circle. Better than one webcam: embeddings come from the same cameras/angles used for live recognition, so enroll/recognize are consistent.
- **USB-2 bandwidth wall:** the 6 webcams share one controller; the generic "1080P USB Camera" units HANG forever inside `cv2.VideoCapture` at 1280×720. So enrollment runs the two C920s at 1280×720 (bigger face crop, ~40–70 px at 2–3 m) and the generics at 640×480. The live viewer runs all at 640×360 for the same reason. **Never open 6 webcams at 1280 concurrently.**
- **Parallel bounded open:** `_ThreadedCamera.__init__` starts the open in a worker thread and does NOT block; the caller waits on all cameras with a shared ~7 s deadline → all 6 open in ~0.8 s, a flaky/slow unit is skipped (contributes 0), and a hung `VideoCapture` can never freeze the app. Sequential per-camera opens summed to ~36 s and stalled. Reuse this pattern for any multi-USB open.
- **Clean exit is mandatory:** OpenCV's V4L2 backend + camera threads `std::terminate` (SIGABRT / core dump) or sit in `do_wait` during normal interpreter shutdown, even after the gallery is saved. The arena path therefore `os._exit(code)` on EVERY exit path (normal / signal / exception). A **hard-stop signal handler (`SIGINT/SIGTERM → os._exit`) installed at the very start** so a control-center STOP kills the process instantly in any phase (open / capture / shutdown) — verified ~100–700 ms (it previously appeared to "never stop" because the handler only covered the capture loop).
- Completion = time window `--max-duration` (30 s, "walk one lap"), early finish if `--target-samples` (24) from `--target-cameras` (1) after `--min-duration`; saves if ≥8 samples. STOP aborts without saving; only a normal window-finish saves. Progress bar is TIME-based so it fills predictably even when faces are far.

## Known Issues
- maxfps at 960x540 causes skeleton placement errors
- matplotlib 3D rendering is the main bottleneck — render-worker-process helps
- Threaded capture + staleness gate improves freshness but not raw throughput
- Kalman prediction is ~neutral on jump motion (CV model limitation) — do not tune to it
