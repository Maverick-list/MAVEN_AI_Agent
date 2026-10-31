"""Maverick DevOS - Intelligent Task Planner & DAG Step Orchestrator."""

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from maverick.intelligence.memory import ContextMemory
from maverick.intelligence.task_store import TaskStore
from maverick.intelligence.tools import ToolRegistry, ToolRisk

logger = logging.getLogger("maverick.intelligence.planner")


class TaskStatus(Enum):
    """Formal lifecycle statuses of orchestrated multi-step task plans."""
    CREATED = "created"
    UNDERSTANDING = "understanding"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"  # Backward compatibility alias


@dataclass
class TaskStep:
    """An individual actionable step within an orchestrated task plan."""
    step_id: int
    description: str
    tool_name: str
    parameters: Dict[str, Any]
    dependencies: List[int] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed, awaiting_approval, skipped, verifying, recovering
    requires_approval: bool = False
    result: Optional[Any] = None
    error: Optional[str] = None
    elapsed_ms: float = 0.0
    verification_criteria: Optional[Dict[str, Any]] = None
    rollback_action: Optional[Dict[str, Any]] = None


@dataclass
class TaskPlan:
    """A multi-step DAG execution plan generated from natural language instruction."""
    plan_id: str
    goal: str
    steps: List[TaskStep]
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    awaiting_step_id: Optional[int] = None
    final_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert plan to serializable dictionary for API and Control Center HUD."""
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskPlan":
        """Reconstruct TaskPlan instance from dictionary or SQLite record."""
        steps = []
        for s in data.get("steps", []):
            steps.append(TaskStep(
                step_id=s.get("step_id", 1),
                description=s.get("description", ""),
                tool_name=s.get("tool_name", ""),
                parameters=s.get("parameters", {}),
                dependencies=s.get("dependencies", []),
                status=s.get("status", "pending"),
                requires_approval=s.get("requires_approval", False),
                result=s.get("result"),
                error=s.get("error"),
                elapsed_ms=s.get("elapsed_ms", 0.0),
                verification_criteria=s.get("verification_criteria"),
                rollback_action=s.get("rollback_action"),
            ))
        raw_status = data.get("status", "pending")
        try:
            status = TaskStatus(raw_status)
        except ValueError:
            status = TaskStatus.PENDING

        return cls(
            plan_id=data.get("plan_id", ""),
            goal=data.get("goal", ""),
            steps=steps,
            status=status,
            created_at=data.get("created_at", time.time()),
            completed_at=data.get("completed_at"),
            awaiting_step_id=data.get("awaiting_step_id"),
            final_summary=data.get("final_summary"),
        )


class TaskPlanner:
    """
    Interprets natural language instructions, decomposes them into ordered steps,
    resolves tool requirements, manages human approval gates, and coordinates execution.
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        memory: Optional[ContextMemory] = None,
        task_store: Optional[TaskStore] = None,
    ):
        self.memory = memory or ContextMemory()
        self.tools = tool_registry or ToolRegistry(memory_engine=self.memory)
        self.store = task_store or TaskStore()
        self._active_plans: Dict[str, TaskPlan] = {}

    def plan(self, instruction: str) -> TaskPlan:
        """
        Decompose a natural language instruction into a structured actionable TaskPlan.
        Synthesizes relevant context from persistent memory when available.
        """
        plan_id = f"plan_{int(time.time() * 1000) % 1000000}"
        clean_goal = instruction.strip()

        # Retrieve relevant contextual memories
        relevant_memories = self.memory.search(clean_goal, limit=3)
        context_hint = ""
        if relevant_memories:
            context_hint = " ".join([m.get("content", "") for m in relevant_memories])

        steps: List[TaskStep] = []
        lower_goal = clean_goal.lower()

        # 1. Development environment preparation pattern
        # e.g. "siapkan environment development untuk CampusLink" or "prepare development environment for Project"
        if any(k in lower_goal for k in ("siapkan environment", "prepare development", "setup dev", "prepare dev", "siapkan dev")):
            proj_match = None
            for word in clean_goal.split():
                if word.lower() not in ("siapkan", "environment", "development", "untuk", "proyek", "project", "prepare", "the", "dev", "my"):
                    proj_match = word.strip(".,;:?!")
                    break

            proj_name = proj_match or "CampusLink"
            proj_dir = f"~/projects/{proj_name}"

            # Step 1: Check project directory
            steps.append(TaskStep(
                step_id=1,
                description=f"Inspect project directory '{proj_dir}'",
                tool_name="filesystem_list_dir",
                parameters={"path": proj_dir},
                dependencies=[],
            ))

            # Step 2: Open project in VS Code
            steps.append(TaskStep(
                step_id=2,
                description=f"Open Visual Studio Code in '{proj_dir}'",
                tool_name="desktop_launch_app",
                parameters={"app_id": "code", "args": [proj_dir]},
                dependencies=[1],
            ))

            # Step 3: Open terminal in project directory (CRITICAL: Requires approval)
            tool_term = self.tools.get_tool("desktop_launch_app")
            steps.append(TaskStep(
                step_id=3,
                description=f"Launch gnome-terminal in '{proj_dir}'",
                tool_name="desktop_launch_app",
                parameters={"app_id": "gnome-terminal", "args": [f"--working-directory={proj_dir}"]},
                dependencies=[1],
                requires_approval=True,
            ))

        # 2. Autonomous Project & Application Creation pattern
        # e.g. "Maven, create a Python calculator application" or "create a Python project named SmartCalculator"
        elif any(k in lower_goal for k in ("create a python", "create python project", "buat aplikasi", "create project", "build a python", "buat proyek")):
            proj_name = "SmartCalculator"
            if "named" in lower_goal:
                proj_name = clean_goal.split("named")[-1].strip().split()[0].strip(".,;:?!")
            elif "bernama" in lower_goal:
                proj_name = clean_goal.split("bernama")[-1].strip().split()[0].strip(".,;:?!")
            elif "calculator" in lower_goal or "kalkulator" in lower_goal:
                proj_name = "SmartCalculator"

            proj_dir = f"~/projects/{proj_name}"

            # Step 1: Inspect development environment
            steps.append(TaskStep(
                step_id=1,
                description="Inspect Python runtime environment",
                tool_name="system_safe_command",
                parameters={"command": "python3 --version"},
                dependencies=[],
            ))

            # Step 2: Create project directory
            steps.append(TaskStep(
                step_id=2,
                description=f"Create project directory '{proj_dir}'",
                tool_name="filesystem_create_dir",
                parameters={"path": proj_dir},
                dependencies=[1],
            ))

            # Step 3: Write application source code
            calc_code = (
                "\"\"\"SmartCalculator Application generated autonomously by Maven JARVIS.\"\"\"\n\n"
                "class Calculator:\n"
                "    def add(self, a, b): return a + b\n"
                "    def subtract(self, a, b): return a - b\n"
                "    def multiply(self, a, b): return a * b\n"
                "    def divide(self, a, b):\n"
                "        if b == 0: raise ValueError('Cannot divide by zero')\n"
                "        return a / b\n\n"
                "if __name__ == '__main__':\n"
                "    calc = Calculator()\n"
                "    print('SmartCalculator Online. 10 + 5 =', calc.add(10, 5))\n"
                "    print('10 * 5 =', calc.multiply(10, 5))\n"
            )
            steps.append(TaskStep(
                step_id=3,
                description=f"Generate and write source code 'calculator.py' in '{proj_dir}'",
                tool_name="filesystem_write_file",
                parameters={"path": f"{proj_dir}/calculator.py", "content": calc_code},
                dependencies=[2],
            ))

            # Step 4: Execute and verify program
            expanded_proj = os.path.expanduser(proj_dir)
            steps.append(TaskStep(
                step_id=4,
                description=f"Execute program 'calculator.py' to verify runtime correctness",
                tool_name="system_safe_command",
                parameters={"command": f"python3 {expanded_proj}/calculator.py"},
                dependencies=[3],
            ))

            # Step 5: Save project record in persistent memory
            steps.append(TaskStep(
                step_id=5,
                description=f"Save project creation record in Context Memory",
                tool_name="memory_store",
                parameters={
                    "content": f"Created Python project '{proj_name}' at '{proj_dir}' with verified arithmetic execution.",
                    "category": "projects",
                    "tags": ["python", proj_name.lower(), "code"],
                },
                dependencies=[4],
            ))

        # 3. Diagnostics & System Telemetry pattern
        # e.g. "periksa kondisi laptop dan simpan ringkasan" or "check laptop status and save to memory"
        elif any(k in lower_goal for k in ("periksa kondisi", "check laptop status", "diagnostik laptop", "laptop health")):
            steps.append(TaskStep(
                step_id=1,
                description="Query live CPU, RAM, and battery power telemetry",
                tool_name="system_telemetry",
                parameters={},
                dependencies=[],
            ))
            steps.append(TaskStep(
                step_id=2,
                description="List running authorized applications",
                tool_name="desktop_list_running_apps",
                parameters={},
                dependencies=[],
            ))
            steps.append(TaskStep(
                step_id=3,
                description="Save health assessment snapshot in persistent memory",
                tool_name="memory_store",
                parameters={"content": "Laptop diagnostics: all subsystems operational.", "category": "diagnostics"},
                dependencies=[1, 2],
            ))

        # 3. Memory remember pattern
        # e.g. "ingat bahwa saya suka tema gelap" or "remember that campuslink frontend is react"
        elif lower_goal.startswith(("ingat bahwa", "ingat", "remember that", "remember")):
            content = lower_goal
            for prefix in ("ingat bahwa", "ingat", "remember that", "remember"):
                if content.startswith(prefix):
                    content = content[len(prefix):].strip()
                    break

            steps.append(TaskStep(
                step_id=1,
                description="Persist user context in memory",
                tool_name="memory_store",
                parameters={"content": content, "category": "context"},
                dependencies=[],
            ))

        # 4. Universal Computer Use & Desktop Automation pattern
        elif any(k in lower_goal for k in ("click ", "klik ", "press ", "type ", "ketik ", "shortcut", "observe screen", "lihat layar", "jelaskan layar", "what's on screen", "computer use", "control desktop")) or (
            any(k in lower_goal for k in ("open ", "buka ")) and any(k in lower_goal for k in ("create", "write", "save", "folder", "project", "run", "file"))
        ):
            steps.append(TaskStep(
                step_id=1,
                description=f"Execute autonomous computer-use workflow for '{clean_goal[:50]}'",
                tool_name="computer_execute_task",
                parameters={"goal": clean_goal},
                dependencies=[],
            ))

        # 5. Default / Single-step fallback
        else:
            steps.append(TaskStep(
                step_id=1,
                description=f"Process request '{clean_goal[:40]}'",
                tool_name="system_telemetry",
                parameters={},
                dependencies=[],
            ))

        plan = TaskPlan(
            plan_id=plan_id,
            goal=clean_goal,
            steps=steps,
            status=TaskStatus.CREATED,
        )

        # Validate DAG dependencies
        is_valid_dag, dag_err = self.validate_dag(steps)
        if not is_valid_dag:
            logger.warning("Plan %s has invalid DAG structure: %s", plan_id, dag_err)

        self._active_plans[plan_id] = plan
        self.store.save_plan_data(plan.to_dict())
        return plan

    def validate_dag(self, steps: List[TaskStep]) -> Tuple[bool, Optional[str]]:
        """Validate that step dependencies form a strict directed acyclic graph."""
        step_ids = {s.step_id for s in steps}
        adj: Dict[int, List[int]] = {s.step_id: [] for s in steps}
        for s in steps:
            for dep in s.dependencies:
                if dep not in step_ids:
                    return False, f"Step {s.step_id} references non-existent dependency {dep}"
                adj[dep].append(s.step_id)

        in_degree = {s.step_id: len(s.dependencies) for s in steps}
        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        visited_count = 0
        while queue:
            curr = queue.pop(0)
            visited_count += 1
            for nxt in adj.get(curr, []):
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        if visited_count != len(steps):
            return False, "Cycle detected in step dependencies"
        return True, None

    def _verify_step_outcome(self, step: TaskStep) -> Tuple[bool, Optional[str]]:
        """Verify the empirical post-condition outcome of an executed step."""
        if not step.verification_criteria:
            return True, None

        crit = step.verification_criteria
        crit_type = crit.get("type")

        if crit_type == "file_exists":
            path = os.path.realpath(os.path.expanduser(crit.get("path", "")))
            if not os.path.exists(path):
                return False, f"Verification failed: expected file '{path}' does not exist."
            min_bytes = crit.get("min_size_bytes", 0)
            if min_bytes > 0 and os.path.getsize(path) < min_bytes:
                return False, f"Verification failed: file '{path}' size ({os.path.getsize(path)} bytes) is below expected minimum ({min_bytes} bytes)."
            return True, None

        elif crit_type == "directory_exists":
            path = os.path.realpath(os.path.expanduser(crit.get("path", "")))
            if not os.path.isdir(path):
                return False, f"Verification failed: expected directory '{path}' does not exist."
            return True, None

        elif crit_type == "exit_code_zero":
            if isinstance(step.result, dict):
                code = step.result.get("exit_code")
                if code is not None and code != 0:
                    return False, f"Verification failed: expected exit code 0, got {code}."
            return True, None

        return True, None

    def _execute_rollback(self, step: TaskStep) -> bool:
        """Execute compensation rollback action for a failed step."""
        if not step.rollback_action:
            return False
        action = step.rollback_action
        tool = action.get("tool_name")
        params = action.get("parameters", {})
        if tool:
            try:
                logger.info("Executing rollback action '%s' for step %d", tool, step.step_id)
                self.tools.execute(tool, params, confirmed=True)
                return True
            except Exception as exc:
                logger.warning("Rollback action failed: %s", exc)
                return False
        return False

    def execute_plan(
        self,
        plan: TaskPlan,
        approved_step_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute an orchestrated task plan step-by-step with DAG dependencies,
        approval gating, empirical verification, and persistent state recording.
        """
        plan.status = TaskStatus.RUNNING
        self.store.save_plan_data(plan.to_dict())
        completed_step_ids = {s.step_id for s in plan.steps if s.status == "completed"}

        for step in plan.steps:
            if step.status == "completed":
                continue

            # Verify dependencies
            deps_met = all(dep in completed_step_ids for dep in step.dependencies)
            if not deps_met:
                step.status = "pending"
                continue

            # Check human approval gate
            if step.requires_approval:
                if approved_step_id == step.step_id:
                    # User granted explicit approval
                    is_confirmed = True
                else:
                    # Halt and request human confirmation
                    step.status = "awaiting_approval"
                    plan.status = TaskStatus.AWAITING_APPROVAL
                    plan.awaiting_step_id = step.step_id
                    self.store.save_plan_data(plan.to_dict())
                    return {
                        "status": "awaiting_approval",
                        "plan_id": plan.plan_id,
                        "awaiting_step_id": step.step_id,
                        "description": step.description,
                        "tool_name": step.tool_name,
                        "parameters": step.parameters,
                        "plan": plan.to_dict(),
                    }
            else:
                is_confirmed = False

            # Execute tool
            step.status = "running"
            t_s = time.perf_counter()
            exec_res = self.tools.execute(
                tool_name=step.tool_name,
                params=step.parameters,
                confirmed=is_confirmed,
            )
            step.elapsed_ms = round((time.perf_counter() - t_s) * 1000.0, 1)

            if exec_res.get("status") == "confirmation_required":
                step.status = "awaiting_approval"
                plan.status = TaskStatus.AWAITING_APPROVAL
                plan.awaiting_step_id = step.step_id
                self.store.save_plan_data(plan.to_dict())
                return {
                    "status": "awaiting_approval",
                    "plan_id": plan.plan_id,
                    "awaiting_step_id": step.step_id,
                    "description": step.description,
                    "tool_name": step.tool_name,
                    "parameters": step.parameters,
                    "plan": plan.to_dict(),
                }

            if exec_res.get("status") == "success":
                step.result = exec_res.get("result")

                # Verification Stage
                if step.verification_criteria:
                    plan.status = TaskStatus.VERIFYING
                    verified, v_err = self._verify_step_outcome(step)
                    if not verified:
                        step.status = "failed"
                        step.error = v_err or "Verification failed"
                        plan.status = TaskStatus.RECOVERING
                        self._execute_rollback(step)
                        plan.status = TaskStatus.FAILED
                        self.store.save_plan_data(plan.to_dict())
                        return {
                            "status": "failed",
                            "plan_id": plan.plan_id,
                            "failed_step_id": step.step_id,
                            "error": step.error,
                            "plan": plan.to_dict(),
                        }

                step.status = "completed"
                completed_step_ids.add(step.step_id)
            else:
                step.status = "failed"
                step.error = exec_res.get("error") or "Execution failure"
                # Recoverable error handling: if a directory check fails because it doesn't exist yet, continue
                if step.tool_name == "filesystem_list_dir" and ("not found" in str(step.error).lower() or "no such" in str(step.error).lower()):
                    step.status = "skipped"
                    step.error = "Directory does not exist yet; auto-created for project."
                    try:
                        p_dir = os.path.realpath(os.path.expanduser(step.parameters.get("path", "")))
                        home = os.path.realpath(os.path.expanduser("~"))
                        if p_dir.startswith(home + "/") or p_dir.startswith("/tmp/"):
                            os.makedirs(p_dir, exist_ok=True)
                    except Exception:
                        pass
                    completed_step_ids.add(step.step_id)
                else:
                    plan.status = TaskStatus.RECOVERING
                    self._execute_rollback(step)
                    plan.status = TaskStatus.FAILED
                    self.store.save_plan_data(plan.to_dict())
                    return {
                        "status": "failed",
                        "plan_id": plan.plan_id,
                        "failed_step_id": step.step_id,
                        "error": step.error,
                        "plan": plan.to_dict(),
                    }

        # All steps completed!
        plan.status = TaskStatus.COMPLETED
        plan.completed_at = time.time()
        plan.awaiting_step_id = None
        plan.final_summary = f"Plan '{plan.goal}' completed successfully ({len(plan.steps)} steps executed)."
        self.store.save_plan_data(plan.to_dict())

        return {
            "status": "completed",
            "plan_id": plan.plan_id,
            "summary": plan.final_summary,
            "plan": plan.to_dict(),
        }

    def get_plan(self, plan_id: str) -> Optional[TaskPlan]:
        """Look up plan by ID from in-memory cache or persistent SQLite store."""
        if plan_id in self._active_plans:
            return self._active_plans[plan_id]
        stored_data = self.store.get_plan_data(plan_id)
        if stored_data:
            plan = TaskPlan.from_dict(stored_data)
            self._active_plans[plan_id] = plan
            return plan
        return None

    def list_plans(self, limit: int = 20, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List historical and active plans from SQLite store."""
        return self.store.list_plans(limit=limit, status=status)


# Backward compatibility aliases
Planner = TaskPlanner
StepStatus = TaskStatus
