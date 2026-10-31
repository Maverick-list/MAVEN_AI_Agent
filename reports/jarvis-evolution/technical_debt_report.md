# Maven JARVIS — Technical Debt & Anti-Pattern Audit
**Comprehensive Technical Debt & Structural Quality Analysis**
*Document Version: 1.0.0 | Date: October 31, 2026 | Environment: Ubuntu 26.04.1 LTS (Wayland)*

---

## 1. Executive Summary

An exhaustive codebase audit was conducted across 19,602 lines of Python, shell, and JavaScript source code within `Maverick-DevOS`. While the architecture successfully satisfies high-level functional requirements across voice, vision, computer use, and desktop containment, several architectural compromises, coupling anti-patterns, and brittle heuristics have accumulated across rapid iteration cycles.

Addressing these technical debt items is required to achieve the reliability, extensibility, and autonomy demanded by the **Ultimate AI Operating Assistant** target.

---

## 2. Detailed Technical Debt Inventory

### 2.1 Orchestration & Planning Anti-Patterns

#### TD-01: Brittle Regex and Keyword Intent Routing in TaskPlanner
- **Location:** [`maverick/intelligence/planner.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/intelligence/planner.py#L90-L270)
- **Problem:** `TaskPlanner.plan()` uses hardcoded substring checks (e.g. `if any(k in lower_goal for k in ("siapkan environment", "prepare dev")...)`) to synthesize multi-step plans.
- **Impact:** Any goal phrasing differing slightly from the hardcoded keywords falls back to a generic single-step `system_telemetry` diagnostic call. It lacks true dynamic DAG generation from generative reasoning.
- **Remediation:** Introduce an LLM-assisted DAG planner with structured JSON schema outputs, step validation, and dependency graph topological sorting.

#### TD-02: In-Memory Ephemeral Plan Storage
- **Location:** [`maverick/intelligence/planner.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/intelligence/planner.py#L72) (`self._active_plans: Dict[str, TaskPlan]`)
- **Problem:** Active plans, execution state, and approval gates reside solely in Python process memory.
- **Impact:** Restarting the dashboard server or gateway immediately drops ongoing plan state, preventing pause-and-resume workflows across sessions.
- **Remediation:** Back plan state with persistent SQLite WAL storage (`~/.maverick/tasks.db`) with atomic state transitions and serialization.

#### TD-03: Lack of Formal Parameter Schemas in Tool Registry
- **Location:** [`maverick/intelligence/tools.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/intelligence/tools.py#L40-L100)
- **Problem:** Tools declare arguments informally without standard JSON Schema, Pydantic, or TypeVar validation.
- **Impact:** Malformed arguments from the planner or LLM lead to runtime KeyError or TypeError exceptions instead of clear schema validation errors.
- **Remediation:** Define standard `ToolParameter` specifications with explicit types, defaults, constraints, and validation hooks.

---

### 2.2 Concurrency, Network & Server Architecture

#### TD-04: Monolithic ThreadingHTTPServer in Dashboard Server
- **Location:** [`maverick/dashboard/server.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/dashboard/server.py) (1,473 lines)
- **Problem:** The entire REST API, SSE event streams, static asset serving, and agent hooks are packed into a single 1,473-line file using standard library `ThreadingHTTPServer`.
- **Impact:** Heavy HTTP requests or slow AT-SPI tree inspections block server worker threads; lacks connection pooling, rate limiting, and modular routing.
- **Remediation:** Refactor `server.py` into modular route controllers (`routes/system.py`, `routes/vision.py`, `routes/tasks.py`) and adopt structured async handling or hardened WSGI/ASGI patterns while preserving zero-dependency local performance.

#### TD-05: Synchronous Subprocess Execution in Critical Request Loops
- **Location:** [`maverick/dashboard/server.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/dashboard/server.py#L450-L520), [`maverick/computer_use/screen.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/computer_use/screen.py)
- **Problem:** Calls to `subprocess.run(["grim", ...])`, `pgrep`, or `systemctl` run synchronously within HTTP request threads without asynchronous I/O dispatch.
- **Impact:** Spikes in desktop rendering or disk I/O cause intermittent latency spikes in HUD telemetry and API responses.
- **Remediation:** Offload blocking I/O calls to dedicated thread pools with bounded timeouts (e.g. `concurrent.futures.ThreadPoolExecutor(max_workers=4)`).

---

### 2.3 Computer Use & Accessibility Robustness

#### TD-06: Asynchronous AT-SPI Tree Hierarchy Desynchronization
- **Location:** [`maverick/computer_use/accessibility.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/computer_use/accessibility.py#L85-L160)
- **Problem:** Electron and Chromium-based applications (VS Code, Chrome) populate their accessibility tree lazily. AT-SPI queries immediately after window focus occasionally return empty node lists.
- **Impact:** Requires fallback to visual template matching or blind keystrokes when AT-SPI returns 0 nodes on freshly opened dialogs.
- **Remediation:** Implement an exponential backoff retry loop with caching and accessibility event listener hooks (`window:activate`, `object:state-changed`).

#### TD-07: Unchecked External Dependency Assumptions (e.g. LibreOffice)
- **Location:** Computer use benchmark scripts & tool dispatchers
- **Problem:** System assumes CLI binaries (`libreoffice`, `pdftotext`, `tesseract`) exist in `/usr/bin/` without graceful capability detection.
- **Impact:** Workflows attempting to automate office documents fail silently or raise binary missing exceptions.
- **Remediation:** Implement a dynamic capabilities registry (`SystemCapabilities.has_binary("libreoffice")`) with automatic fallback to pure-Python libraries (`python-docx`, `pypdf`, `reportlab`, `openpyxl`).

---

### 2.4 Code Duplication & Legacy Facades

#### TD-08: Redundant Tool Facades & Dual Registry Implementations
- **Location:** [`maverick/intelligence/tools.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/intelligence/tools.py) vs [`maverick/computer_use/registry.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/computer_use/registry.py)
- **Problem:** Tool definitions for computer control (`click_target`, `move_cursor`, `type_text`) are defined in both `intelligence/tools.py` and wrapped separately in `computer_use/registry.py`.
- **Impact:** Inconsistent risk tier tagging and duplicated validation logic.
- **Remediation:** Consolidate all tool definitions into a single source of truth in `maverick/intelligence/tools/` with modular category packages.

#### TD-09: Legacy Re-Export Stubs
- **Location:** [`maverick/vision/virtual_mouse.py`](file:///home/firza-ilmi/Maverick-DevOS/maverick/vision/virtual_mouse.py)
- **Problem:** 8-line facade file re-exporting `VirtualMouse` from `virtual_input.py`.
- **Impact:** Mild codebase clutter; acceptable for backward compatibility, but imports across codebase should standardize on `virtual_input.py`.

---

## 3. Severity & Refactoring Priority Matrix

| Item ID | Description | Severity | Impact Surface | Target Phase |
| :--- | :--- | :---: | :--- | :---: |
| **TD-01** | Brittle Regex Intent Routing in TaskPlanner | **HIGH** | Planner / Autonomous Agent | Phase C |
| **TD-02** | In-Memory Ephemeral Plan State | **HIGH** | Reliability / Workflow State | Phase C |
| **TD-03** | Lack of Formal Parameter Schemas | **MEDIUM** | Tool Execution / Safety | Phase D |
| **TD-04** | Monolithic ThreadingHTTPServer in server.py | **MEDIUM** | Dashboard / Control Center | Phase F |
| **TD-05** | Synchronous Subprocess Execution in Request Threads | **MEDIUM** | HUD Latency / Telemetry | Phase B |
| **TD-06** | Asynchronous AT-SPI Tree Desynchronization | **HIGH** | Computer Use Reliability | Phase B |
| **TD-07** | Missing External Dependency Verification | **MEDIUM** | Document Generation / Tools | Phase D |
| **TD-08** | Redundant Tool Definitions across Registries | **LOW** | Code Cleanliness / Maintainability | Phase D |

---

## 4. Remediation Strategy

To preserve stability and safeguard the active 7-Day Usage Trial:
1. All refactoring will occur in an **isolated development worktree** (`feature/jarvis-evolution`).
2. Core refactorings (TD-01, TD-02, TD-03) will feature strict backward compatibility wrappers to ensure zero disruption to existing CLI and dashboard callers.
3. Every refactored module must maintain 100% pass rate across the existing 295 regression tests.
