# Revision Summary

## Evaluator Comment 1: Literature review not sufficiently critical

The literature review was rewritten to compare the thesis system more explicitly against the closest alternatives: commercial open-loop launchers, professional optical motion capture, depth-camera systems, and robotic ball-striking/serving research. A new critical comparison table explains what each system category does well, where it is limited, and how those limitations justify the design choices in this thesis. The revised text now makes clear that the thesis contribution is not a new detector or a motion-capture replacement, but a low-cost integration of multi-camera 3D localisation, body-joint targeting, ballistic aim computation, and safety-gated actuation. A final source-only pass further strengthened the explicit justification for four fixed cameras, DLT/SVD triangulation, the PC--ESP32 architecture split, and staged safety validation.

## Evaluator Comment 2: Evaluation is strong but incomplete

The evaluation, discussion, and conclusion were reframed as partial validation. The revised thesis now explicitly states that full autonomous closed-loop firing at a moving human target has not been completed. The current repository metrics are used as primary evidence: ball static mean error 156.90 mm, P95 288.34 mm; joint-touch mean error 178.98 mm, P95 243.77 mm over 62 valid trials. RQ1 is now marked as not fully satisfied under the current raw evaluation, RQ2 as satisfied with limitations, and RQ3 as partial.

## Evaluator Comment 3: Awkward grammar and repetitive wording

The abstract and Chapters 1--6 were substantially polished for formal academic tone, clearer transitions, and less repetitive phrasing. Claims were made more precise, chapter titles were fixed to avoid duplicated "Chapter N" headings, and appendices were corrected where they referenced older grid coordinates or legacy calibration paths.

## Repository Alignment

The revision uses the local `/home/hanush/Desktop/Project_Cam` project root as the priority technical context. In particular, `README.md`, `CLAUDE.md`, `CANONICAL.md`, `new_complete.md`, `control_12_full.ino`, `.claude/rules/*.md`, `arena_fixed/config/calibration_manifest.yaml`, and `garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/` were used to align the thesis with the current calibration/evaluation state. Older corrected metrics remain treated as bias-correction context only, not as final validation claims.

## Source-Only Figure and Context Pass

The latest pass added a thesis-safe BLM/world-frame context figure to the LaTeX source and clarified the current ESP32 firmware state machine using local project files. These additions support system understanding only; they do not introduce new experiments or claim full moving-target closed-loop validation.

## Output Files

- Revised LaTeX source: `latex_tevised_codex/Master_Thesis_3_revised/`
- Added figure asset: `latex_tevised_codex/Master_Thesis_3_revised/figures/blm_anchor_600_1560_500_multiview.png`
- No DOCX or PDF was regenerated in the latest source-only pass.
