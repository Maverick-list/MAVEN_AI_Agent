"""Maverick DevOS - Voice Interaction Configuration."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class VoiceConfig:
    """Configuration settings for the Maverick Voice Interaction System."""

    # Audio capture specifications
    sample_rate: int = 16000
    channels: int = 1
    sample_width_bytes: int = 2  # 16-bit PCM (S16_LE)
    chunk_size: int = 1024

    # Wake word settings
    wake_words: List[str] = field(default_factory=lambda: ["maven", "jarvis"])
    wake_word_sensitivity: float = 0.6
    wake_debounce_seconds: float = 1.5

    # Voice Activity Detection (VAD) & speech boundaries
    silence_threshold_rms: float = 0.015
    speech_start_threshold_rms: float = 0.025
    silence_duration_seconds: float = 1.2
    listening_timeout_seconds: float = 8.0

    # Text-to-Speech (TTS) settings
    tts_engine: str = "speech_dispatcher"  # local /usr/bin/spd-say
    tts_voice: str = "default"
    tts_rate: int = 15  # -100 to +100
    tts_pitch: int = 0  # -100 to +100
    tts_volume: int = 100  # 0 to 100

    # Audio devices
    device_input: str = "default"
    device_output: str = "default"

    # Runtime behavior & safety guardrails
    muted: bool = False
    feedback_prevention: bool = True  # Mute capture during TTS playback
    enable_openclaw_fallback: bool = True
    model_id: str = "google/gemini-2.5-flash"
    max_recording_seconds: float = 15.0  # Guardrail against infinite recording

    # Confirmation requirement for consequential actions
    enforce_confirmation: bool = True
