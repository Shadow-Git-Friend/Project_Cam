import fitz  # PyMuPDF
import cv2
import numpy as np
import os

PDF_PATH = "/home/altay/Desktop/Footbonaut/Garage/apriltags_A3_24pages.pdf"  # change if needed
OUT_DIR = "/home/altay/Desktop/Footbonaut/Garage/tag_corner_debug"
os.makedirs(OUT_DIR, exist_ok=True)

# AprilTag dictionary in OpenCV
DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)

# Detector (OpenCV 4.7+ has ArucoDetector; fallback to detectMarkers otherwise)
params = cv2.aruco.DetectorParameters()

def render_page_to_bgr(doc, page_index: int, dpi: int = 200):
    page = doc.load_page(page_index)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 1:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    return img

doc = fitz.open(PDF_PATH)

for i in range(len(doc)):
    img = render_page_to_bgr(doc, i, dpi=200)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Detect
    if hasattr(cv2.aruco, "ArucoDetector"):
        detector = cv2.aruco.ArucoDetector(DICT, params)
        corners, ids, rejected = detector.detectMarkers(gray)
    else:
        corners, ids, rejected = cv2.aruco.detectMarkers(gray, DICT, parameters=params)

    if ids is None or len(ids) == 0:
        print(f"Page {i}: no tag found")
        continue

    # Draw and label corner indices for each detected marker
    vis = img.copy()
    cv2.aruco.drawDetectedMarkers(vis, corners, ids)

    for m, tag_id in enumerate(ids.flatten()):
        c = corners[m].reshape(-1, 2).astype(int)  # shape (4,2)
        # c[0],c[1],c[2],c[3] are the detector's corner order
        for k, (x, y) in enumerate(c):
            cv2.circle(vis, (x, y), 10, (0, 0, 255), -1)
            cv2.putText(vis, f"{k}", (x + 12, y - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        # Put tag id near corner 0
        x0, y0 = c[0]
        cv2.putText(vis, f"ID {tag_id}", (x0 + 12, y0 + 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3)

    out_path = os.path.join(OUT_DIR, f"page_{i:02d}_corners.png")
    cv2.imwrite(out_path, vis)
    print(f"Page {i}: saved {out_path}")

print("Done.")
