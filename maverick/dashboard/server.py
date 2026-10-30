"""Maverick DevOS - Local-Only (127.0.0.1) Control Center Backend & SSE Telemetry Stream."""

import argparse
from collections import deque
import fcntl
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from typing import Any, Deque, Dict, List, Optional, Tuple

import psutil

from maverick.activity.logger import ActivityLogger
from maverick.core.config import AUTHORIZED_APPLICATIONS
from maverick.core.profile import get_active_profile, set_active_profile
from maverick.desktop.awareness import get_running_authorized_apps
from maverick.launcher import (
    LOG_FILE,
    PID_FILE,
    STATE_DIR,
    cmd_restart,
    cmd_start,
    cmd_stop,
    ensure_state_dir,
    get_voice_process_pid,
    verify_openclaw_gateway,
    verify_whisper_model,
)
from maverick.system.monitor import (
    get_battery_status,
    get_disk_usage,
    get_memory_usage,
    get_network_status,
    get_os_session_info,
)
from maverick.voice.audio import calculate_rms, list_audio_devices
from maverick.voice.config import VoiceConfig, save_voice_settings
from maverick.voice.controller import VoiceController
from maverick.voice.elevenlabs_tts import ElevenLabsError
from maverick.voice.observability import (
    get_latency_summary,
    record_turn_latency,
    redact_sensitive_text,
    voice_logger,
)
from maverick.voice.tts import HybridTTSProvider, create_tts_provider

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
CONVERSATION_LOG_FILE = os.path.join(STATE_DIR, "conversation-history.jsonl")
DEFAULT_PORT = 8765

# Regex parsers for real structured lines in ~/.local/state/maverick/maven-voice.log
_LOG_LINE_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\]\s+\[(?P<sub>[^\]]+)\]\s+\[(?P<lvl>[^\]]+)\]\s+(?P<msg>.*)$"
)
_KV_PAIR_RE = re.compile(r'([a-zA-Z0-9_]+)=("[^"]*"|[0-9.\-]+|[A-Za-z0-9_]+)')
_STATE_TRANS_RE = re.compile(r"State transition:\s+([A-Z_]+)\s*->\s*([A-Z_]+)")
_STT_TRANS_RE = re.compile(r'Transcribed:\s+"(.*)"')
_TTS_SPEAK_RE = re.compile(r'Speaking response:\s+"(.*)"')


def _parse_kv_tail(msg: str) -> Tuple[str, Dict[str, Any]]:
    """Split log message and optional trailing '{k=v, ...}' metadata."""
    brace_idx = msg.rfind(" {")
    if brace_idx == -1 or not msg.endswith("}"):
        return msg.strip(), {}
    clean_msg = msg[:brace_idx].strip()
    kv_blob = msg[brace_idx + 2 : -1]
    meta: Dict[str, Any] = {}
    for m in _KV_PAIR_RE.finditer(kv_blob):
        k = m.group(1)
        raw_v = m.group(2)
        if raw_v.startswith('"') and raw_v.endswith('"'):
            meta[k] = raw_v[1:-1]
        else:
            try:
                meta[k] = float(raw_v) if "." in raw_v else int(raw_v)
            except ValueError:
                if raw_v in ("True", "False"):
                    meta[k] = raw_v == "True"
                else:
                    meta[k] = raw_v
    return clean_msg, meta


def _map_ui_state(raw_state: str) -> str:
    """Normalize VoiceState values into canonical HUD visual states."""
    s = (raw_state or "idle").strip().lower()
    if s in ("wake_word_detected", "listening"):
        return "listening"
    if s in ("processing", "thinking"):
        return "thinking"
    if s == "speaking":
        return "speaking"
    if s == "error":
        return "error"
    return "idle"


