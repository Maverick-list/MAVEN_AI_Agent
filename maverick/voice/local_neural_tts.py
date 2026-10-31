"""
Maverick DevOS - Permanent Local Neural TTS Provider (Primary English Male + Optional Indonesian).

Architecture:
- Primary Default: Kyutai Pocket-TTS English 6L (CC-BY-4.0), male voice 'george' (24 kHz Mimi neural codec).
- Optional Secondary: Pocket-TTS Indonesian 6L (CC-BY-4.0) when Indonesian speech is explicitly requested.
- Warm Persistent Worker: Keeps model weights & precomputed .safetensors voice states resident in an
  isolated offline worker subprocess (HF_HUB_OFFLINE=1), delivering ~140-200ms TTFB and RTF ~0.33 on CPU
  with automatic crash recovery and zero cloud/API dependency.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from maverick.voice.audio import AudioPlayer
from maverick.voice.config import (
    DEFAULT_LOCAL_NEURAL_INDONESIAN_MODEL_DIR,
    DEFAULT_LOCAL_NEURAL_INDONESIAN_VOICE,
    DEFAULT_LOCAL_NEURAL_MODEL_DIR,
    DEFAULT_LOCAL_NEURAL_VOICE,
    LOCAL_NEURAL_VOICE_CATALOG,
    VoiceConfig,
    load_voice_settings,
)
from maverick.voice.text_normalization import (
    normalize_english_voice_text,
    normalize_voice_text,
)

DEFAULT_MODEL_DIR = DEFAULT_LOCAL_NEURAL_MODEL_DIR
DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_MODEL_DIR, "english_local.yaml")
DEFAULT_VOICE_NAME = DEFAULT_LOCAL_NEURAL_VOICE
DEFAULT_VENV_PYTHON = os.path.expanduser("~/.local/share/maverick/tts-env/bin/python")


_PERSISTENT_WORKER_CODE = r"""
import json
import os
import resource
import sys
import time
import wave
import numpy as np

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"


from pocket_tts import TTSModel

models_cache = {}
voice_cache = {}

def get_model(config_path, temp, eos_threshold):
    key = (config_path, round(float(temp), 3), round(float(eos_threshold), 3))
    if key in models_cache:
        return models_cache[key], 0.0
    t0 = time.perf_counter()
    m = TTSModel.load_model(config=config_path, temp=float(temp), eos_threshold=float(eos_threshold))
    dt = time.perf_counter() - t0
    models_cache[key] = m
    return m, dt

def get_voice(model, config_path, voice_prompt):
    key = (config_path, voice_prompt)
    if key in voice_cache:
        return voice_cache[key], 0.0
    t0 = time.perf_counter()
    vs = model.get_state_for_audio_prompt(voice_prompt)
    dt = time.perf_counter() - t0
    voice_cache[key] = vs
    return vs, dt

sys.stdout.write(json.dumps({"ready": True}) + "\n")
sys.stdout.flush()

