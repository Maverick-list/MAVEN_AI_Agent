"""Maverick DevOS - Unified Browser Client Facade."""

from typing import Any, Dict, List, Optional
from maverick.browser.config import BrowserConfig
from maverick.browser.lifecycle import BrowserLifecycle
from maverick.browser.tabs import TabManager
from maverick.browser.navigation import BrowserNavigator
from maverick.browser.page import PageInspector
from maverick.browser.interaction import ElementInteractor


class BrowserClient:
    """
    Unified, high-level browser automation facade coordinating lifecycle,
    tabs, navigation, page inspection, and element interaction.
    """

    def __init__(self, config: Optional[BrowserConfig] = None):
        self.config = config or BrowserConfig()
        self.lifecycle = BrowserLifecycle(self.config)
        self.tab_manager = TabManager(self.config)
        self.navigator = BrowserNavigator(self.tab_manager)
        self.inspector = PageInspector(self.tab_manager)
        self.interactor = ElementInteractor(self.tab_manager)

    def status(self) -> Dict[str, Any]:
        """Query browser automation status, CDP health, and open tabs."""
        return self.lifecycle.status()

    def start(self, headless: bool = False, open_url: Optional[str] = None) -> Dict[str, Any]:
        """Launch the isolated Chrome automation session."""
        return self.lifecycle.start(headless=headless, open_url=open_url)

    def stop(self) -> Dict[str, Any]:
        """Gracefully terminate the Chrome automation session."""
        return self.lifecycle.stop()

    def tabs(self) -> List[Dict[str, Any]]:
        """List all open page tabs."""
        return self.tab_manager.list_tabs()

    def open_tab(self, url: str = "about:blank") -> Dict[str, Any]:
        """Open a new tab with an optional URL."""
        return self.tab_manager.new_tab(url=url)

    def close_tab(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Close a specific tab (or active tab if not specified)."""
        return self.tab_manager.close_tab(tab_id=tab_id)

    def activate_tab(self, tab_id: str) -> Dict[str, Any]:
        """Bring a tab to focus."""
        return self.tab_manager.activate_tab(tab_id=tab_id)

    def navigate(self, url: str, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Navigate target tab to a safe URL."""
        return self.navigator.navigate(url=url, tab_id=tab_id)

    def reload(self, ignore_cache: bool = False, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Reload the target tab."""
        return self.navigator.reload(ignore_cache=ignore_cache, tab_id=tab_id)

    def back(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Navigate back in history."""
        return self.navigator.back(tab_id=tab_id)

    def forward(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Navigate forward in history."""
        return self.navigator.forward(tab_id=tab_id)

    def inspect(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Inspect visible page content, title, and metadata."""
        return self.inspector.inspect(tab_id=tab_id)

    def screenshot(self, output_path: Optional[str] = None, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Capture and save page screenshot to disk."""
        return self.inspector.screenshot(output_path=output_path, tab_id=tab_id)

    def click(self, selector: str, tab_id: Optional[str] = None, confirmed: bool = False) -> Dict[str, Any]:
        """Click an element by selector, requiring confirmation for consequential actions."""
        return self.interactor.click(selector=selector, tab_id=tab_id, confirmed=confirmed)

    def fill(self, selector: str, value: str, tab_id: Optional[str] = None, confirmed: bool = False) -> Dict[str, Any]:
        """Fill text into an element by selector."""
        return self.interactor.fill(selector=selector, value=value, tab_id=tab_id, confirmed=confirmed)

    def scroll(self, direction: str = "down", amount: int = 500, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """Scroll page up, down, top, or bottom."""
        return self.interactor.scroll(direction=direction, amount=amount, tab_id=tab_id)
