"""Unit tests for Maverick DevOS Hardware & Desktop Lifecycle Management."""

import unittest
from unittest.mock import patch, MagicMock

from maverick.system.lifecycle import (
    is_screen_locked,
    get_hardware_profile,
    register_gnome_shortcut,
    reinitialize_audio_devices,
)


class TestLifecycle(unittest.TestCase):
    """Test suite for ASUS ROG Strix and GNOME lifecycle helpers."""

    def test_is_screen_locked_returns_bool(self):
        locked = is_screen_locked()
        self.assertIsInstance(locked, bool)

    def test_get_hardware_profile_keys(self):
        prof = get_hardware_profile()
        self.assertIn("vendor", prof)
        self.assertIn("product_name", prof)
        self.assertIn("is_rog_strix", prof)
        self.assertIn("screen_locked", prof)
        self.assertIsInstance(prof["is_rog_strix"], bool)

    def test_reinitialize_audio_devices(self):
        res = reinitialize_audio_devices()
        self.assertIn("status", res)
        self.assertIn("timestamp", res)
        self.assertIn("details", res)

    @patch("shutil.which")
    def test_register_gnome_shortcut_when_gsettings_missing(self, mock_which):
        mock_which.return_value = None
        ok = register_gnome_shortcut()
        self.assertFalse(ok)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_register_gnome_shortcut_success(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/gsettings"
        mock_run.return_value = MagicMock(return_value=0, stdout="['/some/existing/']")
        ok = register_gnome_shortcut()
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()

