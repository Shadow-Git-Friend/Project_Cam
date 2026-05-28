# Defense Deck Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply slide-level corrections to `thesis_defense_presentation/thesis_defense_final.pptx` per the design spec at `docs/superpowers/specs/2026-04-27-defense-deck-revision-design.md`, producing `thesis_defense_final_revised.pptx` with the NU brown master, NU/SEDS logos, and template untouched.

**Architecture:** A single mutator script `scripts/defense_deck/revise_defense_deck.py` opens the original, applies idempotent per-slide edits, writes a new file, then runs assertion checks on that file and exits non-zero on any failure. Each task adds one logical block of slide edits + corresponding assertions. Re-running the script always produces the same output.

**Tech Stack:** Python 3 (`./venv/bin/python`), `python-pptx` (already installed in `venv/`), `lxml` (transitive), `libreoffice` headless for the final PDF render.

**Spec source of truth:** `docs/superpowers/specs/2026-04-27-defense-deck-revision-design.md`. The "Source-of-truth numbers" table in §5 of that spec is authoritative; thesis values win wherever GLM/Gemini reviews disagree.

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `scripts/defense_deck/__init__.py` | Create | Package marker (empty) |
| `scripts/defense_deck/helpers.py` | Create | Shape lookup, text-frame replacement preserving runs/format, table cell helpers |
| `scripts/defense_deck/revise_defense_deck.py` | Create | Top-level: orchestrates per-slide `apply_*` and `check_*` functions; `__main__` runs revise + check |
| `scripts/defense_deck/slide_edits.py` | Create | One `apply_sN(prs)` and one `check_sN(prs)` function per touched slide, growing per task |
| `thesis_defense_presentation/thesis_defense_final_revised.pptx` | Create (output) | The revised deck. Original is never opened in write mode. |
| `thesis_defense_presentation/thesis_defense_final_revised.pdf` | Create (verification) | Headless LibreOffice render of the revised deck for visual eyeball |

The original `thesis_defense_presentation/thesis_defense_final.pptx` is read-only input throughout.

---

## Helpers contract (used by every task)

These are defined once in Task 1 and called by every subsequent task. **Do not redefine them** — import from `scripts.defense_deck.helpers`:

```python
# scripts/defense_deck/helpers.py
from typing import Optional
from pptx.slide import Slide
from pptx.shapes.base import BaseShape
from pptx.shapes.graphfrm import GraphicFrame
from pptx.util import Pt

def find_shape_by_name(slide: Slide, name: str) -> BaseShape:
    """Return first shape on slide whose .name matches exactly. Raises KeyError if none."""
    for sh in slide.shapes:
        if sh.name == name:
            return sh
    raise KeyError(f"shape {name!r} not on slide {slide.slide_id}; have: {[s.name for s in slide.shapes]}")

def find_shape_containing(slide: Slide, substring: str) -> BaseShape:
    """Return first shape with text_frame whose text contains substring. Raises KeyError."""
    for sh in slide.shapes:
        if sh.has_text_frame and substring in sh.text_frame.text:
            return sh
    raise KeyError(f"no shape on slide {slide.slide_id} contains {substring!r}")

def shape_text(sh: BaseShape) -> str:
    return sh.text_frame.text if sh.has_text_frame else ""

def replace_run_text(sh: BaseShape, search: str, replace: str) -> int:
    """Replace `search` with `replace` inside any single run of any paragraph of sh.
    Preserves run formatting. Returns count of replacements made.
    Idempotent: re-running with same args after a successful replace returns 0."""
    if not sh.has_text_frame:
        return 0
    n = 0
    for para in sh.text_frame.paragraphs:
        for run in para.runs:
            if search in run.text:
                run.text = run.text.replace(search, replace)
                n += 1
    return n

def set_paragraphs(sh: BaseShape, lines: list[str]) -> None:
    """Replace text frame body with `lines` (one paragraph per line). Preserves
    the first paragraph's run-zero formatting and applies it to all new lines.
    Use only when the existing paragraph structure can be discarded."""
    if not sh.has_text_frame:
        raise ValueError(f"shape {sh.name} has no text frame")
    tf = sh.text_frame
    template_para = tf.paragraphs[0]
    template_run = template_para.runs[0] if template_para.runs else None
    template_font = template_run.font if template_run else None
    # Clear all but the first paragraph; clear first paragraph's runs.
    for p in list(tf.paragraphs[1:]):
        p._p.getparent().remove(p._p)
    first = tf.paragraphs[0]
    for r in list(first.runs):
        r._r.getparent().remove(r._r)
    # Write lines.
    first.text = lines[0]
    if template_font is not None and first.runs:
        _copy_font(template_font, first.runs[0].font)
    for line in lines[1:]:
        p = tf.add_paragraph()
        p.text = line
        if template_font is not None and p.runs:
            _copy_font(template_font, p.runs[0].font)

def _copy_font(src, dst) -> None:
    if src.size is not None:
        dst.size = src.size
    if src.bold is not None:
        dst.bold = src.bold
    if src.italic is not None:
        dst.italic = src.italic
    if src.name is not None:
        dst.name = src.name
    try:
        if src.color and src.color.rgb is not None:
            dst.color.rgb = src.color.rgb
    except Exception:
        pass

def get_table(sh: BaseShape):
    if not sh.has_table:
        raise ValueError(f"shape {sh.name} has no table")
    return sh.table

def set_cell_text(cell, new_text: str) -> None:
    """Replace a table cell's text while keeping its first run's formatting."""
    tf = cell.text_frame
    template_run = tf.paragraphs[0].runs[0] if tf.paragraphs[0].runs else None
    template_font = template_run.font if template_run else None
    for p in list(tf.paragraphs[1:]):
        p._p.getparent().remove(p._p)
    first = tf.paragraphs[0]
    for r in list(first.runs):
        r._r.getparent().remove(r._r)
    first.text = new_text
    if template_font is not None and first.runs:
        _copy_font(template_font, first.runs[0].font)

def find_table_on_slide(slide: Slide):
    """Return first GraphicFrame containing a table on the slide. Raises KeyError."""
    for sh in slide.shapes:
        if sh.has_table:
            return sh.table
    raise KeyError(f"no table on slide {slide.slide_id}")

def assert_slide_text_contains(slide: Slide, needle: str) -> None:
    haystack = "\n".join(shape_text(sh) for sh in slide.shapes)
    if needle not in haystack:
        raise AssertionError(f"slide {slide.slide_id} missing {needle!r}; have:\n{haystack[:1200]}")

def assert_slide_text_not_contains(slide: Slide, needle: str) -> None:
    haystack = "\n".join(shape_text(sh) for sh in slide.shapes)
    if needle in haystack:
        raise AssertionError(f"slide {slide.slide_id} still contains banned {needle!r}")
```

