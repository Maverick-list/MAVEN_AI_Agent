# Independent Engineering Audit: Voice Barge-In System

**System Under Audit:** MAVEN JARVIS Ultimate AI Operating Assistant Evolution  
**Target Repository:** `/home/firza-ilmi/Maverick-DevOS-evolution`  
**Target File:** [`maverick/voice/session.py`](file:///home/firza-ilmi/Maverick-DevOS-evolution/maverick/voice/session.py)  
**Auditor:** Principal Software Architect, Voice AI & Digital Signal Processing Engineer  
**Date:** October 31, 2026  
**Status:** COMPLETE — AUDIT ONLY (NO CODE MODIFIED)

---

## 1. Executive Summary

This audit independently reviewed the newly introduced conversational barge-in capability implemented in [`VoiceSession.step()`](file:///home/firza-ilmi/Maverick-DevOS-evolution/maverick/voice/session.py#L140). The goal of this feature is to allow a user to interrupt active Text-To-Speech (TTS) playback by speaking.

### Overall Assessment: HEURISTIC / PARTIALLY EFFECTIVE
- **Mechanism:** The implementation uses an **acoustic energy threshold gate** (`calculate_rms(chunk) > max(0.22, noise_floor * 3.8)`). It does not use True Acoustic Echo Cancellation (AEC), digital reference subtraction, or neural speech separation.
- **Reliability:** Effective for firm or loud speech bursts in quiet rooms.
- **Vulnerabilities:**
  1. **Acoustic Self-Interruption Risk:** If the user sets laptop speaker volume high, the microphone array on the laptop bezel/chassis can pick up the assistant's own voice with $\text{RMS} > 0.22$, causing MAVEN to interrupt itself.
  2. **Post-Interrupt State Drop:** Upon interruption, the state transitions from `SPEAKING` $\to$ `INTERRUPTED` $\to$ `IDLE`, **not** to `LISTENING`. The speech uttered by the user during the interruption is discarded, requiring the user to speak the wake-word again from scratch.
  3. **Vulnerability to Mechanical Transients:** Door slams, heavy typing clatter on the built-in laptop keyboard, or coughs close to the mic will falsely trigger barge-in.

---

## 2. Acoustic Analysis & Threshold Mechanics

### Gating Implementation
Located at [`session.py#L140-L157`](file:///home/firza-ilmi/Maverick-DevOS-evolution/maverick/voice/session.py#L140-L157):
```python
if self.tts.is_speaking():
    if self._state != VoiceState.SPEAKING:
        self._transition_to(VoiceState.SPEAKING)

    # Barge-in detection: inspect incoming microphone audio for user speech bursts
    chunk = self.audio.read_chunk()
    if chunk:
        rms = calculate_rms(chunk)
        noise_floor = getattr(self.wake_detector, "_noise_floor", 0.05) or 0.05
        # Distinct acoustic onset during playback interrupts assistant speech immediately
        if rms > max(0.22, noise_floor * 3.8):
            voice_logger.tts_interrupted()
            self.interrupt()
            return None
    time.sleep(0.04)
    return None
```

### Analysis of the Mathematical Boundary
- Standard 16-bit PCM audio samples are normalized between $-1.0$ and $+1.0$.
- Quiet ambient room noise typically measures $\text{RMS} \in [0.005, 0.02]$.
- Conversational human speech at $40\text{ cm}$ from a laptop microphone typically measures $\text{RMS} \in [0.08, 0.25]$.
- The static threshold is pinned at a minimum of **$0.22$** (`max(0.22, noise_floor * 3.8)`):
  - **Quiet Speech:** Normal or hesitant utterances ($\text{RMS} \approx 0.12 - 0.18$) will **fail to trigger barge-in**.
  - **Loud Speech:** Intentional, firm interruptions ("Maven!", "Stop!") ($\text{RMS} > 0.22$) trigger interruption within one audio frame ($\le 40\text{ms}$).

---

## 3. Acoustic Environment Evaluation Matrix

| Acoustic Condition | Signal Level (RMS) | Software Behavior | Architectural Verdict |
| :--- | :---: | :--- | :--- |
| **Normal Playback Silence** | $< 0.03$ | Retains `SPEAKING`, no interruption | **PASS** — Stable |
| **Background HVAC / Fan** | $0.02 - 0.05$ | Noise floor adapts, threshold remains $> 0.22$ | **PASS** — Stable |
| **Soft User Speech ("wait...")** | $0.10 - 0.18$ | Fails threshold, TTS keeps speaking | **DEFECT** — User ignored |
| **Firm User Speech ("Maven stop!")** | $0.25 - 0.40$ | Exceeds 0.22, interrupts TTS immediately | **PASS** — Interrupted |
| **High Speaker Volume (Echo)** | $> 0.22$ | Microphone captures chassis resonance | **RISK** — False self-interrupt |
| **Laptop Keyboard Clatter** | Spikes $> 0.25$ | Mechanical conduction triggers threshold | **RISK** — False interrupt |
| **Desk Bump / Book Drop** | Spikes $> 0.30$ | Low-frequency impulse triggers threshold | **RISK** — False interrupt |

---

## 4. Lifecycle & State Transition Defects

### The Post-Interrupt Black Hole
Look at [`session.py#L106-L111`](file:///home/firza-ilmi/Maverick-DevOS-evolution/maverick/voice/session.py#L106-L111):
```python
def interrupt(self) -> None:
    """Stop TTS speech and return session to IDLE immediately."""
    voice_logger.tts_interrupted()
    self.tts.stop()
    self._transition_to(VoiceState.INTERRUPTED)
    time.sleep(0.05)
    self._transition_to(VoiceState.IDLE)
```

1. **User Experience Defect:**
   - When a user interrupts ("Maven, cancel that and check the weather instead"), the onset triggers `interrupt()`.
   - The session halts TTS and transitions to `IDLE` after 50ms.
   - In `IDLE`, the engine is only scanning for the wake-word ("Maven").
   - The audio chunk that triggered the interrupt was discarded.
   - The remainder of the user's sentence ("cancel that and...") is received in `IDLE`, where the wake-word detector fails to match because "Maven" was already spoken.
   - Result: The user's command is completely lost. The assistant stops talking, but does nothing further.
2. **Double Logging Flaw:**
   - `voice_logger.tts_interrupted()` is called on line 152 of `session.py` and again inside `interrupt()` on line 107, resulting in duplicated audit log entries for every interruption.

---

## 5. Architectural Recommendations

To elevate this prototype to production-grade conversational barge-in:
1. **Direct-to-Listening Transition:** When interrupted by speech, transition directly to `VoiceState.LISTENING` with the triggering audio chunk pre-loaded into `_audio_buffer`, rather than resetting to `IDLE`.
2. **Acoustic Echo Cancellation (AEC):** Integrate WebRTC AEC3 or SpeexDSP echo cancellation to subtract the outbound TTS playback buffer from the inbound microphone stream. This will allow lowering the speech detection threshold to $0.08$ without risk of self-interruption.
3. **Spectral Voice Activity Detector (VAD):** Replace raw RMS thresholding with a neural VAD (e.g. Silero VAD) to distinguish actual human phonemes from chassis keyboard taps or ambient impulse thumps.

---

## 6. Audit Verdict

| Criteria | Status |
| :--- | :--- |
| **Functional Interruption** | **WORKING** (for loud voice commands) |
| **Audio Device Recovery** | **SOUND** (`tts.stop()` cleanly halts playback stream) |
| **Conversational Continuity** | **DEFECTIVE** (drops user command; returns to IDLE) |
| **Acoustic Robustness** | **HEURISTIC** (vulnerable to high speaker volume & chassis taps) |

**Audit Recommendation:** Document as an experimental heuristic barge-in feature; do not market as full full-duplex conversational AI until WebRTC AEC and direct-to-listening buffering are added.
