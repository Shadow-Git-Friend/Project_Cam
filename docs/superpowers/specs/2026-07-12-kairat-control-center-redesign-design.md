# Kairat-Style Arena Control Center — Design Spec

**Date:** 2026-07-12  
**Status:** Approved by the user's explicit request to make the app close to the FC Kairat landing-page language and continue the existing redesign  
**Scope:** `desktop/arena_control_center.py`, desktop icon, headless data contracts, and visual verification

## Goal

Turn the existing dark developer-oriented launcher into a coherent sports-performance desktop product while preserving every working launch, Face ID, process-management, and STOP behavior. The result should feel related to FC Kairat through black/yellow contrast, bold condensed uppercase typography, disciplined card grids, and match-oriented information hierarchy, without copying the club logo or site assets.

## Inputs And Constraints

The design is driven by three user-provided screenshots:

- the current black Control Center with launch actions and `IDLE` footer;
- a future match/ball table with gun, target, speed, angle, spin, result, and time;
- a future analytics dashboard with Level, Exactness, Quickness, Progress, Rating, trend, and radar charts.

The official site blocks automated inspection with HTTP 403, so the implementation uses the stable FC Kairat brand language visible in public references: yellow `#FFDD00`/`#FFDE00`, black, white, bold sports typography, rectangular editorial blocks, and strong high-contrast navigation.

## Approaches Considered

### 1. Cosmetic Restyle Only

Keep the single Control screen and only replace orange/cyan accents with yellow. This is low risk but does not create the future athlete dashboard shown in the references.

### 2. Native Tk Sports Dashboard Shell — Selected

Keep the current Python/Tk desktop runtime and add a persistent branded shell with `CONTROL`, `ANALYTICS`, and `MATCHES` views. This preserves one-click local operation, works offline, requires no web server, and creates stable data seams for future camera metrics.

### 3. Browser/Electron Frontend

Build a separate HTML application. This could provide more advanced visual effects, but adds packaging, IPC, browser-runtime, and deployment complexity before the camera/analytics schemas are stable.

## Visual System

- Background: `#0A0A0B`.
- Sidebar: `#0E0E10`.
- Panels: `#141416`; cards: `#19191C`; borders: `#26262B`.
- Primary accent: Kairat-inspired yellow `#FFDE00`; hover `#FFE94D`.
- Main text: `#F7F7F4`; muted text: `#9C9CA3`; faint metadata: `#5F5F66`.
- Green is semantic success only; red is miss/error/STOP only.
- Uppercase condensed sans-serif for brand, navigation, section headings, and KPIs.
- Monospace only for logs, commands, timestamps, and dense machine values.
- Rectangular cards and thin rules; no decorative gradients in the app UI.
- The SVG application icon keeps the Project Cam camera/skeleton mark and adopts the same black/yellow palette.

## Application Shell

The window uses one stable frame:

1. Top brand bar with `PC`, `PROJECT CAM`, and yellow `ARENA CONTROL CENTER`.
2. A thin yellow separator.
3. A 210 px sidebar with `CONTROL`, `ANALYTICS`, and `MATCHES`.
4. One content view at a time.
5. A global process footer with state, command, and STOP.

Active navigation is shown by a yellow four-pixel bar and yellow label. Future navigation items remain visible but disabled/faint so the product direction is legible without pretending those features exist.

## CONTROL View

CONTROL retains all existing behavior:

- four launch modes;
- multi-person count;
- local Face ID toggle;
- auto-orbit and limb heat;
- primary-person name;
- model download, enrollment, and gallery list;
- mission log;
- one-process interlock and process-group SIGINT STOP.

The left side contains dense operational cards; the right side is an expandable mission log. A compact readiness strip reports only real local state:

- configured camera devices found or `NOT CONNECTED`;
- calibration/config availability;
- Face ID model availability;
- gallery availability/sample count.

Readiness must never fabricate connected hardware.

## ANALYTICS View

The view contains:

- athlete/session heading and refresh action;
- five equal KPI cards: Level, Exactness, Quickness, Progress, Rating;
- rating trend chart occupying roughly 60% of the lower row;
- radar chart occupying roughly 40%;
- a conspicuous `PREVIEW · DEMO DATA` banner when live analytics are absent.

Live and demo values must never be mixed. When a live profile exists but omits a field, the UI shows `—`/`N/A`; it must not silently borrow the demo value.

## MATCHES View

The view mirrors the future session screenshot using a dense table:

`# / GUN / TARGET / SPEED / ANGLE / SPIN / RESULT / TIME`

Hit and miss use both symbols/text and color. Missing fields render as `—`. Live source path and refresh time remain visible. When no shot log exists, the table uses clearly labelled preview data.

## Data Boundaries

The GUI reads optional artifacts but does not invent a new analytics pipeline:

- analytics: `output/analytics/athlete_profile.json`, then `garage_lab_combined/output/analytics/athlete_profile.json`;
- match logs: newest JSONL with shot/fire events under supported `blm_logs` directories;
- readiness: filesystem/config/model/gallery inspection only.

Each loader is a pure, headless-testable function. Invalid JSON, partial records, and absent directories degrade to an honest unavailable/demo state instead of crashing the GUI.

## Process Safety

The redesign must not alter how live pipelines are constructed or stopped. Commands remain argv lists, not shell strings. Only one child process may run. STOP sends SIGINT to the child process group so video writers can finalize. Closing the window sends the same signal when a child is active.

## Verification

- Headless unit tests for live/demo analytics separation, shot parsing including spin, readiness state, and argv safety.
- Existing desktop tests must remain green.
- Python compile and Ruff checks.
- Render all three views under Xvfb at 1280×820 and inspect screenshots for clipping, hierarchy, demo labels, table columns, and state colors.
- Re-run related multi-person/Face ID tests to ensure the UI redesign did not alter the tracking layer.

## Out Of Scope

- Implementing the future training-scoring algorithms.
- Claiming cameras are connected when they are not available.
- Adding liveness authentication.
- Replacing Tk with a web runtime.
- Copying FC Kairat logos, copyrighted imagery, or website source assets.
