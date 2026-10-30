"""
Tests for Coordinate Space Calibration and Virtual Mouse Controller.
"""

import unittest
from unittest.mock import MagicMock
from maverick.vision.calibration import (
    CalibrationConfig,
    CoordinateCalibrator,
)
from maverick.vision.virtual_mouse import (
    MouseButton,
    VirtualMouse,
)


class TestCalibrationAndMouse(unittest.TestCase):
    def test_calibration_defaults(self):
        cfg = CalibrationConfig()
        self.assertEqual(cfg.screen_width, 3840)
        self.assertEqual(cfg.screen_height, 2400)
        self.assertTrue(cfg.invert_x)
        self.assertEqual(cfg.box_x_min, 0.20)
        self.assertEqual(cfg.box_x_max, 0.80)

    def test_map_center_to_screen_center(self):
        cal = CoordinateCalibrator(CalibrationConfig(screen_width=1920, screen_height=1080))
        # Center of camera active box: x = (0.2 + 0.8)/2 = 0.5, y = (0.18 + 0.82)/2 = 0.5
        sx, sy = cal.map_to_screen(0.5, 0.5)
        self.assertEqual(sx, 960)
        self.assertEqual(sy, 540)

    def test_dead_zone_tremor_suppression(self):
        cal = CoordinateCalibrator(CalibrationConfig(dead_zone_radius=0.01))
        # First point
        x1, y1 = cal.map_to_screen(0.5, 0.5)

        # Micro perturbation smaller than dead_zone_radius (0.003 < 0.01)
        x2, y2 = cal.map_to_screen(0.502, 0.501)
        self.assertEqual(x1, x2)
        self.assertEqual(y1, y2)

        # Large motion exceeding dead_zone_radius
        x3, y3 = cal.map_to_screen(0.60, 0.60)
        self.assertNotEqual(x1, x3)
        self.assertNotEqual(y1, y3)

    def test_invert_x_mirror_behavior(self):
        cal = CoordinateCalibrator(CalibrationConfig(screen_width=1000, invert_x=True, box_x_min=0.0, box_x_max=1.0))
        # Invert_x=True: camera left (x=0.0) -> mapped to screen right (x=1000)
        sx, _ = cal.map_to_screen(0.0, 0.5)
        self.assertEqual(sx, 1000)

        # camera right (x=1.0) -> mapped to screen left (x=0)
        sx_r, _ = cal.map_to_screen(1.0, 0.5)
        self.assertEqual(sx_r, 0)

    def test_virtual_mouse_state_and_disable(self):
        mouse = VirtualMouse(enabled=True)
        # Mock AT-SPI to test pure logic without sending OS input events
        mouse._atspi = MagicMock()
        mouse._atspi.generate_mouse_event.return_value = True

        self.assertTrue(mouse.enabled)
        ok = mouse.move_to(500, 300)
        self.assertTrue(ok)
        self.assertEqual(mouse._current_x, 500)
        self.assertEqual(mouse._current_y, 300)

        # Test click
        self.assertTrue(mouse.click(MouseButton.LEFT))
        mouse._atspi.generate_mouse_event.assert_called_with(500, 300, "b1c")

        # Test hold and release
        self.assertTrue(mouse.press_and_hold(MouseButton.LEFT))
        self.assertTrue(mouse._is_holding_left)
        self.assertTrue(mouse.release_hold(MouseButton.LEFT))
        self.assertFalse(mouse._is_holding_left)

        # Test scroll
        self.assertTrue(mouse.scroll(3))

        # Test emergency stop
        mouse.press_and_hold(MouseButton.LEFT)
        mouse.emergency_stop()
        self.assertFalse(mouse.enabled)
        self.assertFalse(mouse._is_holding_left)

        # Actions fail when disabled
        self.assertFalse(mouse.move_to(100, 100))
        self.assertFalse(mouse.click())
        self.assertFalse(mouse.scroll(2))

    def test_mouse_telemetry_state(self):
        mouse = VirtualMouse()
        st = mouse.get_state()
        self.assertIn("enabled", st)
        self.assertIn("cursor", st)
        self.assertIn("is_holding_left", st)
        self.assertIn("backend", st)


if __name__ == "__main__":
    unittest.main()
