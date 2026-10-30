"""Maverick DevOS - Final Integration & Production Readiness Acceptance Tests."""

import unittest
from unittest.mock import patch, MagicMock
import os
import sys

from maverick.core.profile import get_active_profile, set_active_profile, is_feature_enabled
from maverick.voice.config import VoiceConfig
from maverick.voice.controller import VoiceController
from maverick.voice.intent import BilingualIntentClassifier
from maverick.context.engine import ContextEngine
from maverick.launcher import verify_openclaw_gateway, verify_audio_hardware, verify_whisper_model


class TestFinalIntegration(unittest.TestCase):
    """Rigorous acceptance testing for production readiness."""

    def setUp(self):
        self.config = VoiceConfig()
        self.ctl = VoiceController(self.config)
        # Ensure tests leave profile in developer mode
        set_active_profile("developer")

    def tearDown(self):
        set_active_profile("developer")

    # 1. Profile Switching & Reversibility
    def test_profile_switching(self):
        # Switch to Light Mode
        res_light = set_active_profile("light")
        self.assertEqual(res_light["status"], "success")
        self.assertEqual(res_light["active_profile"], "light")
        self.assertFalse(is_feature_enabled("chrome_cdp_automation"))
        self.assertFalse(is_feature_enabled("full_desktop_context"))

        # Context engine in light mode returns basic context
        ce = ContextEngine()
        ctx_light = ce.get_context()
        self.assertEqual(ctx_light["status"], "success")
        self.assertEqual(ctx_light["applications"]["browser_tab"], None)
        self.assertEqual(ctx_light["recent_maven_actions"], [])

        # Switch back to Developer Mode
        res_dev = set_active_profile("developer")
        self.assertEqual(res_dev["status"], "success")
        self.assertEqual(res_dev["active_profile"], "developer")
        self.assertTrue(is_feature_enabled("chrome_cdp_automation"))
        self.assertTrue(is_feature_enabled("full_desktop_context"))

    # 2. Wake-Word Conversational Acknowledgment
    def test_wake_word_acknowledgment(self):
        # English wake greeting
        res_en = self.ctl.handle_voice_command("Hey Maven")
        self.assertEqual(res_en["status"], "success")
        self.assertEqual(res_en["action"], "wake_acknowledgment")
        self.assertEqual(res_en["response"], "Yes, I'm listening.")

        # Indonesian wake greeting
        res_id = self.ctl.handle_voice_command("Halo Maven")
        self.assertEqual(res_id["status"], "success")
        self.assertEqual(res_id["action"], "wake_acknowledgment")
        self.assertEqual(res_id["response"], "Ya, saya mendengarkan.")

        # Single word wake greeting
        res_single = self.ctl.handle_voice_command("Maven")
        self.assertEqual(res_single["status"], "success")
        self.assertEqual(res_single["action"], "wake_acknowledgment")
        self.assertEqual(res_single["response"], "Yes, I'm listening.")

    # 3. Application Launch Verbal Feedback
    def test_app_launch_feedback(self):
        # VS Code launch verbal response
        res = self.ctl.handle_voice_command("Maven, open Visual Studio Code")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["action"], "app_launch")
        self.assertTrue(
            "Visual Studio Code is open" in res["response"] or "Visual Studio Code is already open" in res["response"]
        )

        # Indonesian VS Code launch verbal response
        res_id = self.ctl.handle_voice_command("Maven, buka Visual Studio Code")
        self.assertEqual(res_id["status"], "success")
        self.assertEqual(res_id["action"], "app_launch")
        self.assertTrue(
            "Visual Studio Code" in res_id["response"] and ("sudah berjalan" in res_id["response"] or "dibuka" in res_id["response"])
        )

    # 4. Actual Telemetry Verbal Feedback
    def test_telemetry_verbal_feedback(self):
        # Indonesian RAM telemetry
        res_ram = self.ctl.handle_voice_command("Maven, berapa sisa RAM laptopku?")
        self.assertEqual(res_ram["status"], "success")
        self.assertEqual(res_ram["action"], "system_ram")
        self.assertIn("RAM yang tersedia", res_ram["response"])
        self.assertIn("gigabyte", res_ram["response"])

        # English RAM telemetry
        res_en = self.ctl.handle_voice_command("Maven, how much RAM is available?")
        self.assertEqual(res_en["status"], "success")
        self.assertEqual(res_en["action"], "system_ram")
        self.assertIn("RAM available", res_en["response"])

    # 5. Security & Confirmation Gates
    def test_dangerous_actions_gated(self):
        # Terminal requires confirmation
        res_term = self.ctl.handle_voice_command("Maven, open terminal", confirmed=False)
        self.assertEqual(res_term["status"], "confirmation_required")
        self.assertIn("requires confirmation", res_term["response"])

        # Firefox requires confirmation
        res_ff = self.ctl.handle_voice_command("Maven, open firefox", confirmed=False)
        self.assertEqual(res_ff["status"], "confirmation_required")
        self.assertIn("requires confirmation", res_ff["response"])

    # 6. Unknown Speech Fallback
    def test_unknown_speech_safe_fallback(self):
        res = self.ctl.handle_voice_command("Fly me to the moon on a giant rocket", confirmed=False)
        # Must route safely to conversational fallback or graceful notice, never executing arbitrary desktop actions
        self.assertIn(res["status"], ("success", "unhandled", "error", "rate_limited"))
        self.assertNotIn("action", res)

    # 7. Volume Boundary Enforcement
    def test_volume_bounding(self):
        parsed_neg = BilingualIntentClassifier.classify("Set volume to -50")
        self.assertEqual(parsed_neg["intent"], "spotify_volume")
        self.assertEqual(parsed_neg["target"], 0)

        parsed_over = BilingualIntentClassifier.classify("Set volume to 200")
        self.assertEqual(parsed_over["intent"], "spotify_volume")
        self.assertEqual(parsed_over["target"], 100)

    # 8. Launcher Subsystem Verifications
    def test_launcher_diagnostics(self):
        gw_ok, _ = verify_openclaw_gateway()
        self.assertTrue(gw_ok)

        audio_ok, _, _ = verify_audio_hardware()
        self.assertTrue(audio_ok)

        w_ok, _ = verify_whisper_model()
        self.assertTrue(w_ok)


if __name__ == "__main__":
    unittest.main()
