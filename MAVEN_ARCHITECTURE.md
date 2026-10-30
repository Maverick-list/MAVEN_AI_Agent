# MAVEN JARVIS — System Architecture & Engineering Specifications

**Project:** Maverick DevOS (Maven JARVIS)  
**Host Workstation:** ASUS ROG Strix G16 (AMD Ryzen 9 7845HX, 16 Cores / 32 Threads, 16 GB DDR5 RAM)  
**OS & Desktop:** Ubuntu Linux 26.04.1 LTS ("resolute"), Kernel 7.0.0-38-generic, GNOME Wayland  
**Orchestration:** OpenClaw 2026.10.8 (`google/gemini-2.5-flash`)  
**Production Checkpoint:** `~/Maverick-DevOS`  

---

## 1. High-Level System Decomposition

Maven JARVIS integrates four primary functional tiers into a cohesive, secure desktop automation and intelligence system:

```
+-----------------------------------------------------------------------------------+
|                            USER INTERACTION TIER                                  |
|   Hardware Mic (ALC294)  <--->  Terminal Voice UI  <--->  Local TTS (spd-say)     |
+-----------------------------------------------------------------------------------+
                                      |
+-----------------------------------------------------------------------------------+
|                             VOICE ENGINE TIER                                     |
|  - Energy VAD + Two-Pass Wake Detector (Prefix Anchored, Contrastive Phonetics)  |
|  - Native whisper.cpp (AVX-512, ggml-tiny.bin, Multilingual ID/EN)                |
|  - Deterministic Bilingual Intent Normalizer & Classifier (BilingualIntentClassifier) |
+-----------------------------------------------------------------------------------+
                                      |
                     +----------------+----------------+
                     |                                 |
           [Local Desktop Intent]           [Conversational Query]
                     |                                 |
+-----------------------------------------+   +-------------------------------------+
|         DESKTOP AUTOMATION TIER         |   |         OPENCLAW AI GATEWAY         |
|  - Safe Launcher & Confirmation Gates   |   |  - OpenClaw Daemon (systemd user)   |
|  - Spotify MPRIS Controller (D-Bus)     |   |  - Google Gemini 2.5 Flash          |
|  - Chrome CDP Controller (127.0.0.1)    |   |  - Telegram & Discord Integrations  |
|  - Context Engine & Telemetry Monitors  |   |  - (WhatsApp Quarantined / Disabled)|
+-----------------------------------------+   +-------------------------------------+
                                      |
+-----------------------------------------------------------------------------------+
|                           SECURITY & AUDIT TIER                                   |
|  - AppArmor Boundary Preservation (Strict DBus exception scope)                   |
|  - Isolated Chrome Profile (~/.local/share/maverick/chrome-automation)            |
|  - Masked Activity Logger (~/.local/share/maverick/activity.jsonl, 1000 cap)      |
|  - Zero Audio Persistence (In-memory buffers, ephemeral execution)                |
+-----------------------------------------------------------------------------------+
```

---

## 2. Voice Subsystem & Finite State Machine

The voice lifecycle is managed by a thread-safe 7-state finite state machine (`VoiceSession`):

```
       [ IDLE ]  <----------------------------------------------------+
          |                                                           |
  Wake Word Detected                                                  |
          v                                                           |
  [ WAKE_WORD_DETECTED ]                                              |
          |                                                           |
   Begin Buffering                                                    |
          v                                                           |
   [ LISTENING ] -------- (Silence >= 1.2s or Max 15s) --------------->+
          |                                                           |
   Utterance Complete                                                 |
          v                                                           |
   [ PROCESSING ] (whisper.cpp STT & Intent Classification)           |
          |                                                           |
   Dispatch Action                                                    |
          v                                                           |
    [ SPEAKING ] (Microphone Suppressed via Feedback Guard)           |
          |                                                           |
     TTS Complete ----------------------------------------------------+
          |
    (Interrupted via 's' or 'diam') ---> [ INTERRUPTED ] ---> [ IDLE ]
```

### Two-Pass Acoustic Wake-Word Engine
1. **Dynamic Rolling Buffer:** Evaluates audio snapshots with a 0.3s minimum window (9,600 bytes), ensuring short single-word utterances ("Maven!") are captured without boundary clipping.
2. **Prefix Anchoring (`WAKE_REGEX`):** Wake phrases must start the utterance (`^\s*(?:(?:hey|hei|halo|hai|ok|okay)\s+)?(?:maven|jarvis)\b`), preventing mid-sentence conversational hallucinations.
3. **Contrastive Proper-Noun Prompting:**
   - **Pass 1:** Sensitive candidate detection using `PROMPT_PASS1 = "Hey Maven, Jarvis, haven, mayhem, bacon, raven"`. Two-word phrases (`Hey Maven`) pass immediately.
   - **Pass 2:** Precision confirmation for single-word candidates against distractor vocabulary (`haven`, `shaven`, `modern`, `motor`, `bacon`). Distractors are rejected offline with zero cloud roundtrips.

---

## 3. Bilingual Intent Normalization (`BilingualIntentClassifier`)

