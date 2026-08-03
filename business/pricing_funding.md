# Pricing, revenue model & funding plan

## Revenue model (open-core)

| Line | What | Price shape |
|---|---|---|
| Hardware + install | 4–6 cameras, mounts, PoE switch, GPU workstation, calibration day, staff training | one-time, cost + install margin (~$6–12k site, config-dependent) |
| Software maintenance | updates, recalibration support, model refreshes, remote (on-request, not phone-home) diagnostics | annual, ~$3–6k/site |
| Analytics packs (paid, closed) | scouting export pack, cohort benchmarking vs KZ norms, longitudinal athlete file | annual add-ons |
| Consulting | custom drills instrumentation, KPI benchmarking studies, C3D/biomech lab integrations | day rate |
| Open core (free) | geometry + metrics engine, calibration tools, base dashboard | Apache-2.0 — the trust and adoption engine |

Deliberately absent: per-player fees (the anti-Catapult), cloud storage tiers
(on-prem), and any SaaS dependency for core function.

## Cost reality per rig (BOM-level, from repo research)

Camera BOM already researched in-repo (2026-05-29): 4× GigE global-shutter
(HikRobot MV-CS016-10GC / FLIR BFS-PGE-16S2C-CS ≈ $370–450/cam), quad-port
GigE NIC, lenses, mounts, cabling ≈ **$1.5–1.9k**; used-market RTX-class
workstation ≈ $1.5–2.5k; webcam-tier pilot rig (the current 6-USB stack)
proves the software for a fraction of that. Install day + calibration is the
real cost driver — productize it (charuco kit + guided tool, `feat/auto-calibration-v2`).

## Funding phases & asks

| Phase | Ask | Use | Exit criteria |
|---|---|---|---|
| 0. Pilot (now) | LOI + facility access from 1 academy; hardware at cost | 1 rig, 3 months, weekly coach reports | coach adoption ≥ 80 % of sessions, GPS-parallel MAE published, zero data incidents |
| 1. Validation | ~$120–180k (angel/strategic — academy backers are the natural angels) | 2 engineers × 6 mo, 3 rigs, KZ dataset collection under consent | 2/3 academies renew at full price; documented decisions changed by data |
| 2. Scale | KFF league license negotiation + seed | install team, cheaper 2-cam SKU, EasyCoach integration | KFF endorsement; 10+ paying sites |

## Why an academy backer says yes (their words, not ours)

- "Kids train with nothing strapped on, and I still get the load numbers."
- "Parents get a real report in Kazakh — retention and justification for fees."
- "Scouting export means our best 14-year-old is visible to European clubs
  with data, not a highlight reel."
- "It runs in our building; nobody else has our children's video."

## KZ-specific compliance line items (budgeted, not afterthoughts)

- Consent workflow (guardian signatures, registry) — built into onboarding.
- Law № 94-V data-locality audit — annual, part of maintenance.
- Insurance rider for mounted equipment in shared arenas.
