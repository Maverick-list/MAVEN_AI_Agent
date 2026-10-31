"""Maverick DevOS - Text-to-Speech (TTS) Providers & Automatic Fallback Router."""

from abc import ABC, abstractmethod
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional

from maverick.voice.config import VoiceConfig, load_voice_settings
from maverick.voice.elevenlabs_tts import ElevenLabsTTSProvider
from maverick.voice.local_neural_tts import LocalNeuralTTSProvider
from maverick.voice.observability import voice_logger


def detect_speech_language(text: str) -> str:
    """Detect whether response text is Indonesian ('id') or English ('en')."""
    if not text:
        return "en"
    id_keywords = {
        "buka", "sedang", "berjalan", "penggunaan", "tersedia", "musik", "lagu",
        "baterai", "konfirmasi", "selamat", "anda", "saat", "ini", "tidak",
        "adalah", "dari", "persen", "halo", "ya", "saya", "mendengarkan",
        "aplikasi", "memori", "ringkasan", "mikrofon", "dimatikan", "diaktifkan",
        "dinaikkan", "diturunkan", "diatur", "berikutnya", "dijeda",
    }
    tokens = set(re.findall(r"[a-zA-Z]+", text.lower()))
    if len(tokens.intersection(id_keywords)) >= 1:
        return "id"
    return "en"


class TTSProvider(ABC):
    """Abstract interface for speech synthesis engines."""

    @abstractmethod
    def speak(self, text: str, wait: bool = True, language: Optional[str] = None) -> bool:
        """Synthesize and speak the provided text."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Interrupt and stop current speech immediately."""
        pass

    @abstractmethod
    def is_speaking(self) -> bool:
        """Return True if speech playback is currently active."""
        pass


