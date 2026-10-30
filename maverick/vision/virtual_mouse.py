"""Maverick DevOS - Virtual Mouse Controller for GNOME Wayland.

Translates high-level gesture actions (move, click, drag, scroll) into native desktop input events
using GNOME AT-SPI (Atspi.generate_mouse_event), eliminating reliance on X11 or insecure hacks.
"""

from enum import Enum
import math
import threading
import time
from typing import Any, Dict, Optional, Tuple


class MouseButton(Enum):
    LEFT = 1
    MIDDLE = 2
    RIGHT = 3
    SCROLL_UP = 4
    SCROLL_DOWN = 5


class VirtualMouse:
    """
    Wayland-native virtual pointer controller using GNOME accessibility infrastructure.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._is_holding_left = False
        self._is_holding_right = False
        self._current_x = 0
        self._current_y = 0
        self._lock = threading.RLock()
        self._atspi = None

        self._init_backend()

    def _init_backend(self) -> None:
        """Initialize AT-SPI accessibility bindings."""
        try:
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi
            self._atspi = Atspi
        except Exception:
            self._atspi = None

    def move_to(self, x: int, y: int) -> bool:
        """Move cursor to absolute screen pixel coordinate (x, y)."""
        if not self.enabled:
            return False

        with self._lock:
            self._current_x = x
            self._current_y = y

            if self._atspi:
                try:
                    return bool(self._atspi.generate_mouse_event(x, y, "abs"))
                except Exception:
                    return False
            return True

    def click(self, button: MouseButton = MouseButton.LEFT) -> bool:
        """Synthesize a discrete mouse click at current cursor position."""
        if not self.enabled:
            return False

        with self._lock:
            x, y = self._current_x, self._current_y
            if self._atspi:
                try:
                    ev_name = "b1c" if button == MouseButton.LEFT else "b3c"
                    return bool(self._atspi.generate_mouse_event(x, y, ev_name))
                except Exception:
                    return False
            return True

    def double_click(self) -> bool:
        """Synthesize a double-click."""
        if not self.enabled:
            return False

        with self._lock:
            x, y = self._current_x, self._current_y
            if self._atspi:
                try:
                    # AT-SPI double click
                    ok1 = self._atspi.generate_mouse_event(x, y, "b1c")
                    time.sleep(0.08)
                    ok2 = self._atspi.generate_mouse_event(x, y, "b1c")
                    return bool(ok1 and ok2)
                except Exception:
                    return False
            return True

    def press_and_hold(self, button: MouseButton = MouseButton.LEFT) -> bool:
        """Press down button and hold for drag-and-drop operations."""
        if not self.enabled:
            return False

        with self._lock:
            x, y = self._current_x, self._current_y
            if self._atspi:
                try:
                    ev = "b1p" if button == MouseButton.LEFT else "b3p"
                    ok = bool(self._atspi.generate_mouse_event(x, y, ev))
                    if ok:
                        if button == MouseButton.LEFT:
                            self._is_holding_left = True
                        else:
                            self._is_holding_right = True
                    return ok
                except Exception:
                    return False
            return True

    def release_hold(self, button: MouseButton = MouseButton.LEFT) -> bool:
        """Release previously held mouse button."""
        with self._lock:
            x, y = self._current_x, self._current_y
            if self._atspi:
                try:
                    ev = "b1r" if button == MouseButton.LEFT else "b3r"
                    self._atspi.generate_mouse_event(x, y, ev)
                except Exception:
                    pass
            if button == MouseButton.LEFT:
                self._is_holding_left = False
            else:
                self._is_holding_right = False
            return True

    def scroll(self, delta_lines: int) -> bool:
        """Scroll vertical wheel by delta_lines (positive = up, negative = down)."""
        if not self.enabled:
            return False

        with self._lock:
            x, y = self._current_x, self._current_y
            if self._atspi:
                try:
                    ev = "b4c" if delta_lines > 0 else "b5c"
                    count = min(8, abs(delta_lines))
                    for _ in range(count):
                        self._atspi.generate_mouse_event(x, y, ev)
                        time.sleep(0.02)
                    return True
                except Exception:
                    return False
            return True

    def emergency_stop(self) -> None:
        """Immediate failsafe release of all mouse presses and disabling."""
        with self._lock:
            self.release_hold(MouseButton.LEFT)
            self.release_hold(MouseButton.RIGHT)
            self.enabled = False

    def get_state(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "cursor": {"x": self._current_x, "y": self._current_y},
            "is_holding_left": self._is_holding_left,
            "is_holding_right": self._is_holding_right,
            "backend": "AT-SPI 2.0" if self._atspi else "mock/headless",
        }
