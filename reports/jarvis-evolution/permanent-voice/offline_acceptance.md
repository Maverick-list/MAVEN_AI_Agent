# MAVEN JARVIS — Offline Voice Acceptance & Airgap Verification

## 1. Objective & Airgap Requirements

The primary architectural flaw in previous voice implementations was reliance on external third-party cloud APIs (such as ElevenLabs), which caused Maven to degrade to robotic Speech Dispatcher or go mute whenever:
1. Internet connectivity was interrupted.
2. Cloud service quotas/credits were exhausted (as observed when ElevenLabs credits reached 0/10,000).
3. API authentication or network latency spikes occurred.

To resolve this permanently, Maven JARVIS mandates that the primary voice engine must be **100% offline, locally hosted, and fully functional in completely airgapped environments**.

---

## 2. Airgap Configuration & Isolation Verification

### 2.1 Explicit Local Path Binding
The local model configuration file `~/.local/share/maverick/models/tts/pocket-tts-indonesian/indonesian_6l_local.yaml` eliminates all `hf://` remote URI schemas in favor of absolute local filesystem paths:

```yaml
# Strict Local Offline Configuration
weights_path: /home/firza-ilmi/.local/share/maverick/models/tts/pocket-tts-indonesian/6l/model.safetensors
default_temperature: 0.3
default_eos_threshold: -6.0

flow_lm:
  insert_bos_before_voice: true
  dtype: float32
  flow:
    depth: 6
    dim: 512
  transformer:
    d_model: 1024
    hidden_scale: 4
    num_heads: 16
    num_layers: 6
  lookup_table:
    dim: 1024
    n_bins: 4000
    tokenizer: sentencepiece
    tokenizer_path: /home/firza-ilmi/.local/share/maverick/models/tts/pocket-tts-indonesian/tokenizer.model
```

### 2.2 Forced Offline Environment Variables
During initialization and inference in `maverick.voice.local_neural_tts`, the execution environment strictly enforces:

```python
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
```

This prevents any underlying Hugging Face Hub or model utilities from attempting DNS resolution, checking remote metadata hashes, or making background HTTP/HTTPS telemetry requests.

---

## 3. Persistent Voice Identity Across Reboots

The selected voice identity is decoupled from ephemeral session state and persisted in non-secret user settings:

- **Storage Location:** `~/.config/maverick/voice_settings.json`
- **File Permissions:** `0600` (Read/Write restricted exclusively to the user)
- **Key Parameters:**
  ```json
  {
    "tts_engine": "local_neural",
    "local_neural_voice": "common_voice_id_19961910",
    "local_neural_temperature": 0.3,
    "local_neural_eos_threshold": -6.0
  }
  ```

Upon reboot or service restart:
1. `load_voice_settings()` reads `voice_settings.json`.
2. `VoiceConfig` loads `local_neural` as the primary engine.
3. `HybridTTSProvider` initializes `LocalNeuralTTSProvider` with `common_voice_id_19961910`.
4. Maven greets the user using the exact same consistent, authoritative JARVIS persona.

