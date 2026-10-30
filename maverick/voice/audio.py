"""Maverick DevOS - Local Audio Capture & Playback Subsystem."""

import os
import re
import shutil
import signal
import subprocess
import threading
import time
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
            if self._is_capturing and self._proc and self._proc.poll() is None:
                return True

            # Prefer arecord or pw-record
            backend = shutil.which("arecord")
            if not backend:
                backend = shutil.which("pw-record")

            if not backend:
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

    def read_chunk(self, chunk_size: Optional[int] = None) -> bytes:
        """
        Read one frame chunk of audio bytes (default 1024 samples = 2048 bytes).
        Returns empty bytes on EOF or error.
        """
        if not self._is_capturing or not self._proc or not self._proc.stdout:
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
    """Plays audio prompts and sound effects through PipeWire / ALSA."""

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or VoiceConfig()
        self._current_proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def play_wav(self, wav_path: str, wait: bool = True) -> bool:
        """Play a WAV file using aplay or pw-play."""
        if not os.path.isfile(wav_path):
            return False

        player = shutil.which("aplay") or shutil.which("pw-play")
        if not player:
            return False

        self.stop()

        try:
            proc = subprocess.Popen(
                [player, "-q", wav_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with self._lock:
                self._current_proc = proc

            if wait:
                proc.wait(timeout=10.0)
                return proc.returncode == 0
            return True
        except Exception:
            return False

    def stop(self) -> None:
        """Interrupt and terminate active audio playback."""
        with self._lock:
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
