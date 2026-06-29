# Point-by-Point Response to Evaluators

Dear Evaluators,

Thank you for the careful and constructive feedback. I revised the thesis to address each point directly, while preserving the original project contribution and avoiding unsupported claims.

## 1. Literature review should be more critical

I revised Chapter 2 to make the literature review more analytical rather than only descriptive. The revised chapter now compares the proposed system against four closest categories: commercial open-loop launchers, professional optical motion-capture systems, depth-camera systems, and robotic ball-striking/serving research. I added a critical comparison table that identifies each category's strength, limitation, and design implication for this thesis. I also added clearer justification for the main design choices: low-cost multi-camera triangulation instead of motion capture or a single depth camera, markerless COCO-format pose estimation, a PC--ESP32 architecture split, and staged safety validation for human-facing actuation.

## 2. Evaluation should be framed as partial validation

I revised the evaluation framing throughout the abstract, Chapters 1, 4, 5, and 6. The thesis now explicitly states that the current work validates the perception, calibration, targeting, and safety-gated integration components, but does not claim a completed full closed-loop moving-target firing demonstration. Chapter 5 now uses the current repository evaluation metrics as primary evidence and interprets them conservatively. Chapter 6 updates the research-objective status: RQ1 is not fully satisfied under the current raw ball-localisation metrics, RQ2 is satisfied with limitations, and RQ3 is partial because moving-target closed-loop firing remains future work.

## 3. Language polishing and repetitive wording

I substantially polished the academic English across the front matter and Chapters 1--6. Awkward wording, repetitive claims, and overconfident phrasing were revised. I also corrected inconsistent chapter headings, stale protocol coordinates, and outdated calibration-path references in the appendices. The revised thesis now uses a more formal and cautious tone suitable for final master's thesis submission.

## Summary of Main Substantive Revisions

- The abstract now states the work as strong but incomplete validation.
- The literature review now includes explicit comparison and design justification.
- The evaluation now reports current raw repository metrics and avoids relying on in-sample corrected values as final proof.
- The dynamic tracking section now states clearly that qualitative clips are not equivalent to closed-loop moving-target validation.
- The conclusion now avoids overclaiming and identifies the exact future experiment required: autonomous firing at a moving target with measured projectile outcome.

Respectfully,  
Arlen Smagulov
