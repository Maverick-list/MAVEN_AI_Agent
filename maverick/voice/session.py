"""Maverick DevOS - Voice Interaction Session & Finite State Machine."""

from enum import Enum
import threading
import time
from typing import Callable, List, Optional

from maverick.voice.audio import AudioCapture, calculate_rms
from maverick.voice.config import VoiceConfig
from maverick.voice.tts import TTSProvider, SpeechDispatcherTTS
from maverick.voice.wakeword import WakeWordDetector, EnergySpectralWakeWordDetector


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
    ):
        self.config = config or VoiceConfig()
        self.audio = audio_capture or AudioCapture(self.config)
        self.wake_detector = wake_detector or EnergySpectralWakeWordDetector(self.config)
        self.tts = tts or SpeechDispatcherTTS(self.config)

        self._state = VoiceState.IDLE
        self._muted = self.config.muted
        self._is_running = False
        self._state_callbacks: List[Callable[[VoiceState], None]] = []
        self._lock = threading.Lock()

        # Recorded utterance buffer
        self._audio_buffer: bytearray = bytearray()
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
            self._state = new_state

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
        self.tts.stop()
        self._transition_to(VoiceState.INTERRUPTED)
        time.sleep(0.05)
        self._transition_to(VoiceState.IDLE)

    def trigger_wake_word(self) -> None:
        """Programmatically trigger wake-word state (e.g. from UI keypress)."""
        if self._state in (VoiceState.IDLE, VoiceState.ERROR):
            self._transition_to(VoiceState.WAKE_WORD_DETECTED)
            self._start_listening()

    def _start_listening(self) -> None:
        """Enter listening state and begin buffering user speech."""
        self._audio_buffer.clear()
        self._listen_start_time = time.time()
        self._last_speech_time = time.time()
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
            self._transition_to(VoiceState.IDLE)

        # 1. State: IDLE - Monitor for wake word
        if self._state == VoiceState.IDLE:
            chunk = self.audio.read_chunk()
            if not chunk:
                return None

            if self.wake_detector.process_frame(chunk):
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

            if rms >= self.config.silence_threshold_rms:
                self._last_speech_time = now

            # Check silence duration
            silence_elapsed = now - self._last_speech_time
            total_elapsed = now - self._listen_start_time

            # Enforce maximum recording boundary (no infinite recording)
            if total_elapsed >= self.config.max_recording_seconds:
                self._transition_to(VoiceState.PROCESSING)
                utterance = bytes(self._audio_buffer)
                self._audio_buffer.clear()
                return utterance

            # Utterance complete when silence threshold met after at least 0.5s recording
            if total_elapsed > 0.5 and silence_elapsed >= self.config.silence_duration_seconds:
                self._transition_to(VoiceState.PROCESSING)
                utterance = bytes(self._audio_buffer)
                self._audio_buffer.clear()
                return utterance

            # Timeout with no speech detected at all
            if total_elapsed >= self.config.listening_timeout_seconds and len(self._audio_buffer) < 4000:
                self._transition_to(VoiceState.IDLE)
                self._audio_buffer.clear()
                return None

            return None

        return None

    def speak(self, text: str, wait: bool = True) -> bool:
        """Speak response text through TTS with feedback protection."""
        self._transition_to(VoiceState.SPEAKING)
        success = self.tts.speak(text, wait=wait)
        if wait:
            self._transition_to(VoiceState.IDLE)
        return success

    def reset(self) -> None:
        """Reset session to clean idle state."""
        self.tts.stop()
        self._audio_buffer.clear()
        self.wake_detector.reset()
        self._transition_to(VoiceState.IDLE)
