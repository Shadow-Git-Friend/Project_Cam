# P0B Session Evidence Pipeline Design

**Date:** 2026-07-29

**Status:** Approved scope; written design awaiting user review

**Parent design:** `2026-07-15-garage-pilot-product-design.md`

**Scope:** Default-on desktop session identity and lifecycle evidence,
deterministic aggregation of existing training and launcher logs, honest
Tauri `SESSIONS`/`SHOTS` views, and fail-closed readiness presentation.

**Protected boundary:** Do not modify `triangulate_multi`,
`transform_world_point_y`, `ema_update`, UDP axis semantics, trajectory
geometry, or launcher fire-control policy.

## 1. Decision

The next locally executable Project Cam milestone is the P0B session evidence
pipeline.

RPM-to-exit-speed and target-plane placement remain the first system-level P0,
but they require physical measurements and cannot be completed from the local
terminal. P0B can proceed now without inventing those measurements: unknown
speed and placement fields remain explicitly unknown until P0A produces them.

The desktop application will stop presenting built-in athlete ratings and
shot rows as though they were operational data. It will instead expose:

- every process launch as a uniquely identified local session attempt;
- immutable launch metadata and append-only lifecycle events;
- existing training summaries and launcher events through one typed,
  read-only evidence API;
- honest empty, partial, malformed-source, and uncalibrated states;
- real `SESSIONS` and `SHOTS` views with source and freshness information.

No database or background service is introduced.

## 2. Verified Starting Point

- The Tauri Rust backend already owns process-group launch, log streaming,
  graduated stop, process polling, local readiness inspection, face-gallery
  name lookup, and a read-only tail of
  `training_logs/sessions_index.jsonl`.
- Training drills already write `project_cam.training.v1` per-session summary
  JSON and append the same record to `sessions_index.jsonl`.
- `project_cam.closed_loop.EventLogger` already defines the versioned
  `project_cam.closed_loop.event_log.v1` stream and the event vocabulary
  `session_start` through `session_end`.
- `launcher_runtime_from_udp.py` can already write the curated EventLogger
  stream and the separate raw engineering decision log when optional CLI
  paths are supplied.
- The legacy Tk control center contains tolerant, bounded-tail parsing for old
  shot-log variants. It is useful compatibility evidence, but it currently
  falls back to synthetic preview rows.
- The Tauri `ANALYTICS` and `MATCHES` views still import fixed `KPIS`, `TREND`,
  `RADAR`, and `MATCHES` data from `src/data.ts`.
- `ControlView` starts with a static green readiness array and keeps that
  fallback when the Rust readiness command fails. This is misleading and
  contradicts the approved product design.

## 3. Approaches Considered

### 3.1 Rust-owned evidence boundary — selected

The Tauri backend creates session lifecycle artifacts, reads bounded local
sources, normalizes them into typed response objects, and returns those
objects to React.

Advantages:

- filesystem access and process lifecycle already live in Rust;
- React receives one stable contract instead of knowing repository paths and
  historical JSONL variants;
- malformed or very large files can be handled before they reach the UI;
- the browser-preview build cannot accidentally claim local operational data;
- unit tests can exercise temporary directory trees without cameras or
  launcher hardware.

Cost: Rust must implement a small amount of tolerant schema conversion that
also exists in the legacy Tk reader.

### 3.2 Python aggregation command

A Python CLI could own normalization and emit `session.json`, `shots.json`,
and `summary.json`; Rust would invoke it and deserialize the result.

This maximizes reuse with Python producers, but it makes every refresh depend
on process startup, Python environment health, stdout protocol discipline,
and another failure mode in the desktop application. It is appropriate later
if aggregation becomes a reusable offline product, not for this local P0.

### 3.3 Frontend filesystem parsing

React could read raw JSON/JSONL through a Tauri filesystem capability and
normalize it in TypeScript.

This is the shortest path to visible rows, but it spreads filesystem paths,
schema compatibility, byte limits, and corruption handling into visual
components. It also weakens the distinction between browser preview and live
desktop data. This approach is rejected.

## 4. Architecture

