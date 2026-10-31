# Maven JARVIS — Implementation Plan
**Detailed Engineering Execution Plan & File Modification Strategy**
*Document Version: 1.0.0 | Date: October 31, 2026 | Environment: Ubuntu 26.04.1 LTS (Wayland)*

---

## 1. Execution Principles & Safeguards

To maintain zero disruption to the ongoing 7-Day Usage Trial and ensure pristine code hygiene:
1. **Isolated Worktree:** All feature development will take place in an isolated Git branch/worktree (`feature/jarvis-evolution`).
2. **Backward Compatibility:** All existing entry points (`maverick.cli`, `maverick.desktop.app`, `TaskPlanner`, `ToolRegistry`) must preserve their public interfaces and return structures.
3. **Continuous Regression Testing:** Automated unit tests will be executed after every milestone, requiring 100% pass rate.
4. **Rollback Points:** Git tags will be created before each major phase transition.

---

## 2. Step-by-Step Implementation Breakdown

### Milestone 1: Phase B — Reliability & Lifecycle Hardening

#### Step 1.1: Security Sandbox Patch (Canonical Path Resolution)
- **Target File:** [`maverick/intelligence/tools.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/intelligence/tools.py)
- **Modifications:**
  - Update `_tool_filesystem_create_dir` and `_tool_filesystem_write_file`.
  - Replace naive `os.path.expanduser()` checks with `os.path.realpath()`.
  - Validate target canonical path starts with canonical `$HOME/` or `/tmp/`.
  - Prohibit writing into sensitive hidden dotdirectories (`~/.ssh`, `~/.bashrc`, `~/.config`) without explicit bypass flag.
- **Verification:** New test in `tests/test_security.py` verifying path traversal attempts (`~/../../etc/passwd`) are blocked with `SecurityPolicyViolationError`.

#### Step 1.2: Virtual Input Watchdog & Auto-Release
- **Target File:** [`maverick/vision/virtual_input.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/vision/virtual_input.py)
- **Modifications:**
  - Add `_watchdog_timer` in `VirtualMouse` to auto-release held mouse buttons if not refreshed within 3.0 seconds.
  - Implement instant release hook when `mode_manager.py` signals physical mouse interception.
- **Verification:** Unit test simulating stuck mouse button and confirming automatic release after timeout.

#### Step 1.3: Dynamic System Dependency Verifier
- **Target File:** Create [`maverick/core/dependencies.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/core/dependencies.py)
- **Modifications:**
  - Implement `SystemDependencyVerifier` checking binary availability (`which code`, `which libreoffice`, `which google-chrome`, etc.).
  - Cache results with 60-second TTL.
  - Export convenient helper `has_dependency(name: str) -> bool`.

---

### Milestone 2: Phase C — Unified Orchestrator & Dynamic DAG Planning

#### Step 2.1: Formal Task Lifecycle State Machine
- **Target File:** [`maverick/intelligence/planner.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/intelligence/planner.py)
- **Modifications:**
  - Expand `TaskStatus(Enum)`:
    - `CREATED = "created"`
    - `UNDERSTANDING = "understanding"`
    - `PLANNING = "planning"`
    - `AWAITING_APPROVAL = "awaiting_approval"`
    - `EXECUTING = "executing"`
    - `VERIFYING = "verifying"`
    - `RECOVERING = "recovering"`
    - `COMPLETED = "completed"`
    - `FAILED = "failed"`
  - Add `verification_criteria` and `rollback_action` fields to `TaskStep`.

#### Step 2.2: Generative LLM-Assisted DAG Planner
- **Target File:** [`maverick/intelligence/planner.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/intelligence/planner.py)
- **Modifications:**
  - Implement `_synthesize_llm_dag(goal: str, context: str) -> List[TaskStep]`.
  - Connect to local/cloud Gemini Flash model with structured JSON output prompt containing available tool schemas.
  - Retain existing rule-based patterns as instant local zero-latency fallbacks when prompt matches dev/code/diagnostics templates.
  - Add topological sort to validate that step dependencies form a strict acyclic graph.

#### Step 2.3: Persistent Task Storage Engine
- **Target File:** Create [`maverick/intelligence/task_store.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/intelligence/task_store.py)
- **Modifications:**
  - Implement `SQLiteTaskStore` utilizing `~/.maverick/tasks.db` with WAL mode.
  - Schema: `plans(plan_id TEXT PRIMARY KEY, goal TEXT, status TEXT, created_at REAL, completed_at REAL, payload JSON)`.
  - Methods: `save_plan(plan)`, `get_plan(plan_id)`, `list_recent_plans(limit=20)`.
  - Integrate into `TaskPlanner` so plans persist across server restarts.

