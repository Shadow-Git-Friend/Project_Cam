# Voice Command Integration Plan

## 1. Recommendation: Vosk (Offline, Lightweight)

### Why Vosk over alternatives

| Library | Offline | Latency | GPU | CPU | Accuracy | Best For |
|---------|---------|---------|-----|-----|----------|----------|
| **Vosk** | Yes | ~50-100ms | No (CPU only) | Low (~5%) | Good for commands | **Our choice** |
| faster-whisper | Yes | ~200-500ms | Yes (competes with YOLO!) | Medium | Excellent | Transcription |
| OpenAI Whisper | Yes | ~1-3s | Yes (competes with YOLO!) | High | Best | Transcription |
| Google STT | No (cloud) | ~300ms + network | No | Low | Excellent | Online apps |
| SpeechRecognition | Wrapper | Varies | Varies | Varies | Varies | Prototyping |
| Picovoice/Porcupine | Yes | ~30ms | No | Very low | Wake word only | Wake word |

### Why Vosk wins for our project:
1. **No GPU needed** — YOLO + YOLO-Pose already use the RTX 2080 Ti. Whisper would compete for GPU memory
2. **50ms latency** — fast enough for real-time commands
3. **50MB model** — small English model works fine for a fixed vocabulary of ~20 commands
4. **Streaming API** — processes audio chunks as they arrive, no need to wait for silence
5. **Configurable vocabulary** — can restrict to our command words only, boosting accuracy
6. **Runs on CPU** — our workstation has 20 CPU threads, plenty of headroom

### Alternative consideration: Vosk + Porcupine hybrid
- Porcupine for wake word ("Hey launcher") — ~30ms, near-zero CPU
- Vosk for command recognition after wake word
- This prevents false triggers from conversation/ambient noise

---

## 2. Microphone Hardware

### Recommended (Budget): USB Headset Microphone
- **Jabra Evolve2 40** (~$80) — noise-cancelling boom mic, USB, works on Linux
- **Logitech H390** (~$30) — basic USB headset, cardioid, plug-and-play Linux
- Why headset: operator wears it, mic is close to mouth, rejects launcher motor noise

### Recommended (Hands-free): Directional USB Microphone  
- **Shure MV7** (~$250) — dynamic cardioid, excellent noise rejection, USB class-compliant on Linux
- **Blue Yeti Nano** (~$80) — cardioid mode, USB, Linux compatible
- **Samson Q2U** (~$70) — dynamic cardioid, USB + XLR, great noise rejection

### Recommended (Budget + Distance): Lapel/Lavalier
- **Fifine K053** (~$15) — clip-on USB lavalier, 2m cable
- **Rode Lavalier GO** (~$80) — broadcast quality clip-on

### For our case (noisy arena, 2-5m distance):
**Best choice: USB headset (Jabra or Logitech H390)** — operator wears it, no distance problem, motor noise rejected by proximity + cardioid pattern.

If hands-free needed: **Samson Q2U** on a stand near the operator.

---

## 3. Software Dependencies

```bash
# Core: Vosk speech recognition
pip install vosk

# Audio capture
pip install sounddevice   # preferred over PyAudio (easier install on Linux)

# Optional: wake word detection
pip install pvporcupine   # Picovoice Porcupine (free tier: 3 custom wake words)

# Download Vosk model (small English, 50MB)
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip -d voice_commands/models/
```

### System dependencies (Ubuntu):
```bash
sudo apt install portaudio19-dev   # needed for audio
```

---

## 4. Voice Command Vocabulary

### Design principles:
- Short (1-2 syllables preferred)
- Phonetically distinct from each other
- Distinct from ambient noise / conversation
- Map directly to BLM serial commands

### Command Set:

| Voice Command | Action | Serial Command | Notes |
|--------------|--------|----------------|-------|
| **"aim hip"** | Target right_hip | (compute + set) | Default target |
| **"aim knee"** | Target right_knee | (compute + set) | |
| **"aim shoulder"** | Target left_shoulder | (compute + set) | |
| **"aim center"** | Target body_center | (compute + set) | Midpoint of hips |
| **"track"** | Start continuous tracking | (continuous set) | Auto-follows target |
| **"hold"** | Freeze current aim | (stop updating) | Keep current angles |
| **"fire"** | Shoot one ball | `shoot` | Only after aim lock |
| **"reload"** | Reload mechanism | `reload` | |
| **"stop"** | Stop everything | `stop` | Immediate halt |
| **"emergency"** | Emergency stop | `estop` | Latched until "clear" |
| **"clear"** | Release e-stop | `clear` | |
| **"home"** | Return to center | `center` | |
| **"status"** | Report current state | `status` | Spoken feedback |

