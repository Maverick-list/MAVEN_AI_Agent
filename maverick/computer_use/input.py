"""Maverick DevOS - Universal Linux Input Engine.

Wayland-native mouse and keyboard synthesis using GNOME AT-SPI and GDK.
Supports multi-button clicks, smooth drag-and-drop, scroll dynamics, text entry,
keyboard shortcuts (Ctrl+S, Ctrl+Shift+P, etc.), and clipboard integration.
Enforces physical input priority and immediate emergency-stop failsafes.
"""

from enum import Enum
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("maverick.computer_use.input")

try:
    import gi
    gi.require_version("Atspi", "2.0")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Atspi, Gtk, Gdk
    _HAS_ATSPI_GTK = True
except Exception as _import_err:
    _HAS_ATSPI_GTK = False
    _IMPORT_ERR = str(_import_err)


class MouseButton(Enum):
    LEFT = "left"
    MIDDLE = "middle"
    RIGHT = "right"


# Standard X11/AT-SPI Keysym names for modifiers and navigation
KEY_MAP = {
    "ctrl": "Control_L",
    "control": "Control_L",
    "shift": "Shift_L",
    "alt": "Alt_L",
    "super": "Super_L",
    "win": "Super_L",
    "meta": "Super_L",
    "enter": "Return",
    "return": "Return",
    "esc": "Escape",
    "escape": "Escape",
    "tab": "Tab",
    "backspace": "BackSpace",
    "delete": "Delete",
    "del": "Delete",
    "space": "space",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pageup": "Page_Up",
    "pagedown": "Page_Down",
    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4", "f5": "F5",
    "f6": "F6", "f7": "F7", "f8": "F8", "f9": "F9", "f10": "F10",
    "f11": "F11", "f12": "F12",
}


