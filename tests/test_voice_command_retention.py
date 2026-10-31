"""
Tests for Voice Barge-In, Speech Audio Retention, and Interrupted Command Dispatch.
Validates that speech during TTS stops playback promptly, preserves the user's spoken audio,
and cleanly delivers the utterance to Speech-to-Text and Intent routing.
"""

import time
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from maverick.voice.config import VoiceConfig
from maverick.voice.session import VoiceSession, VoiceState


class TestVoiceCommandRetention(unittest.TestCase):
    def setUp(self):
        self.config = VoiceConfig()
        self.session = VoiceSession(self.config)
        self.session.tts = MagicMock()
        self.session.audio = MagicMock()

    def _make_audio_chunk(self, rms_target: float, length: int = 1024) -> bytes:
        """Synthesize PCM audio chunk with calibrated RMS."""
        samples = np.random.normal(0, rms_target, length).astype(np.float32)
        samples = np.clip(samples, -1.0, 1.0)
        pcm16 = (samples * 32767).astype(np.int16)
        return pcm16.tobytes()

    def test_barge_in_stops_tts_and_preserves_audio_buffer(self):
        """
        Verify that speech during TTS:
        1. Immediately halts TTS (tts.stop()).
        2. Transitions from SPEAKING -> INTERRUPTED -> LISTENING (not IDLE!).
        3. Preserves the triggering speech audio chunk in _audio_buffer.
        """
        self.session.tts.is_speaking.return_value = True
        speech_burst = self._make_audio_chunk(rms_target=0.35)
        self.session.audio.read_chunk.return_value = speech_burst

        # Execute step during playback with user voice burst
        res = self.session.step()
        self.assertIsNone(res)

        # TTS must have been stopped
        self.assertTrue(self.session.tts.stop.called)

        # Session must be in LISTENING state (NOT IDLE!)
        self.assertEqual(self.session.state, VoiceState.LISTENING)
        self.assertEqual(self.session.last_trigger_source, "barge_in")

        # The initial speech chunk must be preserved in the audio buffer!
        self.assertGreater(len(self.session._audio_buffer), 0)
        self.assertTrue(self.session._has_detected_speech)

    def test_silence_during_tts_does_not_interrupt(self):
        """Verify ambient silence during TTS does not interrupt playback."""
        self.session.tts.is_speaking.return_value = True
        silence_chunk = self._make_audio_chunk(rms_target=0.01)
        self.session.audio.read_chunk.return_value = silence_chunk

        res = self.session.step()
        self.assertIsNone(res)
        self.assertFalse(self.session.tts.stop.called)
        self.assertEqual(self.session.state, VoiceState.SPEAKING)

    def test_background_noise_below_threshold_does_not_interrupt(self):
        """Verify normal room noise (HVAC/fans, RMS ~0.04) does not trigger false interruption."""
        self.session.tts.is_speaking.return_value = True
        noise_chunk = self._make_audio_chunk(rms_target=0.04)
        self.session.audio.read_chunk.return_value = noise_chunk

        res = self.session.step()
        self.assertIsNone(res)
        self.assertFalse(self.session.tts.stop.called)
        self.assertEqual(self.session.state, VoiceState.SPEAKING)

    def test_full_barge_in_command_retention_and_utterance_delivery(self):
        """
        Simulate full conversational interruption lifecycle:
        1. Assistant speaks.
        2. User interrupts: 'Stop and check battery'.
        3. Session transitions to LISTENING and buffers audio.
        4. User stops speaking -> trailing silence detected.
        5. Session produces full utterance bytes with trigger='silence_detected'.
        """
        self.session.tts.is_speaking.return_value = True
        onset_chunk = self._make_audio_chunk(rms_target=0.30)
        self.session.audio.read_chunk.return_value = onset_chunk

        # Turn 1: Onset causes barge-in
        self.session.step()
        self.assertEqual(self.session.state, VoiceState.LISTENING)

        # TTS has now halted
        self.session.tts.is_speaking.return_value = False

        # Turn 2: User continues speaking
        speech_chunk2 = self._make_audio_chunk(rms_target=0.25)
        self.session.audio.read_chunk.return_value = speech_chunk2
        self.session.step()
        self.assertEqual(self.session.state, VoiceState.LISTENING)

        # Turn 3: User finishes speaking; trailing silence follows
        silence_chunk = self._make_audio_chunk(rms_target=0.005)
        self.session.audio.read_chunk.return_value = silence_chunk

        # Simulate trailing silence duration exceeding silence_duration_seconds
        self.session._last_speech_time = time.time() - (self.config.silence_duration_seconds + 0.1)

        utterance = self.session.step()

        # Utterance must be returned ready for STT!
        self.assertIsNotNone(utterance)
        self.assertIsInstance(utterance, bytes)
        self.assertGreater(len(utterance), len(onset_chunk))
        self.assertEqual(self.session.state, VoiceState.PROCESSING)

    def test_repeated_interruptions(self):
        """Verify session handles multiple successive interruptions without state corruption."""
        for i in range(3):
            self.session.tts.is_speaking.return_value = True
            burst = self._make_audio_chunk(rms_target=0.32)
            self.session.audio.read_chunk.return_value = burst

            self.session.step()
            self.assertEqual(self.session.state, VoiceState.LISTENING)

            # Re-arm back to speaking for next test iteration
            self.session.rearm()
            self.assertEqual(self.session.state, VoiceState.IDLE)


if __name__ == "__main__":
    unittest.main()

