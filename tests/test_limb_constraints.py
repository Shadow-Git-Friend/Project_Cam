"""Segment-length prior calibration + rejection for leg-raise tracking."""

import numpy as np

from project_cam.assessment.live_trainer.limb_constraints import (
    accept_by_segment_prior,
    calibrate_segment_lengths,
    segment_length,
    segment_length_error,
)


def _triples(thigh, shin, n):
    hip = np.array([0.0, 0.0, 500.0])
    knee = hip + np.array([0.0, float(thigh), 0.0])
    ankle = knee + np.array([0.0, float(shin), 0.0])
    return [(hip, knee, ankle) for _ in range(n)]


def test_segment_length_basic():
    assert segment_length([0, 0, 0], [0, 0, 400]) == 400.0
    assert segment_length(None, [0, 0, 0]) is None


def test_calibrate_estimates_lengths():
    prior = calibrate_segment_lengths(_triples(400, 380, 10))
    assert prior is not None
    assert prior.reliable
    assert abs(prior.thigh_mm - 400) < 1e-6
    assert abs(prior.shin_mm - 380) < 1e-6
    assert prior.samples == 10


def test_calibrate_too_few_samples_is_unreliable():
    prior = calibrate_segment_lengths(_triples(400, 400, 3))
    assert prior is not None
    assert not prior.reliable


def test_calibrate_returns_none_without_complete_triples():
    assert calibrate_segment_lengths([(None, None, None)]) is None


def test_segment_error_flags_impossible_geometry():
    prior = calibrate_segment_lengths(_triples(400, 400, 8))
    hip = np.array([0.0, 0.0, 500.0])
    knee = hip + np.array([0.0, 400.0, 0.0])
    bad_ankle = knee + np.array([0.0, 700.0, 0.0])  # shin 700 vs prior 400 -> +75 %
    err = segment_length_error(prior, hip, knee, bad_ankle)
    assert err > 0.25
    assert accept_by_segment_prior(prior, hip, knee, bad_ankle) is False


def test_accept_within_tolerance():
    prior = calibrate_segment_lengths(_triples(400, 400, 8))
    hip = np.array([0.0, 0.0, 500.0])
    knee = hip + np.array([0.0, 410.0, 0.0])      # +2.5 %
    ankle = knee + np.array([0.0, 380.0, 0.0])    # -5 %
    assert accept_by_segment_prior(prior, hip, knee, ankle) is True


def test_no_prior_never_rejects():
    hip = np.array([0.0, 0.0, 500.0])
    knee = np.array([9999.0, 0.0, 0.0])
    ankle = np.array([-9999.0, 0.0, 0.0])
    assert accept_by_segment_prior(None, hip, knee, ankle) is True