---

## Task 1: Project scaffold, helpers, baseline, S1 footer fix

**Files:**
- Create: `scripts/defense_deck/__init__.py`
- Create: `scripts/defense_deck/helpers.py`
- Create: `scripts/defense_deck/revise_defense_deck.py`
- Create: `scripts/defense_deck/slide_edits.py`

- [ ] **Step 1: Create empty package marker**

```bash
mkdir -p scripts/defense_deck
: > scripts/defense_deck/__init__.py
```

- [ ] **Step 2: Write `helpers.py`** — paste the entire `helpers.py` block from the "Helpers contract" section above into `scripts/defense_deck/helpers.py`.

- [ ] **Step 3: Write the orchestrator `revise_defense_deck.py`**

```python
# scripts/defense_deck/revise_defense_deck.py
"""Idempotent revision of thesis_defense_final.pptx -> thesis_defense_final_revised.pptx.

Run from repo root:
    ./venv/bin/python -m scripts.defense_deck.revise_defense_deck
"""
from __future__ import annotations
import shutil
import sys
from pathlib import Path

from pptx import Presentation

from scripts.defense_deck import slide_edits

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "thesis_defense_presentation" / "thesis_defense_final.pptx"
DST = REPO / "thesis_defense_presentation" / "thesis_defense_final_revised.pptx"

# Banned strings + slide indices where they may legitimately appear (0-based).
# Note: S4 says "Live-aim closed loop" without a hyphen, so it does not match
# "closed-loop" and does not need to be allow-listed. The legitimate appearances
# of the hyphenated form are S13 (limitation describing the unvalidated boundary)
# and S22 (untouched Q&A backup quoting the future-work plan).
BANNED = {
    "[PLACEHOLDER_": (),  # never anywhere
    "closed-loop": (12, 21),
}

REQUIRED_STRINGS = [
    "150.77",
    "166.51",
    "198.73",
    "USD 358",
    "USD 120",
    "Dual-use",
    "in-sample",
    "ISO 13849-1",
    "NC E-STOP",
    "2-8 px",
    "3-7 px",
    "Arlen Smagulov",
]

def revise() -> None:
    if not SRC.exists():
        print(f"FATAL: source missing: {SRC}", file=sys.stderr)
        sys.exit(2)
    shutil.copyfile(SRC, DST)
    prs = Presentation(str(DST))
    for fn in slide_edits.APPLY_FUNCTIONS:
        fn(prs)
    prs.save(str(DST))
    print(f"WROTE  {DST}")

def check() -> None:
    prs = Presentation(str(DST))
    failures: list[str] = []
    for fn in slide_edits.CHECK_FUNCTIONS:
        try:
            fn(prs)
        except AssertionError as e:
            failures.append(f"{fn.__name__}: {e}")
    # Banned strings.
    for needle, allow_idx in BANNED.items():
        for i, slide in enumerate(prs.slides):
            haystack = "\n".join(
                sh.text_frame.text for sh in slide.shapes if sh.has_text_frame
            )
            if needle in haystack and i not in allow_idx:
                failures.append(f"slide {i+1} contains banned {needle!r}")
    # Required strings (anywhere in deck).
    full = "\n".join(
        sh.text_frame.text
        for slide in prs.slides
        for sh in slide.shapes
        if sh.has_text_frame
    )
    for s in REQUIRED_STRINGS:
        if s not in full:
            failures.append(f"deck missing required string {s!r}")
    if failures:
        print("CHECK FAIL:", file=sys.stderr)
        for f in failures:
            print("  -", f, file=sys.stderr)
        sys.exit(1)
    print(f"CHECK OK  ({len(prs.slides)} slides)")

def main() -> None:
    revise()
    check()

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write the initial `slide_edits.py` with S1 footer fix**

```python
# scripts/defense_deck/slide_edits.py
"""Per-slide apply/check functions. New tasks append to this file and
extend APPLY_FUNCTIONS / CHECK_FUNCTIONS at the bottom."""
from pptx.presentation import Presentation as _Prs

from scripts.defense_deck.helpers import (
    find_shape_by_name,
    find_shape_containing,
    replace_run_text,
    set_paragraphs,
    set_cell_text,
    find_table_on_slide,
    shape_text,
    assert_slide_text_contains,
    assert_slide_text_not_contains,
)

# ---------- Slide 1: title — footer name only ----------

def apply_s1(prs: _Prs) -> None:
    slide = prs.slides[0]
    footer = find_shape_by_name(slide, "FooterText")
    replace_run_text(footer, "Hanush", "Arlen Smagulov")

def check_s1(prs: _Prs) -> None:
    slide = prs.slides[0]
    footer = find_shape_by_name(slide, "FooterText")
    txt = shape_text(footer)
    if "Arlen Smagulov" not in txt:
        raise AssertionError(f"S1 footer not updated: {txt!r}")
    if "Hanush" in txt:
        raise AssertionError(f"S1 footer still contains 'Hanush': {txt!r}")

# ---------- Registries (extended by later tasks) ----------

APPLY_FUNCTIONS = [apply_s1]
CHECK_FUNCTIONS = [check_s1]
```

- [ ] **Step 5: Run the script — first end-to-end exercise**

```bash
cd /home/hanush/Desktop/Project_Cam
./venv/bin/python -m scripts.defense_deck.revise_defense_deck
```

Expected: prints `WROTE  …thesis_defense_final_revised.pptx` then `CHECK FAIL:` with the 12 missing required strings (because we have only done S1). Confirms scaffolding works and shows the gap.

- [ ] **Step 6: Adjust banned-string check to be temporarily lenient**

While building, the `REQUIRED_STRINGS` list will fail until later tasks land. **Comment out the `REQUIRED_STRINGS` loop in `check()` for now**, leaving a `# TODO uncomment in Task 12` marker. Re-run; expected: `CHECK OK  (22 slides)`.

```python
    # for s in REQUIRED_STRINGS:                       # TODO uncomment in Task 12
    #     if s not in full:                            # TODO uncomment in Task 12
    #         failures.append(...)                     # TODO uncomment in Task 12
```

- [ ] **Step 7: Commit**

