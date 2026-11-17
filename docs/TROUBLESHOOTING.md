# MAVEN AI Agent — Troubleshooting & Diagnostic Runbook

> **Common issues, root cause explanations, and verified remediation procedures.**

---

## 1. Voice & Speech Recognition Issues

### Issue 1.1: MAVEN hallucinates strange words when the room is silent
- **Symptom:** Transcript shows random phrases ("BELENCIS!", "MAMAHA!", or repetitive word loops) when nobody spoke.
- **Root Cause:** Audio buffer was passed to Whisper without acoustic speech detection after timing out.
- **Remedy:** Ensure latest `VoiceSession` code with Silence VAD Gating is active:
  ```bash
  git pull origin main
  systemctl --user restart maven-jarvis.service
  ```

### Issue 1.2: Microphone not detecting input
- **Symptom:** Logs show `Audio RMS: 0.000` or `no input device found`.
- **Diagnosis:**
  ```bash
  # Check recognized ALSA/PulseAudio input cards
  python3 -c "from maverick.voice.audio import list_audio_devices; print(list_audio_devices())"
  ```
- **Remedy:** Verify your microphone is not muted in PulseAudio:
  ```bash
  pactl set-source-mute @DEFAULT_SOURCE@ 0
  pactl set-source-volume @DEFAULT_SOURCE@ 100%
  ```

---

## 2. Clap Detection & Gesture Issues

### Issue 2.1: Desk taps or typing trigger accidental claps
- **Symptom:** Typing on keyboard triggers single-clap or dual-clap.
- **Root Cause:** Spectral energy ratio threshold is set too low for your microphone's frequency curve.
- **Remedy:** In `~/.config/maverick/voice_settings.json`, decrease sensitivity:
  ```json
  {
    "clap_sensitivity": 0.55
  }
  ```

### Issue 2.2: Dual-clap does not open HUD
- **Symptom:** Two claps are heard but window does not appear.
- **Remedy:** Ensure claps occur between **180ms and 750ms** apart. Check `/home/firza-ilmi/.local/state/maverick/window_control.json`:
  ```bash
  cat ~/.local/state/maverick/window_control.json
  ```

---

## 3. Computer Use & Desktop Automation Issues

### Issue 3.1: "AT-SPI2 accessibility bus unreachable"
- **Symptom:** Computer use agent cannot inspect window trees.
- **Remedy:** Enable GNOME accessibility toolkit in your user session:
  ```bash
  gsettings set org.gnome.desktop.interface toolkit-accessibility true
  ```

---

## 4. Subsystem Reset & Clean Restart

To completely reset all caches and restart MAVEN cleanly:

```bash
# 1. Stop all services
systemctl --user stop maven-jarvis-gui.service maven-jarvis.service

# 2. Clear temporary state (memory records are preserved)
rm -f ~/.local/state/maverick/window_control.json*

# 3. Start services
systemctl --user start maven-jarvis.service
systemctl --user start maven-jarvis-gui.service
```