```text
React CONTROL / TRAINING
        |
        | launch request + session context
        v
Rust process supervisor
        |
        +--> garage_lab_combined/output/sessions/<session_id>/manifest.json
        +--> garage_lab_combined/output/sessions/<session_id>/lifecycle.jsonl
        +--> child environment:
             PROJECT_CAM_SESSION_ID
             PROJECT_CAM_SESSION_DIR
             PROJECT_CAM_EVENT_LOG_OUTPUT

existing raw evidence
  training_logs/sessions_index.jsonl
  training_logs/*_summary.json
  closed-loop EventLogger JSONL
  legacy/raw BLM JSONL
        |
        v
Rust evidence reader/normalizer
        |
        +--> typed sessions
        +--> typed shots
        +--> per-source diagnostics
        |
        v
React SESSIONS / SHOTS
```

The raw files remain the source of truth. Normalized response objects are
derived and can always be regenerated.

The canonical desktop evidence root is
`garage_lab_combined/output/sessions/`. The child event-log default is
`<session_dir>/events.jsonl`.

## 5. Desktop Session Identity and Lifecycle

### 5.1 Session ID

The backend generates the ID; the frontend never invents it. Use an opaque,
filesystem-safe value containing UTC time plus sufficient process-local
uniqueness, for example:

```text
20260729T104512.381Z-000042
```

Athlete names, Face ID labels, and drill names must not appear in directory or
file names.

### 5.2 Manifest

The frontend supplies a small session context alongside the existing process
request: `athlete`, `launch_kind`, and optional `drill`. `launch_kind` is one
of `training`, `viewer`, `recording`, `launcher`, or `maintenance`.

Before starting a child, Rust atomically writes:

```json
{
  "schema_version": "project_cam.desktop.session_manifest.v1",
  "session_id": "20260729T104512.381Z-000042",
  "created_at": "2026-07-29T10:45:12.381Z",
  "athlete": "Арлен",
  "launch_kind": "training",
  "label": "DRILL · SINGLE-LEG BALANCE",
  "program": "bash",
  "args": ["..."],
  "repo_root": "/home/hanush/Desktop/Project_Cam"
}
```

The manifest is immutable after creation. Environment variables and secrets
are not serialized. Arguments are retained because they are part of local
reproducibility evidence; this project currently passes no credentials in
launch arguments.

The launch fails before process creation if the session directory or manifest
cannot be written. A run without writable evidence is not reported as a valid
desktop session.

### 5.3 Lifecycle stream

Rust appends versioned records to `lifecycle.jsonl`:

- `launch_requested`;
- `process_started` with PID/process-group ID;
- `stop_requested`;
- `sigint_sent`, `sigterm_sent`, or `sigkill_sent` when applicable;
- `process_exited` with the observed code;
- `launch_failed` when process creation fails after manifest creation.

Every record contains `schema_version`, `session_id`, UTC timestamp, event,
and a small JSON detail object. The lifecycle stream is append-only.

The frontend receives the generated `session_id` in the launch response and
may display it in diagnostics. It does not write lifecycle files.

### 5.4 Child contract

Every child receives:

- `PROJECT_CAM_SESSION_ID`;
- `PROJECT_CAM_SESSION_DIR`;
- `PROJECT_CAM_EVENT_LOG_OUTPUT`.

`PROJECT_CAM_SESSION_DIR` is the absolute canonical session directory and
`PROJECT_CAM_EVENT_LOG_OUTPUT` is its `events.jsonl` child.

Training summaries will copy `PROJECT_CAM_SESSION_ID` into new
`project_cam.training.v1` records. The launcher runtime will use the
environment values as defaults only when the corresponding explicit CLI
arguments are absent. Explicit CLI values retain precedence.

View-only launchers that do not emit domain events still have supervisor
manifest/lifecycle evidence. This design does not fabricate target, launch,
or outcome events for them.

Maintenance launches such as Face ID enrollment receive lifecycle evidence
with `launch_kind="maintenance"`, but they are excluded from the athlete
`SESSIONS` view by default.

## 6. Evidence Sources and Normalization

### 6.1 Source priority

The reader uses these sources:

1. desktop session manifests and lifecycle streams;
2. `project_cam.training.v1` session index/summary records;
3. `project_cam.closed_loop.event_log.v1` records;
4. legacy/raw BLM JSONL as a compatibility source.