```bash
git add scripts/defense_deck/ && git commit -m "$(cat <<'EOF'
Defense deck: scaffold revise script + S1 footer fix

Script lives at scripts/defense_deck/. Reads thesis_defense_final.pptx,
writes thesis_defense_final_revised.pptx, then asserts. S1 footer name
'Hanush' -> 'Arlen Smagulov' for consistency with title subtitle.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: S2 motivation citations + S3 problem takeaway

**Files:**
- Modify: `scripts/defense_deck/slide_edits.py`

**Source-of-truth strings:**
- S2 bullet block currently lives in shape `Rectangle 12` on slide index 1. Bullets are pipe-separated (` | `) inside one text frame.
- S3 takeaway currently in shape `t119` on slide index 2.

- [ ] **Step 1: Extend `slide_edits.py` with S2 + S3**

Append to `slide_edits.py` (above the registries):

```python
# ---------- Slide 2: motivation — add inline references ----------

S2_OLD_BULLETS = (
    "Fixed launchers cannot react |  | "
    "MoCap is costly and marker-based  |  | "
    "Training needs joint-specific delivery  |  | "
    "Low-cost cameras can bridge the gap |  | "
    "This thesis builds pose-guided aiming"
)
S2_NEW_LINES = [
    "Fixed launchers cannot react [Lobster Elite, Sec 1.1]",
    "MoCap is costly and marker-based [OptiTrack/Vicon, Sec 2.1]",
    "Training needs joint-specific delivery",
    "Low-cost cameras can bridge the gap",
    "This thesis builds pose-guided aiming",
]

def apply_s2(prs: _Prs) -> None:
    slide = prs.slides[1]
    block = find_shape_by_name(slide, "Rectangle 12")
    set_paragraphs(block, S2_NEW_LINES)

def check_s2(prs: _Prs) -> None:
    slide = prs.slides[1]
    assert_slide_text_contains(slide, "[Lobster Elite, Sec 1.1]")
    assert_slide_text_contains(slide, "[OptiTrack/Vicon, Sec 2.1]")

# ---------- Slide 3: problem & objectives — soften takeaway ----------

S3_NEW_TAKEAWAY = (
    "Takeaway: RQ1/RQ2 met within validated scope; RQ3/RQ4 satisfied "
    "for static + controlled live-aim only — moving-target firing is "
    "the unvalidated boundary (Sec 1.3, 6.4)."
)

def apply_s3(prs: _Prs) -> None:
    slide = prs.slides[2]
    takeaway = find_shape_by_name(slide, "t119")
    set_paragraphs(takeaway, [S3_NEW_TAKEAWAY])

def check_s3(prs: _Prs) -> None:
    slide = prs.slides[2]
    assert_slide_text_contains(slide, "moving-target firing is the unvalidated boundary")
    assert_slide_text_not_contains(slide, "all four objectives are met")
```

- [ ] **Step 2: Register**

Update the registry lists at the bottom of `slide_edits.py`:

```python
APPLY_FUNCTIONS = [apply_s1, apply_s2, apply_s3]
CHECK_FUNCTIONS = [check_s1, check_s2, check_s3]
```

- [ ] **Step 3: Run**

```bash
./venv/bin/python -m scripts.defense_deck.revise_defense_deck
```

Expected: `WROTE …` then `CHECK OK  (22 slides)`.

- [ ] **Step 4: Commit**

```bash
git add scripts/defense_deck/slide_edits.py && git commit -m "Defense deck: S2 citations + S3 soften takeaway

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: S4 background table — column rename + cell rewrite

**Files:**
- Modify: `scripts/defense_deck/slide_edits.py`

**Source-of-truth strings:**
- Slide 4 (index 3) has many free-floating text shapes that visually form a table. The "Closed-loop" column header lives in shape `t111`. The "This work" row's closed-loop cell is `t151` (currently `Static/live-aim validated`).

- [ ] **Step 1: Append S4 functions**

```python
# ---------- Slide 4: background table — rename header + rewrite cell ----------

def apply_s4(prs: _Prs) -> None:
    slide = prs.slides[3]
    header = find_shape_by_name(slide, "t111")
    set_paragraphs(header, ["Live-aim closed loop"])
    cell = find_shape_by_name(slide, "t151")
    set_paragraphs(cell, ["Aim + controlled single-shot validated"])

def check_s4(prs: _Prs) -> None:
    slide = prs.slides[3]
    assert_slide_text_contains(slide, "Live-aim closed loop")
    assert_slide_text_contains(slide, "Aim + controlled single-shot validated")
    # The original misleading label must be gone.
    header = find_shape_by_name(slide, "t111")
    if shape_text(header).strip() == "Closed-loop":
        raise AssertionError("S4 column header still 'Closed-loop'")
```

- [ ] **Step 2: Register**

```python
APPLY_FUNCTIONS = [apply_s1, apply_s2, apply_s3, apply_s4]
CHECK_FUNCTIONS = [check_s1, check_s2, check_s3, check_s4]
```

- [ ] **Step 3: Run**

```bash
./venv/bin/python -m scripts.defense_deck.revise_defense_deck
```

Expected: `CHECK OK  (22 slides)`.

- [ ] **Step 4: Commit**

```bash
git add scripts/defense_deck/slide_edits.py && git commit -m "Defense deck: S4 background table — drop misleading closed-loop label

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: S5 six contributions — drop closed-loop, add Sec refs

**Files:**
- Modify: `scripts/defense_deck/slide_edits.py`

- [ ] **Step 1: Append S5 functions**

```python
# ---------- Slide 5: six contributions ----------

S5_CARDS = {
    "card1": "01 | Pose-reactive aiming at low-cost | Markerless live-aim, commodity hardware (Sec 5.9)",
    "card2": "02 | Validated 4-camera 3D targeting pipeline | DLT/SVD, 95.17 mm corrected ball mean (Table 5.1)",
    "card3": "03 | High-speed YOLO-Pose launch loop | 6.2 ms/frame TRT FP16, 15 FPS live pipeline (Sec 5.6)",
    "card4": "04 | Six-stage safety validation architecture | S0-S4 passed 2026-04-09, E-STOP <100 ms (Sec 3.14.3)",
    "card5": "05 | Multi-modal voice command interface | Offline ASR + UDP inter-process channel (Sec 3.12)",
    "card6": "06 | Reproducible GT datasets & JSONL logs | 36-pt ball grid + 81-trial joint-touch protocol (Ch 4)",
}

def apply_s5(prs: _Prs) -> None:
    slide = prs.slides[4]
    for name, text in S5_CARDS.items():
        sh = find_shape_by_name(slide, name)
        set_paragraphs(sh, [text])

def check_s5(prs: _Prs) -> None:
    slide = prs.slides[4]
    card1 = find_shape_by_name(slide, "card1")
    if "closed-loop" in shape_text(card1).lower():
        raise AssertionError(f"S5 card1 still contains 'closed-loop': {shape_text(card1)!r}")
    assert_slide_text_contains(slide, "Markerless live-aim, commodity hardware")
    assert_slide_text_contains(slide, "Table 5.1")
    assert_slide_text_contains(slide, "Sec 3.14.3")
