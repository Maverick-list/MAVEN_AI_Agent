"""Unit tests for BootGreetingManager."""

from datetime import datetime
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from maverick.voice.config import VoiceConfig
from maverick.voice.greeting import BootGreetingManager


class TestBootGreetingManager(unittest.TestCase):
    """Test suite for once-per-boot greeting and presence coordinator."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.config = VoiceConfig(
            boot_greeting_enabled=True,
            quiet_hours_enabled=True,
            quiet_hours_start=22,
            quiet_hours_end=7,
        )
        self.manager = BootGreetingManager(self.config)
        self.manager.BOOT_TOKEN_FILE = os.path.join(self.tmp_dir.name, "boot_greeting.json")
        self.manager.STATE_DIR = self.tmp_dir.name

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_boot_id_and_single_greeting_enforcement(self):
        """Greeting must only fire once per unique kernel boot ID."""
        self.assertFalse(self.manager.has_greeted_this_boot())

        self.manager.mark_greeted("Good morning. Maven is online.")
        self.assertTrue(self.manager.has_greeted_this_boot())

        # Second evaluation should be blocked
        should_speak, reason = self.manager.should_speak_greeting(is_muted=False)
        self.assertFalse(should_speak)
        self.assertEqual(reason, "already_greeted_this_boot")

    def test_quiet_hours_detection(self):
        """Verify quiet hours across midnight boundary."""
        # 23:30 (Quiet)
        dt_night = datetime(2026, 10, 30, 23, 30)
        self.assertTrue(self.manager.is_in_quiet_hours(dt_night))

        # 03:00 (Quiet)
        dt_dawn = datetime(2026, 10, 31, 3, 0)
        self.assertTrue(self.manager.is_in_quiet_hours(dt_dawn))

        # 14:00 (Active / Not quiet)
        dt_day = datetime(2026, 10, 30, 14, 0)
        self.assertFalse(self.manager.is_in_quiet_hours(dt_day))

    def test_mute_suppresses_speech(self):
        """Muted microphone/assistant must suppress audible boot greeting."""
        dt_day = datetime(2026, 10, 30, 14, 0)
        with patch.object(self.manager, "is_in_quiet_hours", return_value=False):
            should_speak, reason = self.manager.should_speak_greeting(is_muted=True)
            self.assertFalse(should_speak)
            self.assertEqual(reason, "system_muted")

    def test_bilingual_time_of_day_generation(self):
        """Greetings should reflect correct time of day in EN and ID."""
        # Morning (08:00)
        dt_morning = datetime(2026, 10, 30, 8, 0)
        en_m, id_m = self.manager.generate_greeting(dt_morning)
        self.assertIn("Good morning", en_m)
        self.assertIn("Selamat pagi", id_m)

        # Evening (19:00)
        dt_evening = datetime(2026, 10, 30, 19, 0)
        en_e, id_e = self.manager.generate_greeting(dt_evening)
        self.assertIn("Good evening", en_e)
        self.assertIn("Selamat malam", id_e)

    def test_execute_boot_greeting_dispatch(self):
        """Execution should trigger speech output and mark boot token."""
        mock_session = MagicMock()
        mock_session.is_muted = False

        with patch.object(self.manager, "should_speak_greeting", return_value=(True, "ready")), \
             patch.object(self.manager, "send_desktop_notification", return_value=True):
            spoken = self.manager.execute_boot_greeting(mock_session)
            self.assertIsNotNone(spoken)
            mock_session.speak_stream.assert_called_once()
            self.assertTrue(self.manager.has_greeted_this_boot())


if __name__ == "__main__":
    unittest.main()

