# MAVEN JARVIS — User Guide

**Maverick DevOS Desktop AI Assistant**
**Host Workstation:** ASUS ROG Strix G16 (AMD Ryzen 9 7845HX, 16 GB RAM)
**Operating System:** Ubuntu Linux 26.04.1 LTS ("resolute"), GNOME Wayland
**Version:** Production Release 1.0 (Phase 5.3 Final)

---

## 1. Quick Start: One-Command Launcher

Maven JARVIS provides a centralized CLI launcher available system-wide as `maven`:

```bash
# 1. Start Maven in background daemon mode (Default)
maven start

# 2. Check live operational status & resource telemetry
maven status

# 3. Stop Maven Voice Assistant
maven stop
```

### Interactive Wayland Terminal UI Mode
If you prefer visual feedback with real-time audio meters and push-to-talk controls:

```bash
maven start --ui
```

**Interactive Keybindings:**
- `[Space]` or `[Enter]`: Push-to-Talk (manually activate listening)
- `[m]`: Toggle microphone mute / unmute
- `[s]`: Instant abort / silence current speech
- `[q]` or `[Ctrl+C]`: Exit interface

---

## 2. Managing Operational Profiles

Maven JARVIS supports two reversible operational profiles tailored for daily battery life or high-performance programming:

```bash
# Check current active profile and enabled features
maven profile status

# Switch to LIGHT Mode (Everyday laptop use)
maven profile light

# Switch to DEVELOPER Mode (Programming & automation)
maven profile developer
```

### Profile Differences

| Feature | Light Mode (`maven profile light`) | Developer Mode (`maven profile developer`) |
| :--- | :---: | :---: |
| **Voice Assistant & Wake Word** | Enabled | Enabled |
| **Local STT (`whisper.cpp`) & Local TTS** | Enabled | Enabled |
| **Bilingual Intent Classification** | Enabled | Enabled |
| **OpenClaw Gateway (Gemini 2.5 Flash)** | Enabled | Enabled |
| **Telegram & Discord Messaging Bots** | Enabled | Enabled |
| **Spotify MPRIS Playback & Volume** | Enabled | Enabled |
| **Basic System Telemetry (RAM/CPU/Battery)** | Enabled | Enabled |
| **Chrome DevTools Protocol (CDP) Automation** | Disabled (Releases RAM & ports) | Enabled (`127.0.0.1:9222`) |
| **Full Context Engine Multi-Probe** | Disabled (Saves CPU cycles) | Enabled (Full desktop context) |
| **Verbose Activity Audit Logging** | Disabled | Enabled |

*Note: Switching to Light Mode automatically closes any open automation browser session to immediately reclaim resident memory.*

---

## 3. Hands-Free Voice Interaction

Maven continuously listens for your voice when active. The interaction model supports both two-turn dialogue and direct single-breath commands.

### Two-Turn Wake Dialogue
1. **You:** *"Hey Maven"* (or *"Maven"*, *"Halo Maven"*)
2. **Maven:** *"Yes, I'm listening."* (or *"Ya, saya mendengarkan."*)
3. **You:** *"Buka Visual Studio Code."*
4. **Maven:** Launches VS Code $\rightarrow$ *"Visual Studio Code is open."*

---

## 4. Bilingual Command Reference

### Indonesian Natural Expressions

| Command | Action Performed | Maven Response |
| :--- | :--- | :--- |
| *"Buka Visual Studio Code."* / *"Aku mau coding."* | Launches VS Code | *"Visual Studio Code is open."* |
| *"Tolong buka peramban Chrome."* | Launches Google Chrome | *"Google Chrome is open."* |
| *"Buka manajer berkas."* | Launches GNOME Files (Nautilus) | *"Files (Nautilus) is open."* |
| *"Buka Spotify."* | Launches Spotify client | *"Spotify is open."* |
| *"Putar musik."* / *"Lanjutkan lagu."* | Resumes Spotify playback | *"Melanjutkan pemutaran musik di Spotify."* |
| *"Jeda musik."* / *"Hentikan lagu."* | Pauses Spotify playback | *"Musik dijeda."* |
| *"Lagu berikutnya."* / *"Ganti lagu."* | Skips to next track | *"Beralih ke trek berikutnya."* |
| *"Lagu apa ini?"* / *"Sedang memutar apa?"* | Queries current track and artist | *"Sedang memutar [Judul] oleh [Artis]."* |
| *"Naikkan volume."* / *"Perbesar suara."* | Increases volume by 10% | *"Volume Spotify dinaikkan ke [X] persen."* |
| *"Turunkan volume."* / *"Pelankan suara."* | Lowers volume by 10% | *"Volume Spotify diturunkan ke [X] persen."* |
| *"Volume-nya 70 persen."* | Clamps volume exactly to 70% | *"Volume Spotify diatur ke 70 persen."* |
| *"Berapa sisa RAM laptopku?"* | Reads actual kernel telemetry | *"RAM yang tersedia adalah [X] gigabyte, dengan total penggunaan [Y] persen."* |
| *"Cek baterai laptop."* | Checks charging state & battery % | *"Baterai berada pada [X] persen dan sedang mengisi daya."* |
| *"Bagaimana kondisi laptopku?"* | Aggregates full desktop context | *"Ringkasan desktop: [N] aplikasi aktif, CPU di [X] persen, dan memori di [Y] persen."* |
| *"Aplikasi apa yang sedang berjalan?"* | Audits authorized running apps | *"Saat ini terdapat [N] aplikasi yang sedang berjalan: [Daftar]."* |
| *"Matikan suara Maven."* / *"Bisu"* | Mutes microphone input | *"Mikrofon dimatikan."* |
| *"Aktifkan mikrofon."* | Unmutes microphone input | *"Mikrofon diaktifkan."* |
| *"Diam"* / *"Berhenti"* | Immediately stops TTS playback | *(Instant silence)* |

