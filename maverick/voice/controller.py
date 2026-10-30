"""Maverick DevOS - Voice Interaction Controller & Desktop Action Router."""

import json
import re
import shutil
import subprocess
from typing import Any, Dict, Optional, Tuple

from maverick.activity.logger import ActivityLogger
from maverick.context.engine import ContextEngine
from maverick.core.security import ConfirmationRequiredError
from maverick.desktop.awareness import get_running_authorized_apps
from maverick.desktop.launcher import launch_app
from maverick.media.spotify import SpotifyController
from maverick.system.monitor import (
    get_battery_status,
    get_cpu_usage,
    get_memory_usage,
    get_system_resources,
)
from maverick.voice.config import VoiceConfig
from maverick.voice.session import VoiceSession, VoiceState
from maverick.voice.stt import LocalIntentSTTProvider, STTProvider, WhisperCppSTTProvider
from maverick.voice.tts import SpeechDispatcherTTS, TTSProvider


class VoiceController:
    """
    Coordinates voice session lifecycle, routes recognized speech to
    authorized desktop actions, and orchestrates OpenClaw conversation turns.
    """

    def __init__(
        self,
        config: Optional[VoiceConfig] = None,
        session: Optional[VoiceSession] = None,
        stt: Optional[STTProvider] = None,
        tts: Optional[TTSProvider] = None,
        activity_logger: Optional[ActivityLogger] = None,
    ):
        self.config = config or VoiceConfig()
        self.session = session or VoiceSession(self.config)
        if stt is not None:
            self.stt = stt
        else:
            whisper_stt = WhisperCppSTTProvider(self.config)
            if whisper_stt.is_available():
                self.stt = whisper_stt
            else:
                self.stt = LocalIntentSTTProvider(self.config)
        self.tts = tts or SpeechDispatcherTTS(self.config)
        self.logger = activity_logger or ActivityLogger()

    def handle_voice_command(self, raw_text: str, confirmed: bool = False) -> Dict[str, Any]:
        """
        Process a recognized text command, execute the matching desktop action
        or forward to OpenClaw Gemini 2.5 Flash, and return the execution summary.
        """
        clean_text = raw_text.strip()
        if not clean_text:
            return {"status": "empty", "response": ""}

        # 1. Strip wake word prefix if present ("Maven, ...", "Jarvis, ...")
        cmd_text = re.sub(r"^(?:maven|jarvis)[\s,:]*", "", clean_text, flags=re.IGNORECASE).strip()
        cmd_lower = cmd_text.lower()

        # 2. Check Local Desktop Actions
        action_result = self._route_desktop_action(cmd_lower, confirmed=confirmed)
        if action_result:
            response_text = action_result.get("response", "")
            self.logger.log_action(
                action_type="voice_action",
                target=cmd_text,
                status=action_result.get("status", "success"),
                confirmed=confirmed,
                details=action_result,
            )
            return action_result

        # 3. Conversational query: forward to OpenClaw (Gemini 2.5 Flash)
        if self.config.enable_openclaw_fallback:
            ai_result = self._query_openclaw(cmd_text)
            self.logger.log_action(
                action_type="voice_conversation",
                target=cmd_text,
                status=ai_result.get("status", "success"),
                confirmed=False,
                details={"model": self.config.model_id},
            )
            return ai_result

        return {
            "status": "unhandled",
            "response": "I didn't understand that instruction. How can I assist you with your desktop?",
        }

    def _route_desktop_action(self, cmd: str, confirmed: bool = False) -> Optional[Dict[str, Any]]:
        """Route speech command to Maverick's secure desktop automation subsystems."""

        # Determine language context for localized responses
        is_id = any(w in cmd for w in ("buka", "putar", "jeda", "hentikan", "sisa", "baterai", "ringkasan", "matikan", "aktifkan", "senyapkan", "bisu", "lagu", "musik", "berikutnya", "aplikasi", "atur", "persen", "naikkan", "turunkan", "tambah", "kurang"))

        # 1. Spotify / Media Controls
        if re.search(r"\b(play|resume|putar|mainkan|lanjutkan)\b.*\b(music|spotify|song|musik|lagu)\b", cmd) or cmd in ("play", "resume", "putar musik", "mainkan musik", "lanjutkan musik"):
            try:
                ctl = SpotifyController()
                res = ctl.play()
                if res.get("status") == "success":
                    resp = "Melanjutkan pemutaran musik di Spotify." if is_id else "Resuming music on Spotify."
                    return {"status": "success", "action": "spotify_play", "response": resp}
                resp = "Spotify belum berjalan. Ucapkan 'buka Spotify' untuk meluncurkannya." if is_id else "Spotify is not running. Say 'open Spotify' to launch it."
                return {"status": "error", "response": resp}
            except Exception as e:
                return {"status": "error", "response": f"Could not control music: {str(e)}"}

        elif re.search(r"\b(pause|stop|jeda|hentikan)\b.*\b(music|spotify|playback|musik|lagu)\b", cmd) or cmd in ("pause music", "pause", "jeda musik", "hentikan musik"):
            try:
                ctl = SpotifyController()
                res = ctl.pause()
                if res.get("status") == "success":
                    resp = "Musik dijeda." if is_id else "Music paused."
                    return {"status": "success", "action": "spotify_pause", "response": resp}
                resp = "Spotify tidak aktif pada D-Bus." if is_id else "Spotify is not active on D-Bus."
                return {"status": "error", "response": resp}
            except Exception as e:
                return {"status": "error", "response": f"Failed to pause music: {str(e)}"}

        elif re.search(r"\b(next|berikutnya|selanjutnya)\b.*\b(track|song|lagu|trek)\b", cmd) or cmd in ("next song", "lagu berikutnya", "berikutnya"):
            try:
                ctl = SpotifyController()
                ctl.next()
                resp = "Beralih ke trek berikutnya." if is_id else "Skipping to next track."
                return {"status": "success", "action": "spotify_next", "response": resp}
            except Exception:
                resp = "Tidak dapat beralih trek." if is_id else "Could not skip track."
                return {"status": "error", "response": resp}

        elif re.search(r"\b(what is playing|now playing|what song|lagu apa|sedang memutar apa|apa yang diputar)\b", cmd):
            try:
                ctl = SpotifyController()
                status = ctl.get_status()
                if status.get("status") == "success":
                    title = status.get("title", "Unknown track")
                    artist = status.get("artist", "Unknown artist")
                    resp = f"Sedang memutar {title} oleh {artist}." if is_id else f"Now playing {title} by {artist}."
                    return {"status": "success", "response": resp}
                resp = "Tidak ada musik yang sedang diputar di Spotify." if is_id else "No music is currently playing on Spotify."
                return {"status": "info", "response": resp}
            except Exception:
                resp = "Tidak dapat memeriksa status pemutar musik." if is_id else "Unable to query media player status."
                return {"status": "error", "response": resp}

        elif re.search(r"\b(volume|suara)\b", cmd):
            try:
                ctl = SpotifyController()
                # 1. Volume up / down
                if any(w in cmd for w in ("up", "increase", "raise", "naik", "naikkan", "tambah", "perbesar")):
                    status = ctl.get_status()
                    curr = status.get("volume", 0.5) if status.get("status") == "success" else 0.5
                    new_vol = min(1.0, curr + 0.1)
                    res = ctl.set_volume(new_vol)
                    pct = int(round(new_vol * 100))
                    resp = f"Volume Spotify dinaikkan ke {pct} persen." if is_id else f"Spotify volume increased to {pct} percent."
                    return {"status": "success", "action": "spotify_volume", "response": resp}
                elif any(w in cmd for w in ("down", "decrease", "lower", "turun", "turunkan", "kurang", "perkecil")):
                    status = ctl.get_status()
                    curr = status.get("volume", 0.5) if status.get("status") == "success" else 0.5
                    new_vol = max(0.0, curr - 0.1)
                    res = ctl.set_volume(new_vol)
                    pct = int(round(new_vol * 100))
                    resp = f"Volume Spotify diturunkan ke {pct} persen." if is_id else f"Spotify volume decreased to {pct} percent."
                    return {"status": "success", "action": "spotify_volume", "response": resp}
                # 2. Explicit numeric level: e.g. "volume 70" or "volume to 80 percent"
                num_match = re.search(r"\b(\d{1,3})\b", cmd)
                if num_match:
                    level_int = int(num_match.group(1))
                    level_int = max(0, min(100, level_int))
                    res = ctl.set_volume(level_int)
                    resp = f"Volume Spotify diatur ke {level_int} persen." if is_id else f"Spotify volume set to {level_int} percent."
                    return {"status": "success", "action": "spotify_volume", "response": resp}
                # 3. Query current volume
                status = ctl.get_status()
                pct = status.get("volume_percent", 50)
                resp = f"Volume Spotify saat ini adalah {pct} persen." if is_id else f"Current Spotify volume is {pct} percent."
                return {"status": "success", "action": "spotify_volume", "response": resp}
            except Exception as e:
                resp = f"Gagal mengatur volume: {str(e)}" if is_id else f"Could not set volume: {str(e)}"
                return {"status": "error", "response": resp}

        # 2. Application Launching
        app_map = {
            "code": ["code", "visual studio code", "vs code", "visual studio"],
            "google-chrome": ["chrome", "google chrome", "browser", "peramban"],
            "firefox": ["firefox", "mozilla"],
            "nautilus": ["files", "nautilus", "file manager", "berkas", "manajer berkas"],
            "spotify": ["spotify", "spotify client"],
            "gnome-terminal": ["terminal", "gnome terminal", "command line"],
        }

        for app_id, triggers in app_map.items():
            if any(re.search(rf"\b(open|launch|start|buka|jalankan)\b.*\b{re.escape(t)}\b", cmd) for t in triggers):
                try:
                    res = launch_app(app_id, confirmed=confirmed)
                    if res.get("status") == "success":
                        name = res.get("display_name", app_id)
                        if res.get("action") == "already_running":
                            resp = f"{name} sudah berjalan." if is_id else f"{name} is already open."
                            return {"status": "success", "response": resp}
                        resp = f"Membuka {name}." if is_id else f"Opening {name}."
                        return {"status": "success", "response": resp}
                    elif res.get("status") == "confirmation_required":
                        resp = f"Membuka {app_id} membutuhkan konfirmasi. Katakan 'konfirmasi' untuk melanjutkan." if is_id else f"Launching {app_id} requires confirmation. Say 'confirm' to proceed."
                        return {
                            "status": "confirmation_required",
                            "response": resp,
                        }
                    resp = f"Gagal membuka {app_id}." if is_id else f"Failed to launch {app_id}."
                    return {"status": "error", "response": resp}
                except ConfirmationRequiredError:
                    resp = f"Tindakan pada {app_id} memerlukan konfirmasi." if is_id else f"Action on {app_id} requires confirmation. Say 'confirm' to proceed."
                    return {
                        "status": "confirmation_required",
                        "response": resp,
                    }
                except Exception as e:
                    return {"status": "error", "response": f"Error opening application: {str(e)}"}

        # 3. Application Awareness
        if re.search(r"\b(running|active|aktif|berjalan)\b.*\b(apps|applications|aplikasi)\b", cmd) or "what applications are running" in cmd or "aplikasi yang sedang berjalan" in cmd:
            apps = get_running_authorized_apps()
            if not apps:
                resp = "Tidak ada aplikasi resmi yang sedang berjalan." if is_id else "No authorized applications are currently running."
                return {"status": "success", "response": resp}
            names = [a.get("display_name", a.get("app_id")) for a in apps]
            app_list_str = ", ".join(names)
            if is_id:
                resp = f"Saat ini terdapat {len(apps)} aplikasi yang sedang berjalan: {app_list_str}."
            else:
                resp = f"You currently have {len(apps)} applications running: {app_list_str}."
            return {
                "status": "success",
                "response": resp,
            }

        # 4. System Telemetry & Hardware Context
        if "ram" in cmd or "memory" in cmd or "memori" in cmd:
            mem = get_memory_usage()
            avail = mem.get("available_gb", 0.0)
            pct = mem.get("percent", 0.0)
            if is_id:
                resp = f"RAM yang tersedia adalah {avail} gigabyte, dengan total penggunaan {pct} persen."
            else:
                resp = f"You have {avail} gigabytes of RAM available, with {pct} percent total usage."
            return {
                "status": "success",
                "response": resp,
            }

        if "battery" in cmd or "charging" in cmd or "baterai" in cmd:
            bat = get_battery_status()
            pct = bat.get("percent", 100)
            charging_en = "charging" if bat.get("is_charging") else "discharging"
            charging_id = "sedang mengisi daya" if bat.get("is_charging") else "menggunakan daya baterai"
            if is_id:
                resp = f"Baterai berada pada {pct} persen dan {charging_id}."
            else:
                resp = f"Battery is at {pct} percent and currently {charging_en}."
            return {
                "status": "success",
                "response": resp,
            }

        if "cpu" in cmd or "processor" in cmd or "prosesor" in cmd:
            cpu = get_cpu_usage()
            pct = cpu.get("usage_percent", 0.0)
            cores = cpu.get("cores_logical", 1)
            if is_id:
                resp = f"Penggunaan CPU berada pada {pct} persen di {cores} thread."
            else:
                resp = f"CPU utilization is at {pct} percent across {cores} threads."
            return {
                "status": "success",
                "response": resp,
            }

        if re.search(r"\b(desktop context|summarize desktop|what is happening|ringkasan desktop|status desktop)\b", cmd):
            ce = ContextEngine()
            ctx = ce.get_context()
            running_cnt = ctx.get("applications", {}).get("running_authorized_count", 0)
            cpu_pct = ctx.get("system", {}).get("cpu_percent", 0.0)
            mem_pct = ctx.get("system", {}).get("memory_percent", 0.0)
            if is_id:
                resp = f"Ringkasan desktop: {running_cnt} aplikasi aktif, CPU di {cpu_pct} persen, dan memori di {mem_pct} persen."
            else:
                resp = f"Desktop summary: {running_cnt} applications active, CPU at {cpu_pct} percent, and memory at {mem_pct} percent."
            return {
                "status": "success",
                "response": resp,
            }

        # 5. Audio Mute / Stop
        if cmd in ("mute", "mute microphone", "mute mic", "bisu", "matikan mikrofon", "senyapkan mikrofon"):
            self.session.set_muted(True)
            resp = "Mikrofon dimatikan." if is_id else "Microphone muted."
            return {"status": "success", "response": resp}

        if cmd in ("unmute", "unmute microphone", "unmute mic", "aktifkan mikrofon", "bunyikan mikrofon"):
            self.session.set_muted(False)
            resp = "Mikrofon diaktifkan." if is_id else "Microphone unmuted."
            return {"status": "success", "response": resp}

        if cmd in ("stop", "cancel", "be quiet", "silence", "berhenti", "diam", "batalkan"):
            self.session.interrupt()
            return {"status": "success", "response": ""}
            return {"status": "success", "response": ""}

        return None

    def _query_openclaw(self, prompt: str) -> Dict[str, Any]:
        """
        Dispatch conversational turn to OpenClaw Gateway using Google Gemini 2.5 Flash.
        Handles API errors, rate limits (429), and timeouts gracefully.
        """
        openclaw_bin = shutil.which("openclaw")
        if not openclaw_bin:
            return {
                "status": "error",
                "response": "OpenClaw CLI is not installed on this workstation.",
            }

        cmd = [
            openclaw_bin,
            "agent",
            "--model", self.config.model_id,
            "--message", prompt,
            "--json",
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25.0)
            output = res.stdout.strip()

            if output:
                # Find valid JSON payload
                for line in output.splitlines():
                    if line.startswith("{"):
                        try:
                            data = json.loads(line)
                            if data.get("ok"):
                                reply = (
                                    data.get("result", {}).get("reply")
                                    or data.get("reply")
                                    or data.get("message")
                                    or "Turn completed."
                                )
                                return {"status": "success", "response": str(reply).strip()}
                            elif "error" in data:
                                err_msg = data["error"].get("message", "")
                                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                                    return {
                                        "status": "rate_limited",
                                        "response": "Google Gemini API reported a temporary quota rate limit.",
                                    }
                                return {
                                    "status": "error",
                                    "response": f"AI service notice: {err_msg[:80]}.",
                                }
                        except Exception:
                            continue

            # Check stderr for known error codes
            stderr_text = res.stderr.strip()
            if "RESOURCE_EXHAUSTED" in stderr_text or "429" in stderr_text:
                return {
                    "status": "rate_limited",
                    "response": "Gemini API quota is currently exhausted. Ready for local desktop commands.",
                }

            return {
                "status": "error",
                "response": "I could not reach the OpenClaw agent at this moment.",
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "response": "The request timed out while communicating with the AI gateway.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "response": f"Voice controller encountered an error: {str(exc)}",
            }
