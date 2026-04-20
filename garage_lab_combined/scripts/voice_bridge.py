"""
Voice -> BLM bridge.

Listens to mic via Vosk, maps spoken commands to blm_follow.py semantics, and
sends each command as a UTF-8 UDP packet to 127.0.0.1:<port>.

Pair with:
    blm_follow.py --voice-port 5006 ...

Run on a Vosk-enabled venv (vosk + pyaudio installed there):
    PROJECT_CAM_VOSK_MODEL="$HOME/Desktop/Speech to text/model" \
    /path/to/voice-venv/bin/python garage_lab_combined/scripts/voice_bridge.py

Command mapping (voice -> blm_follow.py command):
    head              -> nose
    left/right foot   -> left/right_ankle
    left/right knee   -> left/right_knee
    left/right shoulder -> left/right_shoulder
    left/right hip    -> left/right_hip
    go / shoot        -> shoot
    reload            -> reload
    pause / stop      -> pause
    resume            -> resume
    quit              -> quit
"""

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path

import pyaudio
from vosk import Model, KaldiRecognizer

MODEL_PATH = os.environ.get("PROJECT_CAM_VOSK_MODEL", str(Path.home() / "Desktop" / "Speech to text" / "model"))
SAMPLE_RATE = 16000

VOICE_TO_CMD = {
    "head": "nose",
    "left foot": "left_ankle",
    "right foot": "right_ankle",
    "left knee": "left_knee",
    "right knee": "right_knee",
    "left shoulder": "left_shoulder",
    "right shoulder": "right_shoulder",
    "left hip": "left_hip",
    "right hip": "right_hip",
    "go": "shoot",
    "shoot": "shoot",
    "reload": "reload",
    "pause": "pause",
    "stop": "pause",
    "resume": "resume",
    "quit": "quit",
}

GRAMMAR = list(VOICE_TO_CMD.keys()) + ["[unk]"]
COOLDOWN_SECONDS = 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5006)
    ap.add_argument("--model", default=MODEL_PATH)
    args = ap.parse_args()

    if not Path(args.model).exists():
        print(f"[ERR] Vosk model not found: {args.model}", file=sys.stderr)
        sys.exit(1)

    model = Model(args.model)
    rec = KaldiRecognizer(model, SAMPLE_RATE, json.dumps(GRAMMAR))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dest = (args.host, args.port)

    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
        input=True, frames_per_buffer=4000,
    )
    stream.start_stream()

    print(f">>> Voice bridge -> udp://{args.host}:{args.port}")
    print(f">>> Grammar ({len(GRAMMAR) - 1} phrases): {', '.join(VOICE_TO_CMD.keys())}")
    print(">>> Ctrl+C to stop.\n")

    last_cmd_time = 0.0
    last_cmd = None

    try:
        while True:
            data = stream.read(2000, exception_on_overflow=False)
            if not rec.AcceptWaveform(data):
                continue
            text = json.loads(rec.Result()).get("text", "").strip()
            if not text or text == "[unk]" or text not in VOICE_TO_CMD:
                continue

            now = time.time()
            if text == last_cmd and (now - last_cmd_time) < COOLDOWN_SECONDS:
                continue
            last_cmd = text
            last_cmd_time = now

            cmd = VOICE_TO_CMD[text]
            sock.sendto(cmd.encode("utf-8"), dest)
            print(f"[VOICE] '{text}' -> {cmd} -> udp://{args.host}:{args.port}")
    except KeyboardInterrupt:
        print("\n[EXIT] stopping...")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()
        sock.close()


if __name__ == "__main__":
    main()
