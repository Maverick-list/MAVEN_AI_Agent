"""Unit tests for SystemDependencyVerifier."""

import unittest
from maverick.core.dependencies import (
    SystemDependencyVerifier,
    has_dependency,
    get_dependency_path,
)


class TestDependencyVerifier(unittest.TestCase):
    def test_python3_is_always_available(self):
        verifier = SystemDependencyVerifier.get_instance()
        self.assertTrue(verifier.has_binary("python3"))
        path = verifier.get_path("python3")
        self.assertIsNotNone(path)
        self.assertTrue(path.endswith("python3"))

    def test_nonexistent_binary(self):
        self.assertFalse(has_dependency("nonexistent_binary_xyz_12345"))
        self.assertIsNone(get_dependency_path("nonexistent_binary_xyz_12345"))

    def test_audit_environment(self):
        verifier = SystemDependencyVerifier.get_instance()
        report = verifier.audit_environment()
        self.assertIn("capabilities", report)
        self.assertIn("available_count", report)
        self.assertGreater(report["available_count"], 0)
        self.assertTrue(report["capabilities"]["python3"]["available"])


if __name__ == "__main__":
    unittest.main()

