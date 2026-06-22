# LaTeX Submission Package (NU MSc ECE)

This package follows NU handbook Appendix III structure and formatting intent:
- Times New Roman 12 pt
- Double spacing
- 2.5 cm margins
- First-line indent 1.25 cm
- Chapter/section/subsection numbering
- Page number centered at top
- Required manuscript order

## Files
- `main.tex`: master thesis file
- `frontmatter/*`: title/declaration/abstract/acknowledgements/abbreviations
- `chapters/ch01.tex` ... `chapters/ch09.tex`: chapter content generated from the full draft
- `references/references_list.tex`: ASME numeric reference list text
- `references/references.bib`: starter BibTeX entries
- `appendices/*`: required order, formatting checklist, reproducibility artifacts
- `figures/*`: selected thesis figures ready for inclusion

## Build
Use XeLaTeX (required for Times New Roman via `fontspec`):

```bash
cd garage_lab_combined/thesis/submission_latex
xelatex main.tex
xelatex main.tex
```

If Times New Roman is not installed in your TeX environment, replace `\setmainfont{Times New Roman}` in `main.tex` with an available Times-compatible font.

## Figure placement
Use `garage_lab_combined/thesis/FIGURE_TABLE_INSERTION_PLAN_2026-03-11.md` for exact chapter-to-figure mapping.
Copy-paste figure environments from `FIGURE_INSERT_SNIPPETS.tex` into chapter files.
