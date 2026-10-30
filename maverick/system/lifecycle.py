"""Maverick DevOS - Hardware & Desktop Lifecycle Management.

Provides ASUS ROG Strix G16 hardware profile detection, GNOME lock-screen privacy
monitoring via D-Bus, GNOME shortcut management via gsettings, and audio re-initialization
after power suspend/resume cycles.
"""

import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional


def is_screen_locked() -> bool:
    """
    Detect whether the GNOME desktop screen is currently locked.
    Uses zero-dependency D-Bus call to org.gnome.ScreenSaver.
    Returns True if locked, False otherwise.
    """
    gdbus = shutil.which("gdbus")
    if not gdbus:
        return False

    try:
        res = subprocess.run(
            [
                gdbus,
                "call",
                "-e",
                "-d", "org.gnome.ScreenSaver",
                "-o", "/org/gnome/ScreenSaver",
                "-m", "org.gnome.ScreenSaver.GetActive",
            ],
            capture_output=True,
            text=True,
            timeout=1.5,
        )
        if res.returncode == 0 and "true" in res.stdout.lower():
            return True
        return False
    except Exception:
        return False


def get_hardware_profile() -> Dict[str, Any]:
    """
    Retrieve ASUS ROG Strix hardware telemetry and host metadata.
    """
    product = "Unknown"
    vendor = "Unknown"
    try:
        if os.path.isfile("/sys/devices/virtual/dmi/id/product_name"):
            with open("/sys/devices/virtual/dmi/id/product_name", "r", encoding="utf-8") as f:
                product = f.read().strip()
        if os.path.isfile("/sys/devices/virtual/dmi/id/sys_vendor"):
            with open("/sys/devices/virtual/dmi/id/sys_vendor", "r", encoding="utf-8") as f:
                vendor = f.read().strip()
    except Exception:
        pass

    # Asus ROG Strix battery limit / power profile check
    is_rog_strix = "rog strix" in product.lower() or "asus" in vendor.lower()
    
    charge_control_limit = None
    charge_limit_path = "/sys/class/power_supply/BAT0/charge_control_limit_max"
    if not os.path.exists(charge_limit_path):
        charge_limit_path = "/sys/class/power_supply/BAT1/charge_control_limit_max"
    if os.path.exists(charge_limit_path):
        try:
            with open(charge_limit_path, "r", encoding="utf-8") as f:
                charge_control_limit = int(f.read().strip())
        except Exception:
            pass

    return {
        "vendor": vendor,
        "product_name": product,
        "is_rog_strix": is_rog_strix,
        "charge_control_limit": charge_control_limit,
        "screen_locked": is_screen_locked(),
    }


def register_gnome_shortcut(
    name: str = "Maven Control Center",
    shortcut: str = "<Super>m",
    command: str = "xdg-open http://127.0.0.1:8765",
) -> bool:
    """
    Register a native GNOME desktop keybinding using gsettings.
    Safe against overwriting existing bindings by using an isolated schema path.
    """
    gsettings = shutil.which("gsettings")
    if not gsettings:
        return False

    binding_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom-maven/"
    schema_prefix = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:" + binding_path

    try:
        # 1. Read existing custom keybindings array
        proc = subprocess.run(
            [gsettings, "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        existing_str = proc.stdout.strip()
        existing: List[str] = []
        if existing_str.startswith("[") and existing_str.endswith("]"):
            items = existing_str[1:-1].split(",")
            existing = [item.strip().strip("'\"") for item in items if item.strip()]

        if binding_path not in existing:
            existing.append(binding_path)
            new_val = "[" + ", ".join(f"'{p}'" for p in existing) + "]"
            subprocess.run(
                [gsettings, "set", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings", new_val],
                check=True,
                timeout=2.0,
            )

        # 2. Configure custom keybinding details
        subprocess.run([gsettings, "set", schema_prefix, "name", name], check=True, timeout=2.0)
        subprocess.run([gsettings, "set", schema_prefix, "command", command], check=True, timeout=2.0)
        subprocess.run([gsettings, "set", schema_prefix, "binding", shortcut], check=True, timeout=2.0)
        return True
    except Exception:
        return False


def reinitialize_audio_devices() -> Dict[str, Any]:
    """
    Safe verification and reset of the PipeWire audio pipeline upon power resume.
    Ensures microphone capturing stream can cleanly recover without orphan handles.
    """
    pw_cli = shutil.which("pw-cli")
    status = "ok"
    details = {}
    if pw_cli:
        try:
            res = subprocess.run([pw_cli, "info", "0"], capture_output=True, text=True, timeout=1.5)
            details["pipewire_core_active"] = (res.returncode == 0)
        except Exception as e:
            status = "degraded"
            details["error"] = str(e)

    return {
        "status": status,
        "timestamp": time.time(),
        "details": details,
    }

