"""Maverick DevOS - Text-to-Speech (TTS) Providers & Automatic Fallback Router."""

from abc import ABC, abstractmethod
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, Optional

from maverick.voice.config import VoiceConfig, load_voice_settings
from maverick.voice.elevenlabs_tts import ElevenLabsTTSProvider
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
    Primary ElevenLabs neural TTS with automatic, zero-downtime fallback
    to local SpeechDispatcherTTS (spd-say / espeak-ng).
    """

    def __init__(
        self,
        config: Optional[VoiceConfig] = None,
        primary: Optional[ElevenLabsTTSProvider] = None,
        fallback: Optional[SpeechDispatcherTTS] = None,
    ):
        self.config = config or VoiceConfig()
        self.primary = primary or ElevenLabsTTSProvider(self.config)
        self.fallback = fallback or SpeechDispatcherTTS(self.config)
        self.last_used_engine: str = "none"
        self.last_fallback_reason: Optional[str] = None
        self._unconfigured_logged = False

    def _preferred_engine(self) -> str:
        saved = load_voice_settings()
        eng = saved.get("tts_engine") or self.config.tts_engine or "elevenlabs"
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
        if preferred == "elevenlabs":
            if self.primary.is_configured():
                self._unconfigured_logged = False
                ok = self.primary.speak(text, wait=wait, language=language, overrides=overrides)
                if ok:
                    self.last_used_engine = "elevenlabs"
                    self.last_fallback_reason = None
                    return True
                reason = self.primary._last_error_code or "synthesis_failed"
                self.last_fallback_reason = reason
                voice_logger.tts_fallback("elevenlabs", "speech_dispatcher", reason=reason)
            else:
                _, code, _ = self.primary.get_public_status()["configured"], self.primary.get_public_status()["key_status"], ""
                self.last_fallback_reason = code
                if not self._unconfigured_logged:
                    voice_logger.tts_fallback("elevenlabs", "speech_dispatcher", reason=code)
                    self._unconfigured_logged = True

        ok_fb = self.fallback.speak(text, wait=wait, language=language)
        if ok_fb:
            self.last_used_engine = "speech_dispatcher"
        return ok_fb

    def stop(self) -> None:
        self.primary.stop()
        self.fallback.stop()

    def is_speaking(self) -> bool:
        return self.primary.is_speaking() or self.fallback.is_speaking()

    def get_status(self) -> Dict[str, Any]:
        el_status = self.primary.get_public_status()
        preferred = self._preferred_engine()
        spd_avail = self.fallback.is_available()
        active_mode = (
            "elevenlabs"
            if (preferred == "elevenlabs" and el_status["configured"] and not el_status["last_error_code"])
            else "speech_dispatcher"
        )
        return {
            "preferred_engine": preferred,
            "active_engine": active_mode,
            "last_used_engine": self.last_used_engine,
            "last_fallback_reason": self.last_fallback_reason,
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

    def stop(self) -> None:
        self._is_speaking = False

    def is_speaking(self) -> bool:
        return self._is_speaking
