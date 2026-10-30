"""Maverick DevOS - Local Wake-Word Detection Engine."""

from abc import ABC, abstractmethod
import re
import time
from typing import List, Optional
import numpy as np

from maverick.voice.audio import calculate_rms
from maverick.voice.config import VoiceConfig
from maverick.voice.observability import voice_logger
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

    def rearm(self) -> None:
        """Re-arm wake detector for the next interaction turn."""
        self.reset()


class LocalKeywordWakeWordDetector(WakeWordDetector):
    """
    True local keyword recognition engine.
    Combines stage-1 energy onset Voice Activity Detection (VAD) with dynamic
    ambient noise floor tracking and stage-2 two-pass acoustic keyword verification
    via whisper.cpp.
    Operates offline, recognizes 'Hey Maven' and 'Maven' (or 'Jarvis'), and
    decisively rejects unrelated loud noises (claps, coughs, sneezes), near-homophones
    (haven, mayhem, memory, modern), and non-wake speech.
    """

    WAKE_REGEX = re.compile(
        r"^\s*[\"'\.,\-\s]*(?:(?:hey|hei|halo|hai|ok|okay)\s+)?(?:maven|jarvis|mavin|mayven|meiven|maveran|maveram)\b",
        re.IGNORECASE,
    )
    TWO_WORD_WAKE = re.compile(
        r"^\s*[\"'\.,\-\s]*(?:hey|hei|halo|hai|ok|okay)\s+(?:maven|jarvis)\b",
        re.IGNORECASE,
    )
    PROMPT_PASS1 = "Hey Maven, Jarvis, haven, mayhem, bacon, raven"
    PROMPT_PASS2 = "memory, modern, method, motor, haven, morning, music, meeting, weather, question, report, project"
    DISTRACTOR_REGEX = re.compile(
        r"\b(memory|modern|method|motor|haven|shaven|mayhem|marvin|bacon|morning|music|meeting)\b",
        re.IGNORECASE,
    )

    @classmethod
    def verify_text_candidate(cls, t1: str, t2: Optional[str] = None) -> bool:
        """
        Evaluate candidate transcription strings against two-pass wake rules:
        - Must start with wake word prefix (WAKE_REGEX).
        - Mid-sentence matches are rejected.
        - Two-word wake phrases (TWO_WORD_WAKE) pass directly.
        - Single-word candidates are rejected if distractor pass (t2) indicates near-homophone.
        """
        if not t1 or not cls.WAKE_REGEX.search(t1):
            return False
        if cls.TWO_WORD_WAKE.search(t1):
            return True
        if t2 and cls.DISTRACTOR_REGEX.search(t2):
            if not cls.WAKE_REGEX.search(t2):
                return False
        return True

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
        self._last_burst_time = 0.0
        self._failed_checks = 0
        self._noise_floor = 0.02
        self._noise_floor_initialized = False
        self._ring_buffer = bytearray()
        # Maintain ~1.2 seconds of 16kHz 16-bit mono audio
        self._max_buffer_bytes = int(self.config.sample_rate * 1.2 * 2)

    def reset(self) -> None:
        """Reset buffer and trigger timers."""
        self._ring_buffer.clear()
        self._last_trigger_time = 0.0
        self._last_check_time = 0.0
        self._last_burst_time = 0.0
        self._failed_checks = 0
        if self._noise_floor_initialized:
            self._noise_floor = min(0.35, self._noise_floor)
        else:
            self._noise_floor = 0.02

    def rearm(self) -> None:
        """
        Re-arm wake-word detection for the next interaction turn.
        Clears buffered audio, resets check cooldown, and ensures debounce timer
        allows immediate activation without erasing the calibrated acoustic noise floor.
        """
        self._ring_buffer.clear()
        self._last_trigger_time = 0.0
        self._last_check_time = 0.0
        self._last_burst_time = 0.0
        self._failed_checks = 0
        if self._noise_floor > 0.45:
            self._noise_floor = 0.35

    def process_frame(self, frame_bytes: bytes) -> bool:
        """
        Evaluate incoming audio frame.
        Uses fast RMS energy gating with dynamic background floor adaptation to avoid
        running inference on silence or steady ambient hum, followed by acoustic
        keyword verification when speech energy rises over the ambient floor.
        Includes adaptive backoff cooldown on consecutive non-wake bursts to protect
        CPU during continuous background noise.
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

        # Adaptively track ambient noise floor using asymmetric tracking
        if not self._noise_floor_initialized:
            self._noise_floor = min(0.40, rms)
            self._noise_floor_initialized = True
        else:
            if rms < self._noise_floor:
                self._noise_floor = 0.85 * self._noise_floor + 0.15 * rms
            else:
                self._noise_floor = 0.985 * self._noise_floor + 0.015 * rms

        delta = rms - self._noise_floor
        threshold_delta = max(0.06, self._noise_floor * 0.40)
        is_burst = delta > threshold_delta

        if not is_burst:
            if (now - self._last_burst_time) > 3.0:
                self._failed_checks = 0
            return False

        self._last_burst_time = now
        voice_logger.vad_burst(rms, self._noise_floor, delta)

        # Stage 1: Fast VAD check - verify energy exceeds both absolute threshold and ambient floor
        if rms < self.config.speech_start_threshold_rms:
            return False

        # Adaptive cooldown check between acoustic verification passes
        # Base cooldown is 0.4s; backs off to 1.2s and 2.5s on sustained non-wake bursts to protect CPU
        if self._failed_checks >= 3:
            required_cooldown = 2.5
        elif self._failed_checks >= 1:
            required_cooldown = 1.2
        else:
            required_cooldown = 0.4
        if (now - self._last_check_time) < required_cooldown:
            return False

        # Stage 2: Two-pass acoustic keyword verification
        # Need at least ~0.3s of buffered audio (9,600 bytes) to support rapid/short wake utterances
        if len(self._ring_buffer) < 9600:
            return False

        self._last_check_time = now
        audio_snapshot = bytes(self._ring_buffer)

        # Pass 1: Sensitive candidate detection with contrastive proper-noun prompt
        voice_logger.wake_candidate(len(audio_snapshot), self.PROMPT_PASS1, pass_num=1)
        t1 = self.stt.transcribe(
            audio_snapshot,
            language="en",
            prompt=self.PROMPT_PASS1,
        )

        if not t1 or not self.WAKE_REGEX.search(t1):
            voice_logger.wake_result(accepted=False, transcript=t1 or "", reason="pass1_no_match")
            self._failed_checks += 1
            return False

        # If high-confidence two-word wake phrase ("Hey Maven", "Hey Jarvis") is detected at prefix:
        if self.TWO_WORD_WAKE.search(t1):
            voice_logger.wake_result(accepted=True, phrase=t1)
            self._last_trigger_time = now
            self._ring_buffer.clear()
            self._failed_checks = 0
            return True

        # Pass 2: Precision confirmation for single-word candidates against common phonetically overlapping words
        voice_logger.wake_candidate(len(audio_snapshot), self.PROMPT_PASS2, pass_num=2)
        t2 = self.stt.transcribe(
            audio_snapshot,
            language="en",
            prompt=self.PROMPT_PASS2,
        )

        if not self.verify_text_candidate(t1, t2):
            voice_logger.wake_result(accepted=False, transcript=f"t1={t1}, t2={t2}", reason="rejected_distractor")
            self._failed_checks += 1
            return False

        voice_logger.wake_result(accepted=True, phrase=t1)
        self._last_trigger_time = now
        self._ring_buffer.clear()
        self._failed_checks = 0
        return True


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
