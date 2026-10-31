# Engineering Remediation Report: Voice Barge-In & Command Retention (P1)

**Subsystem:** Voice Interaction Session & Conversational Engine  
**Worktree:** `/home/firza-ilmi/Maverick-DevOS-evolution`  
**Modified Files:**
- [`maverick/voice/session.py`](file:///home/firza-ilmi/Maverick-DevOS-evolution/maverick/voice/session.py)
- [`maverick/voice/config.py`](file:///home/firza-ilmi/Maverick-DevOS-evolution/maverick/voice/config.py)  
**Test Suite Created:** [`tests/test_voice_command_retention.py`](file:///home/firza-ilmi/Maverick-DevOS-evolution/tests/test_voice_command_retention.py)  
**Date:** October 31, 2026  
**Status:** REMEDIATED & VERIFIED (5/5 Tests Passing)

---

## 1. Problem Statement & Audit Finding

The independent engineering audit identified a critical conversational defect in the original voice barge-in implementation:
- When a user interrupted TTS speech playback, [`VoiceSession.interrupt()`](file:///home/firza-ilmi/Maverick-DevOS/reports/jarvis-evolution/independent-audit/voice_barge_in_audit.md) halted the audio output and transitioned the session from `SPEAKING` $\to$ `INTERRUPTED` $\to$ `IDLE`.
- Transitioning to `IDLE` meant that the user’s spoken interruption was completely discarded. The session sat waiting for the wake-word ("Maven") again.
- The assistant went silent, but never executed what the user asked when interrupting.

---

## 2. Technical Remediation Architecture

### A. Direct Transition to `LISTENING` with Audio Onset Retention
In [`VoiceSession.interrupt()`](file:///home/firza-ilmi/Maverick-DevOS-evolution/maverick/voice/session.py#L106):
```python
def interrupt(self, preserve_audio: Optional[bytes] = None) -> None:
    """Stop TTS speech, preserve incoming audio buffer, and transition immediately to LISTENING."""
    voice_logger.tts_interrupted()
    self.tts.stop()
    self._transition_to(VoiceState.INTERRUPTED)
    self.last_trigger_source = "barge_in"

    # Preserve the onset speech buffer and transition directly to LISTENING
    self._audio_buffer.clear()
    if preserve_audio:
        self._audio_buffer.extend(preserve_audio)
        self._has_detected_speech = True
    else:
        self._has_detected_speech = False

    self._listen_start_time = time.time()
    self._last_speech_time = self._listen_start_time
    self._transition_to(VoiceState.LISTENING)
```

### B. Dynamic Acoustic Gating
In [`VoiceSession.step()`](file:///home/firza-ilmi/Maverick-DevOS-evolution/maverick/voice/session.py#L140):
- Replaced the hardcoded $0.22$ gate with an adaptive threshold:
  ```python
  threshold = max(getattr(self.config, "barge_in_threshold_rms", 0.18), noise_floor * 3.5)
  if rms >= threshold:
      self.interrupt(preserve_audio=chunk)
      return None
  ```
- Normal ambient room noise and fan noise (RMS $< 0.05$) do not trigger false interruptions.
- Firm user speech bursts ($> 0.18$ RMS or $> 3.5\times$ dynamic noise floor) immediately interrupt TTS and preserve the triggering chunk in `_audio_buffer`.

### C. Conversational Lifecycle Continuity
- Because the session is placed directly in `VoiceState.LISTENING`, subsequent audio chunks from the user ("...cancel that and check battery") are seamlessly accumulated.
- When silence is detected, `step()` returns the full utterance to `VoiceDaemon`.
- `VoiceDaemon` dispatches the audio to Whisper STT, and the intent classifier processes the command without requiring the user to re-utter the wake word.

---

## 3. Verification & Test Evidence

All 5 tests in [`tests/test_voice_command_retention.py`](file:///home/firza-ilmi/Maverick-DevOS-evolution/tests/test_voice_command_retention.py) passed:
- `test_barge_in_stops_tts_and_preserves_audio_buffer`: Verified TTS halts immediately and session enters `LISTENING` with preserved onset audio.
- `test_silence_during_tts_does_not_interrupt`: Verified ambient silence maintains `SPEAKING`.
- `test_background_noise_below_threshold_does_not_interrupt`: Verified HVAC/fan noise does not trigger false interruptions.
- `test_full_barge_in_command_retention_and_utterance_delivery`: Verified complete lifecycle where user speech during TTS is buffered, trailed by silence, and delivered as an STT utterance.
- `test_repeated_interruptions`: Verified multiple consecutive barge-in events execute cleanly without state leaks.

