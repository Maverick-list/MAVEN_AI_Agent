# MAVEN JARVIS — The Autonomous Linux Desktop AI Agent

<div align="center">

```
   __  ______ _    _____________   __   ___    ____   ___                    __ 
  /  |/  /   | |  / / ____/ | / /  /  | / / |  / / /  /   | ____ ____  ____  / /_
 / /|_/ / /| | | / / __/ /  |/ /  / /| / /| | / / /  / /| |/ __ `/ _ \/ __ \/ __/
/ /  / / ___ | |/ / /___/ /|  /  / ___  / | |/ / /__/ ___ / /_/ /  __/ / / / /_  
/_/  /_/_/  |_|___/_____/_/ |_/  /_/  |_/  |___/____/_/  |_\__, /\___/_/ /_/\__/  
                                                          /____/                  
```

**Next-Generation Autonomous Linux Operating Agent, Voice Companion & Holographic HUD**

[![GitHub License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue?style=flat-square&logo=python)](https://python.org)
[![Platform](https://img.shields.io/badge/platform-Linux%20(Ubuntu%20%7C%20Debian%20%7C%20Wayland%20%7C%20X11)-orange?style=flat-square&logo=linux)](https://ubuntu.com)
[![Vercel Deployment](https://img.shields.io/badge/Vercel-Online%20Live-black?style=flat-square&logo=vercel)](https://maven-ai-agent.vercel.app)
[![Voice Latency](https://img.shields.io/badge/voice%20TTFT-%3C%201.8s-success?style=flat-square&logo=speedtest)](docs/TESTING.md)
[![Action Dispatch](https://img.shields.io/badge/OS%20Actions-217ms-brightgreen?style=flat-square)](docs/TESTING.md)
[![Tests Passing](https://img.shields.io/badge/tests-64%2F64%20passed-brightgreen?style=flat-square)](docs/TESTING.md)
[![Security Gate](https://img.shields.io/badge/security-5--Tier%20Gated%20Policy-blueviolet?style=flat-square)](docs/SECURITY.md)

[**🌐 Live Online Demo**](https://maven-ai-agent.vercel.app) • [**Features**](#-key-features--capabilities) • [**Architecture**](#-system-architecture) • [**Screenshots**](#-visual-previews--screenshots) • [**Installation**](#-quick-start--installation) • [**Documentation**](#-comprehensive-documentation-system) • [**Development History**](development/README.md)

---

</div>

## 📌 Project Overview & Vision

### Vision
**MAVEN JARVIS** (Maverick Autonomous Virtual Ecological Navigator) is an offline-first, low-latency, autonomous desktop operating agent engineered for Linux power users and developers. Modeled after Tony Stark's J.A.R.V.I.S., MAVEN transforms the traditional Linux desktop into an intelligent, proactive computing environment that understands natural speech, acoustic gestures, visual hand tracking, and native OS accessibility structures.

### Problem Statement
Traditional AI desktop assistants on Linux suffer from critical architectural deficiencies:
1. **Severe Conversational Latency:** 15s to 60s delays caused by unoptimized LLM cascading, redundant cloud handshakes, and unindexed prompts.
2. **Acoustic & Whisper Hallucinations:** Speech-to-Text models inferring phantom words ("BELENCIS!", "kamu kamu...") when fed ambient silence or room echo.
3. **No Native OS Agency:** Assistants are relegated to sandboxed browser wrappers or dumb shell executors incapable of inspecting Linux accessibility trees or managing complex multi-step workflows.
4. **Accidental Acoustic Triggers:** Naive microphone listeners triggering randomly on keyboard typing, desk thuds, or background conversation.

### The Solution: MAVEN Architecture
MAVEN solves these problems at the kernel, audio DSP, and cognitive levels:
- **Sub-1.8s Speech Pipeline:** AVX-512 accelerated local whisper.cpp with strict silence VAD energy gating, paired with Gemini 2.5 Flash and streaming neural speech synthesis.
- **Spectral Acoustic Clap Detection:** Real-time $O(N \log N)$ FFT bandpass discriminator. Double-clap opens the HUD and awakens listening mode; single-clap dismisses the HUD. Table knocks and bumps are rejected automatically.
- **Universal Computer Use (AT-SPI2):** Traverses the GNOME/KDE accessibility tree in $< 0.1\text{ ms}$, inspecting widgets, invoking accessible actions, and navigating Wayland desktops safely.
- **Deterministic DAG Task Planning:** Synthesizes multi-step execution graphs sorted via Kahn's algorithm ($O(V+E)$), enforcing human-in-the-loop approvals for consequential operations.
- **Persistent Cognitive Context:** Multi-tier SQLite WAL memory store retaining developer preferences, project contexts, and acoustic calibration.

---

## 📸 Visual Previews & Screenshots

All screenshots below are captured from live, running sessions on Ubuntu 26.04 LTS (ASUS ROG Strix G16, AMD Ryzen 9 7845HX, Wayland).

---

### 1. Holographic Control Center HUD
The main command center displays real-time hardware telemetry, acoustic DSP visualizer, active AI model routing, and the pulsating JARVIS Arc Reactor core.

<p align="center">
  <a href="docs/screenshots/control-center.png">
    <img src="docs/screenshots/control-center.png" alt="MAVEN JARVIS Control Center Dashboard" width="94%" />
  </a>
  <br/>
  <em>Figure 1: Full 1080p Holographic HUD featuring 32-thread CPU meters, segmented RAM gauge, acoustic spectrum, and active pipeline status.</em>
  <br/>
  <a href="docs/screenshots/control-center.png">🔍 View Full 1080p Resolution</a>
</p>

---

### 2. Conversational Voice Pipeline & Latency Telemetry
Instantaneous, bilingual voice interaction with live sentence-by-sentence audio playback and verified per-stage pipeline latency tracking.

<p align="center">
  <a href="docs/screenshots/voice-interaction.png">
    <img src="docs/screenshots/voice-interaction.png" alt="MAVEN JARVIS Voice Interaction" width="94%" />
  </a>
  <br/>
  <em>Figure 2: Real-time bilingual dialogue with J.A.R.V.I.S. persona and microsecond-level latency breakdown (WAKE: 12ms, STT: 310ms, LLM TTFT: 820ms, TTFA: 1.34s).</em>
  <br/>
  <a href="docs/screenshots/voice-interaction.png">🔍 View Full 1080p Resolution</a>
</p>

---

### 3. Universal Autonomous Computer Use (AT-SPI2)
Native Linux desktop agency executing UI navigation, application discovery, window management, and shell inspection via the AT-SPI2 accessibility bus.

<p align="center">
  <a href="docs/screenshots/autonomous-computer-use.png">
    <img src="docs/screenshots/autonomous-computer-use.png" alt="Autonomous Computer Use Interface" width="94%" />
  </a>
  <br/>
  <em>Figure 3: Universal Computer Use agent traversing the desktop tree, verifying window state, and logging execution telemetry.</em>
  <br/>
  <a href="docs/screenshots/autonomous-computer-use.png">🔍 View Full 1080p Resolution</a>
</p>

---

### 4. Autonomous DAG Task Planning & Human-in-the-Loop Gate
Complex user goals are decomposed into Directed Acyclic Graphs with topological dependency ordering and security approval prompts before executing consequential steps.

<p align="center">
  <a href="docs/screenshots/real-task-execution.png">
    <img src="docs/screenshots/real-task-execution.png" alt="Autonomous Task Plan HUD" width="94%" />
  </a>
  <br/>
  <em>Figure 4: Multi-step DAG workflow with completed steps, execution timestamps, and an explicit human confirmation gate for terminal execution.</em>
  <br/>
  <a href="docs/screenshots/real-task-execution.png">🔍 View Full 1080p Resolution</a>
</p>

---

### 5. MediaPipe 21-Joint Vision & Gesture Tracking
Real-time contactless desktop control powered by Google MediaPipe 3D hand tracking, dynamic coordinate mapping, and physical input override priority.

<p align="center">
  <a href="docs/screenshots/vision-tracking.png">
    <img src="docs/screenshots/vision-tracking.png" alt="MediaPipe Vision Tracking HUD" width="94%" />
  </a>
  <br/>
  <em>Figure 5: 30 FPS gesture tracking HUD with OPEN_PALM recognition (94% confidence), virtual pointer coordinates, and E-Stop safeguards.</em>
  <br/>
  <a href="docs/screenshots/vision-tracking.png">🔍 View Full 1080p Resolution</a>
</p>

---

### 6. Hardware Telemetry & Audio DSP Monitoring
Detailed hardware monitoring showing per-core CPU utilization across 32 threads, segmented RAM consumption, battery health, and microphone noise-floor tracking.

<p align="center">
  <a href="docs/screenshots/hardware-monitoring.png">
    <img src="docs/screenshots/hardware-monitoring.png" alt="Hardware Telemetry and DSP Status" width="94%" />
  </a>
  <br/>
  <em>Figure 6: System telemetry card with AMD Ryzen 9 load distribution, PipeWire ALC294 audio sink verification, and whisper.cpp worker status.</em>
  <br/>
  <a href="docs/screenshots/hardware-monitoring.png">🔍 View Full 1080p Resolution</a>
</p>

---

### 7. Persistent Cognitive Context Memory
Persistent long-term memory store allowing MAVEN to recall developer preferences, project architectures, system parameters, and past interactions across sessions.

<p align="center">
  <a href="docs/screenshots/memory-management.png">
    <img src="docs/screenshots/memory-management.png" alt="Context Memory Persistent Cognitive Store" width="94%" />
  </a>
  <br/>
  <em>Figure 7: Context Memory slide-over drawer with real-time search, tag filtering (#hardware, #dsp, #git), and persistent SQLite storage.</em>
  <br/>
  <a href="docs/screenshots/memory-management.png">🔍 View Full 1080p Resolution</a>
</p>

---

### 8. Isolated Chrome CDP Browser Automation
Dedicated browser automation subsystem managing isolated Chrome instances via loopback-only Chrome DevTools Protocol (CDP) WebSocket sessions.

<p align="center">
  <a href="docs/screenshots/browser-automation.png">
    <img src="docs/screenshots/browser-automation.png" alt="Browser Automation and CDP Session" width="94%" />
  </a>
  <br/>
  <em>Figure 8: Chrome CDP subsystem settings confirming loopback isolation (127.0.0.1:9222) and dedicated automation profile sandboxing.</em>
  <br/>
  <a href="docs/screenshots/browser-automation.png">🔍 View Full 1080p Resolution</a>
</p>

---

## ⚡ Key Features & Capabilities

| Capability | Status | Implementation Details |
| :--- | :---: | :--- |
| **Bilingual J.A.R.V.I.S. Voice Engine** | `IMPLEMENTED` | Local whisper.cpp STT, Gemini 2.5 Flash, ElevenLabs / spd-say streaming. Bilingual in English & Indonesian. |
| **Silence VAD Energy Gating** | `IMPLEMENTED` | Discards silent frames ($< 0.015\text{ RMS}$) before STT to eliminate Whisper audio hallucinations. |
| **Spectral Acoustic Clap Detector** | `IMPLEMENTED` | High-frequency FFT snap discriminator ($>2.2\text{ kHz}, \text{ZCR}>0.18$). Dual-clap opens HUD; single-clap closes. |
| **Universal Computer Use (AT-SPI2)** | `IMPLEMENTED` | Traverses GNOME accessibility tree, triggers actions, clicks, and keystrokes without mouse hijacking. |
| **DAG Autonomous Task Planner** | `IMPLEMENTED` | Kahn's topological sort for dependency graphs, step execution retries, and rollback capabilities. |
| **5-Tier Action Risk Gate** | `IMPLEMENTED` | Tier 0–4 risk classification. Shell commands and destructive operations require human confirmation. |
| **Persistent Cognitive Memory** | `IMPLEMENTED` | SQLite 3 (WAL mode) schema indexing preferences, project contexts, and structured entity tags. |
| **Isolated Chrome CDP Automation** | `IMPLEMENTED` | Pure-Python RFC 6455 WebSocket CDP client with dedicated profile and credential scrubbing. |
| **MediaPipe 21-Joint Vision HUD** | `IMPLEMENTED` | Contactless hand gesture recognition, pointer coordinate mapping, and instant priority override. |
| **Hardware E-Stop Lockdown** | `IMPLEMENTED` | Sub-5ms emergency kill switch via voice command, HUD button, or keyboard shortcut. |
| **Multi-Modal Camera Screen Stream** | `EXPERIMENTAL` | V4L2 loopback visual frame buffer streaming into cognitive context window. |
| **Local LLM Quantization (AVX-512)** | `PLANNED` | Fully offline Llama.cpp inference on Ryzen 9 CPU/NPU without cloud API dependency. |

---

## 🏛️ System Architecture

```mermaid
flowchart TB
    subgraph Ingress ["1. Ingress & Sensory Layer"]
        MIC["Microphone Array (ALC294)"]
        CAM["Webcam (/dev/video0)"]
        CLAP["Spectral Clap Detector (FFT >2.2kHz)"]
        TOUCH["Keyboard / Mouse / AT-SPI2"]
    end

    subgraph Perception ["2. Perception & Signal Processing"]
        WAKE["Prefix-Anchored Wake Detector ('Hey Maven')"]
        VAD["Silence VAD Energy Gating (RMS >0.015)"]
        STT["Whisper.cpp STT (AVX-512 SIMD)"]
        VISION["MediaPipe Hand Landmark Tracker (21 Joints)"]
        A11Y["AT-SPI2 Accessibility Tree Observer"]
    end

    subgraph Cognition ["3. Cognitive Engine (MavenAgentCore)"]
        ROUTER["Bilingual Intent Classifier (ID / EN)"]
        GATE["5-Tier Action Risk Policy Gate"]
        DAG["DAG Task Planner (Kahn's Topological Sort)"]
        MEM["Context Memory Engine (SQLite WAL)"]
        LLM["AI Gateway (Google Gemini 2.5 Flash)"]
    end

    subgraph Subagents ["4. Specialized Execution Subagents"]
        CU["ComputerUseAgent (Desktop UI)"]
        CODE["CodingAgent (Terminal & Git)"]
        BROWSER["BrowserAgent (Chrome CDP)"]
        SYS["SystemMonitoringAgent (Telemetry)"]
    end

    subgraph Actuation ["5. Actuation & Presentation Layer"]
        TTS["Neural TTS / Speech Dispatcher (spd-say)"]
        HUD["FastAPI Holographic Control Center (:8765)"]
        SHELL["Native GTK3 + WebKit2 Desktop Window"]
        INPUT["Virtual UInput Linux Device"]
    end

    MIC --> WAKE & CLAP & VAD
    VAD --> STT --> ROUTER
    CLAP --> SHELL
    CAM --> VISION --> INPUT
    TOUCH --> A11Y --> CU

    ROUTER --> GATE
    GATE --> LLM & DAG
    DAG <--> MEM
    DAG --> CU & CODE & BROWSER & SYS

    Subagents --> Actuation
    Cognition --> TTS & HUD
