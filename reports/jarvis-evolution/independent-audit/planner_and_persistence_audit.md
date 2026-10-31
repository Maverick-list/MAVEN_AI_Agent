# Independent Engineering Audit: Autonomous Planner & Task Persistence

**System Under Audit:** MAVEN JARVIS Ultimate AI Operating Assistant Evolution  
**Target Repository:** `/home/firza-ilmi/Maverick-DevOS-evolution`  
**Target Files:**
- [`maverick/intelligence/planner.py`](file:///home/firza-ilmi/Maverick-DevOS-evolution/maverick/intelligence/planner.py)
- [`maverick/intelligence/task_store.py`](file:///home/firza-ilmi/Maverick-DevOS-evolution/maverick/intelligence/task_store.py)  
**Auditor:** Principal Software Architect, AI Systems Reliability Engineer  
**Date:** October 31, 2026  
**Status:** COMPLETE — AUDIT ONLY (NO CODE MODIFIED)

---

## 1. Executive Summary

This engineering audit independently scrutinized the architecture, state machine, DAG execution engine, persistence layer, and rollback mechanisms of the newly introduced task planning subsystem. 

### Key Audit Conclusions
1. **DAG Topological Execution Defect (CRITICAL):** While `validate_dag()` correctly detects cycles using Kahn's algorithm, `execute_plan()` iterates through `plan.steps` in a **single linear pass**. If steps in the plan are not pre-sorted in topological order, dependent steps appearing earlier in the list are silently skipped, left in `pending` status, and the plan is falsely reported as `completed`.
2. **Template-Driven Pseudo-Planner:** `TaskPlanner.plan()` does not perform dynamic LLM-driven DAG synthesis; it relies on hardcoded keyword string heuristics (`if any(k in lower_goal...)`). Unknown goals fall back to a single-step diagnostic call.
3. **Dead Enum States:** 3 of the 11 advertised `TaskStatus` states (`UNDERSTANDING`, `PLANNING`, `EXECUTING`) are dead code and never transitioned to at runtime.
4. **Single-Step Rollback & Approval Bypass:** `_execute_rollback()` only compensates the single failing step (not prior completed steps in a saga), and forcibly passes `confirmed=True`, bypassing security gates.
5. **Robust WAL Persistence:** `TaskStore` implements reliable SQLite WAL mode with atomic upserts (`ON CONFLICT(plan_id) DO UPDATE`), suitable for single-process concurrency. However, it lacks startup zombie reconciliation for interrupted plans.

---

## 2. DAG Integrity & Dependency Analysis

### Cycle Detection & Validation
In [`planner.py#L341-L365`](file:///home/firza-ilmi/Maverick-DevOS-evolution/maverick/intelligence/planner.py#L341-L365), `validate_dag()` implements Kahn’s algorithm:
- Computes in-degree for all steps.
- Validates that dependency IDs exist in the plan set (`step_ids`).
- Enqueues zero-in-degree vertices and traverses adjacency list.
- Verified: Correctly detects direct cycles ($A \to B \to A$) and transitive cycles ($A \to B \to C \to A$).
- **Defect:** Duplicate `step_id` entries are not explicitly caught during vertex registration (`step_ids = {s.step_id for s in steps}`); duplicate IDs cause `visited_count != len(steps)` and report a misleading "Cycle detected" error instead of "Duplicate step_id".

### Empirical Finding: Linear Pass Execution Failure
- **Location:** [`planner.py#L427-L436`](file:///home/firza-ilmi/Maverick-DevOS-evolution/maverick/intelligence/planner.py#L427-L436)
- **Code:**
  ```python
  for step in plan.steps:
      if step.status == "completed":
          continue
      deps_met = all(dep in completed_step_ids for dep in step.dependencies)
      if not deps_met:
          step.status = "pending"
          continue
      # executes step and completed_step_ids.add(step.step_id)
  ```
- **Empirical Test:**
  We constructed a valid, acyclic DAG where `Step 1` depends on `Step 2`, arranged as `[Step 1, Step 2]`.
  - Step 1: `deps_met` is `False` (Step 2 not yet executed). Step 1 remains `pending` and loop continues.
  - Step 2: `deps_met` is `True`. Step 2 executes and completes.
  - **Result:** Loop terminates. Step 1 was NEVER executed. Line 533 executes: `plan.status = TaskStatus.COMPLETED`.
  - **Verdict:** **CRITICAL LOGIC DEFECT**. The engine fails to run topologically dependent steps if list order does not match topological sort order.

---

## 3. Task Lifecycle & State Machine Audit

The system reports 11 states in `TaskStatus(Enum)`:

| # | State Name | Meaning | Entry Condition | Allowed Transitions | Terminal? | Real Runtime Use |
| :-: | :--- | :--- | :--- | :--- | :-: | :--- |
| 1 | `CREATED` | Plan initialized & saved | `plan()` completion | $\to$ `RUNNING`, `AWAITING_APPROVAL` | No | Active |
| 2 | `UNDERSTANDING` | Intent comprehension | None | None | No | **DEAD STATE** (Never entered) |
| 3 | `PLANNING` | DAG decomposition | None | None | No | **DEAD STATE** (Never entered) |
| 4 | `AWAITING_APPROVAL`| Gated on human input | `requires_approval=True` or tool confirmation | $\to$ `RUNNING`, `FAILED` | No | Active |
| 5 | `RUNNING` | Step loop executing | `execute_plan()` entry | $\to$ `AWAITING_APPROVAL`, `VERIFYING`, `RECOVERING`, `COMPLETED`, `FAILED` | No | Active |
| 6 | `EXECUTING` | Step active | None | None | No | **DEAD STATE** (Steps use `"running"`) |
| 7 | `VERIFYING` | Post-condition check | Step has `verification_criteria` | $\to$ `RECOVERING`, `RUNNING` | No | Active |
| 8 | `RECOVERING` | Rollback triggered | Verification or execution error | $\to$ `FAILED` | No | Active |
| 9 | `COMPLETED` | Execution completed | Linear step pass finished | None | **YES** | Active |
| 10| `FAILED` | Execution failed | Unrecoverable error or failed verification | None | **YES** | Active |
| 11| `PENDING` | Default uninitialized | `TaskPlan` dataclass default | $\to$ `CREATED` | No | Compatibility alias |

### Lifecycle Deficiencies
1. **Missing Plan Cancellation:** No state or transition exists for user cancellation (`CANCELLED` / `ABORTED`).
2. **Missing Retry Loop:** Steps cannot transition from `FAILED` back to `RUNNING` with an incremented attempt counter.
3. **No Timeout Governance:** Plans running long-running shell scripts or blocking tools have no global timeout governor.

---

## 4. SQLite Task Persistence Audit (`TaskStore`)

- **Storage Location:** `~/.maverick/tasks.db`
- **Schema:**
  ```sql
  CREATE TABLE IF NOT EXISTS orchestrated_plans (
      plan_id TEXT PRIMARY KEY,
      goal TEXT NOT NULL,
      status TEXT NOT NULL,
      created_at REAL NOT NULL,
      completed_at REAL,
      awaiting_step_id INTEGER,
      steps_count INTEGER DEFAULT 0,
      payload TEXT NOT NULL,
      updated_at REAL NOT NULL
  );
  ```
### Architecture Review
- **WAL Mode:** Verified. Connect hook executes `PRAGMA journal_mode = WAL; PRAGMA synchronous = NORMAL;`.
- **Atomic Upsert:** Uses `INSERT ... ON CONFLICT(plan_id) DO UPDATE SET ...`, preventing race conditions during plan state updates.
- **Connection Lifecycle:** Connections are cleanly opened and closed per method call via `@contextmanager _connection()`.
- **Schema Versioning:** Missing `PRAGMA user_version` and schema migration logic. Future column additions will require manual migration.
- **Zombie State on Crash:** If MAVEN is killed while executing a plan, `status` remains `'running'` in SQLite indefinitely. There is no startup sweep to transition orphaned `'running'` plans to `'failed'` or `'aborted'`.

---

## 5. Compensation & Rollback Evaluation

### Rollback Execution Logic
Located at [`planner.py#L400-L417`](file:///home/firza-ilmi/Maverick-DevOS-evolution/maverick/intelligence/planner.py#L400-L417):
```python
def _execute_rollback(self, step: TaskStep) -> bool:
    if not step.rollback_action:
        return False
    action = step.rollback_action
    tool = action.get("tool_name")
    params = action.get("parameters", {})
    if tool:
        try:
            self.tools.execute(tool, params, confirmed=True)
            return True
        except Exception as exc:
            return False
    return False
```

### Critical Security & Safety Assessment
1. **Approval Bypass (`confirmed=True`):**
   `self.tools.execute(tool, params, confirmed=True)` forcefully bypasses confirmation gates during rollback. If a rollback action is configured to delete files, kill processes, or terminate sessions, it runs without human review.
2. **Lack of Saga Compensation:**
   Rollback operates strictly on `step.rollback_action` of the single step that failed. If Step 1 created a project folder, Step 2 wrote files, and Step 3 failed: Steps 1 and 2 are never rolled back.
3. **Template Omission:**
   In all built-in templates in `plan()`, **none** of the generated steps specify `rollback_action` or `verification_criteria`. Rollback is currently only exercised in synthetic tests.

---

## 6. Audit Verdict

| Category | Rating | Notes |
| :--- | :---: | :--- |
| **DAG Dependency Validation** | **ACCEPTABLE** | Cycle detection is sound; missing dependencies caught. |
| **DAG Execution Engine** | **DEFECTIVE** | Linear loop fails out-of-order DAG execution. Must pre-sort topologically. |
| **Planning Intelligence** | **MINIMAL** | Hardcoded keyword heuristics, not an LLM dynamic planner. |
| **SQLite Persistence** | **SOUND** | Clean WAL-backed upsert design. |
| **Rollback Safety** | **MARGINAL** | Only compensates single step; bypasses confirmation gates. |

**Audit Recommendation:** Flag the linear execution loop as a **MUST-FIX** before relying on multi-step DAG workflows.
