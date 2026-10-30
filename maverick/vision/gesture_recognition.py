"""Maverick DevOS - Hand Gesture Recognition Engine.

Classifies 13 deliberate hand gestures using 21-landmark kinematic geometries,
inter-finger Euclidean distances, velocity vectors, debouncing, and gesture cooldowns.
"""

from collections import deque
from enum import Enum
import math
import time
from typing import Any, Dict, List, Optional, Tuple

from maverick.vision.landmarks import HandLandmarks, LandmarkIndex, Point3D


class GestureType(Enum):
    """Recognized discrete and continuous hand gestures."""
    NONE = "none"
    INDEX_POINTING = "index_pointing"          # Move cursor
    INDEX_PINCH = "index_pinch"                # Left click
    DOUBLE_PINCH = "double_pinch"              # Double click
    MIDDLE_PINCH = "middle_pinch"              # Right click
    OPEN_PALM = "open_palm"                    # Release / Pause
    CLOSED_FIST = "closed_fist"                # Emergency Stop
    TWO_FINGERS_POINTING = "two_fingers"       # Scroll mode
    SWIPE_LEFT = "swipe_left"                  # Back
    SWIPE_RIGHT = "swipe_right"                # Forward
    SWIPE_UP = "swipe_up"                      # Scroll up
    SWIPE_DOWN = "swipe_down"                  # Scroll down
    TWO_HAND_EXPANSION = "two_hand_expansion"  # Zoom in
    TWO_HAND_CONTRACTION = "two_hand_contract" # Zoom out


