"""Unit tests for System Awareness & Telemetry."""

import os
import sys
import unittest
from unittest.mock import patch, mock_open

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.system.monitor import (
    get_cpu_usage,
    get_memory_usage,
    get_disk_usage,
    get_battery_status,
    get_os_session_info,
    get_network_status,
    get_system_resources,
    get_system_summary,
)


class TestSystemMonitor(unittest.TestCase):
    """Test safe system telemetry queries."""

    def test_cpu_usage(self):
        """Test CPU metrics return valid percentages and load averages."""
        cpu = get_cpu_usage()
        self.assertIn("usage_percent", cpu)
        self.assertIsInstance(cpu["usage_percent"], (int, float))
        self.assertGreaterEqual(cpu["usage_percent"], 0.0)
        self.assertIn("cores_logical", cpu)
        self.assertGreaterEqual(cpu["cores_logical"], 1)
        self.assertIn("load_average", cpu)
        self.assertIn("1m", cpu["load_average"])

    def test_memory_usage(self):
        """Test RAM and Swap telemetry."""
        mem = get_memory_usage()
        self.assertIn("total_gb", mem)
        self.assertIn("used_gb", mem)
        self.assertIn("available_gb", mem)
        self.assertIn("percent", mem)
        self.assertGreater(mem["total_gb"], 0.0)
        self.assertGreaterEqual(mem["percent"], 0.0)
        self.assertLessEqual(mem["percent"], 100.0)

    def test_disk_usage(self):
        """Test disk usage for root and home paths."""
        disk = get_disk_usage()
        self.assertIn("root", disk)
        self.assertIn("home", disk)
        self.assertGreater(disk["root"]["total_gb"], 0.0)
        self.assertGreater(disk["home"]["total_gb"], 0.0)
        self.assertEqual(disk["root"]["path"], "/")

    def test_battery_status(self):
        """Test battery and AC adapter status."""
        bat = get_battery_status()
        self.assertIn("has_battery", bat)
        self.assertIn("percent", bat)
        self.assertIn("status", bat)
        self.assertIn("is_charging", bat)
        self.assertIn("ac_connected", bat)
        self.assertGreaterEqual(bat["percent"], 0)
        self.assertLessEqual(bat["percent"], 100)

    def test_os_session_info(self):
        """Test OS distribution and desktop environment details."""
        os_info = get_os_session_info()
        self.assertIn("os", os_info)
        self.assertIn("kernel", os_info)
        self.assertIn("desktop", os_info)
        self.assertIn("session_type", os_info)
        self.assertIn("hostname", os_info)
        self.assertGreaterEqual(os_info["uptime_hours"], 0.0)

    def test_network_status(self):
        """Test network connectivity detection."""
        net = get_network_status()
        self.assertIn("connected", net)
        self.assertIsInstance(net["connected"], bool)
        self.assertIn("interfaces", net)
        self.assertIsInstance(net["interfaces"], list)

    def test_system_summary_consolidation(self):
        """Test consolidated summary contains all telemetry domains."""
        summary = get_system_summary()
        self.assertIn("os_session", summary)
        self.assertIn("resources", summary)
        self.assertIn("battery", summary)
        self.assertIn("network", summary)
        self.assertIn("timestamp", summary)


if __name__ == "__main__":
    unittest.main()
