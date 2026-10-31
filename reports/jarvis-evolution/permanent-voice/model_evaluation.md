# MAVEN JARVIS — Pocket TTS Indonesian Model Evaluation

## 1. Model Identification & Repository Metadata

| Attribute | Specification |
| :--- | :--- |
| **Hugging Face Repository** | [`anak10thn/pocket-tts-indonesian`](https://huggingface.co/anak10thn/pocket-tts-indonesian) |
| **Base Architecture** | Kyutai CALM (Continuous Audio Language Model) + Mimi Neural Codec (24 kHz) |
| **License** | **CC-BY-4.0** (Permissive open-source license permitting commercial & private use) |
| **Training Dataset** | LEMAS Indonesian Speech Dataset (~502 hours of conversational & read speech) |
| **Distilled Student Model** | 6-Layer Transformer Distillation (`indonesian_6l.yaml`, `6l/model.safetensors`) |
| **Teacher Model** | 12-Layer Transformer (`indonesian_12l.yaml`, `12l/model.safetensors`, 728.8 MB) |
| **Selected Variant** | **6-Layer Distilled Student Model** (Best latency-to-quality ratio on CPU) |
| **Model Disk Footprint** | Model weights: 417.7 MB, Tokenizer: 311 KB, Voices: 152 KB |
| **Tokenizer Type** | SentencePiece BPE (4,000 bins vocabulary) |
| **Recommended Sampling Params**| `temperature: 0.3`, `eos_threshold: -6.0` |

---

## 2. Technical Architecture Analysis

### 2.1 CALM & Mimi Codec Flow-Matching
Pocket-TTS utilizes a continuous audio representation:
1. **Flow-Matching Latent Transformer:** An autoregressive flow-matching transformer maps text tokens into latent continuous audio embeddings.
2. **Mimi Audio Codec:** Developed by Kyutai Labs, Mimi operates at 12.5 frames per second with a 24 kHz sample rate, reconstructing speech waveforms with high naturalness and minimal robotic artifacts.
3. **Voice Prompt Conditioning:** Zero-shot speaker cloning is achieved by supplying a short 4–5 second reference audio sample (`.mp3` or `.wav`). In Maven JARVIS, reference voice `common_voice_id_19961910` was selected as the male, authoritative JARVIS persona.

### 2.2 Distilled 6-Layer Student Advantages
- **Parameters:** ~100M parameters compared to >1B in large cloud models.
- **CPU Speed:** 2.23x faster than real-time on standard x86_64 CPUs (RTF $\approx 0.45$).
- **Memory Footprint:** Operates under 1.2 GB RAM, well within Maverick DevOS hardware budgets.
- **Latency:** Synthesizes short conversational turns within 300–800 ms.

---

## 3. Linguistic & Vocabulary Capabilities

### 3.1 Indonesian Pronunciation Quality
- **Training Grounding:** 502 hours of native Indonesian audio provides accurate vowel articulation, syllable stress, and sentence-level prosody.
- **Utterance Intonation:** Sentences sound fluid and human-like without the flat monotone characteristic of formant synthesizers (`espeak-ng`).

### 3.2 English Technical Vocabulary & Code-Switching
- The BPE tokenizer was trained primarily on Indonesian text. Direct exposure to raw English technical acronyms or complex English loan words can result in fragmented phonemes or mispronunciations.
- **Solution:** Maven's `text_normalization` engine bridges this gap by intercepting technical terms prior to synthesis:
  - Acronyms are phonetically spaced: `CPU` $\rightarrow$ `C P U`, `API` $\rightarrow$ `A P I`, `RAM` $\rightarrow$ `R A M`.
  - Loan words are phonetically mapped: `Python` $\rightarrow$ `paiton`, `offline` $\rightarrow$ `oflein`, `cache` $\rightarrow$ `kesh`.

### 3.3 Tokenizer Constraints & Remediation
| Constraint | Impact if Unhandled | Maven Remediation |
| :--- | :--- | :--- |
| **Digits Out-of-Vocabulary** | BPE tokenizer cannot represent `0-9` directly | All numbers are expanded to Indonesian words (`15` $\rightarrow$ `lima belas`) |
| **Exclamation Mark OOV** | Tokenizer raises OOV or generates glitch | Exclamation marks `!` are replaced with periods `.` |
| **Hyphenated Compounds** | Subword splitting errors on `anak-anak` | Hyphens replaced with spaces (`anak anak`) |
| **Early Utterance Cutoff** | Default EOS threshold cuts off sentence ends | Tuned `--eos-threshold -6.0` parameter applied |

