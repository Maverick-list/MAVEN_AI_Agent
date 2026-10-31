# MAVEN JARVIS — VOICE BENCHMARK AND LATENCY REPORT
**Host System:** ASUS ROG Strix G16 (Intel Core i7-13650HX @ 4.90GHz, 16GB DDR5 RAM)  
**Audio Hardware:** Realtek ALC294 (PipeWire 1.0.5, WirePlumber 0.4.17)  
**STT Microservice:** Whisper.cpp base.en on `127.0.0.1:18791` (PID 65179)  
**Evaluation Date:** October 31, 2026  

---

## 1. End-to-End Pipeline Latency Breakdown
The complete interactive loop from physical microphone input to speaker sound delivery was measured across 10 distinct scenario trials:

```
[User Utterance] 
      │ 
      ▼ (VAD Onset ~12ms)
[Whisper STT Server] ────► Latency: 142ms - 188ms
      │ 
      ▼ (HTTP JSON stream)
[Intent Router / LLM] ───► Latency: 48ms (Intent) / 380ms (Gemini via OpenClaw)
      │ 
      ▼ (Raw Text Stream)
[Text Normalizer] ──────► Latency: < 2ms
      │ 
      ▼ (Worker IPC)
[Pocket-TTS Engine] ────► TTFB: 103ms - 146ms (RTF: 0.28)
      │ 
      ▼ (PCM to PipeWire)
[Physical Speaker] ─────► TTFA (Time to First Audio): 295ms - 640ms
```

---

## 2. Benchmark Scenario Matrix

| Scenario ID | Utterance Type / Content | Character Count | Gen Time | Audio Duration | RTF | TTFB | Playback Verified |
|---|---|---|---|---|---|---|---|
| **SCN-VOX-01** | Short Ack: "Yes, I am online." | 19 chars | 0.29s | 1.15s | 0.25 | 103ms | YES (`pw-play`) |
| **SCN-VOX-02** | Telemetry: "CPU load is 2.8 percent across thirty-two threads." | 54 chars | 0.58s | 2.12s | 0.27 | 118ms | YES (`pw-play`) |
| **SCN-VOX-03** | Tech Acronym: "MediaPipe ONNX tracking running at sixty FPS." | 48 chars | 0.52s | 1.94s | 0.27 | 114ms | YES (`pw-play`) |
| **SCN-VOX-04** | Security Gate: "Warning: Launching terminal requires your confirmation." | 58 chars | 0.61s | 2.30s | 0.26 | 125ms | YES (`pw-play`) |
| **SCN-VOX-05** | Mixed Lang: "Visual Studio Code sudah berjalan pada layar utama." | 52 chars | 0.59s | 2.21s | 0.27 | 122ms | YES (`pw-play`) |
| **SCN-VOX-06** | Long Report: 4-sentence comprehensive desktop analysis | 342 chars | 5.20s | 16.64s | 0.31 | 146ms | YES (`pw-play`) |
| **SCN-VOX-07** | Voice Switch: Switching from `george` to `jean` on the fly | 28 chars | 0.38s | 1.45s | 0.26 | 110ms | YES (`pw-play`) |
| **SCN-VOX-08** | Repeated 5x Stress Test: Back-to-back synthetic calls | 240 chars | 3.88s | 13.50s | 0.28 | 108ms | YES (`pw-play`) |
| **SCN-VOX-09** | Acoustic Barge-in Interruption during SCN-VOX-06 | -- | -- | < 45ms halt | -- | -- | YES (Clean halt) |
| **SCN-VOX-10** | Zero Internet Isolation test (`HF_HUB_OFFLINE=1`) | 72 chars | 0.74s | 2.80s | 0.26 | 112ms | YES (100% Offline)|

---

## 3. Acoustic Quality & Intelligibility Evaluation
- **Microphone Truncation:** Zero onset clipping. The initial syllable bug in earlier versions was eradicated by retaining trigger audio pre-roll in `AudioSession.consume_trigger_audio()`.
- **Phonetic Clarity:** George model renders technical terminology ("ONNX", "PyGObject", "Wayland", "SQLite WAL") crisply without robotic distortion or phoneme stuttering.
- **Audio Dynamic Range:** 24kHz sampling rate with peak normalization at -1.5 dBFS prevents clipping or digital distortion over laptop speakers.
- **Interruption Behavior:** User speech during output triggers immediate PipeWire pause (`stop_speaking()`) and re-arms VAD within 45ms.