```

- [ ] **Step 2: Register and run**

```python
APPLY_FUNCTIONS = [apply_s1, apply_s2, apply_s3, apply_s4, apply_s5]
CHECK_FUNCTIONS = [check_s1, check_s2, check_s3, check_s4, check_s5]
```

```bash
./venv/bin/python -m scripts.defense_deck.revise_defense_deck
```

Expected: `CHECK OK  (22 slides)`.

- [ ] **Step 3: Commit**

```bash
git add scripts/defense_deck/slide_edits.py && git commit -m "Defense deck: S5 six contributions — drop closed-loop, add Sec refs

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: S8 hardware — cost honesty (~USD 358)

**Files:**
- Modify: `scripts/defense_deck/slide_edits.py`

**Source-of-truth strings:** Slide 8 (index 7) has `t101` (headline subtitle), `t127` (takeaway), and a table with `Item / Cost` rows. The table is the only `GraphicFrame` with `has_table = True` on the slide. There's no AprilTag bullet currently — we'll piggyback it onto `t104` (which already has a multi-line description).

- [ ] **Step 1: Append S8 functions**

```python
# ---------- Slide 8: hardware — cost honesty ----------

S8_HEADLINE = "Practical actuation paired with low-cost sensing — perception ≈USD 120, total ≈USD 358."
S8_TAKEAWAY = (
    "Takeaway: expensive MoCap is not required for pose-guided aiming; "
    "perception is ≈USD 120, with ≈USD 358 for the full BLM (Sec 3.2, Table 3.2)."
)
S8_AREA_TEXT_NEW = (
    "Arena setup: 4 USB cameras at corners, BLM at centre, "
    "24 AprilTag fiducials on walls for extrinsic calibration (Sec 3.5). "
    "All hardware fits in a domestic garage — no lab infrastructure required."
)

def apply_s8(prs: _Prs) -> None:
    slide = prs.slides[7]
    set_paragraphs(find_shape_by_name(slide, "t101"), [S8_HEADLINE])
    set_paragraphs(find_shape_by_name(slide, "t127"), [S8_TAKEAWAY])
    set_paragraphs(find_shape_by_name(slide, "t104"), [S8_AREA_TEXT_NEW])
    # Append a "Total" row to the cost table if not already there.
    table = find_table_on_slide(slide)
    last_row_label = table.cell(len(table.rows) - 1, 0).text.strip()
    if "Total" not in last_row_label:
        # Clone the last row by copying its XML element.
        from copy import deepcopy
        tbl = table._tbl
        last_tr = tbl.tr_lst[-1]
        new_tr = deepcopy(last_tr)
        tbl.append(new_tr)
        # Now update the new last row.
        new_idx = len(table.rows) - 1
        set_cell_text(table.cell(new_idx, 0), "Total")
        set_cell_text(table.cell(new_idx, 1), "≈USD 358")

def check_s8(prs: _Prs) -> None:
    slide = prs.slides[7]
    assert_slide_text_contains(slide, "≈USD 358")
    assert_slide_text_contains(slide, "≈USD 120")
    assert_slide_text_contains(slide, "AprilTag fiducials")
    table = find_table_on_slide(slide)
    last_label = table.cell(len(table.rows) - 1, 0).text.strip()
    if last_label != "Total":
        raise AssertionError(f"S8 cost table last row should be 'Total', got {last_label!r}")
```

- [ ] **Step 2: Register and run**

```python
APPLY_FUNCTIONS = [apply_s1, apply_s2, apply_s3, apply_s4, apply_s5, apply_s8]
CHECK_FUNCTIONS = [check_s1, check_s2, check_s3, check_s4, check_s5, check_s8]
```

```bash
./venv/bin/python -m scripts.defense_deck.revise_defense_deck
```

Expected: `CHECK OK  (22 slides)`. Re-run a second time and confirm the table still has exactly one `Total` row (idempotency).

- [ ] **Step 3: Commit**

```bash
git add scripts/defense_deck/slide_edits.py && git commit -m "Defense deck: S8 hardware — cost honesty (USD 358 total / 120 perception)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: S9 software de-clutter + create hidden A5 firmware appendix

**Files:**
- Modify: `scripts/defense_deck/slide_edits.py`

**Approach:** S9 currently has shapes `t135` (label "Firmware command excerpt") and `t136` (the code block). We blank both shapes' text on S9 and clone S19 (an existing appendix slide that already has the right master/layout) as the new hidden A5 slide carrying the excerpt. Cloning preserves the NU template chrome.

- [ ] **Step 1: Append S9 + new-slide creation**

```python
# ---------- Slide 9: software — de-clutter ----------

S9_NEW_TABLE_ROWS = [
    ("Robust ball", "iterative reprojection-error rejection (Sec 3.7.2)"),
    ("Filter", "adaptive EMA + CV Kalman (Sec 5.7)"),
]
S9_FIRMWARE_EXCERPT = (
    "// control_12_full.ino\n"
    "void handle_set(){\n"
    "  // set <v> <h> <wl> <wr>\n"
    "  float v  = Serial.parseFloat();\n"
    "  float h  = Serial.parseFloat();\n"
    "  int   wl = Serial.parseInt();\n"
    "  int   wr = Serial.parseInt();\n"
    "  if(!armed) return;\n"
    "  clampAngle(v, h);\n"
    "  gateRPM(wl, wr);\n"
    "  target_v = v; target_h = h;\n"
    "}"
)

def apply_s9(prs: _Prs) -> None:
    slide = prs.slides[8]
    # Blank the on-slide code excerpt and its label.
    set_paragraphs(find_shape_by_name(slide, "t135"), [""])
    set_paragraphs(find_shape_by_name(slide, "t136"), [""])
    # The slide-9 software stack table — add the two missing rows by appending.
    # Robust ball + Filter rows already exist as separate text shapes (t119/t121
    # and t123/t125 per the original deck dump), so update them in-place.
    set_paragraphs(find_shape_by_name(slide, "t121"),
                   ["iterative reprojection-error rejection (Sec 3.7.2)"])
    set_paragraphs(find_shape_by_name(slide, "t125"),
                   ["adaptive EMA + CV Kalman (Sec 5.7)"])

def check_s9(prs: _Prs) -> None:
    slide = prs.slides[8]
    excerpt = find_shape_by_name(slide, "t136")
    if "handle_set" in shape_text(excerpt):
        raise AssertionError("S9 still carries the firmware code excerpt")
    assert_slide_text_contains(slide, "iterative reprojection-error rejection (Sec 3.7.2)")
    assert_slide_text_contains(slide, "adaptive EMA + CV Kalman (Sec 5.7)")

