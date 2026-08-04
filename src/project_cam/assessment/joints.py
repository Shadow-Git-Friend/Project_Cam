"""COCO-17 joint naming used by the Project_Cam pose pipeline."""

JOINT_NAMES = [
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
]

JOINT_NAME_TO_INDEX = {name: idx for idx, name in enumerate(JOINT_NAMES)}
JOINT_INDEX_TO_NAME = {idx: name for idx, name in enumerate(JOINT_NAMES)}

LEFT_RIGHT_PAIRS = [
    ("shoulder", "left_shoulder", "right_shoulder"),
    ("elbow", "left_elbow", "right_elbow"),
    ("wrist", "left_wrist", "right_wrist"),
    ("hip", "left_hip", "right_hip"),
    ("knee", "left_knee", "right_knee"),
    ("ankle", "left_ankle", "right_ankle"),
]

ALL_UDP_TARGET_JOINTS = ",".join(JOINT_NAMES)


def empty_joint_list():
    return [None] * len(JOINT_NAMES)


def joint_index(name):
    try:
        return JOINT_NAME_TO_INDEX[name]
    except KeyError as exc:
        raise KeyError(f"Unknown COCO-17 joint name: {name}") from exc

