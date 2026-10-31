# MAVEN JARVIS — SYSTEM ARCHITECTURE AUDIT
## Phase Zero: Comprehensive Codebase Inspection & Runtime Topology

- **Date & Timestamp:** 2026-10-31T10:18:00+07:00 (Local WIB)
- **Workstation:** Asus ROG Strix G16 (G614PM) | AMD Ryzen 9 8940HX | NVIDIA GeForce RTX 5060 Laptop GPU | 16 GB RAM
- **Operating System:** Ubuntu 26.04.1 LTS (Linux Kernel `7.0.0-38-generic`) | GNOME 46 | Wayland Compositor (`wayland-0`)
- **Repository Branch / Local Commit:** `master` (`f47dbd1`)
- **Audit Directory:** [`reports/jarvis-evolution/`](file:///home/firza-ilmi/Maverick-DevOS/reports/jarvis-evolution)

---

## 1. Top-Level Codebase Inventory

The Maverick DevOS repository contains **19,602 lines of Python** across 74 modules, complemented by **5,793 lines of tests** across 36 test suites.

| Subsystem Package | Path | Line Count | Primary Function | Primary Entry Point |
| :--- | :--- | :--- | :--- | :--- |
| **Voice & Speech** | `maverick/voice/` | 5,038 | Audio capture, VAD, wake-word, STT, NLU, TTS, session | `maverick.cli voice daemon` / `VoiceController` |
| **Vision & Gestures** | `maverick/vision/` | 2,476 | Camera, OpenCV kinematic tracking, 21 landmarks, virtual mouse | `VisionController` / `InteractionModeManager` |
| **Computer Use** | `maverick/computer_use/` | 2,752 | AT-SPI2 accessibility, Wayland input, app profiles, agent | `AutonomousComputerUseAgent` / `UniversalInputEngine` |
| **Task Intelligence** | `maverick/intelligence/` | 1,465 | Multi-step DAG planning, 26 registered tools, SQLite memory | `TaskPlanner` / `ToolRegistry` |
| **Control Center** | `maverick/dashboard/` | 1,478 | TelemetryHub, SSE stream, REST API endpoints, static UI | `maverick.cli dashboard --port 8765` |
| **Browser Automation** | `maverick/browser/` | 1,608 | Chrome DevTools Protocol (CDP), isolated user profile | `BrowserLifecycle` / `BrowserClient` |
| **Desktop Shell** | `maverick/desktop/` | 1,021 | PyGObject GTK3 / WebKit2GTK window, app launcher | `maverick.desktop.app` |
| **Core & Security** | `maverick/core/` | 404 | Configuration, security policy, risk tiers, redaction | `maverick.core.security` |
| **System Diagnostics** | `maverick/system/` | 491 | CPU/RAM/Battery monitoring, process lifecycle | `maverick.system.monitor` |
| **Media & Notifications** | `maverick/media/`, `notifications/` | 748 | MPRIS D-Bus Spotify control, notification filtering | `SpotifyController` / `NotificationManager` |
| **Activity Logging** | `maverick/activity/` | 185 | Dual JSONL and human-readable text audit logger | `ActivityLogger` |
| **Master CLI** | `maverick/cli.py` | 804 | Unified command-line dispatcher (`voice`, `dashboard`, `app`) | `maverick.cli:main` |
| **Total Maverick** | `maverick/` | **19,602** | — | — |

---

## 2. Subsystem Architecture Audits

### 2.1 Voice Interaction Pipeline (`maverick/voice/`)
- **Architecture:** Threaded event-driven architecture running on `VoiceSession` state machine (`IDLE` $\rightarrow$ `WAKE_WORD_DETECTED` $\rightarrow$ `LISTENING` $\rightarrow$ `PROCESSING` $\rightarrow$ `SPEAKING` $\rightarrow$ `INTERRUPTED`).
- **Hardware Audio Capture (`audio.py`):** Spawns PipeWire `arecord -q -f S16_LE -r 16000 -c 1 -t raw` streaming 16kHz mono 16-bit PCM in non-blocking 1024-byte frames.
- **Wake-Word Engine (`wakeword.py`):** Two-pass acoustic hypothesis engine. Pass 1 checks dynamic noise floor and RMS energy onset; Pass 2 performs regex matching against `"maven"`, `"hey maven"`, `"jarvis"`.
- **Speech-to-Text (`stt.py`):** `WhisperCppSTTProvider` sends raw PCM over persistent loopback HTTP socket to warm `whisper-server` (`127.0.0.1:18791`) using model `ggml-tiny.bin`. Inference latency averages **431 ms – 608 ms**. Zero temporary files created on disk.
- **Natural Language Understanding (`intent.py`):** `BilingualIntentClassifier` resolves Indonesian and English phrases into 18 discrete desktop intents (`system_ram`, `system_battery`, `app_launch`, `spotify_play`, `memory_store`, `memory_recall`, `vision_mode`, `help`).
- **Text-to-Speech (`tts.py`, `elevenlabs_tts.py`):** `HybridTTSProvider` routes requests to primary ElevenLabs streaming API with automatic graceful degradation to local Linux `SpeechDispatcherTTS` (/usr/bin/spd-say, $15\text{ ms}$ TTFB) when rate-limited or offline.
- **Acoustic Feedback Suppression:** Ingest audio buffer is disabled during `SPEAKING` state to prevent self-triggering feedback loops.

### 2.2 Multimodal Vision & Gesture Subsystem (`maverick/vision/`)
- **Camera Interface (`camera.py`):** Thread-safe OpenCV `cv2.VideoCapture(0)` bound to ASUS FHD WebCam (`/dev/video0`). Real-time capture achieves **19.8 FPS** at $640 \times 480$ resolution. Enforces privacy: zero frame files persisted to disk.
- **Hand Tracking (`hand_tracker.py`):** Pluggable multi-provider architecture:
  1. `OpenCVKinematicProvider`: Native YCrCb skin segmentation, Euclidean distance transform for palm localization, and anatomical skeletal fitting ($2.6\text{ ms}$ latency, 21 3D landmarks per hand).
  2. `OpenCVDNNProvider`: Hardware-accelerated CPU ONNX keypoint model via `cv2.dnn`.
  3. `MediaPipeProvider`: Google MediaPipe Hands fallback.
- **Gesture Recognition (`gesture_recognition.py`):** Classifies 13 distinct gestures using inter-finger Euclidean distance ratios, angle kinematics, and temporal smoothing (`INDEX_POINTING`, `INDEX_PINCH`, `MIDDLE_PINCH`, `DOUBLE_PINCH`, `OPEN_PALM`, `CLOSED_FIST`, `SWIPE_UP`, `SWIPE_DOWN`, `TWO_HAND_EXPANSION`).
- **Virtual Pointer & Wayland Input (`virtual_input.py`):** Uses GNOME AT-SPI (`Atspi.generate_mouse_event`) to move pointer (`abs`), click (`b1c`, `b3c`), drag-and-drop (`b1p`, `b1r`), and scroll (`b4c`, `b5c`) without X11, uinput, or root permissions.
- **Interaction Mode Manager (`mode_manager.py`):** Strict deterministic state machine (`NORMAL`, `VISION_STARTING`, `VISION_ACTIVE`, `VISION_PAUSED`, `EMERGENCY_STOPPED`). Enforces **Normal Mode default** after restart, **1.5s physical mouse/keyboard priority pause**, and **clean hardware release** on exit.

### 2.3 Universal Linux Computer Use (`maverick/computer_use/`)
- **Execution Loop (`agent.py`):** Implements closed-loop: $\text{OBSERVE} \rightarrow \text{UNDERSTAND} \rightarrow \text{PLAN} \rightarrow \text{ACT} \rightarrow \text{VERIFY} \rightarrow \text{RECOVER}$.
- **Accessibility Inspection (`accessibility.py`):** `AccessibilityInspector` connects to AT-SPI2 D-Bus registry (`org.a11y.Bus`), crawling accessible widgets (`ROLE_PUSH_BUTTON`, `ROLE_TEXT`, `ROLE_MENU_ITEM`, `ROLE_PAGE_TAB`).
- **Screen & Window Awareness (`screen.py`):** Detects focused window, bounding boxes, screen dimensions, and cross-application occlusion.
- **Strategy Engine (`strategy.py`):** Resolves action targets via a strict resolution hierarchy:
  1. AT-SPI2 semantic tree node (Preferred, deterministic).
  2. Native CLI / D-Bus protocol.
  3. Browser DevTools Protocol (CDP).
  4. OCR / Visual recognition.
  5. Coordinate-based pointer fallback.
- **Application Compatibility Registry (`registry.py`):** Maintains capability profiles, quirks, and shortcuts for VS Code, GNOME Files (Nautilus), Chrome, Firefox, GNOME Terminal, Evince, GNOME Settings, and GTK File Chooser dialogs.
- **Security & Authorization (`security.py`):** Enforces 3-tier risk gating (`NORMAL`, `CONSEQUENTIAL`, `CRITICAL`), Emergency Stop lockdown, path traversal checks, and confirmation gates.

### 2.4 Browser Automation (`maverick/browser/`)
- **Lifecycle Management (`lifecycle.py`):** Launches Google Chrome with `--remote-debugging-port=9222`, `--remote-debugging-address=127.0.0.1`, and a dedicated automation user profile directory (`~/.config/maverick/browser/automation-profile`).
- **Safety Guarantee:** Verifies `/proc/<pid>/cmdline` before issuing signals. **Never intercepts, kills, or inspects the user's normal Chrome browsing session.**
- **CDP Engine (`cdp.py`, `client.py`):** WebSocket JSON-RPC protocol implementation communicating with Chrome DevTools Protocol domains (`Page`, `Runtime`, `DOM`, `Network`).
- **Security Sandbox (`security.py`):** Enforces URL validation, blocking `file:///`, internal cloud metadata IPs (`169.254.169.254`), and private subnets unless explicitly permitted.

### 2.5 Task Planner & Unified Tools (`maverick/intelligence/`)
- **Task Planner (`planner.py`):** Decomposes user instructions into ordered `TaskStep` DAG plans. Manages task execution states (`pending`, `running`, `awaiting_approval`, `completed`, `failed`).
- **Tool Registry (`tools.py`):** Central catalog of 26 registered tools spanning desktop application control, file I/O, system diagnostics, memory storage/recall, and computer use.
- **Context Memory (`memory.py`):** SQLite3 database (`~/.config/maverick/context_memory.sqlite`) storing user preferences, project context, and interaction summaries with full-text search.

### 2.6 Control Center Dashboard (`maverick/dashboard/`)
- **Web Server (`server.py`):** Multi-threaded HTTP/1.1 and Server-Sent Events (SSE) server bound strictly to loopback `127.0.0.1:8765`.
- **Telemetry Hub (`TelemetryHub`):** Aggregates live system telemetry, active plan DAG, vision mode status, computer use observations, and recent conversation turns.
- **Frontend Assets (`static/`):** Holographic dark charcoal UI styled with CSS glassmorphism, responsive grid layouts, and real-time SSE chart streams.

### 2.7 Native Desktop Application (`maverick/desktop/`)
- **GTK3 Shell (`app.py`):** Standalone Ubuntu desktop application built with PyGObject, Gtk.HeaderBar, WebKit2GTK WebKitWebView, and GtkStatusIcon/AppIndicator system tray support.
- **Window Controls:** Supports minimize to background, restore on click, full Wayland window management, and native desktop keyboard shortcuts.

---

## 3. Runtime Topology & Network Sockets

| Service / Daemon | Process / PID | Network / IPC Endpoint | Protocol | Security Scope |
| :--- | :--- | :--- | :--- | :--- |
| **OpenClaw Gateway** | Node.js (PID 2829) | `127.0.0.1:18789` | HTTP/SSE + WebSocket | Bearer token auth, loopback only |
| **Whisper STT Server** | C++ binary (PID 16312) | `127.0.0.1:18791` | HTTP POST multipart/wav | Local loopback, zero disk write |
| **Maven Voice Daemon** | Python (PID 16313) | PipeWire IPC + D-Bus | Raw PCM Stream | Systemd user session |
| **Control Center Dashboard** | Python (PID 17416) | `127.0.0.1:8765` | HTTP/1.1 + SSE | Local loopback, CORS restricted |
| **Native Desktop App Shell** | Python (PID 19790) | Wayland Display `wayland-0` | Wayland / GTK3 IPC | User desktop session |
| **Trial Monitor Daemon** | Python (PID 20667) | Filesystem polling | POSIX signals / PID | 15s interval, lightweight |
| **AT-SPI2 Accessibility Bus** | `at-spi2-registryd` | D-Bus Session / Accessibility | org.a11y.atspi D-Bus | Wayland user accessibility session |
| **ASUS FHD Camera** | V4L2 Device Driver | `/dev/video0` | V4L2 / OpenCV | Closed by default, opened on explicit approval |
