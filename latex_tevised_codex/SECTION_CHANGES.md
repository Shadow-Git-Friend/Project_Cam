# Section-by-Section Changes

## Front Matter

- Rewrote the abstract to state the thesis as partial validation rather than complete closed-loop demonstration.
- Updated abstract metrics to the current repository results: ball mean 156.90 mm, joint mean 178.98 mm.
- Polished the declaration and acknowledgements for academic tone.

## Chapter 1: Introduction

- Rewrote the motivation and problem statement to avoid overclaiming.
- Clarified that the present contribution is a pose-to-aim architecture and partial integration, not completed moving-target firing.
- Revised the research questions so RQ3 explicitly separates staged integration from future moving-target validation.
- Reframed the novelty claims as conservative contributions supported by the thesis evidence.

## Chapter 2: Literature Review and Background Theory

- Added a critical comparison table across commercial launchers, motion capture, depth-camera systems, and robotic ball-striking systems.
- Added explicit design-justification discussion for using four commodity cameras, markerless pose estimation, DLT/SVD triangulation, and staged safety.
- Clarified limitations of calibration, 2D keypoint triangulation, and simplified ballistic modelling.
- Strengthened the critical discussion by explaining why the system accepts lower absolute accuracy than professional motion capture, why detector confidence is insufficient for actuation, and why the PC--ESP32 split is appropriate for the architecture.

## Chapter 3: System Design and Methodology

- Rewrote the chapter for clearer academic English and consistent terminology.
- Updated repository context to the active `arena_fixed` calibration bundle.
- Clarified that dynamic target handling is a runtime state-machine and future validation issue.
- Removed stale cross-reference wording and reduced claims about completed firing.
- Added a BLM anchor/world-frame figure to clarify launcher placement in the calibrated arena.
- Added conservative firmware context from `control_12_full.ino`, including the 921600-baud command path, feeder state machine, RPM-gated pusher motion, and reload behaviour.

## Chapter 4: Ground-Truth Evaluation Protocols

- Corrected ball grid levels to match the current repository data: 200, 750, 1300, and 1800 mm.
- Corrected joint-touch X positions to 2600, 3600, and 4600 mm.
- Added explicit language that dynamic clips are qualitative tracking checks, not closed-loop moving-target validation.
- Reframed bias correction as diagnostic/runtime compensation requiring held-out validation.

## Chapter 5: Results and Analysis

- Removed duplicated text from Chapter 4.
- Replaced older corrected-result framing with current raw repository metrics.
- Added current-result figures generated from the active CSV reports.
- Marked RQ1-related ball localisation as not fully satisfying the original target under current raw metrics.
- Reframed joint-touch results as satisfying the global mean target only with limitations.
- Rewrote dynamic-results discussion to avoid claiming complete moving-target validation.

## Chapter 6: Conclusions and Future Work

- Rewrote conclusions to state the work as a credible perception-to-aim foundation.
- Updated research-objective status table:
  - RQ1: not fully satisfied.
  - RQ2: satisfied with limitations.
  - RQ3: partial.
- Expanded limitations around calibration bias, occlusion, ballistic calibration, single-arena testing, and safety certification.
- Added future-work items for held-out correction validation, empirical ballistic mapping, camera placement, moving-target firing, multi-person tracking, and Virtual 3D Goal measurement.

## Appendices

- Updated Appendix A to state that later firing/full-cycle stages are protocol stages and not automatically completed.
- Updated Appendix B commands to use the active `arena_fixed` calibration paths.
- Updated Appendix C grid tables to match the current ball and joint ground-truth CSV files.