```

---

## 🔄 Agent Execution Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor User as User (Voice / Gesture)
    participant Audio as Audio Ingress & VAD
    participant Wake as Wake / Clap Engine
    participant Brain as MavenAgentCore
    participant DAG as Task Planner
    participant Sec as 5-Tier Security Gate
    participant AT as AT-SPI2 / OS Subsystem
    participant Voice as Neural TTS Engine

    User->>Audio: Hey Maven, periksa proses aktif dan siapkan workspace
    Audio->>Audio: Silence VAD check (RMS >= 0.015) : PASS
    Audio->>Wake: Keyword Match (Hey Maven) : CONFIRMED
    Audio->>Brain: Transcribed Text via whisper.cpp
    Brain->>Brain: Classify Intent : Multi-Step Workspace Setup
    Brain->>DAG: Generate Execution DAG (3 steps)
    DAG->>DAG: Kahn's Topological Ordering
    DAG->>Sec: Evaluate Step 1 (Inspect Procs) : Tier 0 (Read-Only)
    Sec->>AT: Observe running apps via AT-SPI2
    AT-->>DAG: Active apps: code, chrome, bash
    DAG->>Sec: Evaluate Step 2 (Launch Terminal) : Tier 3 (Consequential)
    Sec->>Voice: Memerlukan konfirmasi untuk meluncurkan terminal. Lanjutkan?
    Voice-->>User: Spoken Confirmation Request
    User->>Audio: Konfirmasi
    Audio->>Sec: Confirmation Verified
    Sec->>AT: Execute desktop_launch_app(gnome-terminal)
    DAG-->>Brain: Workflow Completed
    Brain->>Voice: Synthesize Completion Response
    Voice-->>User: Workspace aktif, Sir. Semua dependensi siap.
```

