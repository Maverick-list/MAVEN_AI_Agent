"""Maverick DevOS - Browser Automation Configuration & Endpoint Resolution."""

import os
from dataclasses import dataclass
from typing import Optional

CHROME_BINARY_PATH = "/usr/bin/google-chrome"
DEFAULT_CDP_HOST = "127.0.0.1"
DEFAULT_CDP_PORT = 9222

DEFAULT_AUTOMATION_PROFILE_DIR = os.path.expanduser("~/.local/share/maverick/chrome-automation")
DEFAULT_SCREENSHOT_DIR = os.path.expanduser("~/.local/share/maverick/screenshots")

DEFAULT_BROWSER_TIMEOUT_SECONDS = 10.0
DEFAULT_CDP_TIMEOUT_SECONDS = 5.0

# Allowed hosts for CDP: strictly local loopback
ALLOWED_CDP_HOSTS = ("127.0.0.1", "localhost")


@dataclass(frozen=True)
class BrowserConfig:
    binary_path: str = CHROME_BINARY_PATH
    host: str = DEFAULT_CDP_HOST
    port: int = DEFAULT_CDP_PORT
    user_data_dir: str = DEFAULT_AUTOMATION_PROFILE_DIR
    screenshot_dir: str = DEFAULT_SCREENSHOT_DIR
    timeout_seconds: float = DEFAULT_BROWSER_TIMEOUT_SECONDS

    def __post_init__(self):
        # Validate that host is strictly loopback
        if self.host not in ALLOWED_CDP_HOSTS:
            raise ValueError(
                f"CDP host must be strictly restricted to loopback {ALLOWED_CDP_HOSTS}, got '{self.host}'."
            )

    @property
    def devtools_active_port_file(self) -> str:
        """Path to Chrome's native DevToolsActivePort file in the profile directory."""
        return os.path.join(self.user_data_dir, "DevToolsActivePort")

    @property
    def session_metadata_file(self) -> str:
        """Path to Maverick session tracking metadata."""
        return os.path.join(self.user_data_dir, "maverick-session.json")

    def resolve_active_port(self) -> int:
        """
        Resolve the active debugging port from DevToolsActivePort file if present.
        Falls back to configured port if file does not exist.
        """
        port_file = self.devtools_active_port_file
        if os.path.isfile(port_file):
            try:
                with open(port_file, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f.readlines()]
                if lines and lines[0].isdigit():
                    return int(lines[0])
            except Exception:
                pass
        return self.port

    @property
    def cdp_http_url(self) -> str:
        """Resolved active CDP HTTP URL."""
        active_port = self.resolve_active_port()
        return f"http://{self.host}:{active_port}"