A newer file does not override a more authoritative schema. Records are
joined by exact `session_id` when present. Historical records without a
session ID receive a deterministic in-memory legacy key based on source path
and record timestamp; the raw file is not rewritten.

### 6.2 Session record

The Rust API returns a stable object with:

- session ID or legacy key;
- source schema and source path;
- athlete, launch kind, drill/mode, start/end timestamps;
- status: `running`, `complete`, `aborted`, `failed`, or `partial`;
- evidence completeness flags;
- one source-authored headline when available;
- typed summary values namespaced by drill/source;
- warnings and malformed-record count.

Drill-specific metrics are not collapsed into a universal rating. A balance
sway value, goalkeeper save rate, and line-hop rate remain distinct metrics.

### 6.3 Shot record

One normalized attempted-shot record contains:

- session ID;
- timestamp and sequence number;
- target joint or zone when recorded;
- commanded left/right RPM;
- calibrated speed in m/s only when the source explicitly records it or a
  validated P0A model is available;
- pitch/yaw when recorded;
- state: `launched`, `blocked`, `aborted`, or `unknown`;
- outcome: `hit`, `miss`, `invalid`, or `unknown`;
- safety block reason when present;
- source schema/path and warnings.

`ball_launched` means launched, not hit. A raw command containing the word
`shoot` is not by itself proof of launch if the record says it was blocked or
unsent.

The legacy `live_aim_test.py` field `visual_check` answers “does the aim look
correct?” before firing. It is not a ball-placement outcome and must never be
mapped to hit/miss. Only explicit outcome fields or `outcome_scored` events
may set the normalized outcome.

RPM is displayed as RPM. The UI must never convert RPM to km/h using an
assumed multiplier. Missing calibrated speed is shown as `UNCALIBRATED` or
`—`.

### 6.4 Bounded and tolerant reading

- JSONL is read from a bounded tail rather than loaded without limit.
- Limits apply to bytes, files, sessions, and rows.
- A truncated first tail line is discarded.
- Blank and malformed lines are skipped and counted.
- Non-finite numbers are rejected.
- Unknown schema versions are surfaced in diagnostics and not interpreted as
  known records.
- One unreadable source cannot erase valid evidence from other sources.
- Results are deterministic for the same source bytes and limits.

## 7. Tauri Command Contract

The backend exposes one read-only command equivalent to:

```text
load_session_evidence(
    repo_root,
    athlete_filter?,
    session_limit,
    shot_limit
) -> SessionEvidence
```

`SessionEvidence` contains:

- `sessions`;
- `shots`;
- `summary` with factual counts only;
- `sources` with path, freshness, records accepted/rejected, and errors;
- `generated_at`.

The backend also returns a launch receipt from `spawn_process`:

```text
{ session_id, session_dir }
```

The existing `pipeline-log` and `pipeline-exit` events remain compatible.

## 8. UI Design

### 8.1 Navigation

- Rename `ANALYTICS` to `SESSIONS`.
- Rename `MATCHES` to `SHOTS`.
- Keep `CONTROL` and `TRAINING` unchanged.

### 8.2 Sessions view

Show:

- selected athlete or `ALL ATHLETES`;
- total sessions, complete, aborted/failed, and partial;
- a chronological session list with status, source, drill/mode, duration, and
  source-authored headline;
- per-drill trend panels only when two or more comparable values exist;
- source freshness and parse warnings.

Do not display `LEVEL`, `RATING`, `PROGRESS`, or a radar chart without a
separately validated definition.

### 8.3 Shots view

Show:

- session/time;
- target or zone;
- commanded RPM and calibrated speed as separate fields;
- pitch/yaw;
- launch/block state;
- outcome;
- safety block reason.

Unknown fields render as `—`. Uncalibrated speed is visually explicit.
Blocked attempts are retained because they are safety evidence, not removed
as failed shots.

### 8.4 Refresh and empty states

- Views load on mount and on explicit `REFRESH`.
- They refresh after a desktop child exits.
- No source files produces an honest empty state with the expected paths.
- A partial parse produces rows plus a warning, not a full-page failure.
- Browser preview shows `BROWSER PREVIEW · NO LOCAL DATA ACCESS`; it does not
  silently substitute operational-looking fixtures.

