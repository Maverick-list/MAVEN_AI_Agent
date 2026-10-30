"""Maverick DevOS - Privacy-Preserving Activity Logger."""

import json
import os
import re
import time
from typing import Any, Dict, List, Optional
from maverick.browser.page import redact_sensitive_text

DEFAULT_ACTIVITY_LOG_FILE = os.path.expanduser("~/.local/share/maverick/activity.jsonl")
DEFAULT_MAX_RECORDS = 1000

# Sensitive keys that must never have their raw values logged
SENSITIVE_KEY_PATTERNS = re.compile(
    r"(password|token|secret|key|cookie|auth|credential|session|pin|card)",
    re.IGNORECASE
)


def sanitize_log_dict(data: Any) -> Any:
    """Recursively scrub secrets, passwords, and tokens from logging payloads."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if SENSITIVE_KEY_PATTERNS.search(str(k)):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_log_dict(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_log_dict(item) for item in data]
    elif isinstance(data, str):
        return redact_sensitive_text(data)
    return data


class ActivityLogger:
    """Auditable, privacy-respecting activity logger for Maven actions."""

    def __init__(self, log_path: Optional[str] = None, max_records: int = DEFAULT_MAX_RECORDS):
        self.log_path = log_path or DEFAULT_ACTIVITY_LOG_FILE
        self.max_records = max_records

    def log_action(
        self,
        action_type: str,
        target: str = "",
        status: str = "success",
        confirmed: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Record an auditable action entry into local JSONL log.
        Automatically scrubs any secret or credential fields.
        """
        sanitized_details = sanitize_log_dict(details or {})
        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action_type": str(action_type).strip(),
            "target": redact_sensitive_text(str(target)),
            "status": str(status).strip(),
            "confirmed": bool(confirmed),
            "details": sanitized_details,
        }

        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            self._enforce_retention()
        except Exception:
            pass

        return record

    def _enforce_retention(self) -> None:
        """Enforce retention policy to prevent unbounded disk growth."""
        if not os.path.isfile(self.log_path):
            return

        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if len(lines) > self.max_records:
                # Keep only the newest max_records
                trimmed = lines[-self.max_records:]
                with open(self.log_path, "w", encoding="utf-8") as f:
                    f.writelines(trimmed)
        except Exception:
            pass

    def get_recent_activity(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent actions in reverse chronological order (newest first)."""
        if not os.path.isfile(self.log_path):
            return []

        records: List[Dict[str, Any]] = []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in reversed(lines):
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                        if len(records) >= limit:
                            break
                    except Exception:
                        continue
        except Exception:
            pass

        return records

    def clear(self) -> Dict[str, Any]:
        """Clear Maven's own activity log file."""
        if os.path.isfile(self.log_path):
            try:
                os.remove(self.log_path)
                return {
                    "status": "success",
                    "action": "clear_activity",
                    "message": f"Cleared activity log at '{self.log_path}'.",
                }
            except Exception as exc:
                return {
                    "status": "error",
                    "action": "clear_activity",
                    "message": f"Failed to clear activity log: {str(exc)}",
                }

        return {
            "status": "success",
            "action": "clear_activity",
            "message": "Activity log was already empty.",
        }
