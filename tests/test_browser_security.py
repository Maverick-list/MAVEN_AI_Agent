"""Unit tests for Browser Security and Policy Enforcement."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.browser.security import (
    validate_navigation_url,
    validate_element_selector,
    validate_target_id,
    validate_cdp_ws_url,
    sanitize_input_value,
    is_consequential_interaction,
    is_sensitive_storage_query,
    verify_browser_confirmation,
    BrowserSecurityError,
)
from maverick.browser.page import redact_sensitive_text
from maverick.core.security import ConfirmationRequiredError


class TestBrowserSecurity(unittest.TestCase):
    """Test browser security rules, scheme filtering, and confirmation gating."""

    def test_safe_navigation_urls(self):
        """Test legitimate URLs pass validation."""
        self.assertEqual(validate_navigation_url("about:blank"), "about:blank")
        self.assertEqual(
            validate_navigation_url("https://www.google.com/search?q=openclaw&hl=en"),
            "https://www.google.com/search?q=openclaw&hl=en",
        )
        self.assertEqual(
            validate_navigation_url("http://127.0.0.1:8080/dashboard?cost=$50&item=book"),
            "http://127.0.0.1:8080/dashboard?cost=$50&item=book",
        )

    def test_unsafe_navigation_schemes_blocked(self):
        """Test dangerous schemes are rejected."""
        unsafe_urls = [
            "javascript:alert(1)",
            "file:///etc/passwd",
            "data:text/html,<h1>Hacked</h1>",
            "chrome://settings",
            "chrome-extension://malicious/popup.html",
            "view-source:https://example.com",
        ]
        for url in unsafe_urls:
            with self.assertRaises(BrowserSecurityError, msg=f"Should reject: {url}"):
                validate_navigation_url(url)

    def test_url_control_characters_blocked(self):
        """Test URLs with null bytes or newlines are rejected."""
        with self.assertRaises(BrowserSecurityError):
            validate_navigation_url("https://example.com/test\x00malicious")
        with self.assertRaises(BrowserSecurityError):
            validate_navigation_url("https://example.com/test\nmalicious")

    def test_safe_element_selectors(self):
        """Test valid CSS selectors."""
        valid_selectors = [
            "#submit-button",
            "button.btn-primary",
            "input[name='search']",
            "div.container > form > input:nth-child(2)",
            "a[href='/login']",
        ]
        for sel in valid_selectors:
            self.assertEqual(validate_element_selector(sel), sel)

    def test_unsafe_element_selectors(self):
        """Test malicious or malformed selectors are rejected."""
        invalid_selectors = [
            "",
            "   ",
            "button; rm -rf /",
            "input\x00[type=text]",
            "<script>alert(1)</script>",
        ]
        for sel in invalid_selectors:
            with self.assertRaises(BrowserSecurityError, msg=f"Should reject selector: {sel}"):
                validate_element_selector(sel)

    def test_validate_target_id(self):
        """Test target ID validation."""
        valid_ids = [
            "8D8502C986A1E742554B19D3ED856DC5",
            "tab1",
            "tab-target-42",
            "8d8502c9-86a1-e742-554b-19d3ed856dc5",
        ]
        for tid in valid_ids:
            self.assertEqual(validate_target_id(tid), tid)

        invalid_ids = [
            "",
            "   ",
            "../etc/passwd",
            "tab/1",
            "tab\x00id",
            "tab id with spaces",
            "a" * 65,  # too long
        ]
        for tid in invalid_ids:
            with self.assertRaises(BrowserSecurityError, msg=f"Should reject target ID: {tid}"):
                validate_target_id(tid)

    def test_validate_cdp_ws_url(self):
        """Test CDP WebSocket endpoint validation."""
        valid_urls = [
            "ws://127.0.0.1:9222/devtools/page/8D8502C986A1E742554B19D3ED856DC5",
            "ws://localhost:9222/devtools/browser/abc-123",
            "ws://127.0.0.1:45123/devtools/page/tab1",
        ]
        for url in valid_urls:
            self.assertEqual(validate_cdp_ws_url(url), url)

        invalid_urls = [
            "ws://0.0.0.0:9222/devtools/page/abc",  # non-loopback
            "ws://192.168.1.1:9222/devtools/page/abc",  # external IP
            "ws://evil.com:9222/devtools/page/abc",  # external domain
            "http://127.0.0.1:9222/devtools/page/abc",  # invalid scheme
            "ws://127.0.0.1:9222/nonexistent",  # invalid path
            "ws://127.0.0.1:9222/devtools/page/../../etc/passwd",  # path traversal
            "ws://127.0.0.1:0/devtools/page/abc",  # invalid port
        ]
        for url in invalid_urls:
            with self.assertRaises(BrowserSecurityError, msg=f"Should reject WS URL: {url}"):
                validate_cdp_ws_url(url)

    def test_consequential_interactions_expanded(self):
        """Test expanded consequential action patterns across messaging, finance, deletion, and settings."""
        # Form submit & messaging
        self.assertTrue(is_consequential_interaction("#submit-btn"))
        self.assertTrue(is_consequential_interaction("button#send-message"))
        self.assertTrue(is_consequential_interaction(".publish-article"))
        self.assertTrue(is_consequential_interaction("button.dispatch-order"))

        # Purchases & financial
        self.assertTrue(is_consequential_interaction("button[data-action='buy-now']"))
        self.assertTrue(is_consequential_interaction(".checkout-confirm"))
        self.assertTrue(is_consequential_interaction("#pay-invoice"))
        self.assertTrue(is_consequential_interaction("button.withdraw-funds"))

        # Deletion & destructive
        self.assertTrue(is_consequential_interaction("a.delete-account"))
        self.assertTrue(is_consequential_interaction(".drop-database"))
        self.assertTrue(is_consequential_interaction("button.trash-item"))
        self.assertTrue(is_consequential_interaction(".terminate-session"))

        # Settings & security
        self.assertTrue(is_consequential_interaction("button#change-password"))
        self.assertTrue(is_consequential_interaction(".reset-2fa"))
        self.assertTrue(is_consequential_interaction(".revoke-oauth"))

        # Benign read-only
        self.assertFalse(is_consequential_interaction("div.content"))
        self.assertFalse(is_consequential_interaction("h1.page-title"))
        self.assertFalse(is_consequential_interaction("span.user-badge"))

    def test_sensitive_storage_detection(self):
        """Test blocking queries targeting private browser storage and cookies."""
        self.assertTrue(is_sensitive_storage_query("return document.cookie;"))
        self.assertTrue(is_sensitive_storage_query("window.localStorage.getItem('token')"))
        self.assertTrue(is_sensitive_storage_query("sessionStorage.clear()"))
        self.assertTrue(is_sensitive_storage_query("window.indexedDB.open('db')"))
        self.assertFalse(is_sensitive_storage_query("document.title"))
        self.assertFalse(is_sensitive_storage_query("document.body.innerText"))

    def test_redact_sensitive_text(self):
        """Test scrubbing sensitive tokens, keys, and cards from visible text."""
        raw_text = (
            "Here is my auth header: Bearer abcdef1234567890.xyz\n"
            "Here is my JWT: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozG6P\n"
            "Here is an API key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234\n"
            "Here is a card: 4111 2222 3333 4444\n"
            "Benign content stays intact."
        )
        scrubbed = redact_sensitive_text(raw_text)
        self.assertNotIn("abcdef1234567890.xyz", scrubbed)
        self.assertIn("Bearer [REDACTED_TOKEN]", scrubbed)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", scrubbed)
        self.assertIn("[REDACTED_JWT]", scrubbed)
        self.assertNotIn("sk-ant-api03", scrubbed)
        self.assertIn("[REDACTED_API_KEY]", scrubbed)
        self.assertNotIn("4111 2222 3333 4444", scrubbed)
        self.assertIn("[REDACTED_CARD]", scrubbed)
        self.assertIn("Benign content stays intact.", scrubbed)

    def test_browser_confirmation_enforcement(self):
        """Test that confirmation requirement raises ConfirmationRequiredError when false."""
        with self.assertRaises(ConfirmationRequiredError) as ctx:
            verify_browser_confirmation(
                action="click",
                target="#submit-order",
                is_confirmed=False,
                reason="Submitting live checkout",
            )
        self.assertEqual(ctx.exception.action, "click")
        self.assertEqual(ctx.exception.target, "#submit-order")

        # When confirmed=True, no exception raised
        verify_browser_confirmation(
            action="click",
            target="#submit-order",
            is_confirmed=True,
            reason="Submitting live checkout",
        )

    def test_sanitize_input_value(self):
        """Test input value sanitization."""
        self.assertEqual(sanitize_input_value("hello world"), "hello world")
        with self.assertRaises(BrowserSecurityError):
            sanitize_input_value("malicious\x00input")


if __name__ == "__main__":
    unittest.main()
