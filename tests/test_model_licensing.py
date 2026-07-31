"""Licence policy guards for the model registry.

Why this file exists: on 2026-07-30 the project discovered that its declared
escape from Ultralytics' AGPL — the MMPose pose backend — was itself unusable
commercially, because every published RTMPose checkpoint is pretrained on AI
Challenger (research-only). The repository badge said Apache-2.0 and was
truthful about the *code*; nothing recorded the *training data*.

Nothing in the suite could have caught that, because `configs/models.yaml` had no
licence fields at all. These tests make the three-layer audit a property the
suite enforces rather than a note someone remembered to write.
"""

from __future__ import annotations

import pytest

from project_cam.models.registry import (
    COMMERCIAL_VERDICTS,
    Licensing,
    ModelRecord,
    load_model_registry,
    non_commercial_markers,
)


@pytest.fixture(scope="module")
def registry():
    return load_model_registry()


# --------------------------------------------------------------- marker detection


def test_the_ai_challenger_pretraining_tag_is_detected():
    """`pt-aic-coco` is the exact string that hid the blocker for three months.

    It is not the word "AI Challenger" and it is not a licence name — it is a
    checkpoint filename fragment. Anything auditing licences by reading licence
    fields alone would miss it, so the marker set has to cover data tags too.
    """
    found = non_commercial_markers(
        "pretrained on pt-aic-coco then fine-tuned on COCO"
    )
    assert "aic" in found


@pytest.mark.parametrize(
    "text, expected",
    [
        ("AGPL-3.0 (Ultralytics)", "agpl"),
        ("trained on MPII", "mpii"),
        ("CrowdPose split", "crowdpose"),
        ("body7 merged dataset", "body7"),
        ("SMPL body model", "smpl"),
        ("CC-BY-NC-4.0", "cc-by-nc"),
        ("research-only licence", "research-only"),
        ("AI-Challenger keypoints", "ai-challenger"),
    ],
)
def test_known_non_commercial_markers_are_detected(text, expected):
    assert expected in non_commercial_markers(text)


@pytest.mark.parametrize(
    "innocent",
    [
        "trained with mosaic augmentation",
        "Jamaica field trial footage",
        "COCO person keypoints (CC-BY-4.0)",
        "Apache-2.0",
        "somebody78 wrote this",
    ],
)
def test_marker_matching_does_not_fire_on_innocent_text(innocent):
    """Word-boundary matching, not substring.

    `aic` inside `mosaic` and `body78` inside `somebody78` would both be false
    positives, and a licence guard that cries wolf gets switched off. Note
    CC-BY-4.0 must NOT match the CC-BY-NC pattern — one is commercial-friendly,
    the other is not, and they differ by two characters.
    """
    assert non_commercial_markers(innocent) == []


def test_absence_of_markers_is_not_a_clean_verdict():
    """An unrecognised licence name is unverified, never clear.

    The marker list only knows the traps found so far. Treating "no marker" as
    "clean" would make every unknown licence silently permissive — the opposite
    of the intended default.
    """
    licence = Licensing(code="Some Bespoke Vendor Licence v3")
    assert non_commercial_markers(licence.code) == []
    assert licence.commercial_use == "undeclared"


# ------------------------------------------------------------ verdict consistency


def test_clear_verdict_cannot_contradict_a_detected_marker():
    """The verdict is checked against the layers, so the two cannot disagree.

    Without this, a copy-paste of a `clear` verdict onto an AGPL row would sit in
    the registry looking authoritative.
    """
    with pytest.raises(ValueError, match="contradicts non-commercial markers"):
        Licensing(
            code="AGPL-3.0",
            weights="AGPL-3.0",
            training_data="COCO",
            commercial_use="clear",
        )


def test_a_marker_in_the_training_data_layer_alone_blocks_a_clear_verdict():
    """Specifically the RTMPose shape: permissive code, permissive weights claim,
    contaminated data. This is the case the old registry could not express."""
    with pytest.raises(ValueError, match="contradicts"):
        Licensing(
            code="Apache-2.0",
            weights="Apache-2.0",
            training_data="pretrained on pt-aic-coco",
            commercial_use="clear",
        )


def test_unknown_verdict_is_rejected():
    with pytest.raises(ValueError, match="commercial_use must be one of"):
        Licensing(commercial_use="probably fine")


