# MAVEN AI Agent — User Guide & Operator Manual

> **Welcome to MAVEN:** Your intelligent, voice-driven autonomous Linux desktop companion.

---

## 1. Quick Start Guide

### 1.1 Waking MAVEN Up
You can activate MAVEN using any of three natural ingress methods:
1. **Acoustic Wake Word:** Speak **"Hey Maven"**, **"Maven"**, or **"Halo Maven"**.
2. **Dual-Clap Gesture:** Clap your hands twice in natural rhythm (between 180ms and 750ms apart). The holographic HUD will automatically spring onto your screen and enter *Listening* mode.
3. **HUD Microphone Icon:** Click the glowing microphone button at the bottom right of the Control Center interface.

### 1.2 Dismissing MAVEN
- **Single Clap:** Clap your hands once firmly. The HUD window will smoothly hide to the background and silence any active speech.
- **Close Button (X):** Click the top-right exit button in the HUD header.

---

## 2. Voice Command Library & Real Examples

MAVEN understands both **Bahasa Indonesia** and **English** fluently.

### 2.1 System Telemetry & Hardware Status
| You Say (Indonesian / English) | What MAVEN Does | MAVEN's Response |
| :--- | :--- | :--- |
| *"Cek status baterai dan CPU sekarang"* | Queries live CPU cores and battery charging state. | *"Diagnostik sistem selesai, Sir. CPU di 0.3 persen, baterai 91 persen dan sedang mengisi daya."* |
| *"How much RAM is available?"* | Checks active RAM and swap usage. | *"You have 5.3 gigabytes of RAM available, with 63 percent total usage, Sir."* |
| *"Aplikasi apa saja yang sedang berjalan?"* | Inspects running authorized desktop applications. | *"Saat ini terdapat 2 aplikasi yang sedang berjalan: Spotify dan Google Chrome."* |

### 2.2 Autonomous Developer Workflows
| You Say | What MAVEN Does | MAVEN's Response |
| :--- | :--- | :--- |
| *"Maven, siapkan environment dev untuk CampusLink"* | Inspects directory, launches Visual Studio Code, and prepares the terminal. | *"Rencana tugas disiapkan: siapkan environment development untuk CampusLink. Langkah buka terminal memerlukan persetujuan. Katakan 'konfirmasi' untuk menjalankan."* |
| *"Konfirmasi"* (or *"Confirm"*) | Executes the gated terminal step. | *"Langkah disetujui, Sir. Terminal telah diluncurkan di folder CampusLink."* |

### 2.3 Media & Spotify Control
| You Say | What MAVEN Does | MAVEN's Response |
| :--- | :--- | :--- |
| *"Putar musik di Spotify"* | Resumes Spotify playback via D-Bus. | *"Melanjutkan pemutaran musik di Spotify, Sir."* |
| *"Volume Spotify set ke 70 persen"* | Adjusts player volume directly. | *"Volume Spotify diatur ke 70 persen, Sir."* |
| *"Lagu apa yang sedang diputar?"* | Queries track metadata. | *"Sedang memutar Ambient Focus oleh Audio Library, Sir."* |

### 2.4 Context Memory & Fact Storage
| You Say | What MAVEN Does | MAVEN's Response |
| :--- | :--- | :--- |
| *"Ingat bahwa saya lebih suka tema gelap"* | Stores fact in SQLite & Vector index. | *"Sudah saya catat dalam memori: saya lebih suka tema gelap, Sir."* |
| *"Apa tema favorit saya?"* | Searches memory via semantic recall. | *"Berdasarkan catatan memori, Anda lebih menyukai tema gelap, Sir."* |

---

## 3. Multimodal Vision & Gesture Control (Optional Mode)

When Vision Mode is enabled:
- **Hover Cursor:** Move your open hand in front of the webcam. The desktop cursor smoothly mirrors your index finger tip.
- **Left Click:** Pinch your index finger and thumb together briefly.
- **Scroll:** Form a fist and move your hand vertically up or down.

---

## 4. Emergency Stop (E-Stop)

If any task or automated pointer action behaves unpredictably, immediately engage E-Stop via:
1. **Voice Directive:** Shout **"EMERGENCY STOP"** or **"DARURAT"**.
2. **HUD Button:** Click the flashing red **E-STOP** pill in the top navigation bar.

*All pointer automation, terminal executions, and background agents are frozen in under 5 milliseconds.*
