"""Contact-aware 3D skeleton interpretation."""

import json

import numpy as np

from project_cam.assessment.joints import JOINT_NAME_TO_INDEX, JOINT_NAMES
from project_cam.assessment.live_trainer.contact_interpreter import (
    ContactAwarePoseInterpreter,
    ContactInterpretationConfig,
    interpret_contact,
)


def _frame(idx=0, *, time_s=0.0, joints_by_name=None, conf=1.0, cams=3):
    joints = [None] * len(JOINT_NAMES)
    confs = [float(conf)] * len(JOINT_NAMES)
    cam_counts = [int(cams)] * len(JOINT_NAMES)
    for name, point in (joints_by_name or {}).items():
        joints[JOINT_NAME_TO_INDEX[name]] = list(np.asarray(point, dtype=float))
    return {
        "frame_index": idx,
        "time_s": time_s,
        "joints": joints,
        "joint_conf": confs,
        "joint_cams": cam_counts,
    }


def test_interpret_contact_finds_support_contacts_and_proxy_com():
    frame = _frame(joints_by_name={
        "left_shoulder": [-220.0, 0.0, 500.0],
        "right_shoulder": [220.0, 0.0, 500.0],
        "left_hip": [-160.0, 420.0, 500.0],
        "right_hip": [160.0, 420.0, 500.0],
        "left_knee": [-160.0, 820.0, 500.0],
        "left_ankle": [-160.0, 1220.0, 500.0],
        "right_knee": [160.0, 820.0, 650.0],
        "right_ankle": [160.0, 1220.0, 920.0],
    })

    result = interpret_contact(frame, ContactInterpretationConfig(
        contact_tolerance_mm=60.0,
        support_z_mm=None,
    ))

    contact_names = {point.name for point in result.contacts}
    assert "left_hip" in contact_names
    assert "left_ankle" in contact_names
    assert "right_ankle" not in contact_names
    assert result.support_status == "supported"
    assert result.proxy_com_xyz_mm == [0.0, 210.0, 500.0]
    assert result.support_center_xy_mm is not None
    assert result.com_to_support_xy_mm is not None


def test_interpret_contact_flags_no_support_against_fixed_plane():
    frame = _frame(joints_by_name={
        "left_hip": [-100.0, 0.0, 500.0],
        "right_hip": [100.0, 0.0, 500.0],
        "left_ankle": [-100.0, 800.0, 500.0],
        "right_ankle": [100.0, 800.0, 500.0],
    })

    result = interpret_contact(frame, ContactInterpretationConfig(
        support_z_mm=0.0,
        contact_tolerance_mm=40.0,
    ))

    assert result.support_status == "unsupported"
    assert result.contacts == []
    assert "no_support_contacts" in result.flags


def test_stateful_interpreter_reports_static_raised_distal_joint():
    cfg = ContactInterpretationConfig(
        support_z_mm=500.0,
        contact_tolerance_mm=60.0,
        static_raise_mm=250.0,
        static_velocity_mm_s=25.0,
    )
    interpreter = ContactAwarePoseInterpreter(cfg)
    points = {
        "left_hip": [-120.0, 0.0, 500.0],
        "right_hip": [120.0, 0.0, 500.0],
        "left_ankle": [-120.0, 800.0, 500.0],
        "right_ankle": [120.0, 800.0, 900.0],
    }

    interpreter.process(_frame(0, time_s=0.0, joints_by_name=points))
    result = interpreter.process(_frame(1, time_s=0.1, joints_by_name=points))

    assert result.raised_static_joints == ["right_ankle"]
    assert "static_raised_joint" in result.flags


def test_contact_result_is_json_ready():
    frame = _frame(joints_by_name={
        "left_hip": [-100.0, 0.0, 500.0],
        "right_hip": [100.0, 0.0, 500.0],
    })

    payload = interpret_contact(frame).to_dict()

    assert payload["frame_index"] == 0
    json.dumps(payload, ensure_ascii=True)
