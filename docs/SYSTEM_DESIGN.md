# MAVEN AI Agent — System Design & Subsystem Specifications

> **Scope:** Inter-Process Communication (IPC), Threading Architecture, State Machines, Data Contracts, and Fault Tolerance.

---

## 1. System Decomposition & IPC Architecture

MAVEN runs as an integrated ecosystem of microservices and background daemons managed by systemd user services. The subsystems communicate via lightweight, zero-copy local loopback interfaces, shared Unix domain sockets, and thread-safe queues.

```mermaid
flowchart LR
    subgraph System_Daemons ["Systemd User Units"]
        SERVICE_VOICE["maven-jarvis.service<br/>(Voice & Cognitive Daemon)"]
        SERVICE_GUI["maven-jarvis-gui.service<br/>(GTK3 / WebKit2 Shell)"]
        WHISPER_SRV["whisper-server<br/>(:18791 AVX-512)"]
    end

    subgraph State_Storage ["Runtime State & IPC Directory (~/.local/state/maverick)"]
        IPC_WIN["window_control.json<br/>(Clap & Focus Signals)"]
        IPC_MEM["context_memory.sqlite<br/>(WAL Mode Database)"]
        IPC_TASKS["tasks.sqlite<br/>(DAG State Store)"]
        IPC_LOG["maven-voice.log<br/>(Structured Activity Stream)"]
    end

    SERVICE_VOICE -- "HTTP POST (wav bytes)" --> WHISPER_SRV
    SERVICE_VOICE -- "Write Window Action" --> IPC_WIN
    SERVICE_GUI -- "Poll Sequence State (100ms)" --> IPC_WIN
    SERVICE_VOICE <--> IPC_MEM
    SERVICE_VOICE <--> IPC_TASKS
    SERVICE_VOICE --> IPC_LOG
    SERVICE_GUI -- "WebSocket WS (:8765)" --> SERVICE_VOICE
```

---

## 2. Voice State Machine (7-State FSM)

The voice interaction lifecycle is orchestrated by a deterministic 7-state finite state machine in [`maverick/voice/session.py`](../maverick/voice/session.py):

```mermaid
stateDiagram-v2
    [*] --> IDLE

    IDLE --> WAKE_WORD_DETECTED: Wake Word ("Hey Maven") or Dual-Clap
    IDLE --> IDLE: Single-Clap (Close Window / Mute)

    WAKE_WORD_DETECTED --> LISTENING: Acknowledgment Spoken ("Yes, Sir")

    LISTENING --> PROCESSING: Trailing Silence Detected (RMS < Threshold)
    LISTENING --> IDLE: Silence Timeout (Discard Ambient Noise)
    LISTENING --> IDLE: Single-Clap (Cancel Listening)
    LISTENING --> LISTENING: Dual-Clap (Reset Speech Buffer)

    PROCESSING --> SPEAKING: Response Generated (Streaming Sentences)
    PROCESSING --> IDLE: Error or Empty Utterance

    SPEAKING --> IDLE: Speech Playback Finished
    SPEAKING --> INTERRUPTED: User Barges In / Audio Interrupt
    INTERRUPTED --> LISTENING: Immediate Re-listen
```

### State Definitions & Invariants
- **`IDLE`:** Microphones listen strictly for impulsive claps or wake-word acoustic energy bursts. No continuous speech-to-text decoding occurs, preserving CPU cycles and RAM.
- **`WAKE_WORD_DETECTED`:** Fast acoustic verification passes; emits window focus signal to GUI.
- **`LISTENING`:** Dynamically samples audio chunks into an in-memory buffer (`bytearray`). Enforces dynamic silence gating: if total time reaches maximum recording boundary without valid speech energy, the buffer is dropped to prevent Whisper hallucinations.
- **`PROCESSING`:** Audio buffer is converted to mono 16 kHz WAV in memory and transmitted to the STT server.
- **`SPEAKING`:** Sentences are spoken sequentially via the active TTS engine.
- **`INTERRUPTED`:** Barge-in handler immediately halts audio playback via `spd-say --cancel` or subprocess signals and transitions back to `LISTENING`.

---

## 3. Concurrency & Threading Model

MAVEN implements an asynchronous event loop combined with dedicated real-time worker threads to ensure user input is never blocked by heavy compute operations:

```mermaid
flowchart TD
    subgraph Main_Process ["Maven Main Process (PID: daemon)"]
        subgraph Audio_Thread ["Audio Capture Thread (High Priority)"]
            T_AUDIO["Continuous PyAudio Ring Buffer<br/>16kHz 16-bit Mono Chunking"]
        end

        subgraph Event_Loop ["Asyncio Event Loop (Main Thread)"]
            FASTAPI["FastAPI Control Center HUD (:8765)"]
            WS_BROADCAST["WebSocket Telemetry Broadcaster"]
            TASK_MANAGER["Async Task Scheduling"]
        end

        subgraph Cognitive_Worker ["Cognitive Worker Pool (ThreadPoolExecutor)"]
            CORE_EXEC["MavenAgentCore Instruction Dispatch"]
            PLAN_EXEC["DAG Step Executor"]
            OPENCLAW_STREAM["HTTP SSE OpenClaw/Gemini Streaming"]
        end

        subgraph Vision_Worker ["Vision Worker Thread (Optional Mode)"]
            CAM_LOOP["OpenCV VideoCapture (/dev/video0)"]
            MP_TRACK["MediaPipe Landmark Estimation"]
            VIRT_INPUT["UInput Event Injection"]
        end
    end

    T_AUDIO -- "Thread-safe Queue" --> Cognitive_Worker
    Cognitive_Worker -- "Async Broadcast" --> WS_BROADCAST
    Cognitive_Worker -- "State Sync" --> TASK_MANAGER
    Vision_Worker -- "Pointer Coordinates" --> Event_Loop
```

