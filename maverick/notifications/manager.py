"""Maverick DevOS - Desktop Notification Manager."""

import json
import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Set
from maverick.notifications.filter import (
    sanitize_notification_text,
    SUPPORTED_CATEGORIES,
    DEFAULT_ENABLED_CATEGORIES,
)

DEFAULT_NOTIFICATION_STORE = os.path.expanduser("~/.local/share/maverick/session_notifications.json")


class NotificationManager:
    """
    Manages desktop notifications via freedesktop D-Bus / notify-send,
    maintains a privacy-preserving session ring-buffer, and filters sensitive data.
    """

    def __init__(self, store_path: Optional[str] = None):
        self.store_path = store_path or DEFAULT_NOTIFICATION_STORE
        self.enabled_categories: Set[str] = set(DEFAULT_ENABLED_CATEGORIES)
        self._load_store()

    def _load_store(self) -> None:
        """Load session notifications from local file."""
        if os.path.isfile(self.store_path):
            try:
                with open(self.store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.session_notifications: List[Dict[str, Any]] = data.get("notifications", [])
                saved_categories = data.get("enabled_categories")
                if saved_categories and isinstance(saved_categories, list):
                    self.enabled_categories = set(saved_categories)
            except Exception:
                self.session_notifications = []
        else:
            self.session_notifications = []

    def _save_store(self) -> None:
        """Save session notifications to local file (max 50 recent items)."""
        try:
            os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump({
                    "notifications": self.session_notifications[-50:],
                    "enabled_categories": sorted(list(self.enabled_categories)),
                }, f, indent=2)
        except Exception:
            pass

    def get_server_info(self) -> Dict[str, Any]:
        """Query freedesktop notification daemon server information."""
        try:
            res = subprocess.run(
                [
                    "gdbus", "call", "--session",
                    "--dest", "org.freedesktop.Notifications",
                    "--object-path", "/org/freedesktop/Notifications",
                    "--method", "org.freedesktop.Notifications.GetServerInformation",
                ],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if res.returncode == 0:
                raw = res.stdout.strip()
                # Parse format: ('gnome-shell', 'GNOME', '50.1', '1.2')
                cleaned = raw.strip("()").replace("'", "")
                parts = [p.strip() for p in cleaned.split(",")]
                return {
                    "available": True,
                    "server_name": parts[0] if len(parts) > 0 else "Unknown",
                    "vendor": parts[1] if len(parts) > 1 else "Unknown",
                    "version": parts[2] if len(parts) > 2 else "Unknown",
                    "spec_version": parts[3] if len(parts) > 3 else "Unknown",
                }
        except Exception:
            pass

        return {
            "available": False,
            "server_name": "Unavailable",
            "vendor": "Unavailable",
            "version": "Unavailable",
            "spec_version": "Unavailable",
        }

    def get_capabilities(self) -> List[str]:
        """Query supported notification server capabilities."""
        try:
            res = subprocess.run(
                [
                    "gdbus", "call", "--session",
                    "--dest", "org.freedesktop.Notifications",
                    "--object-path", "/org/freedesktop/Notifications",
                    "--method", "org.freedesktop.Notifications.GetCapabilities",
                ],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if res.returncode == 0:
                raw = res.stdout.strip()
                # Parse format: (['actions', 'body', 'body-markup', 'icon-static', 'persistence', 'sound'],)
                cleaned = raw.strip("(),[]").replace("'", "")
                return [p.strip() for p in cleaned.split(",") if p.strip()]
        except Exception:
            pass
        return ["body", "persistence"]

    def set_category_state(self, category: str, enabled: bool) -> bool:
        """Enable or disable a notification category."""
        clean_cat = category.strip().lower()
        if clean_cat not in SUPPORTED_CATEGORIES:
            return False

        if enabled:
            self.enabled_categories.add(clean_cat)
        else:
            self.enabled_categories.discard(clean_cat)

        self._save_store()
        return True

    def clear_session_notifications(self) -> int:
        """Clear all notifications from the session store."""
        count = len(self.session_notifications)
        self.session_notifications = []
        self._save_store()
        return count

    def send_notification(
        self,
        title: str,
        body: str = "",
        urgency: str = "normal",
        category: str = "system",
    ) -> Dict[str, Any]:
        """
        Send a desktop notification with sensitive data scrubbing
        and record in active session log.
        """
        clean_cat = category.strip().lower()
        if clean_cat not in self.enabled_categories:
            return {
                "status": "filtered",
                "action": "send_notification",
                "category": clean_cat,
                "message": f"Notification dropped: category '{clean_cat}' is currently disabled.",
            }

        # Scrub passwords, OTP codes, and auth tokens
        safe_title = sanitize_notification_text(title)
        safe_body = sanitize_notification_text(body)
        clean_urgency = urgency.lower() if urgency.lower() in ("low", "normal", "critical") else "normal"

        # Dispatch via /usr/bin/notify-send
        cmd = [
            "/usr/bin/notify-send",
            "-a", "Maven JARVIS",
            "-u", clean_urgency,
            "-c", clean_cat,
            safe_title,
            safe_body,
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=3.0)
            record = {
                "id": len(self.session_notifications) + 1,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "title": safe_title,
                "body": safe_body,
                "urgency": clean_urgency,
                "category": clean_cat,
            }
            self.session_notifications.append(record)
            self._save_store()

            return {
                "status": "success",
                "action": "send_notification",
                "notification": record,
                "message": f"Notification '{safe_title}' dispatched successfully.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "action": "send_notification",
                "message": f"Failed to dispatch notification: {str(exc)}",
            }

    def get_status(self) -> Dict[str, Any]:
        """Comprehensive status report of the notification subsystem."""
        server_info = self.get_server_info()
        capabilities = self.get_capabilities()

        return {
            "status": "success",
            "server": server_info,
            "capabilities": capabilities,
            "enabled_categories": sorted(list(self.enabled_categories)),
            "supported_categories": sorted(list(SUPPORTED_CATEGORIES)),
            "session_notification_count": len(self.session_notifications),
            "recent_notifications": self.session_notifications[-5:],
            "platform_limitations": (
                "GNOME Wayland intentionally does not expose an unrestricted global notification "
                "history reading API across unprivileged processes to prevent secret snooping. "
                "Maven tracks session notifications and interacts through standard freedesktop endpoints."
            ),
        }
