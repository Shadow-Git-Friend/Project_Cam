import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import yaml


def load_cameras(config_path):
    with open(config_path, "r") as f:
        data = yaml.safe_load(f) or {}
    cams = data.get("cameras", {})
    if not cams:
        raise ValueError(f"No cameras found in {config_path}")
    return cams


def open_capture(device, width, height, fourcc, buffer_size):
    cap = cv2.VideoCapture(device)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    if buffer_size is not None:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, buffer_size)
    return cap


def open_writer(path, width, height, fps, codec):
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*codec),
        float(fps),
        (width, height),
    )
    if not writer.isOpened():
        return None
    return writer


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def record_clip(args, caps, clip_index, show_preview):
    clip_name = f"{args.prefix}_{clip_index:03d}"
    clip_dir = Path(args.out_dir) / clip_name
    clip_dir.mkdir(parents=True, exist_ok=True)

    writers = {}
    frame_counts = {}
    for cam_name in caps.keys():
        out_path = clip_dir / f"{cam_name}.{args.ext}"
        writer = open_writer(out_path, args.width, args.height, args.fps, args.out_codec)
        if writer is None:
            for w in writers.values():
                w.release()
            raise RuntimeError(
                f"Cannot open writer for {out_path}. Try --ext avi --out-codec MJPG."
            )
        writers[cam_name] = writer
        frame_counts[cam_name] = 0

    start_wall = utc_now_iso()
    start_mono = time.monotonic()
    end_mono = start_mono + args.duration_sec

    last_frames = {}
    while time.monotonic() < end_mono:
        for cam_name, cap in caps.items():
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            if frame.shape[1] != args.width or frame.shape[0] != args.height:
                frame = cv2.resize(frame, (args.width, args.height))
            writers[cam_name].write(frame)
            frame_counts[cam_name] += 1
            last_frames[cam_name] = frame

        if show_preview:
            for cam_name, frame in last_frames.items():
                display = frame.copy()
                remain = max(0.0, end_mono - time.monotonic())
                cv2.putText(
                    display,
                    f"{cam_name} REC {remain:.1f}s",
                    (12, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.85,
                    (0, 0, 255),
                    2,
                )
                cv2.imshow(cam_name, display)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    for writer in writers.values():
        writer.release()

    end_wall = utc_now_iso()
    duration = time.monotonic() - start_mono

    metadata = {
        "clip_name": clip_name,
        "duration_sec_requested": args.duration_sec,
        "duration_sec_actual": duration,
        "fps_target": args.fps,
        "resolution": [args.width, args.height],
        "started_at_utc": start_wall,
        "ended_at_utc": end_wall,
        "frame_counts": frame_counts,
    }
    with open(clip_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    return clip_name, frame_counts


def pre_record_delay(args, caps, clip_index):
    """Wait before recording starts so operator can move to target point."""
    delay = float(getattr(args, "start_delay_sec", 0.0))
    if delay <= 0:
        return True

    end_mono = time.monotonic() + delay
    last_frames = {}
    while time.monotonic() < end_mono:
        for cam_name, cap in caps.items():
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            last_frames[cam_name] = frame

        remain = max(0.0, end_mono - time.monotonic())
        if args.show:
            for cam_name, frame in last_frames.items():
                display = frame.copy()
                cv2.putText(
                    display,
                    f"{cam_name} start in {remain:.1f}s",
                    (12, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.75,
                    (0, 255, 255),
                    2,
                )
                cv2.putText(
                    display,
                    f"next: {args.prefix}_{clip_index:03d}",
                    (12, 60),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 255, 255),
                    2,
                )
                cv2.imshow(cam_name, display)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                return False
        else:
            time.sleep(min(0.05, remain))

    return True


def main():
    ap = argparse.ArgumentParser(
        description="Record short synchronized clips from garage cameras."
    )
    ap.add_argument("--config", default="garage_lab_combined/config/cameras.yaml")
    ap.add_argument("--out-dir", default="garage_lab_combined/test_clips")
    ap.add_argument("--prefix", default="trial")
    ap.add_argument("--start-index", type=int, default=1)
    ap.add_argument(
        "--clips",
        type=int,
        default=0,
        help="How many clips to record (0 = unlimited until q).",
    )
    ap.add_argument("--duration-sec", type=float, default=2.5)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--in-fourcc", default="MJPG")
    ap.add_argument("--out-codec", default="MJPG")
    ap.add_argument("--ext", default="mkv")
    ap.add_argument("--buffer-size", type=int, default=1)
    ap.add_argument(
        "--start-delay-sec",
        type=float,
        default=4.0,
        help="Delay after pressing r before recording starts (set 0 to disable).",
    )
    ap.add_argument(
        "--show",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show preview windows (default: on). Use --no-show to disable.",
    )
    args = ap.parse_args()

    if args.duration_sec <= 0:
        raise ValueError("--duration-sec must be > 0")
    if len(args.in_fourcc) != 4:
        raise ValueError("--in-fourcc must be exactly 4 chars")
    if len(args.out_codec) != 4:
        raise ValueError("--out-codec must be exactly 4 chars")

    cams_cfg = load_cameras(args.config)
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)

    caps = {}
    try:
        for cam_name, cfg in cams_cfg.items():
            device = cfg.get("device")
            if not device:
                print(f"[WARN] {cam_name}: missing device in config")
                continue
            cap = open_capture(
                device=device,
                width=args.width,
                height=args.height,
                fourcc=args.in_fourcc,
                buffer_size=args.buffer_size,
            )
            if cap is None or not cap.isOpened():
                print(f"[ERROR] {cam_name}: cannot open {device}")
                continue
            caps[cam_name] = cap
            print(f"[OK] {cam_name} -> {device}")

        if len(caps) < 2:
            raise RuntimeError("Need at least 2 opened cameras.")

        print("")
        print("[INFO] Controls")
        print("  r = record one short clip")
        print("  q = quit")
        print("")

        clip_idx = args.start_index
        recorded = 0

        while True:
            last_frames = {}
            for cam_name, cap in caps.items():
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue
                last_frames[cam_name] = frame

            if args.show:
                for cam_name, frame in last_frames.items():
                    display = frame.copy()
                    cv2.putText(
                        display,
                        f"{cam_name} ready | next: {args.prefix}_{clip_idx:03d}",
                        (12, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2,
                    )
                    cv2.imshow(cam_name, display)
                key = cv2.waitKey(1) & 0xFF
            else:
                # Without preview, read commands from terminal.
                key = ord(input("Type r to record, q to quit: ").strip().lower()[:1] or " ")

            if key == ord("q"):
                print("[INFO] Stopped by user.")
                break
            if key != ord("r"):
                continue

            if not pre_record_delay(args=args, caps=caps, clip_index=clip_idx):
                print("[INFO] Stopped by user.")
                break

            clip_name, frame_counts = record_clip(
                args=args,
                caps=caps,
                clip_index=clip_idx,
                show_preview=args.show,
            )
            print(f"[SAVED] {clip_name} | frames: {frame_counts}")

            clip_idx += 1
            recorded += 1
            if args.clips > 0 and recorded >= args.clips:
                print("[DONE] Requested number of clips recorded.")
                break

    finally:
        for cap in caps.values():
            cap.release()
        if args.show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
