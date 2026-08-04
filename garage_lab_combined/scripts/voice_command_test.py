"""
Standalone voice recognition test for BLM commands.

Uses colleague's Vosk model + venv (no install needed on Project_Cam).
Listens on default mic, prints recognized commands. No BLM / network side effects.

Run:
    PROJECT_CAM_VOSK_MODEL="$HOME/Desktop/Speech to text/model" \\
    /path/to/voice-venv/bin/python garage_lab_combined/scripts/voice_command_test.py

Stop: Ctrl+C.

Joint mapping to COCO names used by blm_follow.py:
    head          -> nose
    left_foot     -> left_ankle
    right_foot    -> right_ankle
    left/right knee/shoulder -> same
    go            -> shoot
"""

import json
import os
import sys
import time
from pathlib import Path

import pyaudio
from vosk import Model, KaldiRecognizer

MODEL_PATH = os.environ.get("PROJECT_CAM_VOSK_MODEL", str(Path.home() / "Desktop" / "Speech to text" / "model"))
SAMPLE_RATE = 16000

VOICE_TO_JOINT = {
    "head": "nose",
    "left foot": "left_ankle",
    "right foot": "right_ankle",
    "left knee": "left_knee",
    "right knee": "right_knee",
    "left shoulder": "left_shoulder",
    "right shoulder": "right_shoulder",
    "left hip": "left_hip",
    "right hip": "right_hip",
}

VOICE_TO_ACTION = {
    "go": "shoot",
    "shoot": "shoot",
    "reload": "reload",
    "stop": "pause",
    "pause": "pause",
    "resume": "resume",
    "quit": "quit",
}

GRAMMAR = list(VOICE_TO_JOINT.keys()) + list(VOICE_TO_ACTION.keys()) + ["[unk]"]
COOLDOWN_SECONDS = 1.0


def main():
    if not Path(MODEL_PATH).exists():
        print(f"[ERR] Vosk model not found at {MODEL_PATH}", file=sys.stderr)
        sys.exit(1)

    model = Model(MODEL_PATH)
    rec = KaldiRecognizer(model, SAMPLE_RATE, json.dumps(GRAMMAR))

    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
        input=True, frames_per_buffer=4000,
    )
    stream.start_stream()

    print(">>> Voice test running. Say commands:")
    print(f"    Joints: {', '.join(VOICE_TO_JOINT.keys())}")
    print(f"    Actions: {', '.join(VOICE_TO_ACTION.keys())}")
    print("    Ctrl+C to stop.\n")

    last_cmd_time = 0.0
    last_cmd = None

    try:
        while True:
            data = stream.read(2000, exception_on_overflow=False)
            if not rec.AcceptWaveform(data):
                continue
            text = json.loads(rec.Result()).get("text", "").strip()
            if not text or text == "[unk]":
                continue

            now = time.time()
            if text == last_cmd and (now - last_cmd_time) < COOLDOWN_SECONDS:
                continue
            last_cmd = text
            last_cmd_time = now

            if text in VOICE_TO_JOINT:
                print(f"[JOINT]  '{text}' -> {VOICE_TO_JOINT[text]}")
            elif text in VOICE_TO_ACTION:
                print(f"[ACTION] '{text}' -> {VOICE_TO_ACTION[text]}")
            else:
                print(f"[HEARD]  '{text}' (no mapping)")
    except KeyboardInterrupt:
        print("\n[EXIT] stopping...")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


if __name__ == "__main__":
    main()
