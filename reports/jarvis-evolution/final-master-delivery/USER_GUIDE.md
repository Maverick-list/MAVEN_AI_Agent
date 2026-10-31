# MAVEN JARVIS — USER GUIDE & OPERATOR MANUAL

Welcome to your evolved **MAVEN JARVIS** personal AI operating partner on Ubuntu GNOME Wayland.

---

## 1. Daily Voice Interaction

MAVEN listens continuously for wake triggers with acoustic filtering and syllable protection.

### Spoken Voice Characteristics
- **Default Voice:** Clear, natural male English (`george` - British/American JARVIS tone).
- **Offline Reliability:** 100% local neural synthesis. Zero internet connection or paid cloud credits required.
- **Wake Words:**
  - *"Maven"*
  - *"Hey Maven"*
  - Dual Hand Clap (when enabled in settings)
- **Bilingual Comprehension:**
  - When spoken to in English -> Responds in natural English.
  - When spoken to in Indonesian -> Responds in clear English by default, or Indonesian if you ask *"dalam bahasa Indonesia"*.

### Common Spoken Commands
- *"Hey Maven, what is my system status?"* -> Spoken CPU and available RAM.
- *"Hey Maven, how much battery do I have left?"* -> Battery percentage and charging state.
- *"Hey Maven, open Visual Studio Code"* -> Opens or focuses VS Code.
- *"Hey Maven, increase Spotify volume"* -> Adjusts Spotify playback volume.
- *"Hey Maven, stop"* -> Instantly interrupts assistant speech or media.

---

## 2. Multimodal Vision & Gesture Control

### Privacy-First Dual Modes
- **Normal Mode (Default):**
  - Camera device is **completely closed**. The hardware webcam LED is unlit.
  - Zero camera CPU/GPU power consumption.
  - Physical mouse and keyboard have unrestricted priority.
- **Vision Control Mode:**
  - Toggle anytime with keyboard shortcut: `Super+Shift+V`
  - Or click `⇄ MODE` in the Holographic Control Center header.
  - The webcam LED lights up, and real-time 21-landmark neural hand tracking activates.

### Supported Gestures
- **Index Pinch (Thumb + Index Tip):** Left click. Hold to drag; release pinch to drop.
- **Two Fingers Pointing:**
  - Stationary: Right click.
  - Vertical movement: Smooth scroll up/down.
- **Closed Fist:** Emergency stop. Instantly freezes virtual cursor and drops any held buttons.
- **Open Palm:** Resumes tracking and clears any lingering mouse states.
- **Hand Loss Protection:** If you pull your hand away from the camera, all clicks are released immediately.
- **Physical Override:** Moving your physical trackpad or typing on your keyboard instantly takes control.

---

## 3. Autonomous Task Execution & Complex Planning

MAVEN can plan and execute multi-step tasks safely:
1. Issue a complex goal (by voice or dashboard):
   *"Research Linux eBPF observability and generate a PDF summary in my documents folder."*
2. MAVEN generates a multi-step Directed Acyclic Graph (DAG) with dependency ordering.
3. Steps execute autonomously, verifying real outcomes on disk.
4. If a step involves high-risk actions (modifying critical files or running system scripts), MAVEN pauses and asks for your approval.
5. You can approve with voice (*"Maven, approve"*), by gesture (*Thumbs Up*), or via the dashboard `[ APPROVE ]` button.

---

## 4. Holographic Control Center (Dashboard)

Access the live dashboard in your browser:
**URL:** `http://127.0.0.1:8765`

### Key Features
- **Central Holographic Core:** Visual reactor showing live RMS volume and operational state (`idle`, `listening`, `thinking`, `speaking`, `interrupted`).
- **Telemetry Cluster:** Real-time 24-core CPU usage, RAM, disk, and battery gauges.
- **Microphone Test:** `[ MIC TEST ]` measures acoustic RMS without writing files.
- **Camera Test:** `[ TEST CAM ]` verifies hardware webcam resolution and FPS.
- **Master Emergency Stop:** `[ 🛑 E-STOP ]` instantly halts all virtual mouse actions, pauses computer use, and stops voice playback.
- **Voice Settings Drawer:** Switch voice profiles (`george`, `jean`, `charles`, etc.) or preview test phrases in English and Indonesian.
- **Context Memory Drawer:** View, search, or add persistent memories.
