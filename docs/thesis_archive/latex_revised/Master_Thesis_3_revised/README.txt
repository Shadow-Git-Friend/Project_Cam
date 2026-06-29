Master_Thesis_3_revised - LaTeX Project for Overleaf
=====================================================

This folder is the revised LaTeX source of the MSc thesis
"Pose Guided Predictive Ballistics for Body Part-Targeted
Football Training" by Arlen Smagulov (Nazarbayev University,
March 2026), incorporating the evaluator comments and the
post-submission engineering work.

It is structured to compile under Overleaf with no further
configuration; the same source also compiles with a local
XeLaTeX or LuaLaTeX install.

------------------------------------------------------------
1. Quick start: upload to Overleaf
------------------------------------------------------------

Two equally good ways:

(a) Direct folder upload.
    1.  Zip this folder:
        cd /home/hanush/Desktop/Project_Cam/latex_revised
        zip -r Master_Thesis_3_revised.zip Master_Thesis_3_revised
    2.  In Overleaf, click "New Project" -> "Upload Project"
        and select the .zip from step 1.
    3.  Overleaf will set the root document automatically.
        If it does not, set "Main document" to "main.tex" in
        the Overleaf "Menu" panel.

(b) Drag-and-drop into a fresh Overleaf project.
    1.  In Overleaf, "New Project" -> "Blank Project".
    2.  Delete the default main.tex.
    3.  Drag the entire contents of this folder into the
        Overleaf project file panel. Folder structure is
        preserved (frontmatter/, chapters/, backmatter/,
        figures/, references.bib, nuthesis.cls).
    4.  Set the main document to "main.tex".

Recommended Overleaf compiler: XeLaTeX (set in the project
"Menu" -> "Compiler"). The nuthesis.cls and the existing
fontspec setup require XeLaTeX or LuaLaTeX; PDFLaTeX will
not compile correctly because of the non-Latin font
fallbacks.

The first compile will take a few minutes (Overleaf
regenerates the .aux, .bbl, .toc, .lof, .lot artefacts from
scratch). Subsequent compiles are incremental.

------------------------------------------------------------
2. Local compile (optional)
------------------------------------------------------------

From the folder root:

    latexmk -xelatex -interaction=nonstopmode main.tex

Or, manually:

    xelatex main
    bibtex  main
    xelatex main
    xelatex main

The two repeated xelatex passes resolve cross-references
(\ref, \cite, table-of-contents) and the bibliography.

------------------------------------------------------------
3. What is in the folder
------------------------------------------------------------

main.tex                    Root document. Wires together
                            the frontmatter, chapters, the
                            bibliography, and the appendices.
nuthesis.cls                Nazarbayev University thesis class.
nu_logo.png                 NU logo for the cover page.
references.bib              48 BibTeX entries: 36 original
                            (ref1 - ref36) preserved verbatim
                            with no renumbering, plus 12 new
                            entries (ref37_yolopose ...
                            ref48_voice_hri) added for the
                            post-submission work.

frontmatter/
    declaration.tex
    abstract.tex            Rewritten with partial-validation
                            framing.
    acknowledgements.tex    Polished.
    abbreviations.tex       Extended from ~17 to ~33 entries.

chapters/
    chapter1.tex            Introduction. Rewritten: 4 RQs,
                            scope, 4 novelty claims with
                            scope qualifiers.
    chapter2.tex            Literature review. Rewritten with
                            critical comparison + design-
                            choice justification + new sub-
                            topics (YOLO-Pose, Kalman, voice
                            HRI).
    chapter3.tex            System design. Substantially
                            expanded: BLM firmware FSM,
                            Kalman, ball robustness, comm
                            stack, voice integration, layered
                            safety architecture.
    chapter4.tex            Ground-truth protocols. Original
                            sections preserved; new sections
                            for YOLO-Pose ablation, Kalman
                            tuning, ball-detection analyser,
                            BLM integration protocol.
    chapter5.tex            Results. Original sections
                            preserved verbatim with all
                            numerical anchors; new sections
                            for the post-submission results
                            and the integrated live test.
    chapter6.tex            Conclusions. 4 contributions,
                            updated Table 6.1, expanded
                            limitations, restructured future
                            work.

