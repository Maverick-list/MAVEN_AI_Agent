"""
Tests for Vision Dashboard REST Endpoints and Vision Tool Handlers.
"""

import unittest
from unittest.mock import MagicMock, patch

from maverick.dashboard.server import TelemetryHub
from maverick.intelligence.tools import ToolRegistry, ToolRisk
from maverick.vision.vision_controller import VisionMode


class TestVisionEndpoints(unittest.TestCase):
    def setUp(self):
        self.mock_tts = MagicMock()
        self.mock_tts.get_status.return_value = {"preferred_engine": "speech_dispatcher"}
        self.hub = TelemetryHub(tts=self.mock_tts)

    def test_hub_set_vision_mode(self):
        res = self.hub.set_vision_mode("gesture_control")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["current_mode"], "gesture_control")

        # Invalid mode
        res_err = self.hub.set_vision_mode("super_ai_mode")
        self.assertEqual(res_err["status"], "error")

    def test_hub_vision_emergency_stop(self):
        res = self.hub.vision_emergency_stop()
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["action"], "emergency_stop")

    def test_hub_calibrate_vision(self):
        res = self.hub.calibrate_vision({
            "sensitivity": 1.5,
            "acceleration_exponent": 1.4,
            "invert_x": False,
        })
        self.assertEqual(res["status"], "success")
        cal = res["calibration"]
        self.assertEqual(cal["sensitivity"], 1.5)
        self.assertEqual(cal["acceleration_exponent"], 1.4)
        self.assertFalse(cal["invert_x"])

    def test_vision_tool_move_cursor(self):
        registry = ToolRegistry()
        tool = registry.get_tool("desktop_move_cursor")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.risk, ToolRisk.READ_ONLY)

        with patch("maverick.vision.virtual_mouse.VirtualMouse.move_to", return_value=True):
            res = registry.execute("desktop_move_cursor", {"x": 500, "y": 300})
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["result"]["x"], 500)
            self.assertEqual(res["result"]["y"], 300)

    def test_vision_tool_scroll(self):
        registry = ToolRegistry()
        tool = registry.get_tool("desktop_scroll")
        self.assertIsNotNone(tool)

        with patch("maverick.vision.virtual_mouse.VirtualMouse.scroll", return_value=True):
            res = registry.execute("desktop_scroll", {"delta_lines": 5})
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["result"]["delta_lines"], 5)

    def test_vision_tool_emergency_stop(self):
        registry = ToolRegistry()
        tool = registry.get_tool("desktop_emergency_stop")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.risk, ToolRisk.CRITICAL)

        with patch("maverick.vision.virtual_mouse.VirtualMouse.emergency_stop") as mock_estop:
            res = registry.execute("desktop_emergency_stop", {}, confirmed=True)
            self.assertEqual(res["status"], "success")
            mock_estop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
