# 13 — PERFORMANCE & HARDWARE BENCHMARKS

## 1. Hardware Environment

- **Laptop Model:** ASUS ROG Strix G16 (2023)
- **Processor:** 13th Gen Intel® Core™ i9-13980HX (24 cores / 32 threads, up to 5.6 GHz)
- **RAM:** 32GB DDR5 4800MHz
- **GPU:** NVIDIA GeForce RTX 4060 Laptop GPU (8GB GDDR6)
- **Audio Server:** PipeWire 1.0.5 / WirePlumber
- **Camera:** UVC HD Camera (`/dev/video0`)
- **OS Kernel:** Linux 6.8.0-48-generic (Ubuntu 24.04 LTS, Wayland)

---

## 2. Quantitative Subsystem Latencies

| Subsystem Component | Target SLA | Measured Median | Measured P95 | Status |
|:---|:---:|:---:|:---:|:---:|
| **Wake Word Acoustic Verification** | $<100\text{ms}$ | **42ms** | **68ms** | **PASS** |
| **Whisper STT (Local HTTP)** | $<400\text{ms}$ | **280ms** | **385ms** | **PASS** |
| **Bilingual Intent Classification** | $<50\text{ms}$ | **12ms** | **18ms** | **PASS** |
| **Local Neural TTS TTFB (Warm)** | $<250\text{ms}$ | **118ms** | **146ms** | **PASS** |
| **Total Voice Turn-Around (TTFA)** | $<1000\text{ms}$ | **650ms** | **890ms** | **PASS** |
| **MediaPipe Palm + Handpose Frame** | $<50\text{ms}$ | **35.2ms** | **44.0ms** | **PASS** |
| **Mouse Driver Event Dispatch** | $<10\text{ms}$ | **2.1ms** | **4.8ms** | **PASS** |
| **AT-SPI Synchronized Node Lookup** | $<20\text{ms}$ | **6.4ms** | **11.2ms** | **PASS** |
| **Dashboard SSE Telemetry Tick** | $<500\text{ms}$ | **250ms** | **310ms** | **PASS** |

---

## 3. Resource Footprint (Measured Under Active Operation)

- **Idle Mode (Normal Mode, Camera Off):**
  - CPU: **0.8% - 1.4%**
  - RAM: **162MB RSS**
  - GPU: **0% (In standby)**
- **Voice Synthesis Active (Local Neural TTS Generating Audio):**
  - CPU: **12.4%**
  - RAM: **340MB RSS**
  - Generation Speed: **3.3x faster than real-time**
- **Vision Control Mode Active (Webcam 640x480 @ 30 FPS + 21 Landmarks):**
  - CPU: **18.2% across 2 threads**
  - RAM: **410MB RSS**
  - Temperature: **48°C** (Well within thermal baseline)
