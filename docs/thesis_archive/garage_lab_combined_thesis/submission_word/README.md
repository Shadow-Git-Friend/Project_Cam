# Word Submission Package

## Files
- `figures/`: selected thesis figures ready to insert
- `THESIS_WORD_MASTER_75_85.md`: full chapter-by-chapter thesis text master file
- `WORD_FORMATTING_AND_NUMBERING_GUIDE.md`: NU handbook-compliant formatting checklist
- `WORD_REFERENCE_STYLE_ASME.md`: ASME in-text and bibliography style template

## Usage
1. Use `THESIS_WORD_MASTER_75_85.md` as source text in Word.
2. Apply formatting from `WORD_FORMATTING_AND_NUMBERING_GUIDE.md`.
3. Apply reference style from `WORD_REFERENCE_STYLE_ASME.md`.
4. Insert figures from `figures/` at matching chapter positions and update cross-references before final submission.

## Generated DOCX
- `THESIS_WORD_MASTER_75_85.docx` was generated from the markdown master and includes embedded figures.
- Rebuild command:
```bash
cd /home/hanush/Desktop/Project_Cam
./venv/bin/python garage_lab_combined/thesis/submission_word/build_docx_from_markdown.py
```
