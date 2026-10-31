"""Maverick DevOS - Local Audio Capture & Playback Subsystem."""

import os
import re
import shutil
import signal
import subprocess
import threading
import time
import wave
from typing import Any, Dict, List, Optional
import numpy as np

from maverick.voice.config import VoiceConfig


def calculate_rms(audio_bytes: bytes) -> float:
    """
    Calculate normalized Root Mean Square (RMS) energy (0.0 to 1.0)
    from 16-bit signed PCM audio bytes.
    """
    if not audio_bytes or len(audio_bytes) < 2:
        return 0.0

    try:
        # 16-bit signed integer values range from -32768 to 32767
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if len(samples) == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(samples ** 2)))
        return min(1.0, max(0.0, rms))
    except Exception:
        return 0.0


def list_audio_devices() -> Dict[str, Any]:
    """
    Detect available microphones and speakers via PipeWire (wpctl) and ALSA (arecord/aplay).
    Returns structured device metadata and availability flags.
    """
    inputs: List[Dict[str, Any]] = []
    outputs: List[Dict[str, Any]] = []
    default_input: Optional[str] = None
    default_output: Optional[str] = None

    # 1. Parse wpctl status if available (PipeWire / WirePlumber)
    wpctl_bin = shutil.which("wpctl")
    if wpctl_bin:
        try:
            res = subprocess.run(
                [wpctl_bin, "status"],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if res.returncode == 0:
                current_section = None
                for line in res.stdout.splitlines():
                    trimmed = line.strip()
                    if "Video" in line or "Settings" in line:
                        break
                    elif "Sinks:" in line:
                        current_section = "sinks"
                        continue
                    elif "Sources:" in line:
                        current_section = "sources"
                        continue
                    elif "Filters:" in line or "Streams:" in line:
                        current_section = None
                        continue

                    if current_section == "sinks" and trimmed:
                        is_default = "*" in line
                        name = re.sub(r"^[│\s\*\.\d]+", "", trimmed).split("[")[0].strip()
                        if name:
                            outputs.append({"name": name, "is_default": is_default, "system": "pipewire"})
                            if is_default:
                                default_output = name
                    elif current_section == "sources" and trimmed:
                        is_default = "*" in line
                        name = re.sub(r"^[│\s\*\.\d]+", "", trimmed).split("[")[0].strip()
                        if name:
                            inputs.append({"name": name, "is_default": is_default, "system": "pipewire"})
                            if is_default:
                                default_input = name
        except Exception:
            pass

    # 2. ALSA Fallback discovery
    if not inputs and shutil.which("arecord"):
        try:
            res = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    if line.startswith("card "):
                        inputs.append({"name": line.strip(), "is_default": True, "system": "alsa"})
                        default_input = line.strip()
        except Exception:
            pass

    if not outputs and shutil.which("aplay"):
        try:
            res = subprocess.run(["aplay", "-l"], capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    if line.startswith("card "):
                        outputs.append({"name": line.strip(), "is_default": True, "system": "alsa"})
                        default_output = line.strip()
        except Exception:
            pass

    return {
        "status": "success",
        "has_microphone": len(inputs) > 0,
        "has_speaker": len(outputs) > 0,
        "default_input": default_input or ("Default Microphone" if inputs else None),
        "default_output": default_output or ("Default Speaker" if outputs else None),
        "inputs": inputs,
        "outputs": outputs,
    }


class AudioCapture:
    """
    Streams audio frames from the default PipeWire/ALSA microphone
    using non-blocking raw PCM capture.
    """

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or VoiceConfig()
        self._proc: Optional[subprocess.Popen] = None
        self._is_capturing = False
        self._muted = self.config.muted
        self._lock = threading.Lock()

    @property
    def is_muted(self) -> bool:
        return self._muted

    def set_muted(self, muted: bool) -> None:
        with self._lock:
            self._muted = muted

    def start(self) -> bool:
        """Start streaming microphone input."""
        with self._lock:
            return self._start_capture_unlocked()

    def _start_capture_unlocked(self) -> bool:
        """Internal start helper without locking."""
        if self._is_capturing and self._proc and self._proc.poll() is None:
            return True

        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None

        # Prefer arecord or pw-record
        backend = shutil.which("arecord")
        if not backend:
            backend = shutil.which("pw-record")

        if not backend:
            self._is_capturing = False
            return False

        cmd = [
            backend,
            "-q",
            "-f", "S16_LE",
            "-r", str(self.config.sample_rate),
            "-c", str(self.config.channels),
            "-t", "raw",
        ]

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=self.config.chunk_size * 4,
            )
            self._is_capturing = True
            return True
        except Exception:
            self._is_capturing = False
            self._proc = None
            return False

    def flush(self) -> None:
        """Discard any stale unread audio buffered in the OS pipe (e.g. after TTS playback)."""
        with self._lock:
            if not self._is_capturing or not self._proc or not self._proc.stdout:
                return
            try:
                import fcntl
                fd = self._proc.stdout.fileno()
                flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                try:
                    while True:
                        buf = os.read(fd, 65536)
                        if not buf:
                            break
                except (BlockingIOError, InterruptedError):
                    pass
                finally:
                    fcntl.fcntl(fd, fcntl.F_SETFL, flags)
            except Exception:
                pass

    def read_chunk(self, chunk_size: Optional[int] = None) -> bytes:
        """
        Read one frame chunk of audio bytes (default 1024 samples = 2048 bytes).
        Returns empty bytes on EOF or error. Automatically recovers from dead process.
        """
        with self._lock:
            if not self._is_capturing or not self._proc or self._proc.poll() is not None:
                if self._is_capturing:
                    self._start_capture_unlocked()
                if not self._proc or not self._proc.stdout:
                    return b""

        samples = chunk_size or self.config.chunk_size
        bytes_to_read = samples * self.config.sample_width_bytes * self.config.channels

        if self._muted:
            # Emits silence frame when muted without querying microphone
            time.sleep(samples / self.config.sample_rate)
            return b"\x00" * bytes_to_read

        try:
            data = self._proc.stdout.read(bytes_to_read)
            if not data:
                with self._lock:
                    if self._is_capturing:
                        self._start_capture_unlocked()
                return b""
            return data
        except Exception:
            return b""

    def stop(self) -> None:
        """Safely stop microphone capture and clean up subprocess."""
        with self._lock:
            self._is_capturing = False
            if self._proc:
                try:
                    if self._proc.stdout:
                        self._proc.stdout.close()
                    self._proc.terminate()
                    self._proc.wait(timeout=1.0)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                finally:
                    self._proc = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class AudioPlayer:
    """Plays audio prompts and synthesized speech through PipeWire / ALSA with dynamic timeout and sink failover."""

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or VoiceConfig()
        self._current_proc: Optional[subprocess.Popen] = None
        self._interrupted = False
        self._lock = threading.Lock()

    @staticmethod
    def estimate_wav_duration_seconds(wav_path: str) -> float:
        """Read WAV header to compute exact duration in seconds, falling back to file-size estimate."""
        try:
            with wave.open(wav_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate() or 24000
                return max(0.1, float(frames) / float(rate))
        except Exception:
            try:
                size_bytes = os.path.getsize(wav_path)
                # Conservative 24kHz 16-bit mono = 48,000 bytes/sec
                return max(0.5, float(size_bytes) / 48000.0)
            except OSError:
                return 10.0

    def _build_player_commands(self, wav_path: str) -> List[List[str]]:
        cmds: List[List[str]] = []
        pw_play = shutil.which("pw-play")
        aplay = shutil.which("aplay")
        if pw_play:
            cmds.append([pw_play, wav_path])
        if aplay:
            cmds.append([aplay, "-q", wav_path])
        return cmds

    def play_wav(self, wav_path: str, wait: bool = True) -> bool:
        """Play a WAV file using PipeWire (pw-play) or ALSA (aplay) with dynamic duration timeout and failover."""
        if not os.path.isfile(wav_path):
            return False

        commands = self._build_player_commands(wav_path)
        if not commands:
            return False

        self.stop()
        with self._lock:
            self._interrupted = False

        est_duration = self.estimate_wav_duration_seconds(wav_path)
        wait_timeout = max(30.0, est_duration + 15.0)

        for cmd in commands:
            with self._lock:
                if self._interrupted:
                    return False
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                with self._lock:
                    self._current_proc = proc

                if not wait:
                    return True

                proc.wait(timeout=wait_timeout)
                with self._lock:
                    was_interrupted = self._interrupted
                if was_interrupted:
                    return True
                if proc.returncode == 0:
                    return True
            except subprocess.TimeoutExpired:
                self.stop()
            except Exception:
                continue

        return False

    def stop(self) -> None:
        """Interrupt and terminate active audio playback immediately."""
        with self._lock:
            self._interrupted = True
            if self._current_proc and self._current_proc.poll() is None:
                try:
                    self._current_proc.terminate()
                    self._current_proc.wait(timeout=0.5)
                except Exception:
                    try:
                        self._current_proc.kill()
                    except Exception:
                        pass
                finally:
                    self._current_proc = None
