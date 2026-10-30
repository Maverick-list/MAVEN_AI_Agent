"""Maverick DevOS - Hardened Browser Lifecycle & Session Isolation Management."""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional
from maverick.browser.config import BrowserConfig
from maverick.browser.security import validate_navigation_url, BrowserSecurityError


class BrowserLifecycleError(Exception):
    """Raised when browser lifecycle operations fail."""
    pass


class BrowserLifecycle:
    """
    Manages dedicated automation Chrome processes and enforces strict profile isolation,
    loopback-only binding, and process ownership verification.
    """

    def __init__(self, config: Optional[BrowserConfig] = None):
        self.config = config or BrowserConfig()

    def is_installed(self) -> bool:
        """Verify that the configured Chrome binary exists and is executable."""
        return os.path.isfile(self.config.binary_path) and os.access(self.config.binary_path, os.X_OK)

    def _verify_process_cmdline(self, pid: int) -> bool:
        """
        Verify via /proc/<pid>/cmdline that the process is Chrome and strictly uses
        the configured Maven automation user-data-dir. Handles both null-byte and
        whitespace-tokenized cmdline buffers.
        """
        cmdline_path = f"/proc/{pid}/cmdline"
        if not os.path.isfile(cmdline_path):
            return False

        try:
            with open(cmdline_path, "rb") as f:
                content = f.read()
            raw_text = content.decode("utf-8", errors="ignore")
            tokens = []
            for chunk in raw_text.split("\x00"):
                tokens.extend(chunk.split())

            expected_data_dir = os.path.realpath(self.config.user_data_dir)

            for token in tokens:
                if token.startswith("--user-data-dir="):
                    val = os.path.realpath(token.split("=", 1)[1])
                    if val == expected_data_dir:
                        return True
            return False
        except Exception:
            return False

    def _read_managed_session(self) -> Optional[Dict[str, Any]]:
        """Read session metadata recorded by Maverick upon startup."""
        session_file = self.config.session_metadata_file
        if not os.path.isfile(session_file):
            return None

        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            pid = data.get("pid")
            if pid and self._verify_process_cmdline(pid):
                return data
        except Exception:
            pass
        return None

    def _write_managed_session(self, pid: int, port: int) -> None:
        """Persist session metadata for ownership tracking."""
        session_file = self.config.session_metadata_file
        try:
            os.makedirs(os.path.dirname(session_file), exist_ok=True)
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump({
                    "pid": pid,
                    "port": port,
                    "user_data_dir": self.config.user_data_dir,
                    "host": self.config.host,
                    "created_at": time.time(),
                }, f, indent=2)
        except Exception:
            pass

    def _clear_managed_session(self) -> None:
        """Clear session metadata when browser stops."""
        session_file = self.config.session_metadata_file
        if os.path.isfile(session_file):
            try:
                os.remove(session_file)
            except Exception:
                pass

    def is_port_listening(self) -> bool:
        """Check if Chrome DevTools Protocol port responds to HTTP requests."""
        target_url = f"{self.config.cdp_http_url}/json/version"
        try:
            req = urllib.request.Request(
                target_url,
                headers={"User-Agent": "Maverick-DevOS/1.0"}
            )
            with urllib.request.urlopen(req, timeout=1.5) as res:
                return res.status == 200
        except Exception:
            return False

    def owns_active_session(self) -> bool:
        """Verify that the listening CDP endpoint belongs to Maven's automation profile."""
        if os.path.isfile(self.config.devtools_active_port_file):
            return True
        if self._read_managed_session() is not None:
            return True
        return False

    def is_active(self) -> bool:
        """
        Check if Chrome DevTools Protocol is listening on the configured port
        and strictly belongs to the Maven-managed automation process.
        """
        if not self.is_port_listening():
            return False
        return self.owns_active_session()

    def is_running(self) -> bool:
        """Alias for is_active()."""
        return self.is_active()

    def get_status(self) -> Dict[str, Any]:
        """Query current browser process and CDP debugging session status."""
        installed = self.is_installed()
        active = self.is_active() if installed else False
        version_data = {}
        session = self._read_managed_session()

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
            "managed_pid": session.get("pid") if session else None,
            "binary_path": self.config.binary_path,
            "cdp_url": self.config.cdp_http_url,
            "user_data_dir": self.config.user_data_dir,
            "browser_version": version_data.get("Browser", "Unknown"),
            "protocol_version": version_data.get("Protocol-Version", "Unknown"),
        }

    def status(self) -> Dict[str, Any]:
        """Alias for get_status()."""
        return self.get_status()

    def start(
        self,
        initial_url: str = "about:blank",
        headless: bool = False,
        open_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Launch Chrome with a dedicated, isolated automation profile and CDP loopback port.
        Enforces strict loopback binding (--remote-debugging-address=127.0.0.1) and prevents
        attaching to personal browser sessions.
        """
        if open_url:
            initial_url = open_url

        if not self.is_installed():
            return {
                "status": "error",
                "code": "CHROME_NOT_INSTALLED",
                "message": f"Google Chrome is not installed at '{self.config.binary_path}'.",
            }

        # 1. Check if an automation session is already active
        if self.is_active():
            return {
                "status": "success",
                "action": "already_running",
                "message": f"Chrome automation session is already active on {self.config.cdp_http_url}.",
                "info": self.get_status(),
            }

        # 2. Check if the port is occupied by an external/personal Chrome session
        try:
            probe_req = urllib.request.Request(f"{self.config.cdp_http_url}/json/version")
            with urllib.request.urlopen(probe_req, timeout=1.0) as probe_res:
                if probe_res.status == 200:
                    return {
                        "status": "error",
                        "code": "EXTERNAL_SESSION_CONFLICT",
                        "message": (
                            f"Port {self.config.resolve_active_port()} is occupied by an external browser "
                            "session not managed by Maverick. Refusing to connect to prevent hijacking personal browser data."
                        ),
                    }
        except Exception:
            pass  # Expected: port is currently free

        # Validate startup URL
        target_url = validate_navigation_url(initial_url) if initial_url else "about:blank"

        # 3. Ensure isolated user data directory exists
        os.makedirs(self.config.user_data_dir, exist_ok=True)

        env = os.environ.copy()
        uid = os.getuid()
        env.setdefault("DISPLAY", ":0")
        env.setdefault("WAYLAND_DISPLAY", "wayland-0")
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")

        # Command arguments: strictly bind loopback and dedicated profile
        cmd = [
            self.config.binary_path,
            f"--user-data-dir={self.config.user_data_dir}",
            f"--remote-debugging-address={self.config.host}",
            f"--remote-debugging-port={self.config.port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-features=Translate",
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

            # Record session
            self._write_managed_session(pid=proc.pid, port=self.config.resolve_active_port())

            # Wait for CDP endpoint to become ready
            deadline = time.time() + self.config.timeout_seconds
            while time.time() < deadline:
                if self.is_active():
                    active_port = self.config.resolve_active_port()
                    self._write_managed_session(pid=proc.pid, port=active_port)
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
            self._clear_managed_session()
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

            self._clear_managed_session()
            return {
                "status": "success",
                "action": "stop",
                "message": "Chrome automation session stopped successfully.",
            }
        except Exception as exc:
            self._clear_managed_session()
            return {
                "status": "error",
                "code": "STOP_FAILED",
                "message": f"Failed to close automation browser: {str(exc)}",
            }
