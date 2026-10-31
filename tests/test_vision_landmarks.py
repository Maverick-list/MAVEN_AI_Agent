"""
Tests for Hand Landmarks, Kinematics, and Point Geometry.
"""

import unittest
from maverick.vision.landmarks import (
    Point3D,
    LandmarkIndex,
    HandLandmarks,
)


def create_mock_hand(wrist=(0.5, 0.8, 0.0)) -> HandLandmarks:
    """Generate a realistic mock 21-landmark open hand."""
    points = [Point3D(0.5, 0.8, 0.0) for _ in range(21)]
    points[LandmarkIndex.WRIST.value] = Point3D(wrist[0], wrist[1], wrist[2])

    # Index finger pointing straight up
    points[LandmarkIndex.INDEX_FINGER_MCP.value] = Point3D(0.45, 0.60, 0.0)
    points[LandmarkIndex.INDEX_FINGER_PIP.value] = Point3D(0.45, 0.50, 0.0)
    points[LandmarkIndex.INDEX_FINGER_DIP.value] = Point3D(0.45, 0.40, 0.0)
    points[LandmarkIndex.INDEX_FINGER_TIP.value] = Point3D(0.45, 0.25, 0.0)

    # Middle MCP for scale
    points[LandmarkIndex.MIDDLE_FINGER_MCP.value] = Point3D(0.50, 0.60, 0.0)
    points[LandmarkIndex.MIDDLE_FINGER_PIP.value] = Point3D(0.50, 0.50, 0.0)
    points[LandmarkIndex.MIDDLE_FINGER_DIP.value] = Point3D(0.50, 0.40, 0.0)
    points[LandmarkIndex.MIDDLE_FINGER_TIP.value] = Point3D(0.50, 0.25, 0.0)

    # Ring MCP
    points[LandmarkIndex.RING_FINGER_MCP.value] = Point3D(0.53, 0.60, 0.0)
    points[LandmarkIndex.RING_FINGER_PIP.value] = Point3D(0.53, 0.50, 0.0)
    points[LandmarkIndex.RING_FINGER_DIP.value] = Point3D(0.53, 0.40, 0.0)
    points[LandmarkIndex.RING_FINGER_TIP.value] = Point3D(0.53, 0.25, 0.0)

    # Pinky MCP
    points[LandmarkIndex.PINKY_MCP.value] = Point3D(0.55, 0.60, 0.0)
    points[LandmarkIndex.PINKY_PIP.value] = Point3D(0.55, 0.52, 0.0)
    points[LandmarkIndex.PINKY_DIP.value] = Point3D(0.55, 0.44, 0.0)
    points[LandmarkIndex.PINKY_TIP.value] = Point3D(0.55, 0.28, 0.0)

    # Thumb
    points[LandmarkIndex.THUMB_CMC.value] = Point3D(0.40, 0.75, 0.0)
    points[LandmarkIndex.THUMB_MCP.value] = Point3D(0.35, 0.70, 0.0)
    points[LandmarkIndex.THUMB_IP.value] = Point3D(0.30, 0.65, 0.0)
    points[LandmarkIndex.THUMB_TIP.value] = Point3D(0.20, 0.55, 0.0)

    return HandLandmarks(landmarks=points, handedness="Right", confidence=0.95)


class TestVisionLandmarks(unittest.TestCase):
    def test_point3d_representation(self):
        pt = Point3D(0.25, 0.75, -0.05)
        self.assertEqual(pt.x, 0.25)
        self.assertEqual(pt.y, 0.75)
        self.assertEqual(pt.z, -0.05)
        d = pt.to_dict()
        self.assertEqual(d["x"], 0.25)
        self.assertEqual(d["y"], 0.75)
        self.assertEqual(d["z"], -0.05)

    def test_landmark_indices(self):
        self.assertEqual(LandmarkIndex.WRIST.value, 0)
        self.assertEqual(LandmarkIndex.THUMB_TIP.value, 4)
        self.assertEqual(LandmarkIndex.INDEX_FINGER_TIP.value, 8)
        self.assertEqual(LandmarkIndex.MIDDLE_FINGER_TIP.value, 12)
        self.assertEqual(LandmarkIndex.RING_FINGER_TIP.value, 16)
        self.assertEqual(LandmarkIndex.PINKY_TIP.value, 20)

    def test_hand_landmarks_properties(self):
        hand = create_mock_hand()
        self.assertEqual(len(hand.landmarks), 21)
        self.assertEqual(hand.handedness, "Right")
        self.assertEqual(hand.confidence, 0.95)

        pc = hand.palm_center
        self.assertAlmostEqual(pc.x, 0.5, places=2)
        self.assertAlmostEqual(pc.y, 0.65, places=2)

        self.assertAlmostEqual(hand.palm_scale, 0.20, places=2)

    def test_distances(self):
        hand = create_mock_hand()
        norm_dist = hand.distance_between(LandmarkIndex.INDEX_FINGER_TIP, LandmarkIndex.MIDDLE_FINGER_TIP)
        self.assertAlmostEqual(norm_dist, 0.25, places=2)

    def test_finger_extension(self):
        hand = create_mock_hand()
        self.assertTrue(hand.is_index_extended)
        self.assertTrue(hand.is_middle_extended)
        self.assertTrue(hand.is_pinky_extended)
        self.assertTrue(hand.is_thumb_extended)
        self.assertGreaterEqual(hand.extended_finger_count, 4)

    def test_serialization(self):
        hand = create_mock_hand()
        d = hand.to_dict()
        self.assertEqual(d["handedness"], "Right")
        self.assertEqual(d["confidence"], 0.95)
        self.assertEqual(len(d["landmarks"]), 21)
        self.assertIn("palm_center", d)
        self.assertIn("palm_scale", d)
        self.assertIn("extended_fingers", d)

    def test_mediapipe_onnx_hand_provider_and_jpeg_rendering(self):
        import numpy as np
        from maverick.vision.hand_tracker import (
            HandTracker,
            MediaPipeONNXHandProvider,
            render_landmarks_jpeg,
        )

        provider = MediaPipeONNXHandProvider()
        self.assertTrue(provider.is_available)
        self.assertEqual(provider.get_name(), "mediapipe_onnx")

        # Test HandTracker default resolution selects MediaPipe ONNX
        tracker = HandTracker()
        self.assertEqual(tracker.get_provider_name(), "mediapipe_onnx")

        # Test blank frame fallback
        blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        hands = tracker.process_frame(blank_frame)
        self.assertIsInstance(hands, list)

        # Test JPEG rendering
        mock_hand = create_mock_hand()
        jpeg_bytes = render_landmarks_jpeg(blank_frame, [mock_hand], gesture_name="index_pointing", fps=30.0)
        self.assertTrue(len(jpeg_bytes) > 100)
        # Verify valid JPEG magic header (SOI: 0xFF 0xD8)
        self.assertEqual(jpeg_bytes[:2], b"\xff\xd8")


if __name__ == "__main__":
    unittest.main()
