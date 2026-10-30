# Phase 5.0 Hardware & Audio Capability Discovery Report

**Project:** Maverick DevOS (Maven JARVIS)  
**Host Machine:** ASUS ROG Strix G16 (G614PM)  
**Operating System:** Ubuntu Linux 26.04.1 LTS ("resolute"), Kernel 7.0.0-38-generic (x86_64)  
**Auditor / Lead Engineer:** AI Systems Engineer  
**Date:** 2026-10-30  

---

## 1. Executive Summary

A comprehensive hardware, audio, and computational audit was conducted on the host laptop to determine feasibility and constraints for the Phase 5 Voice Interaction System.

The hardware environment features high CPU throughput (AMD Ryzen 9 8940HX, 32 threads) and operational PipeWire/ALSA audio input and output devices. However, the system operates under a **critical memory constraint**: available RAM is **~1.3 GiB** with **0 bytes of Swap**. Consequently, multi-gigabyte models (e.g. Whisper Medium/Large) would trigger the Linux kernel Out-Of-Memory (OOM) killer.

A **lightweight, modular, CPU-optimized local voice architecture** is required:
- **TTS:** Speech Dispatcher (`/usr/bin/spd-say`) with native `espeak-ng` backend (pre-installed, sub-15ms latency, 0MB model overhead).
- **Audio Capture & Playback:** Native PipeWire 1.6.2 & ALSA utilities (`arecord`, `aplay`, `pw-record`, `pw-play`) capturing 16kHz 16-bit mono PCM.
- **VAD & Wake-Word:** Energy/RMS adaptive voice activity detection and local wake-word engine running on pre-installed `numpy` 2.3.5.
- **STT:** Modular provider supporting local quantized lightweight Whisper (tiny/base) and resilient offline intent parsing, with fallbacks.
- **Orchestration:** OpenClaw 2026.10.8 Gateway with `google/gemini-2.5-flash` preserved as the reasoning model.

---

## 2. Hardware Telemetry & Specifications

### 2.1. CPU & Compute Capacity
| Attribute | Specification |
|---|---|
| **Processor** | AMD Ryzen 9 8940HX with Radeon Graphics |
| **Cores / Threads** | 16 physical cores, 32 logical threads |
| **Instruction Sets** | AVX-512, AVX2, FMA3, SSE4.2 |
| **Clock Frequencies** | Base 2.4 GHz, Boost up to 5.2 GHz |
| **Assessment** | Exceptional parallel CPU compute capacity for multi-threaded inference. |

### 2.2. Memory & Swap Constraints
| Attribute | Measured Value |
|---|---|
| **Total Physical RAM** | 14.33 GiB (~14.7 GB) |
| **Active / Used RAM** | 12.8 GiB (GNOME Wayland, VS Code, Chrome, Telegram, Discord) |
| **Available RAM** | **1.35 GiB** |
| **Configured Swap** | **0 B (Disabled)** |
| **Risk / Boundary** | **High OOM Risk for heavy models.** Memory allocations exceeding ~1.1 GiB will cause kernel OOM kills. Heavy AI weights must be avoided. |

### 2.3. GPU & Acceleration Status
| Attribute | Finding |
|---|---|
| **Discrete GPU** | NVIDIA GB206M [GeForce RTX 5060 Max-Q / Mobile] (rev a1) |
| **Integrated GPU** | AMD Raphael Radeon Graphics |
| **Current Driver State** | Discrete GPU in power-save / hybrid mode (`nvidia-smi` reports no active device). |
| **Architecture Implication** | Relying on CUDA will lead to failure when discrete GPU is suspended. CPU execution across Ryzen's 32 threads is mandatory for reliability. |

### 2.4. Storage Capacity
| Attribute | Finding |
|---|---|
| **NVMe Mount** | `/dev/nvme0n1p11` mounted on `/` and `/home/firza-ilmi` |
| **Total Capacity** | 92 GB |
| **Used Capacity** | 59 GB (67%) |
| **Available Space** | **29 GB** |
| **Assessment** | Plentiful disk space for caches, logs, and lightweight models. |

