"""Regression and security tests for Browser Lifecycle hardening."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.browser.config import BrowserConfig
from maverick.browser.lifecycle import BrowserLifecycle, BrowserLifecycleError


class TestBrowserLifecycleHardening(unittest.TestCase):
    """Test CDP loopback restrictions, process ownership, and personal session isolation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config = BrowserConfig(
            binary_path="/usr/bin/google-chrome",
            host="127.0.0.1",
            port=9222,
            user_data_dir=self.temp_dir.name,
            screenshot_dir=os.path.join(self.temp_dir.name, "screenshots"),
            timeout_seconds=2.0,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_disallowed_external_host_rejected(self):
        """Test BrowserConfig rejects binding to non-loopback or 0.0.0.0."""
        with self.assertRaises(ValueError):
            BrowserConfig(host="0.0.0.0")
        with self.assertRaises(ValueError):
            BrowserConfig(host="192.168.1.50")
        with self.assertRaises(ValueError):
            BrowserConfig(host="evil.com")

    def test_devtools_active_port_resolution(self):
        """Test resolving dynamic active port from DevToolsActivePort file."""
        port_file = self.config.devtools_active_port_file
        with open(port_file, "w", encoding="utf-8") as f:
            f.write("42195\n/devtools/browser/d798935c-c2bf-466f-b258-000\n")

        self.assertEqual(self.config.resolve_active_port(), 42195)
        self.assertEqual(self.config.cdp_http_url, "http://127.0.0.1:42195")

    @patch("maverick.browser.lifecycle.subprocess.Popen")
    @patch("maverick.browser.lifecycle.urllib.request.urlopen")
    def test_start_includes_explicit_loopback_address(self, mock_urlopen, mock_popen):
        """Test that Chrome launch explicitly includes --remote-debugging-address=127.0.0.1."""
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_popen.return_value = mock_proc

        # Port initially closed (URLError), then active after start
        mock_resp_active = MagicMock()
        mock_resp_active.status = 200
        mock_resp_active.__enter__.return_value = mock_resp_active

        mock_urlopen.side_effect = [
            Exception("Port closed"),  # is_active before start
            Exception("Port closed"),  # probe foreign session before start
            mock_resp_active,          # is_active polling after start
        ]

        lifecycle = BrowserLifecycle(self.config)
        with patch.object(lifecycle, "owns_active_session", return_value=True):
            res = lifecycle.start()

        self.assertEqual(res["status"], "success")
        called_cmd = mock_popen.call_args[0][0]
        self.assertIn("--remote-debugging-address=127.0.0.1", called_cmd)
        self.assertIn(f"--user-data-dir={self.config.user_data_dir}", called_cmd)

    @patch("maverick.browser.lifecycle.urllib.request.urlopen")
    def test_refuse_to_hijack_personal_session(self, mock_urlopen):
        """
        Test that if port is listening but is NOT owned by Maven's automation profile,
        lifecycle.start() refuses to connect to prevent hijacking personal browser data.
        """
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        lifecycle = BrowserLifecycle(self.config)
        # Port responds, but owns_active_session returns False (neither session file nor DevToolsActivePort)
        res = lifecycle.start()
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["code"], "EXTERNAL_SESSION_CONFLICT")
        self.assertIn("refusing to connect to prevent hijacking personal browser data", res["message"].lower())


if __name__ == "__main__":
    unittest.main()
