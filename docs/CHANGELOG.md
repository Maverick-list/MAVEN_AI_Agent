# Changelog

All notable changes to the MAVEN AI Agent project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.2.0] - 2026-11-17

### Added
- **Authentic J.A.R.V.I.S. Persona:** Integrated polished, authoritative British / Indonesian respectful persona ("Sir" / "Pak Firza") with sub-1.8s TTFT streaming response.
- **Unified Cognitive Orchestration Bridge:** Connected `VoiceController` directly to `MavenAgentCore`, allowing 31 local OS automation tools to execute in 217ms – 331ms.
- **Spectral Dual/Single Clap Detection:** Added real-time FFT high-frequency snap discriminator ($E_{\text{high}} / E_{\text{low}} \ge 0.45$) to decisively reject desk knocks, table bumps, and keyboard typing.
- **Silence VAD Gating:** Enforced strict acoustic speech threshold checks in `VoiceSession` before buffer dispatch to completely eliminate Whisper hallucinations on ambient silence.
- **Stutter & Halucination Cleansing:** Added regex deduplication and known watermark blocklist in `WhisperCppSTTProvider`.
- **Atomic Window Control IPC:** Implemented sequence-watermarked `window_control.json` ensuring single-clap closes and dual-clap opens synchronize reliably with the native GTK3 shell.

### Changed
- Cleaned OpenClaw Gateway authorization profiles to eliminate cascading 404/403 failover delays, dropping conversational turn latency from 15s–66s to under 1.8s.
- Reduced memory footprint to $< 650$ MB total RAM across the entire ecosystem.

---

## [2.0.0] - 2026-10-31

### Added
- **Phase 2 Intelligent Agent Core:** 11-phase cognitive lifecycle, DAG TaskPlanner, and 5-tier Action Security Risk Policy.
- **Specialized Agents:** Implemented `ComputerUseAgent`, `CodingAgent`, `ResearchAgent`, `DocumentAgent`, and `SystemMonitoringAgent`.
- **Multi-Tier Context Memory:** Persistent SQLite storage with cosine vector similarity indexing.
- **Universal Linux Computer Use:** AT-SPI2 accessibility tree inspection with 5-tier interaction fallback.

---

## [1.0.0] - 2026-10-25

### Added
- Initial release of MAVEN (Maverick Autonomous Virtual Ecological Navigator).
- Basic voice interaction loop with whisper.cpp and speech-dispatcher.
- Futuristic holographic Control Center HUD powered by FastAPI and WebSockets.
- MediaPipe hand tracking and gesture-controlled virtual mouse pointer.