---

## 🛠️ Technology Stack

| Domain | Technologies |
| :--- | :--- |
| **Runtime & Language** | Python 3.10+ (Ubuntu 26.04 LTS / Resolute), C++17 |
| **Speech-to-Text (STT)** | whisper.cpp (AVX-512 & OpenMP SIMD), PyAudio, NumPy DSP |
| **Audio Processing** | PipeWire, PulseAudio API, Scipy FFT, Zero-Crossing Rate (ZCR) |
| **Cognitive Engine** | Google Gemini 2.5 Flash, OpenClaw Gateway, Custom DAG Planner |
| **Computer Vision** | Google MediaPipe Hands (21 3D landmarks), OpenCV, V4L2 |
| **Desktop Automation** | GNOME AT-SPI2 (`gi.repository.Atspi`), `python-uinput`, PyAutoGUI |
| **Browser Automation** | Chrome DevTools Protocol (CDP), RFC 6455 WebSocket Client |
| **Holographic HUD** | FastAPI, HTML5 Canvas, WebSockets, Server-Sent Events (SSE) |
| **Desktop Shell** | GTK+ 3.0, WebKit2GTK (4.1), Wayland Compositor Integration |
| **Storage & Memory** | SQLite 3 (WAL mode), Thread-Safe Connection Pooling |
| **System Integration** | systemd user units, Linux D-Bus (MPRIS2 Spotify control) |

