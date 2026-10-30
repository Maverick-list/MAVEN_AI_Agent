"""Maverick DevOS - Headless Background Voice Assistant Daemon."""

import os
import signal
import sys
import threading
import time
from typing import Any, Dict, Optional, Tuple

from maverick.voice.config import VoiceConfig
from maverick.voice.controller import VoiceController
from maverick.voice.observability import voice_logger
from maverick.voice.session import VoiceSession, VoiceState
from maverick.voice.tts import detect_speech_language


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
            trigger_src = getattr(self.session, "last_trigger_source", "wake_word")
            ack_msg = "Yes, I'm listening."
            if trigger_src == "dual_clap":
                ack_msg = "Yes, I'm here. What can I do for you?"
            voice_logger.wake_acknowledgment(ack_msg)

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

        # Pre-warm OpenClaw voice session in background so Turn #1 avoids cold MCP bundle init
        if hasattr(self.controller, "warm_gateway_session"):
            threading.Thread(
                target=self.controller.warm_gateway_session,
                name="maven-openclaw-warmup",
                daemon=True,
            ).start()

        # Execute once-per-boot greeting asynchronously once audio subsystems settle
        if getattr(self.config, "boot_greeting_enabled", True):
            from maverick.voice.greeting import BootGreetingManager
            def _async_boot_greeting():
                time.sleep(1.2)
                try:
                    BootGreetingManager(self.config).execute_boot_greeting(self.session)
                except Exception as exc:
                    voice_logger.exception("boot_greeting", exc)
            threading.Thread(
                target=_async_boot_greeting,
                name="maven-boot-greeting",
                daemon=True,
            ).start()

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
                        t_turn_start = time.perf_counter()
                        wake_ms = float(getattr(self.session.wake_detector, "last_wake_ms", 0.0) or 0.0)

                        # Speech-to-Text invocation
                        t_stt = time.perf_counter()
                        voice_logger.stt_start(len(utterance))

                        try:
                            transcript = self.controller.stt.transcribe(utterance)
                        except Exception as exc:
                            voice_logger.stt_failure(str(exc))
                            self.session.rearm()
                            continue

                        duration_stt = time.perf_counter() - t_stt
                        stt_ms = round(duration_stt * 1000.0, 1)
                        stt_backend = str(getattr(self.controller.stt, "last_backend", "whisper_cli"))

                        if not transcript or not transcript.strip():
                            voice_logger.stt_empty(duration_stt, reason="silence_or_ambient_noise")
                            self.session.rearm()
                            continue

                        voice_logger.stt_complete(transcript.strip(), duration_stt)

                        # Intent Dispatch & Streaming Sentence-Chunked Execution
                        t_post_stt = time.perf_counter()
                        ttfa_box: Dict[str, Optional[float]] = {"ms": None}

                        def _mark_first_audio() -> None:
                            if ttfa_box["ms"] is None:
                                ttfa_box["ms"] = round((time.perf_counter() - t_turn_start) * 1000.0, 1)

                        local_res, stream_bundle = self.controller.dispatch_streaming_voice_turn(transcript)

                        active_eng = "elevenlabs"
                        if hasattr(self.session.tts, "get_status"):
                            active_eng = self.session.tts.get_status().get("active_engine", "elevenlabs")

                        if local_res is not None:
                            response_text = local_res.get("response", "")
                            tts_ttfb_ms = 0.0
                            tts_play_ms = 0.0
                            dns_ms = 0.0
                            tls_ms = 0.0
                            used_eng = active_eng
                            if response_text:
                                voice_logger.tts_start(response_text, engine=active_eng)
                                tts_stats = self.session.speak_stream([response_text], on_first_audio=_mark_first_audio)
                                used_eng = str(tts_stats.get("engine") or getattr(self.session.tts, "last_used_engine", active_eng))
                                tts_ttfb_ms = float(tts_stats.get("tts_ttfb_ms") or 0.0)
                                tts_play_ms = float(tts_stats.get("tts_playback_ms") or 0.0)
                                dns_ms = float(tts_stats.get("dns_ms") or 0.0)
                                tls_ms = float(tts_stats.get("tls_ms") or 0.0)
                                voice_logger.tts_complete(tts_play_ms / 1000.0, engine=used_eng)

                            total_turn_ms = round((time.perf_counter() - t_turn_start) * 1000.0, 1)
                            voice_logger.pipeline_latency(
                                {
                                    "route": "local_intent",
                                    "lang": detect_speech_language(response_text or transcript),
                                    "model_used": "local_intent_router",
                                    "stt_backend": stt_backend,
                                    "tts_engine": used_eng,
                                    "wake_ms": wake_ms,
                                    "stt_ms": stt_ms,
                                    "network_dns_ms": dns_ms,
                                    "network_tls_ms": tls_ms,
                                    "gateway_queue_ms": 0.0,
                                    "llm_ttft_ms": 0.0,
                                    "llm_first_sentence_ms": 0.0,
                                    "llm_total_ms": float(local_res.get("dispatch_ms") or 0.0),
                                    "llm_retries": 0,
                                    "tts_ttfb_ms": tts_ttfb_ms,
                                    "tts_playback_ms": tts_play_ms,
                                    "tts_chunks": 1 if response_text else 0,
                                    "ttfa_ms": ttfa_box["ms"] or total_turn_ms,
                                    "total_turn_ms": total_turn_ms,
                                }
                            )
                        elif stream_bundle is not None:
                            sent_iter, ai_metrics, cmd_text = stream_bundle
                            tts_stats = self.session.speak_stream(sent_iter, on_first_audio=_mark_first_audio)
                            full_spoken = str(tts_stats.get("full_text") or ai_metrics.get("full_response") or "").strip()
                            used_eng = str(tts_stats.get("engine") or getattr(self.session.tts, "last_used_engine", active_eng))
                            if full_spoken:
                                voice_logger.tts_start(full_spoken, engine=used_eng)
                                voice_logger.tts_complete(float(tts_stats.get("tts_playback_ms") or 0.0) / 1000.0, engine=used_eng)

                            model_used = str(ai_metrics.get("model_used") or self.config.model_id)
                            ai_status = str(ai_metrics.get("status") or "success")
                            self.controller.logger.log_action(
                                action_type="voice_conversation",
                                target=cmd_text,
                                status=ai_status,
                                confirmed=False,
                                details={
                                    "model": model_used,
                                    "configured_primary": self.config.model_id,
                                    "llm_ttft_ms": ai_metrics.get("llm_ttft_ms"),
                                    "llm_total_ms": ai_metrics.get("llm_total_ms"),
                                    "llm_retries": ai_metrics.get("llm_retries", 0),
                                },
                            )
                            total_turn_ms = round((time.perf_counter() - t_turn_start) * 1000.0, 1)
                            voice_logger.pipeline_latency(
                                {
                                    "route": str(ai_metrics.get("route") or "openclaw_stream"),
                                    "lang": str(ai_metrics.get("lang") or detect_speech_language(full_spoken or transcript)),
                                    "model_used": model_used,
                                    "stt_backend": stt_backend,
                                    "tts_engine": used_eng,
                                    "wake_ms": wake_ms,
                                    "stt_ms": stt_ms,
                                    "network_dns_ms": float(tts_stats.get("dns_ms") or 0.0),
                                    "network_tls_ms": float(tts_stats.get("tls_ms") or 0.0),
                                    "gateway_queue_ms": float(ai_metrics.get("gateway_queue_ms") or 0.0),
                                    "llm_ttft_ms": float(ai_metrics.get("llm_ttft_ms") or 0.0),
                                    "llm_first_sentence_ms": float(ai_metrics.get("llm_first_sentence_ms") or 0.0),
                                    "llm_total_ms": float(ai_metrics.get("llm_total_ms") or 0.0),
                                    "llm_retries": int(ai_metrics.get("llm_retries") or 0),
                                    "tts_ttfb_ms": float(tts_stats.get("tts_ttfb_ms") or 0.0),
                                    "tts_playback_ms": float(tts_stats.get("tts_playback_ms") or 0.0),
                                    "tts_chunks": int(tts_stats.get("chunks") or 0),
                                    "ttfa_ms": ttfa_box["ms"] or round((time.perf_counter() - t_post_stt) * 1000.0 + stt_ms, 1),
                                    "total_turn_ms": total_turn_ms,
                                }
                            )

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