class ConversationStore:
    """Privacy-safe persistent conversation history store (chmod 0600, max 100 turns)."""

    def __init__(self, path: str = CONVERSATION_LOG_FILE, max_items: int = 100):
        self.path = path
        self.max_items = max_items
        self._lock = threading.Lock()
        self._items: Deque[Dict[str, Any]] = deque(maxlen=max_items)
        self._load_existing()

    def _load_existing(self) -> None:
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            self._items.append(obj)
                    except Exception:
                        continue
        except Exception:
            pass

    def append(
        self,
        role: str,
        text: str,
        source: str = "voice",
        status: str = "success",
        action: Optional[str] = None,
        requires_confirmation: bool = False,
        pending_command: Optional[str] = None,
    ) -> Dict[str, Any]:
        clean = redact_sensitive_text((text or "").strip())
        entry: Dict[str, Any] = {
            "id": secrets.token_hex(6),
            "timestamp": time.strftime("%H:%M:%S"),
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "role": role,
            "text": clean,
            "source": source,
            "status": status,
        }
        if action:
            entry["action"] = action
        if requires_confirmation:
            entry["requires_confirmation"] = True
            entry["pending_command"] = redact_sensitive_text(pending_command or "")

        with self._lock:
            # Deduplicate identical consecutive daemon log replays on startup
            if self._items:
                last = self._items[-1]
                if last.get("role") == role and last.get("text") == clean and last.get("source") == source:
                    if abs(time.time() - last.get("_epoch", 0.0)) < 2.0:
                        return last
            entry["_epoch"] = time.time()
            self._items.append(entry)
            self._persist_locked()
        return self._public_entry(entry)

    def _persist_locked(self) -> None:
        try:
            ensure_state_dir()
            fd = os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            with open(fd, "w", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    for item in self._items:
                        pub = self._public_entry(item)
                        f.write(json.dumps(pub) + "\n")
                    f.flush()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            os.chmod(self.path, 0o600)
        except Exception:
            pass

    @staticmethod
    def _public_entry(item: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in item.items() if not k.startswith("_")}

    def list_recent(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._lock:
            sliced = list(self._items)[-limit:]
        return [self._public_entry(x) for x in sliced]


class TelemetryHub:
    """
    Aggregates real-time telemetry from the live Maven VoiceDaemon, Linux hardware,
    PipeWire/ALSA devices, OpenClaw Gateway, ActivityLogger, and Hybrid TTS engine.
    Contains ZERO simulated operational metrics.
    """

    def __init__(self, tts: Optional[HybridTTSProvider] = None):
        self.config = VoiceConfig()
        self.tts: HybridTTSProvider = tts or create_tts_provider(self.config)
        self.controller = VoiceController(config=self.config, tts=self.tts)
        self.activity_logger = ActivityLogger()
        self.conversations = ConversationStore()

        self._lock = threading.Lock()
        self._state_cond = threading.Condition()
        self._state_seq = 0

        # Incremental maven-voice.log tail state
        self._log_inode: Optional[int] = None
        self._log_offset: int = 0
        self._recent_logs: Deque[Dict[str, Any]] = deque(maxlen=50)
        self._daemon_state: str = "idle"
        self._daemon_rms: float = 0.0
        self._daemon_noise_floor: float = 0.0
        self._daemon_vad: str = "QUIET"
        self._daemon_frames: int = 0
        self._last_wake_phrase: Optional[str] = None
        self._last_wake_ts: Optional[str] = None

        # Transient interactive state (e.g. dashboard voice test / mic test / text turn)
        self._override_state: Optional[str] = None
        self._override_until: float = 0.0
        self._override_rms: Optional[float] = None
        self._mic_test_last: Optional[Dict[str, Any]] = None

        # Ephemeral in-memory audio buffer for browser Web Audio API visualizer
        self._audio_clips: Dict[str, Tuple[float, bytes]] = {}

        # Short-TTL caches for subprocess-backed probes (still 100% real host checks)
        self._cached_audio_devs: Optional[Dict[str, Any]] = None
        self._cached_audio_ts: float = 0.0
        self._cached_gateway: Optional[Tuple[bool, str]] = None
        self._cached_gateway_ts: float = 0.0
        self._cached_whisper: Optional[Tuple[bool, str]] = None
        self._cached_whisper_ts: float = 0.0
        self._cached_os_info: Dict[str, Any] = get_os_session_info()
        self._cached_openclaw_channels: Dict[str, Any] = self._read_openclaw_channels()
        self._cached_apps: List[Dict[str, Any]] = []
        self._cached_apps_ts: float = 0.0

        # Prime psutil non-blocking CPU counters
        psutil.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None, percpu=True)

        # Prime log parser from tail of existing maven-voice.log
        self._prime_log_tail()

    def notify_change(self) -> None:
        with self._state_cond:
            self._state_seq += 1
            self._state_cond.notify_all()

    def wait_for_change(self, last_seq: int, timeout: float = 0.75) -> int:
        with self._state_cond:
            if self._state_seq == last_seq:
                self._state_cond.wait(timeout=timeout)
            return self._state_seq

    def set_transient_state(
        self,
        state: Optional[str],
        duration_sec: float = 4.0,
        rms: Optional[float] = None,
    ) -> None:
        with self._lock:
            if state is None:
                self._override_state = None
                self._override_until = 0.0
                self._override_rms = None
            else:
                self._override_state = state
                self._override_until = time.time() + duration_sec
                self._override_rms = rms
        self.notify_change()

    def store_ephemeral_mp3(self, mp3_bytes: bytes) -> str:
        """Store synthesized MP3 bytes in memory for 60s for browser Web Audio playback."""
        now = time.time()
        token = secrets.token_urlsafe(16)
        with self._lock:
            expired = [k for k, (exp, _) in self._audio_clips.items() if exp < now]
            for k in expired:
                self._audio_clips.pop(k, None)
            self._audio_clips[token] = (now + 60.0, mp3_bytes)
        return token

    def pop_ephemeral_mp3(self, token: str) -> Optional[bytes]:
        now = time.time()
        with self._lock:
            item = self._audio_clips.get(token)
            if not item:
                return None
            exp, data = item
            if exp < now:
                self._audio_clips.pop(token, None)
                return None
            return data

    def _prime_log_tail(self) -> None:
        """Read last 16 KiB of maven-voice.log on startup to hydrate current state without replay duplicates."""
        if not os.path.isfile(LOG_FILE):
            return
        try:
            st = os.stat(LOG_FILE)
            self._log_inode = st.st_ino
            start_pos = max(0, st.st_size - 16384)
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                f.seek(start_pos)
                if start_pos > 0:
                    f.readline()  # discard partial line
                for line in f:
                    self._ingest_log_line(line, replay=True)
                self._log_offset = f.tell()
        except Exception:
            pass

    def _poll_log_updates(self) -> None:
        """Read newly appended lines from maven-voice.log in O(delta) time."""
        if not os.path.isfile(LOG_FILE):
            return
        try:
            st = os.stat(LOG_FILE)
            if self._log_inode != st.st_ino or st.st_size < self._log_offset:
                self._log_inode = st.st_ino
                self._log_offset = 0
            if st.st_size == self._log_offset:
                return
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._log_offset)
                for line in f:
                    self._ingest_log_line(line, replay=False)
                self._log_offset = f.tell()
        except Exception:
            pass

    def _ingest_log_line(self, raw_line: str, replay: bool = False) -> None:
        line = raw_line.strip()
        if not line:
            return
        m = _LOG_LINE_RE.match(line)
        if not m:
            self._recent_logs.append(
                {
                    "timestamp": time.strftime("%H:%M:%S"),
                    "subsystem": "DAEMON",
                    "level": "INFO",
                    "message": redact_sensitive_text(line[:240]),
                }
            )
            return

        ts = m.group("ts")
        short_ts = ts.split(" ")[-1][:8] if " " in ts else ts[:8]
        sub = m.group("sub").upper()
        lvl = m.group("lvl").upper()
        clean_msg, meta = _parse_kv_tail(m.group("msg"))

        self._recent_logs.append(
            {
                "timestamp": short_ts,
                "subsystem": sub,
                "level": lvl,
                "message": redact_sensitive_text(clean_msg),
                "meta": meta,
            }
        )

        if sub == "DAEMON" and "Heartbeat telemetry" in clean_msg:
            if "state" in meta:
                self._daemon_state = _map_ui_state(str(meta["state"]))
            if "rms" in meta:
                self._daemon_rms = float(meta["rms"])
            if "noise_floor" in meta:
                self._daemon_noise_floor = float(meta["noise_floor"])
            if "vad" in meta:
                self._daemon_vad = str(meta["vad"])
            if "frames_processed" in meta:
                self._daemon_frames = int(meta["frames_processed"])

        elif sub == "VAD" and "rms" in meta:
            self._daemon_rms = float(meta["rms"])
            if "floor" in meta:
                self._daemon_noise_floor = float(meta["floor"])

        elif sub == "STATE":
            sm = _STATE_TRANS_RE.search(clean_msg)
            if sm:
                self._daemon_state = _map_ui_state(sm.group(2))

        elif sub == "WAKE" and "Wake word detected" in clean_msg:
            self._last_wake_phrase = str(meta.get("matched", "Hey Maven"))
            self._last_wake_ts = short_ts
            self._daemon_state = "listening"

        elif sub == "STT" and not replay:
            tm = _STT_TRANS_RE.search(clean_msg)
            if tm and tm.group(1).strip():
                self.conversations.append(
                    role="user",
                    text=tm.group(1).strip(),
                    source="voice",
                    status="transcribed",
                )

        elif sub == "TTS" and not replay:
            spm = _TTS_SPEAK_RE.search(clean_msg)
            if spm and spm.group(1).strip():
                self.conversations.append(
                    role="maven",
                    text=spm.group(1).strip(),
                    source=str(meta.get("engine", "voice")),
                    status="spoken",
                )

        elif sub == "LATENCY":
            self._daemon_state = "idle"

        elif sub == "ERROR":
            self._daemon_state = "error"

    @staticmethod
    def _read_openclaw_channels() -> Dict[str, Any]:
        cfg_path = os.path.expanduser("~/.openclaw/openclaw.json")
        result: Dict[str, Any] = {
            "primary_model": "google/gemini-2.5-flash",
            "fallback_models": [],
            "telegram_enabled": False,
            "discord_enabled": False,
            "whatsapp_disabled": True,
            "whatsapp_policy": "disabled",
        }
        if not os.path.isfile(cfg_path):
            return result
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            model_cfg = data.get("agents", {}).get("defaults", {}).get("model", {})
            if isinstance(model_cfg, str) and model_cfg.strip():
                result["primary_model"] = model_cfg.strip()
            elif isinstance(model_cfg, dict):
                if model_cfg.get("primary"):
                    result["primary_model"] = str(model_cfg["primary"]).strip()
                raw_fb = model_cfg.get("fallbacks") or []
                if isinstance(raw_fb, list):
                    result["fallback_models"] = [str(m).strip() for m in raw_fb if str(m).strip()]
            channels = data.get("channels", {})
            result["telegram_enabled"] = bool(channels.get("telegram", {}).get("enabled", False))
            result["discord_enabled"] = bool(channels.get("discord", {}).get("enabled", False))
            wa = channels.get("whatsapp", {})
            dm_pol = wa.get("dmPolicy", "disabled")
            grp_pol = wa.get("groupPolicy", "disabled")
            result["whatsapp_disabled"] = (dm_pol == "disabled" and grp_pol == "disabled")
            result["whatsapp_policy"] = f"dm:{dm_pol}, group:{grp_pol}"
        except Exception:
            pass
        return result

    def get_snapshot(self) -> Dict[str, Any]:
        """Collect complete real-time operational snapshot with zero simulated status."""
        now = time.time()
        self._poll_log_updates()

        # 1. Live Voice Daemon Process Inspection
        pid = get_voice_process_pid()
        daemon_running = pid is not None
        daemon_rss_mb = 0.0
        daemon_cpu_pct = 0.0
        daemon_uptime_sec = 0
        if pid:
            try:
                proc = psutil.Process(pid)
                daemon_rss_mb = round(proc.memory_info().rss / (1024 * 1024), 1)
                daemon_cpu_pct = round(proc.cpu_percent(interval=None), 1)
                daemon_uptime_sec = max(0, int(now - proc.create_time()))
            except Exception:
                daemon_running = False
                pid = None

        # 2. Resolve Active Assistant Visual State
        with self._lock:
            if self._override_state and now < self._override_until:
                visual_state = self._override_state
                live_rms = self._override_rms if self._override_rms is not None else self._daemon_rms
            else:
                self._override_state = None
                self._override_rms = None
                if self.tts.is_speaking():
                    visual_state = "speaking"
                elif daemon_running:
                    visual_state = self._daemon_state
                else:
                    visual_state = "idle"
                live_rms = self._daemon_rms if daemon_running else 0.0

        # 3. Cached Hardware / Service Probes (real system calls, bounded cadence)
        if not self._cached_audio_devs or (now - self._cached_audio_ts) > 4.0:
            self._cached_audio_devs = list_audio_devices()
            self._cached_audio_ts = now

        if not self._cached_gateway or (now - self._cached_gateway_ts) > 5.0:
            self._cached_gateway = verify_openclaw_gateway()
            self._cached_gateway_ts = now
            self._cached_openclaw_channels = self._read_openclaw_channels()

        if not self._cached_whisper or (now - self._cached_whisper_ts) > 10.0:
            self._cached_whisper = verify_whisper_model()
            self._cached_whisper_ts = now

        if (now - self._cached_apps_ts) > 4.0:
            try:
                self._cached_apps = get_running_authorized_apps()
            except Exception:
                self._cached_apps = []
            self._cached_apps_ts = now

        # 4. Real-Time CPU / Per-Core / RAM / Battery / Network
        cpu_total = round(psutil.cpu_percent(interval=None), 1)
        cpu_per_core = [round(x, 1) for x in psutil.cpu_percent(interval=None, percpu=True)]
        mem = get_memory_usage()
        disk = get_disk_usage()
        battery = get_battery_status()
        net = get_network_status()
        profile = get_active_profile()

        gw_ok, gw_msg = self._cached_gateway
        whisper_ok, whisper_msg = self._cached_whisper
        audio_devs = self._cached_audio_devs

        # 5. Activity & Security Gates
        recent_activities = self.activity_logger.get_recent_activity(limit=8)
        gated_apps = [
            app_id for app_id, spec in AUTHORIZED_APPLICATIONS.items() if spec.requires_confirmation
        ]

        return {
            "status": "success",
            "timestamp": time.strftime("%H:%M:%S"),
            "timezone": time.strftime("%Z") or "LOCAL",
            "epoch_ms": int(now * 1000),
            "assistant": {
                "state": visual_state,
                "daemon_running": daemon_running,
                "pid": pid,
                "rss_mb": daemon_rss_mb,
                "cpu_percent": daemon_cpu_pct,
                "uptime_sec": daemon_uptime_sec,
                "muted": self.controller.session.is_muted,
                "wake_armed": bool(daemon_running and not self.controller.session.is_muted),
                "wake_words": self.config.wake_words,
                "rms": round(float(live_rms), 4),
                "noise_floor": round(float(self._daemon_noise_floor), 4),
                "vad": self._daemon_vad if daemon_running else "OFFLINE",
                "frames_processed": self._daemon_frames,
                "last_wake_phrase": self._last_wake_phrase,
                "last_wake_time": self._last_wake_ts,
            },
            "system": {
                "os": self._cached_os_info,
                "profile": profile,
                "cpu": {
                    "usage_percent": cpu_total,
                    "cores_logical": len(cpu_per_core) or psutil.cpu_count(logical=True) or 1,
                    "cores_physical": psutil.cpu_count(logical=False) or 1,
                    "per_core": cpu_per_core[:24],
                },
                "memory": mem,
                "disk": disk,
                "battery": battery,
                "network": net,
            },
            "audio": {
                "has_microphone": audio_devs.get("has_microphone", False),
                "has_speaker": audio_devs.get("has_speaker", False),
                "default_input": audio_devs.get("default_input") or "Disconnected",
                "default_output": audio_devs.get("default_output") or "Disconnected",
                "inputs": audio_devs.get("inputs", []),
                "outputs": audio_devs.get("outputs", []),
                "whisper_stt": {
                    "ready": whisper_ok,
                    "detail": whisper_msg,
                },
                "last_mic_test": self._mic_test_last,
            },
            "ai_gateway": {
                "openclaw_active": gw_ok,
                "openclaw_detail": gw_msg,
                "primary_model": self._cached_openclaw_channels.get("primary_model") or self.config.model_id,
                "fallback_models": self._cached_openclaw_channels.get("fallback_models", []),
                "channels": self._cached_openclaw_channels,
            },
            "security": {
                "confirmation_gate_armed": bool(self.config.enforce_confirmation),
                "gated_applications": gated_apps,
                "whatsapp_disabled": self._cached_openclaw_channels.get("whatsapp_disabled", True),
                "bind_address": "127.0.0.1",
            },
            "tts": self.tts.get_status(),
            "latency": get_latency_summary(limit=25),
            "activity": {
                "running_apps": self._cached_apps,
                "recent_actions": recent_activities,
                "recent_logs": list(self._recent_logs)[-25:],
            },
            "conversations": self.conversations.list_recent(limit=30),
        }

    # --- Interactive Control Actions ---

    def control_daemon(self, action: str) -> Dict[str, Any]:
        ns = argparse.Namespace(ui=False, daemon=True)
        if action == "start":
            rc = cmd_start(ns)
        elif action == "stop":
            rc = cmd_stop(ns)
        elif action == "restart":
            rc = cmd_restart(ns)
        else:
            return {"status": "error", "message": f"Unsupported daemon action: {action}"}

        time.sleep(0.35)
        pid = get_voice_process_pid()
        self.activity_logger.log_action(
            action_type=f"daemon_{action}",
            target="maven-voice-daemon",
            status="success" if rc == 0 else "error",
            confirmed=False,
            details={"pid": pid},
        )
        self.notify_change()
        return {
            "status": "success" if rc == 0 else "error",
            "action": action,
            "daemon_running": pid is not None,
            "pid": pid,
        }

    def run_microphone_test(self, duration_sec: float = 1.8) -> Dict[str, Any]:
        """Capture real PCM audio from the default microphone for bounded duration and measure RMS."""
        duration_sec = max(0.5, min(3.0, float(duration_sec)))
        backend = shutil.which("arecord") or shutil.which("pw-record")
        if not backend:
            res = {"status": "error", "message": "Neither arecord nor pw-record is available."}
            self._mic_test_last = res
            return res

        sample_rate = 16000
        frame_samples = 1600  # 100ms chunks
        frame_bytes = frame_samples * 2
        total_frames = max(5, int(duration_sec * 10))

        cmd = [
            backend,
            "-q",
            "-f", "S16_LE",
            "-r", str(sample_rate),
            "-c", "1",
            "-t", "raw",
        ]

        rms_series: List[float] = []
        proc: Optional[subprocess.Popen] = None
        try:
            self.set_transient_state("listening", duration_sec=duration_sec + 0.5, rms=0.05)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(total_frames):
                chunk = proc.stdout.read(frame_bytes) if proc.stdout else b""
                if not chunk:
                    break
                r = round(calculate_rms(chunk), 4)
                rms_series.append(r)
                self.set_transient_state("listening", duration_sec=0.6, rms=r)
        except Exception as exc:
            res = {"status": "error", "message": f"Microphone capture failed: {type(exc).__name__}"}
            self._mic_test_last = res
            self.set_transient_state("error", duration_sec=2.0)
            return res
        finally:
            if proc:
                if proc.stdout:
                    try:
                        proc.stdout.close()
                    except Exception:
                        pass
                if proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=0.5)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
            self.set_transient_state(None)

        if not rms_series:
            res = {"status": "error", "message": "No PCM samples received from microphone."}
            self._mic_test_last = res
            return res

        peak = round(max(rms_series), 4)
        mean = round(sum(rms_series) / len(rms_series), 4)
        signal_detected = peak > 0.008
        res = {
            "status": "success",
            "backend": os.path.basename(backend),
            "duration_sec": duration_sec,
            "frames": len(rms_series),
            "peak_rms": peak,
            "mean_rms": mean,
            "signal_detected": signal_detected,
            "rms_series": rms_series,
            "verdict": (
                f"Active audio signal verified (peak RMS {peak:.3f})"
                if signal_detected
                else "Capture stream open, near-zero signal (check hardware mute switch)"
            ),
        }
        self._mic_test_last = res
        self.activity_logger.log_action(
            action_type="microphone_test",
            target=os.path.basename(backend),
            status="success",
            confirmed=False,
            details={"peak_rms": peak, "mean_rms": mean, "signal_detected": signal_detected},
        )
        self.notify_change()
        return res

    def run_voice_test(
        self,
        text: Optional[str] = None,
        lang: str = "en",
        browser_audio: bool = True,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Synthesize and preview Maven's voice in English or Indonesian.
        Uses ElevenLabs primary streaming MP3 (returning browser audio stream URL for real
        Web Audio FFT Core sync, or host playback), and automatically falls back to
        local Speech Dispatcher (spd-say) if ElevenLabs is unconfigured or errors.
        """
        default_en = "Good day. Maven JARVIS holographic control center is online and ready for your instructions."
        default_id = "Selamat siang. Pusat kendali holografik Maven JARVIS telah aktif dan siap menerima perintah Anda."
        phrase = (text or "").strip() or (default_id if lang == "id" else default_en)

        preferred = self.tts._preferred_engine()
        fallback_reason: Optional[str] = None

        if preferred == "elevenlabs" and self.tts.primary.is_configured():
            if browser_audio:
                try:
                    self.set_transient_state("thinking", duration_sec=6.0)
                    mp3_bytes = self.tts.primary.synthesize_mp3(phrase, overrides=overrides)
                    token = self.store_ephemeral_mp3(mp3_bytes)
                    self.tts.last_used_engine = "elevenlabs"
                    self.tts.last_fallback_reason = None
                    est_dur = max(2.0, min(18.0, len(phrase) / 13.0))
                    self.set_transient_state("speaking", duration_sec=est_dur, rms=0.42)
                    return {
                        "status": "success",
                        "engine": "elevenlabs",
                        "playback_mode": "browser_webaudio",
                        "audio_url": f"/api/voice/stream/{token}",
                        "text": phrase,
                        "latency_ms": self.tts.primary._last_latency_ms,
                    }
                except ElevenLabsError as el_err:
                    fallback_reason = el_err.code
                    self.tts.last_fallback_reason = fallback_reason
                    voice_logger.tts_fallback("elevenlabs", "speech_dispatcher", reason=fallback_reason)
            else:
                self.set_transient_state("speaking", duration_sec=10.0, rms=0.40)
                ok_el = self.tts.primary.speak(phrase, wait=False, language=lang, overrides=overrides)
                if ok_el:
                    self.tts.last_used_engine = "elevenlabs"
                    return {
                        "status": "success",
                        "engine": "elevenlabs",
                        "playback_mode": "host_pipewire",
                        "text": phrase,
                        "latency_ms": self.tts.primary._last_latency_ms,
                    }
                fallback_reason = self.tts.primary._last_error_code or "synthesis_failed"
                self.tts.last_fallback_reason = fallback_reason
                voice_logger.tts_fallback("elevenlabs", "speech_dispatcher", reason=fallback_reason)
        elif preferred == "elevenlabs":
            fallback_reason = self.tts.primary.get_public_status().get("key_status", "missing_api_key")
            self.tts.last_fallback_reason = fallback_reason

        # Automatic Fallback to Speech Dispatcher (spd-say) on host speakers
        est_dur = max(1.8, min(14.0, len(phrase) / 14.0))
        self.set_transient_state("speaking", duration_sec=est_dur, rms=0.35)

        def _speak_fb() -> None:
            try:
                self.tts.fallback.speak(phrase, wait=True, language=lang if lang in ("en", "id") else None)
            finally:
                self.set_transient_state(None)

        self.tts.last_used_engine = "speech_dispatcher"
        threading.Thread(target=_speak_fb, name="maven-fallback-preview", daemon=True).start()

        return {
            "status": "success",
            "engine": "speech_dispatcher",
            "playback_mode": "host_speech_dispatcher",
            "fallback_reason": fallback_reason,
            "text": phrase,
        }

    def execute_command(
        self,
        text: str,
        confirmed: bool = False,
        speak_reply: bool = True,
        browser_audio: bool = True,
    ) -> Dict[str, Any]:
        """Route user conversation/command through VoiceController, preserving confirmation gates."""
        clean = (text or "").strip()
        if not clean:
            return {"status": "empty", "response": ""}

        if not confirmed:
            self.conversations.append(
                role="user",
                text=clean,
                source="dashboard",
                status="submitted",
            )

        t_turn_start = time.perf_counter()
        self.set_transient_state("thinking", duration_sec=26.0)
        try:
            res = self.controller.handle_voice_command(clean, confirmed=confirmed)
        except Exception as exc:
            self.set_transient_state("error", duration_sec=3.0)
            err_msg = redact_sensitive_text(str(exc))
            return {"status": "error", "response": f"Execution error: {err_msg}"}

        t_after_llm = time.perf_counter()
        status = res.get("status", "success")
        reply = res.get("response", "")
        action = res.get("action")
        needs_confirm = status == "confirmation_required"

        if status == "error":
            self.set_transient_state("error", duration_sec=2.5)
        else:
            self.set_transient_state(None)

        if reply:
            self.conversations.append(
                role="maven",
                text=reply,
                source="jarvis",
                status=status,
                action=action,
                requires_confirmation=needs_confirm,
                pending_command=clean if needs_confirm else None,
            )

        audio_payload: Optional[Dict[str, Any]] = None
        if speak_reply and reply:
            audio_payload = self.run_voice_test(text=reply, browser_audio=browser_audio)

        total_turn_ms = round((time.perf_counter() - t_turn_start) * 1000.0, 1)
        llm_metrics = res.get("latency") or getattr(self.controller, "last_turn_metrics", {}) or {}
        llm_total_ms = llm_metrics.get("llm_total_ms")
        if llm_total_ms is None:
            llm_total_ms = round((t_after_llm - t_turn_start) * 1000.0, 1)
        tts_ttfb_ms = (
            float(audio_payload["latency_ms"])
            if isinstance(audio_payload, dict) and isinstance(audio_payload.get("latency_ms"), (int, float))
            else None
        )
        ttfa_ms = round(float(llm_total_ms) + (tts_ttfb_ms or 0.0), 1)
        latency_entry = record_turn_latency(
            {
                "route": res.get("route") or llm_metrics.get("route") or "dashboard_command",
                "lang": llm_metrics.get("lang") or "en",
                "model_used": res.get("model_used") or llm_metrics.get("model_used") or "local_intent_router",
                "stt_backend": "dashboard_text",
                "tts_engine": (audio_payload or {}).get("engine") or "none",
                "tts_chunks": 1 if audio_payload else 0,
                "wake_ms": 0.0,
                "stt_ms": 0.0,
                "network_dns_ms": getattr(self.tts.primary, "_last_dns_ms", None),
                "network_tcp_ms": getattr(self.tts.primary, "_last_tcp_ms", None),
                "network_tls_ms": getattr(self.tts.primary, "_last_tls_ms", None),
                "gateway_queue_ms": llm_metrics.get("gateway_queue_ms", 0.0),
                "llm_ttft_ms": llm_metrics.get("llm_ttft_ms", 0.0),
                "llm_first_sentence_ms": llm_metrics.get("llm_first_sentence_ms", llm_total_ms),
                "llm_total_ms": llm_total_ms,
                "llm_retries": llm_metrics.get("llm_retries", 0),
                "tts_ttfb_ms": tts_ttfb_ms,
                "tts_playback_ms": getattr(self.tts.primary, "_last_playback_ms", None),
                "ttfa_ms": ttfa_ms,
                "total_turn_ms": total_turn_ms,
            }
        )

        self.notify_change()
        return {
            "status": status,
            "action": action,
            "response": reply,
            "requires_confirmation": needs_confirm,
            "pending_command": clean if needs_confirm else None,
            "tts_delivery": audio_payload,
            "latency": latency_entry,
        }

    def update_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update non-secret TTS settings and/or operational profile."""
        saved = save_voice_settings(payload)
        # Re-sync config instance
        self.config = VoiceConfig()
        self.tts.config = self.config
        self.tts.primary.config = self.config
        self.tts.fallback.config = self.config

        profile_res = None
        if "profile" in payload and payload["profile"] in ("light", "developer"):
            profile_res = set_active_profile(str(payload["profile"]))

        if "muted" in payload:
            self.controller.session.set_muted(bool(payload["muted"]))

        self.activity_logger.log_action(
            action_type="voice_settings_updated",
            target="dashboard",
            status="success",
            confirmed=False,
            details={"updated_keys": sorted(list(payload.keys()))},
        )
        self.notify_change()
        return {
            "status": "success",
            "saved_settings": saved,
            "profile_result": profile_res,
            "tts": self.tts.get_status(),
        }


class ControlCenterRequestHandler(BaseHTTPRequestHandler):
    """HTTP + SSE request handler bound strictly to 127.0.0.1."""

    protocol_version = "HTTP/1.1"

    @property
    def hub(self) -> TelemetryHub:
        return self.server.hub  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy access logs and prevent query/path leakage
        return

    def _check_local_origin(self) -> bool:
        """Guard mutating POST endpoints against cross-origin browser requests."""
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urllib.parse.urlparse(origin)
        return parsed.hostname in ("127.0.0.1", "localhost")

    def _send_json(self, payload: Dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > 65536:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path

        if route == "/api/status":
            self._send_json(self.hub.get_snapshot())
            return

        if route == "/api/latency":
            self._send_json({"status": "success", "latency": get_latency_summary(limit=25)})
            return

        if route == "/api/voice/voices":
            self._send_json(self.hub.tts.primary.list_available_voices())
            return

        if route.startswith("/api/voice/stream/"):
            token = route.split("/api/voice/stream/", 1)[1].strip("/")
            mp3_bytes = self.hub.pop_ephemeral_mp3(token)
            if not mp3_bytes:
                self._send_json({"status": "error", "message": "Audio stream expired or not found"}, status=404)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(mp3_bytes)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(mp3_bytes)
            return

        if route == "/api/events":
            self._handle_sse()
            return

        # Serve static UI files
        self._serve_static(route)

    def do_POST(self) -> None:
        if not self._check_local_origin():
            self._send_json(
                {"status": "error", "code": "FORBIDDEN_ORIGIN", "message": "Cross-origin POST denied."},
                status=HTTPStatus.FORBIDDEN,
            )
            return

        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        body = self._read_json_body()

        if route in ("/api/daemon/start", "/api/daemon/stop", "/api/daemon/restart"):
            action = route.rsplit("/", 1)[-1]
            res = self.hub.control_daemon(action)
            self._send_json(res)
            return

        if route == "/api/audio/test-mic":
            dur = float(body.get("duration_sec", 1.8))
            res = self.hub.run_microphone_test(duration_sec=dur)
            self._send_json(res)
            return

        if route == "/api/voice/test":
            res = self.hub.run_voice_test(
                text=body.get("text"),
                lang=str(body.get("lang", "en")),
                browser_audio=bool(body.get("browser_audio", True)),
                overrides=body.get("overrides") if isinstance(body.get("overrides"), dict) else None,
            )
            self._send_json(res)
            return

        if route == "/api/voice/stop":
            self.hub.tts.stop()
            self.hub.set_transient_state(None)
            self._send_json({"status": "success", "action": "tts_stopped"})
            return

        if route == "/api/voice/settings":
            res = self.hub.update_settings(body)
            self._send_json(res)
            return

        if route == "/api/command":
            res = self.hub.execute_command(
                text=str(body.get("text", "")),
                confirmed=bool(body.get("confirmed", False)),
                speak_reply=bool(body.get("speak", True)),
                browser_audio=bool(body.get("browser_audio", True)),
            )
            self._send_json(res)
            return

        self._send_json({"status": "error", "message": f"Unknown endpoint: {route}"}, status=HTTPStatus.NOT_FOUND)

    def _handle_sse(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        seq = 0
        try:
            while True:
                snap = self.hub.get_snapshot()
                frame = f"event: telemetry\ndata: {json.dumps(snap)}\n\n".encode("utf-8")
                self.wfile.write(frame)
                self.wfile.flush()
                seq = self.hub.wait_for_change(seq, timeout=0.85)
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _serve_static(self, route: str) -> None:
        rel = "index.html" if route in ("", "/") else route.lstrip("/")
        if rel.startswith("static/"):
            rel = rel[len("static/") :]
        target = os.path.realpath(os.path.join(STATIC_DIR, rel))
        static_root = os.path.realpath(STATIC_DIR)

        if not target.startswith(static_root + os.sep) and target != os.path.join(static_root, "index.html"):
            self._send_json({"status": "error", "message": "Forbidden path"}, status=HTTPStatus.FORBIDDEN)
            return

        if not os.path.isfile(target):
            self._send_json({"status": "error", "message": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return

        ctype, _ = mimetypes.guess_type(target)
        with open(target, "rb") as f:
            content = f.read()

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)


class ControlCenterServer(ThreadingHTTPServer):
    """Multi-threaded local-only HTTP/SSE Control Center server."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
        hub: Optional[TelemetryHub] = None,
    ):
        if host != "127.0.0.1":
            raise ValueError(
                f"Security policy violation: ControlCenterServer must bind strictly to 127.0.0.1 (got '{host}')."
            )
        self.hub = hub or TelemetryHub()
        super().__init__((host, port), ControlCenterRequestHandler)


def run_dashboard_server(
    port: int = DEFAULT_PORT,
    open_browser: bool = False,
) -> None:
    """Start the local-only MAVEN JARVIS Holographic Control Center on 127.0.0.1."""
    server = ControlCenterServer(host="127.0.0.1", port=port)
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}"

    print("=" * 68, flush=True)
    print("  ⚡ MAVEN JARVIS — HOLOGRAPHIC CONTROL CENTER", flush=True)
    print("=" * 68, flush=True)
    print(f"  Local URL:       {url}", flush=True)
    print("  Bind Security:   127.0.0.1 (Loopback Only)", flush=True)
    print("  Press Ctrl+C to stop the dashboard server.", flush=True)
    print("=" * 68, flush=True)

    if open_browser:
        xdg = shutil.which("xdg-open")
        if xdg:
            try:
                subprocess.Popen([xdg, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="MAVEN JARVIS Control Center Server")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--open", action="store_true")
    cli_args = p.parse_args()
    run_dashboard_server(port=cli_args.port, open_browser=cli_args.open)
