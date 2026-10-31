"""Unit tests for Permanent Natural Voice Architecture & Local Neural TTS."""

import os
import unittest
from unittest.mock import MagicMock, patch

from maverick.voice.config import VoiceConfig
from maverick.voice.local_neural_tts import LocalNeuralTTSProvider
from maverick.voice.tts import HybridTTSProvider, MockTTSProvider, SpeechDispatcherTTS


class TestPermanentVoiceSystem(unittest.TestCase):
    def setUp(self):
        self.config = VoiceConfig()

    def test_local_neural_provider_availability(self):
        provider = LocalNeuralTTSProvider(self.config)
        self.assertEqual(provider.voice_name, "common_voice_id_19961910")
        prompt_path = provider.get_voice_prompt_path()
        self.assertTrue(prompt_path.endswith(".mp3"))
        status = provider.get_public_status()
        self.assertEqual(status["engine"], "local_neural")
        self.assertEqual(status["model_name"], "pocket-tts-indonesian-6l")
        self.assertEqual(status["license"], "CC-BY-4.0")

    def test_hybrid_tts_defaults_to_local_neural(self):
        mock_local = MagicMock()
        mock_local.is_available.return_value = True
        mock_local.speak.return_value = True

        mock_el = MagicMock()
        mock_el.is_configured.return_value = True

        mock_fb = MagicMock()

        hybrid = HybridTTSProvider(
            config=self.config,
            local_neural=mock_local,
            elevenlabs=mock_el,
            fallback=mock_fb,
        )

        ok = hybrid.speak("Halo Maven, tes suara lokal.")
        self.assertTrue(ok)
        self.assertEqual(hybrid.last_used_engine, "local_neural")
        mock_local.speak.assert_called_once()
        mock_el.speak.assert_not_called()
        mock_fb.speak.assert_not_called()

    def test_hybrid_tts_elevenlabs_opt_in_and_fallback_to_local_neural(self):
        mock_local = MagicMock()
        mock_local.is_available.return_value = True
        mock_local.speak.return_value = True

        mock_el = MagicMock()
        mock_el.is_configured.return_value = True
        mock_el.speak.return_value = False  # ElevenLabs fails (e.g. quota exceeded)
        mock_el._last_error_code = "quota_exceeded"

        mock_fb = MagicMock()

        with patch("maverick.voice.tts.load_voice_settings", return_value={"tts_engine": "elevenlabs"}):
            hybrid = HybridTTSProvider(
                config=self.config,
                local_neural=mock_local,
                elevenlabs=mock_el,
                fallback=mock_fb,
            )
            ok = hybrid.speak("Halo Maven.")
            self.assertTrue(ok)
            # Should have fallen back to local neural TTS, NOT speech dispatcher!
            self.assertEqual(hybrid.last_used_engine, "local_neural")
            mock_el.speak.assert_called_once()
            mock_local.speak.assert_called_once()
            mock_fb.speak.assert_not_called()

    def test_hybrid_tts_emergency_fallback_speaks_warning(self):
        mock_local = MagicMock()
        mock_local.is_available.return_value = False  # Local neural unavailable

        mock_el = MagicMock()
        mock_el.is_configured.return_value = False

        mock_fb = MagicMock()
        mock_fb.speak.return_value = True

        hybrid = HybridTTSProvider(
            config=self.config,
            local_neural=mock_local,
            elevenlabs=mock_el,
            fallback=mock_fb,
        )

        ok = hybrid.speak("Halo.")
        self.assertTrue(ok)
        self.assertEqual(hybrid.last_used_engine, "speech_dispatcher")
        # Verify emergency notification was spoken first
        self.assertEqual(mock_fb.speak.call_count, 2)
        first_call_args = mock_fb.speak.call_args_list[0]
        self.assertIn("Emergency fallback: voice switched to speech dispatcher.", first_call_args[0][0])
        second_call_args = mock_fb.speak.call_args_list[1]
        self.assertEqual(second_call_args[0][0], "Halo.")

    def test_hybrid_tts_status_structure(self):
        mock_local = MagicMock()
        mock_local.get_public_status.return_value = {"engine": "local_neural", "available": True}
        mock_el = MagicMock()
        mock_el.get_public_status.return_value = {"engine": "elevenlabs", "configured": False}
        mock_fb = MagicMock()
        mock_fb.is_available.return_value = True

        hybrid = HybridTTSProvider(
            config=self.config,
            local_neural=mock_local,
            elevenlabs=mock_el,
            fallback=mock_fb,
        )

        status = hybrid.get_status()
        self.assertEqual(status["active_engine"], "local_neural")
        self.assertEqual(status["preferred_engine"], "local_neural")
        self.assertIn("local_neural", status)
        self.assertIn("elevenlabs", status)
        self.assertIn("fallback", status)


if __name__ == "__main__":
    unittest.main()

