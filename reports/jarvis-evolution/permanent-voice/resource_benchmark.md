# MAVEN JARVIS — Permanent Voice Resource Benchmark

## 1. Hardware & System Baseline

| System Property | Value |
| :--- | :--- |
| **Operating System** | Ubuntu Linux (x86_64, Linux Kernel 6.8+) |
| **Processor** | Standard x86_64 CPU Architecture (32 logical execution threads, AVX2 enabled) |
| **System Memory** | 15.6 GB Physical RAM (~2.1 GB free during trial operation) |
| **Audio Subsystem** | PipeWire with ALSA compatibility (`aplay` / `pw-play`) |
| **Target Runtime** | Isolated Virtualenv (`~/.local/share/maverick/tts-env/`) |
| **Execution Mode** | Pure CPU Inference (Zero GPU / CUDA requirement) |

---

## 2. Model Footprint & Resource Consumption

### 2.1 Storage Footprint
- **Model Weights (`6l/model.safetensors`):** 417.7 MB
- **BPE Tokenizer (`tokenizer.model`):** 311.3 KB
- **Voice Prompts (`voices/`):** 152.0 KB
- **Virtual Environment Runtime:** ~2.1 GB (Python runtime, PyTorch CPU kernels, dependencies)
- **Total Persistent Footprint:** ~2.5 GB

### 2.2 Memory (RAM) Consumption
- **Baseline Maven Idle Process:** ~180 MB RSS
- **Pocket-TTS Model In-Memory Footprint:** ~346.8 MB RSS (measured during benchmark execution)
- **Peak RSS during Synthesis:** ~352.7 MB RSS (well within the available 2.1 GB RAM budget)
- **Zero OOM Risk:** Model memory is managed deterministically with single-instance thread safety.

### 2.3 CPU Utilization
- **Idle Utilization:** 0.0% CPU
- **Synthesis Burst Utilization:** ~11.6%–12.9% CPU across worker threads during active generation.
- **Cool-down Utilization:** Returns immediately to idle (<1.0% CPU) upon audio generation completion.

---

## 3. Latency & Real-Time Factor (RTF) Performance

| Operation | Metric | Measured Performance |
| :--- | :--- | :--- |
| **Model Cold-Start Loading** | Time to load safetensors into memory | **0.917s – 0.954s** (performed once) |
| **Voice Prompt Conditioning**| Time to parse 4.6s reference audio | **0.504s – 0.585s** (cached into state) |
| **Short Utterance Synthesis** | 1–2 sentence conversational turn (~7.5s audio)| **1.965s** generation |
| **Real-Time Factor (RTF)** | Generation Time / Audio Duration | **0.261x – 0.277x** (**3.6x–3.8x faster than real-time**) |
| **Time-to-First-Byte (TTFB)** | Audio playback start latency | **~0.8s** (Direct PCM streaming/buffering) |

### Key Performance Findings:
1. **Real-Time Factor < 0.50x:** The 6-layer distilled model generates speech more than twice as fast as real-time on standard Linux CPU, completely eliminating buffering pauses.
2. **Deterministic Playback:** Unlike cloud APIs that suffer from network jitter, TLS handshakes (150–400 ms), and fluctuating queue times, local neural inference latency is consistent and predictable.
3. **Zero Network Egress/Ingress:** Completely immune to internet outages, bandwidth congestion, or rate limits.

