"""Maverick DevOS - Specialized Planning & Workflow Decomposition Agent."""

import logging
from typing import Any, Dict, Optional, Tuple

from maverick.agent.specialized.base import SpecializedAgent

logger = logging.getLogger("maverick.agent.specialized.planning")


class PlanningAgent(SpecializedAgent):
    """Specialized agent decomposing complex user instructions into validated DAG task plans."""

    def __init__(self, planner_instance=None):
        super().__init__(
            name="planning_agent",
            agent_type="planning",
            description="Decomposes high-level instructions into multi-step DAG execution plans with dependency management.",
            idle_timeout_sec=120.0,
        )
        self._planner = planner_instance

    def initialize(self) -> None:
        if not self._is_initialized or self._planner is None:
            from maverick.intelligence.planner import TaskPlanner
            self._planner = self._planner or TaskPlanner()
            super().initialize()

    def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.initialize()
        self.touch()

        if tool_name in ("plan", "create_plan"):
            instruction = str(parameters.get("instruction") or parameters.get("goal", "")).strip()
            plan = self._planner.plan(instruction)
            return {"status": "success", "plan": plan.to_dict()}

        if tool_name in ("execute_plan", "run_plan"):
            plan_data = parameters.get("plan")
            approved_step = parameters.get("approved_step_id")
            from maverick.intelligence.planner import TaskPlan
            plan_obj = TaskPlan.from_dict(plan_data) if isinstance(plan_data, dict) else plan_data
            exec_res = self._planner.execute_plan(plan_obj, approved_step_id=approved_step)
            return {"status": "success", "execution": exec_res, "plan": plan_obj.to_dict()}

        return {"status": "error", "message": f"Unsupported tool '{tool_name}' for PlanningAgent."}

    def verify(
        self,
        tool_name: str,
        result: Any,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        if not isinstance(result, dict) or result.get("status") != "success":
            return False, "Planning execution produced invalid status."
        return True, None
