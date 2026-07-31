# Remote week plan — 2026-07 (no lab, no assistant)

Everything here is doable with a laptop + phone. Ordered by leverage.
Context: the 3D arena software track hit its hardware ceiling on 2026-07-02
(USB2 bandwidth, rolling shutter, no sync, webcam optics on floor poses).
Next step per plan = hardware + commercial track, both remote-friendly.

## 0. Before leaving (needs the lab PC, ~1 hour)

- [ ] Push branch `projector-goal-detection-fixes-20260528` (+ the 12 academy
      branches if the portfolio repo should carry them) and open the PR —
      public `main` goes green on merge. You run pushes; nothing is pushed yet.
- [ ] Record offline fixtures with the current rig: 30–60 s clips of
      push-ups, single-leg raise, lying down, walking (same format as
      `garage_lab_combined/test_clips/altai_dataset_*`). These make floor-pose
      tuning an offline parameter sweep instead of lab time — the single
      biggest unblocking artifact for when you're back.
- [ ] (Optional) Tailscale/SSH on the Z4 → you can trigger recordings and
      sweeps remotely all week.
- [ ] Send the professor the camera BoM email (drafted 2026-05-29).

## 1. Camera procurement (highest leverage — lead times are weeks)

Spec is final since 2026-05-29 (`.claude/rules/perf.md`, CLAUDE.md 2026-05-29):
- 4× **HikRobot MV-CS016-10GC** (GigE, global shutter, IMX296, ~65 fps)
  — or 4× FLIR BFS-PGE-16S2C-CS (~$371 verified) as alternative
- **Intel I350-T4** quad-port GigE NIC (one dedicated lane per camera)
- Lenses **3.5–4 mm** (NOT 6 mm — matches current ~81–86° HFOV)
- **2 TB NVMe** (M.2) for raw 60 fps recording
- 12 V supply + ESP32 opto trigger via Hirose I/O (skip PoE)
- Total ≈ $1.5–1.9k. PC (HP Z4 G4) needs nothing else.

Remote actions: request quotes (HikRobot KZ/RU distributors, FLIR via Flir/
Teledyne resellers), confirm lead times, push the university PO through the
professor. Every week of delay is a week of the rig staying webcam-bound.

## 2. Academy pilot outreach (PITCH.md + kairat_pitch/ are ready)

- [ ] Kairat academy: request the pilot meeting (deck: `kairat_pitch/*.pptx`,
      one-pager: `PITCH.md`). Ask for: one indoor pitch, 3 months, LOI.
- [ ] Verify every fact marked *(verify)* in `business/market_kz.md` and
      `business/competitors.md` (KFF academy list, FIFA Talent Academy KZ
      contact, EasyCoach partnership terms, Veo/Catapult local pricing).
- [ ] Draft the guardian consent form + data-handling one-pager (KZ Law
      № 94-V; requirements sketched in LICENSE_COMPLIANCE.md §5). Needed
      before ANY academy recording — pure writing, fully remote.

## 3. License swap groundwork (ship-blocker for the startup, laptop-only)

Per STACK.md/LICENSE_COMPLIANCE.md the sold path must drop in-process
AGPL/NC. Remote-friendly prep:
- [ ] Read RT-DETR (Apache) fine-tuning docs; pick the ball/player detector
      path that replaces ultralytics in-process use.
- [ ] Register for SoccerNet (research eval) — approval takes days.
- [ ] Download-queue permissive weights: RTMPose (already in-repo), ViTPose,
      MotionBERT (research eval of the 3D-lift path).
- [ ] Decide open-core split so `pyproject` license metadata can be fixed.

## 4. Writing (zero-dependency)

- [ ] Thesis: fold 2026 spring–summer engineering into the draft (rig
      evolution 4→6 cams, robustness gates, latency compensation, the four
      TRT root-causes from 2026-07-02 — good "lessons" material).
- [ ] Update `ROADMAP.md` W1–2 acceptance tests against what today proved
      (AT-1 calibration gate unchanged; ingestion AT-2 now explicitly needs
      the GigE hardware).

## Explicitly NOT remote (park until back in lab)

- RPM→m/s launcher calibration (needs firing measurements)
- Projector goal-game Phase 1 fix validation (needs projector + cameras)
- Floor-pose tuning sweeps (needs the fixtures from §0 — recorded, they can
  run over SSH; without them, park it)
- Any BLM live testing (S-gates require operator presence)

## If "no assistant" is only about this machine

Claude Code also runs at claude.ai/code (web/mobile) against the GitHub
repo — reviewing quotes, drafting outreach, or editing these docs works from
a phone. Requires the branch to be pushed (§0).
