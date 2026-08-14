# Project_Cam — forward roadmap to a pilot-ready product

**Status: authoritative.** This supersedes the phased plan in
`docs/archive/legacy_notes/plan.md` (kept for history) and replaces the generic
15-priority SaaS checklist reviewed on 2026-08-03, which was written against a
system this is not.

Written 2026-08-03. Every "current state" claim below was verified against the
code on that date; the verification notes are in the CLAUDE.md log entry.

---

## What this system is, stated plainly

One operator. One garage, 6.23 × 3.05 m. One PC (RTX 2080 Ti + Quadro P400).
Six USB-2 webcams whose measured ceiling is **15–18 FPS**, and that ceiling is
hardware, not code. One physical ball launcher on a serial link. A desktop
binary launched from an icon — there is no server, no tenant, no fleet.

Consequences that decide the whole plan:

* **Throughput is not a software problem.** 6 cameras × 15 fps = 90 inferences/s
  is the entire budget, shared by the ball engine, the pose engine and the
  renderer. "Concurrent sessions" is physically one.
* **Nothing scales by adding infrastructure.** Kubernetes, GitOps, Redis, CDNs
  and read replicas have no workload to serve here.
* **The binding constraints are physical and legal**, not architectural:
  uncalibrated projectile speed, drills never run against live cameras, and
  models that cannot legally be sold.

## Where the project actually stands (verified 2026-08-03)

| Layer | State |
|---|---|
| Persistence | No database. **But** 10 versioned schemas (`project_cam.*.v1/v2`), canonical session directories, atomic manifest + lifecycle writes from Rust, one byte-capped typed evidence reader, legacy-log import (`parse_legacy_shot`). Owner-only file modes (`0700`/`0600`) |
| Desktop | Tauri: 4 views, 9 named launch profiles (the launch boundary — the UI cannot express a program path), supervisor states `Idle/Starting/Running/Stopping/Faulted`, app-close containment |
| Drills | 9 drills, one shared board layout grammar, tiled windows that open together, 8 ms/frame budget enforced in CI (worst measured 3.89 ms) |
| Tests | **1005 tests, 72 files** (2026-08-03), 52 Rust tests. Includes contract tests across TS↔Rust↔Python, subprocess CLI tests, rendered-frame inspection, API TestClient. Mutation sweeps used on load-bearing invariants |
| CI/CD | `ci.yml`, `docker-smoke.yml`, `Dockerfile`, `Dockerfile.gpu`, eval-gate |
| Observability | `deploy/prometheus`, `deploy/grafana`, `src/project_cam/monitoring/metrics.py`, per-stage `StageTimer` → `--perf-jsonl` |
| API | 12 routes, 17 pydantic schemas, generated `docs/openapi.json`. **No auth, no rate limiting, no CORS** — and it is not exposed |
| Models | Registry with a three-layer licence audit. **0 of 4 active models are commercially usable** |
| Docs | 31 markdown files, 2 DOCX, technical system report with a fact-check ledger |
| Safety | Fail-closed ballistic corridor, firing-line snapshots, RPM gate, angle clamps, S0–S4 gates passed 2026-04-09. Multi-person actuation deliberately disabled |

### Unmerged work and a trap

`f7b574c6` carried a real **academy KPI engine** — `acwr.py`, `physical.py`,
`biomech.py`, `tactical.py`, `report.py` plus `tests/test_academy_metrics.py`,
11 files / +1372 lines, purely additive. **Landed 2026-08-03 as `28922d98`.**

The trap it illustrates is worth keeping: that branch diverged at `4c1dbde2`, so
`main..branch` was −50 658 lines and **merging it would have deleted the heavy
tree**. Check the merge base, cherry-pick the commit, and confirm with
`git show --stat <commit>` that the diff is what you expect.

### The second unmerged commit, and why it is not a straight cherry-pick

`9e0b3916` adds 10 files / +916 lines: `ARCHITECTURE.md`, `AUDIT.md`,
`LICENSE_COMPLIANCE.md`, `METRICS.md`, `PITCH.md`, `ROADMAP.md`, `STACK.md` at the
repository root plus `business/{competitors,market_kz,pricing_funding}.md`. It is
additive and it is not in `main`. Two of those files are hazards:

