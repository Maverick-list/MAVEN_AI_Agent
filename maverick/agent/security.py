"""Maverick DevOS - Agent Core Security, Provenance & Risk Classification Engine."""

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from maverick.core.security import ConfirmationRequiredError, SecurityError, redact_sensitive_text

logger = logging.getLogger("maverick.agent.security")


class RiskTier(str, Enum):
    """Formal 5-tier risk taxonomy for autonomous agent operations."""
    READ_ONLY = "read_only"          # Zero side effects: queries, inspections, observations
    REVERSIBLE = "reversible"        # Safe modifications: temp files, moving cursor, launching approved apps
    MODERATE_RISK = "moderate_risk"  # Workspace edits, non-critical settings
    HIGH_RISK = "high_risk"          # Overwriting files, sending communications, external network ops
    DESTRUCTIVE = "destructive"      # Deleting files, modifying permissions/auth, format, sudo/root ops


@dataclass
class ActionProvenance:
    """Audit provenance detailing the origin, intent, and parent context of an action."""
    action_id: str
    initiator: str  # 'user_voice', 'user_chat', 'autonomous_agent', 'scheduler'
    task_id: Optional[str] = None
    step_id: Optional[int] = None
    parent_agent: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ApprovalRecord:
    """Formal record of approval decision for an action."""
    action_id: str
    risk_tier: RiskTier
    status: str  # 'approved', 'rejected', 'auto_approved', 'emergency_blocked', 'awaiting_approval'
    approved_by: Optional[str] = None
    reason: Optional[str] = None
    decided_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["risk_tier"] = self.risk_tier.value
        return d


