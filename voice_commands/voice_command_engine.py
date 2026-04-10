#!/usr/bin/env python3
"""
Voice Command Engine for BLM Launcher System.

Runs Vosk speech recognition in a background thread, parses commands,
and puts them into a thread-safe queue for the main pipeline to consume.

Usage (standalone test):
    ./venv/bin/python voice_commands/voice_command_engine.py

Usage (integration):
    from voice_commands.voice_command_engine import VoiceCommandEngine

    engine = VoiceCommandEngine(model_path="voice_commands/models/vosk-model-small-en-us-0.15")
    engine.start()

    while True:
        cmd = engine.get_command()  # non-blocking, returns None if no command
        if cmd:
            print(f"Voice command: {cmd.name} -> {cmd.action}")
        # ... rest of your pipeline
    engine.stop()

Requirements:
    pip install vosk sounddevice
    # Download model:
    wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
    unzip vosk-model-small-en-us-0.15.zip -d voice_commands/models/
"""

import json
import queue
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Optional

try:
    import sounddevice as sd
except ImportError:
    print("ERROR: sounddevice not installed. Run: pip install sounddevice")
    sys.exit(1)

try:
    from vosk import Model, KaldiRecognizer, SetLogLevel
except ImportError:
    print("ERROR: vosk not installed. Run: pip install vosk")
    sys.exit(1)


# --------------- Command definitions ---------------

class CommandAction(Enum):
    AIM_HIP = auto()
    AIM_KNEE = auto()
    AIM_SHOULDER = auto()
    AIM_CENTER = auto()
    TRACK = auto()
    HOLD = auto()
    FIRE = auto()
    RELOAD = auto()
    STOP = auto()
    EMERGENCY = auto()
    CLEAR = auto()
    HOME = auto()
    STATUS = auto()


@dataclass
class VoiceCommand:
    action: CommandAction
    raw_text: str
    confidence: float
    timestamp: float


# Mapping from recognized text fragments to commands.
# Vosk outputs lowercase text. We match substrings/keywords.
COMMAND_MAP = {
    # Aim commands — "aim hip", "aim at hip", "target hip"
    "aim hip": CommandAction.AIM_HIP,
    "target hip": CommandAction.AIM_HIP,
    "aim knee": CommandAction.AIM_KNEE,
    "target knee": CommandAction.AIM_KNEE,
    "aim shoulder": CommandAction.AIM_SHOULDER,
    "target shoulder": CommandAction.AIM_SHOULDER,
    "aim center": CommandAction.AIM_CENTER,
    "aim centre": CommandAction.AIM_CENTER,
    "target center": CommandAction.AIM_CENTER,

    # Control commands
    "track": CommandAction.TRACK,
    "start tracking": CommandAction.TRACK,
    "hold": CommandAction.HOLD,
    "freeze": CommandAction.HOLD,

    # Action commands
    "fire": CommandAction.FIRE,
    "shoot": CommandAction.FIRE,
    "reload": CommandAction.RELOAD,

    # Safety commands
    "stop": CommandAction.STOP,
    "emergency": CommandAction.EMERGENCY,
    "e stop": CommandAction.EMERGENCY,
    "clear": CommandAction.CLEAR,

    # Utility commands
    "home": CommandAction.HOME,
    "center": CommandAction.HOME,
    "status": CommandAction.STATUS,
}

# Map CommandAction to BLM serial commands (where applicable)
ACTION_TO_SERIAL = {
    CommandAction.STOP: "stop",
    CommandAction.EMERGENCY: "estop",
    CommandAction.CLEAR: "clear",
    CommandAction.HOME: "center",
    CommandAction.FIRE: "shoot",
    CommandAction.RELOAD: "reload",
}

# Map CommandAction to target joint name (for aim commands)
ACTION_TO_JOINT = {
    CommandAction.AIM_HIP: "right_hip",
    CommandAction.AIM_KNEE: "right_knee",
    CommandAction.AIM_SHOULDER: "left_shoulder",
    CommandAction.AIM_CENTER: "body_center",
}


