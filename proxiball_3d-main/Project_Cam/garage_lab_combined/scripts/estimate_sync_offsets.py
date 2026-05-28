import argparse
import os
import cv2
import numpy as np


def find_flash_frame(path, ignore=10, step=1, max_frames=0):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    means = []
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            means.append(gray.mean())
        idx += 1
        if max_frames > 0 and idx >= max_frames:
            break
    cap.release()

    if len(means) < 3:
        return None

    means = np.array(means, dtype=np.float32)
    # delta between consecutive means
    delta = means[1:] - means[:-1]

    start = max(0, ignore)
    if start >= len(delta):
        start = 0

    peak_idx = int(np.argmax(delta[start:]) + start + 1)  # +1 to map to frame index in means
    peak_val = float(delta[peak_idx - 1])
    return {
        "flash_frame": int(peak_idx * step),
        "peak_delta": peak_val,
        "mean_at_peak": float(means[peak_idx]),
        "frames_analyzed": int(len(means) * step),
    }


def main():
    ap = argparse.ArgumentParser(description="Estimate sync offsets using flashlight brightness spike")
    ap.add_argument("videos", nargs="+", help="Video paths")
    ap.add_argument("--ignore", type=int, default=10, help="Ignore first N sampled frames (auto-exposure)")
    ap.add_argument("--step", type=int, default=1, help="Process every Nth frame")
    ap.add_argument("--max-frames", type=int, default=0, help="Limit frames per video (0 = all)")
    args = ap.parse_args()

    results = []
    for v in args.videos:
        res = find_flash_frame(v, ignore=args.ignore, step=args.step, max_frames=args.max_frames)
        if res is None:
            print(os.path.basename(v), "-> no data")
            continue
        res["video"] = v
        results.append(res)
        print(os.path.basename(v), "flash frame:", res["flash_frame"], "peak_delta:", f"{res['peak_delta']:.2f}")

    if not results:
        return

    # Compute offsets relative to median
    frames = [r["flash_frame"] for r in results]
    ref = int(np.median(frames))
    print("\nEstimated offsets relative to median frame", ref)
    for r in results:
        off = r["flash_frame"] - ref
        print(os.path.basename(r["video"]), "offset", off)


if __name__ == "__main__":
    main()
