"""Maverick DevOS - Specialized Research & Web Intelligence Agent."""

import logging
from typing import Any, Dict, Optional, Tuple

from maverick.agent.specialized.base import SpecializedAgent

logger = logging.getLogger("maverick.agent.specialized.research")


class ResearchAgent(SpecializedAgent):
    """Specialized agent coordinating web research, information retrieval, and synthesis."""

    def __init__(self):
        super().__init__(
            name="research_agent",
            agent_type="research",
            description="Performs structured web inquiries, information synthesis, and verifiable citations.",
            idle_timeout_sec=90.0,
        )
        self._assistant = None

    def initialize(self) -> None:
        if not self._is_initialized:
            from maverick.intelligence.toolkit.research import ResearchAssistant
            self._assistant = ResearchAssistant()
            super().initialize()

    def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.initialize()
        self.touch()

        if tool_name in ("web_research_synthesize", "research"):
            topic = str(parameters.get("topic") or parameters.get("query", "")).strip()
            if not topic:
                return {"status": "error", "message": "Research topic cannot be empty."}
            max_sources = int(parameters.get("max_sources", 3))
            report = self._assistant.research(topic=topic, max_sources=max_sources)
            return {
                "status": "success",
                "report": report.to_dict(),
                "summary": report.executive_summary,
                "sources_count": len(report.sources),
            }

        return {"status": "error", "message": f"Unsupported tool '{tool_name}' for ResearchAgent."}

    def verify(
        self,
        tool_name: str,
        result: Any,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        if not isinstance(result, dict) or result.get("status") != "success":
            return False, "Research execution returned an error or invalid structure."
        rep = result.get("report")
        if not rep or not rep.get("topic"):
            return False, "Research outcome verification failed: missing executive report."
        return True, None

    def shutdown(self) -> None:
        self._assistant = None
        super().shutdown()
