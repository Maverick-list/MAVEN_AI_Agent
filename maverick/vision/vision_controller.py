"""
Maverick DevOS - Unified Multimodal Vision, Voice & Interaction Mode Controller.

Coordinates camera-based hand gesture recognition, screen target observation,
and verbal desktop commands ("click this", "scroll down", "type Artificial Intelligence")
under the dual-interaction paradigm (NORMAL Mode vs VISION CONTROL Mode).
"""

from enum import Enum
import re
import threading
from typing import Any, Dict, Optional, Tuple

from maverick.vision.calibration import CalibrationConfig
from maverick.vision.gesture_engine import GestureEngine
from maverick.vision.mode_manager import InteractionMode, InteractionModeManager
from maverick.vision.screen import ScreenIntelligence
from maverick.vision.virtual_input import MouseButton, VirtualKeyboard, VirtualMouse


class VisionMode(Enum):
    """Operational permission modes governing vision and desktop actuation (backward compatible)."""
    PRIVACY_MODE = "privacy_mode"        # Camera & gestures completely disabled (hardware off)
    OBSERVE_ONLY = "observe_only"        # Camera & tracking active, mouse actuation blocked
    GESTURE_CONTROL = "gesture_control"  # Virtual mouse & basic gestures active
    VOICE_CONTROL = "voice_control"      # Verbal screen navigation active
    FULL_ASSISTANT = "full_assistant"    # Unified multimodal voice + vision actuation
    NORMAL = "normal"                    # Mode A: Physical default


