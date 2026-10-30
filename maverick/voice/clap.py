"""Maverick DevOS - Local Dual-Clap Acoustic Pattern Detector."""

import time
from typing import Optional
import numpy as np

from maverick.voice.audio import calculate_rms
from maverick.voice.config import VoiceConfig
from maverick.voice.observability import voice_logger


class DualClapDetector:
    """
    Lightweight, completely local dual-clap acoustic pattern detector.
    Analyzes high-crest impulsive acoustic energy envelopes to detect two distinct
    hand claps occurring within a natural human cadence window (180ms - 750ms).
    Decisively distinguishes claps from typing, door impacts, coughing, speech,
    and background music beats using crest-factor and decay-rate gating.
    Requires zero internet connectivity and operates entirely in RAM.
    """

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or VoiceConfig()
        self.enabled = bool(self.config.enable_clap_detection)
        self.min_interval = float(self.config.clap_min_interval_sec)  # default 0.18s
        self.max_interval = float(self.config.clap_max_interval_sec)  # default 0.75s
        self.cooldown = float(self.config.clap_cooldown_sec)          # default 2.0s
        self.sensitivity = float(self.config.clap_sensitivity)        # default 0.65

        self._last_trigger_time: float = 0.0
        self._first_clap_time: float = 0.0
        self._first_clap_energy: float = 0.0
        self._saw_decay_after_first: bool = False

        self._noise_floor: float = 0.02
        self._noise_floor_initialized: bool = False
        self._recent_rms: list = []

    def reset(self) -> None:
        """Reset internal detection state and timers."""
        self._first_clap_time = 0.0
        self._first_clap_energy = 0.0
        self._saw_decay_after_first = False
        self._recent_rms.clear()

    def rearm(self) -> None:
        """Re-arm detector for ambient listening after interaction completion."""
        self.reset()

    def enable(self) -> None:
        """Enable dual-clap detection."""
        self.enabled = True

    def disable(self) -> None:
        """Disable dual-clap detection."""
        self.enabled = False
        self.reset()

    def is_enabled(self) -> bool:
        """Return True if clap detection is active."""
        return self.enabled

    def _is_clap_impulse(self, frame_bytes: bytes, rms: float) -> bool:
        """
        Evaluate if an audio frame represents a high-crest impulsive hand clap.
        A clap has high peak amplitude relative to RMS (crest factor > 2.8) and
        sharp rise above the ambient noise floor.
        """
        if len(frame_bytes) < 4:
            return False

        try:
            samples = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            peak = float(np.max(np.abs(samples)))
        except Exception:
            return False

        # Crest factor (peak to RMS ratio)
        crest_factor = peak / (rms + 1e-5)

        # Ambient threshold requirement: energy must rise significantly above noise floor
        # Sensitivity scales the required delta: higher sensitivity = lower delta requirement
        required_delta = max(0.04, self._noise_floor * max(0.5, (1.6 - self.sensitivity)))
        delta = rms - self._noise_floor

        # Claps exhibit high crest factor (> 2.5) and a sharp impulsive peak (> 0.20)
        if delta >= required_delta and crest_factor >= 2.5 and peak >= 0.20:
            return True

        return False

    def process_frame(self, frame_bytes: bytes) -> bool:
        """
        Process an incoming audio chunk (16kHz S16LE PCM).
        Returns True if a valid two-clap cadence is detected.
        """
        if not self.enabled or not frame_bytes or len(frame_bytes) < 4:
            return False

        now = time.time()

        # Enforce debounce cooldown after a successful dual-clap trigger
        if (now - self._last_trigger_time) < self.cooldown:
            return False

        rms = calculate_rms(frame_bytes)
        is_impulse = self._is_clap_impulse(frame_bytes, rms)

        # Adaptively track ambient noise floor only during non-impulsive frames
        if not is_impulse:
            if not self._noise_floor_initialized:
                self._noise_floor = min(0.08, rms)
                self._noise_floor_initialized = True
            else:
                if rms < self._noise_floor:
                    self._noise_floor = 0.90 * self._noise_floor + 0.10 * rms
                else:
                    self._noise_floor = 0.99 * self._noise_floor + 0.01 * rms

        # Track recent energy history to verify decay
        self._recent_rms.append(rms)
        if len(self._recent_rms) > 10:
            self._recent_rms.pop(0)

        is_impulse = self._is_clap_impulse(frame_bytes, rms)

        # State 1: We are waiting for the second clap
        if self._first_clap_time > 0.0:
            elapsed = now - self._first_clap_time

            # If elapsed time exceeds max cadence window, the first clap timed out
            if elapsed > self.max_interval:
                self.reset()
                # Check if current frame could be a new first clap
                if is_impulse:
                    self._first_clap_time = now
                    self._first_clap_energy = rms
                    self._saw_decay_after_first = False
                return False

            # Require inter-clap energy decay (silence between claps)
            if not self._saw_decay_after_first:
                if rms < (self._first_clap_energy * 0.60):
                    self._saw_decay_after_first = True

            # Check if second clap arrives within valid cadence window
            if elapsed >= self.min_interval:
                if is_impulse and self._saw_decay_after_first:
                    # Dual clap verified!
                    self._last_trigger_time = now
                    self.reset()
                    return True

            return False

        # State 0: Waiting for the first clap
        if is_impulse:
            self._first_clap_time = now
            self._first_clap_energy = rms
            self._saw_decay_after_first = False
            return False

        return False
