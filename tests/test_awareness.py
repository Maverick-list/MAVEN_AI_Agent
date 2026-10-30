"""Unit tests for Application Awareness & Process Intelligence."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.desktop.awareness import (
    get_running_authorized_apps,
    get_active_application_context,
    _get_process_memory_mb,
)


class TestApplicationAwareness(unittest.TestCase):
    """Test discovery of running authorized applications and desktop context."""

    def test_running_authorized_apps_structure(self):
        """Test running authorized apps returns structured process metadata."""
        apps = get_running_authorized_apps()
        self.assertIsInstance(apps, list)
        for app in apps:
            self.assertIn("app_id", app)
            self.assertIn("display_name", app)
            self.assertIn("category", app)
            self.assertIn("is_running", app)
            self.assertTrue(app["is_running"])
            self.assertIn("primary_pid", app)
            self.assertIn("memory_rss_mb", app)
            self.assertGreaterEqual(app["memory_rss_mb"], 0.0)

    def test_active_application_context(self):
        """Test multi-signal desktop context aggregation."""
        ctx = get_active_application_context()
        self.assertIn("running_authorized_apps", ctx)
        self.assertIn("running_count", ctx)
        self.assertIn("media", ctx)
        self.assertIn("automation_browser", ctx)
        self.assertIn("window_detection_note", ctx)
        self.assertIn("Wayland", ctx["window_detection_note"])

    def test_get_process_memory_current_pid(self):
        """Test reading resident memory for current process."""
        my_pid = os.getpid()
        rss = _get_process_memory_mb(my_pid)
        self.assertGreater(rss, 0.0)


if __name__ == "__main__":
    unittest.main()
