# MAVEN AI Agent — Operational Workflows & Interaction Scenarios

> **Guide to Core Operational Workflows:** Step-by-step procedures for voice interaction, desktop automation, safety approvals, multimodal vision gestures, and emergency stops.

---

## 1. End-to-End Voice Interaction Workflow

```mermaid
sequenceDiagram
    autonumber
    actor User as User ("Pak Firza")
    participant Mic as Audio Ingress
    participant Clap as DualClapDetector
    participant Wake as WakeWordDetector
    participant STT as Whisper.cpp STT
    participant Core as MavenAgentCore
    participant TTS as TTS Engine (spd-say)

    User->>Mic: "Hey Maven" or [Clap-Clap]
    alt Trigger via Dual Clap
        Mic->>Clap: Acoustic Waveform Chunk
        Clap->>Clap: FFT Ratio >= 0.45, Cadence 350ms
        Clap->>Core: Signal: Open GUI & Listen
    else Trigger via Acoustic Wake Word
        Mic->>Wake: Speech Energy Onset
        Wake->>Wake: Spectral Match "Hey Maven"
        Wake->>Core: Signal: Wake Acknowledged
    end

    Core->>TTS: Speak Acknowledgment ("Yes, Sir" / "Ya, saya mendengarkan")
    TTS-->>User: [Spoken Confirmation]
    
    User->>Mic: "Periksa kondisi baterai dan CPU sekarang"
    Mic->>STT: PCM Audio Buffer
    STT->>STT: Silence Gated VAD & Local Whisper Decoding
    STT->>Core: "periksa kondisi baterai dan cpu sekarang"
    
    Core->>Core: Intent Classified: system_telemetry (Local Fast-Path)
    Core->>Core: Execute system_telemetry (< 2ms)
    Core->>TTS: "Diagnostik sistem selesai, Sir. CPU di 0.3 persen, baterai 91 persen dan sedang mengisi daya."
    TTS-->>User: [Spoken Results Delivered]
```

---

## 2. Autonomous Developer Workspace Preparation Workflow

This workflow orchestrates multi-step developer environment setup (e.g., inspecting project folders, launching VS Code, and gating terminal launch):

```mermaid
flowchart TD
    START["User: 'Maven, siapkan environment dev untuk CampusLink'"] --> PARSE["Intent Classifier: TASK_EXECUTION (action: prepare_dev)"]
    PARSE --> BUILD_PLAN["TaskPlanner: Synthesize 3-Step DAG Plan"]
    
    BUILD_PLAN --> STEP1["Step 1: filesystem_list_dir('~/projects/CampusLink')<br/>Risk Tier: Read-Only"]
    STEP1 --> RUN1["Execute filesystem_list_dir<br/>Result: Directory Exists (3 files found)"]
    
    RUN1 --> STEP2["Step 2: desktop_launch_app('code', '~/projects/CampusLink')<br/>Risk Tier: Autonomous Safe"]
    STEP2 --> RUN2["Execute desktop_launch_app<br/>Result: VS Code Opened with Project Root"]
    
    RUN2 --> STEP3{"Step 3: desktop_launch_app('gnome-terminal')<br/>Risk Tier: High-Risk Gated"}
    STEP3 --> PAUSE["Execution Halted: AWAITING_APPROVAL<br/>HUD Displays Approval Banner"]
    PAUSE --> SPEAK_PROMPT["Voice: 'Langkah peluncuran terminal memerlukan persetujuan. Katakan konfirmasi untuk menjalankan.'"]
    
    SPEAK_PROMPT --> USER_DECISION{"User Utterance"}
    USER_DECISION -- "'Konfirmasi' / 'Confirm'" --> RUN3["Execute gnome-terminal in project path<br/>Plan Status: COMPLETED"]
    USER_DECISION -- "'Batal' / 'Reject'" --> CANCEL["Step 3 Dropped<br/>Plan Status: COMPLETED_PARTIAL"]
    
    RUN3 --> FINAL_REPORT["Voice: 'Lingkungan kerja CampusLink telah siap sepenuhnya, Sir.'"]
    CANCEL --> CANCEL_REPORT["Voice: 'Peluncuran terminal dibatalkan, Sir. VS Code tetap terbuka.'"]
```

---

## 3. Universal Computer Use & AT-SPI2 Accessibility Workflow

When interacting with arbitrary Linux desktop graphical applications:

```mermaid
sequenceDiagram
    autonumber
    actor Core as MavenAgentCore
    participant CompAgent as ComputerUseAgent
    participant Atspi as Accessibility Engine (AT-SPI2)
    participant Input as VirtualMouse / UInput
    participant App as Target GUI Application (e.g. Chrome / Files)

    Core->>CompAgent: Task: Click "Submit Application" button
    CompAgent->>Atspi: Query active desktop window tree
    Atspi-->>CompAgent: Parsed Tree (Role: PUSH_BUTTON, Name: "Submit Application", Rect: [450, 320, 120, 36])
    
    alt Strategy 1: Direct AT-SPI Invocation (Fastest, zero cursor movement)
        CompAgent->>Atspi: Atspi.Action.do_action(index=0)
        Atspi->>App: Invoke native click handler
        App-->>CompAgent: Button state transitioned to PRESSED
    else Strategy 2: Center-Point Coordinate Click
        CompAgent->>Input: Move cursor to (450 + 60, 320 + 18) = (510, 338)
        Input->>App: Emit native BTN_LEFT click
    end
    
    CompAgent->>Atspi: Post-action verification probe
    Atspi-->>CompAgent: Verify modal dialog appeared
    CompAgent-->>Core: Action verified successfully (24ms elapsed)
```

---

## 4. Hardware Safety & Emergency Stop (E-Stop) Workflow

```mermaid
flowchart TD
    TRIGGER["E-Stop Trigger Detected:<br/>1. Voice: 'EMERGENCY STOP' / 'STOP ALL'<br/>2. HUD: Red E-Stop Button Click<br/>3. Keyboard: Emergency Shortcut"] --> HALT_EXEC["Engage Global Security E-Stop Flag"]
    
    HALT_EXEC --> HALT_INPUT["VirtualMouse: Instantly release all pressed buttons and lock input thread"]
    HALT_EXEC --> HALT_DAG["TaskPlanner: Cancel active DAG plan and mark running step as FAILED"]
    HALT_EXEC --> HALT_SUB["Agents: Shutdown active specialized agent threads"]
    HALT_EXEC --> HALT_VISION["VisionController: Release /dev/video0 and disable camera capture"]
    
    HALT_INPUT & HALT_DAG & HALT_SUB & HALT_VISION --> NOTIFY["Broadcast E-Stop Event via WebSocket (:8765)"]
    NOTIFY --> SPOKEN["Voice: 'Emergency stop engaged. All active automation halted.'"]
    SPOKEN --> LOCKED_STATE["System enters SAFE_IDLE Lockout<br/>Manual operator re-arm required"]
```

All E-Stop trigger paths execute synchronously within **$< 5$ milliseconds**, ensuring physical safety and preventing errant cursor or terminal actions.
