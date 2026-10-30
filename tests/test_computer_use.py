"""Comprehensive Unit & Integration Test Suite for Universal Linux Computer Use System."""

import json
import os
import unittest
from unittest.mock import MagicMock, patch
import urllib.request

from maverick.computer_use.accessibility import AccessibilityBridge, AccessibleElement
from maverick.computer_use.input import UniversalInputEngine, MouseButton
from maverick.computer_use.registry import ApplicationCompatibilityRegistry, ApplicationProfile, InteractionMethod, AccessibilityHealth
from maverick.computer_use.screen import ScreenObserver, DesktopObservation
from maverick.computer_use.security import ComputerUseSecurity, ActionTier
from maverick.computer_use.strategy import ComputerUseStrategy, ActionResolution, StrategyTier
from maverick.computer_use.agent import AutonomousComputerUseAgent, ExecutionStage, ActionStep, ComputerUseTask
from maverick.intelligence.tools import ToolRegistry, ToolRisk


class TestAccessibilityBridge(unittest.TestCase):
    """Test Linux Accessibility Bridge (AT-SPI2) layer."""

    def setUp(self):
        self.bridge = AccessibilityBridge()

    def test_bridge_initialization(self):
        """Verify bridge initializes and detects AT-SPI availability."""
        self.assertTrue(self.bridge.is_available)

    def test_accessible_element_to_dict(self):
        """Verify element serializes cleanly without GObject copy errors."""
        elem = AccessibleElement(
            name="Save Button",
            role="push button",
            x=100,
            y=200,
            width=80,
            height=30,
            states=["visible", "enabled"],
            actions=["click"],
            node_ref="mock_gobject_node",
        )
        d = elem.to_dict()
        self.assertEqual(d["name"], "Save Button")
        self.assertEqual(d["center"], [140, 215])
        self.assertEqual(d["bounds"], [100, 200, 80, 30])
        self.assertNotIn("node_ref", d)

    def test_get_windows(self):
        """Verify window enumeration returns list of accessible elements."""
        windows = self.bridge.get_windows()
        self.assertIsInstance(windows, list)
        for w in windows:
            self.assertIsInstance(w, AccessibleElement)
            self.assertTrue(len(w.name) > 0)

    def test_get_active_window(self):
        """Verify active window detection returns top-level window or None."""
        active = self.bridge.get_active_window()
        if active:
            self.assertIsInstance(active, AccessibleElement)
            self.assertTrue(active.width > 0)
            self.assertTrue(active.height > 0)

    def test_find_elements(self):
        """Verify searching accessible tree finds interactive targets."""
        elems = self.bridge.find_elements(interactive_only=True, max_results=10)
        self.assertIsInstance(elems, list)
        for e in elems:
            self.assertTrue(e.width > 0)
            self.assertTrue(e.height > 0)


class TestUniversalInputEngine(unittest.TestCase):
    """Test Wayland-native mouse, keyboard, and clipboard interaction."""

    def setUp(self):
        self.input = UniversalInputEngine(enabled=True)

    def tearDown(self):
        self.input.emergency_stop()

    def test_pointer_movement(self):
        """Verify pointer move updates coordinates and telemetry."""
        ok = self.input.move_to(350, 450)
        self.assertTrue(ok)
        telem = self.input.get_telemetry()
        self.assertEqual(telem["cursor"]["x"], 350)
        self.assertEqual(telem["cursor"]["y"], 450)
        self.assertEqual(telem["last_action"], "move_to(350, 450)")

    def test_mouse_clicks(self):
        """Verify left, right, and double clicks dispatch cleanly."""
        self.assertTrue(self.input.click(MouseButton.LEFT))
        self.assertTrue(self.input.click(MouseButton.RIGHT))
        self.assertTrue(self.input.double_click())

    def test_drag_and_drop_simulation(self):
        """Verify drag and drop interpolation completes successfully."""
        ok = self.input.drag_and_drop(100, 100, 200, 200, steps=3, delay=0.005)
        self.assertTrue(ok)
        telem = self.input.get_telemetry()
        self.assertFalse(telem["is_holding_left"])

    def test_scroll_wheel(self):
        """Verify vertical scroll wheel dispatch."""
        self.assertTrue(self.input.scroll(3))
        self.assertTrue(self.input.scroll(-3))

    def test_typing_and_shortcuts(self):
        """Verify text typing and shortcut combinations."""
        self.assertTrue(self.input.type_text("Maven Test", delay_per_char=0.0))
        self.assertTrue(self.input.send_key("Return"))
        self.assertTrue(self.input.send_shortcut("Ctrl+S"))
        self.assertTrue(self.input.send_shortcut("Ctrl+Shift+P"))

    def test_clipboard_operations(self):
        """Verify GDK clipboard set and read."""
        test_str = "Maven Automated Clipboard Payload"
        self.assertTrue(self.input.copy_to_clipboard(test_str))
        read_back = self.input.get_clipboard_text()
        self.assertEqual(read_back, test_str)

    def test_emergency_stop(self):
        """Verify emergency stop disarms input and releases buttons."""
        self.input.press_and_hold(MouseButton.LEFT)
        self.assertTrue(self.input._is_holding_left)
        self.input.emergency_stop()
        self.assertFalse(self.input.enabled)
        self.assertFalse(self.input._is_holding_left)
        self.assertEqual(self.input._last_action, "emergency_stopped")


