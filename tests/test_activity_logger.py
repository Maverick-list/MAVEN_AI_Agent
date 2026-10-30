"""Unit tests for Maverick ActivityLogger."""

import json
import os
import tempfile
import unittest

from maverick.activity.logger import (
    ActivityLogger,
    sanitize_log_dict,
    SENSITIVE_KEY_PATTERNS,
)


class TestActivityLogger(unittest.TestCase):
    """Test privacy-preserving activity logging, scrubbing, and retention."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_file = os.path.join(self.temp_dir.name, "activity.jsonl")
        self.logger = ActivityLogger(log_path=self.log_file, max_records=5)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sanitize_log_dict_redaction(self):
        payload = {
            "user": "alice",
            "password": "supersecretpassword",
            "auth_token": "bearer 1234567890",
            "api_key": "xyz123",
            "session_id": "abc_sess_999",
            "nested": {
                "credit_card": "4111222233334444",
                "safe_item": "hello_world",
            },
            "array_data": [
                {"secret_code": "classified"},
                "plain text",
            ],
        }
        sanitized = sanitize_log_dict(payload)
        self.assertEqual(sanitized["user"], "alice")
        self.assertEqual(sanitized["password"], "[REDACTED]")
        self.assertEqual(sanitized["auth_token"], "[REDACTED]")
        self.assertEqual(sanitized["api_key"], "[REDACTED]")
        self.assertEqual(sanitized["session_id"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["credit_card"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["safe_item"], "hello_world")
        self.assertEqual(sanitized["array_data"][0]["secret_code"], "[REDACTED]")
        self.assertEqual(sanitized["array_data"][1], "plain text")

    def test_log_action_creates_record(self):
        record = self.logger.log_action(
            action_type="desktop_launch",
            target="org.gnome.Calculator",
            status="success",
            confirmed=True,
            details={"pid": 12345, "secret_key": "private_data"},
        )

        self.assertEqual(record["action_type"], "desktop_launch")
        self.assertEqual(record["target"], "org.gnome.Calculator")
        self.assertEqual(record["status"], "success")
        self.assertTrue(record["confirmed"])
        self.assertEqual(record["details"]["pid"], 12345)
        self.assertEqual(record["details"]["secret_key"], "[REDACTED]")
        self.assertTrue(os.path.exists(self.log_file))

        with open(self.log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        logged_data = json.loads(lines[0])
        self.assertEqual(logged_data["action_type"], "desktop_launch")

    def test_get_recent_activity_order(self):
        for i in range(3):
            self.logger.log_action(f"action_{i}", target=f"target_{i}")

        recent = self.logger.get_recent_activity(limit=10)
        self.assertEqual(len(recent), 3)
        # Should be newest first
        self.assertEqual(recent[0]["action_type"], "action_2")
        self.assertEqual(recent[1]["action_type"], "action_1")
        self.assertEqual(recent[2]["action_type"], "action_0")

    def test_retention_enforcement(self):
        # max_records was configured to 5
        for i in range(10):
            self.logger.log_action(f"action_{i}")

        with open(self.log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 5)

        recent = self.logger.get_recent_activity()
        self.assertEqual(len(recent), 5)
        self.assertEqual(recent[0]["action_type"], "action_9")
        self.assertEqual(recent[-1]["action_type"], "action_5")

    def test_clear_activity(self):
        self.logger.log_action("action_1")
        self.logger.log_action("action_2")
        self.assertEqual(len(self.logger.get_recent_activity()), 2)

        res = self.logger.clear()
        self.assertEqual(res["status"], "success")
        self.assertEqual(len(self.logger.get_recent_activity()), 0)
        self.assertFalse(os.path.exists(self.log_file))


if __name__ == "__main__":
    unittest.main()
