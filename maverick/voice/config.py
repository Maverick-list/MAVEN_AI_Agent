"""Maverick DevOS - Voice Interaction Configuration."""

from dataclasses import dataclass, field
import json
import os
from typing import Any, Dict, List, Optional

CONFIG_DIR = os.path.expanduser("~/.config/maverick")
ELEVENLABS_ENV_FILE = os.path.join(CONFIG_DIR, "elevenlabs.env")
VOICE_SETTINGS_FILE = os.path.join(CONFIG_DIR, "voice_settings.json")

# Calm, authoritative JARVIS-inspired ElevenLabs voice presets (Multilingual v2 compatible)
DEFAULT_ELEVENLABS_VOICE_ID = "onwK4e9ZLuTAKqWW03F9"  # Daniel (British, calm, authoritative)
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"

# Primary Local Neural English Male Voice presets (Kyutai Pocket-TTS English 6L, CC-BY-4.0)
DEFAULT_LOCAL_NEURAL_VOICE = "george"  # Calm, authoritative British male voice
DEFAULT_LOCAL_NEURAL_MODEL_DIR = os.path.expanduser("~/.local/share/maverick/models/tts/pocket-tts-english")

# Secondary Local Neural Indonesian Voice presets (Pocket-TTS Indonesian 6L, explicit opt-in)
DEFAULT_LOCAL_NEURAL_INDONESIAN_VOICE = "common_voice_id_19961910"
DEFAULT_LOCAL_NEURAL_INDONESIAN_MODEL_DIR = os.path.expanduser(
    "~/.local/share/maverick/models/tts/pocket-tts-indonesian"
)

LOCAL_NEURAL_VOICE_CATALOG: List[Dict[str, str]] = [
    {"voice_id": "george", "name": "George (Calm British Male — Default JARVIS)", "gender": "male", "language": "en"},
    {"voice_id": "jean", "name": "Jean (Clear Conversational Male)", "gender": "male", "language": "en"},
    {"voice_id": "charles", "name": "Charles (Articulate British Male)", "gender": "male", "language": "en"},
    {"voice_id": "stuart_bell", "name": "Stuart (Warm Narrative Male)", "gender": "male", "language": "en"},
    {"voice_id": "marius", "name": "Marius (Crisp Studio Male)", "gender": "male", "language": "en"},
    {"voice_id": "javert", "name": "Javert (Deep Authoritative Male)", "gender": "male", "language": "en"},
    {"voice_id": "michael", "name": "Michael (Neutral American Male)", "gender": "male", "language": "en"},
    {"voice_id": "paul", "name": "Paul (Calm Studio Male)", "gender": "male", "language": "en"},
    {"voice_id": "alba", "name": "Alba (Clear Studio Female)", "gender": "female", "language": "en"},
    {
        "voice_id": "common_voice_id_19961910",
        "name": "Arjuna ID (Indonesian 6L Secondary)",
        "gender": "male",
        "language": "id",
    },
]


def _read_env_file_dict(path: str = ELEVENLABS_ENV_FILE) -> Dict[str, str]:
    """Read KEY=VALUE pairs from ~/.config/maverick/elevenlabs.env without logging values."""
    values: Dict[str, str] = {}
    if not os.path.isfile(path):
        return values
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k:
                        values[k] = v
    except Exception:
        pass
    return values


def get_elevenlabs_api_key(env_file: str = ELEVENLABS_ENV_FILE) -> str:
    """
    Resolve ElevenLabs API key exclusively from environment variables or local 0600 env file.
    Never persists, prints, or exposes the secret key in dataclass fields or API responses.
    """
    env_key = (os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("XI_API_KEY") or "").strip()
    if env_key:
        return env_key
    file_vars = _read_env_file_dict(env_file)
    return (file_vars.get("ELEVENLABS_API_KEY") or file_vars.get("XI_API_KEY") or "").strip()


