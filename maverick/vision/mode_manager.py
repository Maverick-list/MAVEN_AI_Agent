"""
Maverick DevOS - Centralized Interaction Mode Manager.

Governs desktop interaction modes:
- MODE A: NORMAL (Default) - Physical mouse and keyboard are primary. Camera is off.
- MODE B: VISION CONTROL - Camera active, hand/finger gesture cursor and clicks enabled.
  Physical mouse and keyboard remain 100% functional and take immediate priority.

Supported States:
- NORMAL: Default state after boot/restart. Physical input only, camera off, virtual mouse disarmed.
- VISION_STARTING: Transient hardware initialization and camera exposure lock.
- VISION_ACTIVE: Full gestural control active. Virtual mouse and gestures enabled.
- VISION_PAUSED: Temporarily paused when physical mouse/keyboard activity is detected.
- EMERGENCY_STOPPED: Virtual automation halted, button holds released.
- PRIVACY_MODE: Camera completely disconnected and released.
"""

from enum import Enum
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("maverick.vision.mode_manager")

_uid = os.getuid()
_at_spi_socket = f"/run/user/{_uid}/at-spi/bus"
if "AT_SPI_BUS_ADDRESS" not in os.environ and os.path.exists(_at_spi_socket):
    os.environ["AT_SPI_BUS_ADDRESS"] = f"unix:path={_at_spi_socket}"

try:
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
    HAS_ATSPI = True
except Exception:
    Atspi = None
    HAS_ATSPI = False


class InteractionMode(Enum):
    """Deterministic interaction states for Maven desktop control."""
    NORMAL = "normal"                          # Mode A: Physical input default, camera off
    VISION_STARTING = "vision_starting"        # Camera & pipeline initialization
    VISION_ACTIVE = "vision_active"            # Mode B: Vision gestural control active
    VISION_PAUSED = "vision_paused"            # Paused for physical input priority
    EMERGENCY_STOPPED = "emergency_stopped"    # Safety halt engaged
    PRIVACY_MODE = "privacy_mode"              # Hardware camera disconnected


class PhysicalInputMonitor:
    """
    Non-intrusive monitor for physical mouse and keyboard activity on GNOME Wayland.
    Uses AT-SPI DeviceListener to detect physical interaction without intercepting or blocking.
    """

    def __init__(self, on_physical_activity: Optional[Callable[[], None]] = None):
        self.on_physical_activity = on_physical_activity
        self.enabled = False
        self._listener = None
        self._last_event_time = 0.0
        self._lock = threading.Lock()
        self._atspi = Atspi if HAS_ATSPI else None

        self._init_listener()

    def _init_listener(self) -> None:
        """Initialize AT-SPI device event listener."""
        if not HAS_ATSPI or not self._atspi:
            return

        try:
            def _stroke_handler(stroke):
                now = time.time()
                with self._lock:
                    self._last_event_time = now
                if self.enabled and self.on_physical_activity:
                    try:
                        self.on_physical_activity()
                    except Exception:
                        pass
                # return False to ensure event passes to Wayland compositor unimpeded
                return False

            self._listener = self._atspi.DeviceListener.new(_stroke_handler, None)
        except Exception as e:
            logger.debug("AT-SPI PhysicalInputMonitor unavailable: %s", e)
            self._listener = None

    @property
    def last_activity_time(self) -> float:
        with self._lock:
            return self._last_event_time

    def is_physical_active(self, window_s: float = 1.5) -> bool:
        """Return True if physical input was detected within recent window."""
        with self._lock:
            return (time.time() - self._last_event_time) < window_s

    def record_activity(self) -> None:
        """Manually flag physical interaction (e.g. from input device polling)."""
        now = time.time()
        with self._lock:
            self._last_event_time = now
        if self.enabled and self.on_physical_activity:
            self.on_physical_activity()

    def stop(self) -> None:
        """Stop physical input monitoring."""
        self.enabled = False


