"""Maverick DevOS - Low-Latency Voice Intelligence Pipeline Unit Tests."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
import urllib.request

from maverick.dashboard.server import ControlCenterServer, TelemetryHub
from maverick.voice.audio import AudioCapture
from maverick.voice.config import VoiceConfig
from maverick.voice.controller import (
    VoiceController,
    clean_spoken_text,
    split_meaningful_sentences,
)
from maverick.voice.elevenlabs_tts import ElevenLabsError, ElevenLabsTTSProvider
from maverick.voice.observability import get_latency_summary, record_turn_latency
from maverick.voice.session import VoiceSession, VoiceState
from maverick.voice.stt import WhisperCppSTTProvider
from maverick.voice.tts import HybridTTSProvider, MockTTSProvider
from maverick.voice.wakeword import MockWakeWordDetector


class _MockWhisperHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        _ = self.rfile.read(length)
        body = json.dumps({"text": " Buka Visual Studio Code "}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _MockOpenClawSSEHandler(BaseHTTPRequestHandler):
    mode = "normal"
    seen_headers = []

    def log_message(self, format, *args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        _ = self.rfile.read(length)
        _MockOpenClawSSEHandler.seen_headers.append(dict(self.headers))

        if _MockOpenClawSSEHandler.mode == "raw_error":
            err = json.dumps(
                {"error": {"message": "404 NOT_FOUND models/gemini-bad-id trace=0xdeadbeef"}}
            ).encode("utf-8")
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        deltas = [
            "Good afternoon, sir, all primary cores are nominal. ",
            "Secondary workstation subsystems are ready for your instructions.",
        ]
        for d in deltas:
            pkt = json.dumps({"choices": [{"delta": {"content": d}}]})
            self.wfile.write(f"data: {pkt}\n\n".encode("utf-8"))
            self.wfile.flush()
            time.sleep(0.01)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class TestLowLatencyVoicePipeline(unittest.TestCase):
    """Verify streaming LLM, sentence-chunked TTS, warm whisper-server STT, and latency telemetry."""

    def test_sentence_chunking_and_markdown_cleanup(self):
        raw = "**Good afternoon**, Dr. Stark. All systems are online! Preparing diagnostics"
        ready, rem = split_meaningful_sentences(raw, flush=False)
        self.assertEqual(
            ready,
            [
                "Good afternoon, Dr. Stark.",
                "All systems are online!",
            ],
        )
        self.assertEqual(rem, "Preparing diagnostics")

        tail, rem2 = split_meaningful_sentences(rem, flush=True)
        self.assertEqual(tail, ["Preparing diagnostics"])
        self.assertEqual(rem2, "")
        self.assertEqual(clean_spoken_text("Use `git status` **now**"), "Use git status now")

    def test_whisper_server_fast_path_and_hallucination_guard(self):
        srv = HTTPServer(("127.0.0.1", 0), _MockWhisperHTTPHandler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            cfg = VoiceConfig(whisper_server_host="127.0.0.1", whisper_server_port=port, use_whisper_server=True)
            stt = WhisperCppSTTProvider(config=cfg)
            with patch.object(stt, "is_available", return_value=True):
                pcm = b"\x10\x00" * 16000  # 1.0s 16kHz PCM
                text = stt.transcribe(pcm, language="id")
                self.assertEqual(text, "Buka Visual Studio Code")
                self.assertEqual(stt.last_backend, "whisper_server")
                self.assertGreaterEqual(stt.last_stt_ms, 0.0)
            stt.close()
        finally:
            srv.shutdown()
            srv.server_close()

        self.assertTrue(
            WhisperCppSTTProvider.is_noise_hallucination(
                "Please subscribe to our channel and press the bell icon."
            )
        )

    def test_streaming_openclaw_sse_and_sanitized_errors(self):
        _MockOpenClawSSEHandler.seen_headers.clear()
        _MockOpenClawSSEHandler.mode = "normal"
        srv = HTTPServer(("127.0.0.1", 0), _MockOpenClawSSEHandler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            cfg = VoiceConfig(openclaw_http_host="127.0.0.1", openclaw_http_port=port)
            ctl = VoiceController(config=cfg, tts=MockTTSProvider())
            metrics = {}
            with patch("maverick.voice.controller.resolve_openclaw_gateway_token", return_value="test-token"):
                chunks = list(ctl.stream_openclaw("Give me a quick status check.", metrics_out=metrics))

            self.assertEqual(len(chunks), 2)
            self.assertIn("Good afternoon", chunks[0])
            self.assertEqual(metrics["route"], "openclaw_stream")
            self.assertEqual(metrics["status"], "success")
            self.assertIsNotNone(metrics["llm_ttft_ms"])
            self.assertLessEqual(metrics["llm_ttft_ms"], metrics["llm_total_ms"])

            # Verify raw provider errors are NEVER spoken aloud verbatim
            _MockOpenClawSSEHandler.mode = "raw_error"
            err_metrics = {}
            with patch("maverick.voice.controller.resolve_openclaw_gateway_token", return_value="test-token"):
                err_chunks = list(ctl.stream_openclaw("Test broken model.", metrics_out=err_metrics))

            spoken = " ".join(err_chunks)
            self.assertNotIn("0xdeadbeef", spoken)
            self.assertNotIn("models/gemini-bad-id", spoken)
            self.assertEqual(err_metrics["status"], "model_not_found")
        finally:
            srv.shutdown()
            srv.server_close()

    def test_session_speak_stream_rearms_microphone_reliably(self):
        cfg = VoiceConfig()
        audio = AudioCapture(config=cfg)
        audio.flush = MagicMock()
        wake = MockWakeWordDetector()
        tts = MockTTSProvider()
        session = VoiceSession(config=cfg, audio_capture=audio, wake_detector=wake, tts=tts)

        first_audio_events = []
        observed_states = []

        orig_stream = tts.speak_stream

        def _spy_stream(sentences, **kwargs):
            observed_states.append(session.state)
            return orig_stream(sentences, **kwargs)

        tts.speak_stream = _spy_stream  # type: ignore[method-assign]

        info = session.speak_stream(
            iter(["First sentence ready.", "Second sentence follows."]),
            on_first_audio=lambda: first_audio_events.append(time.perf_counter()),
        )
        self.assertTrue(info["ok"])
        self.assertEqual(info["chunks"], 2)
        self.assertEqual(len(first_audio_events), 1)
        self.assertEqual(observed_states, [VoiceState.SPEAKING])
        self.assertEqual(session.state, VoiceState.IDLE)
        self.assertGreaterEqual(audio.flush.call_count, 1)

    def test_hybrid_tts_speak_stream_falls_back_cleanly(self):
        cfg = VoiceConfig()
        primary = MagicMock(spec=ElevenLabsTTSProvider)
        primary.is_configured.return_value = True
        primary.speak_stream.return_value = {"ok": False, "error_code": "rate_limited", "chunks": 0}
        fallback = MockTTSProvider()

        hybrid = HybridTTSProvider(config=cfg, primary=primary, fallback=fallback)
        with patch.object(hybrid, "_preferred_engine", return_value="elevenlabs"):
            res = hybrid.speak_stream(["Kalimat pertama.", "Kalimat kedua."])

        self.assertTrue(res["ok"])
        self.assertEqual(res["engine"], "speech_dispatcher")
        self.assertEqual(len(fallback.spoken_texts), 2)

    def test_latency_telemetry_persistence_and_dashboard_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            lat_file = os.path.join(tmp, "latency.jsonl")
            record_turn_latency(
                {
                    "route": "openclaw_stream",
                    "lang": "en",
                    "model_used": "google/gemini-2.5-flash",
                    "stt_backend": "whisper_server",
                    "tts_engine": "elevenlabs",
                    "tts_chunks": 2,
                    "wake_ms": 310.4,
                    "stt_ms": 392.1,
                    "network_dns_ms": 0.0,
                    "network_tls_ms": 0.0,
                    "gateway_queue_ms": 740.0,
                    "llm_ttft_ms": 1350.2,
                    "llm_first_sentence_ms": 1620.5,
                    "llm_total_ms": 2180.0,
                    "llm_retries": 0,
                    "tts_ttfb_ms": 640.0,
                    "tts_playback_ms": 3200.0,
                    "ttfa_ms": 2260.5,
                    "total_turn_ms": 5852.6,
                },
                path=lat_file,
            )
            mode = os.stat(lat_file).st_mode & 0o777
            self.assertEqual(mode, 0o600)

            summary = get_latency_summary(limit=10, path=lat_file)
            self.assertEqual(summary["turn_count"], 1)
            self.assertEqual(summary["ai_turn_count"], 1)
            self.assertAlmostEqual(summary["averages_ms"]["ttfa_ms"], 2260.5, places=1)

        mock_primary = MagicMock(spec=ElevenLabsTTSProvider)
        mock_primary.get_public_status.return_value = {
            "provider": "elevenlabs",
            "configured": True,
            "last_error_code": None,
            "voice_name": "Daniel",
            "model_id": "eleven_multilingual_v2",
        }
        hub = TelemetryHub(tts=HybridTTSProvider(primary=mock_primary, fallback=MockTTSProvider()))
        srv = ControlCenterServer(host="127.0.0.1", port=0, hub=hub)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=5.0) as resp:
                snap = json.loads(resp.read().decode("utf-8"))
            self.assertIn("latency", snap)
            self.assertIn("averages_ms", snap["latency"])

            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/latency", timeout=5.0) as resp2:
                lat_payload = json.loads(resp2.read().decode("utf-8"))
            self.assertEqual(lat_payload["status"], "success")
            self.assertIn("turn_count", lat_payload["latency"])
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
