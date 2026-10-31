"""
Maverick DevOS - Wayland-Native Virtual Mouse and Keyboard Input Synthesizers.

Uses GNOME AT-SPI (Accessibility Toolkit) to dispatch pointer motion, mouse clicks,
wheel scrolls, and keystroke typing without X11, XWayland, uinput, or root permissions.
Enforces thread-safety with reentrant locks and respects interaction mode gates.
"""

from enum import Enum
import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("maverick.vision.virtual_input")


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
        self._watchdog_timeout = 3.0
        self._watchdog_timer: Optional[threading.Timer] = None

        self._init_backend()

    def _init_backend(self) -> None:
        """Initialize AT-SPI accessibility bindings."""
        try:
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi
            self._atspi = Atspi
        except Exception as e:
            logger.debug("AT-SPI VirtualMouse backend unavailable: %s", e)
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
                    ok1 = self._atspi.generate_mouse_event(x, y, "b1c")
                    time.sleep(0.08)
                    ok2 = self._atspi.generate_mouse_event(x, y, "b1c")
                    return bool(ok1 and ok2)
                except Exception:
                    return False
            return True

    def press_and_hold(self, button: MouseButton = MouseButton.LEFT) -> bool:
        """Press down button and hold for drag-and-drop operations with watchdog safety."""
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
                        self._arm_watchdog()
                    return ok
                except Exception:
                    return False
            else:
                if button == MouseButton.LEFT:
                    self._is_holding_left = True
                else:
                    self._is_holding_right = True
                self._arm_watchdog()
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

            if not (self._is_holding_left or self._is_holding_right):
                self._disarm_watchdog()
            return True

    def release_all_holds(self) -> None:
        """Release all button holds and disarm watchdog timer."""
        with self._lock:
            self._disarm_watchdog()
            if self._is_holding_left:
                self.release_hold(MouseButton.LEFT)
            if self._is_holding_right:
                self.release_hold(MouseButton.RIGHT)

    def _arm_watchdog(self) -> None:
        """Arm or reset watchdog timer to auto-release stuck holds."""
        self._disarm_watchdog()
        self._watchdog_timer = threading.Timer(self._watchdog_timeout, self._on_watchdog_timeout)
        self._watchdog_timer.daemon = True
        self._watchdog_timer.start()

    def _disarm_watchdog(self) -> None:
        """Disarm active watchdog timer."""
        if self._watchdog_timer is not None:
            self._watchdog_timer.cancel()
            self._watchdog_timer = None

    def _on_watchdog_timeout(self) -> None:
        """Triggered when virtual mouse hold exceeds timeout threshold."""
        with self._lock:
            if self._is_holding_left or self._is_holding_right:
                logger.warning(
                    "VirtualMouse watchdog triggered: auto-releasing held buttons after %.1fs inactivity",
                    self._watchdog_timeout,
                )
                self.release_all_holds()

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
            self.release_all_holds()
            self.enabled = False

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.enabled = bool(enabled)

    def get_telemetry(self) -> Dict[str, Any]:
        return self.get_state()

    def get_state(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "cursor": {"x": self._current_x, "y": self._current_y},
            "is_holding_left": self._is_holding_left,
            "is_holding_right": self._is_holding_right,
            "backend": "AT-SPI 2.0" if self._atspi else "mock/headless",
        }


class VirtualKeyboard:
    """
    Wayland-native virtual keyboard synthesizer using GNOME AT-SPI.
    Dispatches string text typing and key combinations safely.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._lock = threading.RLock()
        self._atspi = None

        self._init_backend()

    def _init_backend(self) -> None:
        try:
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi
            self._atspi = Atspi
        except Exception as e:
            logger.debug("AT-SPI VirtualKeyboard backend unavailable: %s", e)
            self._atspi = None

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.enabled = bool(enabled)

    def type_text(self, text: str) -> bool:
        """Type a text string into the currently focused desktop element."""
        if not self.enabled or not text:
            return False

        with self._lock:
            if not self._atspi:
                return False

            try:
                # Dispatch string via AT-SPI STRING synth
                synth_type = getattr(self._atspi.KeySynthType, "STRING", 0)
                return bool(self._atspi.generate_keyboard_event(0, text, synth_type))
            except Exception as e:
                logger.debug("AT-SPI text typing failed: %s", e)
                return False

    def press_key(self, key_name: str) -> bool:
        """Synthesize a special key press (e.g. Return, Escape, Tab)."""
        if not self.enabled:
            return False

        with self._lock:
            if not self._atspi:
                return False

            try:
                press_type = getattr(self._atspi.KeySynthType, "PRESS", 1)
                rel_type = getattr(self._atspi.KeySynthType, "RELEASE", 2)
                p = self._atspi.generate_keyboard_event(0, key_name, press_type)
                r = self._atspi.generate_keyboard_event(0, key_name, rel_type)
                return bool(p and r)
            except Exception:
                return False

    def get_telemetry(self) -> Dict[str, Any]:
        return self.get_state()

    def get_state(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "backend": "AT-SPI 2.0" if self._atspi else "mock/headless",
        }
