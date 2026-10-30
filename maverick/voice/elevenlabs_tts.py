"""Maverick DevOS - ElevenLabs Streaming Neural TTS Provider."""

import http.client
import io
import json
import os
import queue
import re
import shutil
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple

from maverick.voice.config import (
    DEFAULT_ELEVENLABS_MODEL_ID,
    DEFAULT_ELEVENLABS_VOICE_ID,
    VoiceConfig,
    get_elevenlabs_api_key,
    load_voice_settings,
)
from maverick.voice.observability import redact_sensitive_text

ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"

# Curated calm, intelligent, JARVIS-inspired voices (all support eleven_multilingual_v2 EN & ID)
JARVIS_VOICE_PRESETS: List[Dict[str, str]] = [
    {
        "voice_id": "onwK4e9ZLuTAKqWW03F9",
        "name": "Daniel (JARVIS Classic)",
        "accent": "British",
        "description": "Calm, authoritative, composed British intelligence cadence",
    },
    {
        "voice_id": "JBFqnCBsd6RMkjVDRZzb",
        "name": "George (Executive)",
        "accent": "British",
        "description": "Warm, articulate British resonance",
    },
    {
        "voice_id": "nPczCjzI2devNBz1zQrb",
        "name": "Brian (Deep Command)",
        "accent": "American",
        "description": "Deep, confident, crisp studio voice",
    },
    {
        "voice_id": "IKne3meq5aSn9XLyUdCD",
        "name": "Charlie (Natural)",
        "accent": "Australian",
        "description": "Smooth, natural bilingual delivery",
    },
]

SUPPORTED_ELEVENLABS_MODELS: List[Dict[str, str]] = [
    {
        "model_id": "eleven_multilingual_v2",
        "name": "Eleven Multilingual v2 (Best Quality · ID & EN)",
    },
    {
        "model_id": "eleven_flash_v2_5",
        "name": "Eleven Flash v2.5 (Ultra-Low Latency · 75ms · ID & EN)",
    },
    {
        "model_id": "eleven_turbo_v2_5",
        "name": "Eleven Turbo v2.5 (Balanced Speed & Nuance · ID & EN)",
    },
]

_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class ElevenLabsError(Exception):
    """Privacy-safe error raised when ElevenLabs synthesis cannot complete."""

    def __init__(self, code: str, message: str, http_status: Optional[int] = None):
        self.code = code
        self.safe_message = redact_sensitive_text(message)
        self.http_status = http_status
        super().__init__(self.safe_message)


def inspect_elevenlabs_key_state() -> Tuple[bool, str, str]:
    """
    Validate presence and format of ELEVENLABS_API_KEY without exposing its value.
    Returns (is_valid_format, status_code, human_hint).
    """
    raw_key = get_elevenlabs_api_key()
    if not raw_key:
        return (
            False,
            "missing_api_key",
            "Set ELEVENLABS_API_KEY (starting with sk_) in ~/.config/maverick/elevenlabs.env",
        )
    if _HEX64_RE.match(raw_key) and not raw_key.startswith("sk_"):
        return (
            False,
            "key_id_not_secret",
            "Configured value is a 64-char Key ID; replace with secret key starting with 'sk_'",
        )
    if len(raw_key) < 16:
        return (
            False,
            "invalid_key_format",
            "ELEVENLABS_API_KEY appears truncated; expected 'sk_...' secret key",
        )
    return (True, "configured", "ElevenLabs API key configured via secure environment")


