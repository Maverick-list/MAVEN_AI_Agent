"""Maverick DevOS - Browser Security and Policy Enforcement."""

import os
import re
from typing import Optional
from maverick.core.security import SecurityError, ConfirmationRequiredError, _SAFE_URL_REGEX


class BrowserSecurityError(SecurityError):
    """Raised when browser automation encounters a security violation."""
    pass


# Disallowed URL schemes
DISALLOWED_SCHEMES = ("javascript:", "data:", "file:", "chrome:", "chrome-extension:", "view-source:")

# Safe CSS selector pattern: permits standard tags, classes, IDs, attribute selectors, and pseudoclasses
_SAFE_SELECTOR_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.\#\:\s\>\[\]\=\'\"\(\)\,\/]+$")

# Selectors that typically imply consequential form submissions or destructive actions
CONSEQUENTIAL_SELECTOR_PATTERNS = (
    "submit",
    "buy",
    "checkout",
    "purchase",
    "delete",
    "destroy",
    "transfer",
    "confirm-order",
    "send-message",
)


def validate_navigation_url(url: str) -> str:
    """Validate that a URL is safe for browser navigation."""
    if not isinstance(url, str):
        raise BrowserSecurityError(f"URL must be a string, got {type(url).__name__}")

    clean = url.strip()
    if clean == "about:blank":
        return clean

    # Reject null bytes and control chars
    if "\x00" in clean or "\n" in clean or "\r" in clean:
        raise BrowserSecurityError("URL contains illegal control characters.")

    lower = clean.lower()
    for scheme in DISALLOWED_SCHEMES:
        if lower.startswith(scheme):
            raise BrowserSecurityError(f"Navigation to unsafe scheme '{scheme}' is strictly blocked.")

    if not _SAFE_URL_REGEX.match(clean):
        raise BrowserSecurityError(f"Invalid or unsafe URL format: '{clean}'")

    return clean


def validate_element_selector(selector: str) -> str:
    """Validate and sanitize a CSS/element selector."""
    if not isinstance(selector, str):
        raise BrowserSecurityError(f"Selector must be a string, got {type(selector).__name__}")

    clean = selector.strip()
    if not clean:
        raise BrowserSecurityError("Selector cannot be empty.")

    if "\x00" in clean or "\n" in clean or "\r" in clean:
        raise BrowserSecurityError("Selector contains illegal control characters.")

    if not _SAFE_SELECTOR_REGEX.match(clean):
        raise BrowserSecurityError(f"Invalid or unsafe element selector syntax: '{clean}'")

    return clean


def sanitize_input_value(value: str) -> str:
    """Sanitize text input to be filled into web fields."""
    if not isinstance(value, str):
        raise BrowserSecurityError(f"Input value must be a string, got {type(value).__name__}")

    if "\x00" in value:
        raise BrowserSecurityError("Input value cannot contain null bytes.")

    return value


def is_consequential_interaction(selector: str) -> bool:
    """Determine whether an element interaction likely has external consequences."""
    lower = selector.lower()
    return any(p in lower for p in CONSEQUENTIAL_SELECTOR_PATTERNS)


def verify_browser_confirmation(action: str, target: str, is_confirmed: bool, reason: str) -> None:
    """Enforce explicit confirmation on consequential browser actions."""
    if not is_confirmed:
        raise ConfirmationRequiredError(action=action, target=target, reason=reason)
