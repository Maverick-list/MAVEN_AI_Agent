"""Maverick DevOS - Multi-Agent Registry & Dynamic Lifecycle Manager."""

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Type

from maverick.agent.specialized.base import SpecializedAgent
from maverick.agent.specialized.research_agent import ResearchAgent
from maverick.agent.specialized.coding_agent import CodingAgent
from maverick.agent.specialized.computer_use_agent import ComputerUseAgent
from maverick.agent.specialized.document_agent import DocumentAgent
from maverick.agent.specialized.monitoring_agent import SystemMonitoringAgent
from maverick.agent.specialized.planning_agent import PlanningAgent

logger = logging.getLogger("maverick.agent.specialized.registry")


class AgentRegistry:
    """
    Coordinates specialized autonomous agents with lazy on-demand initialization,
    bounded active agent limits, and automatic idle memory reclamation.
    """

    def __init__(
        self,
        max_active_agents: int = 4,
        memory: Optional[Any] = None,
        idle_timeout_sec: Optional[float] = None,
    ):
        self.max_active_agents = max_active_agents
        self.memory = memory
        self.idle_timeout_sec = idle_timeout_sec
        self._lock = threading.Lock()
        self._factories: Dict[str, Type[SpecializedAgent]] = {
            "research": ResearchAgent,
            "coding": CodingAgent,
            "computer_use": ComputerUseAgent,
            "document": DocumentAgent,
            "monitoring": SystemMonitoringAgent,
            "planning": PlanningAgent,
        }
        self._active_agents: Dict[str, SpecializedAgent] = {}

    def register_agent_class(self, agent_type: str, agent_cls: Type[SpecializedAgent]) -> None:
        """Register a new specialized agent class."""
        with self._lock:
            self._factories[agent_type.lower()] = agent_cls

    def get_agent(self, agent_type: str) -> Optional[SpecializedAgent]:
        """Retrieve or lazily instantiate a specialized agent with concurrency bounds."""
        key = str(agent_type).lower().replace("_agent", "")
        with self._lock:
            # 1. Prune expired idle agents first
            self._prune_expired_locked()

            if key in self._active_agents:
                agent = self._active_agents[key]
                agent.touch()
                return agent

            cls = self._factories.get(key)
            if not cls:
                logger.warning("No agent factory registered for agent type '%s'", agent_type)
                return None

            # 2. Check active limits: if full, evict the least recently used agent
            if len(self._active_agents) >= self.max_active_agents:
                lru_key = min(self._active_agents.keys(), key=lambda k: self._active_agents[k].last_active_ts)
                logger.info("Evicting LRU agent '%s' to respect max concurrency (%d)", lru_key, self.max_active_agents)
                evicted = self._active_agents.pop(lru_key)
                evicted.shutdown()

            # 3. Instantiate on-demand
            agent = cls()
            if self.idle_timeout_sec is not None:
                agent.idle_timeout_sec = self.idle_timeout_sec
            agent.initialize()
            self._active_agents[key] = agent
            return agent

    def list_available_agent_types(self) -> List[str]:
        with self._lock:
            return sorted(list(self._factories.keys()))

    def list_active_agents(self) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for k, a in self._active_agents.items():
                out.append({
                    "agent_type": k,
                    "name": a.name,
                    "is_initialized": a.is_initialized,
                    "last_active_ts": a.last_active_ts,
                    "idle_timeout_sec": a.idle_timeout_sec,
                })
            return out

    def prune_idle_agents(self) -> int:
        """Explicitly prune any agents that exceeded their idle timeout."""
        with self._lock:
            return self._prune_expired_locked()

    cleanup_idle_agents = prune_idle_agents

    def _prune_expired_locked(self) -> int:
        now = time.time()
        to_evict = [k for k, a in self._active_agents.items() if a.is_idle_expired(now)]
        for k in to_evict:
            logger.debug("Pruning idle agent '%s' to conserve memory.", k)
            agent = self._active_agents.pop(k)
            agent.shutdown()
        return len(to_evict)

    def shutdown_all(self) -> None:
        """Gracefully shutdown all active agents and release memory."""
        with self._lock:
            for k, a in list(self._active_agents.items()):
                try:
                    a.shutdown()
                except Exception as exc:
                    logger.warning("Error shutting down agent '%s': %s", k, exc)
            self._active_agents.clear()
