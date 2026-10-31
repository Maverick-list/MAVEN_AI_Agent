"""
Maverick DevOS - Local Neural TTS Provider (Pocket TTS Indonesian).

Provides 100% offline, natural-sounding Indonesian neural voice synthesis
on standard Linux CPU without cloud credits, paid APIs, or external internet access.
Based on Kyutai Pocket-TTS architecture distilled with 502 hours LEMAS dataset.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional

from maverick.voice.audio import AudioPlayer
from maverick.voice.config import VoiceConfig, load_voice_settings
from maverick.voice.observability import voice_logger
from maverick.voice.text_normalization import normalize_voice_text

DEFAULT_MODEL_DIR = os.path.expanduser("~/.local/share/maverick/models/tts/pocket-tts-indonesian")
DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_MODEL_DIR, "indonesian_6l_local.yaml")
DEFAULT_VOICE_NAME = "common_voice_id_19961910"  # Calm, balanced voice preset
DEFAULT_VENV_PYTHON = os.path.expanduser("~/.local/share/maverick/tts-env/bin/python")


class LocalNeuralTTSProvider:
    """
    Local Neural Indonesian Text-to-Speech Provider using Pocket-TTS.
    Runs locally on CPU, verified 100% offline with zero cloud dependency.
    """

    def __init__(
        self,
        config: Optional[VoiceConfig] = None,
        model_dir: Optional[str] = None,
        config_path: Optional[str] = None,
        voice_name: Optional[str] = None,
        venv_python: Optional[str] = None,
    ):
        self.config = config or VoiceConfig()
        self.model_dir = model_dir or getattr(self.config, "local_neural_model_dir", DEFAULT_MODEL_DIR)
        self.config_path = config_path or os.path.join(self.model_dir, "indonesian_6l_local.yaml")
        if not os.path.isfile(self.config_path):
            fallback_cfg = os.path.join(self.model_dir, "indonesian_6l.yaml")
            if os.path.isfile(fallback_cfg):
                self.config_path = fallback_cfg

        self.voice_name = voice_name or getattr(self.config, "local_neural_voice", DEFAULT_VOICE_NAME)
        self.venv_python = venv_python or getattr(self.config, "local_neural_venv_python", DEFAULT_VENV_PYTHON)
        self.player = AudioPlayer(self.config)

        self._lock = threading.Lock()
        self._is_speaking = False
        self._model = None
        self._voice_state = None
        self._last_metrics: Dict[str, Any] = {}
        self._last_error: Optional[str] = None

    def get_voice_prompt_path(self, voice_name: Optional[str] = None) -> str:
        """Resolve absolute path to reference audio prompt file."""
        target = voice_name or self.voice_name
        voices_dir = os.path.join(self.model_dir, "voices")
        candidates = [
            os.path.join(voices_dir, f"{target}.mp3"),
            os.path.join(voices_dir, f"{target}.wav"),
            os.path.join(voices_dir, f"{target}.safetensors"),
            os.path.join(self.model_dir, f"{target}.mp3"),
            os.path.join(self.model_dir, f"{target}.wav"),
            target,
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        # Default fallback to first voice found in voices/
        if os.path.isdir(voices_dir):
            files = sorted(os.listdir(voices_dir))
            for f in files:
                if f.endswith((".mp3", ".wav", ".safetensors")):
                    return os.path.join(voices_dir, f)
        return os.path.join(voices_dir, f"{DEFAULT_VOICE_NAME}.mp3")

    def is_available(self) -> bool:
        """Verify that model files and runtime environment are locally present and installed."""
        weights = os.path.join(self.model_dir, "6l", "model.safetensors")
        tokenizer = os.path.join(self.model_dir, "tokenizer.model")
        has_files = os.path.isfile(weights) and os.path.isfile(tokenizer)
        if not has_files:
            return False

        if self._can_import_in_process():
            return True

        if os.path.isfile(self.venv_python):
            venv_lib = os.path.join(os.path.dirname(os.path.dirname(self.venv_python)), "lib")
            if os.path.isdir(venv_lib):
                for root, dirs, _ in os.walk(venv_lib):
                    if "pocket_tts" in dirs:
                        return True
        return False

    def _can_import_in_process(self) -> bool:
        try:
            import pocket_tts  # noqa: F401
            return True
        except ImportError:
            # Check if tts-env site-packages can be added to sys.path
            tts_site = os.path.expanduser("~/.local/share/maverick/tts-env/lib/python3.14/site-packages")
            if os.path.isdir(tts_site) and tts_site not in sys.path:
                sys.path.insert(0, tts_site)
                try:
                    import pocket_tts  # noqa: F401
                    return True
                except ImportError:
                    pass
            return False

    def is_speaking(self) -> bool:
        return self._is_speaking

    def stop(self) -> None:
        """Interrupt and stop current speech playback immediately."""
        with self._lock:
            self._is_speaking = False
            self.player.stop()

    def synthesize_to_wav(
        self,
        text: str,
        output_wav_path: str,
        voice_name: Optional[str] = None,
        temperature: float = 0.3,
        eos_threshold: float = -6.0,
    ) -> Dict[str, Any]:
        """
        Synthesize speech for given text into a WAV file using Pocket-TTS Indonesian.
        Returns execution metrics (latency_ms, duration_ms, rtf).
        """
        if not text or not text.strip():
            return {"ok": False, "error": "empty_text"}

        normalized_text = normalize_voice_text(text)
        voice_prompt = self.get_voice_prompt_path(voice_name)
        if not os.path.isfile(voice_prompt):
            return {"ok": False, "error": f"voice_prompt_not_found: {voice_prompt}"}

        t_start = time.perf_counter()

        # Execute isolated synthesis script via venv python
        os.makedirs(os.path.dirname(os.path.abspath(output_wav_path)), exist_ok=True)

        synth_script = f"""
