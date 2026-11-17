"""Maverick DevOS - Voice Interaction Session & Finite State Machine."""

from enum import Enum
import json
import os
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional

from maverick.voice.audio import AudioCapture, calculate_rms
from maverick.voice.clap import DualClapDetector, ClapResult
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

    def interrupt(self, preserve_audio: Optional[bytes] = None) -> None:
        """Stop TTS speech, preserve incoming audio buffer, and transition immediately to LISTENING."""
        voice_logger.tts_interrupted()
        self.tts.stop()
        self._transition_to(VoiceState.INTERRUPTED)
        self.last_trigger_source = "barge_in"

        # Preserve the onset speech buffer and transition directly to LISTENING
        self._audio_buffer.clear()
        if preserve_audio:
            self._audio_buffer.extend(preserve_audio)
            self._has_detected_speech = True
        else:
            self._has_detected_speech = False

        self._listen_start_time = time.time()
        self._last_speech_time = self._listen_start_time
        self._transition_to(VoiceState.LISTENING)

    def _emit_window_action(self, action: str, source: str) -> None:
        """Persist window control action to local state for instantaneous desktop GUI sync."""
        try:
            from maverick.launcher import ensure_state_dir, STATE_DIR
            ensure_state_dir()
            state_file = os.path.join(STATE_DIR, "window_control.json")
            now = time.time()
            seq = int(now * 1000)
            tmp_file = f"{state_file}.tmp.{os.getpid()}"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump({
                    "action": action,
                    "source": source,
                    "timestamp": now,
                    "seq": seq,
                }, f)
            os.replace(tmp_file, state_file)
        except Exception as exc:
            voice_logger.warning(f"Failed to persist window action: {exc}")

    def trigger_wake_word(self, source: str = "ui") -> None:
        """Programmatically trigger wake-word state (e.g. from UI keypress or clap)."""
        if self._state in (VoiceState.IDLE, VoiceState.ERROR):
            self.last_trigger_source = source
            self._emit_window_action("open", source=source)
            self._transition_to(VoiceState.WAKE_WORD_DETECTED)
            self._start_listening()

    def _start_listening(self, seed_audio: bytes = b"", has_speech: bool = False) -> None:
        """Enter listening state and begin buffering user speech (preserving any wake-word pre-roll)."""
        self._audio_buffer.clear()
        if seed_audio:
            self._audio_buffer.extend(seed_audio)
        self._has_detected_speech = bool(has_speech)
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

        # Feedback loop prevention with intelligent barge-in monitoring
        if self.tts.is_speaking():
            if self._state != VoiceState.SPEAKING:
                self._transition_to(VoiceState.SPEAKING)

            # Barge-in detection: inspect incoming microphone audio for user speech bursts
            chunk = self.audio.read_chunk()
            if chunk:
                # Check for single-clap to immediately dismiss / silence assistant
                if getattr(self, "clap_detector", None) and hasattr(self.clap_detector, "process_event"):
                    c_event = self.clap_detector.process_event(chunk)
                    if c_event == ClapResult.SINGLE:
                        voice_logger.info("Single clap detected during SPEAKING: silencing assistant and closing window")
                        self._emit_window_action("close", source="single_clap")
                        self.tts.stop()
                        self.rearm()
                        return None

                rms = calculate_rms(chunk)
                noise_floor = getattr(self.wake_detector, "_noise_floor", 0.05) or 0.05
                # Distinct acoustic onset during playback interrupts assistant speech and transitions to listening
                threshold = max(getattr(self.config, "barge_in_threshold_rms", 0.18), noise_floor * 3.5)
                if rms >= threshold:
                    self.interrupt(preserve_audio=chunk)
                    return None
            time.sleep(0.04)
            return None
        elif self._state == VoiceState.SPEAKING and not self.tts.is_speaking():
            self.rearm()

        # 1. State: IDLE - Monitor for wake word or dual-clap / single-clap pattern
        if self._state == VoiceState.IDLE:
            chunk = self.audio.read_chunk()
            if not chunk:
                return None

            wake_triggered = bool(self.wake_detector.process_frame(chunk))
            clap_event = ClapResult.NONE
            if getattr(self, "clap_detector", None) and hasattr(self.clap_detector, "process_event"):
                clap_event = self.clap_detector.process_event(chunk)
            elif getattr(self, "clap_detector", None) and self.clap_detector.process_frame(chunk):
                clap_event = ClapResult.DUAL

            if clap_event == ClapResult.SINGLE:
                voice_logger.info("Single clap detected while IDLE: closing GUI window")
                self._emit_window_action("close", source="single_clap")
                if hasattr(self.tts, "stop"):
                    self.tts.stop()
                return None

            if wake_triggered or clap_event == ClapResult.DUAL:
                self.last_trigger_source = "dual_clap" if clap_event == ClapResult.DUAL else "wake_word"
                self._emit_window_action("open", source=self.last_trigger_source)
                seed_audio, has_cmd = b"", False
                if wake_triggered and hasattr(self.wake_detector, "consume_trigger_audio"):
                    seed_audio, has_cmd = self.wake_detector.consume_trigger_audio()
                self._transition_to(VoiceState.WAKE_WORD_DETECTED)
                self._start_listening(seed_audio=seed_audio, has_speech=has_cmd)
            return None

        # 2. State: LISTENING - Buffer speech until silence or timeout
        elif self._state == VoiceState.LISTENING:
            now = time.time()
            chunk = self.audio.read_chunk()
            if not chunk:
                return None

            # Check clap event during listening: single clap closes, dual clap resets listening
            clap_event = ClapResult.NONE
            if getattr(self, "clap_detector", None) and hasattr(self.clap_detector, "process_event"):
                clap_event = self.clap_detector.process_event(chunk)
            elif getattr(self, "clap_detector", None) and self.clap_detector.process_frame(chunk):
                clap_event = ClapResult.DUAL

            if clap_event == ClapResult.SINGLE:
                voice_logger.info("Single clap detected while LISTENING: closing GUI window and returning to IDLE")
                self._emit_window_action("close", source="single_clap")
                if hasattr(self.tts, "stop"):
                    self.tts.stop()
                self.rearm()
                return None
            elif clap_event == ClapResult.DUAL:
                self._emit_window_action("open", source="dual_clap")
                self._audio_buffer.clear()
                self._listen_start_time = now
                self._last_speech_time = now
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
                if not self._has_detected_speech:
                    voice_logger.info("Recording timed out with no speech detected; discarding ambient noise buffer.")
                    self.rearm()
                    return None
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