backmatter/
    appendix_a.tex          BLM integration checklist.
                            Status column added; S0-S4
                            marked Passed 2026-04-09.
    appendix_b.tex          Key script invocation listings.
                            Preserved verbatim.
    appendix_c.tex          Ground-truth grids (full data
                            tables). Preserved verbatim.
    appendix_d.tex          Calibration figures. Preserved.
    appendix_e.tex          YOLO ball training results.
                            Preserved.
    appendix_f.tex          Smoke-test frames. Preserved.
    appendix_g.tex          NEW. Full BLM firmware command
                            map (Table G.1) and voice grammar
                            reference (Table G.2).

figures/                    All original figures preserved
                            in place. Some new sections in
                            chapter5 carry "% TODO: insert
                            figure here" markers indicating
                            where additional figures would
                            strengthen the chapter and from
                            which output directory the
                            canonical image can be exported.

REVISION_NOTES.md           Per-section changelog and
                            evaluator-comment summary.
                            Internal reference for the
                            author; not part of the thesis
                            body.

EVALUATOR_RESPONSE.md       Point-by-point response letter
                            for submission alongside the
                            revised thesis. Plain Markdown;
                            convert to PDF or DOCX with
                            pandoc if a non-Markdown form is
                            required.

README.txt                  This file.

------------------------------------------------------------
4. Pending TODO figures (optional but recommended)
------------------------------------------------------------

Five new sections in chapter5 carry placeholder markers
indicating where new figures would strengthen the chapter.
Each marker includes the source directory or script from
which the canonical image can be exported. The thesis
compiles cleanly without these figures (they are LaTeX
comments, not \includegraphics calls), but adding them is
the recommended next step before defense.

The five figures are:

  Section 5.6 (YOLO-Pose vs MMPose ablation):
    Source:  Parallel_working/output/ablation_results/
    Format:  per-sequence bar chart of 3D jitter and
             per-camera detection-rate bars.

  Section 5.7 (Kalman prediction tuning):
    Source:  Parallel_working/output/prediction_results/
    Format:  line plot of percentage improvement vs
             prediction horizon for each motion class.

  Section 5.8 (Ball detection robustness):
    Source:  Parallel_working/output/test_sequences/bounce_*
    Format:  per-camera detection-rate bar charts at
             imgsz=672 vs 960, with confidence sweep.

  Section 5.9 (Integrated live test):
    Source:  Operational record from 2026-04-09.
    Format:  Still photograph of the launcher in mid-cycle
             with a triangulated skeleton overlay.

  Section 5.10 (Voice-bridge wiring):
    Source:  New diagram. Three-process schematic: ASR
             producer in separate venv -> UDP:5006 -> live
             runtime -> safety gates -> ESP32.

To insert any figure, locate the corresponding "% TODO:
insert ... here" comment in chapter5.tex and replace the
comment with the standard \begin{figure}...\end{figure}
block, with \includegraphics{figures/<filename>}.

------------------------------------------------------------
5. Validating the revised content
------------------------------------------------------------

A short verification check confirms that the revised LaTeX
preserves the original numerical anchors and reference
keys. From the repo root:

    diff <(grep -hroE '[0-9]+\.[0-9]+~?mm|[0-9]+\.[0-9]+ mm' \
              latex_old_version/Master_Thesis_3_/chapters/ \
              latex_old_version/Master_Thesis_3_/frontmatter/ \
            | sort -u) \
         <(grep -hroE '[0-9]+\.[0-9]+~?mm|[0-9]+\.[0-9]+ mm' \
              latex_revised/Master_Thesis_3_revised/chapters/ \
              latex_revised/Master_Thesis_3_revised/frontmatter/ \
            | sort -u)

The original anchors should appear in the revised set; the
revised set adds new figures from the post-submission work.

    grep -hroE '\\cite\{[^}]+\}' \
        latex_old_version/Master_Thesis_3_/ | sort -u \
        > /tmp/cite_old.txt
    grep -hroE '\\cite\{[^}]+\}' \
        latex_revised/Master_Thesis_3_revised/ | sort -u \
        > /tmp/cite_new.txt
    comm -23 /tmp/cite_old.txt /tmp/cite_new.txt

If the comm output is empty, every cite key from the
original is still cited in the revised version (no key was
silently dropped).

------------------------------------------------------------
6. Author and submission notes
------------------------------------------------------------

The folder is intended to be uploaded to Overleaf as-is and
to compile to a submission-ready PDF without any further
manual intervention. If the Overleaf compile reports an
error, the most likely cause is a missing font (xelatex
falls back to system fonts; the nuthesis.cls expects Times
New Roman). Overleaf provides Times New Roman by default;
local builds may need a small change to the \setmainfont
line of nuthesis.cls if the font is not installed.

Date: 2026-04-21
