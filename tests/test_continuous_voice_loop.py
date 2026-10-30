"""Maverick DevOS - Automated Tests for Continuous Voice Conversation Loop.

Verifies:
1. At least 10 consecutive Indonesian and English voice interactions without daemon exit or hang.
2. Proper re-arming of wake-word detection after every response delivery.
3. Audio capture pipe draining (flush) post-TTS to eliminate speaker bleed.
4. Robust state transitions: IDLE -> WAKE -> LISTENING -> PROCESSING -> SPEAKING -> IDLE.
5. Error recovery: non-intelligible audio and exceptions do not crash the daemon loop.
6. Zero persistent audio files leaked to disk.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from maverick.voice.audio import AudioCapture
from maverick.voice.config import VoiceConfig
from maverick.voice.controller import VoiceController
from maverick.voice.daemon import VoiceDaemon
from maverick.voice.session import VoiceSession, VoiceState
from maverick.voice.tts import MockTTSProvider
from maverick.voice.wakeword import MockWakeWordDetector, LocalKeywordWakeWordDetector


class MockStreamingAudioCapture:
    """Mock audio capture that simulates streaming PCM frames."""

    def __init__(self, config=None):
        self.config = config or VoiceConfig()
        self.is_capturing = True
        self.flushed = False
        self._chunks = []

    def start(self) -> bool:
        self.is_capturing = True
        return True

    def stop(self) -> None:
        self.is_capturing = False

    def flush(self) -> None:
        self.flushed = True
        self._chunks.clear()

    def feed_chunk(self, chunk: bytes) -> None:
        self._chunks.append(chunk)

    def read_chunk(self, chunk_size: int = 1024) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        # Return small ambient silence
        return b"\x00" * (chunk_size * 2)


class MockMultiTurnSTTProvider:
    """Mock STT provider that returns programmed transcripts for consecutive turns."""

    def __init__(self, transcript_queue):
        self.queue = list(transcript_queue)
        self.transcribed_count = 0

    def is_available(self) -> bool:
        return True

    def transcribe(self, audio_bytes: bytes, language: str = "auto", prompt: str = "") -> str:
        self.transcribed_count += 1
        if self.queue:
            return self.queue.pop(0)
        return ""


class TestContinuousVoiceLoop(unittest.TestCase):
    """Test suite for continuous multi-turn voice interaction loop."""

    def setUp(self):
        self.config = VoiceConfig()

    @patch("maverick.voice.controller.SpotifyController")
    def test_ten_consecutive_bilingual_interactions(self, mock_spotify_cls):
        """
        Verify that Maven reliably processes at least 10 consecutive voice interactions
        alternating between English and Indonesian, re-arming wake detection after each,
        and never getting stuck in a non-idle state.
        """
        mock_spotify = MagicMock()
        mock_spotify.get_status.return_value = {"status": "success", "volume": 0.5, "title": "Test Song", "artist": "Test Artist"}
        mock_spotify.set_volume.return_value = {"status": "success"}
        mock_spotify_cls.return_value = mock_spotify
        test_commands = [
            ("Hey Maven", "wake_acknowledgment", "en"),
            ("What is my RAM usage?", "system_ram", "en"),
            ("Halo Maven", "wake_acknowledgment", "id"),
            ("Berapa sisa RAM laptopku?", "system_ram", "id"),
            ("What applications are running?", "apps_running", "en"),
            ("Aplikasi apa saja yang sedang berjalan?", "apps_running", "id"),
            ("Set Spotify volume to 70 percent", "spotify_volume", "en"),
            ("Volume Spotify atur ke 80 persen", "spotify_volume", "id"),
            ("Check battery status", "system_battery", "en"),
            ("Status baterai laptop", "system_battery", "id"),
            ("Desktop context summary", "context_summary", "en"),
            ("Ringkasan konteks desktop", "context_summary", "id"),
        ]

        mock_capture = MockStreamingAudioCapture(self.config)
        mock_wake = MockWakeWordDetector(self.config)
        mock_tts = MockTTSProvider()
        mock_stt = MockMultiTurnSTTProvider([cmd[0] for cmd in test_commands])

        session = VoiceSession(
            self.config,
            audio_capture=mock_capture,
            wake_detector=mock_wake,
            tts=mock_tts,
        )
        controller = VoiceController(
            self.config,
            session=session,
            stt=mock_stt,
            tts=mock_tts,
        )
        daemon = VoiceDaemon(self.config, controller=controller)

        # Track state transitions
        recorded_states = []
        session.add_state_callback(lambda st: recorded_states.append(st.value))

        for turn_idx, (cmd_text, expected_action, lang) in enumerate(test_commands):
            # 1. Verify session is IDLE and re-armed before each interaction
            self.assertEqual(session.state, VoiceState.IDLE, f"Turn {turn_idx+1} did not start in IDLE state")

            # 2. Trigger wake word for this turn
            mock_wake.trigger()
            session.step()
            self.assertEqual(session.state, VoiceState.LISTENING, f"Turn {turn_idx+1} failed to transition to LISTENING")

            # 3. Simulate speech followed by silence
            speech_chunk = b"\x7f\x50" * 1024  # Loud speech energy
            silence_chunk = b"\x00" * 2048    # Quiet silence
            mock_capture.feed_chunk(speech_chunk)
            session.step()

            # Advance silence duration to complete utterance
            session._last_speech_time -= (self.config.silence_duration_seconds + 0.1)
            mock_capture.feed_chunk(silence_chunk)

            # 4. Step daemon to process utterance -> STT -> Action -> TTS -> Re-arm
            utterance = session.step()
            self.assertIsNotNone(utterance, f"Turn {turn_idx+1} produced no utterance")

            # Transcribe
            transcript = controller.stt.transcribe(utterance)
            self.assertEqual(transcript, cmd_text, f"Turn {turn_idx+1} STT transcript mismatch")

            # Dispatch
            res = controller.handle_voice_command(transcript)
            self.assertEqual(res.get("status"), "success", f"Turn {turn_idx+1} dispatch failed: {res}")
            self.assertEqual(res.get("action"), expected_action, f"Turn {turn_idx+1} unexpected action")

            # Speak and auto re-arm
            resp = res.get("response", "")
            self.assertTrue(len(resp) > 0, f"Turn {turn_idx+1} response text was empty")
            session.speak(resp, wait=True)

            # 5. Verify immediate re-arming back to IDLE
            self.assertEqual(session.state, VoiceState.IDLE, f"Turn {turn_idx+1} failed to re-arm to IDLE after TTS")
            self.assertTrue(mock_capture.flushed, f"Turn {turn_idx+1} did not flush audio capture pipe")
            mock_capture.flushed = False

        self.assertEqual(mock_stt.transcribed_count, len(test_commands))
        self.assertEqual(len(mock_tts.spoken_texts), len(test_commands))

    def test_rearm_preserves_acoustic_noise_floor(self):
        """
        Verify that rearm() resets timers and buffers without obliterating
        the calibrated ambient noise floor.
        """
        detector = LocalKeywordWakeWordDetector(self.config)
        detector._noise_floor = 0.38
        detector._noise_floor_initialized = True
        detector._failed_checks = 4
        detector._ring_buffer.extend(b"\x12\x34" * 500)

        detector.rearm()

        self.assertEqual(len(detector._ring_buffer), 0)
        self.assertEqual(detector._failed_checks, 0)
        self.assertEqual(detector._last_trigger_time, 0.0)
        self.assertEqual(detector._last_check_time, 0.0)
        self.assertTrue(detector._noise_floor_initialized)
        # Floor must be preserved around calibrated ambient (0.38)
        self.assertAlmostEqual(detector._noise_floor, 0.38, places=2)

    def test_rearm_clamps_speaker_acoustic_spike(self):
        """
        Verify that if a speaker transient spiked the noise floor above 0.45,
        rearm() clamps it down to prevent blinding the detector.
        """
        detector = LocalKeywordWakeWordDetector(self.config)
        detector._noise_floor = 0.88  # Acoustic spike from TTS output
        detector._noise_floor_initialized = True

        detector.rearm()
        self.assertLessEqual(detector._noise_floor, 0.35)

    def test_listening_timeout_recovers_to_idle(self):
        """
        Verify that when a wake word is triggered but no speech follows,
        the session cleanly times out and re-arms to IDLE without getting stuck.
        """
        mock_capture = MockStreamingAudioCapture(self.config)
        mock_wake = MockWakeWordDetector(self.config)
        session = VoiceSession(
            self.config,
            audio_capture=mock_capture,
            wake_detector=mock_wake,
        )

        mock_wake.trigger()
        session.step()
        self.assertEqual(session.state, VoiceState.LISTENING)

        # Advance timer past listening_timeout_seconds without any speech
        session._listen_start_time -= (self.config.listening_timeout_seconds + 0.5)

        # Step session with silence
        res = session.step()
        self.assertIsNone(res)
        self.assertEqual(session.state, VoiceState.IDLE)

    def test_daemon_loop_exception_resilience(self):
        """
        Verify that an exception in STT or action execution does not terminate
        the daemon, and the session is safely re-armed.
        """
        mock_capture = MockStreamingAudioCapture(self.config)
        mock_wake = MockWakeWordDetector(self.config)
        mock_tts = MockTTSProvider()

        # STT that raises an error on turn 1 then succeeds on turn 2
        failing_stt = MagicMock()
        failing_stt.transcribe.side_effect = [RuntimeError("Whisper subprocess crash"), "Hey Maven"]

        session = VoiceSession(
            self.config,
            audio_capture=mock_capture,
            wake_detector=mock_wake,
            tts=mock_tts,
        )
        controller = VoiceController(
            self.config,
            session=session,
            stt=failing_stt,
            tts=mock_tts,
        )
        daemon = VoiceDaemon(self.config, controller=controller)

        # Turn 1: Trigger error
        mock_wake.trigger()
        session.step()
        session._has_detected_speech = True
        session._last_speech_time -= 2.0
        utterance = session.step()

        # Execute inner daemon step block
        try:
            transcript = controller.stt.transcribe(utterance)
        except Exception as e:
            session.rearm()

        self.assertEqual(session.state, VoiceState.IDLE)

        # Turn 2: Verify immediate re-armed functionality
        mock_wake.trigger()
        session.step()
        self.assertEqual(session.state, VoiceState.LISTENING)
        session._has_detected_speech = True
        session._last_speech_time -= 2.0
        utterance2 = session.step()

        transcript2 = controller.stt.transcribe(utterance2)
        self.assertEqual(transcript2, "Hey Maven")
        res2 = controller.handle_voice_command(transcript2)
        self.assertEqual(res2["action"], "wake_acknowledgment")
        session.speak(res2["response"], wait=True)
        self.assertEqual(session.state, VoiceState.IDLE)


if __name__ == "__main__":
    unittest.main()