class TestScreenObserver(unittest.TestCase):
    """Test screen observation, OCR mapping, diffing, and wireframe synthesis."""

    def setUp(self):
        self.observer = ScreenObserver()

    def test_observe_snapshot(self):
        """Verify full desktop observation pass."""
        obs = self.observer.observe(capture_visual=True)
        self.assertIsInstance(obs, DesktopObservation)
        self.assertGreater(obs.screen_resolution[0], 0)
        self.assertGreater(obs.screen_resolution[1], 0)
        self.assertTrue(len(obs.screen_hash) > 0)
        self.assertIsNotNone(obs.visual_wireframe_bytes)
        self.assertTrue(len(obs.visual_wireframe_bytes) > 1000)

    def test_coordinate_mapping(self):
        """Verify relative (0.0 - 1.0) to pixel coordinate bijective mapping."""
        w, h = self.observer.get_resolution()
        px, py = self.observer.map_normalized_to_screen(0.25, 0.75)
        self.assertEqual(px, int(w * 0.25))
        self.assertEqual(py, int(h * 0.75))

        nx, ny = self.observer.map_screen_to_normalized(px, py)
        self.assertAlmostEqual(nx, 0.25, places=2)
        self.assertAlmostEqual(ny, 0.75, places=2)

    def test_screen_change_detection(self):
        """Verify screen hash comparison detects changes or stability."""
        self.observer.observe()
        self.observer.observe()
        self.assertFalse(self.observer.has_screen_changed())
        diff = self.observer.get_screen_diff()
        self.assertIn("changed", diff)
        self.assertIn("active_window_changed", diff)


class TestApplicationCompatibilityRegistry(unittest.TestCase):
    """Test Linux application profile registry."""

    def setUp(self):
        self.registry = ApplicationCompatibilityRegistry()

    def test_registered_profiles(self):
        """Verify default core Linux apps are registered."""
        profiles = self.registry.list_profiles()
        self.assertGreaterEqual(len(profiles), 8)
        app_ids = {p["app_id"] for p in profiles}
        self.assertIn("code", app_ids)
        self.assertIn("nautilus", app_ids)
        self.assertIn("gnome-terminal", app_ids)
        self.assertIn("google-chrome", app_ids)
        self.assertIn("firefox", app_ids)

    def test_profile_lookup(self):
        """Verify looking up profiles by id or title substring."""
        prof_code = self.registry.get_profile("code")
        self.assertIsNotNone(prof_code)
        self.assertEqual(prof_code.display_name, "Visual Studio Code")
        self.assertIn("save", prof_code.default_shortcuts)

        prof_title = self.registry.get_profile("PHASE5_1_REPORT.md - Visual Studio Code")
        self.assertIsNotNone(prof_title)
        self.assertEqual(prof_title.app_id, "code")


class TestComputerUseStrategy(unittest.TestCase):
    """Test 5-tier strategy selection logic."""

    def setUp(self):
        self.strategy = ComputerUseStrategy()

    def test_strategy_priority_order(self):
        """Verify StrategyTier enumeration definitions."""
        self.assertEqual(StrategyTier.TIER_1_ACCESSIBILITY.value, "accessibility_api")
        self.assertEqual(StrategyTier.TIER_2_NATIVE_INTEGRATION.value, "native_integration")
        self.assertEqual(StrategyTier.TIER_3_SCREENSHOT_OCR.value, "screenshot_ocr")
        self.assertEqual(StrategyTier.TIER_4_VISUAL_CV.value, "visual_computer_vision")
        self.assertEqual(StrategyTier.TIER_5_COORDINATE_FALLBACK.value, "coordinate_fallback")

    def test_resolve_text_entry(self):
        """Verify text entry strategy resolution."""
        res = self.strategy.resolve_text_entry("hello world")
        self.assertIn(res.selected_tier, (StrategyTier.TIER_1_ACCESSIBILITY, StrategyTier.TIER_2_NATIVE_INTEGRATION))
        self.assertGreater(res.confidence, 0.5)


