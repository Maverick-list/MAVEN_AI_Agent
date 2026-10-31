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
        unauthorized = [
            "unauthorized_app_xyz",
            "/bin/bash",
            "/bin/sh",
            "/usr/bin/python3",
            "sudo",
            "rm",
            "systemd-run",
            "curl",
        ]
        for app in unauthorized:
            with self.subTest(app=app):
                with self.assertRaises(SecurityError) as ctx:
                    get_authorized_app(app)
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

        # Legitimate multi-parameter query URLs must be allowed
        cleaned_query = validate_app_arguments(chrome, ["https://gemini.google.com/app?hl=en&authuser=0"])
        self.assertEqual(cleaned_query, ["https://gemini.google.com/app?hl=en&authuser=0"])

    def test_argument_validation_for_browser_unsafe_url(self):
        chrome = get_authorized_app("google-chrome")
        with self.assertRaises(SecurityError) as ctx:
            validate_app_arguments(chrome, ["javascript:alert(1)"])
        self.assertIn("Invalid or unsafe URL", str(ctx.exception))

        with self.assertRaises(SecurityError):
            validate_app_arguments(chrome, ["file:///etc/passwd"])

        with self.assertRaises(SecurityError):
            validate_app_arguments(chrome, ["data:text/html,<script>alert(1)</script>"])

    def test_argument_validation_for_spotify_uri(self):
        spotify = get_authorized_app("spotify")
        cleaned = validate_app_arguments(spotify, ["spotify:track:4cOdK2wGLETKBW3PvgPWqT"])
        self.assertEqual(cleaned, ["spotify:track:4cOdK2wGLETKBW3PvgPWqT"])

        cleaned_url = validate_app_arguments(
            spotify, ["https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"]
        )
        self.assertEqual(cleaned_url, ["https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"])

        # Legitimate Spotify web URL with query parameters
        cleaned_url_query = validate_app_arguments(
            spotify, ["https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT?si=abc123xyz&context=playlist"]
        )
        self.assertEqual(cleaned_url_query, ["https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT?si=abc123xyz&context=playlist"])

        # Safe startup flags must be allowed
        cleaned_flags = validate_app_arguments(spotify, ["--no-zygote", "--disable-gpu"])
        self.assertEqual(cleaned_flags, ["--no-zygote", "--disable-gpu"])

        with self.assertRaises(SecurityError) as ctx:
            validate_app_arguments(spotify, ["malicious; rm -rf /"])
        self.assertIn("Invalid Spotify URI or flag", str(ctx.exception))

        with self.assertRaises(SecurityError):
            validate_app_arguments(spotify, ["--unauthorized-flag"])
        self.assertIn("Invalid Spotify URI or flag", str(ctx.exception))

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

    def test_command_injection_rejection(self):
        spotify = get_authorized_app("spotify")
        dangerous_payloads = [
            "spotify:track:123; rm -rf /",
            "spotify:track:123 && id",
            "spotify:track:123 | nc localhost 80",
            "spotify:track:123`whoami`",
            "spotify:track:123$(id)",
            "spotify:track:123\x00evil",
            "spotify:track:123\nevil",
            "spotify:track:123\revil",
        ]
        for payload in dangerous_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(SecurityError):
                    validate_app_arguments(spotify, [payload])

    def test_spotify_unexpected_uris(self):
        spotify = get_authorized_app("spotify")
        invalid_uris = [
            "http://open.spotify.com/track/123",  # Insecure HTTP
            "ftp://open.spotify.com/track/123",
            "spotify:exe:malicious",              # Invalid type
            "spotify:../../etc/passwd",           # Path traversal attempt
            "javascript:alert('pwned')",
            "data:text/html,<script>alert(1)</script>",
            "spotify:track:123?extra=bad&injection=true",
        ]
        for uri in invalid_uris:
            with self.subTest(uri=uri):
                with self.assertRaises(SecurityError):
                    validate_app_arguments(spotify, [uri])

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

    def test_filesystem_sandbox_path_traversal_prevention(self):
        from maverick.intelligence.tools import ToolRegistry, SecurityPolicyViolationError
        reg = ToolRegistry()

        # Path traversal with relative ~ expansion
        traversal_paths = [
            "~/../../etc/cron.d/malicious",
            "~/../../etc/passwd",
            "~/../../../tmp/../etc/shadow",
            "~/.ssh/authorized_keys",
            "~/.bashrc",
        ]
        for bad_path in traversal_paths:
            with self.subTest(bad_path=bad_path):
                # Calling execute returns security_violation
                res_create = reg.execute("filesystem_create_dir", {"path": bad_path})
                self.assertEqual(res_create.get("status"), "security_violation")
                self.assertIn("restricted", res_create.get("error", "").lower())

                res_write = reg.execute("filesystem_write_file", {"path": bad_path, "content": "echo hack"})
                self.assertEqual(res_write.get("status"), "security_violation")
                self.assertIn("restricted", res_write.get("error", "").lower())

                # Calling underlying tool handler directly raises SecurityPolicyViolationError
                with self.assertRaises(SecurityPolicyViolationError):
                    reg._tool_filesystem_create_dir({"path": bad_path})
                with self.assertRaises(SecurityPolicyViolationError):
                    reg._tool_filesystem_write_file({"path": bad_path, "content": "echo hack"})


if __name__ == "__main__":
    unittest.main()