# ---------- New hidden appendix slide A5: firmware excerpt ----------

def apply_a5(prs: _Prs) -> None:
    """Create a hidden appendix slide with the firmware excerpt by cloning S19.
    Idempotent: only appends if no slide already has Title 'A5 · Firmware command excerpt'."""
    for s in prs.slides:
        for sh in s.shapes:
            if sh.has_text_frame and "A5 · Firmware command excerpt" in sh.text_frame.text:
                return  # already present
    from copy import deepcopy
    src = prs.slides[18]  # S19, an appendix slide with full NU chrome
    # Use the same slide layout as the source so master/footer/logos copy through.
    new_slide = prs.slides.add_slide(src.slide_layout)
    # Wipe new_slide's default placeholders, then deep-copy each shape from src.
    for ph in list(new_slide.shapes):
        ph._element.getparent().remove(ph._element)
    for sh in src.shapes:
        new_el = deepcopy(sh._element)
        new_slide.shapes._spTree.append(new_el)
    # Now mutate text on the new slide.
    new_slide.shapes.title.text_frame.text = "A5 · Firmware command excerpt"
    # Replace the body / first text-only shape with the firmware code.
    body = None
    for sh in new_slide.shapes:
        if sh.has_text_frame and sh.shape_id != new_slide.shapes.title.shape_id \
                and sh.name not in ("BottomBar",) \
                and not sh.name.startswith("Rectangle") \
                and "APPENDIX" not in shape_text(sh) \
                and "Hidden slide" not in shape_text(sh) \
                and "SEDS" not in shape_text(sh):
            body = sh
            break
    if body is None:
        raise RuntimeError("could not locate body shape on cloned A5 slide")
    set_paragraphs(body, S9_FIRMWARE_EXCERPT.split("\n"))
    # Mark hidden.
    new_slide._element.set("show", "0")

def check_a5(prs: _Prs) -> None:
    found = None
    for i, s in enumerate(prs.slides):
        for sh in s.shapes:
            if sh.has_text_frame and "A5 · Firmware command excerpt" in sh.text_frame.text:
                found = (i, s)
                break
        if found:
            break
    if not found:
        raise AssertionError("A5 firmware appendix slide missing")
    i, s = found
    if s._element.get("show") == "1":
        raise AssertionError(f"A5 (slide {i+1}) should be hidden")
    assert_slide_text_contains(s, "handle_set")
    assert_slide_text_contains(s, "control_12_full.ino")
```

- [ ] **Step 2: Register and run**

```python
APPLY_FUNCTIONS = [apply_s1, apply_s2, apply_s3, apply_s4, apply_s5, apply_s8, apply_s9, apply_a5]
CHECK_FUNCTIONS = [check_s1, check_s2, check_s3, check_s4, check_s5, check_s8, check_s9, check_a5]
```

```bash
./venv/bin/python -m scripts.defense_deck.revise_defense_deck
```

Expected: `CHECK OK  (23 slides)` — the count grew because `apply_a5` added one slide.

- [ ] **Step 3: Run twice to verify idempotency**

```bash
./venv/bin/python -m scripts.defense_deck.revise_defense_deck && \
./venv/bin/python -m scripts.defense_deck.revise_defense_deck
```

Expected: both runs print `CHECK OK  (23 slides)` (not 24). If 24, the A5-existence guard in `apply_a5` is broken — fix before continuing.

- [ ] **Step 4: Commit**

```bash
git add scripts/defense_deck/slide_edits.py && git commit -m "Defense deck: S9 de-clutter + new hidden A5 firmware appendix

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: S10 calibration numbers + S11 methodology tightening

**Files:**
- Modify: `scripts/defense_deck/slide_edits.py`

**S10 approach:** the slide currently has just a subtitle (`t101`) and a takeaway (`t106`) plus a figure. Replace `t101` with a 4-line bullet block carrying the calibration numbers. The picture stays.

**S11 approach:** the slide is a wide table built from text shapes. The "Stability / 3D trajectory verified" cell is `t133`; the "Bias correction / Ball mean drops to 95.17 mm" cell is `t141`. Update both.

- [ ] **Step 1: Append S10 + S11 functions**

```python
# ---------- Slide 10: calibration — add numbers ----------

S10_BULLETS = [
    "Intrinsic: ChArUco board, reproj 2-8 px (Sec 5.1)",
    "Extrinsic: 24 AprilTags + RANSAC + σ=2.0 sigma-clipping (Sec 3.5.2)",
    "Extrinsic RMSE: 3-7 px after 8-15 % outlier rejection (Sec 5.2)",
    "Overlay validation: reprojected corners within 5-10 px on all 4 cams",
]

def apply_s10(prs: _Prs) -> None:
    slide = prs.slides[9]
    set_paragraphs(find_shape_by_name(slide, "t101"), S10_BULLETS)

def check_s10(prs: _Prs) -> None:
    slide = prs.slides[9]
    assert_slide_text_contains(slide, "2-8 px")
    assert_slide_text_contains(slide, "3-7 px")
    assert_slide_text_contains(slide, "5-10 px")

# ---------- Slide 11: methodology tightening ----------

S11_DYN_OUTCOME = ("<800 mm frame-to-frame jumps (slow), motion-blur stress (fast), "
                   "near-zero false-positive (no-ball)")
S11_BIAS_OUTCOME = "Raw 150.77 mm → corrected 95.17 mm (Fig 5.1)"
S11_NEW_TAKEAWAY = (
    "Takeaway: localisation, dynamic stability, and safety logging satisfy "
    "static + live-aim acceptance. Bias correction was fitted in-sample on "
    "the same 36-pt set (Sec 4.4.2, 6.3)."
)

def apply_s11(prs: _Prs) -> None:
    slide = prs.slides[10]
    set_paragraphs(find_shape_by_name(slide, "t133"), [S11_DYN_OUTCOME])
    set_paragraphs(find_shape_by_name(slide, "t141"), [S11_BIAS_OUTCOME])
    set_paragraphs(find_shape_by_name(slide, "t159"), [S11_NEW_TAKEAWAY])

def check_s11(prs: _Prs) -> None:
    slide = prs.slides[10]
    assert_slide_text_contains(slide, "150.77")
    assert_slide_text_contains(slide, "in-sample")
    assert_slide_text_not_contains(slide, "3D trajectory verified")
```

- [ ] **Step 2: Register and run**

```python
APPLY_FUNCTIONS = [apply_s1, apply_s2, apply_s3, apply_s4, apply_s5, apply_s8, apply_s9, apply_a5, apply_s10, apply_s11]
CHECK_FUNCTIONS = [check_s1, check_s2, check_s3, check_s4, check_s5, check_s8, check_s9, check_a5, check_s10, check_s11]
```

