# 🏛️ MAVEN JARVIS Development History & Phase Progression

This directory archives the engineering progression, benchmark reports, hardware integration logs, and security audit documentation of the **MAVEN JARVIS** autonomous operating agent from inception through production release.

---

## 📅 Architecture Progression Roadmap

```mermaid
timeline
    title MAVEN JARVIS Development & Evolutionary Phases
    section Inception & Core
        Phase 1 - Monolithic Baseline : CLI architecture : Process management : Basic launcher
        Phase 2 - Desktop Integration : Spotify MPRIS : System telemetry : Linux utility wrappers
    section Context & Web Automation
        Phase 3 - Desktop Context Engine : Window geometry : Active app tracking : AT-SPI2 hooks
        Phase 3.1 - Isolated Browser CDP : Headless / visible Chrome automation : Session sandboxing
    section Voice & Security Hardening
        Phase 4 - Hands-Free Voice Engine : Two-pass wake word ("Hey Maven") : AVX-512 whisper.cpp : Local TTS
        Phase 4.1 - Security Audit : 5-Tier risk policy : E-Stop lockdown : Confirmation gates
    section Hardware Optimization & Production
        Phase 5.1 & 5.2 - Hardware Calibration : Realtek ALC294 DSP : Noise floor adaptive VAD : Bilingual ID/EN
        Phase 5.3 - Unified Production CLI : systemd user services : Zero-latency dispatch
    section J.A.R.V.I.S. Evolution (v2.2.0)
        Evolution & Holographic HUD : Glassmorphism GTK dashboard : Silence VAD gating : MediaPipe vision : Dual-clap sensor
```

---

## 📂 Phase Reports Directory (`development/phase-reports/`)

The implementation and benchmark reports detailing each milestone are organized chronologically:

| Report | Phase & Focus | Key Achievements & Metrics |
| :--- | :--- | :--- |
| [`PHASE2_REPORT.md`](./phase-reports/PHASE2_REPORT.md) | **Phase 2: Desktop Integration** | System telemetry hooks, desktop application launching, Spotify MPRIS D-Bus client. |
| [`PHASE3_REPORT.md`](./phase-reports/PHASE3_REPORT.md) | **Phase 3: Context & Accessibility** | AT-SPI2 accessibility tree integration, Wayland active window detection, visual state capture. |
| [`PHASE3_1_REPORT.md`](./phase-reports/PHASE3_1_REPORT.md) | **Phase 3.1: Browser Automation** | Chrome DevTools Protocol (CDP) WebSocket bridge, isolated profile management, web task execution. |
| [`PHASE4_REPORT.md`](./phase-reports/PHASE4_REPORT.md) | **Phase 4: Hands-Free Voice Subsystem** | Prefix-anchored two-pass wake-word detector, local whisper.cpp tiny.en/id inference, sub-2s response latency. |
| [`PHASE5_1_REPORT.md`](./phase-reports/PHASE5_1_REPORT.md) | **Phase 5.1: Real-Time Audio DSP** | PulseAudio/PipeWire ringbuffer streaming, dynamic noise floor estimation, zero audio drops. |
| [`PHASE5_2_REPORT.md`](./phase-reports/PHASE5_2_REPORT.md) | **Phase 5.2: Bilingual Intent Engine** | 50-trial verification matrix in English & Indonesian, regex fallback normalizers, 100% intent dispatch rate. |
| [`PHASE5_3_REPORT.md`](./phase-reports/PHASE5_3_REPORT.md) | **Phase 5.3: Production Verification** | Stress testing under memory pressure, CPU usage $< 1.5\%$, automated background daemon supervision. |
| [`PHASE5_HARDWARE_REPORT.md`](./phase-reports/PHASE5_HARDWARE_REPORT.md) | **Phase 5 Hardware Calibration** | ASUS ROG Strix G16 (Ryzen 9 7845HX, ALC294) mic array calibration, gain staging, AVX-512 profiling. |
| [`PHASE5_IMPLEMENTATION_REPORT.md`](./phase-reports/PHASE5_IMPLEMENTATION_REPORT.md) | **Phase 5 Technical Summary** | End-to-end integration specifications, IPC data structures, unified `maven` CLI architecture. |

---

## 🛡️ Security Audits (`development/security-audits/`)

| Audit Report | Scope | Key Findings & Remediations |
| :--- | :--- | :--- |
| [`PHASE4_1_SECURITY_AUDIT.md`](./security-audits/PHASE4_1_SECURITY_AUDIT.md) | **System Sandbox & Policy Audit** | Implementation of the 5-Tier Action Risk Gate, vocal confirmation safeguards for destructive bash commands, and instant Emergency Stop (E-Stop). |

---

## 🔄 Relationship to Main Documentation (`docs/`)

The reports archived here represent point-in-time milestones and verification records. For current, active system documentation, refer to the root `docs/` hierarchy:

- [System Architecture](../docs/ARCHITECTURE.md)
- [System Design & FSM](../docs/SYSTEM_DESIGN.md)
- [Algorithms & Mathematics](../docs/ALGORITHM.md)
- [Workflows & Sequences](../docs/WORKFLOW.md)
- [API & IPC Reference](../docs/API_DOCUMENTATION.md)
- [Security Guidelines](../docs/SECURITY.md)
- [Installation Guide](../docs/INSTALLATION.md)
