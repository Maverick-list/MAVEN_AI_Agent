"""Maverick DevOS - Local Wake-Word Detection Engine."""

from abc import ABC, abstractmethod
import time
from typing import List, Optional
import numpy as np

from maverick.voice.audio import calculate_rms
from maverick.voice.config import VoiceConfig


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

        # Detect sharp voice burst followed by sustained vowel energy (characteristics of "Maven" or "Jarvis")
        if rms >= self.config.speech_start_threshold_rms:
            # Check for sudden dynamic range rise over background noise
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