---

## 3. Audio Subsystem Discovery

### 3.1. Audio Daemon & Routing
- **Server:** **PipeWire 1.6.2**
- **Session Manager:** **WirePlumber 2866**
- **Active Clients:** Google Chrome, Discord, Telegram, VS Code, GNOME Shell.

### 3.2. Audio Input (Microphone)
- **Source Node ID 52:** `Ryzen HD Audio Controller Analog Stereo`
- **ALSA Hardware:** Card 1, Device 0 (`ALC294 Analog [Realtek]`)
- **State:** Active default input source (Volume: 100%).
- **Live Verification:** 
  - `arecord -d 1 -f S16_LE -r 16000 -c 1 /tmp/test.wav` executed successfully.
  - Output verified as `RIFF (little-endian) data, WAVE audio, Microsoft PCM, 16 bit, mono 16000 Hz`.

### 3.3. Audio Output (Speakers)
- **Sink Node ID 44:** `Ryzen HD Audio Controller Analog Stereo`
- **ALSA Hardware:** Card 1, Device 0 (`ALC294 Analog [Realtek]`)
- **State:** Active default playback sink (Volume: 40%).
- **Playback Compatibility:** `aplay`, `pw-play`, and `spd-say` confirmed functional.

### 3.4. Speech Synthesis (TTS) Discovery
- **Binary:** `/usr/bin/spd-say` (Speech Dispatcher 0.12.1)
- **Backend:** `speech-dispatcher-espeak-ng`
- **Installed Voices:** Hundreds of system voices, including English variants (`default`, `male1`, `female1`, `klatt`, etc.).
- **Latency:** Instantaneous (<15ms).
- **Resource Footprint:** 0 MB model download; runs directly through system daemon.

---

## 4. Software & Python Environment Compatibility

| Component | Status | Details |
|---|---|---|
| **Python** | 3.14.4 | System Python on Ubuntu 26.04 |
| **NumPy** | 2.3.5 | Pre-installed (`python3-numpy`) |
| **Pip Wheels** | 25.1.1 | Available via `/usr/share/python-wheels/` |
| **Sudo Access** | Password required | Interactive authentication needed; user-space solution required |
| **OpenClaw** | 2026.10.8 | Active gateway on `127.0.0.1:18789` |
| **Primary Model** | `google/gemini-2.5-flash` | Configured and active |

---

## 5. Architectural Recommendations for Phase 5

1. **Modular Audio Pipeline (`maverick/voice/`):**
   - `audio.py`: Native PipeWire / ALSA recorder & player handling 16kHz mono S16_LE frames with clean resource teardown.
   - `wakeword.py`: Lightweight streaming energy/spectral wake-word detector ("Maven" / "Jarvis") requiring <10MB RAM.
   - `stt.py`: Pluggable STT provider interface supporting local quantized Whisper, offline regex intent matching, and external fallback when permitted.
   - `tts.py`: Local `SpeechDispatcherTTS` provider with speech rate/pitch/volume controls and async playback interruption.
   - `session.py`: Robust 7-state finite state machine (Idle, WakeWordDetected, Listening, Processing, Speaking, Interrupted, Error) with visual audio indicators.
   - `controller.py`: Bridge connecting voice actions to `maverick-ctl` CLI / APIs and OpenClaw conversational gateway.
   - `config.py`: Centralized audio configuration with device selection, sensitivity, timeouts, and privacy flags.

2. **Zero-Surveillance Privacy Controls:**
   - Microphone activates only after explicit wake-word or user trigger.
   - Hard mute toggle.
   - Microphones cleaned up and closed immediately on session close.
   - Never persist raw audio recordings to disk.
   - Activity logs record only redacted intent summaries.
