"""Non-blocking JSONL event logger for the closed-loop demo narrative.

The live viewer and launcher runtime emit timestamped events
(target_chosen → aim_command_sent → ball_launched → athlete_reacted →
outcome_scored) into a single JSONL stream per session. Downstream tooling
joins this stream with the launcher's `log_decision` stream via `session_id`
to produce demo summaries and validation analyses.

Performance contract:
  - `emit()` is non-blocking. It enqueues via `queue.put_nowait` and returns
    in O(microseconds). A daemon thread drains the queue and writes to disk.
  - If the queue saturates (>= maxsize), the oldest pending event is dropped
    and a `dropped_event_count` counter is incremented. The render loop is
    NEVER blocked on disk I/O.
  - `close()` flushes and joins the writer thread. Always call it before exit
    (atexit registration handles the common case).

Schema is intentionally narrow: one event per line, JSON object with seven
fields. Backwards-incompatible changes bump `SCHEMA_VERSION`.
"""

from __future__ import annotations

import atexit
import json
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "project_cam.closed_loop.event_log.v1"

# Canonical event vocabulary. Producers are free to add fields under `payload`
# but should not invent new top-level event types without bumping schema.
EVENT_TYPES: frozenset[str] = frozenset(
    {
        "session_start",
        "target_chosen",
        "aim_command_sent",
        "ball_launched",
        "athlete_reacted",
        "outcome_scored",
        "safety_gate_blocked",
        "session_end",
    }
)

_REQUIRED_KEYS = (
    "schema_version",
    "session_id",
    "timestamp",
    "wall_clock_iso",
    "event_type",
    "source",
    "payload",
)


class EventLogger:
    """Append-only JSONL writer with bounded async queue.

    Thread-safe for many concurrent `emit()` callers. Single writer thread.
    """

    def __init__(
        self,
        output_path: str | Path,
        session_id: str,
        source: str,
        maxsize: int = 10_000,
        register_atexit: bool = True,
    ) -> None:
        if not session_id:
            raise ValueError("session_id is required")
        if not source:
            raise ValueError("source is required (e.g. 'live_viewer', 'launcher_runtime')")
        self._output_path = Path(output_path)
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        self._session_id = str(session_id)
        self._source = str(source)
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=maxsize)
        self._stop_event = threading.Event()
        self._dropped = 0
        self._dropped_lock = threading.Lock()
        # The writer thread opens the file lazily so that EventLogger can be
        # constructed in __init__ paths without immediate disk I/O.
        self._writer_thread = threading.Thread(
            target=self._writer_loop, name=f"event-log-writer:{source}", daemon=True
        )
        self._writer_thread.start()
        if register_atexit:
            atexit.register(self.close)

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def output_path(self) -> Path:
        return self._output_path

    @property
    def dropped_event_count(self) -> int:
        with self._dropped_lock:
            return self._dropped

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Enqueue an event for asynchronous write. Non-blocking.

        If the queue is full, the OLDEST pending event is dropped (so the most
        recent event still makes it to disk) and `dropped_event_count` ticks.
        """
        if event_type not in EVENT_TYPES:
            # We don't raise — bad event types should not crash a live demo.
            # We do record the violation in the payload so it's debuggable.
            payload = dict(payload or {})
            payload.setdefault("_unknown_event_type", event_type)
            event_type = "session_end"  # safest fallback; surfaces in audit log
        now = time.time()
        record = {
            "schema_version": SCHEMA_VERSION,
            "session_id": self._session_id,
            "timestamp": now,
            "wall_clock_iso": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "event_type": event_type,
            "source": self._source,
            "payload": dict(payload or {}),
        }
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            # Drop oldest, push newest. We never block the producer.
            try:
                self._queue.get_nowait()
                with self._dropped_lock:
                    self._dropped += 1
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(record)
            except queue.Full:
                # Extreme contention: drop the new event rather than block.
                with self._dropped_lock:
                    self._dropped += 1

    def close(self, timeout: float = 5.0) -> None:
        """Flush queue and stop writer thread. Safe to call multiple times."""
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        try:
            self._queue.put_nowait(None)  # sentinel to wake writer
        except queue.Full:
            pass  # writer will see _stop_event regardless
        self._writer_thread.join(timeout=timeout)

    def _writer_loop(self) -> None:
        # Open append-mode so multiple sessions can coexist; live viewer chooses
        # a unique path per session.
        with self._output_path.open("a", encoding="utf-8", buffering=1) as fp:
            while True:
                try:
                    record = self._queue.get(timeout=0.1)
                except queue.Empty:
                    if self._stop_event.is_set():
                        break
                    continue
                if record is None:
                    # Drain anything remaining before exiting.
                    while True:
                        try:
                            extra = self._queue.get_nowait()
                        except queue.Empty:
                            break
                        if extra is None:
                            continue
                        fp.write(json.dumps(extra, ensure_ascii=False) + "\n")
                    break
                fp.write(json.dumps(record, ensure_ascii=False) + "\n")


def validate_event_record(record: dict[str, Any]) -> None:
    """Raise ValueError if a JSONL record violates the schema. Test-helper."""
    for key in _REQUIRED_KEYS:
        if key not in record:
            raise ValueError(f"event record missing required key: {key!r}")
    if record["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"unexpected schema_version: {record['schema_version']!r}")
    if not isinstance(record["payload"], dict):
        raise ValueError("payload must be a dict")
    if not isinstance(record["timestamp"], (int, float)):
        raise ValueError("timestamp must be numeric")
