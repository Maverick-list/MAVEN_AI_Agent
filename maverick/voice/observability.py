"""Maverick DevOS - Structured Observability & Diagnostic Logging for Voice Subsystems."""

import os
import re
import sys
import time
import traceback
from typing import Any, Dict, Optional

# Masking patterns for sensitive authentication credentials and tokens
SENSITIVE_PATTERNS = [
    (re.compile(r"(bearer\s+)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"((?:api[-_]?key|token|secret|password|passwd|auth)\s*[:=]\s*)[A-Za-z0-9_\-\.]{6,}", re.IGNORECASE), r"\1[REDACTED_CREDENTIAL]"),
    (re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b"), "[REDACTED_GOOGLE_API_KEY]"),
    (re.compile(r"\b[0-9]{8,10}:[a-zA-Z0-9_-]{35}\b"), "[REDACTED_TELEGRAM_BOT_TOKEN]"),
    (re.compile(r"\b[MNO][a-zA-Z0-9_-]{23,25}\.[a-zA-Z0-9_-]{6}\.[a-zA-Z0-9_-]{27,}\b"), "[REDACTED_DISCORD_TOKEN]"),
]


def redact_sensitive_text(text: str) -> str:
    """Scrub sensitive tokens, API keys, passwords, and secrets from log strings."""
    if not text:
        return ""
    redacted = str(text)
    for pattern, replacement in SENSITIVE_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


class VoiceLogger:
    """
    Structured, rate-limited, privacy-safe logger for the Maven voice interaction engine.
    Emits formatted diagnostic events with millisecond precision timestamps.
    Ensures standard output and error are immediately flushed so file logs (e.g. tail -f)
    reflect live events with zero buffering latency.
    """

    def __init__(self, stream=None, heartbeat_interval_sec: float = 5.0):
        self.stream = stream or sys.stdout
        self.heartbeat_interval_sec = heartbeat_interval_sec
        self._last_heartbeat_time = 0.0

    def _log(self, subsystem: str, level: str, message: str, **kwargs) -> None:
        """Write formatted timestamped log record and flush."""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        ms = int((time.time() % 1.0) * 1000)
        formatted_ts = f"{now_str}.{ms:03d}"

        extra = ""
        if kwargs:
            parts = []
            for k, v in kwargs.items():
                if isinstance(v, str):
                    val_str = f'"{redact_sensitive_text(v)}"'
                elif isinstance(v, float):
                    val_str = f"{v:.4f}"
                else:
                    val_str = str(v)
                parts.append(f"{k}={val_str}")
            extra = " {" + ", ".join(parts) + "}"

        clean_msg = redact_sensitive_text(message)
        line = f"[{formatted_ts}] [{subsystem.upper()}] [{level.upper()}] {clean_msg}{extra}\n"
        try:
            self.stream.write(line)
            self.stream.flush()
        except Exception:
            pass

    # 1. Daemon Lifecycle
    def startup(self, pid: int, profile: str, device: str, model_id: str, whisper_bin: str) -> None:
        self._log(
            "DAEMON", "INFO",
            "Maven Voice Daemon initialized and listening",
            pid=pid,
            profile=profile,
            device=device,
            model=model_id,
        )

    def shutdown(self, reason: str = "normal") -> None:
        self._log("DAEMON", "INFO", "Maven Voice Daemon shutting down", reason=reason)

    # 2. Audio Capture
    def audio_device_init(self, backend: str, device: str, sample_rate: int, channels: int) -> None:
        self._log(
            "AUDIO", "INFO",
            "Audio capture backend connected",
            backend=backend,
            device=device,
            sample_rate=sample_rate,
            channels=channels,
        )

    def audio_capture_started(self) -> None:
        self._log("AUDIO", "DEBUG", "Microphone stream capture started")

    def audio_capture_stopped(self) -> None:
        self._log("AUDIO", "DEBUG", "Microphone stream capture stopped")

    # 3. Heartbeat & VAD
    def heartbeat(
        self,
        state: str,
        frames: int,
        rms: float,
        noise_floor: float,
        is_burst: bool,
        rss_mb: float,
        cpu_pct: float,
        force: bool = False,
    ) -> None:
        """Emit rate-limited heartbeat telemetry (default every 5 seconds)."""
        now = time.time()
        if not force and (now - self._last_heartbeat_time) < self.heartbeat_interval_sec:
            return
        self._last_heartbeat_time = now

        vad_state = "SPEECH_BURST" if is_burst else "QUIET"
        self._log(
            "DAEMON", "DEBUG",
            "Heartbeat telemetry",
            state=state,
            frames_processed=frames,
            rms=round(rms, 4),
            noise_floor=round(noise_floor, 4),
            vad=vad_state,
            rss_mb=round(rss_mb, 1),
            cpu_pct=round(cpu_pct, 1),
        )

    def vad_burst(self, rms: float, noise_floor: float, delta: float) -> None:
        self._log(
            "VAD", "DEBUG",
            "Acoustic onset burst detected",
            rms=round(rms, 4),
            floor=round(noise_floor, 4),
            delta=round(delta, 4),
        )

    # 4. Wake-Word Engine
    def wake_candidate(self, audio_bytes_len: int, prompt: str, pass_num: int = 1) -> None:
        self._log(
            "WAKE", "DEBUG",
            f"Acoustic verification pass {pass_num} initiated",
            snapshot_bytes=audio_bytes_len,
        )

    def wake_result(
        self,
        accepted: bool,
        phrase: Optional[str] = None,
        transcript: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        if accepted:
            self._log(
                "WAKE", "INFO",
                f"Wake word detected and verified: '{phrase or transcript}'",
                matched=phrase or transcript,
            )
        else:
            self._log(
                "WAKE", "DEBUG",
                "Wake candidate rejected",
                decoded=transcript or "",
                reason=reason or "no_match",
            )

    # 5. Session State Transitions
    def state_transition(self, old_state: str, new_state: str) -> None:
        self._log("STATE", "INFO", f"State transition: {old_state.upper()} -> {new_state.upper()}")

    def wake_acknowledgment(self, phrase: str) -> None:
        self._log("WAKE", "INFO", f"Speaking wake-word acknowledgment: \"{phrase}\"")

    def utterance_ready(self, audio_bytes_len: int, duration_sec: float, trigger: str) -> None:
        self._log(
            "SESSION", "INFO",
            "User speech utterance buffered and ready for transcription",
            bytes=audio_bytes_len,
            duration_sec=round(duration_sec, 2),
            trigger=trigger,
        )

    def session_timeout(self, reason: str = "no_speech_timeout") -> None:
        self._log("SESSION", "INFO", "Listening session reset to IDLE", reason=reason)

    # 6. Speech-to-Text (STT)
    def stt_start(self, audio_bytes_len: int, language: str = "auto") -> None:
        self._log("STT", "DEBUG", "Whisper STT decoding initiated", bytes=audio_bytes_len, language=language)

    def stt_complete(self, transcript: str, duration_sec: float) -> None:
        self._log(
            "STT", "INFO",
            f"Transcribed: \"{transcript}\"",
            duration_sec=round(duration_sec, 3),
        )

    def stt_empty(self, duration_sec: float, reason: str = "silence_or_noise") -> None:
        self._log(
            "STT", "DEBUG",
            "Whisper STT returned no intelligible speech",
            duration_sec=round(duration_sec, 3),
            reason=reason,
        )

    def stt_failure(self, error: str) -> None:
        self._log("STT", "ERROR", f"Whisper STT decoding error: {error}")

    # 7. Intent Classification & Action
    def intent_classified(self, intent: str, target: Optional[str], lang: str, confidence: float, clean_text: str) -> None:
        self._log(
            "INTENT", "INFO",
            f"Classified intent '{intent}'",
            intent=intent,
            target=target or "none",
            lang=lang,
            confidence=round(confidence, 2),
        )

    def action_start(self, action: str, target: Optional[str], confirmed: bool = False) -> None:
        self._log("ACTION", "DEBUG", f"Executing action '{action}'", target=target or "none", confirmed=confirmed)

    def action_complete(self, action: str, status: str, response: str) -> None:
        self._log(
            "ACTION", "INFO",
            f"Action completed with status '{status}'",
            action=action,
            status=status,
            response=response[:80] if response else "",
        )

    def action_confirmation_required(self, app_id: str, prompt: str) -> None:
        self._log(
            "ACTION", "WARNING",
            f"Consequential action on '{app_id}' blocked awaiting human confirmation",
            target=app_id,
        )

    # 8. Text-to-Speech (TTS)
    def tts_start(self, text: str, engine: str = "speech_dispatcher") -> None:
        self._log("TTS", "INFO", f"Speaking response: \"{text}\"", engine=engine)

    def tts_complete(self, duration_sec: float) -> None:
        self._log("TTS", "DEBUG", "TTS speech output completed", duration_sec=round(duration_sec, 2))

    def tts_interrupted(self) -> None:
        self._log("TTS", "WARNING", "TTS speech interrupted by user silence/stop request")

    # 9. Exception Logging
    def exception(self, context: str, exc: Exception) -> None:
        err_msg = f"Exception in {context}: {str(exc)}\n{traceback.format_exc()}"
        self._log("ERROR", "ERROR", err_msg)


# Global default logger singleton
voice_logger = VoiceLogger()