import os
import sys
import time

# Enforce strict offline operation
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import scipy.io.wavfile
from pocket_tts import TTSModel

config_path = {repr(self.config_path)}
voice_prompt = {repr(voice_prompt)}
output_path = {repr(output_wav_path)}
text = {repr(normalized_text)}
temp = {float(temperature)}
eos_thresh = {float(eos_threshold)}

t0 = time.perf_counter()
model = TTSModel.load_model(config=config_path, temp=temp, eos_threshold=eos_thresh)
t_load = time.perf_counter() - t0

t1 = time.perf_counter()
voice_state = model.get_state_for_audio_prompt(voice_prompt)
t_voice = time.perf_counter() - t1

t2 = time.perf_counter()
audio = model.generate_audio(voice_state, text)
t_gen = time.perf_counter() - t2

# Write 24kHz audio to WAV
audio_np = audio.numpy()
scipy.io.wavfile.write(output_path, model.sample_rate, audio_np)

duration_sec = len(audio_np) / float(model.sample_rate)
rtf = t_gen / duration_sec if duration_sec > 0 else 0.0

print(f"SUCCESS|load={{t_load:.3f}}|voice={{t_voice:.3f}}|gen={{t_gen:.3f}}|dur={{duration_sec:.3f}}|rtf={{rtf:.3f}}")
"""
        cmd = [self.venv_python, "-c", synth_script]
        env = dict(os.environ)
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=45.0,
                env=env,
            )
            elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 1)

            if proc.returncode != 0:
                err_msg = proc.stderr.strip() or f"exit code {proc.returncode}"
                self._last_error = err_msg
                return {
                    "ok": False,
                    "error": err_msg,
                    "stdout": proc.stdout,
                    "elapsed_ms": elapsed_ms,
                }

            # Parse stdout
            meta: Dict[str, Any] = {"ok": True, "elapsed_ms": elapsed_ms, "output_path": output_wav_path}
            for line in proc.stdout.splitlines():
                if line.startswith("SUCCESS|"):
                    parts = line.split("|")[1:]
                    for p in parts:
                        if "=" in p:
                            k, v = p.split("=", 1)
                            try:
                                meta[k] = float(v)
                            except ValueError:
                                meta[k] = v

            meta["normalized_text"] = normalized_text
            self._last_metrics = meta
            self._last_error = None
            return meta

        except subprocess.TimeoutExpired:
            self._last_error = "synthesis_timeout"
            return {"ok": False, "error": "synthesis_timeout"}
        except Exception as e:
            self._last_error = str(e)
            return {"ok": False, "error": str(e)}

    def speak(self, text: str, wait: bool = True, language: Optional[str] = None) -> bool:
        """Synthesize and play speech through local audio output."""
        if not text or not text.strip():
            return False

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav = tmp.name

        try:
            res = self.synthesize_to_wav(text, tmp_wav)
            if not res.get("ok") or not os.path.isfile(tmp_wav):
                if os.path.exists(tmp_wav):
                    os.unlink(tmp_wav)
                return False

            with self._lock:
                self._is_speaking = True

            ok_play = self.player.play_wav(tmp_wav, wait=wait)
            return ok_play
        except Exception as exc:
            self._last_error = str(exc)
            return False
        finally:
            with self._lock:
                self._is_speaking = False
            if os.path.exists(tmp_wav):
                try:
                    os.unlink(tmp_wav)
                except OSError:
                    pass

    def get_public_status(self) -> Dict[str, Any]:
        """Return non-sensitive public operational status for Control Center Dashboard."""
        return {
            "engine": "local_neural",
            "model_name": "pocket-tts-indonesian-6l",
            "model_architecture": "CALM + Mimi 24kHz",
            "license": "CC-BY-4.0",
            "available": self.is_available(),
            "config_path": self.config_path,
            "voice_name": self.voice_name,
            "offline_ready": True,
            "last_error": self._last_error,
            "last_metrics": self._last_metrics,
        }
