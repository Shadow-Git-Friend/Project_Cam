"""Record live Project_Cam UDP joint packets to JSONL for offline assessment."""

from __future__ import annotations

import argparse
import json
import socket
import time
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION


def record_udp(
    host: str,
    port: int,
    output: str | Path,
    session_id: str,
    athlete_id: str,
    exercise: str,
    age: int | None,
    sex: str,
    fps: float,
    duration_sec: float = 0.0,
    max_frames: int = 0,
) -> int:
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    sock.settimeout(0.5)

    start = time.time()
    count = 0
    session = {
        "session_id": session_id,
        "athlete_id": athlete_id,
        "exercise": exercise,
        "age": age,
        "sex": sex,
        "fps": fps,
    }

    print(f"[REC] Listening for Project_Cam UDP joints on {host}:{port}")
    print(f"[REC] Writing JSONL -> {out_path}")
    try:
        with out_path.open("w", encoding="utf-8") as fh:
            while True:
                if duration_sec > 0 and (time.time() - start) >= duration_sec:
                    break
                if max_frames > 0 and count >= max_frames:
                    break
                try:
                    data, addr = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                packet = json.loads(data.decode("utf-8"))
                if not isinstance(packet, dict) or packet.get("type") != "joints":
                    continue
                record = _wrap_packet(packet, session=session, addr=addr, start=start)
                fh.write(json.dumps(record, sort_keys=False) + "\n")
                count += 1
                if count % 30 == 0:
                    fh.flush()
                    print(f"[REC] frames={count}")
    except KeyboardInterrupt:
        print("\n[REC] Stopped by user")
    finally:
        sock.close()
    print(f"[DONE] Recorded {count} joint frames -> {out_path}")
    return count


def _wrap_packet(packet: dict[str, Any], session: dict[str, Any], addr: tuple[str, int], start: float) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "type": "joints",
        "session": session,
        "frame": packet.get("frame"),
        "time_s": time.time() - start,
        "ts": packet.get("ts"),
        "source_addr": {"host": addr[0], "port": addr[1]},
        "joints": packet.get("joints", {}),
        "predicted": packet.get("predicted", {}),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Record Project_Cam live UDP joint packets to JSONL.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5015)
    ap.add_argument("--output", required=True)
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--athlete-id", required=True)
    ap.add_argument("--exercise", required=True)
    ap.add_argument("--age", type=int, default=None)
    ap.add_argument("--sex", choices=["male", "female", "unspecified"], default="unspecified")
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--duration-sec", type=float, default=0.0, help="Stop after N seconds; 0 records until Ctrl+C")
    ap.add_argument("--max-frames", type=int, default=0, help="Stop after N UDP frames; 0 disables this limit")
    args = ap.parse_args(argv)

    record_udp(
        host=args.host,
        port=args.port,
        output=args.output,
        session_id=args.session_id,
        athlete_id=args.athlete_id,
        exercise=args.exercise,
        age=args.age,
        sex=args.sex,
        fps=args.fps,
        duration_sec=args.duration_sec,
        max_frames=args.max_frames,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