def parse_command(text: str) -> Optional[CommandAction]:
    """Match recognized text to a command action."""
    text = text.strip().lower()
    if not text:
        return None

    # Try exact match first
    if text in COMMAND_MAP:
        return COMMAND_MAP[text]

    # Try substring match (longest first for specificity)
    sorted_keys = sorted(COMMAND_MAP.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key in text:
            return COMMAND_MAP[key]

    return None


# --------------- Voice Command Engine ---------------

class VoiceCommandEngine:
    """
    Background voice command recognition using Vosk.

    Captures audio from microphone in a callback thread,
    feeds it to Vosk recognizer, and puts parsed commands
    into a thread-safe queue.
    """

    def __init__(
        self,
        model_path: str = "voice_commands/models/vosk-model-small-en-us-0.15",
        sample_rate: int = 16000,
        device: Optional[int] = None,
        max_queue_size: int = 32,
        min_confidence: float = 0.3,
    ):
        self.sample_rate = sample_rate
        self.device = device
        self.min_confidence = min_confidence
        self._command_queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._audio_queue: queue.Queue = queue.Queue()
        self._running = False
        self._recognition_thread: Optional[threading.Thread] = None
        self._stream = None

        # Load Vosk model
        SetLogLevel(-1)  # suppress Vosk logs
        model_dir = Path(model_path)
        if not model_dir.exists():
            raise FileNotFoundError(
                f"Vosk model not found at {model_path}. Download it:\n"
                f"  wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip\n"
                f"  unzip vosk-model-small-en-us-0.15.zip -d voice_commands/models/"
            )
        self._model = Model(str(model_dir))
        self._recognizer = KaldiRecognizer(self._model, sample_rate)
        print(f"[VOICE] Vosk model loaded from {model_path}")

    def _audio_callback(self, indata, frames, time_info, status):
        """Called by sounddevice for each audio chunk (runs in audio thread)."""
        if status:
            print(f"[VOICE] Audio status: {status}", file=sys.stderr)
        # Copy raw bytes to queue
        self._audio_queue.put(bytes(indata))

    def _recognition_loop(self):
        """Runs in background thread: reads audio chunks, feeds to Vosk."""
        print("[VOICE] Recognition thread started")
        while self._running:
            try:
                data = self._audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if self._recognizer.AcceptWaveform(data):
                result = json.loads(self._recognizer.Result())
                text = result.get("text", "").strip()
                if text:
                    self._handle_result(text, final=True)
            else:
                # Partial result — could use for UI feedback
                partial = json.loads(self._recognizer.PartialResult())
                partial_text = partial.get("partial", "").strip()
                # Optional: display partial text for debugging
                # if partial_text:
                #     print(f"[VOICE] (partial) {partial_text}")

        print("[VOICE] Recognition thread stopped")

    def _handle_result(self, text: str, final: bool = True):
        """Parse recognized text and enqueue command if valid."""
        action = parse_command(text)
        if action is None:
            print(f"[VOICE] Heard: \"{text}\" (no matching command)")
            return

        cmd = VoiceCommand(
            action=action,
            raw_text=text,
            confidence=1.0,  # Vosk small model doesn't expose per-word confidence easily
            timestamp=time.time(),
        )

        try:
            self._command_queue.put_nowait(cmd)
            # Print with color based on command type
            if action in (CommandAction.EMERGENCY, CommandAction.STOP):
                print(f"[VOICE] ** {action.name} ** <- \"{text}\"")
            else:
                print(f"[VOICE] {action.name} <- \"{text}\"")
        except queue.Full:
            print("[VOICE] Command queue full, dropping command")

    def start(self):
        """Start audio capture and recognition."""
        if self._running:
            return

        self._running = True

        # List available audio devices
        devices = sd.query_devices()
        if self.device is None:
            default_input = sd.default.device[0]
            dev_info = sd.query_devices(default_input, 'input')
            print(f"[VOICE] Using default input device: {dev_info['name']}")
        else:
            dev_info = sd.query_devices(self.device, 'input')
            print(f"[VOICE] Using device {self.device}: {dev_info['name']}")

        # Start audio stream (callback runs in its own thread)
        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=4000,  # 250ms chunks at 16kHz
            device=self.device,
            dtype="int16",
            channels=1,
            callback=self._audio_callback,
        )
        self._stream.start()

        # Start recognition thread
        self._recognition_thread = threading.Thread(
            target=self._recognition_loop, daemon=True, name="vosk-recognition"
        )
        self._recognition_thread.start()

        print("[VOICE] Engine started — listening for commands")

    def stop(self):
        """Stop audio capture and recognition."""
        self._running = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if self._recognition_thread is not None:
            self._recognition_thread.join(timeout=2.0)
            self._recognition_thread = None
        print("[VOICE] Engine stopped")

    def get_command(self) -> Optional[VoiceCommand]:
        """Non-blocking: get next command or None."""
        try:
            return self._command_queue.get_nowait()
        except queue.Empty:
            return None

    def get_command_blocking(self, timeout: float = 1.0) -> Optional[VoiceCommand]:
        """Blocking: wait up to timeout seconds for a command."""
        try:
            return self._command_queue.get(timeout=timeout)
        except queue.Empty:
            return None


# --------------- Standalone test ---------------

def main():
    """Test the voice command engine standalone."""
    import argparse

    ap = argparse.ArgumentParser(description="Voice Command Engine test")
    ap.add_argument("--model", default="voice_commands/models/vosk-model-small-en-us-0.15",
                    help="Path to Vosk model directory")
    ap.add_argument("--device", type=int, default=None,
                    help="Audio input device index (None = default)")
    ap.add_argument("--list-devices", action="store_true",
                    help="List audio devices and exit")
    args = ap.parse_args()

    if args.list_devices:
        print(sd.query_devices())
        return

    print("=" * 60)
    print("Voice Command Engine — Standalone Test")
    print("=" * 60)
    print()
    print("Available commands:")
    print("  aim hip / aim knee / aim shoulder / aim center")
    print("  track / hold")
    print("  fire / reload")
    print("  stop / emergency / clear")
    print("  home / status")
    print()
    print("Press Ctrl+C to exit")
    print()

    engine = VoiceCommandEngine(model_path=args.model, device=args.device)
    engine.start()

    try:
        while True:
            cmd = engine.get_command_blocking(timeout=0.5)
            if cmd:
                serial_cmd = ACTION_TO_SERIAL.get(cmd.action)
                joint = ACTION_TO_JOINT.get(cmd.action)

                info = f"  Action: {cmd.action.name}"
                if serial_cmd:
                    info += f" -> serial: \"{serial_cmd}\""
                if joint:
                    info += f" -> target joint: {joint}"
                print(info)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
