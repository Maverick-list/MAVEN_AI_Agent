"""Maverick DevOS - Unified Multimodal Vision & Voice Controller.

Coordinates camera-based hand gesture recognition, screen target observation, and verbal desktop
commands ("click this", "scroll down", "move cursor to upper-right") under strict permission modes.
"""

from enum import Enum
import re
import threading
from typing import Any, Dict, Optional, Tuple

from maverick.vision.calibration import CalibrationConfig
from maverick.vision.gesture_engine import GestureEngine
from maverick.vision.screen import ScreenIntelligence
from maverick.vision.virtual_mouse import MouseButton, VirtualMouse


class VisionMode(Enum):
    """Operational permission modes governing vision and desktop actuation."""
    PRIVACY_MODE = "privacy_mode"        # Camera & gestures completely disabled (hardware off)
    OBSERVE_ONLY = "observe_only"        # Camera & tracking active, mouse actuation blocked
    GESTURE_CONTROL = "gesture_control"  # Virtual mouse & basic gestures active
    VOICE_CONTROL = "voice_control"      # Verbal screen navigation active
    FULL_ASSISTANT = "full_assistant"    # Unified multimodal voice + vision actuation


class VisionController:
    """
    High-level multimodal coordinator bridging VoiceController, GestureEngine, and ScreenIntelligence.
    """

    def __init__(
        self,
        gesture_engine: Optional[GestureEngine] = None,
        screen: Optional[ScreenIntelligence] = None,
        initial_mode: VisionMode = VisionMode.PRIVACY_MODE,
    ):
        self.engine = gesture_engine or GestureEngine()
        self.screen = screen or ScreenIntelligence()
        self.mode = initial_mode
        self._lock = threading.Lock()

    def set_mode(self, new_mode: VisionMode) -> Dict[str, Any]:
        """Switch operational permission mode."""
        with self._lock:
            prev = self.mode
            self.mode = new_mode

            if new_mode == VisionMode.PRIVACY_MODE:
                self.engine.stop()
            elif new_mode in (VisionMode.OBSERVE_ONLY, VisionMode.GESTURE_CONTROL, VisionMode.FULL_ASSISTANT):
                self.engine.start()
                if new_mode == VisionMode.OBSERVE_ONLY:
                    self.engine.mouse.enabled = False
                else:
                    self.engine.mouse.enabled = True

            return {
                "status": "success",
                "previous_mode": prev.value,
                "current_mode": self.mode.value,
                "camera_active": self.engine.camera.is_camera_available() and self.engine.enabled,
                "virtual_mouse_enabled": self.engine.mouse.enabled,
            }

    def handle_multimodal_command(self, phrase: str) -> Optional[Dict[str, Any]]:
        """
        Process verbal instructions relating to vision, pointer, or screen manipulation.
        Returns None if instruction is not a vision/pointer directive.
        """
        clean = (phrase or "").strip().lower()

        # 0. Emergency Stop
        if clean in ("stop", "emergency stop", "berhenti", "berhenti total", "diam"):
            self.engine.mouse.emergency_stop()
            return {
                "status": "success",
                "action": "emergency_stop",
                "response": "Virtual mouse and gesture tracking stopped.",
            }

        # 1. Vision Mode Enable / Disable
        if any(w in clean for w in ("enable vision", "aktifkan mode visi", "start vision", "buka kamera gesture")):
            self.set_mode(VisionMode.FULL_ASSISTANT)
            return {
                "status": "success",
                "action": "vision_mode_enabled",
                "response": "Vision mode enabled. Camera active and hand gestures armed.",
            }

        if any(w in clean for w in ("disable vision", "matikan mode visi", "stop vision", "tutup kamera")):
            self.set_mode(VisionMode.PRIVACY_MODE)
            return {
                "status": "success",
                "action": "vision_mode_disabled",
                "response": "Vision mode disabled. Camera released for privacy.",
            }

        # Check if mouse actuation is permitted in current mode
        if self.mode in (VisionMode.PRIVACY_MODE, VisionMode.OBSERVE_ONLY):
            if any(w in clean for w in ("click", "klik", "scroll", "move cursor", "geser kursor")):
                return {
                    "status": "blocked",
                    "action": "permission_blocked",
                    "response": f"Mouse control is disabled in {self.mode.value.replace('_', ' ').title()}. Say 'enable vision mode' to activate.",
                }

        # 2. "Click this" / "Klik ini"
        if clean in ("click this", "klik ini", "click here", "klik di sini", "click", "klik"):
            ok = self.engine.mouse.click(MouseButton.LEFT)
            return {
                "status": "success" if ok else "error",
                "action": "virtual_mouse_click",
                "response": "Clicking current target.",
            }

        # 3. Double click / Right click
        if "double click" in clean or "klik dua kali" in clean:
            ok = self.engine.mouse.double_click()
            return {
                "status": "success" if ok else "error",
                "action": "virtual_mouse_double_click",
                "response": "Double clicking.",
            }

        if "right click" in clean or "klik kanan" in clean:
            ok = self.engine.mouse.click(MouseButton.RIGHT)
            return {
                "status": "success" if ok else "error",
                "action": "virtual_mouse_right_click",
                "response": "Right clicking.",
            }

        # 4. Scroll Up / Scroll Down
        if any(w in clean for w in ("scroll down", "gulir ke bawah", "scroll bawah", "scroll ke bawah")):
            self.engine.mouse.scroll(-6)
            return {
                "status": "success",
                "action": "virtual_mouse_scroll",
                "response": "Scrolling down.",
            }

        if any(w in clean for w in ("scroll up", "gulir ke atas", "scroll atas", "scroll ke atas")):
            self.engine.mouse.scroll(6)
            return {
                "status": "success",
                "action": "virtual_mouse_scroll",
                "response": "Scrolling up.",
            }

        # 5. Semantic Target Search: "click the [target]"
        click_match = re.search(r"(?:click|klik)\s+(?:the\s+|tombol\s+|pada\s+)?([a-zA-Z0-9\s_-]+)", clean)
        if click_match:
            target_name = click_match.group(1).strip()
            if target_name not in ("this", "ini", "here", "kanan", "kiri", "atas", "bawah"):
                elem = self.screen.find_target(target_name)
                if elem:
                    cx, cy = elem.center
                    self.engine.mouse.move_to(cx, cy)
                    self.engine.mouse.click(MouseButton.LEFT)
                    return {
                        "status": "success",
                        "action": "click_ui_target",
                        "target": elem.name,
                        "coords": {"x": cx, "y": cy},
                        "response": f"Clicking {elem.name}.",
                    }

        # 6. Cursor Corner Positioning
        cfg = self.engine.calibrator.config
        w, h = cfg.screen_width, cfg.screen_height

        if any(w in clean for w in ("upper right", "kanan atas", "top right")):
            self.engine.mouse.move_to(int(w * 0.92), int(h * 0.08))
            return {"status": "success", "action": "cursor_move", "response": "Moving cursor to upper-right corner."}

        if any(w in clean for w in ("upper left", "kiri atas", "top left")):
            self.engine.mouse.move_to(int(w * 0.08), int(h * 0.08))
            return {"status": "success", "action": "cursor_move", "response": "Moving cursor to upper-left corner."}

        if any(w in clean for w in ("center", "tengah", "tengah layar")):
            self.engine.mouse.move_to(int(w * 0.5), int(h * 0.5))
            return {"status": "success", "action": "cursor_move", "response": "Centering cursor."}

        return None

    def get_status(self) -> Dict[str, Any]:
        """Multimodal status snapshot for Control Center."""
        return {
            "mode": self.mode.value,
            "engine": self.engine.get_telemetry(),
            "screen": self.screen.get_summary(),
        }
