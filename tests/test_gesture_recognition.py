"""
Tests for Gesture Recognition, Classification, and Temporal Cooldowns.
"""

import time
import unittest
from maverick.vision.landmarks import (
    Point3D,
    LandmarkIndex,
    HandLandmarks,
)
from maverick.vision.gesture_recognition import (
    GestureRecognizer,
    GestureType,
)


def make_hand(
    thumb_ext=True,
    index_ext=True,
    middle_ext=False,
    ring_ext=False,
    pinky_ext=False,
    thumb_tip=(0.20, 0.55),
    idx_tip=(0.45, 0.25),
    mid_tip=(0.50, 0.65),
    palm_scale=0.20,
) -> HandLandmarks:
    """Helper to synthesize a hand with specific extension states and tips."""
    pts = [Point3D(0.5, 0.8, 0.0) for _ in range(21)]
    # Set wrist and MCPs
    pts[LandmarkIndex.WRIST.value] = Point3D(0.5, 0.8, 0.0)
    pts[LandmarkIndex.INDEX_FINGER_MCP.value] = Point3D(0.45, 0.60, 0.0)
    pts[LandmarkIndex.MIDDLE_FINGER_MCP.value] = Point3D(0.50, 0.60, 0.0)
    pts[LandmarkIndex.PINKY_MCP.value] = Point3D(0.55, 0.60, 0.0)

    # Set tips
    pts[LandmarkIndex.THUMB_TIP.value] = Point3D(thumb_tip[0], thumb_tip[1], 0.0)
    pts[LandmarkIndex.INDEX_FINGER_TIP.value] = Point3D(idx_tip[0], idx_tip[1], 0.0)
    pts[LandmarkIndex.MIDDLE_FINGER_TIP.value] = Point3D(mid_tip[0], mid_tip[1], 0.0)

    hand = HandLandmarks(landmarks=pts, handedness="Right", confidence=0.98)
    hand.palm_scale = palm_scale
    hand.is_thumb_extended = thumb_ext
    hand.is_index_extended = index_ext
    hand.is_middle_extended = middle_ext
    hand.is_ring_extended = ring_ext
    hand.is_pinky_extended = pinky_ext
    return hand


class TestGestureRecognition(unittest.TestCase):
    def setUp(self):
        self.recognizer = GestureRecognizer()

    def test_no_hands(self):
        g, conf, meta = self.recognizer.classify([])
        self.assertEqual(g, GestureType.NONE)
        self.assertEqual(conf, 0.0)

    def test_closed_fist_emergency_stop(self):
        fist = make_hand(
            thumb_ext=False,
            index_ext=False,
            middle_ext=False,
            ring_ext=False,
            pinky_ext=False,
        )
        g, conf, meta = self.recognizer.classify([fist])
        self.assertEqual(g, GestureType.CLOSED_FIST)
        self.assertEqual(conf, 1.0)

    def test_open_palm(self):
        palm = make_hand(
            thumb_ext=True,
            index_ext=True,
            middle_ext=True,
            ring_ext=True,
            pinky_ext=True,
            mid_tip=(0.50, 0.25),
        )
        g, conf, meta = self.recognizer.classify([palm])
        self.assertEqual(g, GestureType.OPEN_PALM)
        self.assertGreaterEqual(conf, 0.85)

    def test_index_pointing(self):
        pointing = make_hand(
            thumb_ext=False,
            index_ext=True,
            middle_ext=False,
            ring_ext=False,
            pinky_ext=False,
        )
        g, conf, meta = self.recognizer.classify([pointing])
        self.assertEqual(g, GestureType.INDEX_POINTING)
        self.assertGreaterEqual(conf, 0.90)

    def test_two_fingers_pointing(self):
        two_pt = make_hand(
            thumb_ext=False,
            index_ext=True,
            middle_ext=True,
            ring_ext=False,
            pinky_ext=False,
            mid_tip=(0.50, 0.25),
        )
        g, conf, meta = self.recognizer.classify([two_pt])
        self.assertEqual(g, GestureType.TWO_FINGERS_POINTING)
        self.assertGreaterEqual(conf, 0.90)

    def test_index_pinch(self):
        # Thumb tip and index tip close together (< pinch_threshold * palm_scale = 0.55 * 0.2 = 0.11)
        pinch = make_hand(
            thumb_ext=True,
            index_ext=True,
            thumb_tip=(0.45, 0.30),
            idx_tip=(0.45, 0.32),
        )
        g, conf, meta = self.recognizer.classify([pinch])
        self.assertEqual(g, GestureType.INDEX_PINCH)
        self.assertGreaterEqual(conf, 0.90)

    def test_swipe_detection(self):
        hand = make_hand(thumb_ext=True, index_ext=True)
        # Fast positive x velocity -> swipe right
        g, conf, meta = self.recognizer.classify([hand], velocity=(1.2, 0.1))
        self.assertEqual(g, GestureType.SWIPE_RIGHT)

        # Fast negative y velocity -> swipe up
        # Wait tiny bit to pass cooldown
        time.sleep(0.01)
        rec2 = GestureRecognizer()
        g_up, conf_up, _ = rec2.classify([hand], velocity=(0.0, -1.5))
        self.assertEqual(g_up, GestureType.SWIPE_UP)

    def test_two_hand_expansion_contraction(self):
        h1 = make_hand(thumb_tip=(0.3, 0.5))
        h1.palm_center = Point3D(0.3, 0.5, 0.0)

        h2 = make_hand(thumb_tip=(0.5, 0.5))
        h2.palm_center = Point3D(0.5, 0.5, 0.0)

        # First frame initializes distance
        g1, _, _ = self.recognizer.classify([h1, h2])
        self.assertNotEqual(g1, GestureType.TWO_HAND_EXPANSION)

        # Move hands apart -> Expansion
        h2.palm_center = Point3D(0.7, 0.5, 0.0)
        g2, conf2, _ = self.recognizer.classify([h1, h2])
        self.assertEqual(g2, GestureType.TWO_HAND_EXPANSION)

        # Move hands together -> Contraction
        h2.palm_center = Point3D(0.4, 0.5, 0.0)
        time.sleep(0.36)  # Exceed cooldown
        g3, conf3, _ = self.recognizer.classify([h1, h2])
        self.assertEqual(g3, GestureType.TWO_HAND_CONTRACTION)


if __name__ == "__main__":
    unittest.main()
