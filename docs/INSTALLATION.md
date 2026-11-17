# MAVEN AI Agent — Installation & Setup Guide

> **Target OS:** Ubuntu 22.04 LTS / 24.04 LTS, Debian 12+, Linux Mint 21+  
> **Hardware:** x86_64 CPU (AVX-512 recommended for instant STT), 8 GB+ RAM, Webcam, Microphone.  

---

## 1. System Prerequisites

MAVEN requires a few essential system development libraries, Python 3.10+, and audio/accessibility drivers:

```bash
# Update system package repositories
sudo apt-get update

# Install Core Python, Compilers & Media Dependencies
sudo apt-get install -y \
    python3 python3-pip python3-venv git build-essential cmake \
    portaudio19-dev libasound2-dev libpulse-dev \
    speech-dispatcher pulseaudio-utils \
    libgirepository1.0-dev libcairo2-dev gir1.2-atspi-2.0 \
    gir1.2-gtk-3.0 gir1.2-webkit2-4.1 \
    v4l-utils libgl1 libglib2.0-0
```

---

## 2. Cloning the Repository

```bash
# Clone the official MAVEN repository
git clone https://github.com/Maverick-list/MAVEN_AI_Agent.git ~/MAVEN_AI_Agent

# Navigate to the workspace directory
cd ~/MAVEN_AI_Agent
```

---

## 3. Python Virtual Environment Setup

```bash
# Create an isolated Python virtual environment
python3 -m venv .venv

# Activate the virtual environment
source .venv/bin/activate

# Upgrade packaging tools
pip install --upgrade pip setuptools wheel

# Install required Python dependencies
pip install -r requirements.txt
```

---

## 4. Local Whisper.cpp High-Performance STT Engine

MAVEN operates offline using an AVX-512 accelerated `whisper.cpp` build:

```bash
# Compile whisper.cpp with optimal SIMD vector acceleration
mkdir -p ~/.local/share/maverick
cd ~/.local/share/maverick

if [ ! -d "whisper.cpp" ]; then
    git clone https://github.com/ggerganov/whisper.cpp.git
fi

cd whisper.cpp
cmake -B build -DWHISPER_BUILD_SERVER=ON -DWHISPER_AVX512=ON
cmake --build build --config Release -j$(nproc)

# Download the compact multilingual GGML model (~75 MB)
bash ./models/download-ggml-model.sh tiny
```

---

## 5. Environment & Configuration Setup

Create your user configuration file:

```bash
mkdir -p ~/.config/maverick
cat << 'EOF' > ~/.config/maverick/voice_settings.json
{
  "tts_default_language": "id",
  "enable_clap_detection": true,
  "clap_sensitivity": 0.65,
  "whisper_threads": 4,
  "whisper_model_path": "/home/firza-ilmi/.local/share/maverick/whisper.cpp/models/ggml-tiny.bin",
  "whisper_bin_path": "/home/firza-ilmi/.local/share/maverick/whisper.cpp/build/bin/whisper-cli"
}
EOF
```

---

## 6. Systemd User Service Integration

Enable automatic background execution on user login:

```bash
# Link systemd user service definitions
mkdir -p ~/.config/systemd/user
cp systemd/maven-jarvis.service ~/.config/systemd/user/
cp systemd/maven-jarvis-gui.service ~/.config/systemd/user/

# Reload systemd user daemon
systemctl --user daemon-reload

# Enable services to run on login
systemctl --user enable maven-jarvis.service
```

---

## 7. Verification & Smoke Test

Verify that all subsystems initialize properly:

```bash
# Run unit test suite
python3 -m unittest tests/test_clap_detector.py tests/test_intelligent_agent_core.py tests/test_voice.py

# Launch the interactive terminal console
python3 -m maverick.cli status
```