### English Natural Expressions

| Command | Action Performed | Maven Response |
| :--- | :--- | :--- |
| *"Open VS Code."* / *"I want to code."* | Launches VS Code | *"Visual Studio Code is open."* |
| *"Open Google Chrome."* | Launches Google Chrome | *"Google Chrome is open."* |
| *"Open file manager."* / *"Open files."* | Launches Nautilus | *"Files (Nautilus) is open."* |
| *"Play music."* / *"Resume playback."* | Resumes Spotify | *"Resuming music on Spotify."* |
| *"Pause music."* / *"Stop music."* | Pauses Spotify | *"Music paused."* |
| *"Next song."* / *"Skip track."* | Next track | *"Skipping to next track."* |
| *"What song is playing?"* | Query song & artist | *"Now playing [Title] by [Artist]."* |
| *"Increase volume."* / *"Make it louder."* | Volume +10% | *"Spotify volume increased to [X] percent."* |
| *"Decrease volume."* / *"Lower the volume."* | Volume -10% | *"Spotify volume decreased to [X] percent."* |
| *"Set volume to 80 percent."* | Clamps volume to 80% | *"Spotify volume set to 80 percent."* |
| *"How much RAM is available?"* | Live telemetry check | *"You have [X] gigabytes of RAM available, with [Y] percent total usage."* |
| *"Check laptop battery."* | Battery percentage & AC state | *"Battery is at [X] percent and currently charging."* |
| *"Summarize desktop context."* | System & app context summary | *"Desktop summary: [N] applications active, CPU at [X] percent, and memory at [Y] percent."* |
| *"What applications are running?"* | Lists active apps | *"You currently have [N] applications running: [List]."* |
| *"Mute microphone."* | Mutes microphone | *"Microphone muted."* |
| *"Unmute microphone."* | Unmutes microphone | *"Microphone unmuted."* |
| *"Stop talking."* / *"Be quiet."* | Interrupts TTS | *(Instant silence)* |

---

## 5. Conversational AI Turns (Google Gemini 2.5 Flash)

Any query not matching local desktop controls automatically routes through OpenClaw Gateway to **Google Gemini 2.5 Flash**:

- **You:** *"Ceritakan sesuatu tentang artificial intelligence."*
- **Maven:** *(Queries OpenClaw Gateway $\rightarrow$ Gemini 2.5 Flash $\rightarrow$ Speaks response via Speech Dispatcher)*
- **You:** *"Explain what quantum computing is in simple terms."*
- **Maven:** *(Speaks conversational summary)*

---

## 6. Security & Confirmation Workflow

Consequential actions strictly require user confirmation before execution:
- Launching `gnome-terminal`
- Launching `firefox`
- Browser form submissions / payments

**Confirmation Flow:**
1. **You:** *"Maven, buka terminal."*
2. **Maven:** *"Membuka gnome-terminal memerlukan konfirmasi. Katakan 'konfirmasi' untuk melanjutkan."*
3. **You:** *"Konfirmasi."*
4. **Maven:** Launches `gnome-terminal`.

---

## 7. System Diagnostics & Health Audits

Run the built-in system doctor anytime to inspect hardware, models, and memory:

```bash
maven doctor
```

### Checking CPU and Memory Telemetry
```bash
# Summary telemetry
maven status

# Detailed hardware resource metrics
maverick-ctl system resources

# Activity audit trail
maverick-ctl activity recent --limit 5
```

---

## 8. Troubleshooting & FAQ

### Gateway Unreachable
- **Symptom:** Maven speaks *"I could not reach the OpenClaw agent at this moment."*
- **Fix:** Check gateway status:
  ```bash
  systemctl --user status openclaw-gateway.service
  systemctl --user restart openclaw-gateway.service
  ```

### API Quota Rate Limits (429)
- **Symptom:** Maven speaks *"Google Gemini API reported a temporary quota rate limit."*
- **Fix:** Gemini 2.5 Flash free tier resets every minute. All local desktop commands (apps, Spotify, volume, RAM, battery) continue to operate 100% offline regardless of API quota.

### Audio Device Not Detected
- **Symptom:** `maven start` warns about audio devices.
- **Fix:** Verify PipeWire/ALSA recognizes your microphone:
  ```bash
  arecord -l
  pactl list sources short
  ```

### WhatsApp Status
- Per system safety guidelines, WhatsApp is permanently quarantined (`dmPolicy: disabled`, `groupPolicy: disabled`). Telegram and Discord remain active.
