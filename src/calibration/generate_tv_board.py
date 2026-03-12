
import cv2
import cv2.aruco as aruco
import numpy as np

def generate_board():
    # Resolution (4K essentially, to look sharp on any screen)
    width = 3840
    height = 2160
    
    # Board Params (Same as before to keep logic consistent)
    # Using fewer squares (5x7) allows them to be LARGER on screen
    SQUARES_X = 5
    SQUARES_Y = 7
    
    # In pixels for generation
    square_len_px = 300 
    marker_len_px = 220 
    
    # Margins
    margins = 50
    
    print(f"Generating {SQUARES_X}x{SQUARES_Y} board...")
    
    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    try:
        board = aruco.CharucoBoard((SQUARES_X, SQUARES_Y), square_len_px, marker_len_px, aruco_dict)
    except AttributeError:
         board = aruco.CharucoBoard_create(SQUARES_X, SQUARES_Y, square_len_px, marker_len_px, aruco_dict)

    # Calculate size in pixels
    # OpenCV's draw function needs approximate size
    img_size = (width, height)
    board_img = board.generateImage(img_size, marginSize=margins, borderBits=1)
    
    filename = "tv_charuco_5x7.png"
    cv2.imwrite(filename, board_img)
    print(f"[SUCCESS] Saved {filename}")
    print("---------------------------------------------------")
    print("INSTRUCTIONS:")
    print("1. Open this image on your TV.")
    print("2. Set to Full Screen (100% zoom, no stretch).")
    print("3. Use a RULER to measure the black square side length in millimeters.")
    print("4. Update 'SQUARE_LENGTH' in capture_charuco_auto.py with this value.")
    print("---------------------------------------------------")

if __name__ == "__main__":
    generate_board()