### Why these words:
- "aim" is distinct and unlikely in ambient speech
- Body part names (hip, knee, shoulder) are phonetically very different
- "fire" instead of "shoot" — shorter, more distinct
- "emergency" is a long unique word — hard to trigger accidentally
- "stop" is universal and instinctive

---

## 5. Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Microphone  │────▶│  Audio Thread    │────▶│  Vosk Recognizer│
│  (USB)       │     │  (sounddevice)   │     │  (CPU, ~5%)     │
└─────────────┘     │  16kHz, mono     │     │  streaming      │
                    └──────────────────┘     └────────┬────────┘
                                                      │
                                              recognized text
                                                      │
                                                      ▼
                                            ┌──────────────────┐
                                            │  Command Parser  │
                                            │  (fuzzy match)   │
                                            └────────┬─────────┘
                                                     │
                                              VoiceCommand enum
                                                     │
                                    ┌────────────────┼────────────────┐
                                    ▼                ▼                ▼
                          ┌──────────────┐  ┌──────────────┐  ┌────────────┐
                          │  BLM Serial  │  │  CV Pipeline  │  │  Audio     │
                          │  (aim/fire)  │  │  (joint sel)  │  │  Feedback  │
                          └──────────────┘  └──────────────┘  └────────────┘

Threading model:
  Thread 1: Main CV pipeline (cameras + YOLO + triangulation + rendering)
  Thread 2: Audio capture (sounddevice callback → ring buffer)
  Thread 3: Voice recognition (Vosk processes chunks from ring buffer)
  Main thread coordination via threading.Event + queue.Queue
```

### Key design decisions:
1. **sounddevice callback mode** — audio capture runs in its own thread automatically, never blocks
2. **Vosk streaming** — feed audio chunks as they arrive, get results with zero delay
3. **Command queue** — recognized commands go into `queue.Queue`, main loop polls it (non-blocking)
4. **No GPU contention** — Vosk is CPU-only, YOLO keeps full GPU
5. **Confirmation beep** — play a short tone when command is recognized (audio feedback)

### Latency budget:
| Stage | Time |
|-------|------|
| Audio capture buffer | 50ms |
| Vosk recognition | 50-100ms |
| Command parsing | <1ms |
| Serial send | <5ms |
| **Total** | **~100-150ms** |

---

## 6. Safety Considerations

1. **"fire" requires prior "aim" lock** — cannot fire without a valid aim solution
2. **"emergency" always works** — highest priority, bypasses all other commands
3. **Confidence threshold** — Vosk returns confidence scores; reject low-confidence commands
4. **No continuous fire** — "fire" is single-shot, must be repeated for each ball
5. **Audio feedback** — spoken/tone confirmation of each command so operator knows it was heard
6. **Timeout** — if no voice command for 30s during "track" mode, auto-stop

---

## 7. Implementation Phases

### Phase 1: Basic recognition (1-2 days)
- Install Vosk + sounddevice
- Test microphone on workstation
- Recognize fixed vocabulary in isolation
- Print recognized commands to terminal

### Phase 2: Integration with pipeline (1-2 days)
- Add VoiceCommandThread to live_4cam_arena_view_parallel.py
- Command queue → main loop reads and acts
- "aim hip/knee/shoulder" changes the demo-blm target joint
- "stop" / "home" send serial if connected

### Phase 3: BLM control (1 day)
- Wire voice commands to launcher_runtime_from_udp.py
- "fire" → shoot sequence (only with --shoot-enabled)
- "emergency" → estop
- Audio feedback (beep on recognition)

### Phase 4: Polish (1 day)
- Confidence tuning (reject noise)
- Custom Vosk vocabulary (restrict to our words)
- Optional: wake word with Porcupine
- Logging voice commands to JSONL
