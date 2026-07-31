import pytest
from PIL import Image
from docx import Document

from scripts.build_project_cam_technical_system_report import (
    ASSET_DIR,
    OUTPUT,
    SOURCE,
    generate_pose_geometry,
    inject_static_toc,
    referenced_figures,
    select_table_style,
    verify_figures,
)

FACT_CHECK = (
    SOURCE.parent
    / "project_cam_technical_system_report_fact_check_2026-07-29.md"
)


def test_select_table_style_falls_back_to_pandoc_default():
    assert select_table_style({"Table"}) == "Table"


def test_select_table_style_prefers_grid_when_available():
    assert select_table_style({"Table", "Table Grid"}) == "Table Grid"


def test_pose_geometry_warning_stays_inside_its_callout():
    generate_pose_geometry()
    image = Image.open(ASSET_DIR / "pose_geometry.png").convert("RGB")
    warning_pixels = [
        (x, y)
        for y in range(800, image.height)
        for x in range(image.width)
        if (lambda pixel: pixel[0] > 150 and pixel[0] > pixel[1] * 1.35)(image.getpixel((x, y)))
    ]

    assert warning_pixels
    assert min(x for x, _ in warning_pixels) >= 440
    assert max(x for x, _ in warning_pixels) <= 1160


def test_cover_date_ends_with_a_page_break_before_the_toc():
    document = Document(OUTPUT)
    date_paragraph = next(paragraph for paragraph in document.paragraphs if paragraph.style.name == "Date")

    assert date_paragraph._p.xpath('.//w:br[@w:type="page"]')
    assert "29 July 2026" in document.core_properties.subject


def test_static_toc_is_generated_from_top_level_headings():
    markdown = """---
title: Example
---

# First Section

## Child Section

# Second Section
"""

    prepared = inject_static_toc(markdown)

    assert "# Table of Contents {.unnumbered}" in prepared
    assert "1. [First Section](#first-section)" in prepared
    assert "2. [Second Section](#second-section)" in prepared
    assert "Child Section" not in prepared.split("# First Section", 1)[0]


def test_every_referenced_figure_resolves():
    """The shipped report must not link a figure that does not exist.

    Pandoc downgrades an unresolvable image to a warning and still exits 0, so
    `check=True` on the subprocess cannot catch it: the DOCX would go to an
    external reader with the figure silently absent while the build printed
    success. Diagram filenames are written twice — in generate_*() and in the
    Markdown link — so this guards the rename that touches only one of them.
    """
    figures = referenced_figures(SOURCE.read_text(encoding="utf-8"))
    assert figures, "report should reference at least one local figure"
    missing = [p for p in figures if not p.exists()]
    assert not missing, f"unresolvable figures: {missing}"


def test_missing_figure_is_a_build_failure():
    markdown = SOURCE.read_text(encoding="utf-8")
    ghost = markdown + "\n\n![ghost](../assets/project_cam_report/__absent__.png)\n"
    with pytest.raises(FileNotFoundError, match="do not exist"):
        verify_figures(ghost)


def test_report_does_not_claim_the_stabilizer_is_inactive():
    """The bone-length clamp ships default-ON (--pose-bone-consistency), so the
    report must not tell a reader the viz stabilizer is unused — that sends
    anyone debugging a render-vs-state difference to the wrong layer."""
    text = SOURCE.read_text(encoding="utf-8")
    assert "not integrated into the active runtime" not in text
    assert "display-only by construction" in text


def test_report_describes_the_per_pair_lr_verdict():
    """A summed whole-chain L/R vote was withdrawn as a state-corrupting
    regression; the report must not still present it as the design."""
    text = SOURCE.read_text(encoding="utf-8")
    assert "whole paired chain is kept or swapped" not in text
    assert "swap, keep, or ambiguous" in text


def test_report_records_the_completed_29_july_verification():
    text = SOURCE.read_text(encoding="utf-8")
    assert 'date: "Evidence snapshot: 29 July 2026"' in text
    assert "Run interrupted/inconclusive" not in text
    assert "full suite remains explicitly inconclusive" not in text
    assert "`682` tests passed across `60` files" in text
    assert "`245` tests passed across `11` files" in text


def test_fact_check_ledger_resolves_every_material_claim():
    text = FACT_CHECK.read_text(encoding="utf-8")
    required_sections = (
        "## Repository and Runtime Claims",
        "## Quantitative Evidence",
        "## Safety and Maturity Claims",
        "## External Licensing Claims",
    )
    for heading in required_sections:
        assert heading in text
    assert "| unresolved |" not in text.lower()
    assert (
        "garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/"
        in text
    )
    assert "configs/calibration/usb6_manifest.yaml" in text