---

## 4. Multi-Tier Context Memory Engine

Context and long-term memory are managed by `ContextMemory` in [`maverick/intelligence/memory.py`](../maverick/intelligence/memory.py), structured across three persistent tiers:

```mermaid
erDiagram
    CONTEXT_MEMORY ||--o{ MEMORY_EMBEDDINGS : indexes
    CONTEXT_MEMORY {
        string id PK
        string category "preference, project, routine, fact, diagnostic"
        string content "Raw textual content"
        string tags "JSON list of tags"
        string source "user, tool, observation"
        float created_at
        float updated_at
        float expires_at
        int access_count
        string metadata_json
    }

    TASK_STORE ||--o{ TASK_STEPS : contains
    TASK_STORE {
        string plan_id PK
        string goal
        string status "created, running, completed, failed, paused"
        float created_at
        float completed_at
        float progress
        string summary
    }

    TASK_STEPS {
        int step_id PK
        string plan_id FK
        string description
        string tool_name
        string parameters_json
        string dependencies_json
        string status
        string result_json
        string error
        float elapsed_ms
    }
```

### Memory Tier Separation
1. **Tier 1 — Short-Term Turn Buffer:** Retains the last 8 conversation turns in memory for immediate pronoun and anaphora resolution ("buka yang tadi", "tutup itu").
2. **Tier 2 — SQLite Persistent Record Store:** Stores structured user preferences, developer environment configurations, and past action traces in `~/.local/state/maverick/context_memory.sqlite` with WAL mode enabled.
3. **Tier 3 — Vector Semantic Recall:** Computes local embeddings for fuzzy semantic match, allowing natural language queries ("bagaimana cara setup database kemarin?") to recall historical instructions with cosine similarity $\ge 0.72$.

---

## 5. Security & Risk Gating Pipeline

All actions evaluated by `AgentSecurityManager` pass through a strict 5-tier policy matrix:

| Risk Tier | Definition | Examples | Execution Mode |
| :--- | :--- | :--- | :--- |
| **Tier 1: Read-Only** | Information gathering with zero state mutation. | Read files, check CPU/RAM, list apps, inspect window tree. | **Fully Autonomous** (No prompt) |
| **Tier 2: Autonomous Safe** | Benign state change within user workspace. | Create project dir, write test code, focus existing app. | **Autonomous with Audit Log** |
| **Tier 3: Low-Risk Confirm** | Non-destructive system action affecting user focus. | Launch new heavy browser, change system volume, switch modes. | **Autonomous / Audible Notice** |
| **Tier 4: High-Risk Gated** | Actions that modify system state, delete files, or execute CLI. | Launch terminal, run shell commands, delete files, install packages. | **Strictly Gated** (Requires "confirm") |
| **Tier 5: Prohibited** | Dangerous commands that can harm OS or compromise system. | `rm -rf /`, `dd`, `mkfs`, fork bombs, unauthorized sudo. | **Hard-Blocked & E-Stop Triggered** |

---

## 6. Fault Tolerance & Graceful Degradation

```mermaid
flowchart TD
    INPUT["User Voice Utterance"] --> GATEWAY_TRY["Route to Streaming Engine"]
    GATEWAY_TRY -->|Success (200)| RESP_STREAM["Immediate Spoken Sentence Streaming"]

    GATEWAY_TRY -->|HTTP 404 / 403 / 429| ROTATE["Route Fallback / Sanitization"]
    ROTATE --> COOLDOWN["Mark Model in Route Cooldown"]
    COOLDOWN --> LOCAL_FALLBACK["Fallback to Local MavenAgentCore Tool Results"]
    LOCAL_FALLBACK --> SANITIZED_SPEAK["Speak Concise Calm Status to User"]
```

1. **Dead Auth & Key Failover:** If an external LLM route reports rate limits (`429`) or credential failure (`403`), the route is quarantined with an adaptive cooldown timer, falling back instantly to verified local tools and spoken notifications without throwing unhandled exceptions.
2. **Crash-Safe SQLite:** All SQLite database connections use `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL`, preventing database corruption even if power is abruptly disconnected.
3. **Subprocess Watchdogs:** External binaries (`whisper-server`, browser CDP, audio recording) run under explicit process timeouts (`subprocess.run(timeout=...)`) with automatic PID reaping.
