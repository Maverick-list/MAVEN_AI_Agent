"""Maverick DevOS - Security and Allowlist Enforcement."""

import os
import re
from typing import List, Optional, Tuple
from maverick.core.config import AUTHORIZED_APPLICATIONS, AuthorizedApp


class SecurityError(Exception):
    """Raised when an operation violates security policy or allowlists."""
    pass


class ConfirmationRequiredError(SecurityError):
    """Raised when an operation requires explicit user confirmation."""
    def __init__(self, action: str, target: str, reason: str):
        super().__init__(f"Action '{action}' on '{target}' requires explicit confirmation: {reason}")
        self.action = action
        self.target = target
        self.reason = reason


# Safe URL pattern (HTTP/HTTPS only)
_SAFE_URL_REGEX = re.compile(r"^https?://[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=]+$")

# Safe Spotify URI pattern
_SAFE_SPOTIFY_URI_REGEX = re.compile(
    r"^(spotify:(track|album|artist|playlist|episode|show):[a-zA-Z0-9]+|https://open\.spotify\.com/(track|album|artist|playlist)/[a-zA-Z0-9]+(\?[a-zA-Z0-9=&_\-]+)?)$"
)


def get_authorized_app(app_id: str) -> AuthorizedApp:
    """Retrieve an authorized application by ID or raise SecurityError."""
    norm_id = app_id.strip().lower()
    if norm_id not in AUTHORIZED_APPLICATIONS:
        allowed = ", ".join(sorted(AUTHORIZED_APPLICATIONS.keys()))
        raise SecurityError(
            f"Unauthorized application: '{app_id}'. Authorized applications: {allowed}"
        )
    return AUTHORIZED_APPLICATIONS[norm_id]


def validate_app_arguments(app: AuthorizedApp, args: Optional[List[str]] = None) -> List[str]:
    """
    Validate and sanitize arguments passed to an authorized application.
    Enforces strict typing and rejects shell meta-characters.
    """
    if not args:
        return []

    if not app.allow_args:
        raise SecurityError(f"Application '{app.id}' does not permit custom arguments.")

    cleaned_args: List[str] = []
    for arg in args:
        if not isinstance(arg, str):
            raise SecurityError(f"Argument must be a string, got {type(arg).__name__}")

        val = arg.strip()
        # Global check: reject null bytes, newlines, and carriage returns across all arguments
        if "\x00" in val or "\n" in val or "\r" in val:
            raise SecurityError(f"Argument contains illegal control characters: '{repr(val)}'")

        # Application-specific validation
        if app.id in ("google-chrome", "firefox"):
            if not _SAFE_URL_REGEX.match(val):
                raise SecurityError(f"Invalid or unsafe URL passed to browser: '{val}'")
            cleaned_args.append(val)

        elif app.id == "spotify":
            if val in ("--no-zygote", "--disable-gpu"):
                cleaned_args.append(val)
            elif _SAFE_SPOTIFY_URI_REGEX.match(val):
                cleaned_args.append(val)
            else:
                raise SecurityError(f"Invalid Spotify URI or flag: '{val}'")

        elif app.id in ("code", "nautilus"):
            # Arguments must resolve to an existing local filesystem directory or file
            # Disallow flag arguments like --execute or -e
            if val.startswith("-"):
                # Permit only safe informational flags
                if val not in ("--version", "--help", "-v", "-h"):
                    raise SecurityError(f"Option flag '{val}' is not allowed for '{app.id}'.")
                cleaned_args.append(val)
            else:
                expanded = os.path.expanduser(val)
                resolved = os.path.realpath(expanded)
                if not os.path.exists(resolved):
                    raise SecurityError(f"Path target does not exist: '{val}' (resolved: '{resolved}')")
                cleaned_args.append(resolved)
        else:
            raise SecurityError(f"No argument policy configured for '{app.id}'.")

    return cleaned_args


def verify_confirmation(
    action: str,
    target: str,
    requires_confirmation: bool,
    is_confirmed: bool,
    reason: str,
) -> None:
    """Enforce confirmation requirement on consequential actions."""
    if requires_confirmation and not is_confirmed:
        raise ConfirmationRequiredError(action=action, target=target, reason=reason)


# Masking patterns for sensitive authentication credentials, tokens, and secrets
SENSITIVE_PATTERNS = [
    (re.compile(r"(bearer\s+)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"(xi-api-key\s*[:=]\s*)[A-Za-z0-9_\-\.]{6,}", re.IGNORECASE), r"\1[REDACTED_API_KEY]"),
    (re.compile(r"((?:api[-_]?key|token|secret|password|passwd|auth)\s*[:=]\s*)[A-Za-z0-9_\-\.]{6,}", re.IGNORECASE), r"\1[REDACTED_CREDENTIAL]"),
    (re.compile(r"\bsk[-_][A-Za-z0-9_\-]{16,}\b"), "[REDACTED_ELEVENLABS_OR_API_KEY]"),
    (re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b"), "[REDACTED_GOOGLE_API_KEY]"),
    (re.compile(r"\b[0-9]{8,10}:[a-zA-Z0-9_-]{35}\b"), "[REDACTED_TELEGRAM_BOT_TOKEN]"),
    (re.compile(r"\b[MNO][a-zA-Z0-9_-]{23,25}\.[a-zA-Z0-9_-]{6}\.[a-zA-Z0-9_-]{27,}\b"), "[REDACTED_DISCORD_TOKEN]"),
]


def redact_sensitive_text(text: str) -> str:
    """Scrub sensitive tokens, API keys, passwords, and secrets from strings."""
    if not text:
        return ""
    redacted = str(text)
    for pattern, replacement in SENSITIVE_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
