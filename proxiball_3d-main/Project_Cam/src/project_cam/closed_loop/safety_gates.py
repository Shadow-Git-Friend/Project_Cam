"""Pure-function safety gates for BLM target acquisition.

The launcher runtimes (`launcher_runtime_from_udp.py`, `blm_follow.py`) decide
whether to act on a UDP joint sample. Those decisions used to be inline and
hard to unit-test because the surrounding code requires serial ports and
threads. These helpers extract the predicates so tests can drive them with
plain dicts.

The functions are stateless and side-effect-free. Callers wire them into
their main loops and forward `BLOCKED` results to the EventLogger / decision
log for audit.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GateResult:
    """Outcome of evaluating a joint sample against the safety gates.

    `ok` is True only when EVERY gate passes. When False, `reason` is a short
    machine-readable code (e.g. "low_confidence", "low_camera_count", "stale")
    and `message` is a human-readable detail string useful in logs.
    """

    ok: bool
    reason: str | None
    message: str | None
    detail: dict[str, Any]


def evaluate_joint_gate(
    joint_data: dict[str, Any] | None,
    *,
    min_confidence: float,
    min_cameras: int,
    max_staleness_s: float,
    now: float | None = None,
) -> GateResult:
    """Decide whether a UDP joint sample is fresh and trustworthy enough to act on.

    `joint_data` is expected to have keys `conf`, `cams`, `ts` (Unix seconds).
    Missing data is treated as a `missing` failure. The function never raises.

    The order of checks is intentional: missing → stale → cameras → confidence.
    That order surfaces the most diagnostic failure first when multiple gates
    would have blocked the sample.
    """
    if joint_data is None:
        return GateResult(
            ok=False,
            reason="missing",
            message="no joint sample available",
            detail={},
        )

    if now is None:
        now = time.time()

    ts = joint_data.get("ts")
    if ts is None:
        return GateResult(
            ok=False,
            reason="missing",
            message="joint sample has no timestamp",
            detail={"keys_present": sorted(joint_data.keys())},
        )

    age_s = float(now) - float(ts)
    if max_staleness_s > 0 and age_s > max_staleness_s:
        return GateResult(
            ok=False,
            reason="stale",
            message=f"sample age {age_s:.2f}s exceeds max_staleness_s={max_staleness_s:.2f}s",
            detail={"age_s": age_s, "max_staleness_s": max_staleness_s},
        )

    cams = int(joint_data.get("cams", 0) or 0)
    if min_cameras > 0 and cams < min_cameras:
        return GateResult(
            ok=False,
            reason="low_camera_count",
            message=f"cameras={cams} below min_cameras={min_cameras}",
            detail={"cams": cams, "min_cameras": min_cameras},
        )

    conf_raw = joint_data.get("conf")
    try:
        conf = float(conf_raw) if conf_raw is not None else 0.0
    except (TypeError, ValueError):
        conf = 0.0
    if min_confidence > 0 and conf < min_confidence:
        return GateResult(
            ok=False,
            reason="low_confidence",
            message=f"conf={conf:.3f} below min_confidence={min_confidence:.3f}",
            detail={"conf": conf, "min_confidence": min_confidence},
        )

    return GateResult(
        ok=True,
        reason=None,
        message=None,
        detail={"age_s": age_s, "cams": cams, "conf": conf},
    )
