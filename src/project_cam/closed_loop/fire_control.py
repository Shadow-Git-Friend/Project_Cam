"""One-shot fire authorization at the serial command boundary.

The helpers in this module own no sockets or hardware.  They capture the exact
aim that was sent to a launcher, then re-evaluate the latest all-person safety
snapshot immediately before a caller is allowed to transmit ``shoot``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .firing_line import FiringLineDecision, evaluate_shot_clearance


@dataclass(frozen=True)
class ArmedShotContext:
    """Immutable geometry and primary epoch captured for one commanded aim."""

    target_xyz_mm: tuple[float, float, float]
    pitch_deg: float
    yaw_deg: float
    speed_mps: float
    primary_track_id: int
    primary_epoch: int
    y_mirrored: bool
    aim_timestamp: float

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON-safe audit representation."""

        return {
            "target_xyz_mm": list(self.target_xyz_mm),
            "pitch_deg": self.pitch_deg,
            "yaw_deg": self.yaw_deg,
            "speed_mps": self.speed_mps,
            "primary_track_id": self.primary_track_id,
            "primary_epoch": self.primary_epoch,
            "y_mirrored": self.y_mirrored,
            "aim_timestamp": self.aim_timestamp,
        }


def arm_shot_context(
    snapshot: dict[str, Any] | None,
    *,
    target_xyz_mm: Iterable[float],
    pitch_deg: float,
    yaw_deg: float,
    speed_mps: float,
    launcher_xyz_mm: Iterable[float],
    launcher_yaw_deg: float,
    now: float | None = None,
    **clearance_kwargs: Any,
) -> tuple[ArmedShotContext | None, FiringLineDecision]:
    """Authorize and capture one actual aim, returning no context on a block."""

    aim_time = time.time() if now is None else now
    primary_track_id = snapshot.get("primary_track_id") if isinstance(snapshot, dict) else None
    primary_epoch = snapshot.get("primary_epoch") if isinstance(snapshot, dict) else None
    y_mirrored = snapshot.get("y_mirrored") if isinstance(snapshot, dict) else None
    decision = evaluate_shot_clearance(
        snapshot,
        launcher_xyz_mm=launcher_xyz_mm,
        launcher_yaw_deg=launcher_yaw_deg,
        pitch_deg=pitch_deg,
        yaw_deg=yaw_deg,
        speed_mps=speed_mps,
        target_xyz_mm=target_xyz_mm,
        expected_primary_track_id=primary_track_id,
        expected_primary_epoch=primary_epoch,
        expected_y_mirrored=y_mirrored,
        now=aim_time,
        **clearance_kwargs,
    )
    if not decision.ok:
        return None, decision

    target = tuple(float(value) for value in target_xyz_mm)
    context = ArmedShotContext(
        target_xyz_mm=(target[0], target[1], target[2]),
        pitch_deg=float(pitch_deg),
        yaw_deg=float(yaw_deg),
        speed_mps=float(speed_mps),
        primary_track_id=int(primary_track_id),
        primary_epoch=int(primary_epoch),
        y_mirrored=bool(y_mirrored),
        aim_timestamp=float(aim_time),
    )
    return context, decision


def _base_outcome(
    *,
    source: str,
    requested_at: float,
    shoot_enabled: bool,
    armed_context: ArmedShotContext | None,
) -> dict[str, Any]:
    return {
        "source": str(source),
        "requested_at": float(requested_at),
        "shoot_enabled": bool(shoot_enabled),
        "serial_shoot_sent": False,
        "stop_command_sent": False,
        "stop_error": None,
        "reason": None,
        "message": None,
        "decision": None,
        "armed_context": armed_context.to_dict() if isinstance(armed_context, ArmedShotContext) else None,
    }


def _best_effort_stop(
    send_command: Callable[[str], None], outcome: dict[str, Any]
) -> None:
    try:
        send_command("stop")
        outcome["stop_command_sent"] = True
    except Exception as exc:  # serial containment must never turn a block into fire
        outcome["stop_error"] = f"{type(exc).__name__}: {exc}"


def request_shoot(
    send_command: Callable[[str], None],
    *,
    shoot_enabled: bool,
    latest_snapshot: dict[str, Any] | None,
    armed_context: ArmedShotContext | None,
    launcher_xyz_mm: Iterable[float],
    launcher_yaw_deg: float,
    source: str,
    now: float | None = None,
    **clearance_kwargs: Any,
) -> dict[str, Any]:
    """Re-evaluate clearance and transmit exactly one ``shoot`` only if clear.

    The returned dictionary is JSON-safe.  Any blocked request that may have an
    armed launcher (shoot mode enabled or a context exists) attempts ``stop``;
    that containment write is deliberately best-effort.
    """

    requested_at = time.time() if now is None else now
    valid_context = armed_context if isinstance(armed_context, ArmedShotContext) else None
    outcome = _base_outcome(
        source=source,
        requested_at=requested_at,
        shoot_enabled=shoot_enabled,
        armed_context=valid_context,
    )

    if not shoot_enabled:
        outcome["reason"] = "shoot_disabled"
        outcome["message"] = "shooting is disabled"
    elif valid_context is None:
        outcome["reason"] = (
            "aim_context_missing" if armed_context is None else "aim_context_invalid"
        )
        outcome["message"] = "a fresh armed aim context is required"
    else:
        decision = evaluate_shot_clearance(
            latest_snapshot,
            launcher_xyz_mm=launcher_xyz_mm,
            launcher_yaw_deg=launcher_yaw_deg,
            pitch_deg=valid_context.pitch_deg,
            yaw_deg=valid_context.yaw_deg,
            speed_mps=valid_context.speed_mps,
            target_xyz_mm=valid_context.target_xyz_mm,
            expected_primary_track_id=valid_context.primary_track_id,
            expected_primary_epoch=valid_context.primary_epoch,
            expected_y_mirrored=valid_context.y_mirrored,
            now=requested_at,
            **clearance_kwargs,
        )
        outcome["decision"] = decision.to_dict()
        outcome["reason"] = decision.reason
        outcome["message"] = decision.message
        if decision.ok:
            try:
                send_command("shoot")
            except Exception as exc:
                outcome["reason"] = "shoot_command_failed"
                outcome["message"] = "serial shoot command failed"
                outcome["shoot_error"] = f"{type(exc).__name__}: {exc}"
                _best_effort_stop(send_command, outcome)
                return outcome
            outcome["serial_shoot_sent"] = True
            return outcome

    if bool(shoot_enabled) or armed_context is not None:
        _best_effort_stop(send_command, outcome)
    return outcome


__all__ = ["ArmedShotContext", "arm_shot_context", "request_shoot"]
