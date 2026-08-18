#!/usr/bin/env python3
"""Deterministic software evidence for the control_15 PI hypothesis.

This is deliberately a small first-order plant, not a hardware substitute.  It
uses the firmware's feed-forward maps, PI gains, trim/PWM limits, and actuator
ramp, then adds fixed per-wheel disturbances that are smaller than the measured
109 RPM worst case.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

SAMPLE_S = 0.2
RAMP_STEP_US = 5.0
LEFT_SLOPE = 0.1763
LEFT_OFFSET = 1101
RIGHT_SLOPE = 0.1670
RIGHT_OFFSET = 1088
KP = 0.12
KI = 0.08
MAX_TRIM_US = 30.0
PWM_MIN_US = 1000.0
PWM_MAX_US = 1800.0
OVERSPEED_RPM = 1300.0
PLANT_TAU_S = 0.8
LEFT_DISTURBANCE_RPM = -60.0
RIGHT_DISTURBANCE_RPM = 70.0


@dataclass(frozen=True)
class WheelResult:
    final_rpm: float
    max_rpm: float
    min_pwm: float
    max_pwm: float
    max_abs_trim_us: float
    integrated_while_ramping: int


@dataclass(frozen=True)
class PairResult:
    left: WheelResult
    right: WheelResult


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _simulate_wheel(
    *,
    target_rpm: float,
    closed_loop: bool,
    duration_s: float,
    slope: float,
    offset: int,
    disturbance_rpm: float,
) -> WheelResult:
    base_pwm = float(int(target_rpm * slope + offset))
    current_pwm = PWM_MIN_US
    desired_pwm = _clamp(base_pwm, PWM_MIN_US, PWM_MAX_US)
    measured_rpm = 0.0
    integral_us = 0.0
    trim_us = 0.0
    max_rpm = 0.0
    min_pwm = current_pwm
    max_pwm = current_pwm
    max_abs_trim = 0.0
    integrated_while_ramping = 0

    steps = round(duration_s / SAMPLE_S)
    for _ in range(steps):
        if closed_loop:
            error_rpm = target_rpm - measured_rpm
            proportional_us = KP * error_rpm
            ramp_caught = abs(desired_pwm - current_pwm) <= RAMP_STEP_US
            before_integral = integral_us
            if ramp_caught:
                candidate_integral = _clamp(
                    integral_us + KI * error_rpm * SAMPLE_S,
                    -MAX_TRIM_US,
                    MAX_TRIM_US,
                )
                candidate_trim = proportional_us + candidate_integral
                candidate_pwm = base_pwm + candidate_trim
                pushes_high = candidate_trim > MAX_TRIM_US and error_rpm > 0.0
                pushes_low = candidate_trim < -MAX_TRIM_US and error_rpm < 0.0
                pushes_pwm_high = candidate_pwm > PWM_MAX_US and error_rpm > 0.0
                pushes_pwm_low = candidate_pwm < PWM_MIN_US and error_rpm < 0.0
                if not (
                    pushes_high or pushes_low or pushes_pwm_high or pushes_pwm_low
                ):
                    integral_us = candidate_integral
            if not ramp_caught and integral_us != before_integral:
                integrated_while_ramping += 1
            trim_us = _clamp(
                proportional_us + integral_us, -MAX_TRIM_US, MAX_TRIM_US
            )
        else:
            trim_us = 0.0

        desired_pwm = _clamp(base_pwm + round(trim_us), PWM_MIN_US, PWM_MAX_US)
        pwm_delta = _clamp(
            desired_pwm - current_pwm, -RAMP_STEP_US, RAMP_STEP_US
        )
        current_pwm += pwm_delta

        steady_rpm = max(
            0.0, (current_pwm - offset) / slope + disturbance_rpm
        )
        measured_rpm += (steady_rpm - measured_rpm) * (SAMPLE_S / PLANT_TAU_S)

        max_rpm = max(max_rpm, measured_rpm)
        min_pwm = min(min_pwm, current_pwm)
        max_pwm = max(max_pwm, current_pwm)
        max_abs_trim = max(max_abs_trim, abs(trim_us))

    return WheelResult(
        final_rpm=measured_rpm,
        max_rpm=max_rpm,
        min_pwm=min_pwm,
        max_pwm=max_pwm,
        max_abs_trim_us=max_abs_trim,
        integrated_while_ramping=integrated_while_ramping,
    )


def simulate_pair(
    *, target_rpm: float, closed_loop: bool, duration_s: float
) -> PairResult:
    if not 200.0 <= target_rpm <= 1200.0:
        raise ValueError("target_rpm must be inside the controller range 200..1200")
    if duration_s <= 0.0:
        raise ValueError("duration_s must be positive")
    return PairResult(
        left=_simulate_wheel(
            target_rpm=target_rpm,
            closed_loop=closed_loop,
            duration_s=duration_s,
            slope=LEFT_SLOPE,
            offset=LEFT_OFFSET,
            disturbance_rpm=LEFT_DISTURBANCE_RPM,
        ),
        right=_simulate_wheel(
            target_rpm=target_rpm,
            closed_loop=closed_loop,
            duration_s=duration_s,
            slope=RIGHT_SLOPE,
            offset=RIGHT_OFFSET,
            disturbance_rpm=RIGHT_DISTURBANCE_RPM,
        ),
    )


def _summary(label: str, result: PairResult) -> str:
    return (
        f"{label}: "
        f"L={result.left.final_rpm:.2f} RPM "
        f"R={result.right.final_rpm:.2f} RPM "
        f"trim_max={max(result.left.max_abs_trim_us, result.right.max_abs_trim_us):.2f} us "
        f"pwm={min(result.left.min_pwm, result.right.min_pwm):.0f}.."
        f"{max(result.left.max_pwm, result.right.max_pwm):.0f} us "
        f"integrated_while_ramping="
        f"{result.left.integrated_while_ramping}/"
        f"{result.right.integrated_while_ramping}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-rpm", type=float, default=500.0)
    args = parser.parse_args()
    open_loop = simulate_pair(
        target_rpm=args.target_rpm, closed_loop=False, duration_s=35.0
    )
    closed_loop = simulate_pair(
        target_rpm=args.target_rpm, closed_loop=True, duration_s=45.0
    )
    print(_summary("feed-forward", open_loop))
    print(_summary("closed-loop", closed_loop))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