for raw_line in sys.stdin:
    line = raw_line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        if req.get("cmd") == "ping":
            sys.stdout.write(json.dumps({"ok": True, "pong": True}) + "\n")
            sys.stdout.flush()
            continue
        if req.get("cmd") == "quit":
            break

        config_path = req["config_path"]
        voice_prompt = req["voice_prompt"]
        output_path = req["output_path"]
        text = req["text"]
        temp = float(req.get("temperature", 0.45))
        eos_thresh = float(req.get("eos_threshold", -4.0))

        model, t_load = get_model(config_path, temp, eos_thresh)
        voice_state, t_voice = get_voice(model, config_path, voice_prompt)

        t_gen_start = time.perf_counter()
        ttfb_sec = None
        chunks = []
        for chunk in model.generate_audio_stream(voice_state, text):
            if ttfb_sec is None:
                ttfb_sec = time.perf_counter() - t_gen_start
            chunks.append(chunk.detach().cpu().numpy())
        t_gen = time.perf_counter() - t_gen_start
        if ttfb_sec is None:
            ttfb_sec = t_gen

        if chunks:
            audio_np = np.concatenate(chunks, axis=0).astype(np.float32)
        else:
            audio_np = np.zeros(int(model.sample_rate * 0.1), dtype=np.float32)

        peak = float(np.max(np.abs(audio_np))) if len(audio_np) > 0 else 0.0
        if 0.01 < peak < 0.80:
            audio_np = audio_np * (0.85 / peak)
        audio_np = np.clip(audio_np, -1.0, 1.0)
        pcm16 = (audio_np * 32767.0).astype(np.int16)

        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(int(model.sample_rate))
            wf.writeframes(pcm16.tobytes())

        duration_sec = float(len(pcm16)) / float(model.sample_rate)
        rtf = t_gen / duration_sec if duration_sec > 0 else 0.0
        rms = float(np.sqrt(np.mean(audio_np ** 2))) if len(audio_np) > 0 else 0.0
        rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

        resp = {
            "ok": True,
            "load": round(t_load, 4),
            "voice": round(t_voice, 4),
            "ttfb_ms": round(ttfb_sec * 1000.0, 1),
            "gen": round(t_gen, 4),
            "dur": round(duration_sec, 3),
            "rtf": round(rtf, 3),
            "rms": round(rms, 4),
            "sample_rate": int(model.sample_rate),
            "rss_mb": round(rss_mb, 1),
        }
    except Exception as exc:
        resp = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    sys.stdout.write(json.dumps(resp) + "\n")
    sys.stdout.flush()