## 9. Readiness Honesty

This P0B slice does not implement active camera opening, model inference
smoke, GPU health, serial identity, or E-stop validation. Those remain the
next readiness/reliability pass.

It does remove the dangerous presentation fallback:

- readiness starts as `UNKNOWN`, not `6/6 ONLINE`;
- failure to invoke or parse `check_readiness` sets explicit
  `CHECK FAILED`/`UNKNOWN` items;
- file presence uses `AVAILABLE` or `PRESENT`, not operational `READY`;
- browser preview is always `UNKNOWN`;
- no readiness card authorizes firing.

## 10. Error Handling and Atomicity

- Create session directories with restrictive normal local permissions and
  opaque names.
- Write `manifest.json` to a sibling temporary file, flush, then rename.
- Append lifecycle records one JSON object per line and flush immediately.
- Failure to create mandatory session evidence prevents the launch and is
  returned to the UI.
- Evidence-read errors are data-quality diagnostics; they do not crash or
  freeze the application.
- UTF-8 athlete names are preserved in JSON content.
- No biometric embeddings, face images, or recognition scores are copied
  into session evidence.

## 11. Testing Strategy

### Rust unit tests

Use temporary repository trees to prove:

- session IDs are unique and filesystem-safe;
- manifest creation is atomic and preserves Unicode;
- lifecycle ordering records clean exit and SIGINT escalation;
- unwritable evidence prevents launch before child creation;
- training records with and without session IDs normalize correctly;
- EventLogger events join by session ID;
- blocked attempts remain visible and are not classified as launches;
- `ball_launched` never implies a hit;
- legacy `visual_check` never becomes a hit/miss outcome;
- RPM without calibrated speed remains RPM/uncalibrated;
- malformed, truncated, non-finite, oversized, and unknown-schema input is
  bounded and diagnosed;
- maintenance launches do not appear in athlete sessions by default.

### Frontend and contract checks

Prove:

- TypeScript compiles with the typed Rust response;
- `SESSIONS`/`SHOTS` replace the old navigation;
- production views do not import synthetic KPI/match constants;
- empty, partial, uncalibrated, blocked, and Unicode-athlete states render;
- readiness starts/fails as unknown;
- refresh occurs after process exit without polling raw files from React.

### Repository verification

Run:

- Rust unit tests;
- TypeScript typecheck and production build;
- focused desktop contract tests;
- existing training, EventLogger, launcher fire-control, and safety tests;
- full Python suite;
- `git diff --check`.

No camera or launcher hardware result may be inferred from these tests.

## 12. Non-Goals

- collecting RPM/speed or target-plane measurements;
- evaluating a trajectory with invented speed uncertainty;
- changing firing authorization or serial ownership;
- active camera/model/GPU/serial/E-stop preflight;
- allowlisted launch profiles and the full supervisor state machine;
- app-close process containment;
- SQLite, cloud sync, accounts, or multi-installation data access;
- synthetic athlete scores or cross-drill ranking;
- rewriting historical source logs;
- changing protected geometry or UDP semantics.

## 13. Acceptance Criteria

P0B is complete when:

1. Every Tauri-started process attempt has a unique manifest. Every
   termination observed by the supervisor has a terminal lifecycle record,
   including launch failures and force-killed runs; a process left behind by
   an application or machine crash remains visibly `partial` rather than
   being reported as complete.
2. New training summaries carry the desktop session ID.
3. Launcher EventLogger defaults can consume the desktop session context
   without overriding explicit CLI values.
4. Historical training sessions appear without source-file rewrites.
5. Existing launcher events and raw shot logs produce honest typed shot or
   blocked-attempt rows.
6. No production screen shows built-in operational-looking athlete or shot
   data when sources are absent.
7. RPM is never presented as calibrated speed without measurement evidence.
8. Readiness command failure produces `UNKNOWN`/`CHECK FAILED`, never green.
9. Corrupt or oversized logs remain bounded and visibly diagnosed.
10. Rust, frontend, focused Python, and full Python verification are green.

The next hardware step remains P0A: collect repeated RPM/speed and
target-plane placement measurements, then feed those measured fields into
this pipeline.
