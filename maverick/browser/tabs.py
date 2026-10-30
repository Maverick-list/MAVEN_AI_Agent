"""Maverick DevOS - Browser Tab Management."""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from maverick.browser.config import BrowserConfig
from maverick.browser.security import validate_navigation_url, BrowserSecurityError


class TabManagerError(Exception):
    """Raised when tab management operations fail."""
    pass


class TabManager:
    """Manages browser tabs via CDP HTTP endpoints."""

    def __init__(self, config: Optional[BrowserConfig] = None):
        self.config = config or BrowserConfig()

    def list_tabs(self) -> List[Dict[str, Any]]:
        """List all open page tabs in the automation session."""
        try:
            with urllib.request.urlopen(f"{self.config.cdp_http_url}/json/list", timeout=3.0) as res:
                all_targets = json.loads(res.read().decode("utf-8"))
        except Exception as exc:
            raise TabManagerError(f"Failed to query tab list from {self.config.cdp_http_url}: {exc}")

        # Filter strictly for page targets
        tabs = []
        for t in all_targets:
            if t.get("type") == "page":
                tabs.append({
                    "id": t.get("id"),
                    "title": t.get("title", ""),
                    "url": t.get("url", ""),
                    "ws_url": t.get("webSocketDebuggerUrl", ""),
                })
        return tabs

    def get_target_tab(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Resolve a specific tab by ID or default to the most recent page tab."""
        tabs = self.list_tabs()
        if not tabs:
            raise TabManagerError("No open page tabs available in the browser session.")

        if tab_id:
            for t in tabs:
                if t["id"] == tab_id:
                    return t
            raise TabManagerError(f"Tab with ID '{tab_id}' was not found.")

        # Default to the first open page tab
        return tabs[0]

    def open_tab(self, url: str = "about:blank") -> Dict[str, Any]:
        """Open a new tab with the specified safe URL."""
        clean_url = validate_navigation_url(url) if url else "about:blank"
        encoded = urllib.parse.quote(clean_url, safe=":/?#[]@!$&'()*+,;=-_.~")
        endpoint = f"{self.config.cdp_http_url}/json/new?{encoded}"

        try:
            req = urllib.request.Request(endpoint, method="PUT")
            with urllib.request.urlopen(req, timeout=5.0) as res:
                tab_info = json.loads(res.read().decode("utf-8"))

            return {
                "status": "success",
                "action": "open_tab",
                "id": tab_info.get("id"),
                "title": tab_info.get("title", ""),
                "url": tab_info.get("url", clean_url),
                "message": f"Opened new tab navigating to '{clean_url}'.",
            }
        except Exception as exc:
            raise TabManagerError(f"Failed to open new tab: {exc}")

    def new_tab(self, url: str = "about:blank") -> Dict[str, Any]:
        """Alias for open_tab()."""
        return self.open_tab(url=url)

    def close_tab(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Close an existing tab by ID (or the active tab if None)."""
        if not tab_id:
            target = self.get_target_tab()
            clean_id = target["id"]
        else:
            clean_id = tab_id.strip()

        if not clean_id or "/" in clean_id or ".." in clean_id:
            raise BrowserSecurityError(f"Invalid tab ID: '{tab_id}'")

        endpoint = f"{self.config.cdp_http_url}/json/close/{clean_id}"
        try:
            with urllib.request.urlopen(endpoint, timeout=3.0) as res:
                resp = res.read().decode("utf-8")

            return {
                "status": "success",
                "action": "close_tab",
                "id": clean_id,
                "message": f"Closed tab '{clean_id}'.",
            }
        except Exception as exc:
            raise TabManagerError(f"Failed to close tab '{clean_id}': {exc}")

    def activate_tab(self, tab_id: str) -> Dict[str, Any]:
        """Switch to and focus a tab by ID."""
        clean_id = tab_id.strip()
        if not clean_id:
            raise BrowserSecurityError("Tab ID cannot be empty.")

        endpoint = f"{self.config.cdp_http_url}/json/activate/{clean_id}"
        try:
            with urllib.request.urlopen(endpoint, timeout=3.0) as res:
                res.read()

            return {
                "status": "success",
                "action": "activate_tab",
                "id": clean_id,
                "message": f"Activated tab '{clean_id}'.",
            }
        except Exception as exc:
            raise TabManagerError(f"Failed to activate tab '{clean_id}': {exc}")
