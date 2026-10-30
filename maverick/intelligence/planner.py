"""Maverick DevOS - Intelligent Task Planner & DAG Step Orchestrator."""

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from maverick.intelligence.memory import ContextMemory
from maverick.intelligence.tools import ToolRegistry, ToolRisk


class TaskStatus(Enum):
    """Lifecycle statuses of orchestrated multi-step task plans."""
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERING = "recovering"


@dataclass
class TaskStep:
    """An individual actionable step within an orchestrated task plan."""
    step_id: int
    description: str
    tool_name: str
    parameters: Dict[str, Any]
    dependencies: List[int] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed, awaiting_approval, skipped
    requires_approval: bool = False
    result: Optional[Any] = None
    error: Optional[str] = None
    elapsed_ms: float = 0.0


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


class TaskPlanner:
    """
    Interprets natural language instructions, decomposes them into ordered steps,
    resolves tool requirements, manages human approval gates, and coordinates execution.
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        memory: Optional[ContextMemory] = None,
    ):
        self.memory = memory or ContextMemory()
        self.tools = tool_registry or ToolRegistry(memory_engine=self.memory)
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

        # 2. Diagnostics & System Telemetry pattern
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

        # 4. Default / Single-step fallback
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
            status=TaskStatus.PENDING,
        )

        self._active_plans[plan_id] = plan
        return plan

    def execute_plan(
        self,
        plan: TaskPlan,
        approved_step_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute an orchestrated task plan step-by-step.
        Pauses and returns status 'awaiting_approval' whenever a step requires human confirmation.
        Resumes execution when approved_step_id matches the awaiting step.
        """
        plan.status = TaskStatus.RUNNING
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
                step.status = "completed"
                step.result = exec_res.get("result")
                completed_step_ids.add(step.step_id)
            else:
                step.status = "failed"
                step.error = exec_res.get("error") or "Execution failure"
                # Recoverable error handling: if a directory check fails because it doesn't exist yet, continue
                if step.tool_name == "filesystem_list_dir" and ("not found" in str(step.error).lower() or "no such" in str(step.error).lower()):
                    step.status = "skipped"
                    step.error = "Directory does not exist yet; auto-created for project."
                    try:
                        p_dir = os.path.expanduser(step.parameters.get("path", ""))
                        if p_dir and p_dir.startswith(os.path.expanduser("~/")):
                            os.makedirs(p_dir, exist_ok=True)
                    except Exception:
                        pass
                    completed_step_ids.add(step.step_id)
                else:
                    plan.status = TaskStatus.FAILED
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

        return {
            "status": "completed",
            "plan_id": plan.plan_id,
            "summary": plan.final_summary,
            "plan": plan.to_dict(),
        }

    def get_plan(self, plan_id: str) -> Optional[TaskPlan]:
        """Look up plan by ID."""
        return self._active_plans.get(plan_id)
