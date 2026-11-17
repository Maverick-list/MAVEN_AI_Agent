"""Maverick DevOS - Local Dual-Clap Acoustic Pattern Detector."""

import time
from typing import Optional
import numpy as np

from maverick.voice.audio import calculate_rms
from maverick.voice.config import VoiceConfig
from maverick.voice.observability import voice_logger


class ClapResult:
    """Acoustic clap event types."""
    NONE = "none"
    SINGLE = "single"
    DUAL = "dual"


class DualClapDetector:
    """
    Lightweight, completely local dual-clap and single-clap acoustic pattern detector.
    Analyzes high-crest impulsive acoustic energy envelopes to detect:
    1. Dual-clap: two distinct hand claps occurring within natural cadence (180ms - 750ms).
       Action: open GUI window and start listening.
    2. Single-clap: exactly one hand clap followed by decay and timeout (> 750ms).
       Action: close GUI window and return to IDLE.
    Decisively distinguishes genuine hand claps from typing, door impacts, table knocks,
    coughing, speech, and background noise using FFT spectral ratio and crest factor.
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
        """Enable clap detection."""
        self.enabled = True

    def disable(self) -> None:
        """Disable clap detection."""
        self.enabled = False
        self.reset()

    def is_enabled(self) -> bool:
        """Return True if clap detection is active."""
        return self.enabled

    def _is_clap_impulse(self, frame_bytes: bytes, rms: float) -> bool:
        """
        Evaluate if an audio frame represents a genuine acoustic hand clap.
        Strictly discriminates hand claps from table knocks, bumps, and speech:
        1. Crest factor: sharp transient peak relative to RMS (crest >= 2.8).
        2. Absolute peak threshold: must be loud enough (peak >= 0.20).
        3. Spectral acoustic signature: hand claps possess dominant acoustic energy
           in the high snap frequencies (1200 Hz - 5500 Hz), whereas table knocks,
           desk taps, and thuds have almost all energy concentrated below 900 Hz.
        """
        if len(frame_bytes) < 32:
            return False

        try:
            samples = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            peak = float(np.max(np.abs(samples)))
        except Exception:
            return False

        # Crest factor (peak to RMS ratio)
        crest_factor = peak / (rms + 1e-5)

        # Baseline amplitude check: genuine hand claps produce sharp peaks
        if peak < 0.20 or crest_factor < 2.8:
            return False

        # Energy must decisively rise above noise floor
        delta = rms - self._noise_floor
        required_delta = max(0.04, self._noise_floor * 0.8)
        if delta < required_delta:
            return False

        # Spectral discrimination: Hand Clap vs Table Knock/Thud
        try:
            fft_mag = np.abs(np.fft.rfft(samples))
            freqs = np.fft.rfftfreq(len(samples), 1.0 / 16000.0)

            low_band = (freqs >= 100) & (freqs < 900)
            high_band = (freqs >= 1200) & (freqs <= 5500)

            e_low = float(np.sum(fft_mag[low_band] ** 2)) + 1e-6
            e_high = float(np.sum(fft_mag[high_band] ** 2)) + 1e-6

            # Real hand claps have high-frequency snap energy >= 0.45 * low-frequency energy
            # Table knocks and thuds typically have e_high / e_low < 0.15
            if (e_high / e_low) < 0.45:
                return False
        except Exception:
            return False

        return True

    def process_event(self, frame_bytes: bytes) -> str:
        """
        Process an incoming audio chunk (16kHz S16LE PCM).
        Returns:
            ClapResult.DUAL: if two valid claps occur within cadence (180ms - 750ms).
            ClapResult.SINGLE: if one valid clap occurred and timed out with no second clap.
            ClapResult.NONE: no event detected.
        """
        if not self.enabled or not frame_bytes or len(frame_bytes) < 4:
            return ClapResult.NONE

        now = time.time()

        # Enforce debounce cooldown after a trigger
        if (now - self._last_trigger_time) < self.cooldown:
            return ClapResult.NONE

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

        # State 1: We are waiting for the second clap
        if self._first_clap_time > 0.0:
            elapsed = now - self._first_clap_time

            # If elapsed time exceeds max cadence window, the first clap timed out -> confirmed SINGLE CLAP!
            if elapsed > self.max_interval:
                self.reset()
                # Check if current frame could be a new first clap
                if is_impulse:
                    self._first_clap_time = now
                    self._first_clap_energy = rms
                    self._saw_decay_after_first = False
                    return ClapResult.NONE

                # Confirm SINGLE CLAP with small debounce so next dual-clap isn't locked out
                self._last_trigger_time = now - max(0.0, self.cooldown - 0.25)
                return ClapResult.SINGLE

            # Any non-impulsive frame proves acoustic decay between claps
            if not is_impulse or rms < (self._first_clap_energy * 0.75):
                self._saw_decay_after_first = True

            # Check if second clap arrives within valid cadence window
            if elapsed >= self.min_interval:
                if is_impulse and self._saw_decay_after_first:
                    # Dual clap verified!
                    self._last_trigger_time = now
                    self.reset()
                    return ClapResult.DUAL

            return ClapResult.NONE

        # State 0: Waiting for the first clap
        if is_impulse:
            self._first_clap_time = now
            self._first_clap_energy = rms
            self._saw_decay_after_first = False
            return ClapResult.NONE

        return ClapResult.NONE

    def process_frame(self, frame_bytes: bytes) -> bool:
        """
        Process an incoming audio chunk (16kHz S16LE PCM).
        Backward compatible helper: Returns True if a dual-clap cadence is detected.
        """
        return self.process_event(frame_bytes) == ClapResult.DUAL

