"""Maverick DevOS - Browser Lifecycle & Session Management."""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional
from maverick.browser.config import BrowserConfig
from maverick.browser.security import validate_navigation_url


class BrowserLifecycleError(Exception):
    """Raised when browser lifecycle operations fail."""
    pass


class BrowserLifecycle:
    """Manages dedicated automation Chrome processes and connection checks."""

    def __init__(self, config: Optional[BrowserConfig] = None):
        self.config = config or BrowserConfig()

    def is_installed(self) -> bool:
        """Verify that the configured Chrome binary exists and is executable."""
        return os.path.isfile(self.config.binary_path) and os.access(self.config.binary_path, os.X_OK)

    def is_active(self) -> bool:
        """Check if Chrome DevTools Protocol is listening on the configured port."""
        try:
            req = urllib.request.Request(
                f"{self.config.cdp_http_url}/json/version",
                headers={"User-Agent": "Maverick-DevOS/1.0"}
            )
            with urllib.request.urlopen(req, timeout=1.5) as res:
                return res.status == 200
        except Exception:
            return False

    def is_running(self) -> bool:
        """Alias for is_active()."""
        return self.is_active()

    def get_status(self) -> Dict[str, Any]:
        """Query current browser process and CDP debugging session status."""
        installed = self.is_installed()
        active = self.is_active() if installed else False
        version_data = {}

        if active:
            try:
                with urllib.request.urlopen(f"{self.config.cdp_http_url}/json/version", timeout=2.0) as res:
                    version_data = json.loads(res.read().decode("utf-8"))
            except Exception:
                pass

        return {
            "status": "success",
            "installed": installed,
            "active": active,
            "binary_path": self.config.binary_path,
            "cdp_url": self.config.cdp_http_url,
            "user_data_dir": self.config.user_data_dir,
            "browser_version": version_data.get("Browser", "Unknown"),
            "protocol_version": version_data.get("Protocol-Version", "Unknown"),
        }

    def status(self) -> Dict[str, Any]:
        """Alias for get_status()."""
        return self.get_status()

    def start(self, initial_url: str = "about:blank", headless: bool = False, open_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Launch Chrome with a dedicated, isolated automation profile and CDP port.
        Detects and returns existing active sessions without launching duplicates.
        """
        if open_url:
            initial_url = open_url
        if not self.is_installed():
            return {
                "status": "error",
                "code": "CHROME_NOT_INSTALLED",
                "message": f"Google Chrome is not installed at '{self.config.binary_path}'.",
            }

        # 1. Prevent duplicate automation sessions
        if self.is_active():
            return {
                "status": "success",
                "action": "already_running",
                "message": f"Chrome automation session is already active on {self.config.cdp_http_url}.",
                "info": self.get_status(),
            }

        # Validate startup URL
        target_url = validate_navigation_url(initial_url) if initial_url else "about:blank"

        # 2. Ensure isolated user data directory exists
        os.makedirs(self.config.user_data_dir, exist_ok=True)

        env = os.environ.copy()
        uid = os.getuid()
        env.setdefault("DISPLAY", ":0")
        env.setdefault("WAYLAND_DISPLAY", "wayland-0")
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")

        cmd = [
            self.config.binary_path,
            f"--user-data-dir={self.config.user_data_dir}",
            f"--remote-debugging-port={self.config.port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
        ]
        if headless:
            cmd.append("--headless=new")
        cmd.append(target_url)

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )

            # Wait for CDP endpoint to become ready
            deadline = time.time() + self.config.timeout_seconds
            while time.time() < deadline:
                if self.is_active():
                    return {
                        "status": "success",
                        "action": "start",
                        "pid": proc.pid,
                        "cdp_url": self.config.cdp_http_url,
                        "initial_url": target_url,
                        "message": f"Started Chrome automation session on PID {proc.pid} ({self.config.cdp_http_url}).",
                    }
                time.sleep(0.3)

            return {
                "status": "error",
                "code": "CDP_STARTUP_TIMEOUT",
                "message": f"Chrome started (PID {proc.pid}), but CDP endpoint did not respond on port {self.config.port} within timeout.",
            }

        except Exception as exc:
            return {
                "status": "error",
                "code": "LAUNCH_EXCEPTION",
                "message": f"Failed to spawn Chrome process: {str(exc)}",
            }

    def stop(self) -> Dict[str, Any]:
        """Stop the automation Chrome session cleanly."""
        if not self.is_active():
            return {
                "status": "success",
                "action": "stop",
                "message": "Chrome automation session is not currently running.",
            }

        try:
            # Query browser websocket debugger URL to issue Browser.close
            with urllib.request.urlopen(f"{self.config.cdp_http_url}/json/version", timeout=2.0) as res:
                vdata = json.loads(res.read().decode("utf-8"))
            browser_ws = vdata.get("webSocketDebuggerUrl")

            if browser_ws:
                from maverick.browser.cdp import CDPClient
                cdp = CDPClient(browser_ws, timeout=2.0)
                cdp.send_command("Browser.close")
                cdp.close()
                time.sleep(0.5)

            return {
                "status": "success",
                "action": "stop",
                "message": "Chrome automation session stopped successfully.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "code": "STOP_FAILED",
                "message": f"Failed to close automation browser: {str(exc)}",
            }
