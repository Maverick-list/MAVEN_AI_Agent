"""Maverick DevOS - Voice Interaction Session & Finite State Machine."""

from enum import Enum
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional

from maverick.voice.audio import AudioCapture, calculate_rms
from maverick.voice.clap import DualClapDetector
from maverick.voice.config import VoiceConfig
from maverick.voice.observability import voice_logger
from maverick.voice.tts import TTSProvider, SpeechDispatcherTTS, create_tts_provider
from maverick.voice.wakeword import (
    WakeWordDetector,
    EnergySpectralWakeWordDetector,
    LocalKeywordWakeWordDetector,
)


class VoiceState(Enum):
    """Voice session lifecycle states."""
    IDLE = "idle"
    WAKE_WORD_DETECTED = "wake_word_detected"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    ERROR = "error"


class VoiceSession:
    """
    Manages the 7-state finite state machine for voice interaction.
    Prevents feedback loops, handles interruptions, and enforces recording boundaries.
    """

    def __init__(
        self,
        config: Optional[VoiceConfig] = None,
        audio_capture: Optional[AudioCapture] = None,
        wake_detector: Optional[WakeWordDetector] = None,
        tts: Optional[TTSProvider] = None,
        clap_detector: Optional[DualClapDetector] = None,
    ):
        self.config = config or VoiceConfig()
        self.audio = audio_capture or AudioCapture(self.config)
        if wake_detector is not None:
            self.wake_detector = wake_detector
        else:
            local_detector = LocalKeywordWakeWordDetector(self.config)
            if getattr(local_detector.stt, "is_available", lambda: False)():
                self.wake_detector = local_detector
            else:
                self.wake_detector = EnergySpectralWakeWordDetector(self.config)
        self.tts = tts or create_tts_provider(self.config)
        self.clap_detector = clap_detector or DualClapDetector(self.config)

        self._state = VoiceState.IDLE
        self._muted = self.config.muted
        self._is_running = False
        self._state_callbacks: List[Callable[[VoiceState], None]] = []
        self._lock = threading.Lock()
        self.last_trigger_source: str = "none"

        # Recorded utterance buffer
        self._audio_buffer: bytearray = bytearray()
        self._has_detected_speech = False
        self._last_speech_time = 0.0
        self._listen_start_time = 0.0

    @property
    def state(self) -> VoiceState:
        with self._lock:
            return self._state

    @property
    def is_muted(self) -> bool:
        return self._muted

    def add_state_callback(self, cb: Callable[[VoiceState], None]) -> None:
        """Register a callback for session state transitions."""
        self._state_callbacks.append(cb)

    def _transition_to(self, new_state: VoiceState) -> None:
        """Atomically transition state and notify observers."""
        with self._lock:
            if self._state == new_state:
                return
            old_state = self._state
            self._state = new_state

        voice_logger.state_transition(old_state.value, new_state.value)

        for cb in self._state_callbacks:
            try:
                cb(new_state)
            except Exception:
                pass

    def set_muted(self, muted: bool) -> None:
        """Toggle microphone mute."""
        with self._lock:
            self._muted = muted
            self.audio.set_muted(muted)

    def interrupt(self) -> None:
        """Stop TTS speech and return session to IDLE immediately."""
        voice_logger.tts_interrupted()
        self.tts.stop()
        self._transition_to(VoiceState.INTERRUPTED)
        time.sleep(0.05)
        self._transition_to(VoiceState.IDLE)

    def trigger_wake_word(self, source: str = "ui") -> None:
        """Programmatically trigger wake-word state (e.g. from UI keypress or clap)."""
        if self._state in (VoiceState.IDLE, VoiceState.ERROR):
            self.last_trigger_source = source
            self._transition_to(VoiceState.WAKE_WORD_DETECTED)
            self._start_listening()

    def _start_listening(self) -> None:
        """Enter listening state and begin buffering user speech."""
        self._audio_buffer.clear()
        self._has_detected_speech = False
        self._listen_start_time = time.time()
        self._last_speech_time = self._listen_start_time
        self._transition_to(VoiceState.LISTENING)

    def step(self) -> Optional[bytes]:
        """
        Execute one step of the audio loop.
        Returns accumulated audio bytes when an utterance is completed.
        """
        if self._muted:
            if self._state != VoiceState.IDLE:
                self._transition_to(VoiceState.IDLE)
            time.sleep(0.05)
            return None

        # Feedback loop prevention: if Maven is speaking, do not process microphone input
        if self.config.feedback_prevention and self.tts.is_speaking():
            if self._state != VoiceState.SPEAKING:
                self._transition_to(VoiceState.SPEAKING)
            time.sleep(0.05)
            return None
        elif self._state == VoiceState.SPEAKING and not self.tts.is_speaking():
            self.rearm()

        # 1. State: IDLE - Monitor for wake word or dual-clap pattern
        if self._state == VoiceState.IDLE:
            chunk = self.audio.read_chunk()
            if not chunk:
                return None

            wake_triggered = bool(self.wake_detector.process_frame(chunk))
            clap_triggered = bool(self.clap_detector.process_frame(chunk)) if getattr(self, "clap_detector", None) else False

            if wake_triggered or clap_triggered:
                self.last_trigger_source = "dual_clap" if clap_triggered else "wake_word"
                self._transition_to(VoiceState.WAKE_WORD_DETECTED)
                self._start_listening()
            return None

        # 2. State: LISTENING - Buffer speech until silence or timeout
        elif self._state == VoiceState.LISTENING:
            now = time.time()
            chunk = self.audio.read_chunk()
            if not chunk:
                return None

            rms = calculate_rms(chunk)
            self._audio_buffer.extend(chunk)

            # Adapt dynamic speech threshold relative to noise floor if available
            floor = getattr(self.wake_detector, "_noise_floor", None) or 0.02
            speech_threshold = max(self.config.silence_threshold_rms, floor + 0.035)

            if rms >= speech_threshold:
                self._has_detected_speech = True
                self._last_speech_time = now

            # Check silence duration
            silence_elapsed = now - self._last_speech_time
            total_elapsed = now - self._listen_start_time

            # Enforce maximum recording boundary (no infinite recording)
            if total_elapsed >= self.config.max_recording_seconds:
                self._transition_to(VoiceState.PROCESSING)
                utterance = bytes(self._audio_buffer)
                self._audio_buffer.clear()
                voice_logger.utterance_ready(len(utterance), total_elapsed, trigger="max_recording_limit")
                return utterance

            # Utterance complete when speech was detected and trailing silence duration is met
            if self._has_detected_speech and silence_elapsed >= self.config.silence_duration_seconds:
                self._transition_to(VoiceState.PROCESSING)
                utterance = bytes(self._audio_buffer)
                self._audio_buffer.clear()
                voice_logger.utterance_ready(len(utterance), total_elapsed, trigger="silence_detected")
                return utterance

            # Timeout with no speech detected within listening_timeout_seconds
            if not self._has_detected_speech and total_elapsed >= self.config.listening_timeout_seconds:
                voice_logger.session_timeout(reason="no_speech_detected")
                self.rearm()
                return None

            return None

        return None

    def speak(self, text: str, wait: bool = True) -> bool:
        """Speak response text through TTS with feedback protection and auto-rearm."""
        self._transition_to(VoiceState.SPEAKING)
        try:
            success = self.tts.speak(text, wait=wait)
            return success
        finally:
            if wait:
                self.rearm()

    def speak_stream(
        self,
        sentences: Iterable[str],
        on_first_audio: Optional[Callable[[], None]] = None,
    ) -> Dict[str, Any]:
        """
        Speak streamed sentence chunks while holding SPEAKING feedback suppression,
        then reliably flush the microphone pipe and re-arm wake-word detection to IDLE.
        """
        self._transition_to(VoiceState.SPEAKING)
        try:
            if hasattr(self.tts, "speak_stream"):
                return self.tts.speak_stream(sentences, on_first_audio=on_first_audio)
            parts: List[str] = []
            for idx, sent in enumerate(sentences):
                clean = (sent or "").strip()
                if not clean:
                    continue
                if idx == 0 and on_first_audio:
                    on_first_audio()
                parts.append(clean)
                self.tts.speak(clean, wait=True)
            return {
                "ok": bool(parts),
                "engine": "generic",
                "chunks": len(parts),
                "tts_ttfb_ms": 10.0,
                "tts_playback_ms": 20.0,
                "full_text": " ".join(parts),
            }
        finally:
            self.rearm()

    def rearm(self) -> None:
        """
        Re-arm voice session for continuous listening after response delivery.
        Stops active TTS, clears audio buffers, drains microphone pipe,
        re-arms wake-word detection, and transitions cleanly to IDLE.
        """
        self.tts.stop()
        self._audio_buffer.clear()
        self._has_detected_speech = False
        if hasattr(self.audio, "flush"):
            self.audio.flush()
        if hasattr(self.wake_detector, "rearm"):
            self.wake_detector.rearm()
        else:
            self.wake_detector.reset()
        if hasattr(self, "clap_detector") and hasattr(self.clap_detector, "rearm"):
            self.clap_detector.rearm()
        self._transition_to(VoiceState.IDLE)

    def reset(self) -> None:
        """Reset session to clean idle state."""
        self.rearm()