* **`LICENSE_COMPLIANCE.md` is stale in a dangerous direction.** Written 2026-07-02,
  it knows only about Ultralytics AGPL and SMPL, and argues for shipping AGPL code
  behind process isolation. It predates the AI Challenger finding (2026-07-30) and
  the face-model data-layer finding (2026-08-03), so landing it puts a document
  saying "isolate the process and you are fine" next to a registry that marks four
  models `blocked` with a test enforcing it.
* **`ROADMAP.md` at the repository root would compete with this file**, counting
  weeks from 2026-07-06. A second, more discoverable roadmap is the exact failure
  mode the `plan.md` banner exists to prevent.

**Resolved 2026-08-03 (`724574eb`):** `PITCH.md` and `business/*` landed, the six
other root docs dropped (recoverable with `git show 9e0b3916:<file>`). Landing a
subset broke three cross-references, and two of them were not merely dangling but
*false in an investor-facing document*: `PITCH.md` listed licence isolation as
"mitigated in CI" when four models are blocked, and `business/competitors.md`
promised "a published parallel-session MAE table" that does not exist. Both now
state the real position. **Lesson: cherry-picking part of a docs commit needs a
cross-reference sweep, and the surviving text has to be re-read for claims the
dropped files were carrying.**

Ten local branches are named after features they do not contain —
`feat/triton-serving`, `feat/kz-localization`, `feat/biomechanics-engine`,
`feat/tactical-engine`, `feat/dashboard-streamlit-v1`, `feat/auto-calibration-v2`,
`feat/pose-rtmpose-motionbert`, `feat/metrics-package`, `feat/detect-track-isolated`
and `feat/unified-ingestion`. All ten point at the same two commits. They were
anchor branches from 2026-07-02 and they actively misled planning from a branch
list — renamed to `anchor/*` on 2026-08-03.

## The four real blockers

1. **RPM → m/s is uncalibrated, and it is a safety input, not an accuracy nicety.**
   The corridor evaluator samples the commanded arc using an *assumed* speed
   (`.claude/rules/safety.md`). Tooling exists (`fit_rpm_speed.py`,
   `launcher_common.rpm_to_speed`, `--rpm-speed-model`); measurements do not.
2. ~~**None of the 9 drills has run against a live 6-camera stream.**~~
   **Wrong, corrected 2026-08-03.** `garage_lab_combined/output/training_logs/sessions_index.jsonl`
   holds **34 live sessions** between 2026-07-16 and 2026-08-01 covering all nine
   drills. What was missing was the *reading* of them: an audit that day found
   four sessions carrying physically impossible numbers — 31.6 m of pelvis travel
   in a 6.2 m room, a 0.034 s "save", a 0.10 s down-up, a 751 mm pelvis rise —
   **every one with 6/6 cameras open and `pose_valid_frame_ratio` 1.0**, so a
   capture-quality policy would have admitted all of them. All four root causes
   are now fixed and guarded (`src/project_cam/training/plausibility.py`).
   **The blocker that remains is narrower and real: no session has been read as
   evidence rather than watched**, and until 2026-08-03 the raw pose stream was
   never recorded, so a live fault could not be replayed. `--record-packets` +
   `project_cam.training.replay` close that; the guards themselves are still
   tuned against synthetic noise until a real trace exists.
3. **No model in the live path is commercially usable — but the DRILL product needs
   only one of them fixed (found 2026-08-04).** The drill profile already runs
   `--no-track-ball`, so the AGPL ball detector is never loaded; Face ID is
   optional and already prohibited for academy athletes; SMPL is off for drills.
   That leaves `yolo11m-pose` alone on the critical path, and A5 has now measured
   a licence-clean replacement for it that needs no TensorRT work. Three distinct
   causes remain for the launcher product:
   Ultralytics **AGPL** (ball + pose, code layer), AI Challenger **research-only**
   (RTMPose, data layer), and — found 2026-08-03 — the face pair blocked at the
   **data layer while their code and weights are permissive**: YuNet is MIT but
   trained on WIDER FACE (CC BY-NC-ND 4.0), SFace is Apache-2.0 but trained on
   CASIA-WebFace / VGGFace2 / MS-Celeb-1M (research-only; MS-Celeb-1M retracted).
