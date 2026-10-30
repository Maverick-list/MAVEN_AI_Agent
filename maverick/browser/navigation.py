"""Maverick DevOS - Browser Navigation."""

import time
from typing import Any, Dict, Optional
from maverick.browser.cdp import CDPClient
from maverick.browser.config import BrowserConfig
from maverick.browser.security import validate_navigation_url
from maverick.browser.tabs import TabManager


class NavigationError(Exception):
    """Raised when navigation operations fail."""
    pass


class BrowserNavigator:
    """Handles page navigation, reloads, and history traversal via CDP."""

    def __init__(self, tab_manager: TabManager):
        self.tab_manager = tab_manager

    def navigate(self, url: str, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Navigate target tab to a validated HTTP/HTTPS URL."""
        clean_url = validate_navigation_url(url)
        tab = self.tab_manager.get_target_tab(tab_id)
        ws_url = tab.get("ws_url")
        if not ws_url:
            raise NavigationError(f"No WebSocket URL available for tab '{tab.get('id')}'.")

        cdp = CDPClient(ws_url, timeout=self.tab_manager.config.timeout_seconds)
        try:
            res = cdp.send_command("Page.navigate", {"url": clean_url})
            # Brief settling time
            time.sleep(0.5)
            return {
                "status": "success",
                "action": "navigate",
                "tab_id": tab["id"],
                "url": clean_url,
                "frame_id": res.get("frameId", ""),
                "loader_id": res.get("loaderId", ""),
                "message": f"Navigated tab '{tab['id']}' to '{clean_url}'.",
            }
        finally:
            cdp.close()

    def reload(self, ignore_cache: bool = False, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Reload the page in the specified tab."""
        tab = self.tab_manager.get_target_tab(tab_id)
        ws_url = tab.get("ws_url")
        if not ws_url:
            raise NavigationError(f"No WebSocket URL available for tab '{tab.get('id')}'.")

        cdp = CDPClient(ws_url, timeout=self.tab_manager.config.timeout_seconds)
        try:
            cdp.send_command("Page.reload", {"ignoreCache": ignore_cache})
            time.sleep(0.5)
            return {
                "status": "success",
                "action": "reload",
                "tab_id": tab["id"],
                "message": f"Reloaded page in tab '{tab['id']}'.",
            }
        finally:
            cdp.close()

    def go_back(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Navigate one step backward in browser history."""
        return self._step_history(step=-1, tab_id=tab_id, action_name="back")

    def back(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Alias for go_back()."""
        return self.go_back(tab_id=tab_id)

    def go_forward(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Navigate one step forward in browser history."""
        return self._step_history(step=1, tab_id=tab_id, action_name="forward")

    def forward(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Alias for go_forward()."""
        return self.go_forward(tab_id=tab_id)

    def _step_history(self, step: int, tab_id: Optional[str], action_name: str) -> Dict[str, Any]:
        tab = self.tab_manager.get_target_tab(tab_id)
        ws_url = tab.get("ws_url")
        if not ws_url:
            raise NavigationError(f"No WebSocket URL available for tab '{tab.get('id')}'.")

        cdp = CDPClient(ws_url, timeout=self.tab_manager.config.timeout_seconds)
        try:
            history = cdp.send_command("Page.getNavigationHistory")
            current_index = history.get("currentIndex", 0)
            entries = history.get("entries", [])
            target_index = current_index + step

            if 0 <= target_index < len(entries):
                target_entry = entries[target_index]
                cdp.send_command("Page.navigateToHistoryEntry", {"entryId": target_entry["id"]})
                time.sleep(0.5)
                return {
                    "status": "success",
                    "action": action_name,
                    "tab_id": tab["id"],
                    "url": target_entry.get("url", ""),
                    "title": target_entry.get("title", ""),
                    "message": f"Navigated {action_name} to '{target_entry.get('url', '')}'.",
                }
            else:
                return {
                    "status": "error",
                    "code": "NO_HISTORY_ENTRY",
                    "message": f"Cannot navigate {action_name}: no history entry at relative index {step}.",
                }
        finally:
            cdp.close()
