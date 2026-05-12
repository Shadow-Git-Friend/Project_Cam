# Response to Evaluator Comments — Master_Thesis_3 (Revised Submission)

**Author:** Arlen Smagulov
**Programme:** MSc Electrical and Computer Engineering, Nazarbayev University
**Supervisor:** Prof.\ Sultangali Arzykulov
**Co-supervisor:** Prof.\ Mohammad Hashmi
**Date:** 2026

---

Dear evaluator,

Thank you for the careful and constructive review of my thesis. The three points you raised — the critical depth of the literature review, the framing of the evaluation as partial rather than complete, and the language polish — were valuable, and the revised submission addresses them in full. The revision also incorporates substantive engineering and validation work completed since the original submission, which strengthens the answers to your concerns rather than introducing new claims that would need to be re-evaluated. The point-by-point response below summarises the changes.

---

## Comment 1 — "The literature review is good in coverage but not sufficiently critical. Compare your approach more explicitly with the closest existing systems and justify your design choices more clearly."

**Where addressed:** Chapter 2 (Literature Review and Background Theory), particularly §2.7 (Summary, Critical Comparison, and Research Gap), and the new sub-topic sections within §§2.4, §2.5, and §2.7.

**What changed:**

1. **Two new analytical subsections** were added at the end of §2.7. The first, "Why the observed accuracy gap is acceptable," explicitly acknowledges that this work's 95.17 mm ball / 143.38 mm joint figures are roughly an order of magnitude worse than Category-B motion capture (sub-millimetre, with markers, in laboratories) and are the same order as Category-C ball-only research prototypes (50–100 mm). The paragraph then explains why the contribution is the combined capability–cost envelope (joint-level targeting, which Category B does not do, plus closed-loop ballistic actuation, which Category B does not include) at one to three orders of magnitude lower hardware cost, rather than point-wise accuracy superiority.

2. The second new subsection, "Design-choice justification," ties each major engineering decision in this thesis to the specific limitation of the analogue system it replaces. The decisions covered are: (i) four commodity USB cameras over stereo or depth, (ii) ChArUco-plus-AprilTag calibration over bundle adjustment or SLAM, (iii) DLT/SVD triangulation over iterative non-linear methods, (iv) YOLO-Pose primary with MMPose as a reference back-end, (v) constant-velocity Kalman filter for prediction, (vi) asymmetric minimum-camera thresholds (3 for joints, 2 for ball), (vii) ESP32 single-microcontroller architecture at 921 600 baud, and (viii) multi-modal voice integration via UDP IPC. Each justification is grounded in material already present elsewhere in the thesis; no new experiments are claimed.

3. **Three new sub-topic sections** were added to extend coverage where the original review was thin: real-time pose estimation under edge-deployment constraints (grounding the YOLO-Pose backend choice and the TensorRT FP16 deployment), Kalman filtering for sports and human-motion tracking (grounding the predictive layer used in the live runtime), and voice-command interfaces in human–robot interaction (grounding the Vosk integration). These sub-topics use a small set of newly-added references (YOLO-Pose, TensorRT, Kalman 1960, Bar-Shalom, Vosk, ISO 13849-1, IEC 60204-1, plus a pose-estimation survey and a voice-HRI survey) and do not renumber any of the existing references.

4. The bold research-gap statement at the end of §2.7 was rewritten with the partial-validation caveat appended, so that the gap stated in the literature review is consistent with the validation regime actually achieved.

---

## Comment 2 — "The system is not validated in a full closed-loop setting with a moving target; conclusions should be carefully framed as partial validation."

**Where addressed:** Throughout the thesis. The partial-validation framing is now applied at every overclaim surface, with the moving-target closed-loop firing regime consistently identified as the unvalidated boundary.

**What changed:**

1. **Abstract** was rewritten. The opening paragraph now states explicitly that the thesis is a "strong but partial validation," that the perception pipeline, the predictive tracker, the safety-gated runtime, and the static and live-aim integration tests have been validated end-to-end on real hardware, and that fully autonomous closed-loop firing at a moving human subject remains as the final integration milestone and is designated as future work.

2. **Chapter 1, §1.4 Statement of Novelty and Contributions** was rewritten. Each of the original three contributions retains its substantive claim but now carries an explicit scope qualifier tying it to the validation regime actually achieved. A fourth contribution (the multi-modal voice + auto-reload training-mode interface) was added with the same discipline — it is claimed at the level of integration wiring and dry-run / aim-only operation, with closed-loop voice firing on a moving subject explicitly deferred.

3. **Chapter 2, §2.7 Research Gap** appends the partial-validation caveat to the bold gap statement, so that the literature-review gap is consistent with what has actually been demonstrated.

4. **Chapter 5 opens with a new "Scope of Validation" preamble paragraph** that enumerates the eight validated regimes and the one unvalidated boundary. The paragraph explicitly reiterates the in-sample bias-correction limitation that was already noted at the end of Chapter 4. The "Both acceptance criteria are met" sentence in §5.3 was softened to make the in-sample nature of the corrected figures clear.

