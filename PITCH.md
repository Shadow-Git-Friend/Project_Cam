# PITCH.md — Project_Cam Academy Edition

> **Buy cameras once. Replace the GPS vest and the manual video-review
> session with a wall-mounted AI lab.**

## One-pager (academy-facing)

**What it is.** A box of 4–6 fixed cameras plus one workstation that turns
every training session into: GPS-style load numbers for each player (no vest,
no charging, no lost pods), sprint & kick biomechanics, tactical maps, and a
per-player report parents and scouts can read — in Kazakh, Russian or English.

**Why it's different.**
- **No wearables.** Kids train unencumbered; nothing to collect, charge, or
  break. Whole-squad coverage including trialists and visiting teams.
- **On-prem, yours.** Video and child data never leave the building
  (KZ Law № 94-V compliant, consent-first). No subscription meter running
  per player.
- **Open core.** The geometry and metrics engine is inspectable open-source;
  you are not locked to us to read your own data (CSV/Parquet/C3D/PDF export).
- **Built here.** Kazakh/Russian UI, Asia/Almaty time, indoor-arena-first —
  designed for −30 °C winters where training moves inside.

**What's real today (measured, in-repo).** A working multi-camera 3D
tracking rig: 3–4 mm 3D precision on a calibrated volume, 6.2 ms pose
inference, robust ball tracking at 15–18 FPS on 2019-era hardware, a
service layer with CI, monitoring and Docker deploy, and a unit-tested
metrics engine (load, ACWR, stride/kick biomech, pitch control, xT).
A pilot pitch to FC Kairat's academy is already drafted (`kairat_pitch/`).

**The ask.** One pilot academy, 3 months, free: one indoor pitch
instrumented, weekly reports to coaches, exit criteria agreed up front
(see §Funding phases). Hardware at cost (~$4–8k incl. workstation & cameras,
config-dependent); our software free during the pilot.

---

## 10-slide outline (KFF / academy investor deck)

1. **The gap** — GPS vests + video analysts cost €10–50k/yr per academy and
   still miss biomechanics; most KZ academies have neither. One camera rig
   replaces both cost lines.
2. **Product** — 30-second demo video: live 3D skeletons → session report in
   RU/KZ. (Script: docs/, demo/ notebook renders the artifacts.)
3. **What the coach gets** — player card: load, sprints, ACWR injury band,
   asymmetry alert, scan rate; team card: pitch control, pressing, pass map.
4. **Technology proof** — measured rig numbers (3–4 mm precision, 24 GT-tested
   KPIs, benchmark table), not vendor claims. Built on the author's MSc
   multi-camera ballistics research.
5. **Why camera-only wins in KZ** — indoor-first (climate), no per-child
   hardware, data residency, KZ/RU native.
6. **Market** — KFF-affiliated academies + FIFA Talent Academy KZ + private
   academies (Kairat, Jenis, regional); expansion: futsal clubs, Central Asia.
7. **Competition** — Catapult/STATSports (wearables, per-athlete fees),
   Hudl/Wyscout (video, cloud, no biomech), SkillCorner (broadcast-only).
   We are the only on-prem camera-only stack priced for academies.
   (Detail: `business/competitors.md`.)
8. **Business model** — hardware+install one-time, annual software
   maintenance, optional analytics packs & benchmarking consulting.
   Open-core keeps trust and the door open. (`business/pricing_funding.md`.)
9. **Roadmap & team** — engineering plan in
   [`docs/roadmap_2026-08_mvp.md`](docs/roadmap_2026-08_mvp.md), pilot →
   3-academy validation → KFF league-wide.
10. **The ask** — pilot LOI now; ₸-denominated seed for 2 engineers + 4 rigs
    after pilot exit criteria hit.

## Funding phases

| Phase | Duration | Cost to academy | Exit criteria |
|---|---|---|---|
| Pilot (1 academy) | 3 months | hardware at cost, software free | coaches use reports weekly ≥ 80 % of sessions; load KPIs within 10 % of a parallel GPS-vest session; zero data incidents |
| Validation (3 academies) | 6 months | paid install + support | retention ≥ 2/3; documented training-decision changes; parent-report NPS |
| Scale (KFF league-wide) | ongoing | per-academy license | KFF endorsement; standardized scouting export adopted |

## Risks we name ourselves

GPU supply (mitigate: CPU-fallback profile); **model licensing — open, not
solved**: every artifact is audited across three layers (code, weights, training
data) in [`configs/models.yaml`](configs/models.yaml) and
[`docs/model_card.md`](docs/model_card.md), and as of 2026-08-03 **no model in the
live path is cleared for commercial use** — two are Ultralytics AGPL, one is
pretrained on AI Challenger, and the two face models are blocked by their training
data (WIDER FACE CC BY-NC-ND, CASIA/VGGFace2/MS-Celeb-1M) despite permissive code.
A verified-clean pose replacement (RTMO, COCO-only) is identified and is the first
engineering item; **consent and deletion for minors are specified but not yet
implemented**, so Face ID is off for academy use until they are. Astana winters
(indoor-first is the design center, not a workaround), camera vandalism/theft
(ceiling mounts, arena insurance), and
the honest scale limit: full-pitch 11v11 tracking needs the Phase-2 optics
budget — the pilot scope is indoor/small-sided, where the physics is proven.
