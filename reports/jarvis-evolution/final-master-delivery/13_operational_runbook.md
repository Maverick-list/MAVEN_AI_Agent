# MAVEN JARVIS — OPERATIONAL RUNBOOK
**System:** Maverick DevOS (JARVIS Operating Assistant)  
**Target Worktree:** `/home/firza-ilmi/Maverick-DevOS-evolution`  
**Run Mode:** Local Service & Control Center  

---

## 1. Quick Start Commands

### 1.1 Launching the Holographic Control Center
```bash
# Enter the evolution workspace
cd /home/firza-ilmi/Maverick-DevOS-evolution

# Start dashboard server on loopback port 8765
PYTHONPATH=. python3 maverick/dashboard/server.py --port 8765 --open
```
*Access URL:* `http://127.0.0.1:8765`

### 1.2 Running Voice & Vision Services
```bash
# Launch Maven Voice Daemon (Runs in background)
PYTHONPATH=. python3 -m maverick.voice.cli start

# Check Voice Daemon Status
PYTHONPATH=. python3 -m maverick.voice.cli status

# Stop Voice Daemon
PYTHONPATH=. python3 -m maverick.voice.cli stop
```

---

## 2. Interaction Modes & Shortcuts

### Normal Mode (Default)
- **Camera Sensor:** Completely powered OFF (`cv2.VideoCapture.release()`).
- **Physical Controls:** Mouse and keyboard are 100% unrestricted.
- **Voice Assistant:** Fully active; responds to wake word *"Maven"* or *"Hey Maven"*.

### Vision Control Mode (Toggle: `Super + Shift + V` or Dashboard Button)
- **Camera Sensor:** Powered ON (`/dev/video0`).
- **Tracking:** Real-time 21-landmark skeletal hand tracking.
- **Pointer Control:**
  - `INDEX_POINTING`: Moves cursor across Wayland display.
  - `INDEX_PINCH`: Left-click / Drag-and-drop.
  - `TWO_FINGERS_POINTING`: Stationary right-click / Vertical scroll.
  - `CLOSED_FIST`: Instant Emergency Stop.
  - `OPEN_PALM`: Release all held buttons.

---

## 3. Configuration & Voice Preferences
Voice preferences are persisted in `~/.config/maverick/voice_settings.json`:

```json
{
  "tts_engine": "local_neural",
  "local_neural_voice": "george",
  "tts_default_language": "en",
  "wake_words": ["maven", "hey maven"],
  "enable_clap_detection": true,
  "enforce_confirmation": true
}
```

To switch Maven's voice to clear American English (`jean`):
```bash
# Update setting via CLI or Dashboard Voice Settings Drawer
curl -X POST http://127.0.0.1:8765/api/voice/settings \
  -H "Content-Type: application/json" \
  -H "Origin: http://127.0.0.1:8765" \
  -d '{"local_neural_voice": "jean"}'
```
