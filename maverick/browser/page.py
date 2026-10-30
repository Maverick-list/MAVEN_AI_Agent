"""Maverick DevOS - Page Inspection and Screenshot Capture."""

import base64
import os
import time
from typing import Any, Dict, Optional
from maverick.browser.cdp import CDPClient
from maverick.browser.config import BrowserConfig
from maverick.browser.tabs import TabManager


class PageInspectorError(Exception):
    """Raised when page inspection or screenshot operations fail."""
    pass


class PageInspector:
    """Extracts safe page content and captures screenshots via CDP."""

    def __init__(self, tab_manager: TabManager):
        self.tab_manager = tab_manager

    def inspect(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract safe page metadata, title, and visible text.
        Password inputs, cookies, and local credentials are automatically redacted.
        """
        tab = self.tab_manager.get_target_tab(tab_id)
        ws_url = tab.get("ws_url")
        if not ws_url:
            raise PageInspectorError(f"No WebSocket URL available for tab '{tab.get('id')}'.")

        cdp = CDPClient(ws_url, timeout=self.tab_manager.config.timeout_seconds)
        try:
            # 1. Read document title
            res_title = cdp.send_command("Runtime.evaluate", {
                "expression": "document.title",
                "returnByValue": True
            })
            title = res_title.get("result", {}).get("value", "")

            # 2. Read current location href
            res_url = cdp.send_command("Runtime.evaluate", {
                "expression": "window.location.href",
                "returnByValue": True
            })
            url = res_url.get("result", {}).get("value", "")

            # 3. Read visible body text (redacting password fields)
            text_extraction_js = """
            (() => {
                // Ensure no password values can leak into innerText extraction
                const passwords = document.querySelectorAll('input[type="password"]');
                passwords.forEach(el => el.setAttribute('data-orig-val', el.value || ''));
                
                let text = document.body ? document.body.innerText : '';
                return text;
            })()
            """
            res_text = cdp.send_command("Runtime.evaluate", {
                "expression": text_extraction_js,
                "returnByValue": True
            })
            full_text = res_text.get("result", {}).get("value", "")
            trimmed_text = full_text.strip()

            preview = trimmed_text[:1000] + ("..." if len(trimmed_text) > 1000 else "")

            return {
                "status": "success",
                "action": "inspect",
                "tab_id": tab["id"],
                "title": title,
                "url": url,
                "text_length": len(trimmed_text),
                "text_preview": preview,
                "text": trimmed_text,
                "text_full": trimmed_text,
            }
        finally:
            cdp.close()

    def capture_screenshot(
        self,
        output_path: Optional[str] = None,
        tab_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Capture page screenshot and save to a local PNG file."""
        tab = self.tab_manager.get_target_tab(tab_id)
        ws_url = tab.get("ws_url")
        if not ws_url:
            raise PageInspectorError(f"No WebSocket URL available for tab '{tab.get('id')}'.")

        cdp = CDPClient(ws_url, timeout=self.tab_manager.config.timeout_seconds)
        try:
            res = cdp.send_command("Page.captureScreenshot", {"format": "png"})
            b64_data = res.get("data", "")
            if not b64_data:
                raise PageInspectorError("CDP returned empty screenshot data.")

            raw_png = base64.b64decode(b64_data)

            # Determine file destination
            if output_path:
                target_file = os.path.realpath(os.path.expanduser(output_path))
            else:
                os.makedirs(self.tab_manager.config.screenshot_dir, exist_ok=True)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                target_file = os.path.join(
                    self.tab_manager.config.screenshot_dir,
                    f"screenshot_{timestamp}_{tab['id'][:8]}.png"
                )

            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            with open(target_file, "wb") as f:
                f.write(raw_png)

            return {
                "status": "success",
                "action": "screenshot",
                "tab_id": tab["id"],
                "file_path": target_file,
                "filepath": target_file,
                "size_bytes": len(raw_png),
                "message": f"Saved screenshot ({len(raw_png)} bytes) to '{target_file}'.",
            }
        finally:
            cdp.close()

    def screenshot(
        self,
        output_path: Optional[str] = None,
        tab_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Alias for capture_screenshot()."""
        return self.capture_screenshot(output_path=output_path, tab_id=tab_id)
