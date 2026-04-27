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

# ---------- Slide 2: motivation — add inline references ----------

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
    header = find_shape_by_name(slide, "t111")
    if shape_text(header).strip() == "Closed-loop":
        raise AssertionError("S4 column header still 'Closed-loop'")

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

# ---------- Registries (extended by later tasks) ----------

APPLY_FUNCTIONS = [apply_s1, apply_s2, apply_s3, apply_s4, apply_s5]
CHECK_FUNCTIONS = [check_s1, check_s2, check_s3, check_s4, check_s5]
