"""Unit tests for Maverick DevOS CLI execution."""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestCLI(unittest.TestCase):
    """Test CLI commands, JSON serialization, and exit codes."""

    def run_cli(self, args):
        cmd = [sys.executable, "-m", "maverick.cli"] + args
        env = os.environ.copy()
        env["PYTHONPATH"] = "/home/firza-ilmi/Maverick-DevOS"
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5.0,
            cwd="/home/firza-ilmi/Maverick-DevOS",
            env=env,
        )
        try:
            parsed = json.loads(res.stdout) if res.stdout else {}
        except json.JSONDecodeError:
            parsed = None
        return res.returncode, parsed, res.stderr

    def test_cli_app_list(self):
        code, data, _ = self.run_cli(["app", "list"])
        self.assertEqual(code, 0)
        self.assertIsNotNone(data)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["action"], "list_apps")
        self.assertGreaterEqual(data["count"], 9)

    def test_cli_app_status(self):
        code, data, _ = self.run_cli(["app", "status", "spotify"])
        self.assertEqual(code, 0)
        self.assertIsNotNone(data)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["app"]["id"], "spotify")

    def test_cli_confirmation_gating_exit_code(self):
        code, data, _ = self.run_cli(["app", "launch", "gnome-terminal"])
        # Exit code 2 indicates confirmation required
        self.assertEqual(code, 2)
        self.assertIsNotNone(data)
        self.assertEqual(data["status"], "confirmation_required")
        self.assertEqual(data["code"], "CONFIRMATION_REQUIRED")

    def test_cli_unauthorized_app_exit_code(self):
        code, data, _ = self.run_cli(["app", "launch", "forbidden_app"])
        # Exit code 1 indicates security violation
        self.assertEqual(code, 1)
        self.assertIsNotNone(data)
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["code"], "SECURITY_VIOLATION")

    def test_cli_spotify_players(self):
        code, data, _ = self.run_cli(["spotify", "players"])
        self.assertEqual(code, 0)
        self.assertIsNotNone(data)
        self.assertEqual(data["status"], "success")
        self.assertIsInstance(data["players"], list)

    def test_cli_wrapper_confinement_preserved(self):
        # Verify bin/maverick-ctl executes directly without aa-exec de-confinement
        wrapper_path = "/home/firza-ilmi/Maverick-DevOS/bin/maverick-ctl"
        with open(wrapper_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("aa-exec -p unconfined", content)

        # Run wrapper script directly
        res = subprocess.run(
            [wrapper_path, "app", "list"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5.0,
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "success")


if __name__ == "__main__":
    unittest.main()
