"""CLI + UDP receive loop for the live push-up / squat trainer.

Run: PYTHONPATH=src ./venv/bin/python -m project_cam.assessment.live_trainer \
         --host 127.0.0.1 --port 5015 --exercise squat
"""

from __future__ import annotations

import argparse
import json
import socket

import cv2

from ..io import normalize_frame
from ..kinematics import frame_kinematics
from ..rules import DEFAULT_CONFIG_PATH, exercise_rules, load_rules
from .dashboard import render_dashboard
from .rep_state import make_counter


def run(host: str, port: int, exercise: str, config_path: str, fps: float,
        log_jsonl: str | None = None) -> int:
    config = load_rules(config_path)
    rules = exercise_rules(config, exercise)
    counter = make_counter(exercise, rules)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    sock.settimeout(0.2)

    window = f"Project_Cam Live Trainer - {exercise}"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    log_fh = open(log_jsonl, "w", encoding="utf-8") if log_jsonl else None
    last_joints: list = [None] * 17
    count = 0
    print(f"[TRAINER] exercise={exercise}  listening on {host}:{port}")
    print("[TRAINER] press 'q' or ESC in the window to quit")
    try:
        while True:
            try:
                data, _addr = sock.recvfrom(65535)
                packet = json.loads(data.decode("utf-8"))
                if isinstance(packet, dict) and packet.get("type") == "joints":
                    frame = normalize_frame(packet, index=count,
                                            default_fps=fps, source="udp")
                    metrics = frame_kinematics(frame)
                    state = counter.update(metrics)
                    last_joints = frame["joints"]
                    count += 1
                    if log_fh is not None:
                        log_fh.write(json.dumps({
                            "frame": frame["frame_index"],
                            "time_s": frame["time_s"],
                            "rep_count": state.rep_count,
                            "incomplete_count": state.incomplete_count,
                            "phase": state.phase,
                            "angle": state.current_angle,
                            "tracking_quality": state.tracking_quality,
                            "cue": state.cue,
                        }) + "\n")
            except socket.timeout:
                pass
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

            canvas = render_dashboard(exercise, counter.state, last_joints)
            cv2.imshow(window, canvas)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        if log_fh is not None:
            log_fh.close()
        cv2.destroyAllWindows()
    print(f"[TRAINER] stopped. reps={counter.state.rep_count} "
          f"incomplete={counter.state.incomplete_count}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Live push-up / squat trainer.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5015)
    ap.add_argument("--exercise", choices=["squat", "push_up"], default="squat")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--log-jsonl", default=None,
                    help="Optional path to record per-frame trainer state as JSONL.")
    args = ap.parse_args(argv)
    return run(host=args.host, port=args.port, exercise=args.exercise,
               config_path=args.config, fps=args.fps, log_jsonl=args.log_jsonl)


if __name__ == "__main__":
    raise SystemExit(main())
