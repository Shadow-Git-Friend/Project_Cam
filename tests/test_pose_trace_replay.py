"""Recording the pose stream, and replaying it into a drill.

The gap this closes: before 2026-08-03 nothing persisted the viewer's packets, so
the three defective live sessions of 2026-07-31/08-01 could only be studied by
reconstructing their shape by hand. Every threshold in
`project_cam.training.plausibility` was therefore tuned against synthetic noise.
A recorded trace makes the real noise available, and makes a live fault into a
regression fixture that needs no cameras.

These tests cover the round trip — a real UDP packet in, a drill driven out —
plus the properties that decide whether a trace can be trusted: it is verbatim,
it survives truncation, it is bounded, and recording never takes a session down.
"""

import importlib.util
import json
import socket
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from project_cam.training.drills import BalanceDrill, CmjDrill
from project_cam.training.replay import (
    PACKET_TRACE_SCHEMA,
    iter_trace,
    parse_joints,
    replay,
    trace_stats,
)

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "garage_lab_combined/scripts/training_drill.py"


@pytest.fixture(scope="module")
def board():
    spec = importlib.util.spec_from_file_location("training_drill_board", BOARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def packet(x=3000.0, y=1500.0, z=950.0, conf=0.8, cams=4, capture=None):
    joints = {}
    for name, offset in (("left_hip", -90.0), ("right_hip", 90.0)):
        joints[name] = {"x_mm": x, "y_mm": y + offset, "z_mm": z,
                        "conf": conf, "cams": cams}
    payload = {"schema": "project_cam.target.v1", "joints": joints}
    if capture is not None:
        payload["capture"] = capture
    return payload


def write_trace(path, packets, t0=1000.0, dt=1.0 / 15.0):
    with path.open("w", encoding="utf-8") as stream:
        for index, pkt in enumerate(packets):
            stream.write(json.dumps({"schema": PACKET_TRACE_SCHEMA,
                                     "t": t0 + index * dt,
                                     "packet": pkt}) + "\n")
    return path


# ------------------------------------------------------------------ recording

def test_a_real_udp_packet_lands_in_the_trace_verbatim(board, tmp_path):
    """The packet IS the viewer/consumer interface; a parsed subset would rot."""
    trace = tmp_path / "pose_trace.jsonl"
    listener = board.UDPJointListener(host="127.0.0.1", port=0,
                                      record_path=str(trace))
    try:
        # port=0 asks the OS for a free port, so read back what it bound to.
        deadline = time.time() + 3.0
        while listener.bound_port is None and time.time() < deadline:
            time.sleep(0.01)
        assert listener.bound_port, "listener never bound a port"
        sent = packet(capture={"context_schema": "project_cam.capture_context.v1",
                               "opened_camera_roles": ["camUsb01_C920"]})
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(json.dumps(sent).encode("utf-8"),
                    ("127.0.0.1", listener.bound_port))
        sock.close()
        deadline = time.time() + 3.0
        while listener.records_written < 1 and time.time() < deadline:
            time.sleep(0.01)
    finally:
        listener.stop()
    assert listener.records_written == 1
    (timestamp, recorded), = list(iter_trace(trace))
    assert recorded == sent, "the trace must be byte-faithful, not a projection"
    assert timestamp > 0


def test_recording_is_off_unless_asked_for_or_inside_a_desktop_session(
        board, monkeypatch, tmp_path):
    monkeypatch.delenv("PROJECT_CAM_SESSION_DIR", raising=False)
    bare = SimpleNamespace(record_packets="", no_record_packets=False)
    assert board.resolve_trace_path(bare) == ""

    monkeypatch.setenv("PROJECT_CAM_SESSION_DIR", str(tmp_path / "s-1"))
    assert board.resolve_trace_path(bare) == str(tmp_path / "s-1" / "pose_trace.jsonl")

    explicit = SimpleNamespace(record_packets="/tmp/x.jsonl",
                               no_record_packets=False)
    assert board.resolve_trace_path(explicit) == "/tmp/x.jsonl"

    # An explicit refusal beats both, including inside a session.
    refused = SimpleNamespace(record_packets="/tmp/x.jsonl",
                              no_record_packets=True)
    assert board.resolve_trace_path(refused) == ""


def test_the_trace_is_bounded_and_says_where_it_stopped(board, tmp_path):
    trace = tmp_path / "capped.jsonl"
    listener = board.UDPJointListener.__new__(board.UDPJointListener)
    listener.record_path = str(trace)
    listener.record_max_bytes = 400        # a couple of records
    listener.records_written = 0
    listener.record_bytes = 0
    listener.record_truncated = False
    listener._record_stream = None
    for _ in range(50):
        listener._record(packet(), 1000.0)
    assert listener.record_truncated, "an unattended session must not fill the disk"
    assert listener.record_bytes <= 400
    body = trace.read_text(encoding="utf-8")
    assert "truncated_at_bytes" in body, "silent truncation reads as a clean trace"
    # And the marker record must not be replayed as a packet.
    assert all("truncated_at_bytes" not in p for _t, p in iter_trace(trace))


def test_an_unwritable_trace_path_never_takes_the_session_down(board, tmp_path):
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("this is a file, so its child path cannot be created\n")
    listener = board.UDPJointListener.__new__(board.UDPJointListener)
    listener.record_path = str(blocked / "pose_trace.jsonl")
    listener.record_max_bytes = 1024
    listener.records_written = 0
    listener.record_bytes = 0
    listener.record_truncated = False
    listener._record_stream = None
    listener._record(packet(), 1000.0)     # must not raise
    assert listener.records_written == 0
    assert listener.record_truncated


# -------------------------------------------------------------------- reading

def test_a_truncated_final_line_is_normal_not_corruption(tmp_path):
    trace = tmp_path / "cut.jsonl"
    write_trace(trace, [packet(), packet()])
    with trace.open("a", encoding="utf-8") as stream:
        stream.write('{"schema": "project_cam.pose_trace.v1", "t": 1000.2, "pack')
    assert len(list(iter_trace(trace))) == 2


def test_malformed_records_are_skipped_individually(tmp_path):
    trace = tmp_path / "mixed.jsonl"
    lines = [
        json.dumps({"schema": PACKET_TRACE_SCHEMA, "t": 1.0, "packet": packet()}),
        "not json at all",
        json.dumps([1, 2, 3]),
        json.dumps({"schema": PACKET_TRACE_SCHEMA, "t": "later",
                    "packet": packet()}),
        json.dumps({"schema": PACKET_TRACE_SCHEMA, "t": 2.0, "packet": "nope"}),
        json.dumps({"schema": PACKET_TRACE_SCHEMA, "t": 3.0, "packet": packet()}),
    ]
    trace.write_text("\n".join(lines) + "\n", encoding="utf-8")
    kept = list(iter_trace(trace))
    assert [t for t, _ in kept] == [1.0, 3.0]


def test_a_heartbeat_packet_reads_as_absence_of_tracking():
    """The empty-joints heartbeat proves liveness, never a fresh observation."""
    joints, conf, cams = parse_joints({"joints": {}})
    assert joints == {} and conf == {} and cams == {}
    # A non-finite coordinate is not an observation either.
    bad = {"joints": {"left_hip": {"x_mm": "nan", "y_mm": 0.0, "z_mm": 0.0}}}
    assert parse_joints(bad)[0] == {}


def test_trace_stats_report_the_observed_packet_rate(tmp_path):
    trace = tmp_path / "rate.jsonl"
    write_trace(trace, [packet() for _ in range(16)], dt=1.0 / 15.0)
    stats = trace_stats(trace)
    assert stats["packets"] == 16
    assert stats["packets_with_joints"] == 16
    assert stats["observed_hz"] == pytest.approx(15.0, rel=0.02)


# --------------------------------------------------------------------- replay

def test_replaying_a_trace_drives_a_real_drill_to_completion(tmp_path):
    """The round trip that makes a live session a regression fixture."""
    trace = tmp_path / "cmj.jsonl"
    heights = ([950.0] * 30                      # stand, so calibration sees it
               + [870.0, 850.0]                  # dip
               + [1090.0, 1290.0, 1250.0]        # rise and apex
               + [950.0] * 5)
    write_trace(trace, [packet(z=z) for z in heights])
    drill = CmjDrill(jumps=1, countdown_s=1.0, calib_s=0.5)
    states = replay(drill, trace)
    assert states, "replay produced no states"
    assert drill.summary()["jumps_completed"] == 1
    assert drill.summary()["best_pelvis_rise_mm"] == pytest.approx(340.0, abs=15.0)


def test_a_trace_containing_the_2026_08_01_flier_reproduces_and_is_now_gated():
    """The point of the harness: a fault becomes a test, and the guard answers it.

    Written as a synthesised trace because the original session's packets were
    never recorded — which is precisely the gap being closed. From the next live
    session on, this test can be pointed at the real file instead.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        trace = Path(directory) / "balance.jsonl"
        packets = []
        for step in range(200):
            if step == 120:
                packets.append(packet(x=31000.0))      # the 31.6 m excursion
            else:
                packets.append(packet(x=3000.0 + 6.0 * (step % 5)))
        # Raise a foot so the drill actually samples: ankles come from the same
        # packet, so they are appended here rather than in `packet()`.
        for pkt in packets:
            pkt["joints"]["left_ankle"] = {"x_mm": 3000.0, "y_mm": 1400.0,
                                           "z_mm": 80.0, "conf": 0.8, "cams": 4}
            pkt["joints"]["right_ankle"] = {"x_mm": 3000.0, "y_mm": 1600.0,
                                            "z_mm": 400.0, "conf": 0.8, "cams": 4}
        write_trace(trace, packets)

        drill = BalanceDrill(holds=1, hold_s=8.0, countdown_s=1.0)
        replay(drill, trace)
        hold = drill.results[0]
        assert hold["samples_rejected"] == 1, "the flier must be seen and counted"
        assert hold["sway_rms_mm"] is not None
        assert hold["sway_rms_mm"] < 40.0, "and must not reach the measurement"
