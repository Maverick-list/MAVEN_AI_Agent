"""Unit & Integration Tests for Memory Management, Subsystem Profiling, and 6 Operating Modes."""

import unittest
from unittest.mock import MagicMock, patch
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.system.memory_manager import (
    MemoryManager,
    MavenOperatingMode,
    MemoryPressureLevel,
    BoundedQueue,
)
from maverick.dashboard.server import TelemetryHub


class TestMemoryAndModes(unittest.TestCase):
    """Test suite verifying RAM optimization, bounded queues, and mode switches."""

    def setUp(self):
        self.mgr = MemoryManager()
        self.mgr.set_mode(MavenOperatingMode.NORMAL)

    def tearDown(self):
        self.mgr.set_mode(MavenOperatingMode.NORMAL)

    def test_all_six_operating_modes_exist(self):
        """Verify all 6 canonical operating modes are defined."""
        modes = [m.value for m in MavenOperatingMode]
        self.assertIn("normal", modes)
        self.assertIn("voice", modes)
        self.assertIn("vision", modes)
        self.assertIn("full_assistant", modes)
        self.assertIn("low_memory", modes)
        self.assertIn("safe_idle", modes)
        self.assertEqual(len(modes), 6)

    def test_mode_transitions(self):
        """Test transitions between operating modes."""
        res_voice = self.mgr.set_mode(MavenOperatingMode.VOICE)
        self.assertEqual(res_voice["status"], "success")
        self.assertEqual(res_voice["mode"], "voice")
        self.assertEqual(self.mgr.current_mode, MavenOperatingMode.VOICE)

        # Transition to LOW_MEMORY triggers defensive cleanup
        res_low = self.mgr.set_mode(MavenOperatingMode.LOW_MEMORY)
        self.assertEqual(res_low["status"], "success")
        self.assertEqual(res_low["mode"], "low_memory")
        self.assertIn("garbage_collection_executed", res_low["actions"])

        # Transition back to NORMAL
        res_norm = self.mgr.set_mode(MavenOperatingMode.NORMAL)
        self.assertEqual(res_norm["status"], "success")
        self.assertEqual(res_norm["mode"], "normal")

    def test_mode_change_hooks(self):
        """Test mode hook notification callbacks."""
        hook_called = []

        def my_hook(prev, target):
            hook_called.append((prev, target))

        self.mgr.register_mode_hook(my_hook)
        self.mgr.set_mode(MavenOperatingMode.SAFE_IDLE)
        self.assertGreaterEqual(len(hook_called), 1)
        self.assertEqual(hook_called[-1][1], MavenOperatingMode.SAFE_IDLE)

    def test_bounded_queue_eviction(self):
        """Test BoundedQueue evicts oldest items to prevent memory leaks."""
        bq = BoundedQueue(maxlen=3)
        bq.push("item1")
        bq.push("item2")
        bq.push("item3")
        self.assertEqual(bq.size(), 3)

        # 4th item triggers eviction of item1
        bq.push("item4")
        self.assertEqual(bq.size(), 3)
        stats = bq.stats()
        self.assertEqual(stats["evicted_count"], 1)

        # Oldest item is now item2
        first = bq.pop()
        self.assertEqual(first, "item2")

    def test_system_memory_status_and_pressure(self):
        """Test system RAM telemetry and pressure classification."""
        stat = self.mgr.get_system_memory_status()
        self.assertIn("total_gb", stat)
        self.assertIn("used_gb", stat)
        self.assertIn("available_gb", stat)
        self.assertIn("pressure_level", stat)
        self.assertIn(stat["pressure_level"], [p.value for p in MemoryPressureLevel])

    def test_process_memory_info(self):
        """Test current process RSS and PSS telemetry."""
        p_info = self.mgr.get_process_memory_info()
        self.assertIn("rss_mb", p_info)
        self.assertIn("pss_mb", p_info)
        self.assertIn("threads", p_info)
        self.assertGreater(p_info["rss_mb"], 0.0)

    def test_subsystem_memory_profiling(self):
        """Test consolidated subsystem profiling."""
        prof = self.mgr.profile_all_subsystems()
        self.assertIn("subsystems", prof)
        self.assertIn("total_maven_rss_mb", prof)
        self.assertIn("total_maven_pss_mb", prof)
        self.assertGreater(len(prof["subsystems"]), 0)

    def test_telemetry_hub_mode_endpoints(self):
        """Test TelemetryHub mode integration."""
        hub = TelemetryHub()
        mode_info = hub.get_operating_mode()
        self.assertEqual(mode_info["status"], "success")
        self.assertIn("active_mode", mode_info)
        self.assertEqual(len(mode_info["all_modes"]), 6)

        # Switch mode via hub
        set_res = hub.set_operating_mode("low_memory")
        self.assertEqual(set_res["status"], "success")
        self.assertEqual(set_res["mode"], "low_memory")

        # Invalid mode
        err_res = hub.set_operating_mode("invalid_super_mode")
        self.assertEqual(err_res["status"], "error")

        # Memory profile via hub
        prof_hub = hub.get_memory_profile()
        self.assertIn("subsystems", prof_hub)

        # Cleanup memory via hub
        clean_res = hub.cleanup_memory()
        self.assertIn("pressure", clean_res)

        # Reset back to normal
        hub.set_operating_mode("normal")


if __name__ == "__main__":
    unittest.main()
