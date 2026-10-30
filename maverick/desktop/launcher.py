"""Maverick DevOS - Safe Desktop Application Launcher."""

import os
import subprocess
import time
from typing import Any, Dict, List, Optional
from maverick.core.config import AUTHORIZED_APPLICATIONS, AuthorizedApp, DEFAULT_TIMEOUT_SECONDS
from maverick.core.security import (
    get_authorized_app,
    validate_app_arguments,
    verify_confirmation,
    SecurityError,
    ConfirmationRequiredError,
)


def is_binary_available(binary_path: str) -> bool:
    """Check if the given binary path exists and is executable."""
    return os.path.isfile(binary_path) and os.access(binary_path, os.X_OK)


def get_running_pids(app: AuthorizedApp) -> List[int]:
    """
    Find running PIDs for an authorized application without shell execution.
    Checks /proc safely without matching inspecting commands or subprocesses.
    """
    pids: List[int] = []
    my_pid = os.getpid()
    parent_pid = os.getppid()
    
    # Process executable name mapping for reliable discovery
    name_patterns = {
        "spotify": {"spotify"},
        "code": {"code"},
        "google-chrome": {"chrome", "google-chrome"},
        "firefox": {"firefox"},
        "claude-desktop": {"claude-desktop", "claude"},
        "chatgpt-desktop": {"chatgpt-desktop", "chatgpt"},
        "gemini-desktop": {"gemini-desktop", "gemini"},
        "nautilus": {"nautilus"},
        "gnome-terminal": {"gnome-terminal-server", "gnome-terminal"},
    }

    target_names = name_patterns.get(app.id, {os.path.basename(app.binary_path)})
    
    try:
        for pid_dir in os.listdir("/proc"):
            if not pid_dir.isdigit():
                continue
            pid = int(pid_dir)
            if pid in (my_pid, parent_pid):
                continue

            try:
                # 1. Match comm (process name)
                comm_path = os.path.join("/proc", pid_dir, "comm")
                if os.path.isfile(comm_path):
                    with open(comm_path, "r", encoding="utf-8", errors="ignore") as f:
                        comm = f.read().strip()
                        if comm in target_names:
                            pids.append(pid)
                            continue

                # 2. Inspect first argument of cmdline (executable path / argv[0])
                cmd_path = os.path.join("/proc", pid_dir, "cmdline")
                if os.path.isfile(cmd_path):
                    with open(cmd_path, "rb") as f:
                        raw = f.read()
                        if raw:
                            argv0 = raw.split(b"\x00")[0].decode("utf-8", errors="ignore")
                            bin_name = os.path.basename(argv0)
                            if bin_name in target_names or argv0 == app.binary_path:
                                pids.append(pid)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
    except Exception:
        pass

    return sorted(list(set(pids)))


def check_app_status(app_id: str) -> Dict[str, Any]:
    """Return status of an authorized application (installed, running, PIDs)."""
    app = get_authorized_app(app_id)
    installed = is_binary_available(app.binary_path)
    pids = get_running_pids(app) if installed else []
    
    return {
        "id": app.id,
        "display_name": app.display_name,
        "category": app.category,
        "binary_path": app.binary_path,
        "installed": installed,
        "running": len(pids) > 0,
        "pids": pids,
        "requires_confirmation": app.requires_confirmation,
        "description": app.description,
    }


def list_all_apps_status() -> List[Dict[str, Any]]:
    """Return status for all authorized applications."""
    return [check_app_status(app_id) for app_id in sorted(AUTHORIZED_APPLICATIONS.keys())]


def launch_app(
    app_id: str,
    args: Optional[List[str]] = None,
    confirmed: bool = False,
) -> Dict[str, Any]:
    """
    Safely launch an authorized application.
    Enforces allowlisting, argument sanitization, confirmation gating,
    and decouples the process from the current session.
    """
    app = get_authorized_app(app_id)

    # 1. Verify installed
    if not is_binary_available(app.binary_path):
        return {
            "status": "error",
            "code": "APP_NOT_INSTALLED",
            "message": f"Application '{app.display_name}' ({app.id}) is not installed at '{app.binary_path}'.",
            "app": check_app_status(app.id),
        }

    # 2. Enforce confirmation if required
    if app.requires_confirmation:
        verify_confirmation(
            action="launch",
            target=app.id,
            requires_confirmation=True,
            is_confirmed=confirmed,
            reason=f"Launching {app.display_name} has external desktop or browser consequences.",
        )

    # 3. Validate arguments (apply default_args if no custom args supplied)
    effective_args = list(app.default_args) if (not args and app.default_args) else (args or [])
    sanitized_args = validate_app_arguments(app, effective_args)

    # 4. Prepare execution environment (Wayland & D-Bus awareness)
    env = os.environ.copy()
    uid = os.getuid()
    env.setdefault("DISPLAY", ":0")
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")

    # Command array: binary + sanitized arguments
    cmd = [app.binary_path] + sanitized_args

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Decouple process group
            env=env,
        )
        
        # Give short moment to verify it didn't immediately crash
        time.sleep(0.3)
        poll_res = proc.poll()
        if poll_res is not None and poll_res != 0:
            return {
                "status": "error",
                "code": "LAUNCH_FAILED",
                "message": f"Application exited immediately with code {poll_res}",
                "app": app.id,
            }

        return {
            "status": "success",
            "action": "launch",
            "target": app.id,
            "display_name": app.display_name,
            "pid": proc.pid,
            "arguments": sanitized_args,
            "message": f"Successfully launched {app.display_name} (PID: {proc.pid}).",
        }

    except Exception as exc:
        return {
            "status": "error",
            "code": "EXECUTION_EXCEPTION",
            "message": f"Failed to spawn application: {str(exc)}",
            "app": app.id,
        }
