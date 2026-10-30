"""Automated QA & Security Test Suite for MAVEN JARVIS Control Center & ElevenLabs TTS."""

import io
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

from maverick.activity.logger import ActivityLogger
from maverick.dashboard.server import ControlCenterServer, TelemetryHub, _map_ui_state
from maverick.voice.audio import AudioCapture
from maverick.voice.config import (
    VoiceConfig,
    get_elevenlabs_api_key,
    load_voice_settings,
    save_voice_settings,
)
from maverick.voice.controller import VoiceController
from maverick.voice.elevenlabs_tts import (
    ElevenLabsError,
    ElevenLabsTTSProvider,
    inspect_elevenlabs_key_state,
)
from maverick.voice.observability import redact_sensitive_text
from maverick.voice.session import VoiceSession, VoiceState
from maverick.voice.stt import MockSTTProvider
from maverick.voice.tts import HybridTTSProvider, MockTTSProvider, SpeechDispatcherTTS
from maverick.voice.wakeword import MockWakeWordDetector


class _FakeHTTPStream:
    """Simulated chunked HTTP response stream for deterministic ElevenLabs streaming tests."""

    def __init__(self, payload: bytes = b"ID3\x04\x00fake_mp3_audio_frames" * 8):
        self._buf = io.BytesIO(payload)
        self.closed = False

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    def close(self) -> None:
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class TestControlCenterAndElevenLabs(unittest.TestCase):
    """Comprehensive Phase 2, Phase 3, and Phase 4 verification tests."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.settings_file = os.path.join(self.tmp_dir.name, "voice_settings.json")
        self.env_file = os.path.join(self.tmp_dir.name, "elevenlabs.env")
        self.conv_file = os.path.join(self.tmp_dir.name, "conversations.jsonl")

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    # 1. Loopback-Only Binding & Cross-Origin CSRF Defense
    def test_strict_loopback_binding_and_origin_protection(self) -> None:
        with self.assertRaises(ValueError):
            ControlCenterServer(host="0.0.0.0", port=0)
        with self.assertRaises(ValueError):
            ControlCenterServer(host="192.168.1.10", port=0)

        mock_tts = HybridTTSProvider(fallback=SpeechDispatcherTTS())
        hub = TelemetryHub(tts=mock_tts)
        hub.conversations.path = self.conv_file
        server = ControlCenterServer(host="127.0.0.1", port=0, hub=hub)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            # Foreign Origin POST must be blocked with 403
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/voice/stop",
                data=b"{}",
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://malicious.example.com",
                },
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=3)
            self.assertEqual(ctx.exception.code, 403)

            # Path traversal must not escape static root
            req_trav = urllib.request.Request(f"http://127.0.0.1:{port}/../../etc/passwd")
            with self.assertRaises(urllib.error.HTTPError) as ctx2:
                urllib.request.urlopen(req_trav, timeout=3)
            self.assertIn(ctx2.exception.code, (403, 404))
        finally:
            server.shutdown()
            server.server_close()

    # 2. Credential Redaction & Zero Secret Exposure
    def test_credential_redaction_and_secret_hygiene(self) -> None:
        fake_sk = "sk_9f8e7d6c5b4a3210fedcba9876543210abcdef"
        leaked_line = f"Error calling ElevenLabs with xi-api-key: {fake_sk} and api_key={fake_sk}"
        scrubbed = redact_sensitive_text(leaked_line)
        self.assertNotIn(fake_sk, scrubbed)
        self.assertIn("REDACTED", scrubbed)

        act_log_path = os.path.join(self.tmp_dir.name, "activity.jsonl")
        act = ActivityLogger(log_path=act_log_path)
        rec = act.log_action(
            "tts_test",
            target=f"token {fake_sk}",
            details={"elevenlabs_api_key": fake_sk, "voice_id": "onwK4e9ZLuTAKqWW03F9"},
        )
        raw_json = json.dumps(rec)
        self.assertNotIn(fake_sk, raw_json)

        # Distinguish 64-hex Key ID vs real sk_ secret key without exposing either
        with open(self.env_file, "w") as f:
            f.write("ELEVENLABS_API_KEY=" + ("a1" * 32) + "\n")
        with patch("maverick.voice.elevenlabs_tts.get_elevenlabs_api_key", side_effect=lambda: get_elevenlabs_api_key(self.env_file)):
            ok, code, _ = inspect_elevenlabs_key_state()
            self.assertFalse(ok)
            self.assertEqual(code, "key_id_not_secret")

        with open(self.env_file, "w") as f:
            f.write(f"ELEVENLABS_API_KEY={fake_sk}\n")
        with patch("maverick.voice.elevenlabs_tts.get_elevenlabs_api_key", side_effect=lambda: get_elevenlabs_api_key(self.env_file)):
            ok2, code2, _ = inspect_elevenlabs_key_state()
            self.assertTrue(ok2)
            self.assertEqual(code2, "configured")
            el = ElevenLabsTTSProvider()
            pub_json = json.dumps(el.get_public_status())
            self.assertNotIn(fake_sk, pub_json)

    # 3. ElevenLabs Streaming Synthesis (Indonesian & English) + Voice Settings
    @patch("urllib.request.urlopen")
    @patch.object(ElevenLabsTTSProvider, "_resolve_streaming_player_cmd", return_value=["/bin/cat"])
    @patch("subprocess.Popen")
    def test_elevenlabs_bilingual_synthesis_and_streaming(self, mock_popen, _mock_cmd, mock_urlopen) -> None:
        fake_sk = "sk_live_test_key_1234567890abcdef123456"
        captured_requests = []

        def _fake_urlopen(req, timeout=10):
            captured_requests.append(json.loads(req.data.decode("utf-8")))
            return _FakeHTTPStream()

        mock_urlopen.side_effect = _fake_urlopen
        mock_popen.side_effect = lambda *a, **kw: MagicMock(poll=lambda: 0, wait=lambda timeout=None: 0, stdin=io.BytesIO())

        with patch("maverick.voice.elevenlabs_tts.get_elevenlabs_api_key", return_value=fake_sk):
            el = ElevenLabsTTSProvider()
            # English synthesis
            ok_en = el.speak(
                "Good evening. All systems are operational.",
                wait=True,
                overrides={"stability": 0.65, "similarity_boost": 0.85, "style": 0.2, "speed": 1.05},
            )
            self.assertTrue(ok_en)

            # Indonesian synthesis
            ok_id = el.speak(
                "Selamat malam. Semua sistem Maven JARVIS berjalan optimal.",
                wait=True,
            )
            self.assertTrue(ok_id)

        self.assertEqual(len(captured_requests), 2)
        self.assertEqual(captured_requests[0]["model_id"], "eleven_multilingual_v2")
        self.assertEqual(captured_requests[0]["voice_settings"]["stability"], 0.65)
        self.assertEqual(captured_requests[0]["voice_settings"]["speed"], 1.05)
        self.assertIn("Selamat malam", captured_requests[1]["text"])

    # 4. Automatic TTS Fallback & Recovery After Network / Rate-Limit Failures
    @patch("urllib.request.urlopen")
    @patch.object(ElevenLabsTTSProvider, "_resolve_streaming_player_cmd", return_value=["/bin/cat"])
    @patch("subprocess.Popen")
    def test_tts_fallback_and_network_failure_recovery(self, mock_popen, _mock_cmd, mock_urlopen) -> None:
        fake_sk = "sk_live_test_key_1234567890abcdef123456"
        mock_popen.side_effect = lambda *a, **kw: MagicMock(poll=lambda: 0, wait=lambda timeout=None: 0, stdin=io.BytesIO())

        fallback_mock = MagicMock(spec=SpeechDispatcherTTS)
        fallback_mock.speak.return_value = True
        fallback_mock.is_speaking.return_value = False
        fallback_mock.is_available.return_value = True

        with patch("maverick.voice.elevenlabs_tts.get_elevenlabs_api_key", return_value=fake_sk):
            primary = ElevenLabsTTSProvider()
            hybrid = HybridTTSProvider(primary=primary, fallback=fallback_mock)

            # Case A: Network failure -> falls back to SpeechDispatcherTTS
            mock_urlopen.side_effect = urllib.error.URLError("Name or service not known")
            self.assertTrue(hybrid.speak("Network down test", wait=True))
            self.assertEqual(hybrid.last_used_engine, "speech_dispatcher")
            self.assertEqual(hybrid.last_fallback_reason, "network_error")

            # Case B: HTTP 429 Rate Limit -> falls back to SpeechDispatcherTTS
            err_body = io.BytesIO(b'{"detail":{"status":"quota_exceeded","message":"Quota reached"}}')
            mock_urlopen.side_effect = urllib.error.HTTPError(
                "https://api.elevenlabs.io/v1/text-to-speech/x/stream",
                429, "Too Many Requests", {}, err_body,
            )
            self.assertTrue(hybrid.speak("Quota test", wait=True))
            self.assertEqual(hybrid.last_used_engine, "speech_dispatcher")
            self.assertEqual(hybrid.last_fallback_reason, "rate_limited")

            # Case C: Timeout -> falls back to SpeechDispatcherTTS
            mock_urlopen.side_effect = socket.timeout("timed out")
            self.assertTrue(hybrid.speak("Timeout test", wait=True))
            self.assertEqual(hybrid.last_used_engine, "speech_dispatcher")
            self.assertEqual(hybrid.last_fallback_reason, "timeout")

            # Case D: Automatic Recovery when ElevenLabs API returns 200 OK again!
            mock_urlopen.side_effect = lambda req, timeout=10: _FakeHTTPStream()
            self.assertTrue(hybrid.speak("Recovered online", wait=True))
            self.assertEqual(hybrid.last_used_engine, "elevenlabs")
            self.assertIsNone(hybrid.last_fallback_reason)

    # 5. Live Dashboard Endpoints, SSE Stream, Daemon Buttons, Mic/Voice Tests & All 5 Visual States
    def test_dashboard_live_endpoints_and_all_visual_states(self) -> None:
        # Verify all 5 visual states map cleanly
        self.assertEqual(_map_ui_state("idle"), "idle")
        self.assertEqual(_map_ui_state("wake_word_detected"), "listening")
        self.assertEqual(_map_ui_state("listening"), "listening")
        self.assertEqual(_map_ui_state("processing"), "thinking")
        self.assertEqual(_map_ui_state("speaking"), "speaking")
        self.assertEqual(_map_ui_state("error"), "error")

        mock_fb = MagicMock(spec=SpeechDispatcherTTS)
        mock_fb.speak.return_value = True
        mock_fb.is_speaking.return_value = False
        mock_fb.is_available.return_value = True
        hybrid = HybridTTSProvider(fallback=mock_fb)

        hub = TelemetryHub(tts=hybrid)
        hub.conversations.path = self.conv_file
        server = ControlCenterServer(host="127.0.0.1", port=0, hub=hub)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        def _get(path: str):
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
                return r.status, r.read().decode("utf-8")

        def _post(path: str, payload: dict):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"},
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                return r.status, json.loads(r.read().decode("utf-8"))

        try:
            # Static UI serves index.html, styles.css, app.js
            st_html, html = _get("/")
            self.assertEqual(st_html, 200)
            self.assertIn("jarvis-core-canvas", html)

            # Real-time status snapshot contains live system, audio, gateway, security, TTS
            st_api, raw_snap = _get("/api/status")
            self.assertEqual(st_api, 200)
            snap = json.loads(raw_snap)
            self.assertEqual(snap["status"], "success")
            self.assertEqual(snap["security"]["bind_address"], "127.0.0.1")
            self.assertTrue(snap["security"]["whatsapp_disabled"])
            self.assertEqual(snap["ai_gateway"]["primary_model"], "google/gemini-2.5-flash")
            self.assertGreater(snap["system"]["memory"]["total_gb"], 1.0)

            # SSE stream emits live telemetry event frame
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/events", timeout=5) as sse_resp:
                line1 = sse_resp.readline().decode("utf-8")
                line2 = sse_resp.readline().decode("utf-8")
                self.assertIn("event: telemetry", line1)
                self.assertTrue(line2.startswith("data: "))

            # Test all 5 visual states on the live hub
            for st_name in ("idle", "listening", "thinking", "speaking", "error"):
                hub.set_transient_state(st_name, duration_sec=5.0)
                _, s_raw = _get("/api/status")
                self.assertEqual(json.loads(s_raw)["assistant"]["state"], st_name)
            hub.set_transient_state(None)

            # Daemon control buttons (mocked launcher calls so live PID 593226 is never killed!)
            with patch("maverick.dashboard.server.cmd_start", return_value=0) as m_start, \
                 patch("maverick.dashboard.server.cmd_stop", return_value=0) as m_stop, \
                 patch("maverick.dashboard.server.cmd_restart", return_value=0) as m_restart:
                self.assertEqual(_post("/api/daemon/start", {})[1]["status"], "success")
                self.assertEqual(_post("/api/daemon/stop", {})[1]["status"], "success")
                self.assertEqual(_post("/api/daemon/restart", {})[1]["status"], "success")
                m_start.assert_called_once()
                m_stop.assert_called_once()
                m_restart.assert_called_once()

            # Bounded real microphone test (0.5s capture)
            _, mic_res = _post("/api/audio/test-mic", {"duration_sec": 0.5})
            self.assertEqual(mic_res["status"], "success")
            self.assertGreaterEqual(mic_res["frames"], 5)

            # Bilingual Voice Test (EN & ID)
            _, vt_en = _post("/api/voice/test", {"lang": "en", "browser_audio": False})
            self.assertEqual(vt_en["status"], "success")
            _, vt_id = _post("/api/voice/test", {"lang": "id", "browser_audio": False})
            self.assertEqual(vt_id["status"], "success")

            # Confirmation gate enforced through /api/command
            _, gate_res = _post("/api/command", {"text": "open terminal", "confirmed": False, "speak": False})
            self.assertEqual(gate_res["status"], "confirmation_required")
            self.assertTrue(gate_res["requires_confirmation"])
        finally:
            server.shutdown()
            server.server_close()

    # 6. Ten Consecutive Bilingual Voice Interactions with Hybrid TTS
    def test_ten_consecutive_bilingual_voice_interactions_with_hybrid_tts(self) -> None:
        utterances = [
            "Maven, how much RAM is available?",
            "Maven, berapa sisa ram?",
            "Maven, check CPU usage",
            "Maven, status baterai",
            "Maven, what applications are running?",
            "Maven, aplikasi apa yang sedang berjalan?",
            "Maven, summarize desktop context",
            "Maven, ringkasan desktop",
            "Maven, battery status",
            "Maven, penggunaan cpu",
            "Hey Maven",
            "Halo Maven",
        ]

        cfg = VoiceConfig(silence_duration_seconds=0.05, listening_timeout_seconds=1.0)
        mock_audio = MagicMock(spec=AudioCapture)
        speech_chunk = b"\x30\x25" * 1024
        silence_chunk = b"\x00\x00" * 1024
        mock_wake = MockWakeWordDetector()

        fallback_tts = MockTTSProvider()
        fallback_tts.is_available = lambda: True  # type: ignore[attr-defined]
        primary_el = ElevenLabsTTSProvider(cfg)
        with patch.object(primary_el, "is_configured", return_value=False):
            hybrid_tts = HybridTTSProvider(config=cfg, primary=primary_el, fallback=fallback_tts)  # type: ignore[arg-type]
            session = VoiceSession(cfg, audio_capture=mock_audio, wake_detector=mock_wake, tts=hybrid_tts)
            stt = MockSTTProvider("")
            ctl = VoiceController(cfg, session=session, stt=stt, tts=hybrid_tts)

            for idx, phrase in enumerate(utterances):
                self.assertEqual(session.state, VoiceState.IDLE, f"Turn {idx + 1} did not start in IDLE")
                mock_wake.trigger()
                mock_audio.read_chunk.return_value = speech_chunk
                session.step()
                self.assertEqual(session.state, VoiceState.LISTENING)

                # Feed speech frame then trailing silence
                session.step()
                time.sleep(0.06)
                mock_audio.read_chunk.return_value = silence_chunk
                captured = session.step()
                self.assertIsNotNone(captured, f"Turn {idx + 1} failed to emit utterance")
                self.assertEqual(session.state, VoiceState.PROCESSING)

                stt.set_transcript(phrase)
                transcript = ctl.stt.transcribe(captured or b"")
                res = ctl.handle_voice_command(transcript)
                self.assertEqual(res["status"], "success", f"Turn {idx + 1} failed: {res}")
                self.assertTrue(session.speak(res["response"], wait=True))
                self.assertEqual(session.state, VoiceState.IDLE, f"Turn {idx + 1} failed to re-arm to IDLE")

        self.assertEqual(len(fallback_tts.spoken_texts), 12)

    @patch("subprocess.run")
    def test_openclaw_v2026_payload_and_model_not_found_sanitization(self, mock_run) -> None:
        """Verify OpenClaw 2026.10+ payloads[] JSON parsing and clean NOT_FOUND handling."""
        from maverick.voice.stt import WhisperCppSTTProvider

        ctl = VoiceController(VoiceConfig())
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "runId": "test-run-1",
                    "status": "ok",
                    "summary": "completed",
                    "result": {
                        "payloads": [{"text": "Systems nominal, Sir.", "mediaUrl": None}],
                        "meta": {"agentMeta": {"provider": "google", "model": "gemini-2.5-flash"}},
                    },
                }
            ),
            stderr="",
        )
        ok_res = ctl._query_openclaw("Status report")
        self.assertEqual(ok_res["status"], "success")
        self.assertEqual(ok_res["response"], "Systems nominal, Sir.")
        self.assertEqual(ok_res["model_used"], "google/gemini-2.5-flash")

        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=json.dumps(
                {
                    "ok": False,
                    "origin": "gateway",
                    "error": {
                        "type": "cli_error",
                        "message": "This model was not found. Choose another model in the Control UI. | NOT_FOUND",
                    },
                }
            ),
            stderr="",
        )
        err_res = ctl._query_openclaw("Hello")
        self.assertEqual(err_res["status"], "model_not_found")
        self.assertNotIn("| NOT_FOUND", err_res["response"])
        self.assertNotIn("Control UI", err_res["response"])

        # Whisper noise-hallucination filter checks
        self.assertTrue(WhisperCppSTTProvider.is_noise_hallucination("오케이 이리 와구!"))
        self.assertTrue(WhisperCppSTTProvider.is_noise_hallucination("Jangan, jangan, jangan, jangan, jangan."))
        self.assertFalse(WhisperCppSTTProvider.is_noise_hallucination("Hello Maven, how are you today?"))
        self.assertFalse(WhisperCppSTTProvider.is_noise_hallucination("Tolong jelaskan status proyek hari ini."))


if __name__ == "__main__":
    unittest.main()
