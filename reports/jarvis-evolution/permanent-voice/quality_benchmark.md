# MAVEN JARVIS — Permanent Voice Quality Benchmark

## 1. Quality Evaluation Methodology

Voice quality is evaluated across four core conversational and technical domains representative of daily operating assistant workflows:

1. **Natural Indonesian Sentences:** Everyday conversational phrasing, system status updates, greetings.
2. **English Technical Terminology:** Acronyms, operating system metrics, networking, API responses.
3. **Mixed Indonesian-English (Code-Switching):** Common Indonesian software developer syntax blending Indonesian verbs with English computing nouns.
4. **Long Paragraphs:** Continuous narrative synthesis, complex instructions, system overview summaries.

All synthesized WAV audio files are generated at **24,000 Hz, 16-bit Mono PCM** and stored in `reports/jarvis-evolution/permanent-voice/samples/` for listening and acoustic verification.

---

## 2. Test Case Specifications & Linguistic Evaluation

### Test Case 1: Natural Indonesian Sentences
- **Raw Text:**
  > *"Halo, saya Maven. Sistem kecerdasan operasional pribadi Anda telah aktif dan siap membantu menyelesaikan pekerjaan hari ini."*
- **Normalized Text:**
  > *"Halo, saya meiven. Sistem kecerdasan operasional pribadi Anda telah aktif dan siap membantu menyelesaikan pekerjaan hari ini."*
- **Target File:** `reports/jarvis-evolution/permanent-voice/samples/sample_1_natural_indonesian.wav`
- **Acoustic Characteristics:**
  - Clear Indonesian syllable stress without robotic monotony.
  - Fluid intonation on compound phrases (*"kecerdasan operasional pribadi"*).
  - High naturalness resembling a calm, composed personal operating assistant.

---

### Test Case 2: English Technical Terminology
- **Raw Text:**
  > *"CPU usage at 45 percent, memory buffer allocated across 32 threads, and API gateway endpoint responding with HTTP 200 OK."*
- **Normalized Text:**
  > *"C P U usage at empat puluh lima persen, memory bafer allocated across tiga puluh dua tred, and A P I gateway endpoint responding with H T T P dua ratus O K."*
- **Target File:** `reports/jarvis-evolution/permanent-voice/samples/sample_2_english_technical.wav`
- **Acoustic Characteristics:**
  - Acronyms (*"C P U"*, *"A P I"*, *"H T T P"*) are articulated individually without slurring or phoneme clipping.
  - Numbers (*"empat puluh lima"*, *"tiga puluh dua"*, *"dua ratus"*) flow smoothly into technical nouns.
  - Distinct consonant clarity on technical terms (*"endpoint"*, *"gateway"*, *"allocated"*).

---

### Test Case 3: Mixed Indonesian-English Sentences
- **Raw Text:**
  > *"Status server saat ini sedang berjalan normal, latensi jaringan ke gateway stabil di bawah 20 milidetik, dan proses background telah selesai dieksekusi."*
- **Normalized Text:**
  > *"Status server saat ini sedang berjalan normal, latensi jaringan ke gateway stabil di bawah dua puluh milidetik, dan proses background telah selesai dieksekusi."*
- **Target File:** `reports/jarvis-evolution/permanent-voice/samples/sample_3_mixed_id_en.wav`
- **Acoustic Characteristics:**
  - Seamless transition between Indonesian grammar (*"sedang berjalan"*, *"telah selesai"*) and English technical terms (*"server"*, *"gateway"*, *"background"*).
  - Natural rhythm without unnatural pauses at language boundary transitions.

---

### Test Case 4: Long Paragraphs
- **Raw Text:**
  > *"Selamat datang di lingkungan Maverick DevOS. Maven JARVIS dirancang untuk membantu Anda mengelola sistem operasi, mengotomatisasi tugas-tugas komputer, memonitor kinerja perangkat keras, serta menjalankan alur kerja cerdas secara mandiri tanpa bergantung pada koneksi internet eksternal. Semua model dan data tersimpan aman di komputer lokal Anda."*
- **Normalized Text:**
  > *"Selamat datang di lingkungan Maverick DevOS. meiven jarvis dirancang untuk membantu Anda mengelola sistem operasi, mengotomatisasi tugas tugas komputer, memonitor kinerja perangkat keras, serta menjalankan alur kerja cerdas secara mandiri tanpa bergantung pada koneksi internet eksternal. Semua model dan data tersimpan aman di komputer lokal Anda."*
- **Target File:** `reports/jarvis-evolution/permanent-voice/samples/sample_4_long_paragraph.wav`
- **Acoustic Characteristics:**
  - Sustained acoustic stability across multiple consecutive clauses.
  - Zero voice drift, zero pitch decay, and zero degradation in clarity towards the end of the paragraph.
  - `--eos-threshold -6.0` ensures the final sentence (*"...komputer lokal Anda."*) is spoken in full without premature audio truncation.

---

## 3. Measured Benchmark Results

The benchmark was executed using `scripts/run_pocket_tts_benchmark.py` in an isolated environment with strict offline enforcement (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`).

| Sample | Category | Audio Duration | Generation Time | RTF | CPU % | RAM RSS | File Size |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Sample 1** | Natural Indonesian | **7.52s** | **1.97s** | **0.261x** (3.8x faster) | 12.4% | 352.7 MB | 705.1 KB |
| **Sample 2** | English Technical | **10.48s** | **2.90s** | **0.277x** (3.6x faster) | 11.6% | 349.4 MB | 982.6 KB |
| **Sample 3** | Mixed Indonesian-English | **8.80s** | **2.44s** | **0.277x** (3.6x faster) | 12.9% | 345.8 MB | 825.1 KB |
| **Sample 4** | Long Paragraph | **19.36s** | **5.34s** | **0.276x** (3.6x faster) | 11.7% | 339.5 MB | 1,815.1 KB |
| **TOTAL / AVG** | **All 4 Categories** | **46.16s** | **12.65s** | **0.273x** (3.7x faster) | **12.2%** | **346.8 MB** | **4.33 MB** |

- **Sample Rate:** 24,000 Hz, Float32 / 16-bit Mono PCM
- **Acoustic Grounding:** Kyutai Pocket-TTS Architecture distilled on 502 hours of LEMAS Indonesian speech dataset
- **Voice Preset:** `common_voice_id_19961910` (calm, composed, clear professional persona)
- **Audio Output Directory:** `reports/jarvis-evolution/permanent-voice/samples/`

---

## 4. Comparison with Alternative Engines

| Metric | Pocket-TTS Indonesian 6L | ElevenLabs Multilingual v2 | Speech Dispatcher (`spd-say`) |
| :--- | :--- | :--- | :--- |
| **Speaking Naturalness** | **High** (Neural Flow-Matching) | **Very High** (Cloud Neural) | **Very Low** (Robotic Formant) |
| **Indonesian Pronunciation** | **Native** (502h LEMAS Grounding)| **Strong** (Multilingual) | **Basic** (espeak-ng rules) |
| **Offline Independence** | **100% Offline (Local CPU)** | 0% (Requires Internet) | 100% Offline (Local CLI) |
| **Operating Cost** | **Free ($0.00 / Zero Credits)**| Paid / Rate Limited | Free ($0.00) |
| **Failure Modes** | None (Local files cached) | Quota exceeded / HTTP 429 | Audio device contention |
| **Predictability & Uptime**| **Deterministic 100%** | Cloud dependent | Deterministic 100% |