def load_voice_settings(settings_file: str = VOICE_SETTINGS_FILE) -> Dict[str, Any]:
    """Load non-secret user voice configuration overrides from ~/.config/maverick/voice_settings.json."""
    if not os.path.isfile(settings_file):
        return {}
    try:
        with open(settings_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {
                    k: v
                    for k, v in data.items()
                    if "key" not in k.lower() and "secret" not in k.lower() and "token" not in k.lower()
                }
    except Exception:
        pass
    return {}


def save_voice_settings(updates: Dict[str, Any], settings_file: str = VOICE_SETTINGS_FILE) -> Dict[str, Any]:
    """Persist non-secret voice tuning settings with 0600 permissions."""
    allowed_keys = {
        "tts_engine",
        "tts_default_language",
        "stt_language",
        "local_neural_voice",
        "local_neural_temperature",
        "local_neural_eos_threshold",
        "local_neural_idle_timeout_sec",
        "elevenlabs_voice_id",
        "elevenlabs_model_id",
        "elevenlabs_stability",
        "elevenlabs_similarity_boost",
        "elevenlabs_style",
        "elevenlabs_speed",
        "elevenlabs_use_speaker_boost",
        "tts_rate",
        "tts_pitch",
        "tts_volume",
    }
    current = load_voice_settings(settings_file)
    for k, v in updates.items():
        if k in allowed_keys:
            current[k] = v

    os.makedirs(os.path.dirname(settings_file), mode=0o700, exist_ok=True)
    tmp_path = f"{settings_file}.tmp"
    fd = os.open(tmp_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with open(fd, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
        f.flush()
    os.replace(tmp_path, settings_file)
    try:
        os.chmod(settings_file, 0o600)
    except OSError:
        pass
    return current


def _default_voice_id() -> str:
    env_vid = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if env_vid:
        return env_vid
    saved = load_voice_settings()
    if saved.get("elevenlabs_voice_id"):
        return str(saved["elevenlabs_voice_id"]).strip()
    file_vars = _read_env_file_dict()
    if file_vars.get("ELEVENLABS_VOICE_ID"):
        return file_vars["ELEVENLABS_VOICE_ID"].strip()
    return DEFAULT_ELEVENLABS_VOICE_ID


def _default_model_id() -> str:
    env_mid = os.environ.get("ELEVENLABS_MODEL_ID", "").strip()
    if env_mid:
        return env_mid
    saved = load_voice_settings()
    if saved.get("elevenlabs_model_id"):
        return str(saved["elevenlabs_model_id"]).strip()
    file_vars = _read_env_file_dict()
    if file_vars.get("ELEVENLABS_MODEL_ID"):
        return file_vars["ELEVENLABS_MODEL_ID"].strip()
    return DEFAULT_ELEVENLABS_MODEL_ID


def _default_openclaw_model_config() -> Dict[str, Any]:
    """Read primary and fallback model IDs from ~/.openclaw/openclaw.json without touching secrets."""
    cfg_path = os.path.expanduser("~/.openclaw/openclaw.json")
    default_primary = "google/gemini-2.5-flash"
    if not os.path.isfile(cfg_path):
        return {"primary": default_primary, "fallbacks": []}
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        model_cfg = data.get("agents", {}).get("defaults", {}).get("model", {})
        if isinstance(model_cfg, str) and model_cfg.strip():
            return {"primary": model_cfg.strip(), "fallbacks": []}
        if isinstance(model_cfg, dict):
            primary = str(model_cfg.get("primary") or default_primary).strip()
            raw_fb = model_cfg.get("fallbacks") or []
            fallbacks = [str(m).strip() for m in raw_fb if str(m).strip()] if isinstance(raw_fb, list) else []
            return {"primary": primary, "fallbacks": fallbacks}
    except Exception:
        pass
    return {"primary": default_primary, "fallbacks": []}


@dataclass
class VoiceConfig:
    """Configuration settings for the Maverick Voice Interaction System."""

    # Audio capture specifications
    sample_rate: int = 16000
    channels: int = 1
    sample_width_bytes: int = 2  # 16-bit PCM (S16_LE)
    chunk_size: int = 1024

    # Whisper STT & Local Inference specifications
    whisper_bin_path: str = "/home/firza-ilmi/.local/share/maverick/whisper.cpp/build/bin/whisper-cli"
    whisper_server_bin_path: str = "/home/firza-ilmi/.local/share/maverick/whisper.cpp/build/bin/whisper-server"
    whisper_model_path: str = "/home/firza-ilmi/.local/share/maverick/whisper.cpp/models/ggml-tiny.bin"
    whisper_server_host: str = "127.0.0.1"
    whisper_server_port: int = 18791
    use_whisper_server: bool = True
    stt_language: str = "id"  # Prioritize Indonesian speech recognition
    whisper_threads: int = 8

    # Wake word settings
    wake_words: List[str] = field(default_factory=lambda: ["maven", "jarvis"])
    wake_word_sensitivity: float = 0.6
    wake_debounce_seconds: float = 1.5

    # Voice Activity Detection (VAD) & speech boundaries
    silence_threshold_rms: float = 0.015
    speech_start_threshold_rms: float = 0.025
    barge_in_threshold_rms: float = 0.18
    silence_duration_seconds: float = 1.2
    listening_timeout_seconds: float = 8.0

    # Text-to-Speech (TTS) permanent hierarchy:
    # 1. PRIMARY: 'local_neural' (Kyutai Pocket-TTS English 6L, male voice 'george')
    # 2. OPTIONAL PREMIUM: 'elevenlabs' (explicit user opt-in only)
    # 3. EMERGENCY FALLBACK: 'speech_dispatcher' (with audible warning)
    tts_engine: str = "local_neural"
    tts_default_language: str = "en"
    tts_voice: str = "default"
    tts_rate: int = 15  # -100 to +100 (Speech Dispatcher fallback)
    tts_pitch: int = 0  # -100 to +100
    tts_volume: int = 100  # 0 to 100

    # Local Neural Voice settings (Primary English 6L + Secondary Indonesian 6L)
    local_neural_model_dir: str = DEFAULT_LOCAL_NEURAL_MODEL_DIR
    local_neural_indonesian_model_dir: str = DEFAULT_LOCAL_NEURAL_INDONESIAN_MODEL_DIR
    local_neural_voice: str = DEFAULT_LOCAL_NEURAL_VOICE
    local_neural_indonesian_voice: str = DEFAULT_LOCAL_NEURAL_INDONESIAN_VOICE
    local_neural_temperature: float = 0.45
    local_neural_eos_threshold: float = -4.0
    local_neural_idle_timeout_sec: float = 60.0

    # ElevenLabs neural voice tuning (Optional Premium)
    elevenlabs_voice_id: str = field(default_factory=_default_voice_id)
    elevenlabs_model_id: str = field(default_factory=_default_model_id)
    elevenlabs_stability: float = 0.55
    elevenlabs_similarity_boost: float = 0.80
    elevenlabs_style: float = 0.15
    elevenlabs_speed: float = 1.0
    elevenlabs_use_speaker_boost: bool = True
    elevenlabs_timeout_sec: float = 12.0
    elevenlabs_optimize_streaming_latency: int = 3

    # OpenClaw Local Gateway SSE Streaming settings
    openclaw_http_host: str = "127.0.0.1"
    openclaw_http_port: int = 18789
    openclaw_voice_session_user: str = "maven-voice-fast"
    openclaw_voice_max_tokens: int = 140
    openclaw_primary_cooldown_sec: float = 300.0

    # Audio devices
    device_input: str = "default"
    device_output: str = "default"

    # Runtime behavior & safety guardrails
    muted: bool = False
    feedback_prevention: bool = True
    enable_openclaw_fallback: bool = True
    model_id: str = field(default_factory=lambda: _default_openclaw_model_config()["primary"])
    model_fallbacks: List[str] = field(default_factory=lambda: _default_openclaw_model_config()["fallbacks"])
    max_recording_seconds: float = 15.0

    # Confirmation requirement for consequential actions
    enforce_confirmation: bool = True

    # Dual-Clap Detection & Ambient Presence
    enable_clap_detection: bool = True
    clap_min_interval_sec: float = 0.15
    clap_max_interval_sec: float = 0.50
    clap_cooldown_sec: float = 1.0
    clap_sensitivity: float = 0.65

    # Boot Greeting & Quiet Hours
    boot_greeting_enabled: bool = True
    boot_greeting_lang: str = "en"
    quiet_hours_enabled: bool = True
    quiet_hours_start: int = 22
    quiet_hours_end: int = 7

    def __post_init__(self) -> None:
        """Apply persisted non-secret user tuning overrides if present."""
        saved = load_voice_settings()
        if not saved:
            return
        if "tts_engine" in saved and saved["tts_engine"] in ("local_neural", "elevenlabs", "speech_dispatcher"):
            self.tts_engine = str(saved["tts_engine"])
        if "tts_default_language" in saved and saved["tts_default_language"] in ("en", "id", "auto"):
            self.tts_default_language = str(saved["tts_default_language"])
        if "local_neural_voice" in saved and str(saved["local_neural_voice"]).strip():
            self.local_neural_voice = str(saved["local_neural_voice"]).strip()
        for float_key, lo, hi in (
            ("local_neural_temperature", 0.0, 1.0),
            ("local_neural_eos_threshold", -10.0, 0.0),
            ("elevenlabs_stability", 0.0, 1.0),
            ("elevenlabs_similarity_boost", 0.0, 1.0),
            ("elevenlabs_style", 0.0, 1.0),
            ("elevenlabs_speed", 0.7, 1.2),
        ):
            if float_key in saved:
                try:
                    setattr(self, float_key, max(lo, min(hi, float(saved[float_key]))))
                except (TypeError, ValueError):
                    pass
        if "elevenlabs_use_speaker_boost" in saved:
            self.elevenlabs_use_speaker_boost = bool(saved["elevenlabs_use_speaker_boost"])
        for int_key, lo_i, hi_i in (
            ("tts_rate", -100, 100),
            ("tts_pitch", -100, 100),
            ("tts_volume", 0, 100),
        ):
            if int_key in saved:
                try:
                    setattr(self, int_key, max(lo_i, min(hi_i, int(saved[int_key]))))
                except (TypeError, ValueError):
                    pass
