"""
Generate a ChArUco board image for printing.

Board specs (very coarse for an ~150 cm x 85 cm display):
- Canvas: 150 cm x 85 cm.
- Square size: 21 cm (very large markers while fitting 85 cm height).
- Board grid: 6 squares wide x 4 squares tall (15 interior corners).
- ArUco dictionary: DICT_4X4_50.

Usage:
    python charuco_board.py
Outputs:
- charuco_board.png saved alongside this script.
"""

from pathlib import Path

import cv2
import numpy as np


def mm_to_pixels(mm: float, dpi: int) -> int:
    """Convert millimeters to pixels at the given DPI."""
    return int(round(mm / 25.4 * dpi))


def main() -> None:
    # Physical parameters (all lengths in millimeters)
    canvas_width_mm = 1500  # 150 cm (matches TV width)
    canvas_height_mm = 850  # 85 cm (matches TV height)
    square_length_mm = 210.0  # 21 cm squares
    marker_length_mm = square_length_mm * 0.7
    squares_x = 6
    squares_y = 4
    dpi = 300  # adjust if you need a different print resolution

    # Derived sizes
    board_width_mm = squares_x * square_length_mm
    board_height_mm = squares_y * square_length_mm
    board_width_px = mm_to_pixels(board_width_mm, dpi)
    board_height_px = mm_to_pixels(board_height_mm, dpi)
    canvas_width_px = mm_to_pixels(canvas_width_mm, dpi)
    canvas_height_px = mm_to_pixels(canvas_height_mm, dpi)

    # Create ChArUco board
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    # CharucoBoard places a marker on every other square (≈ half the squares).
    # The 4x4_50 dictionary only has 50 unique markers, so we tile IDs to cover
    # the full board without exceeding the dictionary size.
    marker_count = (squares_x * squares_y + 1) // 2
    dictionary_size = dictionary.bytesList.shape[0]
    tiled_ids = np.arange(marker_count, dtype=np.int32) % dictionary_size
    board = cv2.aruco.CharucoBoard(
        (squares_x, squares_y),
        squareLength=square_length_mm,
        markerLength=marker_length_mm,
        dictionary=dictionary,
        ids=tiled_ids.reshape(-1, 1),
    )

    # Render board at target resolution
    board_img = board.generateImage((board_width_px, board_height_px))

    # Create white canvas and center the board to reach the 100 x 70 cm size
    canvas = np.full((canvas_height_px, canvas_width_px), 255, dtype=np.uint8)
    offset_x = (canvas_width_px - board_width_px) // 2
    offset_y = (canvas_height_px - board_height_px) // 2
    canvas[offset_y : offset_y + board_height_px, offset_x : offset_x + board_width_px] = board_img

    output_path = Path(__file__).with_name("charuco_board.png")
    cv2.imwrite(str(output_path), canvas)
    print(f"Saved board to {output_path.resolve()}")
    print(
        f"Squares: {squares_x} x {squares_y} | Corners: {(squares_x - 1) * (squares_y - 1)} "
        f"| Square size: {square_length_mm/10:.2f} cm | Canvas: {canvas_width_mm/10:.1f} x {canvas_height_mm/10:.1f} cm"
    )


if __name__ == "__main__":
    main()