Located at `maverick/voice/intent.py`, this module provides sub-millisecond, deterministic offline routing:
- **Language Detection:** Analyzes intersection scores against curated Indonesian (`ID_WORDS`) and English (`EN_WORDS`) lexicons.
- **Colloquial Normalization:** Strips modal and polite fillers (*"tolong"*, *"aku mau"*, *"please"*, *"can you"*) and leading wake words.
- **14 Canonical Intents:**
  1. `wake_acknowledgment`: Responds with *"Yes, I'm listening."* or *"Ya, saya mendengarkan."*
  2. `app_launch`: Launches approved applications (`code`, `google-chrome`, `firefox`, `nautilus`, `spotify`, `gnome-terminal`).
  3. `spotify_play`, `spotify_pause`, `spotify_next`, `spotify_status`: Native MPRIS control.
  4. `spotify_volume`: Adjusts volume (up, down, numeric clamping $[0, 100]$, query).
  5. `system_ram`, `system_battery`, `system_cpu`: Live hardware telemetry via `psutil`.
  6. `context_summary`: Multi-signal desktop status from `ContextEngine`.
  7. `apps_running`: Active authorized running applications.
  8. `mute`, `unmute`, `interrupt`: Voice session control.
  9. `unhandled`: Fallback to OpenClaw / Gemini 2.5 Flash for general conversation.

---

## 4. Operational Profiles (Light vs. Developer Mode)

Profiles are managed by `maverick/core/profile.py` and persisted in `~/.config/maverick/profile.json` (`0600` permissions):

```
+--------------------------------------------------------------------------------+
|                             OPERATIONAL PROFILES                               |
+---------------------------------------+----------------------------------------+
|              LIGHT MODE               |             DEVELOPER MODE             |
|  - Everyday battery/memory efficiency |  - Full programming & desktop automation|
|  - Voice Assistant & Wake Word        |  - Voice Assistant & Wake Word         |
|  - Local STT/TTS & Intent Classifier  |  - Local STT/TTS & Intent Classifier   |
|  - OpenClaw Gateway (Gemini 2.5 Flash)|  - OpenClaw Gateway (Gemini 2.5 Flash) |
|  - Telegram & Discord Messaging Bots  |  - Telegram & Discord Messaging Bots   |
|  - Essential Desktop Controls         |  - Essential Desktop Controls          |
|  - Basic System Telemetry             |  - Chrome CDP Automation (127.0.0.1)   |
|  - Chrome CDP Disabled (RAM reclaimed)|  - Full Multi-Source Context Engine    |
|  - Context Engine Probes Bypassed     |  - Verbose Activity Audit Logging      |
+---------------------------------------+----------------------------------------+
```

Switching to `light` automatically invokes `BrowserClient().lifecycle.stop()` to immediately release Chrome CDP resident memory, sockets, and the 9222 debugging port.

---

## 5. Workstation Memory Analysis & ZRAM Evaluation

### Workstation Telemetry
- **Hardware RAM:** 14.33 GiB DDR5 (Single-node AMD Ryzen 9 7845HX)
- **Available RAM:** ~4.9 – 5.4 GiB (Healthy margin $> 4\text{ GiB}$)
- **Configured Swap:** 0 MiB (No physical swap partition or file)

### Resident Memory Footprint by Subsystem
- **OpenClaw Gateway Service:** ~2.4 GiB resident (Node.js runtime + model embeddings)
- **Maven Voice Daemon:** **50.1 MiB RSS** (Idle continuous listening)
- **Whisper STT Subprocess:** **~120 MiB Peak RSS** (Transient during 300ms inference)
- **Continuous Listening CPU:** **0.0% – 0.5%** (Energy onset VAD gating)

### Safe ZRAM Recommendation
Because the workstation has 0 swap, any extreme memory spike from concurrent heavy workloads (e.g. multiple IDE instances, large compilations, or complex local LLM inference) could trigger the Linux kernel out-of-memory killer (`oom-killer`), terminating critical processes abruptly.
- **Recommendation:** Deploy `zram-generator` configured for 4–8 GiB of RAM swap using `zstd` compression.
- **Clarification:** ZRAM provides a compressed virtual swap pool in RAM to cushion burst memory demand; it does *not* reduce resident application RSS.
- **Implementation Notice:** No privileged system changes (`sudo`) are executed automatically. The sysadmin configuration recipe is provided below:
  ```bash
  # Optional sysadmin recipe for ZRAM swap on Ubuntu 26.04:
  sudo apt install -y systemd-zram-generator
  # /etc/systemd/zram-generator.conf:
  # [zram0]
  # zram-size = ram / 2
  # compression-algorithm = zstd
  # sudo systemctl restart systemd-zram-setup@zram0.service
  ```

---

## 6. Security, Confinement & Privacy Guarantees

1. **Wayland Window Isolation:** Under GNOME Wayland, unprivileged applications cannot capture global keystrokes or record foreign window contents. Maven respects this architecture.
2. **AppArmor Boundary Preservation:** Unconfined execution is strictly limited to mediated Spotify D-Bus calls under validated arguments; parent CLI processes never drop confinement.
3. **Chrome DevTools Protocol (CDP) Isolation:**
   - Automation binds exclusively to `127.0.0.1:9222` (never `0.0.0.0`).
   - Automation profile is isolated to `~/.local/share/maverick/chrome-automation`, strictly avoiding the user's personal Google Chrome profile.
4. **Mandatory Confirmation Gates:**
   - Launching `gnome-terminal` or `firefox` via voice or CLI returns `confirmation_required` and blocks execution until confirmed.
5. **Zero Audio Persistence:**
   - Audio chunks are processed in RAM buffers; temporary transcription WAV files are unlinked in `finally` blocks.
6. **WhatsApp Quarantine:**
   - WhatsApp channel policy is permanently locked to `dmPolicy: disabled`, `groupPolicy: disabled`.
