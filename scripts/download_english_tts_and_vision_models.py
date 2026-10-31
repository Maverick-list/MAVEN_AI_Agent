#!/usr/bin/env python3
"""
Download and cache offline local models for Maven JARVIS:
1. Kyutai English Pocket-TTS (6L CALM + Mimi 24kHz, CC-BY-4.0) + precomputed English male/female voice embeddings
   -> ~/.local/share/maverick/models/tts/pocket-tts-english/
2. OpenCV Zoo MediaPipe 21-Landmark Hand Tracking ONNX models (BlazePalm + HandPose, Apache-2.0)
   -> ~/.local/share/maverick/models/vision/
"""

import os
from pathlib import Path
import shutil

from huggingface_hub import hf_hub_download


ENGLISH_TTS_DIR = Path.home() / ".local" / "share" / "maverick" / "models" / "tts" / "pocket-tts-english"
VISION_MODELS_DIR = Path.home() / ".local" / "share" / "maverick" / "models" / "vision"

ENGLISH_VOICES = [
    "george",       # Clear, calm British/English male voice (default JARVIS-like male)
    "stuart_bell",  # Calm, authoritative British male voice
    "charles",      # Articulate British male voice
    "jean",         # Clear conversational male voice
    "marius",       # Warm male voice
    "javert",       # Deep authoritative male voice
    "michael",      # Clear American male voice
    "paul",         # Balanced male voice
    "alba",         # Clear female voice (optional alternative)
]


def download_vision_models() -> None:
    print("[1/2] Downloading OpenCV Zoo MediaPipe 21-Landmark Hand Tracking ONNX models...")
    VISION_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    vision_assets = [
        ("opencv/palm_detection_mediapipe", "palm_detection_mediapipe_2023feb.onnx"),
        ("opencv/palm_detection_mediapipe", "mp_palmdet.py"),
        ("opencv/handpose_estimation_mediapipe", "handpose_estimation_mediapipe_2023feb.onnx"),
        ("opencv/handpose_estimation_mediapipe", "mp_handpose.py"),
        ("opencv/handpose_estimation_mediapipe", "LICENSE"),
    ]
    for repo_id, filename in vision_assets:
        src = hf_hub_download(repo_id=repo_id, filename=filename)
        dst = VISION_MODELS_DIR / Path(filename).name
        shutil.copy2(src, dst)
        print(f"  -> Cached {dst} ({dst.stat().st_size / 1024:.1f} KB)")


def download_english_tts() -> None:
    print("[2/2] Downloading Kyutai English Pocket-TTS model & male voice embeddings...")
    ENGLISH_TTS_DIR.mkdir(parents=True, exist_ok=True)
    voices_dir = ENGLISH_TTS_DIR / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)

    repo_id = "kyutai/pocket-tts-without-voice-cloning"
    core_files = [
        ("languages/english/model.safetensors", ENGLISH_TTS_DIR / "model.safetensors"),
        ("languages/english/tokenizer.json", ENGLISH_TTS_DIR / "tokenizer.json"),
        ("languages/english/tokenizer.model", ENGLISH_TTS_DIR / "tokenizer.model"),
    ]
    for remote_path, local_dst in core_files:
        src = hf_hub_download(repo_id=repo_id, filename=remote_path)
        shutil.copy2(src, local_dst)
        print(f"  -> Cached {local_dst} ({local_dst.stat().st_size / 1048576:.2f} MB)")

    for voice in ENGLISH_VOICES:
        remote_voice = f"languages/english/embeddings/{voice}.safetensors"
        local_voice = voices_dir / f"{voice}.safetensors"
        src = hf_hub_download(repo_id=repo_id, filename=remote_voice)
        shutil.copy2(src, local_voice)
        print(f"  -> Cached voice {voice}: {local_voice} ({local_voice.stat().st_size / 1048576:.2f} MB)")

    # Write 100% offline local YAML configuration (zero hf:// URLs)
    local_yaml = f"""# Local Offline Configuration for Kyutai English Pocket-TTS (6L CALM + Mimi 24kHz)
# License: CC-BY-4.0
weights_path: {ENGLISH_TTS_DIR / "model.safetensors"}
weights_path_without_voice_cloning: {ENGLISH_TTS_DIR / "model.safetensors"}
default_temperature: 0.3

replace_characters:
  '’': "'"
  '‘': "'"

flow_lm:
  insert_bos_before_voice: true
  dtype: float32
  flow:
    depth: 6
    dim: 512
  transformer:
    d_model: 1024
    hidden_scale: 4
    max_period: 10000
    num_heads: 16
    num_layers: 6
  lookup_table:
    dim: 1024
    n_bins: 4000
    tokenizer: tokenizers
    tokenizer_path: {ENGLISH_TTS_DIR / "tokenizer.json"}

mimi:
  dtype: float32
  sample_rate: 24000
  inner_dim: 32
  outer_dim: 512
  channels: 1
  frame_rate: 12.5
  seanet:
    dimension: 512
    channels: 1
    n_filters: 64
    n_residual_layers: 1
    ratios:
    - 6
    - 5
    - 4
    kernel_size: 7
    residual_kernel_size: 3
    last_kernel_size: 3
    dilation_base: 2
    pad_mode: constant
    compress: 2
  transformer:
    d_model: 512
    num_heads: 8
    num_layers: 2
    layer_scale: 0.01
    context: 250
    dim_feedforward: 2048
    input_dimension: 512
    output_dimensions:
    - 512
  quantizer:
    dimension: 32
    output_dimension: 512
"""
    cfg_file = ENGLISH_TTS_DIR / "english_local.yaml"
    cfg_file.write_text(local_yaml, encoding="utf-8")
    print(f"  -> Wrote offline config: {cfg_file}")
    print("ALL MODELS CACHED SUCCESSFULLY.")


if __name__ == "__main__":
    download_vision_models()
    download_english_tts()
