"""Maverick DevOS - Computer Use Security & Approval Governance Layer.

Enforces three-tier security policy on all computer-use operations:
- NORMAL: Observation, window navigation, reversible clicks, text typing.
- SENSITIVE: Modifying files, overwriting code, uploading, sending messages (Requires confirmation).
- CRITICAL: sudo execution, disk commands, credential alteration, security policy changes (Strictly gated).

Maintains an immutable audit log of automated interactions and provides
emergency stop interception.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import logging
import os
import time
from typing import Any, Dict, List, Optional

from maverick.core.security import verify_confirmation, ConfirmationRequiredError, SecurityError
from maverick.intelligence.tools import ToolRisk

logger = logging.getLogger("maverick.computer_use.security")


class ActionTier(Enum):
    """Classification of action risk level."""
    NORMAL = "normal"          # Reversible, safe UI interaction
    SENSITIVE = "sensitive"    # File write/delete, preferences, form submission
    CRITICAL = "critical"      # sudo, rm -rf, partition, security change


@dataclass
class AuditRecord:
    """Immutable audit trail log for every computer use action."""
    action_id: str
    tier: ActionTier
    action_name: str
    target_app: str
    parameters: Dict[str, Any]
    confirmed: bool
    status: str  # approved, rejected, blocked, completed, failed
    timestamp: float = field(default_factory=time.time)
    message: Optional[str] = None


class ComputerUseSecurity:
    """Security enforcement gateway for computer use automation."""

    SENSITIVE_KEYWORDS = {
        "delete", "remove", "overwrite", "upload", "send", "drop",
        "format", "terminate", "kill", "purge", "discard",
    }

    CRITICAL_PATTERNS = {
        "sudo", "dd ", "mkfs", "fdisk", "parted", "chmod -r 777",
        "rm -rf /", "passwd", "shadow", "authorized_keys",
    }

    def __init__(self, log_path: Optional[str] = None):
        self._audit_log: List[AuditRecord] = []
        self._log_path = log_path
        self._emergency_stopped = False

    @property
    def is_emergency_stopped(self) -> bool:
        """Check if security has tripped emergency stop."""
        return self._emergency_stopped

    def trigger_emergency_stop(self) -> None:
        """Lock down execution immediately."""
        self._emergency_stopped = True
        logger.warning("ComputerUseSecurity: EMERGENCY STOP LOCKDOWN ACTIVATED.")

    def reset_emergency_stop(self) -> None:
        """Reset emergency stop lockdown."""
        self._emergency_stopped = False

    def classify_action(self, action_name: str, target_app: str = "", params: Optional[Dict[str, Any]] = None) -> ActionTier:
        """Determine risk tier for a proposed action."""
        params = params or {}
        text_rep = f"{action_name} {target_app} {json_str(params)}".lower()

        # 1. Critical Check
        for pat in self.CRITICAL_PATTERNS:
            if pat in text_rep:
                return ActionTier.CRITICAL

        # 2. Sensitive Check
        for kw in self.SENSITIVE_KEYWORDS:
            if kw in text_rep:
                return ActionTier.SENSITIVE

        # File write or destructive parameter checks
        if action_name in ("filesystem_write_file", "file_delete", "file_overwrite"):
            return ActionTier.SENSITIVE

        return ActionTier.NORMAL

    def authorize_action(
        self,
        action_name: str,
        target_app: str = "",
        params: Optional[Dict[str, Any]] = None,
        confirmed: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluate proposed action against security policy.
        Returns:
          { "allowed": True/False, "tier": ActionTier, "needs_confirmation": True/False, "reason": str }
        """
        if self._emergency_stopped:
            self._log_action(action_name, target_app, params or {}, confirmed, "blocked", ActionTier.CRITICAL, "Emergency stop active.")
            return {
                "allowed": False,
                "tier": ActionTier.CRITICAL.value,
                "needs_confirmation": False,
                "error": "Execution blocked: Emergency Stop is currently engaged.",
            }

        tier = self.classify_action(action_name, target_app, params)

        if tier == ActionTier.CRITICAL:
            if not confirmed:
                self._log_action(action_name, target_app, params or {}, False, "blocked", tier, "Critical action requires explicit user confirmation.")
                return {
                    "allowed": False,
                    "tier": tier.value,
                    "needs_confirmation": True,
                    "error": f"CRITICAL OPERATION: Action on '{action_name}' requires explicit user confirmation.",
                }

        if tier == ActionTier.SENSITIVE:
            if not confirmed:
                self._log_action(action_name, target_app, params or {}, False, "blocked", tier, "Sensitive action awaiting confirmation.")
                return {
                    "allowed": False,
                    "tier": tier.value,
                    "needs_confirmation": True,
                    "error": f"SENSITIVE ACTION: '{action_name}' modifies user data and requires approval.",
                }

        self._log_action(action_name, target_app, params or {}, confirmed, "approved", tier, "Authorized by security policy.")
        return {
            "allowed": True,
            "tier": tier.value,
            "needs_confirmation": False,
            "reason": "Authorized",
        }

    def _log_action(
        self,
        action_name: str,
        target_app: str,
        params: Dict[str, Any],
        confirmed: bool,
        status: str,
        tier: ActionTier,
        message: Optional[str] = None,
    ) -> None:
        """Append to immutable memory audit log."""
        action_id = f"act_{int(time.time() * 1000) % 1000000}"
        rec = AuditRecord(
            action_id=action_id,
            tier=tier,
            action_name=action_name,
            target_app=target_app,
            parameters=params,
            confirmed=confirmed,
            status=status,
            message=message,
        )
        self._audit_log.append(rec)
        if len(self._audit_log) > 200:
            self._audit_log.pop(0)

    def get_audit_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve recent audit logs for Control Center inspection."""
        recent = self._audit_log[-limit:]
        out = []
        for r in recent:
            d = asdict(r)
            d["tier"] = r.tier.value
            out.append(d)
        return out


def json_str(obj: Any) -> str:
    """Safe compact string conversion."""
    try:
        import json
        return json.dumps(obj)
    except Exception:
        return str(obj)
