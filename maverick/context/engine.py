"""Maverick DevOS - Context Engine & Multi-Signal Aggregator."""

import time
from typing import Any, Dict, Optional
from maverick.system.monitor import (
    get_cpu_usage,
    get_memory_usage,
    get_disk_usage,
    get_battery_status,
    get_os_session_info,
    get_network_status,
)
from maverick.desktop.awareness import (
    get_running_authorized_apps,
    get_active_application_context,
)
from maverick.notifications.manager import NotificationManager
from maverick.activity.logger import ActivityLogger


class ContextEngine:
    """
    Combines authorized desktop, system telemetry, media, and recent activity
    signals into a concise, privacy-respecting context snapshot for Maven JARVIS.
    """

    def __init__(
        self,
        notification_mgr: Optional[NotificationManager] = None,
        activity_logger: Optional[ActivityLogger] = None,
    ):
        self.notification_mgr = notification_mgr or NotificationManager()
        self.activity_logger = activity_logger or ActivityLogger()

    def get_context(self) -> Dict[str, Any]:
        """
        Aggregate authorized contextual signals into a structured dictionary.
        Strictly read-only; records no background surveillance or private user data.
        """
        os_info = get_os_session_info()
        cpu = get_cpu_usage()
        memory = get_memory_usage()
        disk = get_disk_usage()
        battery = get_battery_status()
        network = get_network_status()

        app_ctx = get_active_application_context()
        running_apps = app_ctx.get("running_authorized_apps", [])
        media_info = app_ctx.get("media", {})
        browser_info = app_ctx.get("automation_browser", {})

        recent_notifications = self.notification_mgr.session_notifications[-3:]
        recent_actions = self.activity_logger.get_recent_activity(limit=5)

        return {
            "status": "success",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "system": {
                "os": os_info.get("os"),
                "desktop": os_info.get("desktop"),
                "session_type": os_info.get("session_type"),
                "uptime_hours": os_info.get("uptime_hours"),
                "cpu_percent": cpu.get("usage_percent"),
                "cpu_cores": cpu.get("cores_logical"),
                "memory_used_gb": memory.get("used_gb"),
                "memory_available_gb": memory.get("available_gb"),
                "memory_percent": memory.get("percent"),
                "disk_free_gb": disk.get("root", {}).get("free_gb"),
                "disk_percent": disk.get("root", {}).get("percent"),
                "battery_percent": battery.get("percent"),
                "is_charging": battery.get("is_charging"),
                "ac_connected": battery.get("ac_connected"),
                "network_connected": network.get("connected"),
            },
            "applications": {
                "running_authorized_count": len(running_apps),
                "running_apps": [
                    {
                        "app_id": app.get("app_id"),
                        "display_name": app.get("display_name"),
                        "pid": app.get("primary_pid"),
                        "memory_mb": app.get("memory_rss_mb"),
                    }
                    for app in running_apps
                ],
                "active_media": media_info.get("spotify") if "spotify" in media_info else None,
                "browser_tab": browser_info.get("active_tab") if browser_info.get("active") else None,
            },
            "notifications": {
                "active_session_count": len(self.notification_mgr.session_notifications),
                "recent": recent_notifications,
            },
            "recent_maven_actions": recent_actions,
            "privacy_guarantees": {
                "surveillance": "none",
                "keylogging": "disabled",
                "clipboard_recording": "disabled",
                "secret_scrubbing": "enforced",
            },
        }