---

## 🚀 Quick Start & Installation

### 1. Prerequisites
Ensure you are running Ubuntu 22.04 / 24.04 / 26.04 or a Debian-based distribution with GNOME Wayland or X11:

```bash
sudo apt-get update && sudo apt-get install -y \
    python3 python3-pip python3-venv git build-essential cmake \
    portaudio19-dev libasound2-dev libpulse-dev \
    speech-dispatcher pulseaudio-utils \
    libgirepository1.0-dev libcairo2-dev gir1.2-atspi-2.0 \
    gir1.2-gtk-3.0 gir1.2-webkit2-4.1 v4l-utils
```

### 2. Clone Repository
```bash
git clone https://github.com/Maverick-list/MAVEN_AI_Agent.git
cd MAVEN_AI_Agent
```

### 3. Setup Python Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Build Whisper.cpp for Hardware Acceleration
```bash
mkdir -p ~/.local/share/maverick && cd ~/.local/share/maverick
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
cmake -B build -DWHISPER_BUILD_SERVER=ON -DWHISPER_AVX512=ON
cmake --build build --config Release -j$(nproc)
bash ./models/download-ggml-model.sh tiny
cd ~/MAVEN_AI_Agent
```

### 5. Configure Environment
```bash
cp .env.example .env
# Edit .env to set your GEMINI_API_KEY
```

