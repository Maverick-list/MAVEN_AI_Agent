"""Maverick DevOS - Browser Security and Policy Enforcement."""

import os
import re
import urllib.parse
from typing import Optional
from maverick.core.security import SecurityError, ConfirmationRequiredError, _SAFE_URL_REGEX


class BrowserSecurityError(SecurityError):
    """Raised when browser automation encounters a security violation."""
    pass


# Disallowed URL schemes
DISALLOWED_SCHEMES = ("javascript:", "data:", "file:", "chrome:", "chrome-extension:", "view-source:")

# Safe CSS selector pattern: permits standard tags, classes, IDs, attribute selectors, and pseudoclasses
_SAFE_SELECTOR_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.\#\:\s\>\[\]\=\'\"\(\)\,\/]+$")

# Valid Chrome Target ID pattern (alphanumeric, underscore, hyphen)
_VALID_TARGET_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")

# Valid CDP WebSocket path pattern: strictly /devtools/page/<id> or /devtools/browser/<id>
_VALID_WS_PATH_REGEX = re.compile(r"^/devtools/(page|browser)/[a-zA-Z0-9_\-]+$")

# Selectors that typically imply consequential form submissions, messaging, purchases, or destructive actions
CONSEQUENTIAL_SELECTOR_PATTERNS = (
    # Form submission & messaging
    "submit",
    "send",
    "publish",
    "post",
    "dispatch",
    "confirm",
    # Purchases & billing
    "buy",
    "checkout",
    "purchase",
    "pay",
    "order",
    "subscribe",
    "transfer",
    "withdraw",
    "billing",
    # Destructive & deletion
    "delete",
    "destroy",
    "remove",
    "trash",
    "drop",
    "wipe",
    "terminate",
    "cancel-account",
    # Account settings & credentials
    "settings",
    "password",
    "security",
    "update-account",
    "reset",
    "2fa",
    "oauth",
    "revoke",
)

# Sensitive browser storage keywords that must never be queried
SENSITIVE_STORAGE_KEYWORDS = (
    "document.cookie",
    "localstorage",
    "sessionstorage",
    "indexeddb",
    "opendatabase",
    "caches.open",
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


def validate_target_id(target_id: str) -> str:
    """Validate Chrome CDP Target ID format."""
    if not isinstance(target_id, str):
        raise BrowserSecurityError(f"Target ID must be a string, got {type(target_id).__name__}")

    clean = target_id.strip()
    if not clean or "\x00" in clean or "/" in clean or ".." in clean:
        raise BrowserSecurityError(f"Invalid or unsafe target ID: '{target_id}'")

    if not _VALID_TARGET_ID_REGEX.match(clean):
        raise BrowserSecurityError(f"Target ID '{clean}' does not match expected format.")

    return clean


def validate_cdp_ws_url(ws_url: str) -> str:
    """
    Validate that a WebSocket debugger URL strictly points to local loopback
    and a valid CDP DevTools target endpoint.
    """
    if not isinstance(ws_url, str):
        raise BrowserSecurityError(f"WebSocket URL must be a string, got {type(ws_url).__name__}")

    clean = ws_url.strip()
    if not clean.startswith("ws://"):
        raise BrowserSecurityError(f"CDP WebSocket URL must use ws:// scheme, got '{clean}'.")

    parsed = urllib.parse.urlsplit(clean)
    if parsed.scheme != "ws":
        raise BrowserSecurityError(f"Disallowed scheme '{parsed.scheme}': only ws:// is permitted.")

    hostname = (parsed.hostname or "").lower()
    if hostname not in ("127.0.0.1", "localhost"):
        raise BrowserSecurityError(
            f"CDP connection to external/non-loopback host '{hostname}' is strictly blocked."
        )

    if not parsed.port or parsed.port < 1 or parsed.port > 65535:
        raise BrowserSecurityError(f"Invalid or missing port in CDP WebSocket URL '{clean}'.")

    if not _VALID_WS_PATH_REGEX.match(parsed.path):
        raise BrowserSecurityError(f"Invalid CDP WebSocket path '{parsed.path}'.")

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


def is_sensitive_storage_query(expression: str) -> bool:
    """Determine whether a JavaScript expression queries sensitive browser storage or cookies."""
    lower = expression.lower()
    return any(k in lower for k in SENSITIVE_STORAGE_KEYWORDS)


def verify_browser_confirmation(action: str, target: str, is_confirmed: bool, reason: str) -> None:
    """Enforce explicit confirmation on consequential browser actions."""
    if not is_confirmed:
        raise ConfirmationRequiredError(action=action, target=target, reason=reason)
