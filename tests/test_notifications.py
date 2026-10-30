"""Unit tests for Maverick notification filtering and manager."""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from maverick.notifications.filter import (
    sanitize_notification_text,
    SUPPORTED_CATEGORIES,
    DEFAULT_ENABLED_CATEGORIES,
)
from maverick.notifications.manager import NotificationManager


class TestNotificationFilter(unittest.TestCase):
    """Test notification text redaction and category defaults."""

    def test_sanitize_otp_codes(self):
        text = "Your verification code is 482910."
        sanitized = sanitize_notification_text(text)
        self.assertNotIn("482910", sanitized)
        self.assertIn("[REDACTED_CODE]", sanitized)

    def test_preserve_calendar_years(self):
        text = "Meeting set for October 2026."
        sanitized = sanitize_notification_text(text)
        self.assertIn("2026", sanitized)
        self.assertNotIn("[REDACTED_CODE]", sanitized)

    def test_sanitize_passwords(self):
        text = "Account password: SuperSecretPass123! created"
        sanitized = sanitize_notification_text(text)
        self.assertNotIn("SuperSecretPass123!", sanitized)
        self.assertIn("[REDACTED_PASSWORD]", sanitized)

    def test_sanitize_auth_tokens(self):
        text = "API auth: abcd1234efgh5678ijkl9012"
        sanitized = sanitize_notification_text(text)
        self.assertNotIn("abcd1234efgh5678ijkl9012", sanitized)
        self.assertIn("[REDACTED_TOKEN]", sanitized)

    def test_sanitize_non_string(self):
        self.assertEqual(sanitize_notification_text(None), "")
        self.assertEqual(sanitize_notification_text(12345), "")

    def test_supported_categories(self):
        self.assertIn("system", SUPPORTED_CATEGORIES)
        self.assertIn("media", SUPPORTED_CATEGORIES)
        self.assertIn("browser", SUPPORTED_CATEGORIES)
        self.assertIn("alert", SUPPORTED_CATEGORIES)
        self.assertTrue(DEFAULT_ENABLED_CATEGORIES.issubset(SUPPORTED_CATEGORIES))


class TestNotificationManager(unittest.TestCase):
    """Test NotificationManager lifecycle, store, and D-Bus integration."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store_file = os.path.join(self.temp_dir.name, "notifications.json")
        self.mgr = NotificationManager(store_path=self.store_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initial_state(self):
        self.assertEqual(self.mgr.session_notifications, [])
        self.assertTrue(os.path.exists(self.store_file) is False)

    @patch("subprocess.run")
    def test_send_notification_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="42\n", stderr="")

        res = self.mgr.send_notification(
            title="Deployment Update",
            body="Your OTP is 998877 and password: topsecret",
            category="system",
            urgency="normal",
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(len(self.mgr.session_notifications), 1)

        record = self.mgr.session_notifications[0]
        self.assertEqual(record["title"], "Deployment Update")
        # Ensure sensitive contents were redacted
        self.assertNotIn("998877", record["body"])
        self.assertNotIn("topsecret", record["body"])
        self.assertIn("[REDACTED_CODE]", record["body"])
        self.assertIn("[REDACTED_PASSWORD]", record["body"])

        # Check file store was updated
        self.assertTrue(os.path.exists(self.store_file))

    def test_send_notification_disabled_category(self):
        self.mgr.enabled_categories = {"system"}  # 'social' disabled
        res = self.mgr.send_notification(
            title="Chat",
            body="New message",
            category="social",
        )
        self.assertEqual(res["status"], "filtered")
        self.assertIn("disabled", res.get("message", ""))
        self.assertEqual(len(self.mgr.session_notifications), 0)

    def test_set_category_state(self):
        self.assertTrue(self.mgr.set_category_state("social", True))
        self.assertIn("social", self.mgr.enabled_categories)
        self.assertTrue(self.mgr.set_category_state("social", False))
        self.assertNotIn("social", self.mgr.enabled_categories)
        self.assertFalse(self.mgr.set_category_state("invalid_xyz", True))

    @patch("subprocess.run")
    def test_get_server_info(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="('gnome-shell', 'GNOME', '46.0', '1.2')\n",
            stderr="",
        )
        info = self.mgr.get_server_info()
        self.assertTrue(info["available"])
        self.assertEqual(info["server_name"], "gnome-shell")
        self.assertEqual(info["vendor"], "GNOME")

    @patch("subprocess.run")
    def test_get_capabilities(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="(['body', 'actions'],)\n",
            stderr="",
        )
        caps = self.mgr.get_capabilities()
        self.assertIn("body", caps)
        self.assertIn("actions", caps)

    def test_clear_session_notifications(self):
        self.mgr.session_notifications = [{"id": 1, "title": "Test"}]
        self.mgr._save_store()
        self.assertEqual(len(self.mgr.session_notifications), 1)

        cleared = self.mgr.clear_session_notifications()
        self.assertEqual(cleared, 1)
        self.assertEqual(len(self.mgr.session_notifications), 0)

    def test_get_status(self):
        with patch.object(self.mgr, "get_server_info", return_value={"available": True}):
            with patch.object(self.mgr, "get_capabilities", return_value=["body"]):
                status = self.mgr.get_status()
                self.assertEqual(status["status"], "success")
                self.assertIn("platform_limitations", status)
                self.assertIn("supported_categories", status)


if __name__ == "__main__":
    unittest.main()
