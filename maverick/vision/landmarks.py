"""Maverick DevOS - Hand Landmark Topology & Data Structures.

Defines the standard 21-landmark kinematic hand model matching the MediaPipe topology,
distance metrics, finger extension heuristics, and palm geometry.
"""

from dataclasses import asdict, dataclass, field
from enum import IntEnum
import math
from typing import Any, Dict, List, Optional, Tuple


class LandmarkIndex(IntEnum):
    """Standard 21 MediaPipe Hand Landmark Indices."""
    WRIST = 0
    THUMB_CMC = 1
    THUMB_MCP = 2
    THUMB_IP = 3
    THUMB_TIP = 4
    INDEX_FINGER_MCP = 5
    INDEX_FINGER_PIP = 6
    INDEX_FINGER_DIP = 7
    INDEX_FINGER_TIP = 8
    MIDDLE_FINGER_MCP = 9
    MIDDLE_FINGER_PIP = 10
    MIDDLE_FINGER_DIP = 11
    MIDDLE_FINGER_TIP = 12
    RING_FINGER_MCP = 13
    RING_FINGER_PIP = 14
    RING_FINGER_DIP = 15
    RING_FINGER_TIP = 16
    PINKY_MCP = 17
    PINKY_PIP = 18
    PINKY_DIP = 19
    PINKY_TIP = 20


@dataclass
class Point3D:
    """Normalized 3D coordinate point [0.0, 1.0]."""
    x: float
    y: float
    z: float = 0.0

    def distance_to(self, other: "Point3D") -> float:
        """Euclidean distance in normalized 3D space."""
        return math.sqrt(
            (self.x - other.x) ** 2 +
            (self.y - other.y) ** 2 +
            (self.z - other.z) ** 2
        )

    def to_dict(self) -> Dict[str, float]:
        return {"x": round(self.x, 4), "y": round(self.y, 4), "z": round(self.z, 4)}


@dataclass
class FingerState:
    """Extension, curl, and position of an individual finger."""
    name: str
    is_extended: bool
    tip: Point3D
    mcp: Point3D
    curl_ratio: float = 0.0  # 0.0 = fully straight/extended, 1.0 = fully curled into palm


@dataclass
class HandLandmarks:
    """Complete 21-landmark kinematic observation for a single hand."""
    landmarks: List[Point3D]
    handedness: str = "Right"  # "Left" or "Right"
    confidence: float = 1.0

    # Finger states
    is_thumb_extended: bool = False
    is_index_extended: bool = False
    is_middle_extended: bool = False
    is_ring_extended: bool = False
    is_pinky_extended: bool = False

    # Palm metrics
    palm_center: Point3D = field(default_factory=lambda: Point3D(0.5, 0.5, 0.0))
    palm_scale: float = 0.1  # Normalization distance between wrist and middle MCP

    def __post_init__(self):
        if len(self.landmarks) == 21:
            self._compute_metrics()

    def _compute_metrics(self) -> None:
        """Calculate palm center, scale factor, and finger extension states."""
        wrist = self.landmarks[LandmarkIndex.WRIST]
        mid_mcp = self.landmarks[LandmarkIndex.MIDDLE_FINGER_MCP]
        index_mcp = self.landmarks[LandmarkIndex.INDEX_FINGER_MCP]
        pinky_mcp = self.landmarks[LandmarkIndex.PINKY_MCP]

        # Palm scale is distance from wrist to middle MCP
        self.palm_scale = max(0.01, wrist.distance_to(mid_mcp))

        # Palm center is centroid of wrist and MCPs
        cx = (wrist.x + mid_mcp.x + index_mcp.x + pinky_mcp.x) / 4.0
        cy = (wrist.y + mid_mcp.y + index_mcp.y + pinky_mcp.y) / 4.0
        cz = (wrist.z + mid_mcp.z + index_mcp.z + pinky_mcp.z) / 4.0
        self.palm_center = Point3D(cx, cy, cz)

        # Evaluate finger extensions relative to palm center & MCP joints
        # 1. Index finger
        idx_tip = self.landmarks[LandmarkIndex.INDEX_FINGER_TIP]
        idx_pip = self.landmarks[LandmarkIndex.INDEX_FINGER_PIP]
        self.is_index_extended = (
            idx_tip.distance_to(self.palm_center) > idx_pip.distance_to(self.palm_center) * 1.15
        )

        # 2. Middle finger
        mid_tip = self.landmarks[LandmarkIndex.MIDDLE_FINGER_TIP]
        mid_pip = self.landmarks[LandmarkIndex.MIDDLE_FINGER_PIP]
        self.is_middle_extended = (
            mid_tip.distance_to(self.palm_center) > mid_pip.distance_to(self.palm_center) * 1.15
        )

        # 3. Ring finger
        ring_tip = self.landmarks[LandmarkIndex.RING_FINGER_TIP]
        ring_pip = self.landmarks[LandmarkIndex.RING_FINGER_PIP]
        self.is_ring_extended = (
            ring_tip.distance_to(self.palm_center) > ring_pip.distance_to(self.palm_center) * 1.15
        )

        # 4. Pinky finger
        pinky_tip = self.landmarks[LandmarkIndex.PINKY_TIP]
        pinky_pip = self.landmarks[LandmarkIndex.PINKY_PIP]
        self.is_pinky_extended = (
            pinky_tip.distance_to(self.palm_center) > pinky_pip.distance_to(self.palm_center) * 1.15
        )

        # 5. Thumb
        thumb_tip = self.landmarks[LandmarkIndex.THUMB_TIP]
        thumb_ip = self.landmarks[LandmarkIndex.THUMB_IP]
        self.is_thumb_extended = (
            thumb_tip.distance_to(index_mcp) > thumb_ip.distance_to(index_mcp) * 1.1
        )

    def get_landmark(self, idx: LandmarkIndex) -> Point3D:
        return self.landmarks[int(idx)]

    def distance_between(self, idx1: LandmarkIndex, idx2: LandmarkIndex) -> float:
        """Euclidean distance between two landmarks normalized by palm scale."""
        d = self.landmarks[int(idx1)].distance_to(self.landmarks[int(idx2)])
        return d / self.palm_scale if self.palm_scale > 0 else d

    @property
    def extended_finger_count(self) -> int:
        return sum([
            self.is_thumb_extended,
            self.is_index_extended,
            self.is_middle_extended,
            self.is_ring_extended,
            self.is_pinky_extended,
        ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "handedness": self.handedness,
            "confidence": round(self.confidence, 3),
            "palm_center": self.palm_center.to_dict(),
            "palm_scale": round(self.palm_scale, 4),
            "extended_finger_count": self.extended_finger_count,
            "extended_fingers": {
                "thumb": self.is_thumb_extended,
                "index": self.is_index_extended,
                "middle": self.is_middle_extended,
                "ring": self.is_ring_extended,
                "pinky": self.is_pinky_extended,
            },
            "landmarks": [p.to_dict() for p in self.landmarks],
        }
