"""Unicode-capable text drawing for cv2 overlays.

OpenCV's Hershey fonts are ASCII-only: ``cv2.putText`` renders one ``?`` per
non-ASCII UTF-8 *byte*, so a Cyrillic athlete name like "Арлен" (5 letters,
10 bytes) shows up as ``??????????``.  These helpers keep the exact
``cv2.putText`` fast path for pure-ASCII strings and rasterize anything else
with PIL + DejaVuSans (full Cyrillic/Latin-ext/Greek coverage), cached per
(text, size, weight) so the per-frame cost is one small alpha blend.

If PIL or a usable font is missing, names are transliterated to ASCII
("Арлен" → "Arlen") instead of degrading to question marks.

Display-only: nothing here touches geometry, filters, or UDP.
"""

from __future__ import annotations

import functools
import unicodedata

import cv2
import numpy as np

# Rendered-name pills use a handful of distinct strings per session; a small
# cache holds every (text, size, weight) raster after its first frame.
_PATCH_CACHE_SIZE = 256

# cv2 HERSHEY_SIMPLEX cap height is ~22 px at font_scale 1.0; DejaVuSans cap
# height is ~0.73 em, so 30 px/em keeps mixed ASCII/Unicode rows visually even.
_EM_PER_CV2_SCALE = 30.0

_FONT_FILES = {
    False: (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ),
    True: (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    ),
}

# GOST-style romanization, Russian + Kazakh Cyrillic. Fallback only — the
# normal path draws the real glyphs.
_CYRILLIC_TO_LATIN = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
    "Ж": "Zh", "З": "Z", "И": "I", "Й": "Y", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "Kh", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Shch",
    "Ъ": "", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "Yu", "Я": "Ya",
    "Ә": "A", "Ғ": "G", "Қ": "Q", "Ң": "N", "Ө": "O", "Ұ": "U", "Ү": "U",
    "Һ": "H", "І": "I",
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ә": "a", "ғ": "g", "қ": "q", "ң": "n", "ө": "o", "ұ": "u", "ү": "u",
    "һ": "h", "і": "i",
}


def ascii_safe(text) -> str:
    """Best-effort ASCII rendition of a display name ("Арлен" → "Arlen")."""
    out = []
    for char in str(text):
        if ord(char) < 128:
            out.append(char)
            continue
        mapped = _CYRILLIC_TO_LATIN.get(char)
        if mapped is None:
            mapped = (
                unicodedata.normalize("NFKD", char)
                .encode("ascii", "ignore")
                .decode("ascii")
            ) or "?"
        out.append(mapped)
    return "".join(out)


def _font_px(font_scale: float) -> int:
    return max(11, int(round(_EM_PER_CV2_SCALE * float(font_scale))))


@functools.lru_cache(maxsize=8)
def _load_font(px: int, bold: bool):
    """A PIL FreeType font at `px` em size, or None if PIL/fonts are missing."""
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    candidates = list(_FONT_FILES[bold])
    try:  # matplotlib ships DejaVu — always present in this project's venv
        import matplotlib
        from pathlib import Path

        bundled = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
        candidates.append(
            str(bundled / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"))
        )
    except ImportError:
        pass
    for path in candidates:
        try:
            return ImageFont.truetype(path, px)
        except OSError:
            continue
    return None


@functools.lru_cache(maxsize=_PATCH_CACHE_SIZE)
def _render_patch(text: str, px: int, bold: bool):
    """Rasterize `text` once → (alpha float32 HxW in [0,1], baseline row, left offset).

    Returns None when no Unicode-capable font is available.
    """
    font = _load_font(px, bold)
    if font is None:
        return None
    from PIL import Image, ImageDraw

    ascent, _descent = font.getmetrics()
    x0, y0, x1, y1 = font.getbbox(text)
    width = max(1, int(x1 - x0))
    height = max(1, int(y1 - y0))
    margin = 1
    canvas = Image.new("L", (width + 2 * margin, height + 2 * margin), 0)
    ImageDraw.Draw(canvas).text(
        (margin - x0, margin - y0), text, font=font, fill=255
    )
    alpha = np.asarray(canvas, dtype=np.float32) / 255.0
    baseline_row = int(ascent - y0) + margin  # patch row aligned with org[1]
    left_offset = int(x0) - margin  # shift so glyph ink starts at org[0]
    return alpha, baseline_row, left_offset


def text_size(text, font_scale: float, thickness: int = 1):
    """``cv2.getTextSize``-compatible ``((width, height), baseline)`` for any string."""
    text = str(text)
    if text.isascii():
        return cv2.getTextSize(
            text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
        )
    patch = _render_patch(text, _font_px(font_scale), thickness >= 2)
    if patch is None:
        return cv2.getTextSize(
            ascii_safe(text), cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
        )
    alpha, baseline_row, _left = patch
    height, width = alpha.shape
    above = max(1, baseline_row)
    below = max(0, height - baseline_row)
    return (int(width), int(above)), int(below)


def put_text(img, text, org, font_scale: float, color, thickness: int = 1) -> None:
    """Draw `text` at baseline-left `org` like ``cv2.putText`` (HERSHEY_SIMPLEX,
    LINE_AA), but with real glyphs for non-ASCII strings."""
    text = str(text)
    if not text:
        return
    if text.isascii():
        cv2.putText(
            img, text, org, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color,
            thickness, cv2.LINE_AA,
        )
        return
    patch = (
        _render_patch(text, _font_px(font_scale), thickness >= 2)
        if getattr(img, "ndim", 0) == 3
        else None
    )
    if patch is None:
        cv2.putText(
            img, ascii_safe(text), org, cv2.FONT_HERSHEY_SIMPLEX, font_scale,
            color, thickness, cv2.LINE_AA,
        )
        return
    alpha, baseline_row, left_offset = patch
    patch_h, patch_w = alpha.shape
    img_h, img_w = img.shape[:2]
    x = int(org[0]) + left_offset
    y = int(org[1]) - baseline_row
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(img_w, x + patch_w), min(img_h, y + patch_h)
    if x0 >= x1 or y0 >= y1:
        return
    region_alpha = alpha[y0 - y:y1 - y, x0 - x:x1 - x][..., None]
    roi = img[y0:y1, x0:x1].astype(np.float32)
    tint = np.asarray(color, dtype=np.float32).reshape(1, 1, -1)[..., : roi.shape[2]]
    img[y0:y1, x0:x1] = (
        roi * (1.0 - region_alpha) + tint * region_alpha
    ).astype(img.dtype)
