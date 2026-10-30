"""Maverick DevOS - Browser Automation Configuration."""

import os
from dataclasses import dataclass

CHROME_BINARY_PATH = "/usr/bin/google-chrome"
DEFAULT_CDP_HOST = "127.0.0.1"
DEFAULT_CDP_PORT = 9222
DEFAULT_CDP_URL = f"http://{DEFAULT_CDP_HOST}:{DEFAULT_CDP_PORT}"

DEFAULT_AUTOMATION_PROFILE_DIR = os.path.expanduser("~/.local/share/maverick/chrome-automation")
DEFAULT_SCREENSHOT_DIR = os.path.expanduser("~/.local/share/maverick/screenshots")

DEFAULT_BROWSER_TIMEOUT_SECONDS = 10.0
DEFAULT_CDP_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class BrowserConfig:
    binary_path: str = CHROME_BINARY_PATH
    host: str = DEFAULT_CDP_HOST
    port: int = DEFAULT_CDP_PORT
    user_data_dir: str = DEFAULT_AUTOMATION_PROFILE_DIR
    screenshot_dir: str = DEFAULT_SCREENSHOT_DIR
    timeout_seconds: float = DEFAULT_BROWSER_TIMEOUT_SECONDS

    @property
    def cdp_http_url(self) -> str:
        return f"http://{self.host}:{self.port}"
