"""Maverick DevOS - Element Interaction and Form Handling via CDP."""

import json
from typing import Any, Dict, Optional
from maverick.browser.cdp import CDPClient
from maverick.browser.config import BrowserConfig
from maverick.browser.security import (
    validate_element_selector,
    sanitize_input_value,
    is_consequential_interaction,
    verify_browser_confirmation,
    BrowserSecurityError,
)
from maverick.browser.tabs import TabManager


class InteractionError(Exception):
    """Raised when an element interaction fails."""
    pass


class ElementInteractor:
    """Performs validated element clicking, text filling, and scrolling via CDP."""

    def __init__(self, tab_manager: TabManager):
        self.tab_manager = tab_manager

    def click(self, selector: str, tab_id: Optional[str] = None, confirmed: bool = False) -> Dict[str, Any]:
        """
        Click an element identified by CSS selector.
        Consequential actions (e.g., submit, purchase, delete) require explicit confirmation.
        """
        valid_selector = validate_element_selector(selector)

        # Check for consequential interactions requiring confirmation
        if is_consequential_interaction(valid_selector):
            verify_browser_confirmation(
                action="click",
                target=valid_selector,
                is_confirmed=confirmed,
                reason=f"Element '{valid_selector}' matches consequential interaction pattern.",
            )

        tab = self.tab_manager.get_target_tab(tab_id)
        ws_url = tab.get("ws_url")
        if not ws_url:
            raise InteractionError(f"No WebSocket URL available for tab '{tab.get('id')}'.")

        cdp = CDPClient(ws_url, timeout=self.tab_manager.config.timeout_seconds)

        click_js = f"""
        (() => {{
            const el = document.querySelector({json.dumps(valid_selector)});
            if (!el) {{
                return {{ found: false, error: 'Element not found: ' + {json.dumps(valid_selector)} }};
            }}
            el.scrollIntoView({{ behavior: 'instant', block: 'center' }});
            el.focus();
            el.click();
            return {{
                found: true,
                tagName: el.tagName.toLowerCase(),
                id: el.id || '',
                text: (el.innerText || el.value || '').slice(0, 100).trim()
            }};
        }})()
        """

        res = cdp.send_command("Runtime.evaluate", {
            "expression": click_js,
            "returnByValue": True
        })

        val = res.get("result", {}).get("value", {})
        if not val.get("found"):
            raise InteractionError(val.get("error", f"Element not found: '{valid_selector}'"))

        return {
            "clicked": True,
            "selector": valid_selector,
            "tag": val.get("tagName"),
            "target_id": val.get("id"),
            "target_text": val.get("text"),
            "tab_id": tab.get("id"),
        }

    def fill(self, selector: str, value: str, tab_id: Optional[str] = None, confirmed: bool = False) -> Dict[str, Any]:
        """
        Fill text into an input field or textarea identified by CSS selector.
        """
        valid_selector = validate_element_selector(selector)
        clean_value = sanitize_input_value(value)

        # Enforce confirmation if filling consequential form elements
        if is_consequential_interaction(valid_selector):
            verify_browser_confirmation(
                action="fill",
                target=valid_selector,
                is_confirmed=confirmed,
                reason=f"Element '{valid_selector}' matches consequential interaction pattern.",
            )

        tab = self.tab_manager.get_target_tab(tab_id)
        ws_url = tab.get("ws_url")
        if not ws_url:
            raise InteractionError(f"No WebSocket URL available for tab '{tab.get('id')}'.")

        cdp = CDPClient(ws_url, timeout=self.tab_manager.config.timeout_seconds)

        fill_js = f"""
        (() => {{
            const el = document.querySelector({json.dumps(valid_selector)});
            if (!el) {{
                return {{ found: false, error: 'Element not found: ' + {json.dumps(valid_selector)} }};
            }}
            if (el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA' && !el.isContentEditable) {{
                return {{ found: false, error: 'Element ' + {json.dumps(valid_selector)} + ' is not an input, textarea, or editable element.' }};
            }}
            
            // Set value and trigger events
            el.focus();
            if (el.isContentEditable) {{
                el.innerText = {json.dumps(clean_value)};
            }} else {{
                el.value = {json.dumps(clean_value)};
            }}
            
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            
            return {{
                found: true,
                tagName: el.tagName.toLowerCase(),
                inputType: el.type || 'text',
                length: {len(clean_value)}
            }};
        }})()
        """

        res = cdp.send_command("Runtime.evaluate", {
            "expression": fill_js,
            "returnByValue": True
        })

        val = res.get("result", {}).get("value", {})
        if not val.get("found"):
            raise InteractionError(val.get("error", f"Failed to fill element '{valid_selector}'"))

        return {
            "filled": True,
            "selector": valid_selector,
            "input_type": val.get("inputType"),
            "chars_written": val.get("length"),
            "tab_id": tab.get("id"),
        }

    def scroll(self, direction: str = "down", amount: int = 500, tab_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Scroll the page in the specified direction ('up', 'down', 'top', 'bottom').
        """
        clean_dir = direction.strip().lower()
        if clean_dir not in ("up", "down", "top", "bottom"):
            raise BrowserSecurityError(f"Invalid scroll direction '{direction}'. Expected 'up', 'down', 'top', or 'bottom'.")

        if amount < 0 or amount > 20000:
            raise BrowserSecurityError(f"Invalid scroll amount {amount}. Must be between 0 and 20000.")

        tab = self.tab_manager.get_target_tab(tab_id)
        ws_url = tab.get("ws_url")
        if not ws_url:
            raise InteractionError(f"No WebSocket URL available for tab '{tab.get('id')}'.")

        cdp = CDPClient(ws_url, timeout=self.tab_manager.config.timeout_seconds)

        if clean_dir == "down":
            scroll_expr = f"window.scrollBy({{ top: {amount}, behavior: 'smooth' }});"
        elif clean_dir == "up":
            scroll_expr = f"window.scrollBy({{ top: -{amount}, behavior: 'smooth' }});"
        elif clean_dir == "top":
            scroll_expr = "window.scrollTo({ top: 0, behavior: 'smooth' });"
        elif clean_dir == "bottom":
            scroll_expr = "window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });"

        eval_js = f"""
        (() => {{
            {scroll_expr}
            return {{
                scrollX: window.scrollX,
                scrollY: window.scrollY,
                scrollHeight: document.body ? document.body.scrollHeight : 0
            }};
        }})()
        """

        res = cdp.send_command("Runtime.evaluate", {
            "expression": eval_js,
            "returnByValue": True
        })

        pos = res.get("result", {}).get("value", {})

        return {
            "scrolled": True,
            "direction": clean_dir,
            "amount": amount if clean_dir in ("up", "down") else None,
            "current_y": pos.get("scrollY"),
            "scroll_height": pos.get("scrollHeight"),
            "tab_id": tab.get("id"),
        }
