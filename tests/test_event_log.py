"""Tests for the closed-loop EventLogger.

Properties locked here:
  1. Round-trip: events emitted are recoverable from JSONL with schema intact.
  2. Overflow: queue saturation drops events but never raises or blocks.
  3. Thread safety: concurrent emitters produce well-formed lines (no
     interleaved or partial records).
  4. Unknown event type: tolerated, surfaced in payload for debuggability.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from project_cam.closed_loop.event_log import (
    EVENT_TYPES,
    EventLogger,
    SCHEMA_VERSION,
    validate_event_record,
)


def _read_records(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


class EventLoggerTests(unittest.TestCase):
    def test_round_trip_1000_events(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "events.jsonl"
            logger = EventLogger(
                output_path=path,
                session_id="test_session",
                source="unit_test",
                register_atexit=False,
            )
            for i in range(1000):
                logger.emit("target_chosen", {"i": i})
            logger.close(timeout=10.0)

            records = _read_records(path)
            self.assertEqual(len(records), 1000)
            for idx, rec in enumerate(records):
                validate_event_record(rec)
                self.assertEqual(rec["session_id"], "test_session")
                self.assertEqual(rec["source"], "unit_test")
                self.assertEqual(rec["event_type"], "target_chosen")
                self.assertEqual(rec["payload"]["i"], idx)
                self.assertEqual(rec["schema_version"], SCHEMA_VERSION)
            # Monotonic timestamps.
            timestamps = [r["timestamp"] for r in records]
            self.assertEqual(timestamps, sorted(timestamps))

    def test_overflow_drops_without_blocking_or_raising(self):
        """When emit rate >> drain rate, oldest events drop and counter ticks."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "overflow.jsonl"
            logger = EventLogger(
                output_path=path,
                session_id="overflow",
                source="unit_test",
                maxsize=10,
                register_atexit=False,
            )
            # Hammer 200 events in a tight loop — far exceeds queue capacity if
            # the writer thread can't keep up. Even when the writer is fast,
            # this still verifies no exception leaks.
            for i in range(200):
                logger.emit("target_chosen", {"i": i})
            logger.close(timeout=10.0)

            records = _read_records(path)
            self.assertLessEqual(len(records), 200)
            self.assertGreaterEqual(len(records), 1)
            # Dropped count + records ≈ emitted (modulo extreme-contention double-drops).
            # We allow some slack but the relationship should hold within a small margin.
            total_accounted = len(records) + logger.dropped_event_count
            self.assertLessEqual(total_accounted, 200 + 5)

    def test_thread_safety_concurrent_emitters(self):
        """Four threads emitting concurrently produce well-formed, parseable lines."""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "concurrent.jsonl"
            logger = EventLogger(
                output_path=path,
                session_id="concurrent",
                source="unit_test",
                register_atexit=False,
            )
            per_thread = 250

            def worker(thread_id: int) -> None:
                for j in range(per_thread):
                    logger.emit("ball_launched", {"thread": thread_id, "j": j})

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            logger.close(timeout=10.0)

            records = _read_records(path)
            # Every successfully-emitted line must parse and validate.
            for rec in records:
                validate_event_record(rec)
                self.assertEqual(rec["event_type"], "ball_launched")
            # We expect close to 1000 total; allow some headroom for overflow drops.
            self.assertGreater(len(records), 800)

    def test_unknown_event_type_does_not_crash_and_is_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "unknown.jsonl"
            logger = EventLogger(
                output_path=path,
                session_id="unknown_session",
                source="unit_test",
                register_atexit=False,
            )
            logger.emit("not_a_real_event_type", {"x": 1})
            logger.close(timeout=5.0)

            records = _read_records(path)
            self.assertEqual(len(records), 1)
            rec = records[0]
            validate_event_record(rec)
            self.assertEqual(rec["event_type"], "session_end")  # safest fallback
            self.assertEqual(rec["payload"]["_unknown_event_type"], "not_a_real_event_type")

    def test_all_canonical_event_types_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "all_types.jsonl"
            logger = EventLogger(
                output_path=path,
                session_id="all_types",
                source="unit_test",
                register_atexit=False,
            )
            for et in EVENT_TYPES:
                logger.emit(et, {"marker": et})
            logger.close(timeout=5.0)

            records = _read_records(path)
            seen = {rec["event_type"] for rec in records}
            self.assertEqual(seen, set(EVENT_TYPES))

    def test_close_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "idempotent.jsonl"
            logger = EventLogger(
                output_path=path,
                session_id="idem",
                source="unit_test",
                register_atexit=False,
            )
            logger.emit("session_start", {"k": "v"})
            logger.close(timeout=5.0)
            # Second close must not raise.
            logger.close(timeout=1.0)
            logger.close(timeout=1.0)

    def test_missing_session_id_raises(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                EventLogger(
                    output_path=Path(td) / "x.jsonl",
                    session_id="",
                    source="unit_test",
                    register_atexit=False,
                )


if __name__ == "__main__":
    unittest.main()
