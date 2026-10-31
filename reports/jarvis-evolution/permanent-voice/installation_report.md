# MAVEN JARVIS — Permanent Voice Installation & Environment Report

## 1. Environment & Isolation Overview

To protect Maven JARVIS production services and the active 7-Day Real-World Trial, all dependencies, models, and execution runtimes for the local neural voice system are strictly isolated.

| Component | Target Location | Status / Specification |
| :--- | :--- | :--- |
| **Active Worktree** | `/home/firza-ilmi/Maverick-DevOS-evolution` | Branch `feature/jarvis-evolution` |
| **Master Production** | `/home/firza-ilmi/Maverick-DevOS` | **100% Protected (No modifications)** |
| **7-Day Trial Monitor** | PID 14783 (`scripts/trial_monitor.py`) | **Active & Uninterrupted** |
| **Isolated Virtualenv**| `/home/firza-ilmi/.local/share/maverick/tts-env` | Isolated Python 3.14.4 virtual environment |
| **Package Tooling** | `/home/firza-ilmi/.hermes/tools/uv-0.13.5-linux-x64/uv` | Standalone binary (no global pip pollution) |
| **Dedicated Model Cache**| `/home/firza-ilmi/.local/share/maverick/models/tts/pocket-tts-indonesian/` | Dedicated offline cache |
| **Audio Samples Directory**| `reports/jarvis-evolution/permanent-voice/samples/` | Permanent voice WAV evaluation files |

---

## 2. Package Dependency Architecture

The local neural voice engine utilizes **Pocket-TTS** developed by Kyutai Labs (`pocket-tts==4.0.1`).
The package architecture consists of:
- **`pocket-tts`**: Core runtime providing `TTSModel`, flow-matching audio language model, and Mimi audio codec integration.
- **`torch`**: Neural network tensor computation (optimized for CPU inference).
- **`scipy`**: Standard audio file I/O (`scipy.io.wavfile`) for generating 24 kHz WAV buffers.
- **`sentencepiece`**: Byte-Pair Encoding (BPE) text tokenizer execution.
- **`safetensors`**: Ultra-fast, zero-copy model weight deserialization.
- **`einops`**: High-performance tensor dimension manipulation.

Installation is performed exclusively via `uv` targeting `--python /home/firza-ilmi/.local/share/maverick/tts-env`, ensuring zero system Python packages (`/usr/lib/python3/dist-packages`) are modified and `sudo` is never invoked.

---

## 3. Dedicated Model Cache Inventory

The 6-layer student model and supporting assets have been downloaded into the dedicated Maven cache:

```
~/.local/share/maverick/models/tts/pocket-tts-indonesian/
├── 6l/
│   └── model.safetensors          (417.7 MB, SHA256 verified)
├── indonesian_6l.yaml             (Remote HF configuration)
├── indonesian_6l_local.yaml       (Strict airgapped local configuration)
├── tokenizer.model                (311.3 KB, SentencePiece 4000 BPE)
└── voices/
    ├── common_voice_id_19961910.mp3 (4.6s, Male Balanced - Selected JARVIS Preset)
    ├── common_voice_id_20954552.mp3 (4.7s, Female Warm)
    ├── common_voice_id_20954811.mp3 (4.7s, Male Clear)
    └── common_voice_id_22918082.mp3 (5.0s, Female Expressive)
```

Total disk space utilized by model cache: **418.1 MB**.

---

## 4. Airgapped Local Configuration (`indonesian_6l_local.yaml`)

To ensure 100% offline airgapped operation, `indonesian_6l_local.yaml` was generated with direct absolute file paths:
- `weights_path`: Points directly to local `6l/model.safetensors`.
- `tokenizer_path`: Points directly to local `tokenizer.model`.
- `default_temperature`: `0.3` (Human evaluations preferred setting).
- `default_eos_threshold`: `-6.0` (Prevents premature sentence truncation).

During synthesis, environment variables `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are enforced to guarantee zero network calls.

