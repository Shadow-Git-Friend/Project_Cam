import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import yaml


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_cameras(config_path):
    with open(config_path, "r") as f:
        data = yaml.safe_load(f) or {}
    cams = data.get("cameras", {})
    if not cams:
        raise ValueError(f"No cameras found in {config_path}")
    return cams


def load_trials(path):
    trials = []
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            trial_id = str(r.get("trial_id", "")).strip()
            if not trial_id:
                continue
            trials.append(
                {
                    "trial_id": trial_id,
                    "joint_name": str(r.get("joint_name", "")).strip(),
                    "x_mm": str(r.get("x_mm", "")).strip(),
                    "y_mm": str(r.get("y_mm", "")).strip(),
                    "z_mm": str(r.get("z_mm", "")).strip(),
                    "notes": str(r.get("notes", "")).strip(),
                }
            )
    return trials


def trial_key(trial_id):
    # J001 -> 1, fallback to original string ordering.
    num = "".join(ch for ch in trial_id if ch.isdigit())
    if num:
        return int(num)
    return trial_id


def filter_trials(trials, start_trial, end_trial):
    trials = sorted(trials, key=lambda t: trial_key(t["trial_id"]))
    if start_trial:
        s_key = trial_key(start_trial)
        trials = [t for t in trials if trial_key(t["trial_id"]) >= s_key]
    if end_trial:
        e_key = trial_key(end_trial)
        trials = [t for t in trials if trial_key(t["trial_id"]) <= e_key]
    return trials


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


def draw_overlay(frame, line1, line2, color):
    display = frame.copy()
    cv2.putText(display, line1, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    cv2.putText(display, line2, (12, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)
    return display


def read_last_frames(caps):
    frames = {}
    for cam_name, cap in caps.items():
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        frames[cam_name] = frame
    return frames


def wait_settle(caps, trial, settle_sec, show):
    start = time.monotonic()
    end = start + max(0.0, float(settle_sec))
    while time.monotonic() < end:
        remaining = max(0.0, end - time.monotonic())
        frames = read_last_frames(caps)
        if show:
            line1 = (
                f"{trial['trial_id']} {trial['joint_name']} "
                f"({trial['x_mm']},{trial['y_mm']},{trial['z_mm']})"
            )
            line2 = f"GET READY: {remaining:04.1f}s"
            for cam_name, frame in frames.items():
                display = draw_overlay(frame, line1, line2, (0, 255, 255))
                cv2.imshow(cam_name, display)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                return False
        else:
            time.sleep(0.02)
    return True


def record_trial_clip(args, caps, trial):
    clip_name = f"{trial['trial_id']}_001"
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
    aborted = False

    while time.monotonic() < end_mono:
        remain = max(0.0, end_mono - time.monotonic())
        for cam_name, cap in caps.items():
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            if frame.shape[1] != args.width or frame.shape[0] != args.height:
                frame = cv2.resize(frame, (args.width, args.height))
            writers[cam_name].write(frame)
            frame_counts[cam_name] += 1
            if args.show:
                line1 = (
                    f"{trial['trial_id']} {trial['joint_name']} "
                    f"({trial['x_mm']},{trial['y_mm']},{trial['z_mm']})"
                )
                line2 = f"REC: {remain:04.1f}s"
                display = draw_overlay(frame, line1, line2, (0, 0, 255))
                cv2.imshow(cam_name, display)
        if args.show:
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                aborted = True
                break

    for writer in writers.values():
        writer.release()

    end_wall = utc_now_iso()
    duration = time.monotonic() - start_mono

    metadata = {
        "clip_name": clip_name,
        "trial_id": trial["trial_id"],
        "joint_name": trial["joint_name"],
        "target_mm": [trial["x_mm"], trial["y_mm"], trial["z_mm"]],
        "notes": trial.get("notes", ""),
        "duration_sec_requested": args.duration_sec,
        "duration_sec_actual": duration,
        "fps_target": args.fps,
        "resolution": [args.width, args.height],
        "started_at_utc": start_wall,
        "ended_at_utc": end_wall,
        "frame_counts": frame_counts,
        "aborted": aborted,
    }
    with open(clip_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    return metadata, aborted


def clip_exists(out_dir, trial_id):
    clip_dir = Path(out_dir) / f"{trial_id}_001"
    if not clip_dir.exists():
        return False
    files = list(clip_dir.glob("cam*.*"))
    return len(files) >= 2


def main():
    ap = argparse.ArgumentParser(
        description="Auto-record all joint GT trials from CSV with countdown."
    )
    ap.add_argument("--config", default="garage_lab_combined/config/cameras.yaml")
    ap.add_argument("--trials-csv", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--start-trial", default="")
    ap.add_argument("--end-trial", default="")
    ap.add_argument("--duration-sec", type=float, default=4.0)
    ap.add_argument("--settle-sec", type=float, default=8.0, help="Countdown before each recording")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--in-fourcc", default="MJPG")
    ap.add_argument("--out-codec", default="MJPG")
    ap.add_argument("--ext", default="avi")
    ap.add_argument("--buffer-size", type=int, default=1)
    ap.add_argument("--skip-existing", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument(
        "--show",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show preview windows (default: on). Use --no-show for headless.",
    )
    args = ap.parse_args()

    if args.duration_sec <= 0:
        raise ValueError("--duration-sec must be > 0")
    if len(args.in_fourcc) != 4:
        raise ValueError("--in-fourcc must be exactly 4 chars")
    if len(args.out_codec) != 4:
        raise ValueError("--out-codec must be exactly 4 chars")

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    trials = load_trials(args.trials_csv)
    trials = filter_trials(trials, args.start_trial, args.end_trial)
    if not trials:
        raise RuntimeError("No trials selected.")

    cams_cfg = load_cameras(args.config)
    caps = {}
    manifest = {
        "created_at_utc": utc_now_iso(),
        "trials_csv": args.trials_csv,
        "out_dir": args.out_dir,
        "duration_sec": args.duration_sec,
        "settle_sec": args.settle_sec,
        "resolution": [args.width, args.height],
        "fps": args.fps,
        "trials_total_selected": len(trials),
        "records": [],
    }

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
        print(f"[INFO] Selected trials: {len(trials)}")
        print("[INFO] During run press 'q' in preview windows to stop.")
        print("")

        for idx, trial in enumerate(trials, start=1):
            if args.skip_existing and clip_exists(args.out_dir, trial["trial_id"]):
                print(f"[SKIP] {trial['trial_id']}: clip already exists")
                continue

            print(
                f"[TRIAL {idx}/{len(trials)}] {trial['trial_id']} | "
                f"{trial['joint_name']} | "
                f"target=({trial['x_mm']},{trial['y_mm']},{trial['z_mm']})"
            )
            if trial.get("notes"):
                print(f"  notes: {trial['notes']}")

            if not wait_settle(caps, trial, args.settle_sec, args.show):
                print("[STOP] Interrupted during countdown.")
                break

            metadata, aborted = record_trial_clip(args, caps, trial)
            manifest["records"].append(metadata)
            print(f"[SAVED] {metadata['clip_name']} | frames: {metadata['frame_counts']}")

            if aborted:
                print("[STOP] Interrupted during recording.")
                break

        manifest["finished_at_utc"] = utc_now_iso()
        with open(Path(args.out_dir) / "session_manifest.json", "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"[DONE] Session manifest: {Path(args.out_dir) / 'session_manifest.json'}")

    finally:
        for cap in caps.values():
            cap.release()
        if args.show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