def test_default_verdict_is_undeclared_not_clear():
    """A record that says nothing must read as a gap, never as permission."""
    assert Licensing().commercial_use == "undeclared"
    assert "undeclared" in COMMERCIAL_VERDICTS


# --------------------------------------------------------------- registry policy


def test_every_active_model_declares_all_three_licence_layers(registry):
    """The guard. An active artifact with a blank layer is an unaudited artifact."""
    gaps = {
        model.model_id: model.licensing.undeclared_layers()
        for model in registry.active_models()
        if model.licensing.undeclared_layers()
    }
    assert gaps == {}, f"active models with undeclared licence layers: {gaps}"


def test_every_active_model_records_where_its_verdict_was_checked(registry):
    """`evidence` is what makes a verdict re-checkable by someone else.

    A verdict without a config path, licence file or vendor statement behind it
    is an opinion.
    """
    missing = [
        model.model_id
        for model in registry.active_models()
        if not model.licensing.evidence
    ]
    assert missing == [], f"active models with no licence evidence: {missing}"


def test_undeclared_licensing_counts_as_a_commercial_blocker():
    """Not-audited and not-clean must land in the same bucket."""
    record = ModelRecord.from_dict(
        {
            "model_id": "silent",
            "task": "pose_estimation",
            "version": "1",
            "backend": "pytorch",
            "artifact_format": "pt",
            "path": "nowhere.pt",
            "input_size": [1, 1],
            "status": "active",
        }
    )
    assert record.licensing.commercial_use == "undeclared"
    assert record.licensing.undeclared_layers() == ["code", "weights", "training_data"]


def test_licensing_reaches_the_api_payload(registry):
    """The field has to be in `to_dict()`, otherwise the audit is invisible to
    `GET /v1/models` and only exists for whoever opens the YAML."""
    payload = registry.to_dict()
    for record in payload["models"]:
        assert "licensing" in record
        licence = record["licensing"]
        assert licence["commercial_use"] in COMMERCIAL_VERDICTS
        assert "undeclared_layers" in licence
        assert "detected_markers" in licence


# ------------------------------------------------------------------- the ledger


def test_the_current_commercial_blockers_are_the_known_set(registry):
    """Characterization ledger, deliberately exact.

    Every active model is currently blocked or unverified — zero are clear. That
    is the real state, and pinning it means clearing one is a deliberate edit to
    this list rather than a silent drift. If this test fails because a blocker
    was FIXED, update it and say so in the log.
    """
    blocked = {row["model_id"]: row["commercial_use"] for row in registry.commercial_blockers()}
    assert blocked == {
        "ball_yolo26m_672_trt": "blocked",
        "pose_yolo11m_trt": "blocked",
        "face_detect_yunet_2023mar": "unverified",
        "face_recognize_sface_2021dec": "unverified",
    }


def test_no_active_model_is_yet_cleared_for_commercial_use(registry):
    """States the uncomfortable fact directly rather than leaving it implicit in
    a table: the shipping pipeline has no commercially cleared model."""
    cleared = [
        m.model_id
        for m in registry.active_models()
        if m.licensing.commercial_use == "clear"
    ]
    assert cleared == [], (
        "a model became commercially clear — good, but update the ledger tests "
        f"and the plan: {cleared}"
    )


def test_the_contaminated_rtmpose_path_stays_registered_and_blocked(registry):
    """Keep the blocker visible.

    Deleting this row would remove the only machine-readable record that
    `--pose-backend mmpose` is not the escape route, and the next person would
    rediscover it the hard way.
    """
    record = registry.get("pose_rtmpose_m_mmpose")
    assert record.licensing.commercial_use == "blocked"
    assert record.licensing.blocker == "ai-challenger-research-only"
    assert "aic" in record.licensing.detected_markers()
    assert record.status == "deprecated"


def test_the_clean_pose_target_is_recorded_with_its_evidence(registry):
    """RTMO is the verified replacement; the verdict must carry the config path it
    was read from, because the model-zoo table alone is misleading here (the coco
    metafile lists CrowdPose as an evaluation row)."""
    record = registry.get("pose_rtmo_m_coco")
    assert record.licensing.commercial_use == "clear"
    assert record.licensing.detected_markers() == []
    assert "rtmo-s_8xb32-600e_coco-640x640.py" in record.licensing.evidence
    assert record.status == "candidate", "RTMO is not exported or benchmarked yet"
