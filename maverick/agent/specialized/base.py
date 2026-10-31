"""Maverick DevOS - Specialized Agent Abstract Base Class."""

from abc import ABC, abstractmethod
import logging
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("maverick.agent.specialized.base")


class SpecializedAgent(ABC):
    """
    Abstract base for bounded, on-demand specialized domain agents.
    Enforces lifecycle management, post-action verification, rollback support,
    and automatic idle cleanup to preserve system RAM.
    """

    def __init__(
        self,
        name: str,
        agent_type: str,
        description: str,
        idle_timeout_sec: float = 60.0,
    ):
        self.name = name
        self.agent_type = agent_type
        self.description = description
        self.idle_timeout_sec = idle_timeout_sec
        self.last_active_ts: float = time.time()
        self._is_initialized: bool = False

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    def touch(self) -> None:
        """Update last active timestamp to delay idle eviction."""
        self.last_active_ts = time.time()

    def is_idle_expired(self, now: Optional[float] = None) -> bool:
        """Check if agent has exceeded its idle inactivity timeout."""
        current = now or time.time()
        return self._is_initialized and (current - self.last_active_ts) > self.idle_timeout_sec

    def initialize(self) -> None:
        """Perform on-demand initialization. Subclasses should override and call super()."""
        self._is_initialized = True
        self.touch()
        logger.debug("Initialized specialized agent '%s' (%s)", self.name, self.agent_type)

    @abstractmethod
    def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a domain tool and return structured execution result."""
        pass

    def verify(
        self,
        tool_name: str,
        result: Any,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Perform empirical verification of action outcome.
        Returns: (success_bool, failure_reason_if_any).
        """
        return True, None

    def rollback(self, step_data: Dict[str, Any]) -> bool:
        """Perform compensating rollback action if possible. Default no-op returns False."""
        return False

    def shutdown(self) -> None:
        """Release domain models, sockets, or cache to reclaim memory."""
        self._is_initialized = False
        logger.debug("Shutdown specialized agent '%s' (%s)", self.name, self.agent_type)
