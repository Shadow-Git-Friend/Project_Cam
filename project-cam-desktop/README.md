# Project Cam — Arena Control Center (Desktop)

A Tauri + React + TypeScript + Tailwind desktop rebuild of the Arena Control Center,
styled in the strict **black / yellow (#FFD700) / white** sports-tech theme.
Charts use **Recharts**, icons use **lucide-react**.

## Stack

- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS
- **Charts:** Recharts (only comparable per-drill evidence trends)
- **Icons:** lucide-react
- **Desktop shell:** Tauri 2 (Rust)

## Structure

```
project-cam-desktop/
├─ index.html                 # loads Inter + JetBrains Mono
├─ package.json
├─ tailwind.config.js         # arena.* color tokens
├─ vite.config.ts             # port 1420 for Tauri
├─ src/
│  ├─ main.tsx
│  ├─ index.css               # theme, scrollbars, log-cursor keyframe
│  ├─ App.tsx                 # shell + view state + launch/stop + mission log
│  ├─ data.ts                 # launch catalog + unknown-first presence checks
│  ├─ evidence.ts             # typed boundary for the Rust evidence command
│  ├─ drills.ts               # training drill catalog (ids match project_cam.training)
│  ├─ components/
│  │  ├─ Topbar.tsx           # PC badge + wordmark + meta
│  │  ├─ Sidebar.tsx          # CONTROL / TRAINING / SESSIONS / SHOTS nav
│  │  ├─ Footer.tsx           # status + command + STOP
│  │  └─ SectionLabel.tsx
│  └─ views/
│     ├─ ControlView.tsx      # launch cards, tracking options, face gallery, readiness, log
│     ├─ TrainingView.tsx     # GK + field-player drill catalog, start/config, recent sessions
│     ├─ SessionsView.tsx     # real session totals, rows, comparable drill trend
│     └─ ShotsView.tsx        # explicit launches/blocks; no inferred outcomes
└─ src-tauri/
   ├─ tauri.conf.json         # 1280×860 dark window
   ├─ Cargo.toml
   ├─ build.rs
   ├─ src/main.rs             # process-group supervisor + Tauri commands
   ├─ src/session.rs          # manifests, lifecycle, inherited child context
   ├─ src/evidence/           # bounded JSONL readers + schema normalization
   └─ icons/icon.svg          # app icon (convert to .ico/.icns/.png — see below)
```

## Prerequisites

- Node 18+
- Rust + Cargo (https://rustup.rs)
- Tauri 2 system deps for your OS: https://tauri.app/start/prerequisites/

## Run (development)

```bash
cd project-cam-desktop
npm install
npm run tauri dev
```

`npm run tauri dev` starts Vite on port 1420 and opens the native window.
(For a browser-only preview of the UI, run `npm run dev` and open http://localhost:1420.)

## Build (production binaries)

```bash
npm run tauri build
```

Installers land in `src-tauri/target/release/bundle/`.

## App icon

`src-tauri/icons/icon.svg` is the source. Tauri needs raster/platform icons — generate them from the SVG:

```bash
# rasterize to PNG (needs rsvg-convert or Inkscape)
rsvg-convert -w 1024 -h 1024 src-tauri/icons/icon.svg -o app-icon.png

# let Tauri produce every size + .ico + .icns
npm run tauri icon app-icon.png
```

## Session evidence

The Rust supervisor creates evidence before every desktop-managed process
launch. The canonical layout is:

```text
garage_lab_combined/output/sessions/<opaque-session-id>/
├─ manifest.json       immutable launch context
├─ lifecycle.jsonl     append-only launch/start/stop/exit records
└─ events.jsonl        optional closed-loop EventLogger stream
```

Children inherit:

```text
PROJECT_CAM_SESSION_ID
PROJECT_CAM_SESSION_DIR
PROJECT_CAM_EVENT_LOG_OUTPUT
```

The training runner adds the inherited ID to
`project_cam.training.v1` summaries. The launcher runtime uses the inherited
ID and event-log path only as argparse defaults, so explicit CLI arguments
still win and standalone launches remain compatible.

The `SESSIONS` and `SHOTS` views call one typed Tauri command. Rust reads only
bounded tails and normalizes:

- desktop `project_cam.desktop.session_manifest.v1` +
  `project_cam.desktop.lifecycle.v1`;
- training `project_cam.training.v1`, including historical rows without a
  desktop ID;
- `project_cam.closed_loop.event_log.v1`;
- explicit legacy BLM `shoot`/`shoot_blocked` and
  `FIRE_SENT`/`FIRE_BLOCKED` rows.

Malformed, unknown, oversized, or truncated sources are reported without
inventing replacement rows. A browser-only Vite preview has no local evidence
access and says so. Missing fields render as `—`; partial sessions stay
`PARTIAL`; missing outcomes stay `OUTCOME UNKNOWN`.

`visual_check` in historical `live_aim_test.py` means “did the aim look
correct before firing?” It is never interpreted as HIT/MISS.

RPM and speed are separate evidence fields. RPM is a launcher command value;
an m/s value is labelled calibrated only when its source explicitly records
calibration proof. Otherwise the UI shows `UNCALIBRATED`.

## Presence checks

The CONTROL cards are local file/device-node presence checks only. Their
initial and failed-command state is `UNKNOWN`/`CHECK FAILED`; they do not claim
camera streaming, model loading, GPU, launcher, E-stop, or firing readiness.

## Verification

From the repository root:

```bash
cd project-cam-desktop/src-tauri
cargo fmt --check
cargo test
cargo clippy --all-targets -- -D warnings

cd ..
npm run build

cd ..
venv/bin/python -m pytest -o addopts='' \
  tests/test_desktop_session_evidence_contracts.py \
  tests/test_desktop_training_contracts.py \
  tests/test_training_drills.py \
  tests/test_launcher_runtime_fire_control.py
```

The pipeline is hardware-free to inspect and build. Live camera/launcher
readiness, RPM→m/s calibration, placement measurements, and physical shot
validation remain separate lab procedures.

Colors remain centralized as `arena.*` tokens in `tailwind.config.js`.
