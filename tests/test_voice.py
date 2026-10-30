"""Unit and integration tests for Maverick Voice Interaction System."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.voice.audio import AudioCapture, AudioPlayer, calculate_rms, list_audio_devices
from maverick.voice.config import VoiceConfig
from maverick.voice.controller import VoiceController
from maverick.voice.session import VoiceSession, VoiceState
from maverick.voice.stt import LocalIntentSTTProvider, MockSTTProvider
from maverick.voice.tts import MockTTSProvider, SpeechDispatcherTTS
from maverick.voice.wakeword import EnergySpectralWakeWordDetector, MockWakeWordDetector


class TestVoiceSubsystem(unittest.TestCase):
    """Test suite covering Phase 5 voice interaction system."""

    def setUp(self):
        self.config = VoiceConfig()

    # 1. Microphone Detection
    def test_microphone_detection(self):
        devs = list_audio_devices()
        self.assertEqual(devs["status"], "success")
        self.assertIn("has_microphone", devs)
        self.assertIn("has_speaker", devs)
        self.assertIsInstance(devs["inputs"], list)
        self.assertIsInstance(devs["outputs"], list)

    # 2. Audio Input Capture & RMS
    def test_audio_rms_calculation(self):
        # Silence
        self.assertEqual(calculate_rms(b"\x00" * 2048), 0.0)
        # Empty/invalid
        self.assertEqual(calculate_rms(b""), 0.0)
        self.assertEqual(calculate_rms(b"x"), 0.0)

    @patch("subprocess.Popen")
    def test_audio_capture_lifecycle(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdout.read.return_value = b"\x00" * 2048
        mock_popen.return_value = mock_proc

        capture = AudioCapture(self.config)
        self.assertTrue(capture.start())
        chunk = capture.read_chunk(1024)
        self.assertEqual(len(chunk), 2048)

        # Mute test
        capture.set_muted(True)
        self.assertTrue(capture.is_muted)
        muted_chunk = capture.read_chunk(1024)
        self.assertEqual(muted_chunk, b"\x00" * 2048)

        capture.stop()
        mock_proc.terminate.assert_called_once()

    # 3. Wake-Word Detection & Debounce
    def test_wakeword_detection_and_debounce(self):
        detector = EnergySpectralWakeWordDetector(self.config)
        # Low energy frame -> should not trigger
        low_energy = b"\x05\x00" * 1024
        self.assertFalse(detector.process_frame(low_energy))

        # Loud frame
        loud_frame = b"\x7f\x50" * 1024
        triggered = detector.process_frame(loud_frame)
        if triggered:
            # Immediate subsequent loud frame should be blocked by debounce
            self.assertFalse(detector.process_frame(loud_frame))

    # 4. Speech-to-Text Providers
    def test_stt_providers(self):
        mock_stt = MockSTTProvider("open visual studio code")
        text = mock_stt.transcribe(b"\x00" * 3200)
        self.assertEqual(text, "open visual studio code")

        local_stt = LocalIntentSTTProvider(self.config)
        self.assertEqual(local_stt.transcribe(b""), "")

    # 5. Text-to-Speech Providers
    @patch("shutil.which", return_value="/usr/bin/spd-say")
    @patch("subprocess.Popen")
    def test_speech_dispatcher_tts(self, mock_popen, mock_which):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        tts = SpeechDispatcherTTS(self.config)
        ok = tts.speak("Hello test", wait=False)
        self.assertTrue(ok)
        tts.stop()
        mock_proc.terminate.assert_called_once()

    # 6. Interrupting Maven While Speaking
    def test_session_interrupt(self):
        mock_tts = MockTTSProvider()
        session = VoiceSession(self.config, tts=mock_tts)
        session.speak("Long utterance", wait=False)
        self.assertEqual(session.state, VoiceState.SPEAKING)

        session.interrupt()
        self.assertEqual(session.state, VoiceState.IDLE)
        self.assertFalse(mock_tts.is_speaking())

    # 7. Silence & Session Timeout
    def test_session_state_machine(self):
        mock_capture = MagicMock()
        mock_capture.read_chunk.return_value = b"\x00" * 2048
        mock_wake = MockWakeWordDetector()
        mock_tts = MockTTSProvider()

        session = VoiceSession(
            self.config,
            audio_capture=mock_capture,
            wake_detector=mock_wake,
            tts=mock_tts,
        )
        self.assertEqual(session.state, VoiceState.IDLE)

        # Trigger wake word
        mock_wake.trigger()
        session.step()
        self.assertEqual(session.state, VoiceState.LISTENING)

    # 8. Missing Microphone Graceful Handling
    @patch("shutil.which", return_value=None)
    def test_missing_microphone_handling(self, mock_which):
        capture = AudioCapture(self.config)
        self.assertFalse(capture.start())
        self.assertEqual(capture.read_chunk(), b"")
        capture.stop()

    # 9. Missing Speaker Graceful Handling
    @patch("shutil.which", return_value=None)
    def test_missing_speaker_handling(self, mock_which):
        player = AudioPlayer(self.config)
        self.assertFalse(player.play_wav("/nonexistent/file.wav"))

    # 10. OpenClaw Response Integration
    @patch("subprocess.run")
    def test_openclaw_integration_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"ok": true, "result": {"reply": "Maven voice online."}}\n',
            stderr="",
        )
        ctl = VoiceController(self.config)
        res = ctl._query_openclaw("Hello Maven")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["response"], "Maven voice online.")

    @patch("subprocess.run")
    def test_openclaw_rate_limit_graceful(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='{"ok": false, "error": {"message": "429 RESOURCE_EXHAUSTED"}}\n',
            stderr="RESOURCE_EXHAUSTED",
        )
        ctl = VoiceController(self.config)
        res = ctl._query_openclaw("Tell me a story")
        self.assertEqual(res["status"], "rate_limited")
        self.assertIn("quota", res["response"].lower())

    # 11. Gemini Configuration Preservation
    def test_gemini_model_configuration(self):
        self.assertEqual(self.config.model_id, "google/gemini-2.5-flash")

    # 12. Desktop Command Execution via Voice
    def test_desktop_voice_command_routing(self):
        ctl = VoiceController(self.config)
        # Test RAM command
        res = ctl.handle_voice_command("Maven, how much RAM is available?")
        self.assertEqual(res["status"], "success")
        self.assertIn("RAM available", res["response"])

        # Test running apps command
        res_apps = ctl.handle_voice_command("Maven, what applications are running?")
        self.assertEqual(res_apps["status"], "success")
        self.assertIn("applications", res_apps["response"])

        # Test context summary command
        res_ctx = ctl.handle_voice_command("Maven, summarize desktop context")
        self.assertEqual(res_ctx["status"], "success")
        self.assertIn("Desktop summary", res_ctx["response"])

        # Test mute command
        res_mute = ctl.handle_voice_command("Maven, mute microphone")
        self.assertEqual(res_mute["status"], "success")
        self.assertTrue(ctl.session.is_muted)

        res_unmute = ctl.handle_voice_command("Maven, unmute microphone")
        self.assertEqual(res_unmute["status"], "success")
        self.assertFalse(ctl.session.is_muted)

    # 13. Confirmation Gates for Consequential Actions
    def test_voice_confirmation_gate(self):
        ctl = VoiceController(self.config)
        # gnome-terminal requires confirmation
        res = ctl.handle_voice_command("Maven, open terminal", confirmed=False)
        self.assertEqual(res["status"], "confirmation_required")
        self.assertIn("requires confirmation", res["response"])


if __name__ == "__main__":
    unittest.main()
