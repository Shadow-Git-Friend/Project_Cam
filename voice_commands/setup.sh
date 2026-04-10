#!/usr/bin/env bash
# Setup voice command dependencies
set -euo pipefail

cd /home/hanush/Desktop/Project_Cam

echo "=== Installing Python packages ==="
./venv/bin/pip install vosk sounddevice

echo ""
echo "=== Installing system dependencies ==="
sudo apt install -y portaudio19-dev

echo ""
echo "=== Downloading Vosk English model (50MB) ==="
mkdir -p voice_commands/models
if [ ! -d "voice_commands/models/vosk-model-small-en-us-0.15" ]; then
    wget -q --show-progress \
        https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip \
        -O /tmp/vosk-model.zip
    unzip -q /tmp/vosk-model.zip -d voice_commands/models/
    rm /tmp/vosk-model.zip
    echo "Model downloaded to voice_commands/models/vosk-model-small-en-us-0.15/"
else
    echo "Model already exists, skipping download"
fi

echo ""
echo "=== Testing microphone ==="
python3 -c "import sounddevice as sd; print('Available audio devices:'); print(sd.query_devices())"

echo ""
echo "=== Setup complete! ==="
echo "Test with: ./venv/bin/python voice_commands/voice_command_engine.py"
echo "List audio devices: ./venv/bin/python voice_commands/voice_command_engine.py --list-devices"