5. **Chapter 5 also acquired five new results sections** that report the post-submission engineering work in a manner that is honest about its scope. §5.6 is the YOLO-Pose vs MMPose ablation. §5.7 is the Kalman-prediction tuning. §5.8 is the ball-detection robustness improvement (model upgrade, image-size lever, candidate-selection gates). §5.9 is the integrated live test of 2026-04-09 on three named joints; this section explicitly notes that the second nose-targeted shot at 800 RPM was off-target because the empirical RPM-to-velocity calibration is not yet complete, rather than glossing over the limitation. §5.10 reports the voice-bridge wiring validation in dry-run / aim-only mode and explicitly defers closed-loop voice firing on a moving subject.

6. **Chapter 6 was rewritten**. The summary of contributions mirrors the four contributions of §1.4, each with its scope qualifier. Table 6.1 now has four rows: RQ1 and RQ2 stay "Satisfied" (both are satisfied within their respective static-perception evaluation regimes), RQ3 moves from "Partial" to "Satisfied within static / live-aim regime; moving-target firing pending", and a new RQ4 row covers the voice-bridge wiring marked "Satisfied for wiring; closed-loop voice firing pending." The Limitations section gained four new bullets (in-sample bias-correction fitting, closed-loop firing on a moving subject, RPM-to-velocity calibration pending, constant-velocity assumption on jump motion). Future Work was reorganised so that the closed-loop moving-target firing milestone and the empirical RPM-to-velocity calibration are the two most urgent items, framed as the two halves of the same near-term experiment.

The intent of the framing change is not to retreat from any of the original claims but to make precisely visible what the underlying experiments actually demonstrate. Where additional work has been completed since the original submission, the new claims are added at the same level of evidential discipline (Section 5.9 reports a controlled live test that did happen, with both its successes and the observed nose-shot deviation; Section 5.10 reports a wiring validation that did happen, with the closed-loop firing extension explicitly identified as future work).

---

## Comment 3 — "There are awkward and unidiomatic sentences, grammatical issues, and repetitive wording. The presentation would benefit from substantial language polishing."

**Where addressed:** The full thesis. The polish pass was surgical: sentences with concrete defects (grammar, idiom, awkwardness, repetition) were rewritten; clean prose was left alone to avoid introducing inconsistency.

**Specific defects fixed (representative list):**

- Acknowledgements: the original "show his best thanks…from the bottom of his heart" was rewritten in a formal academic register.
- §1.1: the colloquial "The reason is obvious" was removed; "The athlete has to be in the planned sequence of movements of the simulator" was rewritten as idiomatic English.
- §1.4 Novelty Claim 1 had two pronoun errors: "They determine this by observing the athlete" (the launcher is singular) and "uses the ball launcher themselves as the target" (the noun and pronoun do not agree). Both were rewritten.
- §3.8.5 had the informal section title "Why This Is Non-Trivial," which was changed to "Why Real-Time Targeting Is Non-Trivial."
- §6.5: "The authors comment on this and underpin that" used the wrong number (single-author thesis) and the wrong verb ("underpin" is not the verb intended). The sentence was rewritten as "The author acknowledges this and emphasises that…".
- Across the manuscript, recurring phrases were tightened: "is being dealt with in this paper" → "is addressed in this thesis" (one instance, removed; the phrasing did not survive the rewrite); the over-used connector "which means that" was trimmed in most occurrences; long passive-voice chains in §2.1 and §3.7 were broken into shorter sentences where comprehension benefited.

The polish pass also normalised tense (past for completed experimental work, present for stable system-design statements) and notation (`m/s`, `mm/s$^2$`, `\(\pm 30^\circ\)`, etc.) for consistency.

---

## What was deliberately not changed

To avoid introducing new evaluator concerns, the revision deliberately did not:

- Renumber any chapter, section, table, figure, or equation.
- Renumber or remove any of the original 36 reference entries.
- Modify the original numerical anchors of the evaluation (95.17 mm ball mean, 143.38 mm joint mean, all per-joint figures, the linear correction model, the 36-trial / 81-trial table data).
- Modify the existing figures or claim new figures that have not been produced. Where new figures would strengthen the new sections (Kalman improvement plot, YOLO-Pose vs MMPose ablation plot, ball detection bounce-scenario plot, integrated-live-test photograph, voice-bridge block diagram), `% TODO` markers indicate the location and the source script or output directory from which the canonical figure can be exported.
- Claim moving-target closed-loop firing or any other regime that has not been demonstrated.

---

## Summary

The revised submission preserves every numerical claim and every contribution of the original thesis, addresses each of the three evaluator comments in full, and incorporates the substantive engineering work completed since the original submission (YOLO-Pose backend with TensorRT FP16, BLM firmware control_12 single-MCU 921 600 baud architecture, Kalman-prediction tuning, ball-detection robustness layer, multi-modal Vosk voice integration, integrated live test on three named joints on 2026-04-09). The closed-loop firing regime in which the human subject is in motion during the shot remains the final integration boundary and is honestly identified as future work in Chapter 6.

I am grateful for your guidance, and I look forward to discussing the work further at the defense.

Yours sincerely,

Arlen Smagulov
