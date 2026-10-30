"""Maverick DevOS - Notification Redaction Filter & Category Management."""

import re
from typing import Set

# Notification categories supported by Maverick
SUPPORTED_CATEGORIES: Set[str] = {"system", "media", "browser", "task", "alert", "social"}

# Default enabled categories
DEFAULT_ENABLED_CATEGORIES: Set[str] = {"system", "media", "browser", "task", "alert"}

# Sensitive pattern scrubbers for desktop notifications
_CARD_REGEX = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
_BEARER_REGEX = re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{15,}", re.IGNORECASE)
_JWT_REGEX = re.compile(r"eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]+")
_API_KEY_REGEX = re.compile(r"\b(?:sk-[a-zA-Z0-9_\-]{20,}|(?:ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36})\b")
_PASSWORD_REGEX = re.compile(r"(?:password|passcode|secret|pin)[:\s=]+([^\s,]+)", re.IGNORECASE)
_AUTH_TOKEN_REGEX = re.compile(r"(?:token|auth|bearer|key)[:\s=]+([a-zA-Z0-9_\-\.]{12,})", re.IGNORECASE)
_OTP_CODE_REGEX = re.compile(r"\b\d{4,8}\b")


def sanitize_notification_text(text: str) -> str:
    """
    Scrub authentication codes, OTPs, passwords, private tokens,
    API keys, and credit card numbers from notification title or body text.
    Strips embedded null bytes to avoid subprocess command errors.
    """
    if not isinstance(text, str):
        return ""

    # Strip embedded null bytes and terminal control artifacts
    sanitized = text.replace("\x00", "")

    # 1. Redact credit card numbers (contiguous, dashed, or spaced)
    sanitized = _CARD_REGEX.sub("[REDACTED_CARD]", sanitized)

    # 2. Redact Bearer tokens & JWTs
    sanitized = _BEARER_REGEX.sub("Bearer [REDACTED_TOKEN]", sanitized)
    sanitized = _JWT_REGEX.sub("[REDACTED_JWT]", sanitized)

    # 3. Redact API keys (OpenAI sk-*, GitHub ghp_*, etc.)
    sanitized = _API_KEY_REGEX.sub("[REDACTED_API_KEY]", sanitized)

    # 4. Redact explicit password/secret declarations
    sanitized = _PASSWORD_REGEX.sub(r"password: [REDACTED_PASSWORD]", sanitized)

    # 5. Redact auth tokens
    sanitized = _AUTH_TOKEN_REGEX.sub(r"token: [REDACTED_TOKEN]", sanitized)

    # 6. Redact isolated 4 to 8 digit verification codes (e.g. 2FA/SMS codes)
    # But preserve standard 4-digit calendar years (1900-2099)
    def _mask_otp(match):
        val = match.group(0)
        if len(val) == 4 and (1900 <= int(val) <= 2099):
            return val  # preserve years
        return "[REDACTED_CODE]"

    sanitized = _OTP_CODE_REGEX.sub(_mask_otp, sanitized)
    return sanitized.strip()
