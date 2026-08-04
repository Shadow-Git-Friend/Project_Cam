"""Replay a recorded pose stream into a drill state machine.

Why this exists: until 2026-08-03 nothing persisted the viewer's pose packets, so
a defect observed in a live session could not be reproduced. The 2026-08-01
`balance` session reported `sway_rms_mm 3986.5` from a `max_excursion_mm` of
31,633 mm, and the packets that produced it were gone the moment the process
exited — leaving synthetic reconstruction as the only way to study it.

With a trace on disk (`training_drill.py --record-packets`) the same session can
be pushed through a state machine as many times as needed: to reproduce a fault,
to check that a guard fixes it, and to tune a threshold against real sensor noise
instead of against a hand-written fixture. A recorded trace is also the cheapest
regression fixture the project can make — it needs no cameras and no launcher.

The trace format is one JSON object per line:

    {"schema": "project_cam.pose_trace.v1", "t": <unix seconds>,
     "packet": <the viewer's UDP payload, verbatim>}

Verbatim matters: the packet is the interface between the viewer and every
consumer, so a trace that stored a parsed subset would silently stop being a
faithful replay the first time that interface grew a field.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

PACKET_TRACE_SCHEMA = "project_cam.pose_trace.v1"


def parse_joints(packet):
    """(joints, conf, cams) from a viewer packet, mirroring the board's reader.

    Returns empty dicts for a heartbeat packet (one whose `joints` is empty),
    which the drills must read as absence of tracking rather than as a fresh
    observation.
    """
    joints, conf, cams = {}, {}, {}
    raw = packet.get("joints") if isinstance(packet, dict) else None
    if not isinstance(raw, dict):
        return joints, conf, cams
    for name, value in raw.items():
        if not isinstance(value, dict) or "x_mm" not in value:
            continue
        try:
            point = (float(value["x_mm"]), float(value["y_mm"]),
                     float(value["z_mm"]))
        except (TypeError, ValueError, KeyError):
            continue
        if not all(math.isfinite(v) for v in point):
            continue
        joints[name] = point
        if "conf" in value:
            try:
                conf[name] = float(value["conf"])
            except (TypeError, ValueError):
                pass
        if "cams" in value:
            try:
                cams[name] = int(value["cams"])
            except (TypeError, ValueError):
                pass
    return joints, conf, cams


def iter_trace(path):
    """Yield ``(t, packet)`` for each well-formed record, oldest first.

    Malformed lines are skipped rather than raising: a trace is usually recorded
    right up to a hard exit, so a truncated final line is the normal case, not a
    corrupt file.
    """
    with Path(path).open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            if "truncated_at_bytes" in record:
                continue
            timestamp = record.get("t")
            packet = record.get("packet")
            if not isinstance(packet, dict):
                continue
            try:
                timestamp = float(timestamp)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(timestamp):
                continue
            yield timestamp, packet


def replay(drill, path, start=True):
    """Drive ``drill`` through a recorded trace and return per-packet states.

    Timestamps come from the recording, so the replay is deterministic and the
    drill sees the rig's real packet rate — including its dropouts, which is
    what a synthetic fixture cannot supply.
    """
    states = []
    started = not start
    for timestamp, packet in iter_trace(path):
        if not started:
            drill.start(timestamp)
            started = True
        joints, _conf, _cams = parse_joints(packet)
        drill.update(timestamp, joints or None)
        states.append((timestamp, drill.state))
    return states


def trace_stats(path):
    """Raw facts about a trace, for deciding whether it is worth replaying."""
    packets = with_joints = 0
    first = last = None
    for timestamp, packet in iter_trace(path):
        packets += 1
        if first is None:
            first = timestamp
        last = timestamp
        joints, _conf, _cams = parse_joints(packet)
        if joints:
            with_joints += 1
    duration = None if first is None or last is None else last - first
    rate = None
    if duration and duration > 0 and packets > 1:
        rate = (packets - 1) / duration
    return {
        "packets": packets,
        "packets_with_joints": with_joints,
        "duration_s": duration,
        "observed_hz": rate,
    }
