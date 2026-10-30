"""Unit tests for Browser Security and Policy Enforcement."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.browser.security import (
    validate_navigation_url,
    validate_element_selector,
    sanitize_input_value,
    is_consequential_interaction,
    verify_browser_confirmation,
    BrowserSecurityError,
)
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

    def test_consequential_interactions(self):
        """Test detection of consequential form/button interactions."""
        self.assertTrue(is_consequential_interaction("#submit-btn"))
        self.assertTrue(is_consequential_interaction("button[data-action='buy-now']"))
        self.assertTrue(is_consequential_interaction(".checkout-confirm"))
        self.assertTrue(is_consequential_interaction("a.delete-account"))
        self.assertFalse(is_consequential_interaction("div.content"))
        self.assertFalse(is_consequential_interaction("h1.page-title"))

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