#### Step 2.4: Outcome Verification Engine
- **Target File:** [`maverick/intelligence/planner.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/intelligence/planner.py)
- **Modifications:**
  - Introduce `_verify_step_outcome(step: TaskStep) -> Tuple[bool, str]`.
  - Verifies file creation, non-empty content, zero process exit code, or screen element visibility.

---

### Milestone 3: Phase D — Multi-Functional Tool Expansion

#### Step 3.1: Codebase Exploration & AST Navigation Tool
- **Target File:** Create [`maverick/intelligence/tools/codebase.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/intelligence/tools/codebase.py)
- **Capabilities:**
  - `codebase_find_symbols(path, symbol_name)`: Uses Python `ast` to locate classes, functions, and docstrings.
  - `codebase_grep_pattern(path, regex, file_pattern)`: Fast regex search with bounded line limits.
  - Register as `codebase_explore` in `ToolRegistry`.

#### Step 3.2: Document & Report Generation Tool
- **Target File:** Create [`maverick/intelligence/tools/documents.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/intelligence/tools/documents.py)
- **Capabilities:**
  - `document_generate_markdown(path, title, sections)`: Structured Markdown creation.
  - `document_generate_docx(path, title, sections)`: Word DOCX creation via `docx` library (with fallback).
  - `document_generate_pdf(path, title, content)`: Clean PDF report generation via `reportlab` or text-to-pdf pipeline.
  - Register as `document_generate` in `ToolRegistry`.

#### Step 3.3: Web Research & Synthesis Tool
- **Target File:** Create [`maverick/intelligence/tools/research.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/intelligence/tools/research.py)
- **Capabilities:**
  - `web_research_query(query)`: Leverages browser CDP or search endpoint, strips boilerplate, extracts key paragraphs, and returns synthesized citations.
  - Register as `web_research` in `ToolRegistry`.

---

### Milestone 4: Phase E — Conversational & Voice Refinements

#### Step 4.1: Instant Barge-in Interruption Hook
- **Target File:** [`maverick/voice/controller.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/voice/controller.py)
- **Modifications:**
  - In speech output loop, monitor voice activity flag from microphone stream.
  - If user begins speaking during TTS playback, immediately send abort signal to audio player process (`paplay` / `pw-play` / sounddevice).

#### Step 4.2: Mixed-Language (ID/EN) Intent Normalizer
- **Target File:** [`maverick/voice/intent.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/voice/intent.py)
- **Modifications:**
  - Add bilingual synonym dictionary mapping common Indonesian action verbs (`buka`, `tutup`, `jalankan`, `cari`, `ringkas`, `ingat`) to canonical intent keys.

---

### Milestone 5: Phase F — Control Center HUD & UI Evolution

#### Step 5.1: Live DAG Execution Visualizer Component
- **Target File:** [`maverick/dashboard/static/index.html`](file:///home/firza-ilmi/Maverick-DevOS/maverick/dashboard/static/index.html) or dashboard JS components
- **Modifications:**
  - Render an interactive step graph showing step ID, description, tool name, status pill (`PENDING`, `RUNNING`, `COMPLETED`, `AWAITING_APPROVAL`), and execution latency.
  - Add inline "Approve" and "Reject" buttons for steps awaiting confirmation.

#### Step 5.2: SSE Event Dispatcher for Real-Time Plan Updates
- **Target File:** [`maverick/dashboard/server.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/dashboard/server.py)
- **Modifications:**
  - Dispatch SSE events `task_plan_created`, `task_step_started`, `task_step_finished`, `task_plan_completed` to all connected clients.

---

### Milestone 6: Phase G — Acceptance Testing & Benchmarks

#### Step 6.1: Automated Test Suite Execution
- Run `python3 -m unittest discover -s tests -p "test_*.py"` and ensure all tests pass cleanly.
- Author new unit tests for DAG planner, persistent task storage, and security sandbox.

#### Step 6.2: Real Application Benchmark
- Execute multi-step workflow across VS Code, Web Browser, and File System.
- Capture telemetry and record verification artifacts.

#### Step 6.3: Deliverables Assembly
- Compile `implementation_log.md`, `test_results.md`, `real_world_benchmark.md`, `rollback_guide.md`, and `final_acceptance_report.md`.