---

## 💻 Usage & Operation

### Starting the Daemon & HUD
```bash
# Option A: Start daemon in background via CLI
python3 -m maverick.voice.daemon

# Option B: Launch native desktop HUD application directly
python3 -m maverick.desktop.app
```

### Navigating the Control Center
Navigate to `http://127.0.0.1:8765` in any browser to view the live Holographic Control Center.

### Acoustic & Gesture Controls
- **Dual Clap (Tepuk Tangan 2x):** Instantly awakens MAVEN, reveals the desktop HUD, and triggers active listening.
- **Single Clap (Tepuk Tangan 1x):** Immediately closes the desktop HUD and silences active speech synthesis.
- **Wake Words:** Say `"Hey Maven"`, `"Maven"`, or `"Halo Maven"` followed by your instruction.
- **Emergency Stop:** Say `"Berhenti"`, `"Cancel"`, `"Stop"`, or click the red `🛑 E-STOP` button on the top HUD bar.

---

## 🧪 Quality Assurance & Test Verification

All modules have been validated through rigorous automated unit testing:

```bash
# Run comprehensive test suite
python3 -m unittest discover tests
```

```text
Ran 64 tests in 5.115s

OK (100% Passing)
```

- **Acoustic Clap Synthesis & Rejection Tests:** 12/12 passed (table thumps correctly ignored).
- **DAG Topological Planning & Retries:** 16/16 passed.
- **Bilingual Intent Resolution & Fallbacks:** 24/24 passed.
- **Security Confirmation Gate & E-Stop:** 12/12 passed.

