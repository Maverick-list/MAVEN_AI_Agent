# MAVEN JARVIS — INTELLIGENT AGENT CORE ARCHITECTURE SPECIFICATION
## Central Cognitive Orchestration, Multi-Tier Memory, 5-Tier Risk Governance & Specialized Agent Registry

**System:** Maverick DevOS (Maven JARVIS Evolution)  
**Branch:** `feature/jarvis-evolution`  
**Baseline Production Commit:** `f47dbd1`  
**Document Version:** 2.0.0-PROD  
**Author:** Principal AI Systems Architect & Autonomous Agent Specialist  

---

## 1. ARCHITECTURAL OVERVIEW & DESIGN PRINCIPLES

Maven JARVIS evolves from a set of discrete multimodal features (Whisper STT, Pocket TTS, MediaPipe hand gestures, AT-SPI2 computer-use, and OpenClaw LLM gateway) into a unified, coherent, and fault-tolerant **Intelligent Desktop AI Assistant**.

```
                                +------------------------------------------+
                                |               USER INTERFACES            |
                                |  Voice / Microphone | Web GUI / REST API |
                                +--------------------+---------------------+
                                                     |
                                                     v
                                +------------------------------------------+
                                |      CENTRAL COGNITIVE ORCHESTRATOR      |
                                |            (MavenAgentCore)              |
                                +--------------------+---------------------+
                                                     |
         +--------------------+----------------------+--------------------+--------------------+
         |                    |                      |                    |                    |
         v                    v                      v                    v                    v
+-----------------+  +-----------------+    +-----------------+  +-----------------+  +-----------------+
|  Intent Engine  |  | Multi-Tier Mem  |    | Risk & Security |  |  Task Planner   |  | Agent Registry  |
| (Classification |  |  (TTL, LRU,     |    |  (5-Tier Policy |  | (DAG Scheduler, |  |  (Lazy Init,    |
| & Ambiguity)    |  |  Sanitization)  |    |  & Audit Trail) |  |  Retry, Resume) |  |  LRU Eviction)  |
+-----------------+  +-----------------+    +-----------------+  +-----------------+  +--------+--------+
                                                                                               |
                                             +--------------------+----------------------------+
                                             |                    |                    |
                                             v                    v                    v
                                     +---------------+    +---------------+    +---------------+
                                     | ResearchAgent |    |  CodingAgent  |    |ComputerUseAgnt|
                                     +---------------+    +---------------+    +---------------+
                                     | DocumentAgent |    |MonitorAgent   |    | PlanningAgent |
                                     +---------------+    +---------------+    +---------------+
```

### Core Design Principles:
1. **Zero Memory Leaks & Bounded Concurrency:** All dynamic components are lazily instantiated on-demand, bounded by LRU caches, and automatically reclaimed after configurable idle timeouts.
2. **Defensive Security & Strict Attribution:** Actions with destructive or high-risk potential are irrevocably gated by human approval. Full action provenance (initiator, parent agent, risk tier) is recorded in audit logs.
3. **Deterministic Fail-Safe Fallbacks:** In cases of ambiguity, tool failure, or network disruption, the agent requests clarification or rolls back to known-safe states rather than guessing or executing destructive actions.
4. **Sub-Second Low-Latency Execution:** Single-turn queries bypass multi-step planning through specialized agent fast-paths, maintaining immediate response times while preserving audit integrity.
5. **Universal Emergency Stop:** A single hardware, voice, or GUI emergency command instantly severs execution loops, releases vision and audio devices, and locks down autonomous actions.

---

## 2. THE 11-PHASE COGNITIVE LIFECYCLE

Every user instruction (verbal or text) traverses an explicit 11-phase cognitive lifecycle managed deterministically by `MavenAgentCore`:

```
 [1. USER INPUT] ---> [2. INTENT UNDERSTANDING] ---> [3. CONTEXT RETRIEVAL]
                                                               |
                                                               v
 [6. APPROVAL GATE] <-- [5. RISK CLASSIFICATION] <-- [4. TASK PLANNING]
       |
       v (Approved / Auto-Approved)
 [7. TOOL EXECUTION] -> [8. OBSERVATION] -> [9. RESULT VERIFICATION]
                                                    |
                                                    v
 [11. USER RESPONSE] <-- [10. CONTEXT MEMORY UPDATE]
```

### Phase Details:
1. **User Input Ingestion:** Audio transcription via Whisper STT or text command via `/api/intelligence/plan` or `/api/chat`.
2. **Intent Understanding:** Rule-based and semantic classification of goal, action, target, parameters, and ambiguity rating.
3. **Context Retrieval:** Bounded vector/keyword retrieval of user preferences, active project metadata, and recent conversation turns from `ContextMemory`.
4. **Task Planning:** Decomposition of multi-step goals into a dependency-ordered Directed Acyclic Graph (DAG) with retry and rollback policies.
5. **Risk Classification:** Real-time parameter scanning mapping each step into one of 5 canonical risk tiers.
6. **Approval Gate:** Autonomous pause and user prompting if any step meets `HIGH_RISK` or `DESTRUCTIVE` thresholds.
7. **Tool & Action Execution:** Invocation of sandboxed tools, desktop automation, or specialized domain agents.
8. **Observation & Multi-Modal Feedback:** Capture of stdout, AT-SPI2 accessibility tree changes, exit codes, and screen status.
9. **Result Verification:** Deterministic sanity checks to ensure expected post-conditions are met; automatic retry if failures occur.
10. **Context Memory Update:** Storage of task outcomes, updated project state, and user preferences with automatic credential scrubbing.
11. **User Response Synthesis:** Generation of concise voice output (Pocket TTS) and rich visual dashboard telemetry updates.

---

