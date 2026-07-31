"""Unicode overlay text: real glyphs for non-ASCII athlete names, cv2 parity for ASCII."""

from __future__ import annotations

import cv2
import numpy as np

from project_cam.viz.text import ascii_safe, put_text, text_size


def blank(width=280, height=64):
    return np.zeros((height, width, 3), dtype=np.uint8)


def test_ascii_path_is_bit_exact_with_cv2():
    ours, reference = blank(), blank()
    put_text(ours, "Arlen", (10, 42), 0.52, (240, 240, 240), 1)
    cv2.putText(
        reference, "Arlen", (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.52,
        (240, 240, 240), 1, cv2.LINE_AA,
    )
    assert np.array_equal(ours, reference)


def test_cyrillic_name_draws_glyphs_not_question_marks():
    img = blank()
    put_text(img, "Арлен", (10, 42), 0.52, (255, 255, 255), 1)
    assert int((img > 0).sum()) > 0, "no ink drawn for Cyrillic name"

    question_marks = blank()
    # The old failure mode: one '?' per UTF-8 byte of "Арлен".
    cv2.putText(
        question_marks, "?" * len("Арлен".encode("utf-8")), (10, 42),
        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA,
    )
    assert not np.array_equal(img, question_marks)


def test_cyrillic_metrics_are_comparable_to_ascii():
    (width_u, height_u), baseline_u = text_size("Арлен", 0.52, 1)
    (width_a, height_a), _ = text_size("Arlen", 0.52, 1)
    assert width_u > 0 and height_u > 0 and baseline_u >= 0
    # The identity pill sizes itself from these metrics — keep them in the
    # same visual family as the ASCII font so mixed rosters line up.
    assert 0.5 * width_a <= width_u <= 3.0 * width_a
    assert 0.5 * height_a <= height_u <= 2.5 * height_a


def test_clipped_and_offscreen_draws_are_safe():
    img = blank(width=80, height=40)
    put_text(img, "Арлен", (-30, 12), 0.52, (255, 255, 255), 1)  # left clip
    put_text(img, "Арлен", (70, 39), 0.52, (255, 255, 255), 1)   # right/bottom clip
    put_text(img, "Арлен", (10, -5), 0.6, (255, 255, 255), 2)    # above frame, bold
    put_text(img, "Арлен", (500, 500), 0.52, (255, 255, 255), 1)  # fully off
    # reaching here without an exception is the contract; ink stays in-bounds
    assert img.shape == (40, 80, 3)


def test_color_is_applied_in_bgr_order():
    img = blank()
    put_text(img, "Ә", (12, 44), 0.9, (0, 0, 255), 2)  # red in BGR
    ys, xs = np.nonzero(img[:, :, 2])
    assert ys.size > 0
    assert int(img[:, :, 0].max()) == 0 and int(img[:, :, 1].max()) == 0


def test_repeat_draws_hit_the_patch_cache():
    from project_cam.viz.text import _render_patch

    _render_patch.cache_clear()
    img = blank()
    for _ in range(5):
        put_text(img, "Арлен", (10, 42), 0.52, (255, 255, 255), 1)
    info = _render_patch.cache_info()
    assert info.misses == 1 and info.hits >= 4


def test_ascii_safe_transliterates_instead_of_question_marks():
    assert ascii_safe("Арлен") == "Arlen"
    assert ascii_safe("Zoë") == "Zoe"
    assert ascii_safe("Арлен 2") == "Arlen 2"
    assert ascii_safe("Қайрат") == "Qayrat"
