"""Maverick DevOS - Application Awareness & Process Intelligence."""

import os
import time
from typing import Any, Dict, List, Optional
from maverick.core.config import AUTHORIZED_APPLICATIONS, AuthorizedApp
from maverick.desktop.launcher import get_running_pids, is_binary_available
from maverick.media.spotify import SpotifyController
from maverick.browser.lifecycle import BrowserLifecycle
from maverick.browser.tabs import TabManager

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def _get_process_memory_mb(pid: int) -> float:
    """Read process Resident Set Size (RSS) memory in MB."""
    if _HAS_PSUTIL:
        try:
            proc = psutil.Process(pid)
            return round(proc.memory_info().rss / (1024 ** 2), 1)
        except Exception:
            pass

    statm_path = f"/proc/{pid}/statm"
    if os.path.isfile(statm_path):
        try:
            with open(statm_path, "r", encoding="utf-8") as f:
                # Second field is resident pages (4096 bytes per page)
                resident_pages = int(f.read().split()[1])
                return round((resident_pages * 4096) / (1024 ** 2), 1)
        except Exception:
            pass
    return 0.0


def get_running_authorized_apps() -> List[Dict[str, Any]]:
    """
    Query currently running processes for all authorized applications in the allowlist.
    Returns structured process telemetry including PIDs, process counts, and memory usage.
    """
    running_apps: List[Dict[str, Any]] = []

    for app_id, app in AUTHORIZED_APPLICATIONS.items():
        installed = is_binary_available(app.binary_path)
        if not installed:
            continue

        pids = get_running_pids(app)
        if pids:
            total_rss_mb = sum(_get_process_memory_mb(p) for p in pids[:10])
            running_apps.append({
                "app_id": app.id,
                "display_name": app.display_name,
                "category": app.category,
                "is_running": True,
                "pid_count": len(pids),
                "primary_pid": pids[0],
                "pids": pids[:5],
                "memory_rss_mb": round(total_rss_mb, 1),
            })

    return running_apps


def get_active_application_context() -> Dict[str, Any]:
    """
    Collect active application signals across desktop subsystems:
    1. Active media player playback & track info (Spotify / MPRIS).
    2. Active browser automation session & frontmost page tab.
    3. Running authorized foreground processes.
    4. Wayland window isolation boundary explanation.
    """
    # 1. Media Player Signal
    media_info: Dict[str, Any] = {"active": False, "player": None}
    try:
        ctl = SpotifyController()
        players = ctl.list_active_mpris_players()
        if players:
            media_info["active"] = True
            media_info["players"] = players
            # Check if Spotify is playing
            if any("spotify" in p for p in players):
                status = ctl.get_status()
                media_info["spotify"] = {
                    "playback_status": status.get("playback_status"),
                    "track": status.get("track"),
                    "artist": status.get("artist"),
                    "title": status.get("title"),
                }
    except Exception:
        pass

    # 2. Browser Automation Signal
    browser_info: Dict[str, Any] = {"active": False}
    try:
        lifecycle = BrowserLifecycle()
        if lifecycle.is_active():
            browser_info["active"] = True
            tab_mgr = TabManager()
            tabs = tab_mgr.list_tabs()
            browser_info["tab_count"] = len(tabs)
            if tabs:
                browser_info["active_tab"] = {
                    "id": tabs[0].get("id"),
                    "title": tabs[0].get("title"),
                    "url": tabs[0].get("url"),
                }
    except Exception:
        pass

    # 3. Running Authorized Apps
    running_apps = get_running_authorized_apps()

    return {
        "running_authorized_apps": running_apps,
        "running_count": len(running_apps),
        "media": media_info,
        "automation_browser": browser_info,
        "window_detection_note": (
            "GNOME Wayland intentionally enforces compositor-level client window isolation. "
            "Arbitrary background keystroke/window inspection is restricted by design."
        ),
    }
