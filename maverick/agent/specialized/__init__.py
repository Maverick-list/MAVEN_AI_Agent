"""Maverick DevOS - Specialized Multi-Agent Package."""

from maverick.agent.specialized.base import SpecializedAgent
from maverick.agent.specialized.research_agent import ResearchAgent
from maverick.agent.specialized.coding_agent import CodingAgent
from maverick.agent.specialized.computer_use_agent import ComputerUseAgent
from maverick.agent.specialized.document_agent import DocumentAgent
from maverick.agent.specialized.monitoring_agent import SystemMonitoringAgent, MonitoringAgent
from maverick.agent.specialized.planning_agent import PlanningAgent
from maverick.agent.specialized.registry import AgentRegistry

__all__ = [
    "SpecializedAgent",
    "ResearchAgent",
    "CodingAgent",
    "ComputerUseAgent",
    "DocumentAgent",
    "SystemMonitoringAgent",
    "PlanningAgent",
    "AgentRegistry",
]
