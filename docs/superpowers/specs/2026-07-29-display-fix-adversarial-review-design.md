# Project_Cam Display-Fix Adversarial Review Design

**Date:** 2026-07-29  
**Branch:** `feature/multi-person-face-id-desktop-20260712`  
**Baseline:** 659 tests passing, with two existing environment/deprecation warnings  
**Status:** Design approved; awaiting written-spec review

## Context

The 2026-07-17 “liquid skeleton” work introduced rigid common-mode display
latency compensation, a per-athlete bone-length bank, a display-only skeleton
clamp, and safer left/right relabel guards. The interrupted adversarial review
later confirmed and fixed two regressions:

1. a chain-level left/right vote could corrupt published wrist or hip state;
2. a 2 m/s velocity gate disabled rigid latency compensation during running.

The same review also identified weak tests. Those gaps have since been closed
with tests for production defaults, robust medians, confidence gates, the
left/right ratio and absolute-advantage guards, and anti-churn behavior. The
remaining work is to complete the four review lenses that were interrupted:

1. display/state isolation;
2. skeleton clamp mathematics;
3. integration and per-athlete lifecycle wiring;
4. technical-report fact-checking.

## Goal

Finish the four review lenses, reproduce every material finding, and apply the
smallest safe correction for each confirmed defect. Preserve the invariant
that presentation corrections never affect measurement, drill scoring, UDP
publication, aiming state, or firing-line safety state.

## Non-Goals

- Do not add new training, tracking, launcher, or UI features.
- Do not perform RPM-to-m/s calibration in this change.
- Do not redesign the pose pipeline or split the live viewer into new modules
  unless a confirmed defect cannot be corrected safely in place.
- Do not change protected geometry or safety semantics without a failing
  regression test that demonstrates the defect.
- Do not claim live or hardware commissioning from unit or simulation results.

## Review Method

Each lens follows the same evidence sequence:

1. inspect the current implementation and enumerate its explicit invariants;
2. construct the smallest deterministic reproducer;
3. run the reproducer against the current code;
4. reject findings that do not reproduce;
5. for a confirmed defect, add a test that fails for the demonstrated reason;
6. implement the smallest correction;
7. run the focused tests and then the full suite.

Source changes are not justified by code-reading suspicion alone. A finding
must have observable evidence: a failing test, a numerical counterexample, a
wrong serialized value, or a report claim contradicted by a repository source.

## Lens 1: Display/State Isolation

Use deliberately different sentinel coordinates for measured state, filtered
display state, and clamped/latency-led render state. Verify the consumers at
each boundary:

- rendering consumes `joints_display`;
- drill and coach calculations consume `joints_state`;
- UDP joint serialization consumes `joints_state`;
- the BLM demo target and overlay use state coordinates rather than display
  coordinates;
- `build_firing_line_safety_snapshot` receives state coordinates and metadata;
- display transforms do not mutate `joints_state` through a shared NumPy view.

Where an inline `main()` path cannot be exercised without cameras, use a
focused pure helper or a narrow source-wiring contract. A helper is preferred
when it reduces ambiguity without changing behavior. A source-text assertion
is acceptable only for wiring that cannot be isolated economically, and its
test must explain why it is intentionally structural.

## Lens 2: Skeleton Clamp Mathematics

Test the public behavior of `BoneLengthBank` and
`stabilize_display_skeleton` over representative and adversarial inputs:

- no-op behavior before a length locks and inside the tolerance band;
- upper- and lower-band soft-clamp equations;
- convergence toward the band without overshoot or oscillation;
- root-to-child chain order when a corrected joint is shared by two bones;
- preservation of bone direction and bilateral-pair midpoint;
- NaN, missing, stale, and zero-length endpoint handling;
- plausibility bounds and in-bound median outlier resistance;
- the minimum bilateral separation floor;
- float32/float64 behavior without input alias corruption.

Root-outward order is intentional, not an error by itself. It becomes a defect
only if a deterministic example violates the documented postconditions or
produces unstable repeated application.

## Lens 3: Integration and Athlete Lifecycle

Trace the bone bank and display buffers through initialization, primary-track
handoff, reacquisition, stale-joint expiry, and multi-person rendering.

Required contracts:

- a primary-person change clears learned bone lengths, filter state, and rigid
  lead history before the new athlete is rendered;
- one athlete’s learned proportions cannot be reused for another athlete;
- secondary tracks do not share the primary bank;
- if secondary tracks remain unstabilized, that limitation is explicit and
  consistent with their render-only status;
- learning uses same-tick, sufficiently confident multi-camera measurements
  and excludes joints rewritten by the left/right split;
- the clamp reads a copy of the filtered display buffer and cannot feed a
  later EMA iteration.

If the current behavior is correct but under-documented, improve the contract
test or documentation rather than changing runtime semantics.

## Lens 4: Technical Report Fact-Check

Build a review table with one row per material claim:

| Claim | Repository or authoritative source | Verification result | Action |
|---|---|---|---|
| Runtime default or wrapper behavior | parser/wrapper source | match/mismatch | keep/correct |
| Performance or accuracy number | tracked JSON/CSV/report artifact | recomputed/scoped | keep/correct/qualify |
| Safety behavior | implementation and tests | implemented/prototype/planned | label accurately |
| Generated figure or document link | generated asset path | resolves/missing | keep/fix |
| External product or licensing statement | authoritative upstream source | current/uncertain | cite/qualify/remove |

Repository-grounded claims must be checked against the code and artifacts
actually present in this working tree. External claims that cannot be verified
from an authoritative source are qualified or removed. Corrected Markdown is
the source of truth; the DOCX is regenerated from it. The build must fail on a
missing local figure even if Pandoc exits successfully.

## Error Handling and Safety

- Tests must distinguish a genuine product defect from a missing local tool,
  unavailable GPU, or hardware-only prerequisite.
- Report generation must surface missing Pandoc, fonts, images, or source
  files as explicit failures.
- No camera, launcher, serial device, or live firing action is required.
- Existing unrelated working-tree changes are preserved.
- If a finding would require changing firing authorization or physical
  launcher behavior, stop at the reproduced finding and prepare a separate
  safety design rather than broadening this work.

## Verification

Focused tests run after each confirmed correction. The final verification is:

1. all new reproducer and contract tests pass;
2. the complete Python suite passes from the 659-test baseline;
3. report-builder tests pass;
4. the Markdown report builds to DOCX when local build prerequisites exist;
5. referenced images resolve and the generated document opens successfully;
6. `git diff --check` reports no whitespace errors;
7. the final report distinguishes verified fixes, rejected findings,
   documentation-only corrections, and hardware validation still required.

The two current warnings—Starlette/httpx deprecation and unavailable CUDA
forward compatibility in a CPU-valid test—are recorded but are not success
failures unless this work introduces additional warnings.

## Deliverables

- focused regression or contract tests for confirmed findings;
- minimal runtime fixes, if evidence requires them;
- a fact-checked Markdown technical report and regenerated DOCX;
- updated project review/session documentation;
- a final evidence summary with focused and full-suite command results;
- no commit, because repository commits are performed by the user.
