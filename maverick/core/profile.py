"""Maverick DevOS - Operational Profiles Management (LIGHT & DEVELOPER)."""

import json
import os
import tempfile
from typing import Any, Dict, Optional

CONFIG_DIR = os.path.expanduser("~/.config/maverick")
PROFILE_FILE = os.path.join(CONFIG_DIR, "profile.json")

PROFILES: Dict[str, Dict[str, Any]] = {
    "light": {
        "name": "light",
        "display_name": "Light Mode",
        "description": "Everyday laptop usage profile. Voice assistant, acoustic wake-word, local STT/TTS, OpenClaw gateway, Telegram/Discord, and essential desktop controls with zero background CDP overhead.",
        "features": {
            "voice_assistant": True,
            "wake_word": True,
            "local_stt_tts": True,
            "openclaw_gateway": True,
            "telegram_bot": True,
            "discord_bot": True,
            "essential_desktop_control": True,
            "chrome_cdp_automation": False,
            "full_desktop_context": False,
            "verbose_activity_audit": False,
            "diagnostics_enabled": False,
        },
    },
    "developer": {
        "name": "developer",
        "display_name": "Developer Mode",
        "description": "Full development profile. Enables Chrome DevTools Protocol (CDP) automation, comprehensive multi-source desktop context engine, activity audit monitoring, and developer diagnostics.",
        "features": {
            "voice_assistant": True,
            "wake_word": True,
            "local_stt_tts": True,
            "openclaw_gateway": True,
            "telegram_bot": True,
            "discord_bot": True,
            "essential_desktop_control": True,
            "chrome_cdp_automation": True,
            "full_desktop_context": True,
            "verbose_activity_audit": True,
            "diagnostics_enabled": True,
        },
    },
}

DEFAULT_PROFILE = "developer"


def ensure_config_dir() -> None:
    """Ensure ~/.config/maverick exists with secure permissions (0700)."""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    else:
        try:
            os.chmod(CONFIG_DIR, 0o700)
        except OSError:
            pass


def get_active_profile() -> Dict[str, Any]:
    """Retrieve the currently active profile and features."""
    ensure_config_dir()
    profile_name = DEFAULT_PROFILE

    if os.path.isfile(PROFILE_FILE):
        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                candidate = data.get("active_profile", "").strip().lower()
                if candidate in PROFILES:
                    profile_name = candidate
        except Exception:
            profile_name = DEFAULT_PROFILE

    cfg = PROFILES[profile_name]
    return {
        "status": "success",
        "active_profile": profile_name,
        "display_name": cfg["display_name"],
        "description": cfg["description"],
        "features": cfg["features"],
        "config_path": PROFILE_FILE,
    }


def is_feature_enabled(feature: str) -> bool:
    """Check if a specific capability is enabled in the current profile."""
    prof = get_active_profile()
    return bool(prof.get("features", {}).get(feature, False))


def set_active_profile(profile_name: str) -> Dict[str, Any]:
    """
    Safely switch between 'light' and 'developer' operational profiles.
    Atomic and reversible:
    - Never deletes user data or API configurations.
    - Never interrupts OpenClaw Gateway or messaging services.
    - Gracefully stops Chrome CDP sessions when switching to light mode.
    """
    name = profile_name.strip().lower()
    if name not in PROFILES:
        return {
            "status": "error",
            "message": f"Invalid profile '{profile_name}'. Supported profiles: 'light', 'developer'.",
        }

    ensure_config_dir()

    # If transitioning to LIGHT mode, stop any running Chrome CDP automation session to release RAM
    cdp_cleanup_note = None
    if name == "light":
        try:
            from maverick.browser.lifecycle import BrowserLifecycle
            lifecycle = BrowserLifecycle()
            if lifecycle.is_running():
                lifecycle.stop()
                cdp_cleanup_note = "Chrome CDP automation session stopped and RAM released."
        except Exception as exc:
            cdp_cleanup_note = f"Notice: Could not inspect CDP process ({str(exc)})."

    payload = {
        "active_profile": name,
        "updated_at": os.path.getmtime(PROFILE_FILE) if os.path.exists(PROFILE_FILE) else None,
    }

    # Atomic write with 0600 permissions
    fd, tmp_path = tempfile.mkstemp(dir=CONFIG_DIR, prefix="prof_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, PROFILE_FILE)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return {
            "status": "error",
            "message": f"Failed to persist profile: {str(e)}",
        }

    res = get_active_profile()
    res["action"] = "profile_switch"
    res["notice"] = cdp_cleanup_note
    return res
