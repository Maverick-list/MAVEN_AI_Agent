"""Maverick DevOS - Specialized Computer Use & UI Automation Agent."""

import logging
from typing import Any, Dict, Optional, Tuple

from maverick.agent.specialized.base import SpecializedAgent

logger = logging.getLogger("maverick.agent.specialized.computer_use")


class ComputerUseAgent(SpecializedAgent):
    """Specialized agent operating desktop applications using AT-SPI2 accessibility and observe-plan-act-verify."""

    def __init__(self, cu_agent_instance=None):
        super().__init__(
            name="computer_use_agent",
            agent_type="computer_use",
            description="Inspects active desktop windows, locates UI elements via AT-SPI2, and executes verified UI interactions.",
            idle_timeout_sec=120.0,
        )
        self._cu_agent = cu_agent_instance

    def initialize(self) -> None:
        if not self._is_initialized or self._cu_agent is None:
            from maverick.computer_use.agent import AutonomousComputerUseAgent
            self._cu_agent = self._cu_agent or AutonomousComputerUseAgent()
            super().initialize()

    def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.initialize()
        self.touch()

        if tool_name in ("computer_use_execute", "execute_goal"):
            goal = str(parameters.get("goal") or parameters.get("instruction", "")).strip()
            confirmed = bool(parameters.get("confirmed", False))
            return self._cu_agent.execute_goal(goal, confirmed=confirmed)

        if tool_name in ("observe", "desktop_observe"):
            obs = self._cu_agent.observer.observe()
            return {"status": "success", "observation": obs.to_dict()}

        if tool_name == "desktop_launch_app":
            from maverick.desktop.launcher import launch_app
            app_id = str(parameters.get("app_id", "")).strip()
            args = parameters.get("args")
            confirmed = bool(parameters.get("confirmed", False))
            return launch_app(app_id=app_id, args=args, confirmed=confirmed)

        return {"status": "error", "message": f"Unsupported tool '{tool_name}' for ComputerUseAgent."}

    def verify(
        self,
        tool_name: str,
        result: Any,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        if not isinstance(result, dict):
            return False, "Computer-use execution produced non-dictionary result."

        status = result.get("status")
        if status not in ("success", "completed", "running"):
            err = result.get("message") or result.get("error") or "Unknown error"
            return False, f"Computer use action failed: {err}"

        # Re-observe desktop to confirm UI state changed appropriately
        if self._cu_agent:
            obs = self._cu_agent.observer.observe()
            if not obs.screen_resolution or obs.screen_resolution[0] <= 0:
                return False, "Display server connection dropped during UI action."

        return True, None

    def shutdown(self) -> None:
        if self._cu_agent and hasattr(self._cu_agent, "pause"):
            try:
                self._cu_agent.pause()
            except Exception:
                pass
        self._cu_agent = None
        super().shutdown()