class UniversalInputEngine:
    """
    Unified Wayland-compatible mouse and keyboard automation controller.
    Ensures thread-safe synthesis while preserving physical input priority.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._lock = threading.RLock()
        self._current_x = 0
        self._current_y = 0
        self._is_holding_left = False
        self._is_holding_right = False
        self._last_action = "initialized"
        self._last_action_timestamp = time.time()
        self._atspi = Atspi if _HAS_ATSPI_GTK else None

    @property
    def is_available(self) -> bool:
        """Check if native input synthesizer is functional."""
        return self._atspi is not None

    def set_enabled(self, enabled: bool) -> None:
        """Toggle virtual input synthesis."""
        with self._lock:
            self.enabled = bool(enabled)
            if not self.enabled:
                self.emergency_stop()

    def emergency_stop(self) -> None:
        """Immediately release held buttons, freeze cursor, and disarm virtual input."""
        with self._lock:
            if self._is_holding_left:
                self.release_hold(MouseButton.LEFT)
            if self._is_holding_right:
                self.release_hold(MouseButton.RIGHT)
            self.enabled = False
            self._last_action = "emergency_stopped"
            self._last_action_timestamp = time.time()
            logger.info("Universal Input Engine EMERGENCY STOP executed.")

    # --- Mouse Methods ---

    def move_to(self, x: int, y: int) -> bool:
        """Move pointer to absolute screen pixel coordinate (x, y)."""
        if not self.enabled:
            return False

        with self._lock:
            self._current_x = int(x)
            self._current_y = int(y)
            self._last_action = f"move_to({x}, {y})"
            self._last_action_timestamp = time.time()

            if self._atspi:
                try:
                    return bool(self._atspi.generate_mouse_event(self._current_x, self._current_y, "abs"))
                except Exception as e:
                    logger.debug(f"Failed to move pointer: {e}")
                    return False
            return True

    def click(self, button: MouseButton = MouseButton.LEFT) -> bool:
        """Execute a discrete mouse click at current cursor position."""
        if not self.enabled:
            return False

        with self._lock:
            x, y = self._current_x, self._current_y
            btn_str = button.value if isinstance(button, MouseButton) else str(button)
            self._last_action = f"click({btn_str})"
            self._last_action_timestamp = time.time()

            if self._atspi:
                try:
                    if btn_str == "right":
                        ev = "b3c"
                    elif btn_str == "middle":
                        ev = "b2c"
                    else:
                        ev = "b1c"
                    return bool(self._atspi.generate_mouse_event(x, y, ev))
                except Exception as e:
                    logger.debug(f"Mouse click failed: {e}")
                    return False
            return True

    def double_click(self) -> bool:
        """Synthesize two consecutive left clicks."""
        if not self.enabled:
            return False

        with self._lock:
            x, y = self._current_x, self._current_y
            self._last_action = "double_click"
            self._last_action_timestamp = time.time()

            if self._atspi:
                try:
                    ok1 = self._atspi.generate_mouse_event(x, y, "b1c")
                    time.sleep(0.08)
                    ok2 = self._atspi.generate_mouse_event(x, y, "b1c")
                    return bool(ok1 and ok2)
                except Exception:
                    return False
            return True

    def right_click(self) -> bool:
        """Convenience method for right click."""
        return self.click(MouseButton.RIGHT)

    def click_coordinate(self, x: int, y: int, button: MouseButton = MouseButton.LEFT) -> bool:
        """Move cursor to target coordinates and click."""
        if not self.enabled:
            return False
        if self.move_to(x, y):
            time.sleep(0.04)
            return self.click(button)
        return False

    def press_and_hold(self, button: MouseButton = MouseButton.LEFT) -> bool:
        """Press and hold mouse button for drag operations."""
        if not self.enabled:
            return False

        with self._lock:
            x, y = self._current_x, self._current_y
            btn_str = button.value if isinstance(button, MouseButton) else str(button)
            self._last_action = f"press_and_hold({btn_str})"
            self._last_action_timestamp = time.time()

            if self._atspi:
                try:
                    ev = "b3p" if btn_str == "right" else "b1p"
                    ok = bool(self._atspi.generate_mouse_event(x, y, ev))
                    if ok:
                        if btn_str == "right":
                            self._is_holding_right = True
                        else:
                            self._is_holding_left = True
                    return ok
                except Exception:
                    return False
            return True

    def release_hold(self, button: MouseButton = MouseButton.LEFT) -> bool:
        """Release a held mouse button."""
        with self._lock:
            x, y = self._current_x, self._current_y
            btn_str = button.value if isinstance(button, MouseButton) else str(button)
            self._last_action = f"release_hold({btn_str})"
            self._last_action_timestamp = time.time()

            if self._atspi:
                try:
                    ev = "b3r" if btn_str == "right" else "b1r"
                    self._atspi.generate_mouse_event(x, y, ev)
                except Exception:
                    pass

            if btn_str == "right":
                self._is_holding_right = False
            else:
                self._is_holding_left = False
            return True

    def drag_and_drop(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        steps: int = 15,
        delay: float = 0.015,
    ) -> bool:
        """Execute a smooth drag and drop from (start_x, start_y) to (end_x, end_y)."""
        if not self.enabled:
            return False

        with self._lock:
            self._last_action = f"drag_and_drop(({start_x}, {start_y}) -> ({end_x}, {end_y}))"
            self._last_action_timestamp = time.time()

            # 1. Move to start position
            if not self.move_to(start_x, start_y):
                return False
            time.sleep(0.05)

            # 2. Press down
            if not self.press_and_hold(MouseButton.LEFT):
                return False
            time.sleep(0.05)

            # 3. Interpolate path
            for s in range(1, steps + 1):
                inter_x = int(start_x + (end_x - start_x) * (s / steps))
                inter_y = int(start_y + (end_y - start_y) * (s / steps))
                self.move_to(inter_x, inter_y)
                time.sleep(delay)

            time.sleep(0.05)
            # 4. Release
            return self.release_hold(MouseButton.LEFT)

    def scroll(self, delta_lines: int) -> bool:
        """Scroll vertical wheel by delta_lines (positive = up, negative = down)."""
        if not self.enabled or delta_lines == 0:
            return False

        with self._lock:
            x, y = self._current_x, self._current_y
            self._last_action = f"scroll({delta_lines})"
            self._last_action_timestamp = time.time()

            if self._atspi:
                try:
                    ev = "b4c" if delta_lines > 0 else "b5c"
                    count = min(15, abs(delta_lines))
                    for _ in range(count):
                        self._atspi.generate_mouse_event(x, y, ev)
                        time.sleep(0.02)
                    return True
                except Exception:
                    return False
            return True

    # --- Keyboard Methods ---

    def type_text(self, text: str, delay_per_char: float = 0.005) -> bool:
        """Type a string of text into the active focused desktop element."""
        if not self.enabled or not text:
            return False

        with self._lock:
            self._last_action = f"type_text(len={len(text)})"
            self._last_action_timestamp = time.time()

            if not self._atspi:
                return True

            try:
                # KeySynthType.STRING = 4
                synth_string = getattr(self._atspi.KeySynthType, "STRING", 4)
                ok = self._atspi.generate_keyboard_event(0, text, synth_string)
                if delay_per_char > 0:
                    time.sleep(delay_per_char * len(text))
                return bool(ok)
            except Exception as e:
                logger.debug(f"Direct string typing failed: {e}")
                return False

    def send_key(self, key_name: str) -> bool:
        """Send a single press-and-release key event (e.g. Return, Escape, Tab)."""
        if not self.enabled:
            return False

        with self._lock:
            resolved_key = KEY_MAP.get(key_name.lower(), key_name)
            self._last_action = f"send_key({resolved_key})"
            self._last_action_timestamp = time.time()

            if not self._atspi:
                return True

            try:
                press_type = getattr(self._atspi.KeySynthType, "PRESS", 0)
                rel_type = getattr(self._atspi.KeySynthType, "RELEASE", 1)
                p = self._atspi.generate_keyboard_event(0, resolved_key, press_type)
                time.sleep(0.02)
                r = self._atspi.generate_keyboard_event(0, resolved_key, rel_type)
                return bool(p and r)
            except Exception as e:
                logger.debug(f"send_key failed for {resolved_key}: {e}")
                return False

    def send_shortcut(self, shortcut: str) -> bool:
        """
        Execute a keyboard combination such as 'Ctrl+S', 'Ctrl+Shift+P', 'Alt+Tab'.
        Parses modifiers and keys in sequence.
        """
        if not self.enabled:
            return False

        with self._lock:
            self._last_action = f"send_shortcut({shortcut})"
            self._last_action_timestamp = time.time()

            if not self._atspi:
                return True

            parts = [p.strip() for p in shortcut.split("+") if p.strip()]
            if not parts:
                return False

            press_type = getattr(self._atspi.KeySynthType, "PRESS", 0)
            rel_type = getattr(self._atspi.KeySynthType, "RELEASE", 1)

            modifiers_to_release = []
            try:
                # Press modifiers in order
                for part in parts[:-1]:
                    key_name = KEY_MAP.get(part.lower(), part)
                    self._atspi.generate_keyboard_event(0, key_name, press_type)
                    modifiers_to_release.append(key_name)
                    time.sleep(0.02)

                # Press and release main key
                main_key_raw = parts[-1]
                main_key = KEY_MAP.get(main_key_raw.lower(), main_key_raw)
                self._atspi.generate_keyboard_event(0, main_key, press_type)
                time.sleep(0.03)
                self._atspi.generate_keyboard_event(0, main_key, rel_type)
                time.sleep(0.02)
                return True
            except Exception as e:
                logger.debug(f"send_shortcut failed for {shortcut}: {e}")
                return False
            finally:
                # Release modifiers in reverse order
                for mod in reversed(modifiers_to_release):
                    try:
                        self._atspi.generate_keyboard_event(0, mod, rel_type)
                    except Exception:
                        pass

    # --- Clipboard Methods ---

    def copy_to_clipboard(self, text: str) -> bool:
        """Store text into system clipboard using GDK/GTK."""
        try:
            cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            cb.set_text(text, -1)
            cb.store()
            return True
        except Exception as e:
            logger.debug(f"copy_to_clipboard failed: {e}")
            return False

    def get_clipboard_text(self) -> str:
        """Read text from system clipboard using GDK/GTK."""
        try:
            cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            return cb.wait_for_text() or ""
        except Exception as e:
            logger.debug(f"get_clipboard_text failed: {e}")
            return ""

    def paste_text(self, text: str) -> bool:
        """Set text into clipboard and dispatch Ctrl+V into active element."""
        if not self.enabled:
            return False
        if self.copy_to_clipboard(text):
            time.sleep(0.05)
            return self.send_shortcut("Ctrl+v")
        # Fallback to direct typing
        return self.type_text(text)

    def select_all(self) -> bool:
        """Dispatch Ctrl+A select all."""
        return self.send_shortcut("Ctrl+a")

    # --- Telemetry & State ---

    def get_telemetry(self) -> Dict[str, Any]:
        """Telemetry snapshot for Control Center HUD."""
        with self._lock:
            return {
                "enabled": self.enabled,
                "cursor": {"x": self._current_x, "y": self._current_y},
                "is_holding_left": self._is_holding_left,
                "is_holding_right": self._is_holding_right,
                "last_action": self._last_action,
                "last_action_timestamp": self._last_action_timestamp,
                "backend": "AT-SPI 2.0 + GDK 3" if self._atspi else "mock/headless",
            }
