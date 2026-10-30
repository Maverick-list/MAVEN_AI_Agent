"""Maverick DevOS - Coordinate Space Calibration & Cursor Acceleration.

Maps normalized camera coordinate space ([0.0, 1.0]) into desktop screen pixels ([0, W] x [0, H]).
Provides active workspace bounding box, nonlinear acceleration, tremor dead-zones, and persistence.
"""

from dataclasses import asdict, dataclass
import json
import math
import os
from typing import Any, Dict, Optional, Tuple


@dataclass
class CalibrationConfig:
    """Configurable visual-to-screen coordinate mapping parameters."""
    screen_width: int = 3840
    screen_height: int = 2400
    # Active camera box bounds (avoids having to move hand to camera edge)
    box_x_min: float = 0.20
    box_x_max: float = 0.80
    box_y_min: float = 0.18
    box_y_max: float = 0.82
    # Movement physics
    dead_zone_radius: float = 0.006  # Ignore micro-tremors below this normalized distance
    acceleration_exponent: float = 1.35  # Nonlinear cursor acceleration
    sensitivity: float = 1.25  # Overall speed multiplier
    invert_x: bool = True  # Mirror camera feed so moving right moves cursor right
    invert_y: bool = False


class CoordinateCalibrator:
    """
    Translates raw normalized hand/index landmarks into desktop pixel coordinates.
    """

    def __init__(self, config: Optional[CalibrationConfig] = None):
        self.config = config or CalibrationConfig()
        self._prev_screen_x: Optional[float] = None
        self._prev_screen_y: Optional[float] = None
        self._prev_norm_x: Optional[float] = None
        self._prev_norm_y: Optional[float] = None

    def map_to_screen(self, norm_x: float, norm_y: float) -> Tuple[int, int]:
        """
        Convert normalized camera coordinate (0.0 to 1.0) to screen pixel coordinate (X, Y).
        Applies bounding box clipping, dead zone, inversion, and acceleration.
        """
        cfg = self.config

        # 1. Tremor Dead-zone filter
        if self._prev_norm_x is not None and self._prev_norm_y is not None:
            dist = math.hypot(norm_x - self._prev_norm_x, norm_y - self._prev_norm_y)
            if dist < cfg.dead_zone_radius:
                return int(self._prev_screen_x or 0), int(self._prev_screen_y or 0)

        self._prev_norm_x = norm_x
        self._prev_norm_y = norm_y

        # 2. Map within active box
        box_w = max(0.1, cfg.box_x_max - cfg.box_x_min)
        box_h = max(0.1, cfg.box_y_max - cfg.box_y_min)

        rel_x = (norm_x - cfg.box_x_min) / box_w
        rel_y = (norm_y - cfg.box_y_min) / box_h

        # Invert horizontal axis for natural mirror effect
        if cfg.invert_x:
            rel_x = 1.0 - rel_x
        if cfg.invert_y:
            rel_y = 1.0 - rel_y

        # Clamp to [0.0, 1.0]
        clamped_x = max(0.0, min(1.0, rel_x))
        clamped_y = max(0.0, min(1.0, rel_y))

        # 3. Apply center-relative acceleration curve
        dx = clamped_x - 0.5
        dy = clamped_y - 0.5
        r = math.hypot(dx, dy)

        if r > 0.001:
            accel_r = math.pow(r * 2.0, cfg.acceleration_exponent) / 2.0 * cfg.sensitivity
            scale = accel_r / r
            final_rel_x = max(0.0, min(1.0, 0.5 + dx * scale))
            final_rel_y = max(0.0, min(1.0, 0.5 + dy * scale))
        else:
            final_rel_x = 0.5
            final_rel_y = 0.5

        screen_x = int(final_rel_x * cfg.screen_width)
        screen_y = int(final_rel_y * cfg.screen_height)

        self._prev_screen_x = float(screen_x)
        self._prev_screen_y = float(screen_y)

        return screen_x, screen_y

    def reset(self) -> None:
        """Reset historical positions (e.g. after gesture release or camera drop)."""
        self._prev_screen_x = None
        self._prev_screen_y = None
        self._prev_norm_x = None
        self._prev_norm_y = None

    def update_resolution(self, width: int, height: int) -> None:
        self.config.screen_width = width
        self.config.screen_height = height

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self.config)
