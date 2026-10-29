"""Unit tests for Maverick DevOS Desktop Launcher."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.desktop.launcher import (
    is_binary_available,
    get_running_pids,
    check_app_status,
    launch_app,
)
from maverick.core.config import AuthorizedApp
from maverick.core.security import get_authorized_app, ConfirmationRequiredError, SecurityError


class TestLauncher(unittest.TestCase):
    """Test desktop launcher status checks and safe execution."""

    @patch("os.path.isfile")
    @patch("os.access")
    def test_is_binary_available(self, mock_access, mock_isfile):
        mock_isfile.return_value = True
        mock_access.return_value = True
        self.assertTrue(is_binary_available("/usr/bin/code"))

        mock_access.return_value = False
        self.assertFalse(is_binary_available("/usr/bin/code"))

    @patch("maverick.desktop.launcher.is_binary_available")
    @patch("maverick.desktop.launcher.get_running_pids")
    def test_check_app_status(self, mock_pids, mock_avail):
        mock_avail.return_value = True
        mock_pids.return_value = [1234, 5678]

        status = check_app_status("spotify")
        self.assertEqual(status["id"], "spotify")
        self.assertTrue(status["installed"])
        self.assertTrue(status["running"])
        self.assertEqual(status["pids"], [1234, 5678])

    @patch("maverick.desktop.launcher.is_binary_available")
    def test_launch_app_not_installed(self, mock_avail):
        mock_avail.return_value = False
        res = launch_app("spotify")
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["code"], "APP_NOT_INSTALLED")

    @patch("maverick.desktop.launcher.is_binary_available")
    def test_launch_app_confirmation_required(self, mock_avail):
        mock_avail.return_value = True
        # gnome-terminal has requires_confirmation=True
        with self.assertRaises(ConfirmationRequiredError):
            launch_app("gnome-terminal", confirmed=False)

    @patch("maverick.desktop.launcher.is_binary_available")
    @patch("subprocess.Popen")
    @patch("time.sleep")
    def test_launch_app_success(self, mock_sleep, mock_popen, mock_avail):
        mock_avail.return_value = True
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_proc.poll.return_value = None  # Process is running healthy
        mock_popen.return_value = mock_proc

        res = launch_app("code", args=["~"], confirmed=False)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["pid"], 9999)
        self.assertEqual(res["target"], "code")

        # Verify subprocess.Popen was called safely with decoupled session
        mock_popen.assert_called_once()
        call_args, call_kwargs = mock_popen.call_args
        cmd = call_args[0]
        self.assertEqual(cmd[0], "/usr/bin/code")
        self.assertTrue(call_kwargs.get("start_new_session"))
        self.assertIn("WAYLAND_DISPLAY", call_kwargs.get("env"))


if __name__ == "__main__":
    unittest.main()
