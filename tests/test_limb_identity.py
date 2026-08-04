"""Left/right leg identity lock under crossing and noisy tracks."""

from project_cam.assessment.live_trainer.limb_identity import (
    LegPose,
    LimbIdentityTracker,
)


def _leg(x, z=200.0):
    return LegPose.of(ankle=[x, 0.0, z])


def test_cold_start_trusts_labels():
    t = LimbIdentityTracker()
    r = t.resolve(_leg(-100), _leg(100))
    assert r.status == "cold_start"
    assert r.swapped is False
    assert r.left.ankle[0] == -100


def test_corrects_label_swap():
    t = LimbIdentityTracker(swap_margin_mm=80.0)
    t.resolve(_leg(-100), _leg(100))            # seed: left on -x, right on +x
    # Pose model swaps labels: "left" now reports the +x leg, "right" the -x leg.
    r = t.resolve(_leg(100), _leg(-100))
    assert r.swapped is True
    assert r.left.ankle[0] == -100               # identity restored to history
    assert r.right.ankle[0] == 100
    assert t.swap_count == 1


def test_resists_small_jitter():
    t = LimbIdentityTracker(swap_margin_mm=80.0)
    t.resolve(_leg(-100), _leg(100))
    for dx in (5, -4, 6, -3, 2):
        r = t.resolve(_leg(-100 + dx), _leg(100 - dx))
        assert r.swapped is False
    assert t.swap_count == 0


def test_locks_after_consistent_frames():
    t = LimbIdentityTracker(lock_after=3)
    t.resolve(_leg(-100), _leg(100))
    t.resolve(_leg(-100), _leg(100))
    t.resolve(_leg(-100), _leg(100))
    r = t.resolve(_leg(-100), _leg(100))
    assert r.status == "locked"


def test_missing_joint_does_not_force_swap():
    t = LimbIdentityTracker()
    t.resolve(_leg(-100), _leg(100))
    # right leg drops out entirely this frame; identity must hold for the left.
    r = t.resolve(_leg(-100), LegPose())
    assert r.swapped is False
    assert r.left.ankle[0] == -100
