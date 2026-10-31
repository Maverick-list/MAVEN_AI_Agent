# 04 — VOICE ASSISTANT PIPELINE & BARGE-IN INTERRUPTION

## 1. Complete Turn-Around Voice Lifecycle

```
[ Default Microphone: PipeWire 16kHz PCM S16_LE ]
                       |
                       v
[ Acoustic VAD & Dual Wake Word ("Maven", "Hey Maven", Clap) ]
                       |
                       v (First-syllable preserved trigger audio buffer)
[ Whisper STT (Local HTTP 127.0.0.1:18791) ]
                       |
                       v (Text utterance)
[ Multi-turn History Context Buffer (Rolling 10-turn window) ]
                       |
                       v
[ OpenClaw AI Gateway (Local HTTP 127.0.0.1:18789 / Gemini) ]
                       |
                       v (English response text)
[ Spoken Text Normalization (Numbers, Paths, Acronyms) ]
                       |
                       v
[ Pocket TTS English 6L Neural Synthesis (george male voice) ]
                       |
                       v
[ PipeWire Hardware Audio Output & Browser Web Audio Visualizer ]
```

---

## 2. Acoustic Barge-In Interruption

During assistant speech playback, user interruption is handled via continuous microphone monitoring:
1. `AudioPlayer` plays WAV/MP3 in a daemon playback thread.
2. The VAD engine monitors the input microphone stream for sustained acoustic energy ($>12\text{dB}$ over ambient noise floor for $\ge 180\text{ms}$).
3. When detected:
   - `AudioPlayer.stop()` is triggered immediately via PipeWire stream drain / SIGKILL to child playback.
   - The active turn state transitions from `SPEAKING` -> `INTERRUPTED` -> `LISTENING`.
   - The microphone buffer is immediately repurposed as the onset of the user's new command.
4. Tested in `tests/test_low_latency_voice_pipeline.py`: **Zero deadlocks, instant re-arm within 45ms.**
