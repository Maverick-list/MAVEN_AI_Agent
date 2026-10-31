# 11 — SYSTEM INTELLIGENCE & SECRET REDACTION

## 1. Real-Time Telemetry & Process Inspection

Maven monitors the host operating system in real-time via `maverick/system/monitor.py`:
- **Hardware Resources:** Overall CPU%, per-core CPU usage (24 threads), memory total/available/percent, swap usage, disk capacity on root and home mounts.
- **Battery & Thermal:** Battery percentage, AC power plug status, charge rates.
- **Core AI Service Health:**
  - OpenClaw AI Gateway (`127.0.0.1:18789`)
  - Whisper STT Server (`127.0.0.1:18791`)
  - Video Device node (`/dev/video0`)
  - Audio sinks (`PipeWire` / `ALSA`)

---

## 2. Active CLI Token & Secret Scrubbing

Process inspection (`get_sanitized_processes()`) iterates through top active processes by CPU and memory. Because developers frequently execute commands containing sensitive CLI flags, a strict regex redactor scrubs every command line argument:
- Tokens matching `token`, `key`, `secret`, `password`, `auth`, `bearer` are replaced with `[REDACTED]`.
- Overly long binary string arguments ($>80$ characters) are truncated with an ellipsis.
- Tested in `tests/test_system_monitor.py`: Verifies that arguments such as `--api-key=sk-ant-api03-...` or `export GITHUB_TOKEN=...` are completely sanitized before leaving the process monitoring subsystem.