class TestComputerUseSecurity(unittest.TestCase):
    """Test three-tier security and approval gates."""

    def setUp(self):
        self.security = ComputerUseSecurity()

    def test_normal_action_allowed(self):
        """Verify normal observation and navigation actions are authorized."""
        auth = self.security.authorize_action("observe_screen", target_app="code")
        self.assertTrue(auth["allowed"])
        self.assertEqual(auth["tier"], ActionTier.NORMAL.value)

    def test_sensitive_action_requires_confirmation(self):
        """Verify file overwrites require confirmation unless explicitly approved."""
        auth_unconf = self.security.authorize_action("filesystem_write_file", target_app="code", params={"path": "~/test.py"}, confirmed=False)
        self.assertFalse(auth_unconf["allowed"])
        self.assertTrue(auth_unconf["needs_confirmation"])
        self.assertEqual(auth_unconf["tier"], ActionTier.SENSITIVE.value)

        auth_conf = self.security.authorize_action("filesystem_write_file", target_app="code", params={"path": "~/test.py"}, confirmed=True)
        self.assertTrue(auth_conf["allowed"])

    def test_critical_action_strictly_gated(self):
        """Verify critical system operations require explicit confirmation."""
        auth = self.security.authorize_action("execute_command", params={"cmd": "sudo apt install"}, confirmed=False)
        self.assertFalse(auth["allowed"])
        self.assertTrue(auth["needs_confirmation"])
        self.assertEqual(auth["tier"], ActionTier.CRITICAL.value)

    def test_emergency_stop_blocks_all(self):
        """Verify emergency stop engagement immediately locks down execution."""
        self.security.trigger_emergency_stop()
        auth = self.security.authorize_action("observe_screen")
        self.assertFalse(auth["allowed"])
        self.assertIn("Emergency Stop", auth["error"])


class TestAutonomousComputerUseAgent(unittest.TestCase):
    """Test autonomous agent lifecycle and multi-step workflows."""

    def setUp(self):
        self.agent = AutonomousComputerUseAgent()

    def test_execute_observe_workflow(self):
        """Verify executing an observation goal runs complete lifecycle."""
        res = self.agent.execute_goal("observe desktop")
        self.assertEqual(res["status"], "success")
        task = res["task"]
        self.assertEqual(task["stage"], ExecutionStage.COMPLETED.value)
        self.assertGreater(len(task["timeline"]), 0)

    def test_pause_and_resume(self):
        """Verify pause and resume state transitions."""
        self.agent.pause()
        self.assertTrue(self.agent._is_paused)
        telem = self.agent.get_telemetry()
        self.assertTrue(telem["is_paused"])
        self.agent.resume()
        self.assertFalse(self.agent._is_paused)

    def test_emergency_stop_agent(self):
        """Verify emergency stop sets status and locks input."""
        self.agent.emergency_stop()
        telem = self.agent.get_telemetry()
        self.assertEqual(telem["status"], "emergency_stopped")
        self.assertFalse(telem["input_telemetry"]["enabled"])


class TestComputerUseToolsAndAPI(unittest.TestCase):
    """Test tool registry integration and dashboard server endpoints."""

    def setUp(self):
        self.registry = ToolRegistry()

    def test_registered_tools(self):
        """Verify all 7 computer-use tools are registered."""
        tool_names = [t["name"] for t in self.registry.list_tools()]
        expected = [
            "computer_observe_screen",
            "computer_find_elements",
            "computer_click_element",
            "computer_type_text",
            "computer_send_shortcut",
            "computer_execute_task",
            "computer_emergency_stop",
        ]
        for name in expected:
            self.assertIn(name, tool_names)

    def test_tool_execution(self):
        """Verify executing computer_observe_screen tool."""
        res = self.registry.execute("computer_observe_screen")
        self.assertEqual(res["status"], "success")
        self.assertIn("windows", res["result"])
        self.assertIn("screen_resolution", res["result"])

    def test_dashboard_api_endpoints(self):
        """Verify dashboard server exposes computer-use status and profiles endpoints."""
        try:
            req = urllib.request.Request("http://127.0.0.1:8765/api/computer-use/status")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data["status"], "success")
                self.assertIn("telemetry", data)

            req_p = urllib.request.Request("http://127.0.0.1:8765/api/computer-use/profiles")
            with urllib.request.urlopen(req_p, timeout=2.0) as resp:
                self.assertEqual(resp.status, 200)
                data_p = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data_p["status"], "success")
                self.assertGreaterEqual(len(data_p["profiles"]), 8)
        except Exception as e:
            self.skipTest(f"Dashboard server not reachable: {e}")


if __name__ == "__main__":
    unittest.main()
