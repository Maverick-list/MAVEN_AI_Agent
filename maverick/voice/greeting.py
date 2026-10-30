"""Maverick DevOS - Automatic Boot Greeting & Ambient Presence Coordinator."""

from datetime import datetime
import json
import os
import shutil
import subprocess
import time
from typing import Any, Dict, Optional, Tuple

from maverick.voice.config import VoiceConfig
from maverick.voice.observability import voice_logger


class BootGreetingManager:
    """
    Coordinates once-per-boot greetings when desktop and audio hardware become ready.
    Respects quiet hours, user mute preferences, and exclusive audio playback.
    Operates without blocking service initialization.
    """

    STATE_DIR = os.path.expanduser("~/.local/state/maverick")
    BOOT_TOKEN_FILE = os.path.join(STATE_DIR, "boot_greeting.json")

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or VoiceConfig()
        self._ensure_state_dir()

    def _ensure_state_dir(self) -> None:
        if not os.path.exists(self.STATE_DIR):
            os.makedirs(self.STATE_DIR, mode=0o700, exist_ok=True)

    @staticmethod
    def get_boot_id() -> str:
        """Retrieve Linux kernel unique boot ID from /proc/sys/kernel/random/boot_id."""
        boot_id_file = "/proc/sys/kernel/random/boot_id"
        if os.path.isfile(boot_id_file):
            try:
                with open(boot_id_file, "r") as f:
                    return f.read().strip()
            except Exception:
                pass
        return str(int(time.time() // 86400))

    def has_greeted_this_boot(self) -> bool:
        """Check if greeting has already been delivered for the current system boot."""
        current_boot_id = self.get_boot_id()
        if not os.path.isfile(self.BOOT_TOKEN_FILE):
            return False
        try:
            with open(self.BOOT_TOKEN_FILE, "r") as f:
                data = json.load(f)
            return data.get("boot_id") == current_boot_id and bool(data.get("greeted"))
        except Exception:
            return False

    def mark_greeted(self, greeting_text: str) -> None:
        """Record greeting completion for current boot session."""
        self._ensure_state_dir()
        data = {
            "boot_id": self.get_boot_id(),
            "greeted": True,
            "timestamp": time.time(),
            "time_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "text": greeting_text,
        }
        try:
            with open(self.BOOT_TOKEN_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def is_in_quiet_hours(self, dt: Optional[datetime] = None) -> bool:
        """Check if current time falls within configured quiet hours (e.g. 22:00 to 07:00)."""
        if not self.config.quiet_hours_enabled:
            return False

        now = dt or datetime.now()
        hour = now.hour
        start = self.config.quiet_hours_start  # e.g. 22
        end = self.config.quiet_hours_end      # e.g. 7

        if start > end:
            # Spans midnight (e.g. 22 to 7)
            return hour >= start or hour < end
        else:
            return start <= hour < end

    def generate_greeting(self, dt: Optional[datetime] = None) -> Tuple[str, str]:
        """
        Generate natural time-aware bilingual greeting.
        Returns (greeting_en, greeting_id).
        """
        now = dt or datetime.now()
        hour = now.hour

        if 5 <= hour < 12:
            tod_en = "Good morning"
            tod_id = "Selamat pagi"
        elif 12 <= hour < 15:
            tod_en = "Good afternoon"
            tod_id = "Selamat siang"
        elif 15 <= hour < 18:
            tod_en = "Good afternoon"
            tod_id = "Selamat sore"
        else:
            tod_en = "Good evening"
            tod_id = "Selamat malam"

        text_en = f"{tod_en}. Maven is online. All systems are operational. I'm ready whenever you need me."
        text_id = f"{tod_id}, Firza. Maven online dan semua sistem siap digunakan."
        return text_en, text_id

    def send_desktop_notification(self, title: str, body: str) -> bool:
        """Send a native GNOME notification via notify-send without blocking."""
        notify_bin = shutil.which("notify-send")
        if not notify_bin:
            return False
        try:
            subprocess.run(
                [notify_bin, "-a", "Maven JARVIS", "-i", "audio-volume-high", title, body],
                timeout=2.0,
                check=False,
            )
            return True
        except Exception:
            return False

    def should_speak_greeting(self, is_muted: bool = False) -> Tuple[bool, str]:
        """
        Evaluate if boot greeting should be audibly spoken.
        Returns (should_speak, reason).
        """
        if not self.config.boot_greeting_enabled:
            return False, "disabled_in_config"
        if is_muted:
            return False, "system_muted"
        if self.has_greeted_this_boot():
            return False, "already_greeted_this_boot"
        if self.is_in_quiet_hours():
            return False, "quiet_hours_active"
        return True, "ready"

    def execute_boot_greeting(self, session, force: bool = False) -> Optional[str]:
        """
        Execute boot greeting if conditions are satisfied.
        Delivers via voice session TTS or silent desktop notification.
        """
        is_muted = getattr(session, "is_muted", False)
        should_speak, reason = self.should_speak_greeting(is_muted=is_muted)

        text_en, text_id = self.generate_greeting()
        selected_text = text_id if getattr(self.config, "boot_greeting_lang", "auto") == "id" else text_en

        if not should_speak and not force:
            if reason == "quiet_hours_active":
                self.send_desktop_notification("Maven JARVIS", f"Sistem online. Mode hening aktif ({datetime.now().strftime('%H:%M')}).")
                self.mark_greeted(selected_text)
            return None

        # Audibly deliver greeting
        try:
            self.send_desktop_notification("Maven JARVIS", "Sistem online. Semua layanan siap digunakan.")
            if hasattr(session, "speak_stream"):
                session.speak_stream([selected_text])
            elif hasattr(session, "speak"):
                session.speak(selected_text)
            self.mark_greeted(selected_text)
            return selected_text
        except Exception as e:
            voice_logger.exception("boot_greeting", e)
            return None

