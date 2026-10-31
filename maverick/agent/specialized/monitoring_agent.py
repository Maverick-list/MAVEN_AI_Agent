"""Maverick DevOS - Specialized System Monitoring & Telemetry Agent."""

import logging
from typing import Any, Dict, Optional, Tuple

from maverick.agent.specialized.base import SpecializedAgent

logger = logging.getLogger("maverick.agent.specialized.monitoring")


class SystemMonitoringAgent(SpecializedAgent):
    """Specialized agent monitoring system hardware, operating modes, memory bounds, and safety."""

    def __init__(self):
        super().__init__(
            name="monitoring_agent",
            agent_type="monitoring",
            description="Collects system telemetry, audits memory bounds, manages operating modes, and enforces safety bounds.",
            idle_timeout_sec=120.0,
        )

    def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.initialize()
        self.touch()

        from maverick.system.monitor import get_system_summary
        from maverick.system.memory_manager import memory_manager

        if tool_name in ("system_telemetry", "get_system_summary"):
            return {"status": "success", "summary": get_system_summary()}

        if tool_name in ("set_mode", "set_operating_mode"):
            mode = str(parameters.get("mode", "normal")).lower()
            for m in memory_manager.current_mode.__class__:
                if m.value == mode:
                    res = memory_manager.set_mode(m)
                    return {"status": "success", "result": res}
            return {"status": "error", "message": f"Unknown mode: '{mode}'"}

        if tool_name == "emergency_stop_all":
            memory_manager.enforce_memory_bounds(force=True)
            return {"status": "success", "action": "emergency_stop_executed"}

        return {"status": "error", "message": f"Unsupported tool '{tool_name}' for SystemMonitoringAgent."}

    def verify(
        self,
        tool_name: str,
        result: Any,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        if not isinstance(result, dict) or result.get("status") != "success":
            return False, "System monitoring execution returned error status."
        return True, None


# Convenience alias
MonitoringAgent = SystemMonitoringAgent