class VisionController:
    """
    High-level multimodal coordinator bridging VoiceController, GestureEngine, ScreenIntelligence,
    and the centralized InteractionModeManager.
    """

    def __init__(
        self,
        gesture_engine: Optional[GestureEngine] = None,
        screen: Optional[ScreenIntelligence] = None,
        keyboard: Optional[VirtualKeyboard] = None,
        initial_mode: Any = InteractionMode.NORMAL,
    ):
        self.engine = gesture_engine or GestureEngine()
        self.screen = screen or ScreenIntelligence()
        self.keyboard = keyboard or VirtualKeyboard()
        self._lock = threading.Lock()

        # Central interaction mode manager
        self.mode_manager = InteractionModeManager(gesture_engine=self.engine)

        # Set initial mode
        if isinstance(initial_mode, InteractionMode):
            self._apply_mode(initial_mode)
        elif isinstance(initial_mode, VisionMode):
            self.set_mode(initial_mode)
        else:
            self._apply_mode(InteractionMode.NORMAL)

    @property
    def mode(self) -> Any:
        with self._lock:
            # Map InteractionMode to VisionMode for backward compatibility where applicable
            im = self.mode_manager.mode
            if im == InteractionMode.NORMAL:
                return VisionMode.PRIVACY_MODE
            elif im == InteractionMode.PRIVACY_MODE:
                return VisionMode.PRIVACY_MODE
            elif im == InteractionMode.VISION_ACTIVE:
                return VisionMode.FULL_ASSISTANT
            elif im == InteractionMode.VISION_PAUSED:
                return VisionMode.OBSERVE_ONLY
            elif im == InteractionMode.EMERGENCY_STOPPED:
                return VisionMode.PRIVACY_MODE
            return VisionMode.PRIVACY_MODE

    def _apply_mode(self, im: InteractionMode) -> Dict[str, Any]:
        """Apply an InteractionMode transition."""
        if im in (InteractionMode.NORMAL, InteractionMode.PRIVACY_MODE):
            return self.mode_manager.deactivate_vision()
        elif im == InteractionMode.VISION_ACTIVE:
            return self.mode_manager.activate_vision()
        elif im == InteractionMode.EMERGENCY_STOPPED:
            return self.mode_manager.emergency_stop()
        return self.mode_manager.get_status()

    def set_mode(self, new_mode: VisionMode) -> Dict[str, Any]:
        """Switch operational permission mode (backward compatible)."""
        with self._lock:
            if new_mode in (VisionMode.PRIVACY_MODE, VisionMode.NORMAL):
                res = self.mode_manager.deactivate_vision()
                if new_mode == VisionMode.PRIVACY_MODE:
                    self.mode_manager.set_privacy_mode()
                return {
                    "status": "success",
                    "previous_mode": "active",
                    "current_mode": new_mode.value,
                    "camera_active": False,
                    "virtual_mouse_enabled": False,
                }
            elif new_mode in (VisionMode.OBSERVE_ONLY, VisionMode.GESTURE_CONTROL, VisionMode.FULL_ASSISTANT):
                res = self.mode_manager.activate_vision()
                if new_mode == VisionMode.OBSERVE_ONLY:
                    self.engine.mouse.enabled = False
                else:
                    self.engine.mouse.enabled = True
                return {
                    "status": "success",
                    "previous_mode": "normal",
                    "current_mode": new_mode.value,
                    "camera_active": True,
                    "virtual_mouse_enabled": self.engine.mouse.enabled,
                }

            return self.mode_manager.get_status()

    def handle_multimodal_command(self, phrase: str) -> Optional[Dict[str, Any]]:
        """
        Process verbal instructions relating to vision, pointer, typing, or screen manipulation.
        Returns None if instruction is not a vision/pointer directive.
        """
        clean = (phrase or "").strip().lower()

        # 0. Emergency Stop
        if any(w in clean for w in ("emergency stop", "berhenti", "berhenti total", "diam")) or clean == "stop":
            res = self.mode_manager.emergency_stop()
            return {
                "status": "success",
                "action": "emergency_stop",
                "message": res["message"],
                "response": res["response"],
            }

        # 1. Vision Mode Activation
        if any(w in clean for w in (
            "activate vision mode", "enable gesture control", "switch to visual control",
            "enable vision", "aktifkan mode visi", "aktifkan kontrol gestur", "start vision", "buka kamera gesture"
        )):
            res = self.mode_manager.activate_vision()
            return {
                "status": "success",
                "action": "vision_mode_enabled",
                "message": res["message"],
                "response": res["response"],
            }

        # 2. Vision Mode Deactivation / Return to Normal Mode
        if any(w in clean for w in (
            "deactivate vision mode", "disable gesture control", "return to normal mode",
            "disable vision", "matikan mode visi", "matikan kontrol gestur", "kembali ke mode normal",
            "stop vision", "tutup kamera"
        )):
            res = self.mode_manager.deactivate_vision()
            return {
                "status": "success",
                "action": "vision_mode_disabled",
                "message": res["message"],
                "response": res["response"],
            }

        # 3. Screen Inspection: "explain what is currently visible on my screen"
        if any(w in clean for w in (
            "explain what is currently visible", "explain screen", "what is on my screen",
            "jelaskan layar", "apa yang ada di layar", "terangkan layar"
        )):
            exp = self.screen.explain_screen()
            return {
                "status": "success",
                "action": "explain_screen",
                "explanation": exp.get("explanation", ""),
                "response": exp.get("explanation", ""),
            }

        # 4. Text Typing: "type [text]" / "ketik [text]"
        type_match = re.search(r"^(?:type|ketik|tuliskan)\s+(.+)$", clean)
        if type_match:
            raw_text = type_match.group(1).strip()
            # If in normal mode, typing via voice assistant is still permitted
            ok = self.keyboard.type_text(raw_text)
            return {
                "status": "success" if ok else "error",
                "action": "type_text",
                "text": raw_text,
                "response": f"Typed '{raw_text}'.",
            }

        # Check if mouse actuation is permitted in current mode
        cur_im = self.mode_manager.mode
        if cur_im in (InteractionMode.NORMAL, InteractionMode.PRIVACY_MODE, InteractionMode.VISION_PAUSED, InteractionMode.EMERGENCY_STOPPED):
            if any(w in clean for w in ("click", "klik", "scroll", "move cursor", "geser kursor", "center cursor")):
                return {
                    "status": "blocked",
                    "action": "permission_blocked",
                    "response": (
                        "Normal Mode is currently active. Say 'activate vision mode' to enable gestural mouse control."
                    ),
                }

        # 5. "Click this" / "Klik ini"
        if clean in ("click this", "klik ini", "click here", "klik di sini", "click", "klik"):
            ok = self.engine.mouse.click(MouseButton.LEFT)
            return {
                "status": "success" if ok else "error",
                "action": "virtual_mouse_click",
                "response": "Clicking current target.",
            }

        # 6. Double click / Right click
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

        # 7. Scroll Up / Scroll Down
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

        # 8. Semantic Target Search: "click the [target]"
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

        # 9. Cursor Corner Positioning
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
        mgr_status = self.mode_manager.get_status()
        eng = mgr_status.get("engine", {})
        return {
            "mode": mgr_status["mode"],
            "interaction_mode": mgr_status["mode"],
            "is_vision_active": mgr_status["is_vision_active"],
            "is_vision_paused": mgr_status["is_vision_paused"],
            "is_normal_mode": mgr_status["is_normal_mode"],
            "physical_input_status": mgr_status["physical_input_status"],
            "camera": eng.get("camera", {}),
            "mouse": eng.get("mouse", {}),
            "engine": eng,
            "screen": self.screen.get_summary(),
        }
