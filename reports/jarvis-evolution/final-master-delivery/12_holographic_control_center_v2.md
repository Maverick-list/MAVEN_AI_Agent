# 12 — HOLOGRAPHIC CONTROL CENTER V2 & CONTROL ARCHITECTURE

## 1. Web Architecture & Local Security

The Holographic Control Center is a real-time web interface served by `ControlCenterServer`:
- **Strict Loopback Binding:** Bound strictly to `127.0.0.1`. Attempts to bind to `0.0.0.0` or external network adapters are rejected with a fatal security exception.
- **CSRF Protection:** Mutating `POST` requests inspect the `Origin` header and reject any cross-origin browser requests (`Origin != 127.0.0.1 / localhost`).
- **Real-Time SSE Stream:** Server-Sent Events (`/api/events`) push state deltas to the browser without polling loops.
- **Telemetry Snapshot Caching:** Snapshot generation is throttled with a 250ms TTL in `_cached_snapshot`, while state transitions and user actions trigger immediate cache invalidation via `notify_change()`.

---

## 2. Integrated Control Endpoints

| Endpoint | Method | Action / Purpose |
|:---|:---:|:---|
| `/api/status` | GET | Comprehensive real-time operational snapshot |
| `/api/system/diagnostics` | GET | Hardware telemetry, service health, and sanitized process inspection |
| `/api/vision/frame` | GET | Live JPEG frame stream from hardware camera |
| `/api/voice/voices` | GET | Catalog of available offline neural voices and cloud models |
| `/api/voice/stream/<token>` | GET | Low-latency audio stream (WAV or MP3) for browser Web Audio playback |
| `/api/emergency-stop` | POST | Master emergency stop: instantly halts virtual mouse, pauses computer-use, and stops audio playback |
| `/api/vision/test-camera` | POST | Enumerate camera and capture single test frame |
| `/api/vision/test-gesture` | POST | Run gesture inference test on live frame |
| `/api/intelligence/cancel` | POST | Cancel active planning or execution workflow |
| `/api/toolkit/code` | POST | Execute AST symbol extraction or codebase regex search |
| `/api/toolkit/research` | POST | Run multi-source research and factual synthesis |
| `/api/toolkit/document` | POST | Generate PDF, DOCX, or Markdown document |

---

## 3. UI Controls in `index.html` & `app.js`

- **Visual State Display:** Core reactor reacts dynamically to `idle`, `listening`, `thinking`, `speaking`, `interrupted`, and `error`.
- **Top Control Cluster:** Includes `MIC: ACTIVE / MUTED`, `MODE: NORMAL / VISION CONTROL`, and master `🛑 E-STOP`.
- **Hardware Probes:** Buttons for `MIC TEST`, `TEST CAM`, `CALIBRATE`, and voice language preview toggles.