## 3. MULTI-TIER CONTEXT MEMORY SUBSYSTEM

Memory is partitioned into 6 canonical categories with strictly enforced TTL (Time-To-Live) and LRU capacity bounds, preventing unbounded RAM or disk growth over extended usage:

| Category | Description | Default TTL | Max Entries | Persistence |
| :--- | :--- | :--- | :--- | :--- |
| `SHORT_TERM_CONVERSATION` | Dialog turns, session context | 24 Hours | 100 entries | Memory & Disk |
| `ACTIVE_TASK` | Active plan status, current step, blockers | 12 Hours | 5 entries | Memory & Disk |
| `USER_PREFERENCES` | Themes, language preferences, defaults | Infinite (None) | 200 entries | Memory & Disk |
| `PROJECT_CONTEXT` | Workspace paths, tech stacks, repositories | 30 Days | 50 entries | Memory & Disk |
| `TASK_HISTORY` | Completed / failed task execution summaries | 7 Days | 100 entries | Memory & Disk |
| `VERIFIED_KNOWLEDGE` | Validated facts, environment configurations | Infinite (None) | 500 entries | Memory & Disk |

### Security & Sanitization:
- **Credential Scrubbing:** All text written to memory automatically passes through `redact_sensitive_text()`. API keys (`sk-*`, `AIza*`), bearer tokens, and passwords are masked before persisting to disk.
- **Strict File Permissions:** Memory JSON stores are created with `0o600` permissions inside `~/.config/maverick/`.
- **User-Controlled Wipe:** Users can selectively clear specific categories or perform a total wipe via `/api/intelligence/memory/wipe`.

---

## 4. 5-TIER RISK TAXONOMY & HUMAN APPROVAL GATING

To prevent unauthorized, unexpected, or destructive side-effects, Maven enforces a 5-tier risk taxonomy:

```
+------------------+-------------------------------------------------------+---------------------+
| Risk Tier        | Permitted Action Types                                | Approval Required?  |
+------------------+-------------------------------------------------------+---------------------+
| READ_ONLY        | Status queries, inspections, file reads, telemetry     | No (Auto-approved)  |
| REVERSIBLE       | Cursor move, scroll, hover, temp files, app focus     | No (Auto-approved)  |
| MODERATE_RISK    | Safe app launch, workspace file edits, volume changes | Configurable        |
| HIGH_RISK        | Git push, overwriting files, network requests, tokens | Yes (Mandatory)     |
| DESTRUCTIVE      | File deletion, sudo/root commands, formatting, reboot | Yes (Mandatory)     |
+------------------+-------------------------------------------------------+---------------------+
```

### Action Provenance:
Every action retains an immutable provenance record:
```json
{
  "action_id": "act_1793468000123",
  "initiator": "user_voice",
  "parent_agent": "coding_agent",
  "risk_tier": "destructive",
  "status": "awaiting_approval",
  "created_at": 1793468000.123
}
```

---

## 5. SPECIALIZED MULTI-AGENT ARCHITECTURE

The agent registry coordinates specialized agents using **lazy initialization** and **LRU concurrency limits**:

1. **Research Agent (`ResearchAgent`):** Performs web search, doc synthesis, fact gathering, and external research without cluttering workspace state.
2. **Coding Agent (`CodingAgent`):** Analyzes Python ASTs, navigates code symbols, performs codebase grep, and validates syntax.
3. **Computer Use Agent (`ComputerUseAgent`):** Orchestrates GUI automation through AT-SPI2 accessibility queries, clicks, keystrokes, and visual verification.
4. **Document Agent (`DocumentAgent`):** Generates structured Markdown, PDF, and DOCX documents with automated quality checks.
5. **System Monitoring Agent (`SystemMonitoringAgent`):** Tracks RAM/CPU utilization, manages operating mode transitions, and monitors health.
6. **Planning Agent (`PlanningAgent`):** Synthesizes multi-step dependency DAGs, monitors step execution, and orchestrates rollbacks.

### Memory Optimization Rules:
- Maximum concurrent active agents: `max_active_agents = 4` (configurable).
- When a new agent is required and capacity is saturated, the least recently used agent is gracefully shut down.
- Idle agents automatically self-evict after their configured idle timeout (e.g. 60–300s).

---

## 6. COMPUTER USE INTEGRATION: OBSERVE-PLAN-ACT-VERIFY

The Computer Use agent adheres strictly to a 4-step verified interaction loop:
1. **Observe:** Inspect current active window, focused widget, and AT-SPI2 accessibility tree node coordinates.
2. **Plan:** Calculate bounding box, target click coordinates, or key sequence.
3. **Act:** Issue synthetic hardware events (`libevdev` / `uinput` / `XTest`).
4. **Verify:** Re-query accessibility state or capture frame delta to confirm focus/state transition occurred. If unconfirmed, retry up to `max_retries` before aborting.

---

## 7. FAIL-SAFE & EMERGENCY STOP PROTOCOLS

Emergency Stop can be triggered from:
- Voice: *"Maven, emergency stop"* / *"Berhenti darurat"*
- GUI: Dashboard Emergency Stop button (`/api/emergency-stop`)
- REST API: POST `/api/intelligence/cancel` or `/api/emergency-stop`
- Physical Hardware: User mouse movement override (instant pointer disconnect)

**Upon Emergency Stop:**
1. `AgentSecurityManager.is_emergency_stopped` is set to `True`.
2. All running task plans transition to `CANCELLED`.
3. All specialized agents are shut down immediately.
4. Camera stream and MediaPipe hand tracking are terminated.
5. Audio playback (Pocket TTS) is instantly silenced.
6. Subsequent instructions are rejected with `emergency_blocked` until explicitly cleared.