```bash
./venv/bin/python -m scripts.defense_deck.revise_defense_deck
```

Expected: `CHECK OK  (23 slides)`.

- [ ] **Step 3: Commit**

```bash
git add scripts/defense_deck/slide_edits.py && git commit -m "Defense deck: S10 calibration numbers + S11 methodology in-sample caveat

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 8: S12 key results — P95 row + raw/corrected callout

**Files:**
- Modify: `scripts/defense_deck/slide_edits.py`

**Approach:** S12 has 5 headline boxes. Modify each `caption` shape (the smaller text under each big number) to include P95 inline. Modify the slide subtitle (`t101`) to call out the raw→corrected drop.

- [ ] **Step 1: Append S12 functions**

```python
# ---------- Slide 12: key results — P95 + raw/corrected ----------

S12_SUBTITLE = (
    "All thresholds met within validated static/live-aim scope. "
    "Raw ball mean 150.77 mm → corrected 95.17 mm via in-sample bias model (Fig 5.1)."
)
S12_CAPTIONS = {
    "t105": "corrected ball mean (P95 166.51 mm)",
    "t107": "joint mean over 62 valid trials (P95 198.73 mm)",
    "t109": "knee / hip / shoulder means; P95 171 / 172 / 200 mm (Table 5.3)",
    "t111": "E-STOP latch response (Sec 3.14.3)",
    "t113": "live YOLO-Pose pipeline; ≈15 ms compute, 52 ms headroom (Sec 3.3)",
}

def apply_s12(prs: _Prs) -> None:
    slide = prs.slides[11]
    set_paragraphs(find_shape_by_name(slide, "t101"), [S12_SUBTITLE])
    for name, txt in S12_CAPTIONS.items():
        set_paragraphs(find_shape_by_name(slide, name), [txt])

def check_s12(prs: _Prs) -> None:
    slide = prs.slides[11]
    for needle in ["166.51", "198.73", "171 / 172 / 200", "150.77", "95.17"]:
        assert_slide_text_contains(slide, needle)
```

- [ ] **Step 2: Register and run**

```python
APPLY_FUNCTIONS = [apply_s1, apply_s2, apply_s3, apply_s4, apply_s5, apply_s8, apply_s9, apply_a5, apply_s10, apply_s11, apply_s12]
CHECK_FUNCTIONS = [check_s1, check_s2, check_s3, check_s4, check_s5, check_s8, check_s9, check_a5, check_s10, check_s11, check_s12]
```

```bash
./venv/bin/python -m scripts.defense_deck.revise_defense_deck
```

Expected: `CHECK OK  (23 slides)`.

- [ ] **Step 3: Commit**

```bash
git add scripts/defense_deck/slide_edits.py && git commit -m "Defense deck: S12 key results — add P95 numbers + raw/corrected callout

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 9: S13 limitations — expand 1 → 6 bullets

**Files:**
- Modify: `scripts/defense_deck/slide_edits.py`

**Approach:** S13 has subtitle `t101` ("Validated: … Pending: …") and takeaway `t106`. Replace `t101` with 6 pipe-separated bullets. Update `t106` for tone.

- [ ] **Step 1: Append S13 functions**

```python
# ---------- Slide 13: limitations — expand to 6 bullets ----------

S13_LIMIT_LINES = [
    "1. UNVALIDATED: closed-loop firing at a moving subject (Sec 1.3, 6.3)",
    "2. In-sample bias correction — fitted on same 36-pt set (Sec 4.4.2, 6.3)",
    "3. 19 / 81 joint-touch trials invalid (23.5 %) due to occlusion (Sec 5.4)",
    "4. RPM → velocity not empirically calibrated (Sec 5.9, 6.4.3)",
    "5. Single-person, single-arena, indoor-only evaluation (Sec 6.3)",
    "6. CV Kalman neutral on jump motion — IMM filter is future work (Sec 5.7)",
]
S13_NEW_TAKEAWAY = (
    "Takeaway: validated scope (perception → safety-gated single-shot live-aim) "
    "is a strong partial validation. The unvalidated boundary — moving-subject "
    "closed-loop firing — is precisely defined and is the next milestone."
)

def apply_s13(prs: _Prs) -> None:
    slide = prs.slides[12]
    set_paragraphs(find_shape_by_name(slide, "t101"), S13_LIMIT_LINES)
    set_paragraphs(find_shape_by_name(slide, "t106"), [S13_NEW_TAKEAWAY])

def check_s13(prs: _Prs) -> None:
    slide = prs.slides[12]
    assert_slide_text_contains(slide, "23.5 %")
    assert_slide_text_contains(slide, "RPM → velocity not empirically calibrated")
    assert_slide_text_contains(slide, "IMM filter is future work")
```

- [ ] **Step 2: Register and run**

```python
APPLY_FUNCTIONS = [apply_s1, apply_s2, apply_s3, apply_s4, apply_s5, apply_s8, apply_s9, apply_a5, apply_s10, apply_s11, apply_s12, apply_s13]
CHECK_FUNCTIONS = [check_s1, check_s2, check_s3, check_s4, check_s5, check_s8, check_s9, check_a5, check_s10, check_s11, check_s12, check_s13]
```

```bash
./venv/bin/python -m scripts.defense_deck.revise_defense_deck
```

Expected: `CHECK OK  (23 slides)`.

- [ ] **Step 3: Commit**

```bash
git add scripts/defense_deck/slide_edits.py && git commit -m "Defense deck: S13 limitations — expand to 6 bullets per thesis Sec 6.3

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 10: S14 conclusions + S15 future work / ethics + standards how

**Files:**
- Modify: `scripts/defense_deck/slide_edits.py`

**S14 approach:** there are four "card" labels (`TextBox 3, 4, 6, 7`) that need text changes; the takeaway adds a "Disadvantages" line.

**S15 approach:** the right-hand mini-table on S15 has standard rows. Rewrite each row's "what" cell to include the "how". The takeaway shape is `t119`; we rewrite it as the dual-use statement.

- [ ] **Step 1: Append S14 + S15 functions**

```python
# ---------- Slide 14: conclusions — disadvantages + cost honesty ----------

S14_CARD_TEXT = {
    "TextBox 3":  "BLM aims live from 3D joints (Sec 5.9)",
    "TextBox 4":  "4 USB cameras, ≈USD 120 perception / ≈USD 358 total",
    "TextBox 6":  "Safety-gated S0–S4 integration, E-STOP <100 ms (Sec 3.14.3)",
    "TextBox 7":  "Voice + keyboard control behind safety gates (Sec 3.12)",
}
S14_NEW_TAKEAWAY = (
    "Takeaway: strong partial validation of a low-cost, pose-guided BLM. "
    "Disadvantages: in-sample bias fit · 3-camera occlusion floor · "
    "RPM → velocity not yet calibrated."
)