Detailed test logs and latency metrics are documented in [`docs/TESTING.md`](docs/TESTING.md).

---

## 📚 Comprehensive Documentation System

| Document | Purpose & Description |
| :--- | :--- |
| [📐 ARCHITECTURE.md](docs/ARCHITECTURE.md) | High-level system architecture and 11-phase cognitive lifecycle. |
| [⚙️ SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md) | Subsystem decomposition, 7-state FSM, and IPC data contracts. |
| [🧮 ALGORITHM.md](docs/ALGORITHM.md) | Mathematical formulations for FFT clap detection, Kahn's DAG sort, and VAD gating. |
| [🔄 WORKFLOW.md](docs/WORKFLOW.md) | Step-by-step operational workflows and sequence diagrams. |
| [🔌 API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) | Full REST HTTP routes, WebSocket contracts, and CLI commands. |
| [🗄️ DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | SQLite 3 table schemas (WAL mode), ER diagrams, and indexes. |
| [📦 INSTALLATION.md](docs/INSTALLATION.md) | Detailed Linux setup guide, apt packages, and whisper.cpp build. |
| [📖 USER_GUIDE.md](docs/USER_GUIDE.md) | Voice command reference, gestures, and practical scenarios. |
| [💻 DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) | Codebase tour, extending tools, and adding specialized subagents. |
| [🧪 TESTING.md](docs/TESTING.md) | Test suites, benchmark results, and quality assurance metrics. |
| [🚢 DEPLOYMENT.md](docs/DEPLOYMENT.md) | Systemd user service installation, autostart, and Debian packaging. |
| [🛡️ SECURITY.md](docs/SECURITY.md) | 5-tier action risk policy, credential protection, and E-Stop design. |
| [🔧 TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Diagnostic runbook for microphone, audio sinks, and Wayland hooks. |
| [📜 CHANGELOG.md](docs/CHANGELOG.md) | Version release history and comprehensive changelog for v2.2.0. |
| [🏛️ DEVELOPMENT HISTORY](development/README.md) | Complete archive of historical Phase 1–5 implementation reports and security audits. |

---

## 🗺️ Roadmap & Future Milestones

- [x] **Phase 1–5:** Core Linux integration, Whisper.cpp AVX-512, AT-SPI2, Two-Pass Wake, Production CLI.
- [x] **v2.2.0:** Holographic HUD, Silence VAD Gating, MediaPipe 21-point tracking, Spectral Clap Detector.
- [ ] **v2.3.0:** Local LLM Quantization (Llama.cpp on AMD Ryzen NPU/AVX-512) for 100% offline intelligence.
- [ ] **v2.4.0:** Multi-device swarm coordination (Laptop + Phone + Raspberry Pi sensor nodes).
- [ ] **v2.5.0:** Semantic visual memory indexing for full-desktop episodic replay.

---

## 👥 Contributors & Acknowledgments

- **Lead Architect & Developer:** Firza Ilmi ([@Maverick-list](https://github.com/Maverick-list))
- **Engine Core:** Powered by the open-source Linux community, Georgi Gerganov's [whisper.cpp](https://github.com/ggerganov/whisper.cpp), Google MediaPipe, and GNOME AT-SPI2.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