"""


class LocalNeuralTTSProvider:
    """
    Permanent Local Neural TTS Provider using Kyutai Pocket-TTS (24 kHz).
    Defaults to clear, natural male English ('george'), with optional Indonesian routing.
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
        self.indonesian_model_dir = getattr(
            self.config, "local_neural_indonesian_model_dir", DEFAULT_LOCAL_NEURAL_INDONESIAN_MODEL_DIR
        )

        if config_path:
            self.config_path = config_path
        else:
            en_cfg = os.path.join(self.model_dir, "english_local.yaml")
            id_cfg = os.path.join(self.model_dir, "indonesian_6l_local.yaml")
            self.config_path = en_cfg if os.path.isfile(en_cfg) else id_cfg

        self.voice_name = voice_name or getattr(self.config, "local_neural_voice", DEFAULT_VOICE_NAME)
        self.indonesian_voice_name = getattr(
            self.config, "local_neural_indonesian_voice", DEFAULT_LOCAL_NEURAL_INDONESIAN_VOICE
        )
        self.venv_python = venv_python or getattr(self.config, "local_neural_venv_python", DEFAULT_VENV_PYTHON)
        self.player = AudioPlayer(self.config)

        self._lock = threading.RLock()
        self._worker_lock = threading.RLock()
        self._worker_proc: Optional[subprocess.Popen] = None
        self._is_speaking = False
        self._stop_requested = False
        self._last_metrics: Dict[str, Any] = {}
        self._last_error: Optional[str] = None
        self.idle_timeout_sec = float(getattr(self.config, "local_neural_idle_timeout_sec", 60.0))
        self._idle_timer: Optional[threading.Timer] = None
        self._last_synthesis_time = time.time()

    def _resolve_language_and_bundle(
        self, voice_name: Optional[str] = None, language: Optional[str] = None
    ) -> Tuple[str, str, str, str]:
        """
        Return (lang_code, bundle_dir, yaml_config_path, resolved_voice_name).
        Defaults strictly to English unless language=='id' or an Indonesian voice_id is explicitly chosen.
        """
        saved = load_voice_settings()
        target_voice = (
            voice_name
            or saved.get("local_neural_voice")
            or self.voice_name
            or DEFAULT_VOICE_NAME
        )
        req_lang = (language or saved.get("tts_default_language") or self.config.tts_default_language or "en").lower()
        is_id_voice = target_voice.startswith(("common_voice_id", "indonesian_"))

        if req_lang.startswith("id") or is_id_voice:
            id_cfg = os.path.join(self.indonesian_model_dir, "indonesian_6l_local.yaml")
            if os.path.isfile(id_cfg):
                v_id = target_voice if is_id_voice else self.indonesian_voice_name
                return ("id", self.indonesian_model_dir, id_cfg, v_id)

        en_cfg = self.config_path
        v_en = DEFAULT_VOICE_NAME if is_id_voice else target_voice
        return ("en", self.model_dir, en_cfg, v_en)

    def get_voice_prompt_path(
        self, voice_name: Optional[str] = None, language: Optional[str] = None
    ) -> str:
        """Resolve absolute path to precomputed .safetensors or reference audio prompt file."""
        _, bundle_dir, _, target = self._resolve_language_and_bundle(voice_name=voice_name, language=language)
        voices_dir = os.path.join(bundle_dir, "voices")
        candidates = [
            os.path.join(voices_dir, f"{target}.safetensors"),
            os.path.join(voices_dir, f"{target}.wav"),
            os.path.join(voices_dir, f"{target}.mp3"),
            os.path.join(bundle_dir, f"{target}.safetensors"),
            os.path.join(bundle_dir, f"{target}.wav"),
            os.path.join(bundle_dir, f"{target}.mp3"),
            target,
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        if os.path.isdir(voices_dir):
            for f in sorted(os.listdir(voices_dir)):
                if f.endswith((".safetensors", ".wav", ".mp3")):
                    return os.path.join(voices_dir, f)
        return os.path.join(voices_dir, f"{DEFAULT_VOICE_NAME}.safetensors")

    def list_available_voices(self) -> List[Dict[str, Any]]:
        """List locally cached neural voice presets with gender and language metadata."""
        catalog_by_id = {v["voice_id"]: dict(v) for v in LOCAL_NEURAL_VOICE_CATALOG}
        results: List[Dict[str, Any]] = []
        seen = set()

        en_voices_dir = os.path.join(self.model_dir, "voices")
        if os.path.isdir(en_voices_dir):
            for fname in sorted(os.listdir(en_voices_dir)):
                if fname.endswith((".safetensors", ".wav", ".mp3")):
                    vid = os.path.splitext(fname)[0]
                    if vid in seen:
                        continue
                    seen.add(vid)
                    entry = catalog_by_id.get(
                        vid,
                        {"voice_id": vid, "name": f"{vid.title()} (English Neural)", "gender": "male", "language": "en"},
                    )
                    entry["available"] = True
                    results.append(entry)

        id_voices_dir = os.path.join(self.indonesian_model_dir, "voices")
        if os.path.isdir(id_voices_dir):
            for fname in sorted(os.listdir(id_voices_dir)):
                if fname.endswith((".safetensors", ".wav", ".mp3")):
                    vid = os.path.splitext(fname)[0]
                    if vid in seen:
                        continue
                    seen.add(vid)
                    entry = catalog_by_id.get(
                        vid,
                        {
                            "voice_id": vid,
                            "name": f"{vid} (Indonesian Neural Secondary)",
                            "gender": "male",
                            "language": "id",
                        },
                    )
                    entry["available"] = True
                    results.append(entry)

        # Put default male voice ('george') first
        results.sort(key=lambda x: (0 if x["voice_id"] == DEFAULT_VOICE_NAME else (1 if x["language"] == "en" else 2), x["voice_id"]))
        return results

    def is_available(self) -> bool:
        """Verify that English (or Indonesian) neural model files and runtime environment exist locally."""
        en_weights = os.path.join(self.model_dir, "model.safetensors")
        id_weights = os.path.join(self.indonesian_model_dir, "6l", "model.safetensors")
        legacy_weights = os.path.join(self.model_dir, "6l", "model.safetensors")
        en_tok = os.path.join(self.model_dir, "tokenizer.model")
        has_files = (os.path.isfile(en_weights) or os.path.isfile(legacy_weights) or os.path.isfile(id_weights)) and os.path.isfile(en_tok)
        if not has_files:
            return False

        if self._can_import_in_process():
            return True

        if os.path.isfile(self.venv_python):
            venv_lib = os.path.join(os.path.dirname(os.path.dirname(self.venv_python)), "lib")
            if os.path.isdir(venv_lib):
                for _, dirs, _ in os.walk(venv_lib):
                    if "pocket_tts" in dirs:
                        return True
        return False

    def _can_import_in_process(self) -> bool:
        try:
            import pocket_tts  # noqa: F401
            return True
        except ImportError:
            tts_site = os.path.expanduser("~/.local/share/maverick/tts-env/lib/python3.14/site-packages")
            if os.path.isdir(tts_site) and tts_site not in sys.path:
                sys.path.insert(0, tts_site)
                try:
                    import pocket_tts  # noqa: F401
                    return True
                except ImportError:
                    pass
            return False

    def _ensure_worker_unlocked(self) -> Optional[subprocess.Popen]:
        """Start or return the warm offline Pocket-TTS worker subprocess."""
        if self._worker_proc is not None and self._worker_proc.poll() is None:
            return self._worker_proc

        python_bin = self.venv_python if os.path.isfile(self.venv_python) else sys.executable
        env = dict(os.environ)
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env["MALLOC_ARENA_MAX"] = "2"

        try:
            proc = subprocess.Popen(
                [python_bin, "-u", "-c", _PERSISTENT_WORKER_CODE],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
            if proc.stdout:
                ready_line = proc.stdout.readline().strip()
                if ready_line and json.loads(ready_line).get("ready"):
                    self._worker_proc = proc
                    return proc
            proc.kill()
        except Exception as exc:
            self._last_error = f"worker_init_failed: {exc}"
        self._worker_proc = None
        return None

    def _arm_idle_timer(self) -> None:
        """Schedule auto-shutdown of warm worker after inactivity to reclaim RAM."""
        with self._worker_lock:
            if self._idle_timer is not None:
                self._idle_timer.cancel()
                self._idle_timer = None
            if self.idle_timeout_sec > 0 and self._worker_proc is not None:
                self._idle_timer = threading.Timer(self.idle_timeout_sec, self._on_idle_timeout)
                self._idle_timer.daemon = True
                self._idle_timer.start()

    def _on_idle_timeout(self) -> None:
        """Called when worker idle timeout expires without new synthesis requests."""
        with self._worker_lock:
            if self._worker_proc is not None and not self._is_speaking:
                time_since_last = time.time() - self._last_synthesis_time
                if time_since_last >= self.idle_timeout_sec:
                    try:
                        if self._worker_proc.stdin:
                            self._worker_proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                            self._worker_proc.stdin.flush()
                        self._worker_proc.terminate()
                        self._worker_proc.wait(timeout=1.0)
                    except Exception:
                        try:
                            self._worker_proc.kill()
                        except Exception:
                            pass
                    finally:
                        self._worker_proc = None
                        self._idle_timer = None

    def close(self) -> None:
        """Gracefully terminate warm TTS worker process and release memory."""
        self.stop()
        with self._worker_lock:
            if self._idle_timer is not None:
                self._idle_timer.cancel()
                self._idle_timer = None
            if self._worker_proc is not None:
                try:
                    if self._worker_proc.stdin:
                        self._worker_proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                        self._worker_proc.stdin.flush()
                    self._worker_proc.terminate()
                    self._worker_proc.wait(timeout=1.0)
                except Exception:
                    try:
                        self._worker_proc.kill()
                    except Exception:
                        pass
                finally:
                    self._worker_proc = None

    def is_speaking(self) -> bool:
        return self._is_speaking

    def stop(self) -> None:
        """Interrupt and stop current speech playback immediately."""
        with self._lock:
            self._stop_requested = True
            self._is_speaking = False
            self.player.stop()

    def synthesize_to_wav(
        self,
        text: str,
        output_wav_path: str,
        voice_name: Optional[str] = None,
        language: Optional[str] = None,
        temperature: Optional[float] = None,
        eos_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Synthesize speech into a 24kHz 16-bit PCM WAV file using the warm offline neural worker.
        Automatically restarts the worker once if it was terminated or crashed.
        """
        if not text or not text.strip():
            return {"ok": False, "error": "empty_text"}

        lang_code, _, cfg_path, resolved_voice = self._resolve_language_and_bundle(
            voice_name=voice_name, language=language
        )
        if lang_code == "en":
            normalized_text = normalize_english_voice_text(text)
            default_temp = float(getattr(self.config, "local_neural_temperature", 0.45))
            default_eos = float(getattr(self.config, "local_neural_eos_threshold", -4.0))
        else:
            normalized_text = normalize_voice_text(text, language="id")
            default_temp = 0.30
            default_eos = -6.0

        temp_val = default_temp if temperature is None else float(temperature)
        eos_val = default_eos if eos_threshold is None else float(eos_threshold)

        voice_prompt = self.get_voice_prompt_path(voice_name=resolved_voice, language=lang_code)
        if not os.path.isfile(voice_prompt):
            return {"ok": False, "error": f"voice_prompt_not_found: {voice_prompt}"}

        os.makedirs(os.path.dirname(os.path.abspath(output_wav_path)), exist_ok=True)
        t_start = time.perf_counter()

        payload = {
            "cmd": "synth",
            "config_path": cfg_path,
            "voice_prompt": voice_prompt,
            "output_path": output_wav_path,
            "text": normalized_text,
            "temperature": temp_val,
            "eos_threshold": eos_val,
        }

        with self._worker_lock:
            for attempt in range(2):
                proc = self._ensure_worker_unlocked()
                if proc is None or proc.stdin is None or proc.stdout is None:
                    break
                try:
                    proc.stdin.write(json.dumps(payload) + "\n")
                    proc.stdin.flush()
                    raw_resp = proc.stdout.readline()
                    if not raw_resp:
                        # Worker died unexpectedly; clear and retry once
                        self._worker_proc = None
                        continue
                    resp = json.loads(raw_resp.strip())
                    elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 1)
                    if resp.get("ok"):
                        resp["elapsed_ms"] = elapsed_ms
                        resp["output_path"] = output_wav_path
                        resp["voice_used"] = resolved_voice
                        resp["language"] = lang_code
                        resp["normalized_text"] = normalized_text
                        self._last_metrics = resp
                        self._last_error = None
                        self._last_synthesis_time = time.time()
                        self._arm_idle_timer()
                        return resp
                    else:
                        self._last_error = str(resp.get("error", "unknown_worker_error"))
                        return {"ok": False, "error": self._last_error, "elapsed_ms": elapsed_ms}
                except Exception as exc:
                    self._last_error = str(exc)
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    self._worker_proc = None
                    if attempt == 1:
                        return {"ok": False, "error": self._last_error}

        return {"ok": False, "error": self._last_error or "tts_worker_unavailable"}

    def synthesize_to_bytes(
        self,
        text: str,
        voice_name: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Synthesize speech and return `(wav_bytes, metrics)` without leaving temporary files on disk."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav = tmp.name
        try:
            meta = self.synthesize_to_wav(text, tmp_wav, voice_name=voice_name, language=language)
            if not meta.get("ok") or not os.path.isfile(tmp_wav):
                return b"", meta
            with open(tmp_wav, "rb") as f:
                data = f.read()
            return data, meta
        finally:
            if os.path.exists(tmp_wav):
                try:
                    os.unlink(tmp_wav)
                except OSError:
                    pass

    def speak(
        self,
        text: str,
        wait: bool = True,
        language: Optional[str] = None,
        voice_name: Optional[str] = None,
    ) -> bool:
        """Synthesize and play natural speech through local PipeWire/ALSA audio output."""
        if not text or not text.strip():
            return False

        with self._lock:
            self._stop_requested = False

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav = tmp.name

        try:
            res = self.synthesize_to_wav(text, tmp_wav, voice_name=voice_name, language=language)
            if not res.get("ok") or not os.path.isfile(tmp_wav):
                return False

            with self._lock:
                if self._stop_requested:
                    return True
                self._is_speaking = True

            ok_play = self.player.play_wav(tmp_wav, wait=wait)
            return ok_play
        except Exception as exc:
            self._last_error = str(exc)
            return False
        finally:
            if wait:
                with self._lock:
                    self._is_speaking = False
                self._arm_idle_timer()
                if os.path.exists(tmp_wav):
                    try:
                        os.unlink(tmp_wav)
                    except OSError:
                        pass

    def speak_stream(
        self,
        sentences: Iterable[str],
        on_first_audio: Optional[Callable[[], None]] = None,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synthesize and play streamed sentence chunks sequentially with instant interruption support."""
        t_start = time.perf_counter()
        first_ttfb_ms: Optional[float] = None
        spoken_parts: List[str] = []
        with self._lock:
            self._stop_requested = False
            self._is_speaking = True

        try:
            for sent in sentences:
                with self._lock:
                    if self._stop_requested:
                        break
                clean = (sent or "").strip()
                if not clean:
                    continue

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp_wav = tmp.name
                try:
                    meta = self.synthesize_to_wav(clean, tmp_wav, language=language)
                    if not meta.get("ok") or not os.path.isfile(tmp_wav):
                        continue
                    if first_ttfb_ms is None:
                        first_ttfb_ms = round((time.perf_counter() - t_start) * 1000.0, 1)
                        if on_first_audio:
                            on_first_audio()
                    with self._lock:
                        if self._stop_requested:
                            break
                    if self.player.play_wav(tmp_wav, wait=True):
                        spoken_parts.append(clean)
                finally:
                    if os.path.exists(tmp_wav):
                        try:
                            os.unlink(tmp_wav)
                        except OSError:
                            pass

            return {
                "ok": bool(spoken_parts),
                "engine": "local_neural",
                "chunks": len(spoken_parts),
                "tts_ttfb_ms": first_ttfb_ms or 0.0,
                "tts_playback_ms": round((time.perf_counter() - t_start) * 1000.0, 1),
                "full_text": " ".join(spoken_parts),
            }
        finally:
            with self._lock:
                self._is_speaking = False
            self._arm_idle_timer()

    def get_public_status(self) -> Dict[str, Any]:
        """Return non-sensitive public operational status for Control Center Dashboard."""
        saved = load_voice_settings()
        active_voice = str(saved.get("local_neural_voice") or self.voice_name or DEFAULT_VOICE_NAME)
        default_lang = str(saved.get("tts_default_language") or self.config.tts_default_language or "en")
        return {
            "engine": "local_neural",
            "model_name": "pocket-tts-english-6l",
            "secondary_model_name": "pocket-tts-indonesian-6l",
            "model_architecture": "Kyutai CALM 6L + Mimi 24kHz",
            "license": "CC-BY-4.0",
            "available": self.is_available(),
            "warm_worker_active": bool(self._worker_proc is not None and self._worker_proc.poll() is None),
            "config_path": self.config_path,
            "voice_name": active_voice,
            "default_language": default_lang,
            "voices": self.list_available_voices(),
            "offline_ready": True,
            "last_error": self._last_error,
            "last_metrics": self._last_metrics,
        }
