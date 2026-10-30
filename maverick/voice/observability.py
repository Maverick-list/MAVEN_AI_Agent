"""Maverick DevOS - Structured Observability & Diagnostic Logging for Voice Subsystems."""

from collections import deque
import fcntl
import json
import os
import re
import sys
import threading
import time
import traceback
from typing import Any, Deque, Dict, List, Optional

STATE_DIR = os.path.expanduser("~/.local/state/maverick")
LATENCY_TELEMETRY_FILE = os.path.join(STATE_DIR, "latency-telemetry.jsonl")

# Masking patterns for sensitive authentication credentials and tokens
SENSITIVE_PATTERNS = [
    (re.compile(r"(bearer\s+)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"(xi-api-key\s*[:=]\s*)[A-Za-z0-9_\-\.]{6,}", re.IGNORECASE), r"\1[REDACTED_API_KEY]"),
    (re.compile(r"((?:api[-_]?key|token|secret|password|passwd|auth)\s*[:=]\s*)[A-Za-z0-9_\-\.]{6,}", re.IGNORECASE), r"\1[REDACTED_CREDENTIAL]"),
    (re.compile(r"\bsk[-_][A-Za-z0-9_\-]{16,}\b"), "[REDACTED_ELEVENLABS_OR_API_KEY]"),
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
    def tts_start(self, text: str, engine: str = "elevenlabs") -> None:
        self._log("TTS", "INFO", f"Speaking response: \"{text}\"", engine=engine)

    def tts_fallback(self, primary_engine: str, fallback_engine: str, reason: str) -> None:
        self._log(
            "TTS", "WARNING",
            f"Primary TTS '{primary_engine}' unavailable; falling back to '{fallback_engine}'",
            reason=reason,
        )

    def tts_complete(self, duration_sec: float, engine: Optional[str] = None) -> None:
        kwargs: Dict[str, Any] = {"duration_sec": round(duration_sec, 2)}
        if engine:
            kwargs["engine"] = engine
        self._log("TTS", "DEBUG", "TTS speech output completed", **kwargs)

    def tts_interrupted(self) -> None:
        self._log("TTS", "WARNING", "TTS speech interrupted by user silence/stop request")

    # 9. Per-Stage Voice Pipeline Latency Telemetry
    def pipeline_latency(self, metrics: Dict[str, Any]) -> None:
        safe_kwargs: Dict[str, Any] = {}
        for key in (
            "route",
            "model_used",
            "stt_backend",
            "wake_ms",
            "stt_ms",
            "network_dns_ms",
            "network_tls_ms",
            "gateway_queue_ms",
            "llm_ttft_ms",
            "llm_first_sentence_ms",
            "llm_total_ms",
            "llm_retries",
            "tts_ttfb_ms",
            "tts_playback_ms",
            "tts_chunks",
            "ttfa_ms",
            "total_turn_ms",
        ):
            if key in metrics and metrics[key] is not None:
                val = metrics[key]
                safe_kwargs[key] = round(val, 1) if isinstance(val, float) else val
        self._log("LATENCY", "INFO", "Voice turn latency breakdown", **safe_kwargs)
        record_turn_latency(metrics)

    # 10. Exception Logging
    def exception(self, context: str, exc: Exception) -> None:
        err_msg = f"Exception in {context}: {str(exc)}\n{traceback.format_exc()}"
        self._log("ERROR", "ERROR", err_msg)


_LATENCY_LOCK = threading.Lock()
_RECENT_LATENCY: Deque[Dict[str, Any]] = deque(maxlen=60)
_LATENCY_FILE_SIG: Optional[tuple] = None


def record_turn_latency(metrics: Dict[str, Any], path: str = LATENCY_TELEMETRY_FILE) -> Dict[str, Any]:
    """Persist privacy-safe per-stage latency telemetry (chmod 0600) and update rolling memory buffer."""
    global _LATENCY_FILE_SIG
    now = time.time()
    entry: Dict[str, Any] = {
        "timestamp": time.strftime("%H:%M:%S"),
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "epoch": round(now, 3),
        "route": str(metrics.get("route") or "unknown"),
        "lang": str(metrics.get("lang") or "en"),
        "model_used": redact_sensitive_text(str(metrics.get("model_used") or "local")),
        "stt_backend": str(metrics.get("stt_backend") or "none"),
        "tts_engine": str(metrics.get("tts_engine") or "none"),
        "tts_chunks": int(metrics.get("tts_chunks") or 0),
        "llm_retries": int(metrics.get("llm_retries") or 0),
    }
    for num_key in (
        "wake_ms",
        "stt_ms",
        "network_dns_ms",
        "network_tcp_ms",
        "network_tls_ms",
        "gateway_queue_ms",
        "llm_ttft_ms",
        "llm_first_sentence_ms",
        "llm_total_ms",
        "tts_ttfb_ms",
        "tts_playback_ms",
        "ttfa_ms",
        "total_turn_ms",
    ):
        val = metrics.get(num_key)
        entry[num_key] = round(float(val), 1) if isinstance(val, (int, float)) else None

    with _LATENCY_LOCK:
        if path == LATENCY_TELEMETRY_FILE:
            _RECENT_LATENCY.append(entry)
        try:
            os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
            fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
            with open(fd, "a", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(json.dumps(entry) + "\n")
                    f.flush()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            os.chmod(path, 0o600)
            if path == LATENCY_TELEMETRY_FILE:
                st = os.stat(path)
                _LATENCY_FILE_SIG = (st.st_ino, st.st_size, st.st_mtime_ns)
        except Exception:
            pass
    return entry


def load_recent_latency(limit: int = 25, path: str = LATENCY_TELEMETRY_FILE) -> List[Dict[str, Any]]:
    """Load recent per-turn latency records with cross-process live sync from latency-telemetry.jsonl."""
    global _LATENCY_FILE_SIG
    is_default = path == LATENCY_TELEMETRY_FILE
    if not os.path.isfile(path):
        if is_default:
            with _LATENCY_LOCK:
                return list(_RECENT_LATENCY)[-limit:]
        return []

    try:
        st = os.stat(path)
        sig = (st.st_ino, st.st_size, st.st_mtime_ns)
    except Exception:
        if is_default:
            with _LATENCY_LOCK:
                return list(_RECENT_LATENCY)[-limit:]
        return []

    if is_default:
        with _LATENCY_LOCK:
            if _LATENCY_FILE_SIG == sig and _RECENT_LATENCY:
                return list(_RECENT_LATENCY)[-limit:]

    loaded: Deque[Dict[str, Any]] = deque(maxlen=max(60, limit))
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                    if isinstance(obj, dict):
                        loaded.append(obj)
                except Exception:
                    continue
    except Exception:
        pass

    with _LATENCY_LOCK:
        if path == LATENCY_TELEMETRY_FILE:
            _RECENT_LATENCY.clear()
            _RECENT_LATENCY.extend(loaded)
            _LATENCY_FILE_SIG = sig
            return list(_RECENT_LATENCY)[-limit:]
        return list(loaded)[-limit:]


def get_latency_summary(limit: int = 25, path: str = LATENCY_TELEMETRY_FILE) -> Dict[str, Any]:
    """Compute latest turn + rolling averages across each voice pipeline stage."""
    items = load_recent_latency(limit=limit, path=path)
    latest = items[-1] if items else None

    def _avg(field: str, subset: Optional[List[Dict[str, Any]]] = None) -> Optional[float]:
        pool = subset if subset is not None else items
        vals = [float(x[field]) for x in pool if isinstance(x.get(field), (int, float)) and float(x[field]) >= 0.0]
        return round(sum(vals) / len(vals), 1) if vals else None

    ai_items = [x for x in items if str(x.get("route", "")).startswith("openclaw")]
    return {
        "turn_count": len(items),
        "ai_turn_count": len(ai_items),
        "latest": latest,
        "averages_ms": {
            "wake_ms": _avg("wake_ms"),
            "stt_ms": _avg("stt_ms"),
            "network_dns_ms": _avg("network_dns_ms"),
            "network_tls_ms": _avg("network_tls_ms"),
            "gateway_queue_ms": _avg("gateway_queue_ms", ai_items),
            "llm_ttft_ms": _avg("llm_ttft_ms", ai_items),
            "llm_first_sentence_ms": _avg("llm_first_sentence_ms", ai_items),
            "llm_total_ms": _avg("llm_total_ms", ai_items),
            "tts_ttfb_ms": _avg("tts_ttfb_ms"),
            "tts_playback_ms": _avg("tts_playback_ms"),
            "ttfa_ms": _avg("ttfa_ms"),
            "ai_ttfa_ms": _avg("ttfa_ms", ai_items),
            "total_turn_ms": _avg("total_turn_ms"),
        },
        "recent": items[-12:],
    }


# Global default logger singleton
voice_logger = VoiceLogger()