def apply_s14(prs: _Prs) -> None:
    slide = prs.slides[13]
    for name, txt in S14_CARD_TEXT.items():
        set_paragraphs(find_shape_by_name(slide, name), [txt])
    set_paragraphs(find_shape_by_name(slide, "t121"), [S14_NEW_TAKEAWAY])

def check_s14(prs: _Prs) -> None:
    slide = prs.slides[13]
    assert_slide_text_contains(slide, "USD 358")
    assert_slide_text_contains(slide, "Disadvantages:")
    # closed-loop must NOT appear here (S14 isn't on the BANNED allow-list)
    assert_slide_text_not_contains(slide, "closed-loop")

# ---------- Slide 15: future work + ethics + standards how ----------

S15_DUAL_USE = (
    "Dual-use: a system capable of autonomously tracking human body parts "
    "and directing a projectile has obvious dual-use potential beyond sports "
    "training. Operator presence, hardware NC E-STOP, exclusion zone, and the "
    "six-stage protocol are the necessary safeguards (Sec 6.5)."
)
S15_STD_HOW = {
    "t107": "Machinery safety — L1–L10 hazard map (Sec 3.14)",
    "t110": "Safety-related control — NC E-STOP = ISO 13849-1 Cat-1 stop (L8)",
    "t113": "Wiring, fusing, E-STOP — 24V/50A fuse, single star-point ground (Sec 3.2)",
    "t116": "Operator-only zone during controlled fire (Sec 3.14.2)",
}

def apply_s15(prs: _Prs) -> None:
    slide = prs.slides[14]
    # Replace the takeaway with the dual-use statement (handbook-required).
    set_paragraphs(find_shape_by_name(slide, "t119"), [S15_DUAL_USE])
    for name, txt in S15_STD_HOW.items():
        set_paragraphs(find_shape_by_name(slide, name), [txt])

def check_s15(prs: _Prs) -> None:
    slide = prs.slides[14]
    assert_slide_text_contains(slide, "Dual-use")
    assert_slide_text_contains(slide, "ISO 13849-1 Cat-1")
    assert_slide_text_contains(slide, "NC E-STOP")
    assert_slide_text_contains(slide, "24V/50A fuse")
```

- [ ] **Step 2: Register and run**

```python
APPLY_FUNCTIONS = [apply_s1, apply_s2, apply_s3, apply_s4, apply_s5, apply_s8, apply_s9, apply_a5, apply_s10, apply_s11, apply_s12, apply_s13, apply_s14, apply_s15]
CHECK_FUNCTIONS = [check_s1, check_s2, check_s3, check_s4, check_s5, check_s8, check_s9, check_a5, check_s10, check_s11, check_s12, check_s13, check_s14, check_s15]
```

```bash
./venv/bin/python -m scripts.defense_deck.revise_defense_deck
```

Expected: `CHECK OK  (23 slides)`.

- [ ] **Step 3: Commit**

```bash
git add scripts/defense_deck/slide_edits.py && git commit -m "Defense deck: S14 disadvantages + S15 dual-use & standards-how

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 11: S16 video embed + S18 latency table from JSONL

**Files:**
- Modify: `scripts/defense_deck/slide_edits.py`

**S16 approach:** Use `python-pptx` `slide.shapes.add_movie(...)` with a poster image from a single ffmpeg-extracted thumbnail. If `add_movie` fails or the thumbnail extraction fails, fall back to writing the path into the existing placeholder text shape so a human can drag the file in via LibreOffice. The fallback is logged; the assertion check accepts either outcome but always demands the placeholder substring is gone.

**S18 approach:** Read `Parallel_working/output/perf_blm_20260409_133818.jsonl`, compute mean and P95 over the seven latency fields, and replace the placeholder shape on slide 17 (index 17) with a small text block formatted as a table (lines like `Stage          Mean ms   P95 ms`). We use a monospace text block instead of a real `add_table` for layout safety — adding a new GraphicFrame would risk overlapping existing chrome.

- [ ] **Step 1: Append S16 + S18 functions**

```python
# ---------- Slide 16: A1 live demo — embed video ----------

import os
import shutil as _shutil
import subprocess
from pathlib import Path as _Path

REPO_ROOT = _Path(__file__).resolve().parents[2]
DEMO_VIDEO = REPO_ROOT / "thesis_defense_presentation" / "IMG_1589 (online-video-cutter.com).mp4"
DEMO_POSTER = REPO_ROOT / "thesis_defense_presentation" / "_demo_poster.jpg"

def _ensure_poster() -> _Path | None:
    if DEMO_POSTER.exists():
        return DEMO_POSTER
    if not _shutil.which("ffmpeg"):
        return None
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(DEMO_VIDEO),
             "-vframes", "1", "-q:v", "3", str(DEMO_POSTER)],
            check=True, timeout=60,
        )
        return DEMO_POSTER
    except Exception:
        return None

def apply_s16(prs: _Prs) -> None:
    slide = prs.slides[15]
    placeholder = find_shape_by_name(slide, "t103")
    # Wipe the placeholder text always.
    set_paragraphs(placeholder, ["Demo clip: arena 3D tracking, 20-30 s."])
    # Avoid duplicating the embedded movie on re-runs.
    has_movie = any(getattr(sh, "shape_type", None) and "media" in str(sh.shape_type).lower()
                    for sh in slide.shapes)
    if has_movie or not DEMO_VIDEO.exists():
        return
    poster = _ensure_poster()
    try:
        from pptx.util import Inches
        slide.shapes.add_movie(
            str(DEMO_VIDEO),
            left=Inches(1.0), top=Inches(1.5),
            width=Inches(11.0), height=Inches(5.5),
            poster_frame_image=str(poster) if poster else None,
            mime_type="video/mp4",
        )
    except Exception as e:
        # Fall back: leave a visible note on the slide.
        set_paragraphs(placeholder,
                       [f"Demo clip: {DEMO_VIDEO.name} — drag in via LibreOffice ({e})"])

def check_s16(prs: _Prs) -> None:
    slide = prs.slides[15]
    assert_slide_text_not_contains(slide, "[PLACEHOLDER_VIDEO_1")

# ---------- Slide 18: A3 latency table ----------

import json
import statistics as _stats

PERF_JSONL = REPO_ROOT / "Parallel_working" / "output" / "perf_blm_20260409_133818.jsonl"

LATENCY_FIELDS = ["capture_ms", "ball_ms", "pose_ms", "triang_ms",
                  "udp_ms", "viz3d_ms", "total_ms", "end_to_end_ms"]

def _build_latency_lines() -> list[str]:
    rows = [json.loads(l) for l in open(PERF_JSONL) if l.strip()]
    out = [f"From {PERF_JSONL.name} ({len(rows)} frames)",
           "Stage          Mean ms   P95 ms"]
    for fld in LATENCY_FIELDS:
        vals = [r[fld] for r in rows if isinstance(r.get(fld), (int, float))]
        if not vals:
            continue
        mean = sum(vals) / len(vals)
        p95 = _stats.quantiles(sorted(vals), n=20)[18] if len(vals) >= 20 else max(vals)
        out.append(f"{fld:<14}{mean:>8.1f}{p95:>9.1f}")
    return out

def apply_s18(prs: _Prs) -> None:
    slide = prs.slides[17]
    placeholder = find_shape_by_name(slide, "t103")
    if not PERF_JSONL.exists():
        set_paragraphs(placeholder, [f"Latency log not on disk: {PERF_JSONL.name}"])
        return
    set_paragraphs(placeholder, _build_latency_lines())

def check_s18(prs: _Prs) -> None:
    slide = prs.slides[17]
    assert_slide_text_not_contains(slide, "[PLACEHOLDER_TABLE_1")
    assert_slide_text_contains(slide, "Mean ms")
```