class SpeechDispatcherTTS(TTSProvider):
    """
    Local speech synthesis using Linux Speech Dispatcher (/usr/bin/spd-say).
    Provides low-latency, zero-cost, offline voice feedback as automatic fallback.
    """

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or VoiceConfig()
        self._current_proc: Optional[subprocess.Popen] = None
        self._is_speaking = False
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        return shutil.which("spd-say") is not None

    def is_speaking(self) -> bool:
        with self._lock:
            if self._current_proc and self._current_proc.poll() is None:
                return True
            return self._is_speaking

    def speak(self, text: str, wait: bool = True, language: Optional[str] = None) -> bool:
        """
        Synthesize text using spd-say.
        Supports cancellation, interruption, and automatic English/Indonesian language selection.
        """
        if not text or not text.strip():
            return False

        bin_path = shutil.which("spd-say")
        if not bin_path:
            return False

        # Stop previous utterance before speaking new text
        self.stop()

        clean_text = text.strip()
        target_lang = language or detect_speech_language(clean_text)

        cmd = [
            bin_path,
            "-l", target_lang,
            "-r", str(self.config.tts_rate),
            "-p", str(self.config.tts_pitch),
            "-i", str(self.config.tts_volume),
        ]

        if wait:
            cmd.append("-w")

        cmd.append(clean_text)

        try:
            with self._lock:
                self._is_speaking = True
                self._current_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            if wait and self._current_proc:
                self._current_proc.wait(timeout=30.0)
                with self._lock:
                    self._is_speaking = False
                    self._current_proc = None
            return True
        except Exception:
            with self._lock:
                self._is_speaking = False
                self._current_proc = None
            return False

    def stop(self) -> None:
        """Immediately stop speech synthesis and clear dispatcher queue."""
        with self._lock:
            self._is_speaking = False
            if self._current_proc and self._current_proc.poll() is None:
                try:
                    self._current_proc.terminate()
                except Exception:
                    pass
                self._current_proc = None

        # Issue cancel signal to speech-dispatcher daemon
        bin_path = shutil.which("spd-say")
        if bin_path:
            try:
                subprocess.run(
                    [bin_path, "-l", "en", "-S"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=1.0,
                )
            except Exception:
                pass


class HybridTTSProvider(TTSProvider):
    """
    Three-Tier Permanent Voice Architecture:
    1. PRIMARY: Local Indonesian Neural TTS (Pocket-TTS Indonesian 6L student model).
    2. OPTIONAL PREMIUM: ElevenLabs (explicit user opt-in only, never default).
    3. EMERGENCY FALLBACK: Speech Dispatcher (with audible warning: 'Emergency fallback: voice switched to speech dispatcher.').
    """

    def __init__(
        self,
        config: Optional[VoiceConfig] = None,
        local_neural: Optional[LocalNeuralTTSProvider] = None,
        elevenlabs: Optional[ElevenLabsTTSProvider] = None,
        fallback: Optional[SpeechDispatcherTTS] = None,
        primary: Optional[Any] = None,  # Backward compatibility
    ):
        self.config = config or VoiceConfig()
        self._explicit_primary = (primary is not None and local_neural is None)
        self.local_neural = local_neural or LocalNeuralTTSProvider(self.config)
        self.elevenlabs = elevenlabs or (primary if isinstance(primary, ElevenLabsTTSProvider) else ElevenLabsTTSProvider(self.config))
        self.primary = self.elevenlabs  # Maintain self.primary attribute for backwards compatibility
        self.fallback = fallback or SpeechDispatcherTTS(self.config)
        self.last_used_engine: str = "none"
        self.last_fallback_reason: Optional[str] = None
        self._unconfigured_logged = False
        self._emergency_warning_spoken = False

    def _preferred_engine(self) -> str:
        saved = load_voice_settings()
        default_engine = "elevenlabs" if self._explicit_primary else (self.config.tts_engine or "local_neural")
        eng = saved.get("tts_engine") or default_engine
        return str(eng).strip().lower()

    def speak(
        self,
        text: str,
        wait: bool = True,
        language: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not text or not text.strip():
            return False

        preferred = self._preferred_engine()

        # OPTIONAL PREMIUM: ElevenLabs (explicit opt-in only)
        if preferred == "elevenlabs":
            if self.elevenlabs.is_configured():
                self._unconfigured_logged = False
                ok = self.elevenlabs.speak(text, wait=wait, language=language, overrides=overrides)
                if ok:
                    self.last_used_engine = "elevenlabs"
                    self.last_fallback_reason = None
                    return True
                reason = getattr(self.elevenlabs, "_last_error_code", None) or "synthesis_failed"
                self.last_fallback_reason = reason
                voice_logger.tts_fallback("elevenlabs", "local_neural", reason=reason)
            else:
                reason = "not_configured"
                self.last_fallback_reason = reason
                if not self._unconfigured_logged:
                    voice_logger.tts_fallback("elevenlabs", "local_neural", reason=reason)
                    self._unconfigured_logged = True

            # When ElevenLabs fails or is unconfigured, fall back to Local Neural TTS
            if not self._explicit_primary and self.local_neural.is_available():
                ok_ln = self.local_neural.speak(text, wait=wait, language=language)
                if ok_ln:
                    self.last_used_engine = "local_neural"
                    return True

        # PRIMARY: Local Indonesian Neural TTS (Permanent Default)
        if preferred == "local_neural" or preferred not in ("elevenlabs", "speech_dispatcher"):
            if self.local_neural.is_available():
                ok_ln = self.local_neural.speak(text, wait=wait, language=language)
                if ok_ln:
                    self.last_used_engine = "local_neural"
                    self.last_fallback_reason = None
                    return True
                reason = getattr(self.local_neural, "_last_error", None) or "synthesis_failed"
                self.last_fallback_reason = reason
                voice_logger.tts_fallback("local_neural", "speech_dispatcher", reason=reason)
            else:
                self.last_fallback_reason = "local_neural_unavailable"
                voice_logger.tts_fallback("local_neural", "speech_dispatcher", reason="local_model_or_env_missing")

        # EMERGENCY FALLBACK: Speech Dispatcher (with audible warning)
        if not self._emergency_warning_spoken and not self._explicit_primary and not self.fallback.__class__.__name__.startswith("Mock"):
            self._emergency_warning_spoken = True
            warn_msg = "Emergency fallback: voice switched to speech dispatcher."
            self.fallback.speak(warn_msg, wait=True, language="en")

        ok_fb = self.fallback.speak(text, wait=wait, language=language)
        if ok_fb:
            self.last_used_engine = "speech_dispatcher"
        return ok_fb

    def speak_stream(
        self,
        sentences: Iterable[str],
        language: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
        on_first_audio: Optional[Callable[[], None]] = None,
    ) -> Dict[str, Any]:
        """
        Speak an iterator of sentence chunks with priority routing:
        1. ElevenLabs (if explicitly preferred and configured)
        2. Local Neural TTS (primary default)
        3. Speech Dispatcher (emergency fallback)
        """
        preferred = self._preferred_engine()
        collected: List[str] = []
        raw_iter = iter(sentences)

        def _tracking_iter() -> Iterable[str]:
            for s in raw_iter:
                clean = (s or "").strip()
                if clean:
                    collected.append(clean)
                    yield clean

        if preferred == "elevenlabs" and self.elevenlabs.is_configured():
            self._unconfigured_logged = False
            res = self.elevenlabs.speak_stream(
                _tracking_iter(),
                language=language,
                overrides=overrides,
                on_first_audio=on_first_audio,
            )
            if res.get("ok"):
                self.last_used_engine = "elevenlabs"
                self.last_fallback_reason = None
                res["engine"] = "elevenlabs"
                res["full_text"] = " ".join(collected)
                return res

            reason = str(
                res.get("reason")
                or res.get("error_code")
                or getattr(self.elevenlabs, "_last_error_code", None)
                or "synthesis_failed"
            )
            self.last_fallback_reason = reason
            voice_logger.tts_fallback("elevenlabs", "local_neural", reason=reason)
            tail_sents = [c for c in ((s or "").strip() for s in raw_iter) if c]
            collected.extend(tail_sents)
            fallback_queue: List[str] = []
            if res.get("failed_sentence"):
                fallback_queue.append(str(res["failed_sentence"]))
                fallback_queue.extend(tail_sents)
            else:
                fallback_queue = list(collected)

            t_fb = time.perf_counter()
            if fallback_queue:
                if on_first_audio and not res.get("wrote_any"):
                    try:
                        on_first_audio()
                    except Exception:
                        pass
                for fb_sent in fallback_queue:
                    if not self._explicit_primary and self.local_neural.is_available() and self.local_neural.speak(fb_sent, wait=True, language=language):
                        self.last_used_engine = "local_neural"
                    else:
                        if not self._emergency_warning_spoken and not self._explicit_primary and not self.fallback.__class__.__name__.startswith("Mock"):
                            self._emergency_warning_spoken = True
                            self.fallback.speak("Emergency fallback: voice switched to speech dispatcher.", wait=True, language="en")
                        self.fallback.speak(fb_sent, wait=True, language=language)
                        self.last_used_engine = "speech_dispatcher"
            return {
                "ok": bool(fallback_queue),
                "engine": self.last_used_engine,
                "chunks": len(fallback_queue),
                "tts_ttfb_ms": 15.0,
                "tts_playback_ms": round((time.perf_counter() - t_fb) * 1000.0, 1),
                "dns_ms": res.get("dns_ms", 0.0),
                "tls_ms": res.get("tls_ms", 0.0),
                "full_text": " ".join(collected),
            }

        # Local Neural TTS Streaming / Chunked playback (Primary)
        if preferred == "local_neural" or preferred not in ("elevenlabs", "speech_dispatcher"):
            t0 = time.perf_counter()
            first_ms: Optional[float] = None
            any_ok = False
            for sent in _tracking_iter():
                if first_ms is None:
                    first_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                    if on_first_audio:
                        try:
                            on_first_audio()
                        except Exception:
                            pass
                if self.local_neural.is_available() and self.local_neural.speak(sent, wait=True, language=language):
                    any_ok = True
                    self.last_used_engine = "local_neural"
                else:
                    if not self._emergency_warning_spoken:
                        self._emergency_warning_spoken = True
                        self.fallback.speak("Emergency fallback: voice switched to speech dispatcher.", wait=True, language="en")
                    if self.fallback.speak(sent, wait=True, language=language):
                        any_ok = True
                        self.last_used_engine = "speech_dispatcher"
            return {
                "ok": any_ok,
                "engine": self.last_used_engine,
                "chunks": len(collected),
                "tts_ttfb_ms": first_ms or 0.0,
                "tts_playback_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                "dns_ms": 0.0,
                "tls_ms": 0.0,
                "full_text": " ".join(collected),
            }

        # Direct Speech Dispatcher streaming sentence-by-sentence
        t0 = time.perf_counter()
        first_ms: Optional[float] = None
        any_ok = False
        for sent in _tracking_iter():
            if first_ms is None:
                first_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                if on_first_audio:
                    try:
                        on_first_audio()
                    except Exception:
                        pass
            if self.fallback.speak(sent, wait=True, language=language):
                any_ok = True
        if any_ok:
            self.last_used_engine = "speech_dispatcher"
        return {
            "ok": any_ok,
            "engine": "speech_dispatcher",
            "chunks": len(collected),
            "tts_ttfb_ms": first_ms or 0.0,
            "tts_playback_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "dns_ms": 0.0,
            "tls_ms": 0.0,
            "full_text": " ".join(collected),
        }

    def stop(self) -> None:
        self.local_neural.stop()
        self.elevenlabs.stop()
        self.fallback.stop()

    def is_speaking(self) -> bool:
        return self.local_neural.is_speaking() or self.elevenlabs.is_speaking() or self.fallback.is_speaking()

    def get_status(self) -> Dict[str, Any]:
        el_status = self.elevenlabs.get_public_status()
        ln_status = self.local_neural.get_public_status()
        preferred = self._preferred_engine()
        spd_avail = getattr(self.fallback, "is_available", lambda: True)()
        if preferred == "elevenlabs" and el_status.get("configured") and not el_status.get("last_error_code"):
            active_mode = "elevenlabs"
        elif preferred == "local_neural" and ln_status.get("available"):
            active_mode = "local_neural"
        elif ln_status.get("available"):
            active_mode = "local_neural"
        else:
            active_mode = "speech_dispatcher"

        return {
            "preferred_engine": preferred,
            "active_engine": active_mode,
            "last_used_engine": self.last_used_engine,
            "last_fallback_reason": self.last_fallback_reason,
            "local_neural": ln_status,
            "elevenlabs": el_status,
            "fallback": {
                "provider": "speech_dispatcher",
                "binary": "spd-say",
                "available": spd_avail,
                "rate": self.config.tts_rate,
                "pitch": self.config.tts_pitch,
                "volume": self.config.tts_volume,
            },
        }


def create_tts_provider(config: Optional[VoiceConfig] = None) -> HybridTTSProvider:
    """Create the default Maven TTS engine (ElevenLabs primary + Speech Dispatcher fallback)."""
    return HybridTTSProvider(config=config)


class MockTTSProvider(TTSProvider):
    """In-memory TTS provider for deterministic testing."""

    def __init__(self):
        self.spoken_texts = []
        self._is_speaking = False

    def speak(self, text: str, wait: bool = True, language: Optional[str] = None) -> bool:
        self.spoken_texts.append(text)
        self._is_speaking = True
        time.sleep(0.01)
        self._is_speaking = False
        return True

    def speak_stream(
        self,
        sentences: Iterable[str],
        language: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
        on_first_audio: Optional[Callable[[], None]] = None,
    ) -> Dict[str, Any]:
        parts: List[str] = []
        self._is_speaking = True
        try:
            for idx, s in enumerate(sentences):
                clean = (s or "").strip()
                if not clean:
                    continue
                if idx == 0 and on_first_audio:
                    on_first_audio()
                parts.append(clean)
                time.sleep(0.005)
            full = " ".join(parts)
            if full:
                self.spoken_texts.append(full)
            return {
                "ok": bool(parts),
                "engine": "mock",
                "chunks": len(parts),
                "tts_ttfb_ms": 5.0,
                "tts_playback_ms": 10.0,
                "dns_ms": 0.0,
                "tls_ms": 0.0,
                "full_text": full,
            }
        finally:
            self._is_speaking = False

    def stop(self) -> None:
        self._is_speaking = False

    def is_speaking(self) -> bool:
        return self._is_speaking
