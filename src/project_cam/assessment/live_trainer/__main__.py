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
from .dashboard import SkeletonView, render_dashboard
from .rep_state import make_counter

_RECV_BUF = 65535


def _receive_available(sock: socket.socket) -> list[bytes]:
    """Block briefly for one packet, then drain all queued packets.

    The live tracker streams ~15 packets/s. If a render frame takes longer
    than the packet interval, packets queue in the OS buffer and reading them
    one-per-loop replays stale poses. The counter still needs every queued
    sample, so this returns the drained FIFO and lets the render path draw only
    once from the newest processed frame.
    """
    old_timeout = sock.gettimeout() if hasattr(sock, "gettimeout") else 0.2
    try:
        first, _addr = sock.recvfrom(_RECV_BUF)
    except socket.timeout:
        return []
    except OSError:
        return []
    packets = [first]
    sock.setblocking(False)
    try:
        while True:
            try:
                data, _addr = sock.recvfrom(_RECV_BUF)
                packets.append(data)
            except BlockingIOError:
                break
            except OSError:
                break
    finally:
        sock.settimeout(old_timeout)
    return packets


def _parse_joint_packet(data: bytes) -> dict | None:
    try:
        packet = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(packet, dict) and packet.get("type") == "joints":
        return packet
    return None


def _process_joint_packets(
    packets: list[bytes],
    counter,
    fps: float,
    start_count: int,
    log_fh=None,
) -> tuple[list | None, int]:
    """Feed every drained packet through kinematics/counter; return newest joints."""
    count = start_count
    last_joints = None
    for data in packets:
        packet = _parse_joint_packet(data)
        if packet is None:
            continue
        frame = normalize_frame(packet, index=count, default_fps=fps, source="udp")
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
    return last_joints, count


def run(host: str, port: int, exercise: str, config_path: str, fps: float,
        log_jsonl: str | None = None) -> int:
    config = load_rules(config_path)
    rules = exercise_rules(config, exercise)
    counter = make_counter(exercise, rules)
    skeleton_view = SkeletonView()

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
            packets = _receive_available(sock)
            if packets:
                newest_joints, count = _process_joint_packets(
                    packets, counter, fps=fps, start_count=count, log_fh=log_fh
                )
                if newest_joints is not None:
                    last_joints = newest_joints

            canvas = render_dashboard(exercise, counter.state, last_joints,
                                      view=skeleton_view)
            cv2.imshow(window, canvas)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            # also quit if the window was closed with the window-manager button
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
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
