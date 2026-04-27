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
