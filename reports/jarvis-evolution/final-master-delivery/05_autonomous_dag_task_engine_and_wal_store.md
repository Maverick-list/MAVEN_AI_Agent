# 05 — AUTONOMOUS DAG TASK ENGINE & WAL TASK STORE

## 1. Directed Acyclic Graph (DAG) Task Orchestrator

Complex instructions are decomposed by `AutonomousPlanner` into explicit dependency graphs rather than linear, unverified script executions.

```
       [ Instruction: "Research Linux eBPF and create a PDF summary" ]
                                     |
                                     v
                       +---------------------------+
                       | Step 1: Web Research      |
                       | Tool: web_research        |
                       | Post-condition: sources>0 |
                       +---------------------------+
                                     |
                                     v
                       +---------------------------+
                       | Step 2: AST / Synthesis   |
                       | Tool: document_generate   |
                       | Dep: [Step 1]             |
                       +---------------------------+
                                     |
                                     v
                       +---------------------------+
                       | Step 3: Write PDF File    |
                       | Gate: Requires Approval   |
                       | Post-cond: isfile(path)   |
                       +---------------------------+
```

### Core Execution Guarantees
1. **Topological Ordering:** Tasks with dependencies execute only after all prerequisite steps succeed.
2. **Honest Outcome Verification:** Every step executes a registered `post_condition`. If a step returns `status: success` but fails its post-condition (e.g. file is 0 bytes or not on disk), the step is marked `FAILED` with retry up to `max_retries=2`.
3. **Approval Gates:** High-risk actions (`ToolRisk.CONSEQUENTIAL` like file modification, system configuration, terminal commands) pause execution in `WAITING_APPROVAL`. In `fa2c38f`, approval execution was fixed so that `execute_plan(plan, approved_step_id=N)` safely bypasses the block for the approved step while keeping subsequent gates armed.

---

## 2. SQLite Write-Ahead Logging (WAL) Persistence

Plans, steps, execution logs, and output metadata are stored in `~/.local/share/maverick/tasks.db`:
- **Journal Mode:** `PRAGMA journal_mode=WAL;`
- **Synchronous:** `PRAGMA synchronous=NORMAL;`
- **Busy Timeout:** `PRAGMA busy_timeout=5000;`
- **Durability:** If Maven or the daemon restarts during an active plan, `TaskStore` recovers the uncompleted plan upon boot and resumes from the last completed checkpoint.
- Verified in `tests/test_dag_restart_recovery.py`: 100% plan integrity across simulated process termination.
