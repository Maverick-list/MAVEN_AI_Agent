"""Maverick DevOS - Real-Time Vision & Hand Gesture Coordination Engine.

Binds camera acquisition, landmark tracking, gesture classification, coordinate calibration,
and virtual mouse execution into an asynchronous 30 FPS pipeline.
"""

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from maverick.vision.calibration import CalibrationConfig, CoordinateCalibrator
from maverick.vision.camera import CameraManager
from maverick.vision.gesture_recognition import GestureRecognizer, GestureType
from maverick.vision.hand_tracker import HandTracker
from maverick.vision.landmarks import HandLandmarks, LandmarkIndex, Point3D
from maverick.vision.virtual_mouse import MouseButton, VirtualMouse


class GestureEngine:
    """
    Core runtime coordinating computer vision and virtual mouse interactions.
    """

    def __init__(
        self,
        camera: Optional[CameraManager] = None,
        tracker: Optional[HandTracker] = None,
        recognizer: Optional[GestureRecognizer] = None,
        calibrator: Optional[CoordinateCalibrator] = None,
        mouse: Optional[VirtualMouse] = None,
    ):
        self.camera = camera or CameraManager()
        self.tracker = tracker or HandTracker()
        self.recognizer = recognizer or GestureRecognizer()
        self.calibrator = calibrator or CoordinateCalibrator()
        self.mouse = mouse or VirtualMouse()

        self.enabled = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Telemetry snapshot
        self._last_gesture = GestureType.NONE
        self._last_confidence = 0.0
        self._last_hands: List[HandLandmarks] = []
        self._cursor_pos = (0, 0)
        self._fps_actual = 0.0
        self._fps_counter = 0
        self._last_fps_calc = time.time()
        self._emergency_stop_triggered = False
        self._pinch_hold_count = 0

    def start(self) -> bool:
        """Start vision processing pipeline."""
        with self._lock:
            if self.enabled:
                return True

            if not self.camera.start():
                return False

            self.enabled = True
            self.mouse.enabled = True
            self._emergency_stop_triggered = False
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="MavenVisionEngine")
            self._thread.start()
            return True

    def stop(self) -> None:
        """Stop vision pipeline and release resources cleanly."""
        with self._lock:
            self.enabled = False
            self.mouse.emergency_stop()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
            self._thread = None

        self.camera.stop()
        self.calibrator.reset()

    def _run_loop(self) -> None:
        """Frame processing loop (target ~25-30 FPS)."""
        while self.enabled:
            t_start = time.perf_counter()

            ok, frame, _ = self.camera.read_frame()
            if not ok or frame is None:
                time.sleep(0.02)
                continue

            # Process hand tracking
            hands = self.tracker.process_frame(frame)
            velocity = self.tracker.get_hand_velocity()
            gesture, conf, _ = self.recognizer.classify(hands, velocity)

            with self._lock:
                self._last_hands = hands
                self._last_gesture = gesture
                self._last_confidence = conf

            # Dispatch gesture to virtual mouse
            self._dispatch_gesture(gesture, hands, velocity)

            # Calculate FPS
            self._fps_counter += 1
            now = time.time()
            if now - self._last_fps_calc >= 1.0:
                self._fps_actual = round(self._fps_counter / (now - self._last_fps_calc), 1)
                self._fps_counter = 0
                self._last_fps_calc = now

            # Sleep to maintain bounded 30 FPS ceiling
            elapsed = time.perf_counter() - t_start
            sleep_time = max(0.005, (1.0 / 30.0) - elapsed)
            time.sleep(sleep_time)

    def _dispatch_gesture(
        self,
        gesture: GestureType,
        hands: List[HandLandmarks],
        velocity: Tuple[float, float],
    ) -> None:
        """Execute desktop actions based on classified gesture."""
        if not hands or not self.mouse.enabled:
            return

        primary = hands[0]

        # 1. Closed fist: EMERGENCY STOP
        if gesture == GestureType.CLOSED_FIST:
            self.mouse.emergency_stop()
            self._emergency_stop_triggered = True
            self._pinch_hold_count = 0
            return

        # 2. Open palm: release click-and-hold (drop)
        if gesture == GestureType.OPEN_PALM:
            self.mouse.release_hold(MouseButton.LEFT)
            self.mouse.release_hold(MouseButton.RIGHT)
            self._pinch_hold_count = 0
            return

        # 3. Cursor movement (Index finger pointing or pinching while moving)
        if gesture in (GestureType.INDEX_POINTING, GestureType.INDEX_PINCH, GestureType.TWO_FINGERS_POINTING):
            idx_tip = primary.get_landmark(LandmarkIndex.INDEX_FINGER_TIP)
            sx, sy = self.calibrator.map_to_screen(idx_tip.x, idx_tip.y)
            self._cursor_pos = (sx, sy)
            self.mouse.move_to(sx, sy)

        # 4. Discrete clicks & controlled Drag-and-Drop hold
        if gesture == GestureType.INDEX_PINCH:
            if self._pinch_hold_count == 0:
                self.mouse.click(MouseButton.LEFT)
            self._pinch_hold_count += 1
            if self._pinch_hold_count >= 4:
                # Sustained pinch: engage drag-and-drop hold
                self.mouse.press_and_hold(MouseButton.LEFT)

        elif gesture == GestureType.DOUBLE_PINCH:
            self._pinch_hold_count = 0
            self.mouse.double_click()

        elif gesture == GestureType.MIDDLE_PINCH:
            self._pinch_hold_count = 0
            self.mouse.click(MouseButton.RIGHT)

        # 5. Scroll mode (Two fingers pointing)
        elif gesture == GestureType.TWO_FINGERS_POINTING:
            self._pinch_hold_count = 0
            vy = velocity[1]
            if abs(vy) > 0.08:
                delta = int(round(-vy * 12))
                self.mouse.scroll(delta)

        elif gesture == GestureType.SWIPE_UP:
            self._pinch_hold_count = 0
            self.mouse.scroll(4)

        elif gesture == GestureType.SWIPE_DOWN:
            self._pinch_hold_count = 0
            self.mouse.scroll(-4)

        else:
            if gesture != GestureType.INDEX_POINTING:
                self._pinch_hold_count = 0

    def get_telemetry(self) -> Dict[str, Any]:
        """Telemetry snapshot for Control Center HUD."""
        with self._lock:
            hands_meta = [h.to_dict() for h in self._last_hands]
            return {
                "enabled": self.enabled,
                "fps": self._fps_actual,
                "gesture": self._last_gesture.value,
                "confidence": round(self._last_confidence, 2),
                "cursor": {"x": self._cursor_pos[0], "y": self._cursor_pos[1]},
                "hand_count": len(self._last_hands),
                "hands": hands_meta,
                "emergency_stop": self._emergency_stop_triggered,
                "tracking_provider": self.tracker.get_provider_name(),
                "camera": self.camera.get_status(),
                "mouse": self.mouse.get_state(),
            }