class ElevenLabsTTSProvider:
    """
    Streaming neural Text-to-Speech provider powered by ElevenLabs.
    Supports Indonesian and English via Multilingual v2 / Flash v2.5,
    low-latency chunked playback over PipeWire/GStreamer, non-blocking async mode,
    and strict credential isolation.
    """

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or VoiceConfig()
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._player_proc: Optional[subprocess.Popen] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._is_speaking = False
        self._last_error: Optional[str] = None
        self._last_error_code: Optional[str] = None
        self._last_latency_ms: Optional[float] = None
        self._last_dns_ms: float = 0.0
        self._last_tcp_ms: float = 0.0
        self._last_tls_ms: float = 0.0
        self._last_playback_ms: float = 0.0
        self._conn_lock = threading.Lock()
        self._https_conn: Optional[http.client.HTTPSConnection] = None
        self._ssl_ctx = ssl.create_default_context()

    def _effective_params(self, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Merge config defaults, live saved voice_settings.json, and optional per-call overrides."""
        saved = load_voice_settings()
        ovr = overrides or {}

        voice_id = str(
            ovr.get("voice_id")
            or saved.get("elevenlabs_voice_id")
            or os.environ.get("ELEVENLABS_VOICE_ID")
            or self.config.elevenlabs_voice_id
            or DEFAULT_ELEVENLABS_VOICE_ID
        ).strip()

        model_id = str(
            ovr.get("model_id")
            or saved.get("elevenlabs_model_id")
            or os.environ.get("ELEVENLABS_MODEL_ID")
            or self.config.elevenlabs_model_id
            or DEFAULT_ELEVENLABS_MODEL_ID
        ).strip()

        def _clamp(val: Any, default: float, lo: float, hi: float) -> float:
            try:
                return round(max(lo, min(hi, float(val))), 2)
            except (TypeError, ValueError):
                return default

        stability = _clamp(
            ovr.get("stability", saved.get("elevenlabs_stability", self.config.elevenlabs_stability)),
            0.55, 0.0, 1.0,
        )
        similarity_boost = _clamp(
            ovr.get("similarity_boost", saved.get("elevenlabs_similarity_boost", self.config.elevenlabs_similarity_boost)),
            0.80, 0.0, 1.0,
        )
        style = _clamp(
            ovr.get("style", saved.get("elevenlabs_style", self.config.elevenlabs_style)),
            0.15, 0.0, 1.0,
        )
        speed = _clamp(
            ovr.get("speed", saved.get("elevenlabs_speed", self.config.elevenlabs_speed)),
            1.0, 0.7, 1.2,
        )
        speaker_boost = bool(
            ovr.get(
                "use_speaker_boost",
                saved.get("elevenlabs_use_speaker_boost", self.config.elevenlabs_use_speaker_boost),
            )
        )

        return {
            "voice_id": voice_id,
            "model_id": model_id,
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "speed": speed,
            "use_speaker_boost": speaker_boost,
        }

    def is_configured(self) -> bool:
        ok, _, _ = inspect_elevenlabs_key_state()
        return ok

    def get_public_status(self) -> Dict[str, Any]:
        """Return non-sensitive status metadata safe for dashboard display."""
        key_ok, key_code, key_hint = inspect_elevenlabs_key_state()
        params = self._effective_params()
        preset_map = {p["voice_id"]: p["name"] for p in JARVIS_VOICE_PRESETS}
        voice_name = preset_map.get(params["voice_id"], f"Custom ({params['voice_id'][:8]}…)")
        player_cmd = self._resolve_streaming_player_cmd()

        return {
            "provider": "elevenlabs",
            "configured": key_ok,
            "key_status": key_code,
            "hint": key_hint,
            "voice_id": params["voice_id"],
            "voice_name": voice_name,
            "model_id": params["model_id"],
            "settings": {
                "stability": params["stability"],
                "similarity_boost": params["similarity_boost"],
                "style": params["style"],
                "speed": params["speed"],
                "use_speaker_boost": params["use_speaker_boost"],
            },
            "streaming_supported": player_cmd is not None,
            "streaming_backend": player_cmd[0] if player_cmd else None,
            "last_error_code": self._last_error_code,
            "last_error": self._last_error,
            "last_latency_ms": self._last_latency_ms,
            "last_dns_ms": self._last_dns_ms,
            "last_tls_ms": self._last_tls_ms,
            "last_playback_ms": self._last_playback_ms,
            "presets": JARVIS_VOICE_PRESETS,
            "models": SUPPORTED_ELEVENLABS_MODELS,
        }

    def is_speaking(self) -> bool:
        with self._lock:
            if self._player_proc and self._player_proc.poll() is None:
                return True
            return self._is_speaking

    @staticmethod
    def _resolve_streaming_player_cmd() -> Optional[List[str]]:
        """Locate an installed Linux streaming MP3 stdin audio player (PipeWire/GStreamer/FFmpeg/mpv)."""
        gst = shutil.which("gst-launch-1.0")
        if gst:
            return [
                gst,
                "-q",
                "fdsrc", "fd=0",
                "!", "decodebin",
                "!", "audioconvert",
                "!", "audioresample",
                "!", "autoaudiosink",
            ]
        ffplay = shutil.which("ffplay")
        if ffplay:
            return [ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet", "-i", "pipe:0"]
        mpv = shutil.which("mpv")
        if mpv:
            return [mpv, "--no-video", "--really-quiet", "-"]
        return None

    def _open_keepalive_stream(
        self,
        path_and_query: str,
        payload: bytes,
        headers: Dict[str, str],
    ) -> http.client.HTTPResponse:
        """
        Dispatch TTS POST over a persistent HTTP/1.1 Keep-Alive TLS connection to api.elevenlabs.io,
        measuring DNS, TCP, and TLS handshake latency separately on cold connect and reusing the
        warm socket (0 ms handshake) on subsequent sentence chunks.
        """
        host = "api.elevenlabs.io"
        timeout = float(self.config.elevenlabs_timeout_sec)

        for attempt in range(2):
            conn = self._https_conn
            reused = conn is not None and getattr(conn, "sock", None) is not None
            if not reused:
                t_dns = time.perf_counter()
                infos = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
                dns_ms = (time.perf_counter() - t_dns) * 1000.0
                target_ip = infos[0][4][0]

                t_tcp = time.perf_counter()
                raw_sock = socket.create_connection((target_ip, 443), timeout=timeout)
                raw_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                tcp_ms = (time.perf_counter() - t_tcp) * 1000.0

                t_tls = time.perf_counter()
                tls_sock = self._ssl_ctx.wrap_socket(raw_sock, server_hostname=host)
                tls_ms = (time.perf_counter() - t_tls) * 1000.0

                conn = http.client.HTTPSConnection(host, 443, timeout=timeout, context=self._ssl_ctx)
                conn.sock = tls_sock
                self._https_conn = conn
                self._last_dns_ms = round(dns_ms, 1)
                self._last_tcp_ms = round(tcp_ms, 1)
                self._last_tls_ms = round(tls_ms, 1)
            else:
                self._last_dns_ms = 0.0
                self._last_tcp_ms = 0.0
                self._last_tls_ms = 0.0

            try:
                req_headers = dict(headers)
                req_headers["Connection"] = "keep-alive"
                conn.request("POST", path_and_query, body=payload, headers=req_headers)
                resp = conn.getresponse()
                if resp.status >= 400:
                    raw_err = resp.read()
                    http_err = urllib.error.HTTPError(
                        f"https://{host}{path_and_query}",
                        resp.status,
                        resp.reason,
                        resp.headers,
                        io.BytesIO(raw_err),
                    )
                    raise http_err
                return resp
            except urllib.error.HTTPError:
                raise
            except (http.client.HTTPException, ConnectionError, OSError) as exc:
                try:
                    conn.close()
                except Exception:
                    pass
                self._https_conn = None
                if attempt == 0 and reused:
                    continue
                if isinstance(exc, (socket.timeout, TimeoutError)):
                    raise
                raise urllib.error.URLError(exc) from None

        raise urllib.error.URLError("Failed to establish ElevenLabs connection")

    def stream_mp3_chunks(
        self,
        text: str,
        overrides: Optional[Dict[str, Any]] = None,
        chunk_bytes: int = 4096,
    ) -> Iterator[bytes]:
        """
        Stream MP3 audio chunks from ElevenLabs /stream endpoint.
        Raises ElevenLabsError on missing credentials, auth errors, rate limits, or timeouts.
        """
        clean_text = (text or "").strip()
        if not clean_text:
            raise ElevenLabsError("empty_text", "Cannot synthesize empty text")

        key_ok, key_code, key_hint = inspect_elevenlabs_key_state()
        if not key_ok:
            self._record_error(key_code, key_hint)
            raise ElevenLabsError(key_code, key_hint)

        api_key = get_elevenlabs_api_key()
        params = self._effective_params(overrides)
        voice_id = urllib.parse.quote(params["voice_id"], safe="")
        opt_lat = int(getattr(self.config, "elevenlabs_optimize_streaming_latency", 3))
        path_and_query = (
            f"/v1/text-to-speech/{voice_id}/stream"
            f"?output_format=mp3_44100_128&optimize_streaming_latency={opt_lat}"
        )
        url = f"https://api.elevenlabs.io{path_and_query}"

        voice_settings: Dict[str, Any] = {
            "stability": params["stability"],
            "similarity_boost": params["similarity_boost"],
            "style": params["style"],
            "use_speaker_boost": params["use_speaker_boost"],
        }
        if abs(params["speed"] - 1.0) >= 0.01:
            voice_settings["speed"] = params["speed"]

        payload = json.dumps(
            {
                "text": clean_text,
                "model_id": params["model_id"],
                "voice_settings": voice_settings,
            }
        ).encode("utf-8")

        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
            "User-Agent": "Maven-JARVIS-ControlCenter/1.1",
        }

        use_mocked_urlopen = getattr(urllib.request.urlopen, "__module__", "") != "urllib.request"
        t0 = time.perf_counter()

        if use_mocked_urlopen:
            req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
            try:
                resp = urllib.request.urlopen(req, timeout=self.config.elevenlabs_timeout_sec)
            except urllib.error.HTTPError as http_err:
                code, msg = self._classify_http_error(http_err)
                self._record_error(code, msg)
                raise ElevenLabsError(code, msg, http_status=http_err.code) from None
            except (socket.timeout, TimeoutError):
                msg = "ElevenLabs streaming request timed out"
                self._record_error("timeout", msg)
                raise ElevenLabsError("timeout", msg) from None
            except urllib.error.URLError as url_err:
                reason = getattr(url_err, "reason", None)
                if isinstance(reason, (socket.timeout, TimeoutError)):
                    msg = "ElevenLabs connection timed out"
                    self._record_error("timeout", msg)
                    raise ElevenLabsError("timeout", msg) from None
                msg = f"Network error reaching ElevenLabs: {type(reason).__name__ if reason else 'URLError'}"
                self._record_error("network_error", msg)
                raise ElevenLabsError("network_error", msg) from None
            except Exception as exc:
                msg = f"Unexpected ElevenLabs transport error: {type(exc).__name__}"
                self._record_error("transport_error", msg)
                raise ElevenLabsError("transport_error", msg) from None

            try:
                first_chunk = True
                while True:
                    if self._cancel_event.is_set():
                        break
                    chunk = resp.read(chunk_bytes)
                    if not chunk:
                        break
                    if first_chunk:
                        self._last_latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                        self._last_error = None
                        self._last_error_code = None
                        first_chunk = False
                    yield chunk
            except (socket.timeout, TimeoutError):
                msg = "ElevenLabs audio stream interrupted by timeout"
                self._record_error("timeout", msg)
                raise ElevenLabsError("timeout", msg) from None
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
            return

        # Production Keep-Alive TLS Path
        with self._conn_lock:
            try:
                resp = self._open_keepalive_stream(path_and_query, payload, headers)
            except urllib.error.HTTPError as http_err:
                code, msg = self._classify_http_error(http_err)
                self._record_error(code, msg)
                raise ElevenLabsError(code, msg, http_status=http_err.code) from None
            except (socket.timeout, TimeoutError):
                msg = "ElevenLabs streaming request timed out"
                self._record_error("timeout", msg)
                raise ElevenLabsError("timeout", msg) from None
            except urllib.error.URLError as url_err:
                reason = getattr(url_err, "reason", None)
                if isinstance(reason, (socket.timeout, TimeoutError)):
                    msg = "ElevenLabs connection timed out"
                    self._record_error("timeout", msg)
                    raise ElevenLabsError("timeout", msg) from None
                msg = f"Network error reaching ElevenLabs: {type(reason).__name__ if reason else 'URLError'}"
                self._record_error("network_error", msg)
                raise ElevenLabsError("network_error", msg) from None
            except Exception as exc:
                msg = f"Unexpected ElevenLabs transport error: {type(exc).__name__}"
                self._record_error("transport_error", msg)
                raise ElevenLabsError("transport_error", msg) from None

            completed_cleanly = False
            try:
                first_chunk = True
                while True:
                    if self._cancel_event.is_set():
                        break
                    chunk = resp.read(chunk_bytes)
                    if not chunk:
                        completed_cleanly = True
                        break
                    if first_chunk:
                        self._last_latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                        self._last_error = None
                        self._last_error_code = None
                        first_chunk = False
                    yield chunk
            except (socket.timeout, TimeoutError):
                msg = "ElevenLabs audio stream interrupted by timeout"
                self._record_error("timeout", msg)
                raise ElevenLabsError("timeout", msg) from None
            finally:
                if not completed_cleanly:
                    try:
                        resp.close()
                    except Exception:
                        pass
                    if self._https_conn is not None:
                        try:
                            self._https_conn.close()
                        except Exception:
                            pass
                        self._https_conn = None

    def synthesize_mp3(
        self,
        text: str,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Synthesize full MP3 bytes for browser Web Audio API visualizer playback."""
        self._cancel_event.clear()
        buf = bytearray()
        for chunk in self.stream_mp3_chunks(text, overrides=overrides):
            buf.extend(chunk)
        if not buf:
            raise ElevenLabsError("empty_audio", "ElevenLabs returned empty audio stream")
        return bytes(buf)

    def speak(
        self,
        text: str,
        wait: bool = True,
        language: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Synthesize and play speech through local audio output via streaming pipe.
        Returns True if synthesis and playback succeeded, or False so HybridTTSProvider
        can immediately fall back to SpeechDispatcherTTS without dropping the turn.
        """
        clean_text = (text or "").strip()
        if not clean_text:
            return False

        if not self.is_configured():
            _, code, hint = inspect_elevenlabs_key_state()
            self._record_error(code, hint)
            return False

        player_cmd = self._resolve_streaming_player_cmd()
        if not player_cmd:
            self._record_error("player_missing", "No streaming MP3 audio player (gst-launch-1.0/ffplay/mpv) found")
            return False

        # Cancel any prior active utterance
        self.stop()
        self._cancel_event.clear()

        if wait:
            return self._stream_to_player(clean_text, player_cmd, overrides=overrides)

        # Non-blocking async synthesis & playback: verify first network chunk quickly so
        # immediate auth/rate-limit errors still trigger fallback synchronously!
        ready_evt = threading.Event()
        result_box = {"ok": False}

        def _bg_worker() -> None:
            ok = self._stream_to_player(
                clean_text,
                player_cmd,
                overrides=overrides,
                first_chunk_event=ready_evt,
                result_box=result_box,
            )
            result_box["ok"] = ok
            ready_evt.set()

        t = threading.Thread(target=_bg_worker, name="maven-elevenlabs-tts", daemon=True)
        with self._lock:
            self._worker_thread = t
            self._is_speaking = True
        t.start()

        # Wait up to 3.5s for TTFB (first audio chunk) so caller knows whether fallback is needed
        ready_evt.wait(timeout=3.5)
        return bool(result_box["ok"])

    def _stream_to_player(
        self,
        text: str,
        player_cmd: List[str],
        overrides: Optional[Dict[str, Any]] = None,
        first_chunk_event: Optional[threading.Event] = None,
        result_box: Optional[Dict[str, bool]] = None,
    ) -> bool:
        proc: Optional[subprocess.Popen] = None
        wrote_any = False
        t_start = time.perf_counter()
        try:
            with self._lock:
                self._is_speaking = True

            for chunk in self.stream_mp3_chunks(text, overrides=overrides):
                if self._cancel_event.is_set():
                    break
                if proc is None:
                    proc = subprocess.Popen(
                        player_cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    with self._lock:
                        self._player_proc = proc
                if proc.stdin:
                    try:
                        proc.stdin.write(chunk)
                        proc.stdin.flush()
                        wrote_any = True
                        if result_box is not None:
                            result_box["ok"] = True
                        if first_chunk_event is not None and not first_chunk_event.is_set():
                            first_chunk_event.set()
                    except BrokenPipeError:
                        break

            if proc and proc.stdin:
                try:
                    proc.stdin.close()
                except Exception:
                    pass

            if proc and not self._cancel_event.is_set():
                proc.wait(timeout=45.0)

            self._last_playback_ms = round((time.perf_counter() - t_start) * 1000.0, 1)
            return wrote_any
        except ElevenLabsError:
            return False
        except Exception as exc:
            self._record_error("playback_error", f"Audio playback error: {type(exc).__name__}")
            return False
        finally:
            if first_chunk_event is not None and not first_chunk_event.is_set():
                first_chunk_event.set()
            with self._lock:
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                self._player_proc = None
                self._is_speaking = False

    def speak_stream(
        self,
        sentences: Iterable[str],
        language: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
        on_first_audio: Optional[Callable[[], None]] = None,
    ) -> Dict[str, Any]:
        """
        Stream and play an iterator of meaningful sentence chunks as they arrive from the LLM.
        Synthesizes sentence N+1 in a background prefetch queue over the warm Keep-Alive TLS
        socket while sentence N plays seamlessly through a single PipeWire/GStreamer sink.
        """
        if not self.is_configured():
            _, code, hint = inspect_elevenlabs_key_state()
            self._record_error(code, hint)
            return {"ok": False, "reason": code, "chunks": 0}

        player_cmd = self._resolve_streaming_player_cmd()
        if not player_cmd:
            self._record_error("player_missing", "No streaming MP3 audio player found")
            return {"ok": False, "reason": "player_missing", "chunks": 0}

        self.stop()
        self._cancel_event.clear()

        audio_q: "queue.Queue[Optional[Tuple[str, Any]]]" = queue.Queue(maxsize=3)
        first_dns_ms = 0.0
        first_tls_ms = 0.0
        first_ttfb_ms: Optional[float] = None
        sentence_count = 0

        def _producer() -> None:
            nonlocal first_dns_ms, first_tls_ms, first_ttfb_ms, sentence_count
            try:
                for raw_sent in sentences:
                    if self._cancel_event.is_set():
                        break
                    sent = (raw_sent or "").strip()
                    if not sent:
                        continue
                    sentence_count += 1
                    idx = sentence_count
                    t_req = time.perf_counter()
                    try:
                        first_piece = True
                        for mp3_chunk in self.stream_mp3_chunks(sent, overrides=overrides):
                            if self._cancel_event.is_set():
                                break
                            if first_piece:
                                if idx == 1:
                                    first_ttfb_ms = round((time.perf_counter() - t_req) * 1000.0, 1)
                                    first_dns_ms = self._last_dns_ms
                                    first_tls_ms = self._last_tls_ms
                                first_piece = False
                            audio_q.put(("chunk", mp3_chunk))
                    except ElevenLabsError as err:
                        audio_q.put(("error", (err.code, sent)))
                        return
            finally:
                audio_q.put(None)

        prod_thread = threading.Thread(target=_producer, name="maven-tts-prefetch", daemon=True)
        proc: Optional[subprocess.Popen] = None
        wrote_any = False
        first_audio_fired = False
        failed_sentence: Optional[str] = None
        error_code: Optional[str] = None
        t_play_start: Optional[float] = None

        try:
            with self._lock:
                self._is_speaking = True
            prod_thread.start()

            while True:
                if self._cancel_event.is_set():
                    break
                item = audio_q.get()
                if item is None:
                    break
                kind, payload = item
                if kind == "error":
                    error_code, failed_sentence = payload
                    break
                if proc is None:
                    proc = subprocess.Popen(
                        player_cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    with self._lock:
                        self._player_proc = proc
                if proc.stdin:
                    try:
                        proc.stdin.write(payload)
                        proc.stdin.flush()
                        wrote_any = True
                        if not first_audio_fired:
                            first_audio_fired = True
                            t_play_start = time.perf_counter()
                            if on_first_audio is not None:
                                try:
                                    on_first_audio()
                                except Exception:
                                    pass
                    except BrokenPipeError:
                        break

            if proc and proc.stdin:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
            if proc and not self._cancel_event.is_set():
                proc.wait(timeout=60.0)
        finally:
            with self._lock:
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                self._player_proc = None
                self._is_speaking = False

        total_play_ms = round((time.perf_counter() - t_play_start) * 1000.0, 1) if t_play_start is not None else 0.0
        self._last_playback_ms = total_play_ms
        return {
            "ok": wrote_any and error_code is None,
            "wrote_any": wrote_any,
            "reason": error_code,
            "failed_sentence": failed_sentence,
            "chunks": sentence_count,
            "tts_ttfb_ms": first_ttfb_ms,
            "tts_playback_ms": total_play_ms,
            "dns_ms": first_dns_ms,
            "tls_ms": first_tls_ms,
        }

    def stop(self) -> None:
        """Immediately interrupt active streaming synthesis and audio output."""
        self._cancel_event.set()
        with self._lock:
            self._is_speaking = False
            proc = self._player_proc
            self._player_proc = None
        if proc and proc.poll() is None:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=0.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def close(self) -> None:
        """Close persistent keep-alive TLS socket cleanly."""
        conn = getattr(self, "_https_conn", None)
        self._https_conn = None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def list_available_voices(self) -> Dict[str, Any]:
        """Query ElevenLabs /v1/voices if configured; always include curated JARVIS presets."""
        key_ok, key_code, key_hint = inspect_elevenlabs_key_state()
        if not key_ok:
            return {
                "status": "unconfigured",
                "key_status": key_code,
                "hint": key_hint,
                "voices": JARVIS_VOICE_PRESETS,
            }

        req = urllib.request.Request(
            f"{ELEVENLABS_API_BASE}/voices",
            headers={
                "xi-api-key": get_elevenlabs_api_key(),
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                remote_voices = []
                seen_ids = set()
                for p in JARVIS_VOICE_PRESETS:
                    remote_voices.append(p)
                    seen_ids.add(p["voice_id"])
                for v in data.get("voices", []):
                    vid = v.get("voice_id")
                    if not vid or vid in seen_ids:
                        continue
                    labels = v.get("labels") or {}
                    remote_voices.append(
                        {
                            "voice_id": vid,
                            "name": v.get("name", vid[:8]),
                            "accent": labels.get("accent", ""),
                            "description": labels.get("description", labels.get("use_case", "Account voice")),
                        }
                    )
                    seen_ids.add(vid)
                return {
                    "status": "success",
                    "key_status": "valid",
                    "voices": remote_voices,
                }
        except urllib.error.HTTPError as http_err:
            # Scoped TTS-only keys often omit 'voices_read' permission; keep curated JARVIS presets
            # without polluting TTS synthesis health state.
            code, msg = self._classify_http_error(http_err)
            return {
                "status": "presets_only",
                "key_status": "tts_scoped" if http_err.code in (401, 403) else code,
                "hint": "Using built-in JARVIS voice presets (API key is scoped to Text-to-Speech)",
                "voices": JARVIS_VOICE_PRESETS,
            }
        except Exception as exc:
            msg = f"Could not fetch voices: {type(exc).__name__}"
            return {
                "status": "error",
                "key_status": "network_error",
                "hint": msg,
                "voices": JARVIS_VOICE_PRESETS,
            }

    def _record_error(self, code: str, message: str) -> None:
        self._last_error_code = code
        self._last_error = redact_sensitive_text(message)

    @staticmethod
    def _classify_http_error(err: urllib.error.HTTPError) -> Tuple[str, str]:
        status = err.code
        detail_code = ""
        detail_msg = ""
        try:
            raw = err.read().decode("utf-8", errors="replace")[:400]
            parsed = json.loads(raw)
            detail = parsed.get("detail", {})
            if isinstance(detail, dict):
                detail_code = str(detail.get("code") or detail.get("status") or "")
                detail_msg = str(detail.get("message") or "")
            elif isinstance(detail, str):
                detail_msg = detail
        except Exception:
            pass

        if status == 429 or "quota" in detail_code.lower() or "quota" in detail_msg.lower():
            return "rate_limited", "ElevenLabs rate limit or character quota reached"
        if status in (401, 403) or detail_code == "invalid_api_key":
            if "API key ID used" in detail_msg:
                return "key_id_not_secret", "Key ID provided instead of secret 'sk_...' API key"
            return "auth_error", "ElevenLabs rejected API key (verify 'sk_...' key & permissions)"
        if status == 400:
            return "bad_request", redact_sensitive_text(detail_msg or "ElevenLabs rejected request parameters")
        if status >= 500:
            return "server_error", f"ElevenLabs service error (HTTP {status})"
        return f"http_{status}", f"ElevenLabs HTTP {status}"

