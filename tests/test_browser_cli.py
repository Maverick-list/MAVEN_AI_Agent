"""Unit tests for browser CLI subcommands."""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

CLI_BIN = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bin", "maverick-ctl"))


class TestBrowserCLI(unittest.TestCase):
    """Test CLI commands, JSON formatting, and exit codes for browser operations."""

    def run_cli(self, args, check=False):
        """Helper to invoke maverick-ctl CLI."""
        cmd = [CLI_BIN, "browser"] + args
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
        )
        return proc

    def test_cli_browser_help(self):
        """Test maverick-ctl browser --help."""
        proc = self.run_cli(["--help"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("status", proc.stdout)
        self.assertIn("navigate", proc.stdout)
        self.assertIn("screenshot", proc.stdout)

    def test_cli_browser_status_json(self):
        """Test maverick-ctl browser status returns structured JSON."""
        proc = self.run_cli(["status"])
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "success")
        self.assertIn("installed", data)
        self.assertIn("active", data)
        self.assertIn("cdp_url", data)

    def test_cli_browser_navigate_security_violation(self):
        """Test navigation to disallowed scheme returns exit code 1 with SECURITY_VIOLATION."""
        proc = self.run_cli(["navigate", "javascript:alert(1)"])
        self.assertEqual(proc.returncode, 1)
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "error")
        self.assertEqual(data.get("code"), "SECURITY_VIOLATION")

    def test_cli_browser_consequential_confirmation_required(self):
        """Test consequential click without confirmation returns exit code 2."""
        proc = self.run_cli(["click", "button#submit-order"])
        self.assertEqual(proc.returncode, 2)
        data = json.loads(proc.stdout)
        self.assertEqual(data.get("status"), "confirmation_required")
        self.assertEqual(data.get("code"), "CONFIRMATION_REQUIRED")
        self.assertIn("--confirmed", data.get("prompt", ""))


if __name__ == "__main__":
    unittest.main()
