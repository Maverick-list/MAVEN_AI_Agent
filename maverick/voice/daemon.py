"""Maverick DevOS - Headless Background Voice Assistant Daemon."""

import os
import signal
import sys
import time
from typing import Optional, Tuple

from maverick.voice.config import VoiceConfig
from maverick.voice.controller import VoiceController
from maverick.voice.observability import voice_logger
from maverick.voice.session import VoiceSession, VoiceState


def _get_process_rss_mb() -> float:
    """Read process resident set size directly from /proc/self/statm."""
    try:
        with open("/proc/self/statm", "r") as f:
            parts = f.read().split()
            pages = int(parts[1])
            page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
            return (pages * page_size) / (1024 * 1024)
    except Exception:
        return 0.0


def _get_process_cpu_pct(last_time: float, last_ticks: int) -> Tuple[float, float, int]:
    """Calculate CPU usage percent over time interval from /proc/self/stat."""
    now = time.time()
    elapsed = max(0.001, now - last_time)
    try:
        with open("/proc/self/stat", "r") as f:
            fields = f.read().split()
            ticks = int(fields[13]) + int(fields[14])
            clk_tck = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
            cpu_seconds = (ticks - last_ticks) / clk_tck
            cpu_pct = max(0.0, min(100.0, (cpu_seconds / elapsed) * 100.0))
            return cpu_pct, now, ticks
    except Exception:
        return 0.0, now, last_ticks


class VoiceDaemon:
    """
    Continuous headless voice assistant service.
    Runs background audio capture, wake-word detection, speech-to-text,
    bilingual intent dispatch, and verbal TTS feedback without requiring a TTY.
    Emits structured, privacy-safe, non-blocking telemetry.
    """

    def __init__(
        self,
        config: Optional[VoiceConfig] = None,
        controller: Optional[VoiceController] = None,
    ):
        self.config = config or VoiceConfig()
        self.controller = controller or VoiceController(self.config)
        self.session = self.controller.session
        self._running = False
        self._frames_processed = 0

        # Wire state callback for structured lifecycle events
        self.session.add_state_callback(self._on_state_change)

    def _on_state_change(self, state: VoiceState) -> None:
        """Handle session state transitions."""
        if state == VoiceState.WAKE_WORD_DETECTED:
            voice_logger.wake_acknowledgment("Yes, I'm listening.")

    def stop(self, *args) -> None:
        """Signal daemon to gracefully shut down."""
        self._running = False

    def run(self) -> None:
        """Execute the continuous background voice interaction loop."""
        self._running = True
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

        # 1. Daemon Lifecycle Startup Log
        pid = os.getpid()
        profile = os.getenv("MAVERICK_PROFILE", "light")
        voice_logger.startup(
            pid=pid,
            profile=profile,
            device=self.config.device_input or "default",
            model_id=self.config.model_id,
            whisper_bin=self.config.whisper_bin_path,
        )

        # 2. Audio Capture Startup Log
        self.session.audio.start()
        voice_logger.audio_device_init(
            backend="pipewire/alsa",
            device=self.config.device_input or "default",
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
        )

        last_cpu_time = time.time()
        last_cpu_ticks = 0
        cpu_pct = 0.0

        try:
            while self._running:
                self._frames_processed += 1

                # Heartbeat Telemetry (rate-limited every 5.0 seconds inside VoiceLogger)
                noise_floor = getattr(self.session.wake_detector, "_noise_floor", 0.0) or 0.0
                state_name = self.session.state.value
                rss_mb = _get_process_rss_mb()
                cpu_pct, last_cpu_time, last_cpu_ticks = _get_process_cpu_pct(last_cpu_time, last_cpu_ticks)

                voice_logger.heartbeat(
                    state=state_name,
                    frames=self._frames_processed,
                    rms=noise_floor,
                    noise_floor=noise_floor,
                    is_burst=(state_name == "listening"),
                    rss_mb=rss_mb,
                    cpu_pct=cpu_pct,
                )

                try:
                    # Execute one step in voice session
                    utterance = self.session.step()

                    if utterance:
                        # Speech-to-Text invocation
                        t_stt = time.time()
                        voice_logger.stt_start(len(utterance))

                        try:
                            transcript = self.controller.stt.transcribe(utterance)
                        except Exception as exc:
                            voice_logger.stt_failure(str(exc))
                            self.session.rearm()
                            continue

                        duration_stt = time.time() - t_stt

                        if not transcript or not transcript.strip():
                            voice_logger.stt_empty(duration_stt, reason="silence_or_ambient_noise")
                            self.session.rearm()
                            continue

                        voice_logger.stt_complete(transcript.strip(), duration_stt)

                        # Intent Dispatch and Action Execution
                        res = self.controller.handle_voice_command(transcript)
                        response_text = res.get("response", "")

                        # Verbal Feedback
                        if response_text:
                            active_eng = "elevenlabs"
                            if hasattr(self.session.tts, "get_status"):
                                active_eng = self.session.tts.get_status().get("active_engine", "elevenlabs")
                            voice_logger.tts_start(response_text, engine=active_eng)
                            t_tts = time.time()
                            self.session.speak(response_text, wait=True)
                            used_eng = getattr(self.session.tts, "last_used_engine", active_eng)
                            voice_logger.tts_complete(time.time() - t_tts, engine=used_eng)

                        # Re-arm continuous listening and flush microphone pipe
                        if hasattr(self.session.audio, "flush"):
                            self.session.audio.flush()
                        self.session.rearm()

                except Exception as iter_err:
                    voice_logger.exception("VoiceDaemon.step", iter_err)
                    if hasattr(self.session.audio, "flush"):
                        self.session.audio.flush()
                    self.session.rearm()

                # Sleep small delta to yield CPU during IDLE
                time.sleep(0.01)

        except Exception as e:
            voice_logger.exception("VoiceDaemon.run", e)
        finally:
            self.session.audio.stop()
            self.session.reset()
            voice_logger.shutdown(reason="signal" if not self._running else "error")


def run_daemon() -> None:
    """Entry point for maverick.cli voice daemon."""
    daemon = VoiceDaemon()
    daemon.run()


if __name__ == "__main__":
    run_daemon()