- [ ] **Step 2: Register and run**

```python
APPLY_FUNCTIONS = [apply_s1, apply_s2, apply_s3, apply_s4, apply_s5, apply_s8, apply_s9, apply_a5, apply_s10, apply_s11, apply_s12, apply_s13, apply_s14, apply_s15, apply_s16, apply_s18]
CHECK_FUNCTIONS = [check_s1, check_s2, check_s3, check_s4, check_s5, check_s8, check_s9, check_a5, check_s10, check_s11, check_s12, check_s13, check_s14, check_s15, check_s16, check_s18]
```

```bash
./venv/bin/python -m scripts.defense_deck.revise_defense_deck
```

Expected: `CHECK OK  (23 slides)`. If `add_movie` raises, the fallback note is on slide 16 instead — that's still a pass for the assertion (which only forbids the literal placeholder).

- [ ] **Step 3: Commit**

```bash
git add scripts/defense_deck/slide_edits.py && git commit -m "Defense deck: S16 video embed + S18 latency table from perf JSONL

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 12: Re-enable strict required-string check, render PDF, final commit

**Files:**
- Modify: `scripts/defense_deck/revise_defense_deck.py`
- Create: `thesis_defense_presentation/thesis_defense_final_revised.pdf`

- [ ] **Step 1: Re-enable the `REQUIRED_STRINGS` loop**

In `revise_defense_deck.py`, uncomment the loop that was deferred in Task 1 Step 6:

```python
    for s in REQUIRED_STRINGS:
        if s not in full:
            failures.append(f"deck missing required string {s!r}")
```

- [ ] **Step 2: Run and observe**

```bash
./venv/bin/python -m scripts.defense_deck.revise_defense_deck
```

Expected: `CHECK OK  (23 slides)`. If any required string is reported missing, edit the relevant slide's `apply_*` function (the spec table in §5 of the design doc tells you which thesis section each value comes from) and re-run until clean.

- [ ] **Step 3: Render to PDF for visual eyeball**

```bash
cd /home/hanush/Desktop/Project_Cam/thesis_defense_presentation && \
libreoffice --headless --convert-to pdf thesis_defense_final_revised.pptx
```

Expected: `convert /home/hanush/.../thesis_defense_final_revised.pptx -> .../thesis_defense_final_revised.pdf using filter : impress_pdf_Export`. Confirm `thesis_defense_final_revised.pdf` exists in the same folder.

- [ ] **Step 4: Sanity-check the PDF non-empty and slide count matches**

```bash
./venv/bin/python -c "
from pptx import Presentation
import subprocess
prs = Presentation('thesis_defense_presentation/thesis_defense_final_revised.pptx')
print('pptx slides:', len(prs.slides))
out = subprocess.check_output(['pdfinfo', 'thesis_defense_presentation/thesis_defense_final_revised.pdf']).decode()
for line in out.splitlines():
    if line.startswith('Pages'):
        print(line)
"
```

Expected: `pptx slides: 23`, `Pages: 23` (or `Pages: 18` if hidden slides are excluded by the PDF export filter — both are valid; the visible-only count is 15 + N visible appendix; report whatever it says).

- [ ] **Step 5: Manual eyeball gate (you, not the agent)**

Open `thesis_defense_final_revised.pdf` in any viewer and confirm:
1. NU brown master + NU logo + SEDS logo unchanged on every slide
2. Slide 1 footer reads "Arlen Smagulov · MSc ECE · Nazarbayev University"
3. Slide 8 cost table ends with "Total | ≈USD 358"
4. Slide 12 shows "Raw 150.77 → corrected 95.17 mm" callout and P95 numbers
5. Slide 13 has 6 numbered limitations
6. Slide 15 has the full "Dual-use" sentence and ISO standards with implementation notes
7. The new appendix slide A5 carries the firmware excerpt and is hidden in slideshow mode

If any of those fail, fix the corresponding `apply_*` function and re-run from Task 12 Step 2.

- [ ] **Step 6: Commit the revised deck and PDF**

```bash
cd /home/hanush/Desktop/Project_Cam && \
git add thesis_defense_presentation/thesis_defense_final_revised.pptx \
        thesis_defense_presentation/thesis_defense_final_revised.pdf \
        thesis_defense_presentation/_demo_poster.jpg \
        scripts/defense_deck/revise_defense_deck.py && \
git commit -m "$(cat <<'EOF'
Defense deck: revised pptx + PDF render

Final output of scripts/defense_deck/revise_defense_deck.py.
Original thesis_defense_final.pptx is unchanged. Per design spec
docs/superpowers/specs/2026-04-27-defense-deck-revision-design.md.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review checklist (run by the executing agent before declaring complete)

1. `./venv/bin/python -m scripts.defense_deck.revise_defense_deck` exits 0 and prints `CHECK OK  (23 slides)`.
2. Running it twice in a row still prints `CHECK OK  (23 slides)` — slide count does not grow.
3. The original `thesis_defense_final.pptx` is byte-identical to its pre-task state:

```bash
git diff --stat HEAD~12 -- thesis_defense_presentation/thesis_defense_final.pptx
```

Expected: empty output (no diff).

4. `thesis_defense_final_revised.pdf` opens, has the expected slide count, and the NU template / logos look unchanged versus the original.
5. None of the slides contain the substring `[PLACEHOLDER_`.
6. The 12 required strings from `REQUIRED_STRINGS` all appear in the deck.
