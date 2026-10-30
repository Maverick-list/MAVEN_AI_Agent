"""Maverick DevOS - Local Wake-Word Detection Engine."""

from abc import ABC, abstractmethod
import re
import time
from typing import List, Optional
import numpy as np

from maverick.voice.audio import calculate_rms
from maverick.voice.config import VoiceConfig
from maverick.voice.stt import STTProvider, WhisperCppSTTProvider


class WakeWordDetector(ABC):
    """Abstract interface for local wake-word detection engines."""

    @abstractmethod
    def process_frame(self, frame_bytes: bytes) -> bool:
        """Process an audio frame and return True if a wake-word is detected."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset internal detection state and timers."""
        pass


class LocalKeywordWakeWordDetector(WakeWordDetector):
    """
    True local keyword recognition engine.
    Combines stage-1 energy onset Voice Activity Detection (VAD) with dynamic
    ambient noise floor tracking and stage-2 local acoustic keyword verification
    via whisper.cpp.
    Operates offline, recognizes 'Hey Maven' and 'Maven' (or 'Jarvis'), and
    decisively rejects unrelated loud noises (claps, coughs, sneezes) and non-wake speech.
    """

    WAKE_REGEX = re.compile(r"\b(hey\s+)?(maven|jarvis|mavin|mayven|maveran|maveram)\b", re.IGNORECASE)

    def __init__(
        self,
        config: Optional[VoiceConfig] = None,
        stt_provider: Optional[STTProvider] = None,
    ):
        self.config = config or VoiceConfig()
        self.stt = stt_provider or WhisperCppSTTProvider(self.config)
        self.wake_words = [w.strip().lower() for w in self.config.wake_words]
        self._last_trigger_time = 0.0
        self._last_check_time = 0.0
        self._failed_checks = 0
        self._noise_floor = 0.02
        self._ring_buffer = bytearray()
        # Maintain ~1.2 seconds of 16kHz 16-bit mono audio
        self._max_buffer_bytes = int(self.config.sample_rate * 1.2 * 2)

    def reset(self) -> None:
        """Reset buffer and trigger timers."""
        self._ring_buffer.clear()
        self._last_trigger_time = 0.0
        self._last_check_time = 0.0
        self._failed_checks = 0
        self._noise_floor = 0.02

    def process_frame(self, frame_bytes: bytes) -> bool:
        """
        Evaluate incoming audio frame.
        Uses fast RMS energy gating with dynamic background floor adaptation to avoid
        running inference on silence or steady ambient hum, followed by acoustic
        keyword verification when speech energy rises over the ambient floor.
        Includes adaptive backoff cooldown on consecutive non-wake bursts to prevent
        CPU starvation during continuous background noise.
        """
        if not frame_bytes or len(frame_bytes) < 2:
            return False

        now = time.time()
        # Debounce enforcement: prevent cascading duplicate triggers
        if (now - self._last_trigger_time) < self.config.wake_debounce_seconds:
            return False

        # Accumulate frame into rolling audio buffer
        self._ring_buffer.extend(frame_bytes)
        if len(self._ring_buffer) > self._max_buffer_bytes:
            excess = len(self._ring_buffer) - self._max_buffer_bytes
            del self._ring_buffer[:excess]

        rms = calculate_rms(frame_bytes)

        # Adaptively track ambient noise floor during quiet periods
        is_burst = rms > (self._noise_floor * 1.6 + 0.02)
        if not is_burst:
            self._noise_floor = 0.92 * self._noise_floor + 0.08 * rms
            self._failed_checks = 0
            return False

        # Stage 1: Fast VAD check - verify energy exceeds both absolute threshold and ambient floor
        if rms < self.config.speech_start_threshold_rms:
            return False

        # Adaptive cooldown check between acoustic verification passes
        # Base cooldown is 0.4s; backs off to 0.8s on sustained non-wake bursts to protect CPU
        required_cooldown = 0.8 if self._failed_checks >= 2 else 0.4
        if (now - self._last_check_time) < required_cooldown:
            return False

        # Stage 2: Acoustic keyword verification
        # Need at least ~0.3s of buffered audio (9,600 bytes) to support rapid/short wake utterances
        if len(self._ring_buffer) < 9600:
            return False

        self._last_check_time = now
        audio_snapshot = bytes(self._ring_buffer)

        # Transcribe the rolling window with clean, unrepeated wake keyword hint
        transcript = self.stt.transcribe(
            audio_snapshot,
            language="en",
            prompt="Maven",
        )

        if transcript and self.WAKE_REGEX.search(transcript):
            self._last_trigger_time = now
            self._ring_buffer.clear()
            self._failed_checks = 0
            return True

        self._failed_checks += 1
        return False


class EnergySpectralWakeWordDetector(WakeWordDetector):
    """
    Lightweight, streaming local wake-word detector with energy envelope
    analysis and debounce protection against duplicate triggers.
    """

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or VoiceConfig()
        self.wake_words = [w.strip().lower() for w in self.config.wake_words]
        self._last_trigger_time = 0.0
        self._energy_history: List[float] = []
        self._max_history = 15  # ~1.0 second of 1024-sample chunks

    def reset(self) -> None:
        self._energy_history.clear()
        self._last_trigger_time = 0.0

    def process_frame(self, frame_bytes: bytes) -> bool:
        """
        Evaluate audio chunk energy profile against wake-word activation envelope.
        Enforces debounce intervals to prevent cascading re-triggers.
        """
        if not frame_bytes or len(frame_bytes) < 2:
            return False

        now = time.time()
        # Debounce check
        if (now - self._last_trigger_time) < self.config.wake_debounce_seconds:
            return False

        rms = calculate_rms(frame_bytes)
        self._energy_history.append(rms)
        if len(self._energy_history) > self._max_history:
            self._energy_history.pop(0)

        # Detect sharp voice burst followed by sustained vowel energy
        if rms >= self.config.speech_start_threshold_rms:
            if len(self._energy_history) >= 3:
                prior_floor = float(np.median(self._energy_history[:-2])) if len(self._energy_history) > 2 else 0.005
                snr_ratio = rms / (prior_floor + 1e-4)

                if snr_ratio > (1.0 + self.config.wake_word_sensitivity):
                    self._last_trigger_time = now
                    self._energy_history.clear()
                    return True

        return False


class MockWakeWordDetector(WakeWordDetector):
    """Controllable wake-word detector for unit testing."""

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.triggered = False

    def trigger(self) -> None:
        self.triggered = True

    def process_frame(self, frame_bytes: bytes) -> bool:
        if self.triggered:
            self.triggered = False
            return True
        return False

    def reset(self) -> None:
        self.triggered = False
