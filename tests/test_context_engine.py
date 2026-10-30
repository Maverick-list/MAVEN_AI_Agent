"""Unit tests for Maverick ContextEngine multi-signal aggregator."""

import unittest
from unittest.mock import MagicMock, patch

from maverick.context.engine import ContextEngine


class TestContextEngine(unittest.TestCase):
    """Test ContextEngine multi-signal contextual aggregation."""

    def setUp(self):
        self.mock_notif_mgr = MagicMock()
        self.mock_notif_mgr.session_notifications = [
            {"id": 1, "title": "Notification 1", "body": "Body 1"},
            {"id": 2, "title": "Notification 2", "body": "Body 2"},
        ]
        self.mock_logger = MagicMock()
        self.mock_logger.get_recent_activity.return_value = [
            {"action_type": "desktop_launch", "target": "spotify", "status": "success"},
        ]
        self.engine = ContextEngine(
            notification_mgr=self.mock_notif_mgr,
            activity_logger=self.mock_logger,
        )

    @patch("maverick.context.engine.get_network_status")
    @patch("maverick.context.engine.get_battery_status")
    @patch("maverick.context.engine.get_disk_usage")
    @patch("maverick.context.engine.get_memory_usage")
    @patch("maverick.context.engine.get_cpu_usage")
    @patch("maverick.context.engine.get_os_session_info")
    @patch("maverick.context.engine.get_active_application_context")
    def test_get_context_aggregation(
        self,
        mock_active_ctx,
        mock_os_info,
        mock_cpu,
        mock_memory,
        mock_disk,
        mock_battery,
        mock_network,
    ):
        mock_os_info.return_value = {
            "os": "Ubuntu 24.04 LTS",
            "desktop": "GNOME",
            "session_type": "wayland",
            "uptime_hours": 12.5,
        }
        mock_cpu.return_value = {"usage_percent": 15.0, "cores_logical": 16}
        mock_memory.return_value = {"used_gb": 8.0, "available_gb": 8.0, "percent": 50.0}
        mock_disk.return_value = {"root": {"free_gb": 120.0, "percent": 45.0}}
        mock_battery.return_value = {"percent": 95, "is_charging": False, "ac_connected": True}
        mock_network.return_value = {"connected": True}

        mock_active_ctx.return_value = {
            "running_authorized_apps": [
                {"app_id": "spotify", "display_name": "Spotify", "primary_pid": 1122, "memory_rss_mb": 150.0},
            ],
            "media": {
                "spotify": {"player": "spotify", "playback_status": "Playing", "title": "Song A"},
            },
            "automation_browser": {
                "active": True,
                "active_tab": {"title": "Google", "url": "https://www.google.com"},
            },
        }

        ctx = self.engine.get_context()

        self.assertEqual(ctx["status"], "success")
        self.assertIn("timestamp", ctx)

        # System telemetry checks
        sys_data = ctx["system"]
        self.assertEqual(sys_data["os"], "Ubuntu 24.04 LTS")
        self.assertEqual(sys_data["session_type"], "wayland")
        self.assertEqual(sys_data["cpu_percent"], 15.0)
        self.assertEqual(sys_data["battery_percent"], 95)
        self.assertTrue(sys_data["ac_connected"])
        self.assertTrue(sys_data["network_connected"])

        # Applications context checks
        app_data = ctx["applications"]
        self.assertEqual(app_data["running_authorized_count"], 1)
        self.assertEqual(app_data["running_apps"][0]["app_id"], "spotify")
        self.assertEqual(app_data["running_apps"][0]["pid"], 1122)
        self.assertEqual(app_data["active_media"]["playback_status"], "Playing")
        self.assertEqual(app_data["browser_tab"]["title"], "Google")

        # Notification & Activity checks
        notif_data = ctx["notifications"]
        self.assertEqual(notif_data["active_session_count"], 2)
        self.assertEqual(len(notif_data["recent"]), 2)

        recent_actions = ctx["recent_maven_actions"]
        self.assertEqual(len(recent_actions), 1)
        self.assertEqual(recent_actions[0]["action_type"], "desktop_launch")

        # Privacy guarantees
        privacy = ctx["privacy_guarantees"]
        self.assertEqual(privacy["surveillance"], "none")
        self.assertEqual(privacy["keylogging"], "disabled")
        self.assertEqual(privacy["clipboard_recording"], "disabled")
        self.assertEqual(privacy["secret_scrubbing"], "enforced")


if __name__ == "__main__":
    unittest.main()
