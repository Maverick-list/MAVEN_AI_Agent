"""Unit tests for Maverick DevOS Security & Policy Enforcement."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.core.config import AUTHORIZED_APPLICATIONS
from maverick.core.security import (
    get_authorized_app,
    validate_app_arguments,
    verify_confirmation,
    SecurityError,
    ConfirmationRequiredError,
)


class TestSecurity(unittest.TestCase):
    """Test allowlisting, argument sanitization, and confirmation gating."""

    def test_get_authorized_app_success(self):
        app = get_authorized_app("spotify")
        self.assertEqual(app.id, "spotify")
        self.assertEqual(app.display_name, "Spotify")

        app_code = get_authorized_app("CODE")
        self.assertEqual(app_code.id, "code")

    def test_get_authorized_app_rejection(self):
        with self.assertRaises(SecurityError) as ctx:
            get_authorized_app("unauthorized_app_xyz")
        self.assertIn("Unauthorized application", str(ctx.exception))

    def test_argument_validation_for_disallowed_app(self):
        claude = get_authorized_app("claude-desktop")
        self.assertFalse(claude.allow_args)
        with self.assertRaises(SecurityError) as ctx:
            validate_app_arguments(claude, ["--some-flag"])
        self.assertIn("does not permit custom arguments", str(ctx.exception))

    def test_argument_validation_for_browser_safe_url(self):
        chrome = get_authorized_app("google-chrome")
        cleaned = validate_app_arguments(chrome, ["https://gemini.google.com/app"])
        self.assertEqual(cleaned, ["https://gemini.google.com/app"])

    def test_argument_validation_for_browser_unsafe_url(self):
        chrome = get_authorized_app("google-chrome")
        with self.assertRaises(SecurityError) as ctx:
            validate_app_arguments(chrome, ["javascript:alert(1)"])
        self.assertIn("Invalid or unsafe URL", str(ctx.exception))

        with self.assertRaises(SecurityError):
            validate_app_arguments(chrome, ["file:///etc/passwd"])

    def test_argument_validation_for_spotify_uri(self):
        spotify = get_authorized_app("spotify")
        cleaned = validate_app_arguments(spotify, ["spotify:track:4cOdK2wGLETKBW3PvgPWqT"])
        self.assertEqual(cleaned, ["spotify:track:4cOdK2wGLETKBW3PvgPWqT"])

        cleaned_url = validate_app_arguments(
            spotify, ["https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"]
        )
        self.assertEqual(cleaned_url, ["https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"])

        # Regression: safe startup flags must be allowed
        cleaned_flags = validate_app_arguments(spotify, ["--no-zygote", "--disable-gpu"])
        self.assertEqual(cleaned_flags, ["--no-zygote", "--disable-gpu"])

        with self.assertRaises(SecurityError) as ctx:
            validate_app_arguments(spotify, ["malicious; rm -rf /"])
        self.assertIn("Invalid Spotify URI or flag", str(ctx.exception))

        with self.assertRaises(SecurityError):
            validate_app_arguments(spotify, ["--unauthorized-flag"])

    def test_argument_validation_for_code_path(self):
        code = get_authorized_app("code")
        # Existing directory
        cleaned = validate_app_arguments(code, ["~"])
        self.assertEqual(len(cleaned), 1)
        self.assertTrue(os.path.isdir(cleaned[0]))

        # Non-existing directory should fail
        with self.assertRaises(SecurityError) as ctx:
            validate_app_arguments(code, ["/non/existent/path/xyz_12345"])
        self.assertIn("Path target does not exist", str(ctx.exception))

        # Disallow arbitrary flags
        with self.assertRaises(SecurityError) as ctx:
            validate_app_arguments(code, ["--install-extension"])
        self.assertIn("Option flag '--install-extension' is not allowed", str(ctx.exception))

    def test_confirmation_gating(self):
        # When requires_confirmation is True and is_confirmed is False
        with self.assertRaises(ConfirmationRequiredError) as ctx:
            verify_confirmation(
                action="launch",
                target="gnome-terminal",
                requires_confirmation=True,
                is_confirmed=False,
                reason="Terminal launch requires user approval.",
            )
        self.assertEqual(ctx.exception.action, "launch")
        self.assertEqual(ctx.exception.target, "gnome-terminal")

        # When confirmed is True, should not raise
        verify_confirmation(
            action="launch",
            target="gnome-terminal",
            requires_confirmation=True,
            is_confirmed=True,
            reason="Confirmed",
        )


if __name__ == "__main__":
    unittest.main()
