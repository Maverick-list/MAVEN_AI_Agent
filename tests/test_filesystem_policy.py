"""
Tests for Filesystem Security Policies, Dotfile Allowlisting, and Overwrite Protection.
"""

import os
import shutil
import tempfile
import unittest

from maverick.intelligence.tools import ToolRegistry


class TestFilesystemPolicy(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.temp_dir = tempfile.mkdtemp(prefix="maven_fs_policy_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_project_dotfiles_allowed(self):
        """Verify legitimate developer dotfiles are permitted in project directories."""
        dotfiles = [
            (".gitignore", "*.pyc\n__pycache__/\n"),
            (".editorconfig", "root = true\n"),
            (".prettierrc", '{"semi": true}\n'),
            (".dockerignore", "node_modules\n"),
            (".vscode/launch.json", '{"version": "0.2.0"}\n'),
        ]
        for name, content in dotfiles:
            target = os.path.join(self.temp_dir, name)
            res = self.registry.execute("filesystem_write_file", {"path": target, "content": content})
            self.assertEqual(res["status"], "success", f"Failed to write allowed dotfile {name}: {res}")
            self.assertTrue(os.path.isfile(target))
            with open(target, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), content)

    def test_environment_secret_files_gated(self):
        """Verify .env and .env.* files require explicit confirmation on write."""
        env_files = [".env", ".env.local", ".env.production"]
        for env_name in env_files:
            target = os.path.join(self.temp_dir, env_name)

            # Unconfirmed attempt must trigger confirmation_required
            res_unconf = self.registry.execute("filesystem_write_file", {"path": target, "content": "SECRET_KEY=12345"})
            self.assertEqual(res_unconf["status"], "confirmation_required")
            self.assertFalse(os.path.exists(target))

            # Confirmed attempt must succeed
            res_conf = self.registry.execute("filesystem_write_file", {"path": target, "content": "SECRET_KEY=12345"}, confirmed=True)
            self.assertEqual(res_conf["status"], "success")
            self.assertTrue(os.path.isfile(target))

    def test_overwrite_protection_and_backup(self):
        """Verify existing files cannot be silently overwritten without confirmation."""
        target = os.path.join(self.temp_dir, "document.txt")

        # 1. First write (new file) succeeds
        res1 = self.registry.execute("filesystem_write_file", {"path": target, "content": "Version 1.0\n"})
        self.assertEqual(res1["status"], "success")
        self.assertFalse(res1["result"].get("overwritten", False))

        # 2. Overwrite attempt without confirmation is intercepted
        res2 = self.registry.execute("filesystem_write_file", {"path": target, "content": "Version 2.0 (Overwritten)\n"})
        self.assertEqual(res2["status"], "confirmation_required")
        # Ensure original file content was preserved!
        with open(target, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "Version 1.0\n")

        # 3. Confirmed overwrite succeeds and generates a .bak file
        res3 = self.registry.execute("filesystem_write_file", {"path": target, "content": "Version 2.0 (Overwritten)\n"}, confirmed=True)
        self.assertEqual(res3["status"], "success")
        self.assertTrue(res3["result"].get("overwritten", False))
        backup_path = res3["result"].get("backup_path")
        self.assertIsNotNone(backup_path)
        self.assertTrue(os.path.isfile(backup_path))

        # Backup content is original Version 1.0
        with open(backup_path, "r", encoding="utf-8") as bf:
            self.assertEqual(bf.read(), "Version 1.0\n")

        # Target content is now Version 2.0
        with open(target, "r", encoding="utf-8") as tf:
            self.assertEqual(tf.read(), "Version 2.0 (Overwritten)\n")

    def test_parent_traversal_and_absolute_escape_blocked(self):
        """Verify attempts to escape workspace to /etc or system root are blocked."""
        bad_paths = [
            "/etc/evil_config.conf",
            "/var/log/fake.log",
            os.path.join(self.temp_dir, "../../../../../../etc/shadow"),
        ]
        for p in bad_paths:
            res_write = self.registry.execute("filesystem_write_file", {"path": p, "content": "evil"}, confirmed=True)
            self.assertEqual(res_write["status"], "security_violation")

            res_read = self.registry.execute("filesystem_read_file", {"path": p})
            self.assertIn(res_read["status"], ("security_violation", "error"))

    def test_root_sensitive_configuration_blocked(self):
        """Verify root home sensitive dotfiles (~/.ssh, ~/.bashrc) cannot be targeted."""
        sensitive_targets = [
            "~/.ssh/authorized_keys",
            "~/.bashrc",
            "~/.profile",
            "~/.gnupg/secring.gpg",
        ]
        for target in sensitive_targets:
            res = self.registry.execute("filesystem_write_file", {"path": target, "content": "bad"}, confirmed=True)
            self.assertEqual(res["status"], "security_violation", f"Target {target} was not blocked!")

    def test_unicode_and_nested_directories(self):
        """Verify nested directory creation and Unicode filenames succeed cleanly."""
        nested_path = os.path.join(self.temp_dir, "proyek/sub_direktori/Dokumen_Laporan_日本語.md")
        content = "# Laporan Kinerja Sistem\nStatus: Berjalan normal 🚀\n"

        res = self.registry.execute("filesystem_write_file", {"path": nested_path, "content": content})
        self.assertEqual(res["status"], "success")
        self.assertTrue(os.path.isfile(nested_path))

        read_res = self.registry.execute("filesystem_read_file", {"path": nested_path})
        self.assertEqual(read_res["status"], "success")
        self.assertIn("Berjalan normal 🚀", read_res["result"]["content"])


if __name__ == "__main__":
    unittest.main()