4. **There is no end-to-end pose ground truth.** Every published figure is
   reconstruction *repeatability* (4.4 mm static) plus a systematic bias. No
   measured millimetre error exists for a moving skeleton, so no accuracy claim
   can be made to a customer.

---

## Plan

Ordering rule: nothing that requires the garage blocks something that does not,
and nothing that requires a customer is started before the blockers above.

### Block A — desk work, no hardware (weeks 1–2)

| # | Item | Owner | Acceptance |
|---|---|---|---|
| A1 | Cherry-pick `f7b574c6` into `main` | **done 2026-08-03** | landed as `28922d98`; one `.gitignore` conflict resolved as a union; suite **951 passed**, ruff clean on the paths CI now lints |
| A2 | Rename the anchor branches to `anchor/*` | **done 2026-08-03** | **ten** of them, not eight — `detect-track-isolated` and `unified-ingestion` are anchors too; `git branch` no longer promises unwritten features |
| A3 | Face-model licence audit closed | **done 2026-08-03** | both rows `blocked` with the data-layer reason and evidence; ledger updated |
| A4 | Colour-category encoding on the boards | **done 2026-08-03** | limb readable under simulated deuteranopia; pinned by two tests |
| A5 | RTMO vs YOLO11m-pose, measured on the **6-camera** rig | **decided 2026-08-04** | `docs/reports/a5_rtmo_vs_yolopose_2026-08-04.md`. Ran on `altai_sync_002`/`003` (6 cameras, 2026-07-01), not the retired 4-camera April sequences. Licence clean, verified from the checkpoint's own embedded config. Detection equal-or-better (camUsb06 95% vs 82%); **9–16% more post-EMA jitter**, reproduced on both clips; rtmo-s 13.0 ms at batch 6 fits the drill profile's 6×10 fps in plain PyTorch — no TensorRT needed. **Not integrated:** viewer `--pose-backend` still `{mmpose, yolopose}` |
| A5b | Integrate RTMO into the viewer and re-check `balance` through the real chain | Claude | `--pose-backend rtmo` wired at the 3 dispatch points; sway measured through `robust_triangulate_joint` + L/R split + EMA + clamp, not the bare ablation path. Accept or reject the jitter penalty on that evidence |
| A6 | Measurement protocol for B1: log format, shot matrix, safety procedure | **done 2026-08-03** | `docs/protocols/2026-08-03-rpm-speed-measurement.md` — two independent methods cross-checked at 10 %, shot matrix from 500 RPM up, log format, acceptance. `fit_rpm_speed.py` fixed so its own acceptance criterion is satisfiable (`n_shots` in every branch, a real residual for the interp model); 6 tests |
| A8 | Physical-plausibility guards on the drills, from the live-log audit | **done 2026-08-03** | `plausibility.py` + guards in 6 drills + board/MISSION-LOG rendering; 31 tests, **15/15 mutations caught**; suite 951 → 1005 |
| A9 | Pose-trace recorder + replay harness | **done 2026-08-03** | `training_drill.py --record-packets` (verbatim, capped, session-dir default) + `project_cam.training.replay`; 10 tests. A live fault is now a fixture that needs no hardware |
| A7 | Land the safe half of `9e0b3916` (Academy docs + `business/`) | **done 2026-08-03** | `724574eb` — `PITCH.md` + `business/{competitors,market_kz,pricing_funding}.md`; the six stale root docs dropped and their three dangling references repointed and corrected |

A5 is the highest-value item in the plan: it is the only path to a product that
can legally be sold, and it needs no lab.

### Block B — garage work (weeks 3–6)