class RiskPolicy:
    """Security governance rules mapping actions and parameters to risk tiers."""

    # Explicit patterns requiring HIGH_RISK or DESTRUCTIVE classification
    DESTRUCTIVE_KEYWORDS: Set[str] = {
        "delete", "remove", "unlink", "rmdir", "drop", "truncate", "format",
        "purge", "mkfs", "fdisk", "parted", "wipe", "dd if=", "shutdown",
        "reboot", "init 0", "pkill", "kill -9", "killall",
    }

    HIGH_RISK_KEYWORDS: Set[str] = {
        "overwrite", "send_message", "publish", "post", "checkout", "purchase",
        "pay", "transfer", "upload", "write_file", "save_as", "chmod", "chown",
        "credential", "password", "token", "api_key", "git push", "push", "curl", "wget",
    }

    CRITICAL_SYSTEM_PATTERNS: List[re.Pattern] = [
        re.compile(r"\b(sudo|su|pkexec)\b", re.IGNORECASE),
        re.compile(r"\brm\s+-[rf]{1,2}\s+", re.IGNORECASE),
        re.compile(r"/etc/(passwd|shadow|sudoers)", re.IGNORECASE),
        re.compile(r"~/\.ssh/(id_|authorized_keys)", re.IGNORECASE),
    ]

    @classmethod
    def classify(
        cls,
        tool_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> RiskTier:
        """Classify an action into one of the 5 canonical RiskTiers."""
        params = parameters or {}
        tool_lower = (tool_name or "").lower()
        param_str = json.dumps(params).lower()

        # 1. Critical system commands & dangerous payloads
        for pat in cls.CRITICAL_SYSTEM_PATTERNS:
            if pat.search(tool_lower) or pat.search(param_str):
                return RiskTier.DESTRUCTIVE

        # 2. Destructive keyword matches
        if any(kw in tool_lower or kw in param_str for kw in cls.DESTRUCTIVE_KEYWORDS):
            return RiskTier.DESTRUCTIVE

        # 3. High risk keyword matches
        if any(kw in tool_lower or kw in param_str for kw in cls.HIGH_RISK_KEYWORDS):
            return RiskTier.HIGH_RISK

        # 4. Standard tool name conventions
        if any(k in tool_lower for k in ("list", "read", "check", "get", "status", "observe", "inspect", "search")):
            return RiskTier.READ_ONLY

        if any(k in tool_lower for k in ("move_cursor", "wait", "scroll", "hover", "create_dir")):
            return RiskTier.REVERSIBLE

        if any(k in tool_lower for k in ("click", "type", "shortcut", "launch", "open", "set_volume")):
            return RiskTier.MODERATE_RISK

        return RiskTier.MODERATE_RISK

    @classmethod
    def requires_approval(
        cls,
        tier: RiskTier,
        enforce_confirmation: bool = False,
    ) -> bool:
        """Determine whether human approval is strictly mandatory before execution."""
        if tier in (RiskTier.HIGH_RISK, RiskTier.DESTRUCTIVE):
            return True
        if tier == RiskTier.MODERATE_RISK and enforce_confirmation:
            return True
        return False


class AgentSecurityManager:
    """Centralized security manager maintaining audit provenance, approval records, and emergency stops."""

    def __init__(self, audit_path: Optional[str] = None):
        self.audit_path = audit_path or os.path.expanduser("~/.config/maverick/agent_audit.jsonl")
        self._lock = threading.Lock()
        self._emergency_stop_engaged: bool = False
        self._provenance_log: List[ActionProvenance] = []
        self._approvals: Dict[str, ApprovalRecord] = {}
        self._ensure_audit_storage()

    def _ensure_audit_storage(self) -> None:
        d = os.path.dirname(self.audit_path)
        if not os.path.exists(d):
            os.makedirs(d, mode=0o700, exist_ok=True)

    @property
    def is_emergency_stopped(self) -> bool:
        with self._lock:
            return self._emergency_stop_engaged

    def engage_emergency_stop(self) -> None:
        """Engage global lockdown: halt all executing and pending actions immediately."""
        with self._lock:
            self._emergency_stop_engaged = True
        logger.critical("EMERGENCY STOP ENGAGED: All agent execution locked down.")

    def release_emergency_stop(self) -> None:
        """Disengage global lockdown."""
        with self._lock:
            self._emergency_stop_engaged = False
        logger.info("Emergency Stop released.")

    def evaluate_action(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        provenance: Optional[ActionProvenance] = None,
        confirmed: bool = False,
        enforce_confirmation: bool = False,
    ) -> Tuple[bool, RiskTier, Optional[str]]:
        """
        Evaluate an action against security policies.
        Returns: (allowed_to_proceed, risk_tier, block_reason_or_none)
        """
        if self.is_emergency_stopped:
            return False, RiskTier.DESTRUCTIVE, "Execution blocked: Global Emergency Stop is currently engaged."

        tier = RiskPolicy.classify(action_name, parameters)

        # Check approval requirement
        needs_approval = RiskPolicy.requires_approval(tier, enforce_confirmation=enforce_confirmation)
        action_id = provenance.action_id if provenance else f"act_{int(time.time() * 1000)}"

        if needs_approval and not confirmed:
            app_rec = ApprovalRecord(
                action_id=action_id,
                risk_tier=tier,
                status="awaiting_approval",
                reason=f"Action '{action_name}' is classified as {tier.value.upper()} and requires user confirmation.",
            )
            with self._lock:
                self._approvals[action_id] = app_rec
            return False, tier, app_rec.reason

        app_rec = ApprovalRecord(
            action_id=action_id,
            risk_tier=tier,
            status="approved" if confirmed else "auto_approved",
            approved_by="user" if confirmed else "security_policy",
        )
        with self._lock:
            self._approvals[action_id] = app_rec
            if provenance:
                self._provenance_log.append(provenance)

        # Audit log to file
        self._record_audit_event(action_name, parameters, tier, app_rec.status, provenance)
        return True, tier, None

    def _record_audit_event(
        self,
        action_name: str,
        parameters: Optional[Dict[str, Any]],
        tier: RiskTier,
        status: str,
        provenance: Optional[ActionProvenance],
    ) -> None:
        try:
            entry = {
                "timestamp": time.time(),
                "action": action_name,
                "tier": tier.value,
                "status": status,
                "parameters": redact_sensitive_text(json.dumps(parameters or {})),
                "provenance": provenance.to_dict() if provenance else None,
            }
            with self._lock:
                with open(self.audit_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
                try:
                    os.chmod(self.audit_path, 0o600)
                except OSError:
                    pass
        except Exception as exc:
            logger.warning("Could not append audit record: %s", exc)

    def get_approval_record(self, action_id: str) -> Optional[ApprovalRecord]:
        with self._lock:
            return self._approvals.get(action_id)

    def record_decision(self, action_id: str, approved: bool, reason: Optional[str] = None) -> bool:
        with self._lock:
            if action_id in self._approvals:
                rec = self._approvals[action_id]
                rec.status = "approved" if approved else "rejected"
                rec.decided_at = time.time()
                rec.reason = reason
                return True
        return False
