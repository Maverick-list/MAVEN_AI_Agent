"""Maverick DevOS - Local Text-to-Speech (TTS) Provider."""

from abc import ABC, abstractmethod
import os
import shutil
import subprocess
import threading
import time
from typing import Optional

from maverick.voice.config import VoiceConfig


class TTSProvider(ABC):
    """Abstract interface for speech synthesis engines."""

    @abstractmethod
    def speak(self, text: str, wait: bool = True) -> bool:
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
    Provides low-latency, zero-cost, offline voice feedback.
    """

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or VoiceConfig()
        self._current_proc: Optional[subprocess.Popen] = None
        self._is_speaking = False
        self._lock = threading.Lock()

    def is_speaking(self) -> bool:
        with self._lock:
            if self._current_proc and self._current_proc.poll() is None:
                return True
            return self._is_speaking

    def speak(self, text: str, wait: bool = True) -> bool:
        """
        Synthesize text using spd-say.
        Supports cancellation and interruption.
        """
        if not text or not text.strip():
            return False

        bin_path = shutil.which("spd-say")
        if not bin_path:
            return False

        # Stop previous utterance before speaking new text
        self.stop()

        clean_text = text.strip()
        cmd = [
            bin_path,
            "-l", "en",
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


class MockTTSProvider(TTSProvider):
    """In-memory TTS provider for deterministic testing."""

    def __init__(self):
        self.spoken_texts = []
        self._is_speaking = False

    def speak(self, text: str, wait: bool = True) -> bool:
        self.spoken_texts.append(text)
        self._is_speaking = True
        time.sleep(0.01)
        self._is_speaking = False
        return True

    def stop(self) -> None:
        self._is_speaking = False

    def is_speaking(self) -> bool:
        return self._is_speaking