class GestureRecognizer:
    """
    Robust gesture classification engine with temporal debouncing and cooldown gating.
    """

    def __init__(
        self,
        pinch_threshold: float = 0.55,       # Normalized by palm scale
        cooldown_sec: float = 0.30,
        click_cooldown_sec: float = 0.25,
        double_pinch_window_sec: float = 0.40,
        swipe_velocity_threshold: float = 0.85, # Normalized units per second
    ):
        self.pinch_threshold = pinch_threshold
        self.cooldown_sec = cooldown_sec
        self.click_cooldown_sec = click_cooldown_sec
        self.double_pinch_window_sec = double_pinch_window_sec
        self.swipe_velocity_threshold = swipe_velocity_threshold

        # Cooldown state tracking
        self._last_gesture_time: Dict[GestureType, float] = {}
        self._last_pinch_time: float = 0.0
        self._pinch_count: int = 0
        self._last_two_hand_dist: Optional[float] = None

        # Stability history: queue of recent classified gestures
        self._history = deque(maxlen=6)

    def classify(
        self,
        hands: List[HandLandmarks],
        velocity: Tuple[float, float] = (0.0, 0.0),
    ) -> Tuple[GestureType, float, Dict[str, Any]]:
        """
        Classify active gesture from observed hands and motion vector.
        Returns: (gesture_type, confidence, metadata)
        """
        now = time.perf_counter()

        if not hands:
            return GestureType.NONE, 0.0, {}

        # 1. Two-hand gestures (Expansion / Contraction)
        if len(hands) >= 2:
            g_two, conf_two = self._classify_two_hand_gestures(hands[0], hands[1], now)
            if g_two != GestureType.NONE:
                return g_two, conf_two, {"hand_count": 2}

        # 2. Single hand analysis on primary hand
        primary = hands[0]
        meta = {
            "extended_fingers": primary.extended_finger_count,
            "palm_scale": round(primary.palm_scale, 3),
            "handedness": primary.handedness,
        }

        # High priority: Closed fist (EMERGENCY STOP)
        if self._is_closed_fist(primary):
            return GestureType.CLOSED_FIST, 1.0, meta

        # Swipe gestures (Velocity based)
        vx, vy = velocity
        if abs(vx) > self.swipe_velocity_threshold or abs(vy) > self.swipe_velocity_threshold:
            swipe_g = self._classify_swipe(vx, vy, now)
            if swipe_g != GestureType.NONE:
                return swipe_g, 0.90, {"velocity_x": vx, "velocity_y": vy}

        # Pinch analysis (Index Pinch vs Middle Pinch)
        thumb_idx_dist = primary.distance_between(LandmarkIndex.THUMB_TIP, LandmarkIndex.INDEX_FINGER_TIP)
        thumb_mid_dist = primary.distance_between(LandmarkIndex.THUMB_TIP, LandmarkIndex.MIDDLE_FINGER_TIP)
        meta["thumb_idx_dist"] = round(thumb_idx_dist, 3)
        meta["thumb_mid_dist"] = round(thumb_mid_dist, 3)

        # Right-click: Thumb + Middle finger pinch
        if thumb_mid_dist < self.pinch_threshold and not primary.is_middle_extended:
            if self._check_cooldown(GestureType.MIDDLE_PINCH, now, self.click_cooldown_sec):
                return GestureType.MIDDLE_PINCH, 0.95, meta

        # Left-click / Double click: Thumb + Index finger pinch
        if thumb_idx_dist < self.pinch_threshold:
            dt = now - self._last_pinch_time
            if dt < self.double_pinch_window_sec and dt > 0.08:
                # Double click detected
                self._last_pinch_time = 0.0
                if self._check_cooldown(GestureType.DOUBLE_PINCH, now, 0.40):
                    return GestureType.DOUBLE_PINCH, 0.95, meta
            else:
                self._last_pinch_time = now
                if self._check_cooldown(GestureType.INDEX_PINCH, now, self.click_cooldown_sec):
                    return GestureType.INDEX_PINCH, 0.92, meta

        # Open palm: All fingers extended
        if (
            primary.is_thumb_extended and
            primary.is_index_extended and
            primary.is_middle_extended and
            primary.is_ring_extended and
            primary.is_pinky_extended
        ):
            return GestureType.OPEN_PALM, 0.90, meta

        # Two fingers pointing: Index and middle extended, ring & pinky folded
        if (
            primary.is_index_extended and
            primary.is_middle_extended and
            not primary.is_ring_extended and
            not primary.is_pinky_extended
        ):
            return GestureType.TWO_FINGERS_POINTING, 0.92, meta

        # Index finger pointing: Index extended, middle, ring, pinky folded
        if (
            primary.is_index_extended and
            not primary.is_middle_extended and
            not primary.is_ring_extended and
            not primary.is_pinky_extended
        ):
            return GestureType.INDEX_POINTING, 0.94, meta

        return GestureType.NONE, 0.0, meta

    def _is_closed_fist(self, hand: HandLandmarks) -> bool:
        """Verify all fingers are curled tightly into palm."""
        return (
            not hand.is_index_extended and
            not hand.is_middle_extended and
            not hand.is_ring_extended and
            not hand.is_pinky_extended and
            hand.extended_finger_count <= 1
        )

    def _classify_swipe(self, vx: float, vy: float, now: float) -> GestureType:
        """Classify directional swipe gesture with cooldown."""
        if abs(vx) > abs(vy):
            g = GestureType.SWIPE_RIGHT if vx > 0 else GestureType.SWIPE_LEFT
        else:
            g = GestureType.SWIPE_DOWN if vy > 0 else GestureType.SWIPE_UP

        if self._check_cooldown(g, now, 0.50):
            return g
        return GestureType.NONE

    def _classify_two_hand_gestures(
        self,
        hand1: HandLandmarks,
        hand2: HandLandmarks,
        now: float,
    ) -> Tuple[GestureType, float]:
        """Detect two-hand zoom in/out (expansion/contraction)."""
        dist = hand1.palm_center.distance_to(hand2.palm_center)
        if self._last_two_hand_dist is None:
            self._last_two_hand_dist = dist
            return GestureType.NONE, 0.0

        delta = dist - self._last_two_hand_dist
        self._last_two_hand_dist = dist

        if delta > 0.08:
            if self._check_cooldown(GestureType.TWO_HAND_EXPANSION, now, 0.35):
                return GestureType.TWO_HAND_EXPANSION, 0.88
        elif delta < -0.08:
            if self._check_cooldown(GestureType.TWO_HAND_CONTRACTION, now, 0.35):
                return GestureType.TWO_HAND_CONTRACTION, 0.88

        return GestureType.NONE, 0.0

    def _check_cooldown(self, gesture: GestureType, now: float, cooldown: float) -> bool:
        last = self._last_gesture_time.get(gesture, 0.0)
        if now - last >= cooldown:
            self._last_gesture_time[gesture] = now
            return True
        return False