class InteractionModeManager:
    """
    Central coordinator of Maven desktop interaction modes.
    Enforces deterministic state transitions, camera lifecycle, and physical input priority.
    """

    VOICE_ACTIVATION_RESPONSE = (
        "Vision Control Mode activated. You can now control the desktop using hand gestures."
    )
    VOICE_DEACTIVATION_RESPONSE = (
        "Normal Mode restored. Your physical mouse and keyboard remain in control."
    )
    EMERGENCY_STOP_RESPONSE = (
        "Emergency stop activated. All automated inputs and gestures halted."
    )

    def __init__(
        self,
        gesture_engine: Optional[Any] = None,
        physical_priority_pause_sec: float = 1.5,
        on_mode_change: Optional[Callable[[InteractionMode, InteractionMode], None]] = None,
        camera: Optional[Any] = None,
        virtual_mouse: Optional[Any] = None,
        virtual_keyboard: Optional[Any] = None,
        physical_priority_window_s: Optional[float] = None,
        **kwargs,
    ):
        self.engine = gesture_engine
        self.camera = camera
        self.virtual_mouse = virtual_mouse
        self.virtual_keyboard = virtual_keyboard
        self.physical_priority_pause_sec = (
            physical_priority_window_s if physical_priority_window_s is not None else physical_priority_pause_sec
        )
        self.on_mode_change = on_mode_change

        # Always initialize to NORMAL mode by default
        self._mode = InteractionMode.NORMAL
        self._lock = threading.RLock()
        self._pause_timer: Optional[threading.Timer] = None
        self._state_history: List[Tuple[float, InteractionMode]] = [(time.time(), InteractionMode.NORMAL)]

        # Physical input monitor
        self.physical_monitor = PhysicalInputMonitor(on_physical_activity=self._handle_physical_input_detected)

    @property
    def mode(self) -> InteractionMode:
        with self._lock:
            return self._mode

    @property
    def current_mode(self) -> InteractionMode:
        return self.mode

    def is_vision_active(self) -> bool:
        with self._lock:
            return self._mode == InteractionMode.VISION_ACTIVE

    def shutdown(self) -> None:
        with self._lock:
            if self._pause_timer:
                self._pause_timer.cancel()
                self._pause_timer = None
        self.physical_monitor.stop()

    def activate_vision(self) -> Dict[str, Any]:
        """
        Transition from NORMAL / PRIVACY into VISION_ACTIVE.
        Powers on camera, warms up pipeline, and arms virtual mouse.
        """
        with self._lock:
            prev = self._mode
            if prev == InteractionMode.VISION_ACTIVE:
                return {
                    "ok": True,
                    "status": "already_active",
                    "mode": self._mode.value,
                    "message": "Vision Control Mode is already active.",
                    "response": self.VOICE_ACTIVATION_RESPONSE,
                }

            self._transition(InteractionMode.VISION_STARTING)

            # Start camera if available
            if self.camera:
                try:
                    cam_ok = self.camera.start()
                    if not cam_ok:
                        self._transition(InteractionMode.NORMAL)
                        return {
                            "ok": False,
                            "status": "error",
                            "mode": self._mode.value,
                            "message": "Camera start failed. Falling back to Normal Mode.",
                            "response": "Could not access the camera. Normal Mode restored.",
                        }
                except Exception as e:
                    logger.error("Failed to start camera: %s", e)
                    self._transition(InteractionMode.NORMAL)
                    return {
                        "ok": False,
                        "status": "error",
                        "mode": self._mode.value,
                        "message": str(e),
                        "response": "Could not access the camera. Normal Mode restored.",
                    }

            # Start gesture engine
            engine_started = False
            if self.engine:
                try:
                    res = self.engine.start()
                    engine_started = True if res is None else bool(res)
                except Exception as e:
                    logger.error("Failed to start vision engine: %s", e)
                    engine_started = False
            else:
                engine_started = True

            if not engine_started:
                if self.camera:
                    self.camera.stop()
                self._transition(InteractionMode.NORMAL)
                return {
                    "ok": False,
                    "status": "error",
                    "mode": self._mode.value,
                    "message": "Camera/engine initialization failed. Falling back to Normal Mode.",
                    "response": "Could not access the camera. Normal Mode restored.",
                }

            # Arm virtual mouse and clear prior emergency stops
            if self.engine and hasattr(self.engine, "reset_emergency_stop"):
                self.engine.reset_emergency_stop()
            if self.virtual_mouse and hasattr(self.virtual_mouse, "set_enabled"):
                self.virtual_mouse.set_enabled(True)
            elif self.engine and hasattr(self.engine, "mouse") and hasattr(self.engine.mouse, "set_enabled"):
                self.engine.mouse.set_enabled(True)

            self._transition(InteractionMode.VISION_ACTIVE)
            self.physical_monitor.enabled = True

            return {
                "ok": True,
                "status": "success",
                "previous_mode": prev.value,
                "current_mode": self._mode.value,
                "message": "Vision Control Mode activated.",
                "response": self.VOICE_ACTIVATION_RESPONSE,
            }

    def deactivate_vision(self) -> Dict[str, Any]:
        """
        Transition from VISION_ACTIVE / VISION_PAUSED to NORMAL mode.
        Stops camera capture and ensures physical mouse/keyboard are solely in control.
        """
        with self._lock:
            prev = self._mode
            self.physical_monitor.enabled = False

            if self._pause_timer:
                self._pause_timer.cancel()
                self._pause_timer = None

            if self.virtual_mouse and hasattr(self.virtual_mouse, "set_enabled"):
                self.virtual_mouse.set_enabled(False)
            elif self.engine and hasattr(self.engine, "mouse") and hasattr(self.engine.mouse, "set_enabled"):
                self.engine.mouse.set_enabled(False)

            if self.engine:
                try:
                    self.engine.stop()
                    if hasattr(self.engine, "tracker") and hasattr(self.engine.tracker, "release_resources"):
                        self.engine.tracker.release_resources()
                except Exception as e:
                    logger.error("Error stopping vision engine: %s", e)

            if self.camera:
                try:
                    self.camera.stop()
                except Exception as e:
                    logger.error("Error stopping camera: %s", e)

            self._transition(InteractionMode.NORMAL)

            return {
                "ok": True,
                "status": "success",
                "previous_mode": prev.value,
                "current_mode": self._mode.value,
                "message": "Normal Mode restored.",
                "response": self.VOICE_DEACTIVATION_RESPONSE,
            }

    def toggle_mode(self) -> Dict[str, Any]:
        """Toggle between NORMAL MODE and VISION CONTROL MODE."""
        with self._lock:
            if self._mode in (InteractionMode.VISION_ACTIVE, InteractionMode.VISION_PAUSED, InteractionMode.VISION_STARTING):
                return self.deactivate_vision()
            else:
                return self.activate_vision()

    def pause_vision(self, duration_sec: Optional[float] = None) -> Dict[str, Any]:
        """
        Temporarily pause virtual mouse actuation (e.g. physical user touched mouse).
        Maintains camera awareness but blocks virtual clicks and pointer motion.
        """
        with self._lock:
            if self._mode != InteractionMode.VISION_ACTIVE:
                return {"status": "ignored", "mode": self._mode.value}

            prev = self._mode
            self._transition(InteractionMode.VISION_PAUSED)

            if self.virtual_mouse and hasattr(self.virtual_mouse, "set_enabled"):
                self.virtual_mouse.set_enabled(False)
            elif self.engine and hasattr(self.engine, "mouse"):
                self.engine.mouse.enabled = False

            # Schedule auto-resume
            duration = duration_sec or self.physical_priority_pause_sec
            if self._pause_timer:
                self._pause_timer.cancel()

            self._pause_timer = threading.Timer(duration, self._auto_resume_vision)
            self._pause_timer.daemon = True
            self._pause_timer.start()

            return {
                "status": "paused",
                "previous_mode": prev.value,
                "current_mode": self._mode.value,
                "duration_sec": duration,
            }

    def _auto_resume_vision(self) -> None:
        """Called when physical user pause window elapses."""
        with self._lock:
            if self._mode != InteractionMode.VISION_PAUSED:
                return

            # Check if recent physical input arrived while waiting
            since_physical = time.time() - self.physical_monitor.last_activity_time
            if since_physical < self.physical_priority_pause_sec:
                # Extend pause
                remaining = self.physical_priority_pause_sec - since_physical
                self._pause_timer = threading.Timer(remaining, self._auto_resume_vision)
                self._pause_timer.daemon = True
                self._pause_timer.start()
                return

            # Resume active vision
            self._transition(InteractionMode.VISION_ACTIVE)
            if self.virtual_mouse and hasattr(self.virtual_mouse, "set_enabled"):
                self.virtual_mouse.set_enabled(True)
            elif self.engine and hasattr(self.engine, "mouse"):
                self.engine.mouse.enabled = True

    def _handle_physical_input_detected(self) -> None:
        """Invoked when physical input occurs on desktop."""
        with self._lock:
            if self._mode == InteractionMode.VISION_ACTIVE:
                self.pause_vision(self.physical_priority_pause_sec)

    def emergency_stop(self) -> Dict[str, Any]:
        """
        Failsafe emergency halt.
        Disarms virtual mouse, releases all button holds, and stops camera.
        """
        with self._lock:
            prev = self._mode
            self.physical_monitor.enabled = False

            if self._pause_timer:
                self._pause_timer.cancel()
                self._pause_timer = None

            if self.virtual_mouse and hasattr(self.virtual_mouse, "emergency_stop"):
                self.virtual_mouse.emergency_stop()

            if self.engine:
                try:
                    if hasattr(self.engine, "mouse") and hasattr(self.engine.mouse, "emergency_stop"):
                        self.engine.mouse.emergency_stop()
                    if hasattr(self.engine, "emergency_stop"):
                        self.engine.emergency_stop()
                    else:
                        self.engine.stop()
                except Exception as e:
                    logger.error("Error in emergency stop: %s", e)

            if self.camera:
                try:
                    self.camera.stop()
                except Exception as e:
                    logger.error("Error stopping camera on e-stop: %s", e)

            self._transition(InteractionMode.EMERGENCY_STOPPED)

            return {
                "ok": True,
                "status": "success",
                "action": "emergency_stop",
                "previous_mode": prev.value,
                "current_mode": self._mode.value,
                "message": "Emergency Stop engaged. Automation halted.",
                "response": self.EMERGENCY_STOP_RESPONSE,
            }

    def set_privacy_mode(self) -> Dict[str, Any]:
        """Release camera hardware handle and power down vision pipeline."""
        with self._lock:
            prev = self._mode
            self.physical_monitor.enabled = False

            if self.engine:
                try:
                    self.engine.stop()
                except Exception as e:
                    logger.error("Error entering privacy mode: %s", e)

            self._transition(InteractionMode.PRIVACY_MODE)

            return {
                "status": "success",
                "previous_mode": prev.value,
                "current_mode": self._mode.value,
                "message": "Privacy Mode engaged. Camera disconnected.",
                "response": "Privacy Mode engaged. Camera hardware has been powered off.",
            }

    def _transition(self, new_mode: InteractionMode) -> None:
        """Internal atomic state transition."""
        prev = self._mode
        self._mode = new_mode
        self._state_history.append((time.time(), new_mode))
        if len(self._state_history) > 50:
            self._state_history.pop(0)

        logger.info("Interaction mode transition: %s -> %s", prev.value, new_mode.value)
        if self.on_mode_change:
            try:
                self.on_mode_change(prev, new_mode)
            except Exception:
                pass

    def get_status(self) -> Dict[str, Any]:
        """Telemetry snapshot for Control Center HUD and API."""
        with self._lock:
            engine_telemetry = self.engine.get_telemetry() if self.engine and hasattr(self.engine, "get_telemetry") else {}
            return {
                "mode": self._mode.value,
                "is_vision_active": self._mode == InteractionMode.VISION_ACTIVE,
                "is_vision_paused": self._mode == InteractionMode.VISION_PAUSED,
                "is_normal_mode": self._mode == InteractionMode.NORMAL,
                "is_privacy_mode": self._mode == InteractionMode.PRIVACY_MODE,
                "is_emergency_stopped": self._mode == InteractionMode.EMERGENCY_STOPPED,
                "physical_input_status": "unrestricted_priority",
                "camera_active": bool(engine_telemetry.get("camera", {}).get("is_active", False)),
                "virtual_mouse_enabled": bool(engine_telemetry.get("mouse", {}).get("enabled", False)),
                "engine": engine_telemetry,
            }
