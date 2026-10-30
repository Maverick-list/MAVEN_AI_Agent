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
from maverick.voice.stt import LocalIntentSTTProvider, STTProvider
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
        self.stt = stt or LocalIntentSTTProvider(self.config)
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

        # 1. Spotify / Media Controls
        if re.search(r"\b(play|resume)\b.*\b(music|spotify|song)\b", cmd) or cmd in ("play", "resume"):
            try:
                ctl = SpotifyController()
                res = ctl.play()
                if res.get("status") == "success":
                    return {"status": "success", "action": "spotify_play", "response": "Resuming music on Spotify."}
                return {"status": "error", "response": "Spotify is not running. Say 'open Spotify' to launch it."}
            except Exception as e:
                return {"status": "error", "response": f"Could not control music: {str(e)}"}

        elif re.search(r"\b(pause|stop)\b.*\b(music|spotify|playback)\b", cmd) or cmd in ("pause music", "pause"):
            try:
                ctl = SpotifyController()
                res = ctl.pause()
                if res.get("status") == "success":
                    return {"status": "success", "action": "spotify_pause", "response": "Music paused."}
                return {"status": "error", "response": "Spotify is not active on D-Bus."}
            except Exception as e:
                return {"status": "error", "response": f"Failed to pause music: {str(e)}"}

        elif re.search(r"\bnext\b.*\b(track|song)\b", cmd) or cmd == "next song":
            try:
                ctl = SpotifyController()
                ctl.next()
                return {"status": "success", "action": "spotify_next", "response": "Skipping to next track."}
            except Exception:
                return {"status": "error", "response": "Could not skip track."}

        elif re.search(r"\b(what is playing|now playing|what song)\b", cmd):
            try:
                ctl = SpotifyController()
                status = ctl.get_status()
                if status.get("status") == "success":
                    title = status.get("title", "Unknown track")
                    artist = status.get("artist", "Unknown artist")
                    return {"status": "success", "response": f"Now playing {title} by {artist}."}
                return {"status": "info", "response": "No music is currently playing on Spotify."}
            except Exception:
                return {"status": "error", "response": "Unable to query media player status."}

        # 2. Application Launching
        app_map = {
            "code": ["code", "visual studio code", "vs code"],
            "google-chrome": ["chrome", "google chrome", "browser"],
            "firefox": ["firefox", "mozilla"],
            "nautilus": ["files", "nautilus", "file manager"],
            "spotify": ["spotify", "spotify client"],
            "gnome-terminal": ["terminal", "gnome terminal", "command line"],
        }

        for app_id, triggers in app_map.items():
            if any(re.search(rf"\b(open|launch|start)\b.*\b{re.escape(t)}\b", cmd) for t in triggers):
                try:
                    res = launch_app(app_id, confirmed=confirmed)
                    if res.get("status") == "success":
                        name = res.get("display_name", app_id)
                        if res.get("action") == "already_running":
                            return {"status": "success", "response": f"{name} is already open."}
                        return {"status": "success", "response": f"Opening {name}."}
                    elif res.get("status") == "confirmation_required":
                        return {
                            "status": "confirmation_required",
                            "response": f"Launching {app_id} requires confirmation. Say 'confirm' to proceed.",
                        }
                    return {"status": "error", "response": f"Failed to launch {app_id}."}
                except ConfirmationRequiredError:
                    return {
                        "status": "confirmation_required",
                        "response": f"Action on {app_id} requires confirmation. Say 'confirm' to proceed.",
                    }
                except Exception as e:
                    return {"status": "error", "response": f"Error opening application: {str(e)}"}

        # 3. Application Awareness
        if re.search(r"\b(running|active)\b.*\b(apps|applications)\b", cmd) or "what applications are running" in cmd:
            apps = get_running_authorized_apps()
            if not apps:
                return {"status": "success", "response": "No authorized applications are currently running."}
            names = [a.get("display_name", a.get("app_id")) for a in apps]
            app_list_str = ", ".join(names)
            return {
                "status": "success",
                "response": f"You currently have {len(apps)} applications running: {app_list_str}.",
            }

        # 4. System Telemetry & Hardware Context
        if "ram" in cmd or "memory" in cmd:
            mem = get_memory_usage()
            avail = mem.get("available_gb", 0.0)
            pct = mem.get("percent", 0.0)
            return {
                "status": "success",
                "response": f"You have {avail} gigabytes of RAM available, with {pct} percent total usage.",
            }

        if "battery" in cmd or "charging" in cmd:
            bat = get_battery_status()
            pct = bat.get("percent", 100)
            charging = "charging" if bat.get("is_charging") else "discharging"
            return {
                "status": "success",
                "response": f"Battery is at {pct} percent and currently {charging}.",
            }

        if "cpu" in cmd or "processor" in cmd:
            cpu = get_cpu_usage()
            pct = cpu.get("usage_percent", 0.0)
            cores = cpu.get("cores_logical", 1)
            return {
                "status": "success",
                "response": f"CPU utilization is at {pct} percent across {cores} threads.",
            }

        if re.search(r"\b(desktop context|summarize desktop|what is happening)\b", cmd):
            ce = ContextEngine()
            ctx = ce.get_context()
            running_cnt = ctx.get("applications", {}).get("running_authorized_count", 0)
            cpu_pct = ctx.get("system", {}).get("cpu_percent", 0.0)
            mem_pct = ctx.get("system", {}).get("memory_percent", 0.0)
            return {
                "status": "success",
                "response": f"Desktop summary: {running_cnt} applications active, CPU at {cpu_pct} percent, and memory at {mem_pct} percent.",
            }

        # 5. Audio Mute / Stop
        if cmd in ("mute", "mute microphone", "mute mic"):
            self.session.set_muted(True)
            return {"status": "success", "response": "Microphone muted."}

        if cmd in ("unmute", "unmute microphone", "unmute mic"):
            self.session.set_muted(False)
            return {"status": "success", "response": "Microphone unmuted."}

        if cmd in ("stop", "cancel", "be quiet", "silence"):
            self.session.interrupt()
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
