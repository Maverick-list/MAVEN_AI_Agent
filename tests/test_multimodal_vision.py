"""
Tests for Multimodal Vision, Verbal Gesture Commands, and Screen Intelligence.
"""

import unittest
from unittest.mock import MagicMock
from maverick.vision.calibration import CalibrationConfig
from maverick.vision.gesture_engine import GestureEngine
from maverick.vision.screen import ScreenIntelligence, UIElement
from maverick.vision.virtual_mouse import MouseButton, VirtualMouse
from maverick.vision.vision_controller import VisionController, VisionMode


class TestMultimodalVision(unittest.TestCase):
    def setUp(self):
        self.mock_mouse = VirtualMouse(enabled=True)
        self.mock_mouse._atspi = MagicMock()
        self.mock_mouse._atspi.generate_mouse_event.return_value = True

        self.mock_engine = MagicMock(spec=GestureEngine)
        self.mock_engine.mouse = self.mock_mouse
        self.mock_engine.camera = MagicMock()
        self.mock_engine.camera.is_camera_available.return_value = True
        self.mock_engine.calibrator = MagicMock()
        self.mock_engine.calibrator.config = CalibrationConfig(screen_width=3840, screen_height=2400)
        self.mock_engine.enabled = False
        self.mock_engine.get_telemetry.return_value = {
            "enabled": False,
            "fps": 0.0,
            "gesture": "none",
            "confidence": 0.0,
            "cursor": {"x": 100, "y": 100},
            "emergency_stop": False,
        }

        self.mock_screen = MagicMock(spec=ScreenIntelligence)
        self.mock_screen.get_summary.return_value = {"active_window": "VS Code", "element_count": 12}

        self.vc = VisionController(
            gesture_engine=self.mock_engine,
            screen=self.mock_screen,
            initial_mode=VisionMode.PRIVACY_MODE,
        )

    def test_initial_mode_privacy(self):
        self.assertEqual(self.vc.mode, VisionMode.PRIVACY_MODE)
        st = self.vc.get_status()
        self.assertEqual(st["mode"], "privacy_mode")

    def test_mode_transitions(self):
        # 1. Switch to OBSERVE_ONLY
        res1 = self.vc.set_mode(VisionMode.OBSERVE_ONLY)
        self.assertEqual(res1["current_mode"], "observe_only")
        self.mock_engine.start.assert_called()
        self.assertFalse(self.mock_mouse.enabled)

        # 2. Switch to GESTURE_CONTROL
        res2 = self.vc.set_mode(VisionMode.GESTURE_CONTROL)
        self.assertEqual(res2["current_mode"], "gesture_control")
        self.assertTrue(self.mock_mouse.enabled)

        # 3. Switch to PRIVACY_MODE
        res3 = self.vc.set_mode(VisionMode.PRIVACY_MODE)
        self.assertEqual(res3["current_mode"], "privacy_mode")
        self.mock_engine.stop.assert_called()

    def test_privacy_mode_blocks_actuation(self):
        # By default in PRIVACY_MODE, clicking or scrolling should be blocked
        res = self.vc.handle_multimodal_command("click this")
        self.assertIsNotNone(res)
        self.assertEqual(res["status"], "blocked")
        self.assertEqual(res["action"], "permission_blocked")

    def test_verbal_emergency_stop(self):
        res_en = self.vc.handle_multimodal_command("emergency stop")
        self.assertIsNotNone(res_en)
        self.assertEqual(res_en["action"], "emergency_stop")
        self.assertFalse(self.mock_mouse.enabled)

        self.mock_mouse.enabled = True
        res_id = self.vc.handle_multimodal_command("berhenti")
        self.assertIsNotNone(res_id)
        self.assertEqual(res_id["action"], "emergency_stop")
        self.assertFalse(self.mock_mouse.enabled)

    def test_verbal_mode_switching(self):
        res = self.vc.handle_multimodal_command("enable vision")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "vision_mode_enabled")
        self.assertEqual(self.vc.mode, VisionMode.FULL_ASSISTANT)

        res_off = self.vc.handle_multimodal_command("matikan mode visi")
        self.assertIsNotNone(res_off)
        self.assertEqual(res_off["action"], "vision_mode_disabled")
        self.assertEqual(self.vc.mode, VisionMode.PRIVACY_MODE)

    def test_verbal_clicks(self):
        self.vc.set_mode(VisionMode.FULL_ASSISTANT)
        self.mock_mouse.enabled = True
        self.mock_mouse._current_x = 400
        self.mock_mouse._current_y = 600

        # Click this
        res = self.vc.handle_multimodal_command("click this")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "virtual_mouse_click")
        self.mock_mouse._atspi.generate_mouse_event.assert_called_with(400, 600, "b1c")

        # Double click
        res_dbl = self.vc.handle_multimodal_command("double click")
        self.assertIsNotNone(res_dbl)
        self.assertEqual(res_dbl["action"], "virtual_mouse_double_click")

        # Right click
        res_rt = self.vc.handle_multimodal_command("klik kanan")
        self.assertIsNotNone(res_rt)
        self.assertEqual(res_rt["action"], "virtual_mouse_right_click")

    def test_verbal_scroll(self):
        self.vc.set_mode(VisionMode.FULL_ASSISTANT)
        self.mock_mouse.enabled = True
        res_dn = self.vc.handle_multimodal_command("scroll down")
        self.assertIsNotNone(res_dn)
        self.assertEqual(res_dn["action"], "virtual_mouse_scroll")

        res_up = self.vc.handle_multimodal_command("scroll ke atas")
        self.assertIsNotNone(res_up)
        self.assertEqual(res_up["action"], "virtual_mouse_scroll")

    def test_verbal_semantic_target(self):
        self.vc.set_mode(VisionMode.FULL_ASSISTANT)
        self.mock_screen.find_target.return_value = UIElement(
            name="Search",
            role="push button",
            x=200,
            y=150,
            width=60,
            height=30,
        )

        res = self.vc.handle_multimodal_command("click the Search")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "click_ui_target")
        self.assertEqual(res["target"], "Search")
        self.assertEqual(res["coords"], {"x": 230, "y": 165})

    def test_verbal_cursor_positioning(self):
        self.vc.set_mode(VisionMode.FULL_ASSISTANT)
        res_ur = self.vc.handle_multimodal_command("move cursor to upper right")
        self.assertIsNotNone(res_ur)
        self.assertEqual(res_ur["action"], "cursor_move")

        res_ctr = self.vc.handle_multimodal_command("center cursor")
        self.assertIsNotNone(res_ctr)
        self.assertEqual(res_ctr["action"], "cursor_move")

    def test_unhandled_phrase_returns_none(self):
        self.vc.set_mode(VisionMode.FULL_ASSISTANT)
        res = self.vc.handle_multimodal_command("how is the weather in Tokyo?")
        self.assertIsNone(res)

    def test_gesture_engine_hand_lost_and_drag_release(self):
        from maverick.vision.gesture_engine import GestureEngine
        from maverick.vision.gesture_recognition import GestureType
        from tests.test_vision_landmarks import create_mock_hand

        mock_mouse = MagicMock()
        mock_mouse.enabled = True
        engine = GestureEngine(mouse=mock_mouse)

        hand = create_mock_hand()

        # 1. Sustained pinch triggers drag hold after 4 frames
        for _ in range(4):
            engine._dispatch_gesture(GestureType.INDEX_PINCH, [hand], velocity=(0.0, 0.0))
        mock_mouse.press_and_hold.assert_called_with(MouseButton.LEFT)

        # 2. Hand lost -> releases hold immediately
        engine._dispatch_gesture(GestureType.NONE, [], velocity=(0.0, 0.0))
        mock_mouse.release_hold.assert_any_call(MouseButton.LEFT)
        mock_mouse.release_hold.assert_any_call(MouseButton.RIGHT)

        # 3. Two fingers pointing stationary -> right click
        mock_mouse.reset_mock()
        engine._dispatch_gesture(GestureType.TWO_FINGERS_POINTING, [hand], velocity=(0.0, 0.02))
        mock_mouse.click.assert_called_with(MouseButton.RIGHT)

        # 4. Closed fist -> emergency stop
        mock_mouse.reset_mock()
        engine._dispatch_gesture(GestureType.CLOSED_FIST, [hand], velocity=(0.0, 0.0))
        mock_mouse.emergency_stop.assert_called_once()
        self.assertTrue(engine._emergency_stop_triggered)

        # 5. Open palm -> resumes and releases holds
        mock_mouse.reset_mock()
        engine._dispatch_gesture(GestureType.OPEN_PALM, [hand], velocity=(0.0, 0.0))
        self.assertFalse(engine._emergency_stop_triggered)
        mock_mouse.release_hold.assert_any_call(MouseButton.LEFT)


if __name__ == "__main__":
    unittest.main()
