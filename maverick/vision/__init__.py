"""
Maverick DevOS - Vision Intelligence, Hand Tracking & Multimodal Interaction Package.
"""

from maverick.vision.calibration import CalibrationConfig, CoordinateCalibrator
from maverick.vision.camera import CameraManager
from maverick.vision.gesture_engine import GestureEngine
from maverick.vision.gesture_recognition import GestureRecognizer, GestureType
from maverick.vision.hand_tracker import (
    BaseHandTrackerProvider,
    HandTracker,
    MediaPipeProvider,
    OpenCVDNNProvider,
    OpenCVKinematicProvider,
)
from maverick.vision.landmarks import FingerState, HandLandmarks, LandmarkIndex, Point3D
from maverick.vision.mode_manager import (
    InteractionMode,
    InteractionModeManager,
    PhysicalInputMonitor,
)
from maverick.vision.screen import ScreenIntelligence, UIElement
from maverick.vision.virtual_input import MouseButton, VirtualKeyboard, VirtualMouse
from maverick.vision.vision_controller import VisionController, VisionMode

__all__ = [
    "BaseHandTrackerProvider",
    "CalibrationConfig",
    "CameraManager",
    "CoordinateCalibrator",
    "FingerState",
    "GestureEngine",
    "GestureRecognizer",
    "GestureType",
    "HandLandmarks",
    "HandTracker",
    "InteractionMode",
    "InteractionModeManager",
    "LandmarkIndex",
    "MediaPipeProvider",
    "MouseButton",
    "OpenCVDNNProvider",
    "OpenCVKinematicProvider",
    "PhysicalInputMonitor",
    "Point3D",
    "ScreenIntelligence",
    "UIElement",
    "VirtualKeyboard",
    "VirtualMouse",
    "VisionController",
    "VisionMode",
]
