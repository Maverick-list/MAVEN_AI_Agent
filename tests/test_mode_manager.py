"""
Tests for InteractionModeManager, PhysicalInputMonitor, and Dual-Mode Interaction.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from maverick.vision.mode_manager import (
    InteractionMode,
    InteractionModeManager,
    PhysicalInputMonitor,
)


class TestInteractionModeManager(unittest.TestCase):
    def setUp(self):
        self.mock_camera = MagicMock()
        self.mock_camera.start.return_value = True
        self.mock_camera.stop.return_value = None
        self.mock_camera.read_frame.return_value = MagicMock()

        self.mock_engine = MagicMock()
        self.mock_engine.start.return_value = None
        self.mock_engine.stop.return_value = None
        self.mock_engine.emergency_stop.return_value = None

        self.mock_mouse = MagicMock()
        self.mock_mouse.enabled = False
        self.mock_mouse.set_enabled.return_value = None
        self.mock_mouse.emergency_stop.return_value = None

        self.mock_keyboard = MagicMock()
        self.mock_keyboard.enabled = False
        self.mock_keyboard.set_enabled.return_value = None

        self.manager = InteractionModeManager(
            camera=self.mock_camera,
            gesture_engine=self.mock_engine,
            virtual_mouse=self.mock_mouse,
            virtual_keyboard=self.mock_keyboard,
            physical_priority_window_s=0.2,
        )

    def tearDown(self):
        self.manager.shutdown()

    def test_default_mode_is_normal(self):
        """Mode A (NORMAL) must strictly be the default state on boot and initialization."""
        self.assertEqual(self.manager.current_mode, InteractionMode.NORMAL)
        self.assertFalse(self.manager.is_vision_active())
        self.mock_camera.start.assert_not_called()
        self.mock_engine.start.assert_not_called()

    def test_activate_vision(self):
        """Explicit activation transitions to VISION_ACTIVE, starts camera, and arms virtual input."""
        res = self.manager.activate_vision()
        self.assertTrue(res.get("ok"))
        self.assertEqual(self.manager.current_mode, InteractionMode.VISION_ACTIVE)
        self.assertTrue(self.manager.is_vision_active())
        self.mock_camera.start.assert_called_once()
        self.mock_engine.start.assert_called_once()
        self.mock_mouse.set_enabled.assert_called_with(True)

    def test_deactivate_vision(self):
        """Deactivating vision returns to NORMAL, stops camera, and disarms virtual input."""
        self.manager.activate_vision()
        res = self.manager.deactivate_vision()
        self.assertTrue(res.get("ok"))
        self.assertEqual(self.manager.current_mode, InteractionMode.NORMAL)
        self.assertFalse(self.manager.is_vision_active())
        self.mock_camera.stop.assert_called_once()
        self.mock_engine.stop.assert_called_once()
        self.mock_mouse.set_enabled.assert_called_with(False)

    def test_toggle_mode(self):
        """Toggle alternates cleanly between NORMAL and VISION_ACTIVE."""
        self.assertEqual(self.manager.current_mode, InteractionMode.NORMAL)
        res1 = self.manager.toggle_mode()
        self.assertEqual(self.manager.current_mode, InteractionMode.VISION_ACTIVE)
        res2 = self.manager.toggle_mode()
        self.assertEqual(self.manager.current_mode, InteractionMode.NORMAL)

    def test_camera_failure_safe_fallback_to_normal(self):
        """If camera fails to start or read frame, system safely reverts to NORMAL."""
        self.mock_camera.start.return_value = False
        res = self.manager.activate_vision()
        self.assertFalse(res.get("ok"))
        self.assertEqual(self.manager.current_mode, InteractionMode.NORMAL)

    def test_pause_vision_auto_resumes_after_priority_window(self):
        """Physical input pauses virtual mouse and auto-resumes after priority duration."""
        self.manager.activate_vision()
        self.assertTrue(self.manager.is_vision_active())

        # Trigger pause
        self.manager.pause_vision()
        self.assertEqual(self.manager.current_mode, InteractionMode.VISION_PAUSED)
        self.assertFalse(self.manager.is_vision_active())

        # Wait for auto-resume timeout (priority_window is 0.2s)
        time.sleep(0.35)
        self.assertEqual(self.manager.current_mode, InteractionMode.VISION_ACTIVE)
        self.assertTrue(self.manager.is_vision_active())

    def test_emergency_stop(self):
        """Emergency stop halts engine, mouse, and locks state."""
        self.manager.activate_vision()
        res = self.manager.emergency_stop()
        self.assertTrue(res.get("ok"))
        self.assertEqual(self.manager.current_mode, InteractionMode.EMERGENCY_STOPPED)
        self.mock_mouse.emergency_stop.assert_called_once()
        self.mock_engine.emergency_stop.assert_called_once()


class TestPhysicalInputMonitor(unittest.TestCase):
    def test_monitor_initialization(self):
        with patch("maverick.vision.mode_manager.HAS_ATSPI", True):
            monitor = PhysicalInputMonitor()
            self.assertFalse(monitor.is_physical_active())
            monitor.record_activity()
            self.assertTrue(monitor.is_physical_active(window_s=1.0))
            monitor.stop()
