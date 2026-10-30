"""Unit tests for Browser automation components using mocks."""

import base64
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.browser.config import BrowserConfig
from maverick.browser.lifecycle import BrowserLifecycle, BrowserLifecycleError
from maverick.browser.tabs import TabManager, TabManagerError
from maverick.browser.navigation import BrowserNavigator, NavigationError
from maverick.browser.page import PageInspector, PageInspectorError
from maverick.browser.interaction import ElementInteractor, InteractionError
from maverick.browser.client import BrowserClient
from maverick.core.security import ConfirmationRequiredError


class TestBrowserUnit(unittest.TestCase):
    """Unit tests for browser automation modules."""

    def setUp(self):
        self.config = BrowserConfig(
            binary_path="/usr/bin/google-chrome",
            port=9222,
            user_data_dir="/tmp/test-chrome-profile",
            screenshot_dir="/tmp/test-screenshots",
            timeout_seconds=2.0,
        )

    # 1. Lifecycle Tests
    @patch("maverick.browser.lifecycle.BrowserLifecycle.owns_active_session", return_value=True)
    @patch("maverick.browser.lifecycle.urllib.request.urlopen")
    def test_lifecycle_is_running_true(self, mock_urlopen, mock_owns):
        """Test is_running returns True when /json/version responds and session is owned."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps({"Browser": "Chrome/156.0"}).encode()
        mock_urlopen.return_value = mock_resp

        lifecycle = BrowserLifecycle(self.config)
        self.assertTrue(lifecycle.is_running())

    @patch("maverick.browser.lifecycle.urllib.request.urlopen")
    def test_lifecycle_is_running_false(self, mock_urlopen):
        """Test is_running returns False when connection fails."""
        mock_urlopen.side_effect = Exception("Connection refused")

        lifecycle = BrowserLifecycle(self.config)
        self.assertFalse(lifecycle.is_running())

    @patch("maverick.browser.lifecycle.BrowserLifecycle.is_active", return_value=True)
    def test_lifecycle_start_already_running(self, mock_is_active):
        """Test start warns if already running."""
        lifecycle = BrowserLifecycle(self.config)
        res = lifecycle.start()
        self.assertEqual(res["action"], "already_running")

    # 2. Tabs Tests
    @patch("maverick.browser.tabs.urllib.request.urlopen")
    def test_tab_manager_list_tabs(self, mock_urlopen):
        """Test listing open tabs and filtering page targets."""
        mock_data = [
            {
                "id": "tab1",
                "title": "Google",
                "url": "https://www.google.com",
                "type": "page",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/tab1",
            },
            {
                "id": "ext1",
                "title": "Extension Background",
                "url": "chrome-extension://xyz",
                "type": "background_page",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/ext1",
            },
        ]
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = json.dumps(mock_data).encode()
        mock_urlopen.return_value = mock_resp

        manager = TabManager(self.config)
        tabs = manager.list_tabs()
        self.assertEqual(len(tabs), 1)
        self.assertEqual(tabs[0]["id"], "tab1")
        self.assertEqual(tabs[0]["title"], "Google")

    @patch("maverick.browser.tabs.urllib.request.urlopen")
    def test_tab_manager_new_and_close(self, mock_urlopen):
        """Test opening and closing tabs."""
        mock_resp_new = MagicMock()
        mock_resp_new.__enter__.return_value = mock_resp_new
        mock_resp_new.read.return_value = json.dumps({
            "id": "tab2",
            "url": "about:blank",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/tab2"
        }).encode()

        mock_resp_list = MagicMock()
        mock_resp_list.__enter__.return_value = mock_resp_list
        mock_resp_list.read.return_value = json.dumps([
            {"id": "tab2", "type": "page", "url": "about:blank"}
        ]).encode()

        mock_resp_close = MagicMock()
        mock_resp_close.__enter__.return_value = mock_resp_close
        mock_resp_close.read.return_value = b"Target is closing"

        mock_urlopen.side_effect = [mock_resp_new, mock_resp_list, mock_resp_close]

        manager = TabManager(self.config)
        new_tab = manager.new_tab("about:blank")
        self.assertEqual(new_tab["id"], "tab2")

        close_res = manager.close_tab("tab2")
        self.assertEqual(close_res["action"], "close_tab")
        self.assertEqual(close_res["status"], "success")

    # 3. Navigation Tests
    @patch("maverick.browser.tabs.TabManager.get_target_tab")
    @patch("maverick.browser.navigation.CDPClient")
    def test_navigation_navigate_safe_url(self, mock_cdp_cls, mock_get_tab):
        """Test navigating to a safe URL via CDP."""
        mock_get_tab.return_value = {"id": "tab1", "ws_url": "ws://127.0.0.1:9222/tab1"}
        mock_cdp = MagicMock()
        mock_cdp.send_command.return_value = {"frameId": "F1", "loaderId": "L1"}
        mock_cdp_cls.return_value = mock_cdp

        manager = TabManager(self.config)
        navigator = BrowserNavigator(manager)
        res = navigator.navigate("https://example.com")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["url"], "https://example.com")
        mock_cdp.send_command.assert_called_with("Page.navigate", {"url": "https://example.com"})

    # 4. Page Inspector Tests
    @patch("maverick.browser.tabs.TabManager.get_target_tab")
    @patch("maverick.browser.page.CDPClient")
    def test_page_inspect(self, mock_cdp_cls, mock_get_tab):
        """Test page inspection returns title, url, and sanitized text."""
        mock_get_tab.return_value = {"id": "tab1", "ws_url": "ws://127.0.0.1:9222/tab1"}
        mock_cdp = MagicMock()
        mock_cdp.send_command.side_effect = [
            {"result": {"value": "Test Page Title"}},  # title
            {"result": {"value": "https://example.com/test"}},  # url
            {"result": {"value": "Welcome to test page text"}},  # innerText
        ]
        mock_cdp_cls.return_value = mock_cdp

        manager = TabManager(self.config)
        inspector = PageInspector(manager)
        info = inspector.inspect()
        self.assertEqual(info["title"], "Test Page Title")
        self.assertEqual(info["url"], "https://example.com/test")
        self.assertIn("Welcome to test page", info["text"])

    @patch("maverick.browser.tabs.TabManager.get_target_tab")
    @patch("maverick.browser.page.CDPClient")
    def test_page_screenshot(self, mock_cdp_cls, mock_get_tab):
        """Test screenshot capture decodes base64 and saves to disk."""
        mock_get_tab.return_value = {"id": "tab1", "ws_url": "ws://127.0.0.1:9222/tab1"}
        dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b64_png = base64.b64encode(dummy_png).decode()

        mock_cdp = MagicMock()
        mock_cdp.send_command.return_value = {"data": b64_png}
        mock_cdp_cls.return_value = mock_cdp

        manager = TabManager(self.config)
        inspector = PageInspector(manager)
        res = inspector.screenshot()
        self.assertEqual(res["status"], "success")
        self.assertTrue(os.path.exists(res["filepath"]))
        # Cleanup created file
        try:
            os.remove(res["filepath"])
        except Exception:
            pass

    # 5. Interaction Tests
    @patch("maverick.browser.tabs.TabManager.get_target_tab")
    @patch("maverick.browser.interaction.CDPClient")
    def test_element_click_safe(self, mock_cdp_cls, mock_get_tab):
        """Test clicking standard non-consequential button."""
        mock_get_tab.return_value = {"id": "tab1", "ws_url": "ws://127.0.0.1:9222/tab1"}
        mock_cdp = MagicMock()
        mock_cdp.send_command.return_value = {
            "result": {
                "value": {
                    "found": True,
                    "tagName": "button",
                    "id": "play-btn",
                    "text": "Play Video",
                }
            }
        }
        mock_cdp_cls.return_value = mock_cdp

        manager = TabManager(self.config)
        interactor = ElementInteractor(manager)
        res = interactor.click("button#play-btn")
        self.assertTrue(res["clicked"])
        self.assertEqual(res["tag"], "button")

    def test_element_click_consequential_requires_confirmation(self):
        """Test clicking consequential button requires confirmation."""
        manager = TabManager(self.config)
        interactor = ElementInteractor(manager)
        with self.assertRaises(ConfirmationRequiredError):
            interactor.click("button#submit-order", confirmed=False)

    @patch("maverick.browser.tabs.TabManager.get_target_tab")
    @patch("maverick.browser.interaction.CDPClient")
    def test_element_click_consequential_with_confirmation(self, mock_cdp_cls, mock_get_tab):
        """Test clicking consequential button succeeds when confirmed=True."""
        mock_get_tab.return_value = {"id": "tab1", "ws_url": "ws://127.0.0.1:9222/tab1"}
        mock_cdp = MagicMock()
        mock_cdp.send_command.return_value = {
            "result": {
                "value": {
                    "found": True,
                    "tagName": "button",
                    "id": "submit-order",
                    "text": "Submit Order",
                }
            }
        }
        mock_cdp_cls.return_value = mock_cdp

        manager = TabManager(self.config)
        interactor = ElementInteractor(manager)
        res = interactor.click("button#submit-order", confirmed=True)
        self.assertTrue(res["clicked"])

    @patch("maverick.browser.tabs.TabManager.get_target_tab")
    @patch("maverick.browser.interaction.CDPClient")
    def test_element_fill(self, mock_cdp_cls, mock_get_tab):
        """Test filling text into an input field."""
        mock_get_tab.return_value = {"id": "tab1", "ws_url": "ws://127.0.0.1:9222/tab1"}
        mock_cdp = MagicMock()
        mock_cdp.send_command.return_value = {
            "result": {
                "value": {
                    "found": True,
                    "tagName": "input",
                    "inputType": "text",
                    "length": 11,
                }
            }
        }
        mock_cdp_cls.return_value = mock_cdp

        manager = TabManager(self.config)
        interactor = ElementInteractor(manager)
        res = interactor.fill("input[name='q']", "OpenClaw AI")
        self.assertTrue(res["filled"])
        self.assertEqual(res["chars_written"], 11)

    @patch("maverick.browser.tabs.TabManager.get_target_tab")
    @patch("maverick.browser.interaction.CDPClient")
    def test_scroll(self, mock_cdp_cls, mock_get_tab):
        """Test page scrolling."""
        mock_get_tab.return_value = {"id": "tab1", "ws_url": "ws://127.0.0.1:9222/tab1"}
        mock_cdp = MagicMock()
        mock_cdp.send_command.return_value = {
            "result": {
                "value": {
                    "scrollX": 0,
                    "scrollY": 500,
                    "scrollHeight": 2000,
                }
            }
        }
        mock_cdp_cls.return_value = mock_cdp

        manager = TabManager(self.config)
        interactor = ElementInteractor(manager)
        res = interactor.scroll("down", 500)
        self.assertTrue(res["scrolled"])
        self.assertEqual(res["direction"], "down")
        self.assertEqual(res["current_y"], 500)


if __name__ == "__main__":
    unittest.main()