| # | Item | Owner | Acceptance |
|---|---|---|---|
| B1 | RPM → m/s calibration with measured uncertainty | user (operator) | speed model fitted, residual stated, `--rpm-speed-model` wired into the corridor evaluator. Procedure: A6. **BLOCKED 2026-08-13 by a prerequisite: the RPM setpoint map is ~23% high, so commanding 500 settles near 615 and `blm_bridge` correctly refuses to arm — no shot is possible until the encoder scale is verified with a tachometer and the map refitted (`scripts/fit_rpm_setpoint.py`, protocol §1b) and shipped as control_15.** |
| B1b | Corridor clearance sampled over the speed's uncertainty band, not its point estimate | Claude, **with** B1 | `firing_line.py` accepts a speed uncertainty and evaluates `[v−kσ, v+kσ]`. A widening, never a narrowing. Deliberately not written ahead of B1: safety code should not gain an untested parameter before there is a measured σ |
| B2 | Live run of all 9 drills, 6 cameras, **each with a recorded pose trace** | user + Claude | each drill completes one honest session; the trace is kept; thresholds re-tuned from the REAL noise (the plausibility guards are currently set from synthetic reconstruction); defects filed |
| B2b | Re-audit `sessions_index.jsonl` after B2 | Claude | every reported number is one the room can produce; no session enters a baseline unread |
| B3 | Re-measure 6-camera 3D accuracy | user + Claude | static-ball and joint-touch protocols re-run on the current extrinsics |
| B4 | 10 cold-start/stop cycles, then 20 consecutive complete sessions | user | failure modes recorded; no orphaned viewer, no unfinalised MP4 |

Expect B2 to break two or three drills. That is the point of running it.

### Block C — make the data useful to a coach (weeks 7–10)

| # | Item | Owner | Acceptance |
|---|---|---|---|
| C1 | SQLite adapter over the existing evidence chain (`athletes`, `sessions`, `attempts`) | Claude | rebuildable from the JSONL/manifest files; no new source of truth |
| C2 | Session report: CSV + one-page PDF | Claude | a coach can hand it to a parent |
| C3 | Per-drill trend against the athlete's own baseline, using the comparability facts already recorded (`--udp-capture-context`) | Claude | degraded-capture sessions never silently enter a baseline |
| C4 | Athlete profiles (name, age, height, mass, notes) | Claude | replaces free-text names; `athlete_id` already exists in the session record |

**Not** PostgreSQL, Alembic, S3 or MinIO. One SQLite file, derived data only.

### Block D — what an academy needs on paper (weeks 11–12)

| # | Item | Owner | Acceptance |
|---|---|---|---|
| D1 | Consent record per athlete (video + biometric, separately), with retention expiry | Claude | spec at `docs/superpowers/specs/2026-07-15-…` lines 171/438/443 becomes code |
| D2 | Deletion by athlete — including face embeddings | Claude | one command removes every artifact; currently only `--replace` exists |
| D3 | One-page operator procedure + incident/e-stop sheet | Claude | a coach who has never seen the rig can run a session |
| D4 | Release hygiene for the desktop binary | **done 2026-08-03** | `check-binary-fresh.sh` + a `run.sh` that warns and still launches (a refusal under `Terminal=false` would be a new silent failure) + both `.desktop` entries repointed at `run.sh` + `tests/test_desktop_release_hygiene.py` (5 tests, with a negative control) |

### Explicit non-goals for the next 6 months

PostgreSQL · JWT/OAuth2/2FA/RBAC · MLflow, Triton, BentoML, drift detection ·
OpenTelemetry, ELK/Loki, Sentry · ArgoCD, Terraform, canary deploys, chaos
engineering · Playwright, k6 · React Native or any second frontend ·
teams, sharing, leaderboards, forums · Stripe or any billing · wearable, Hudl,
LMS or calendar integrations · Redis, CDN, read replicas · marketplace, plugins.

Each of these solves a problem this system does not have yet. Revisit only when a
signed pilot creates the problem.

## Success criteria that match the hardware

Replacing "1000+ concurrent sessions", "99.9 % uptime" and "10+ paying
academies", none of which are measurable here yet:

* **Reliability** — 20 consecutive complete sessions with no operator
  intervention; ≤1 rep per session voided by tracking loss.
* **Safety** — ball exit speed calibrated with a stated uncertainty; corridor
  clearance recomputed from the measured model, not an assumed 10 m/s.
* **Accuracy** — a measured end-to-end joint error in mm on a synthetic
  ground-truth harness (ARDY is the candidate motion source: Apache-2.0 code,
  commercially-permitting weights, no SMPL dependency).
* **Legal** — every model in the live path `clear` in the registry.
* **Commercial** — one signed pilot, not ten. A week of sessions that a coach
  chose to run again the following week.

## How to keep this document honest

Every claim of the form "X exists" must name the file. Every claim of the form
"X is measured" must name the number and the date. When a blocker is cleared,
the ledger test in `tests/test_model_licensing.py` or the corresponding
characterization test changes in the same commit, and the CLAUDE.md log says so.
