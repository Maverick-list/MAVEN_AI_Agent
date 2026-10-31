"""Maverick DevOS - Secure Camera Hardware Interface.

Provides safe discovery, initialization, frame capture, and graceful lifecycle management
for the ASUS ROG Strix FHD Webcam (/dev/video0) using OpenCV.
Enforces strict privacy: zero disk recordings, zero external frame streaming.
"""

import glob
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


class CameraManager:
    """
    Thread-safe, privacy-preserving camera interface.
    Controls hardware acquisition, stream health monitoring, and frame distribution.
    """

    def __init__(
        self,
        device_index: int = 0,
        width: int = 640,
        height: int = 480,
        target_fps: int = 30,
    ):
        self.device_index = device_index
        self.target_width = width
        self.target_height = height
        self.target_fps = target_fps

        self._cap: Optional[cv2.VideoCapture] = None
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._frame_event = threading.Event()

        # Frame buffers
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_timestamp: float = 0.0
        self._frame_count: int = 0
        self._fps_actual: float = 0.0
        self._last_fps_calc_time = time.time()
        self._fps_counter = 0

        # Health & Telemetry
        self._is_active = False
        self._error_count = 0
        self._last_error: Optional[str] = None
        self._reconnect_attempts = 0

    @staticmethod
    def discover_devices() -> List[Dict[str, Any]]:
        """Discover available video devices in /dev/video*."""
        devices = []
        video_nodes = sorted(glob.glob("/dev/video*"))
        for node in video_nodes:
            idx_str = node.replace("/dev/video", "")
            if not idx_str.isdigit():
                continue
            idx = int(idx_str)
            readable = os.access(node, os.R_OK)
            writable = os.access(node, os.W_OK)
            devices.append({
                "device_node": node,
                "device_index": idx,
                "is_accessible": readable and writable,
            })
        return devices

    def is_camera_available(self) -> bool:
        """Verify device node accessibility without opening stream."""
        node = f"/dev/video{self.device_index}"
        return os.path.exists(node) and os.access(node, os.R_OK)

    def start(self) -> bool:
        """Start the background camera frame acquisition thread."""
        with self._lock:
            if self._is_running:
                return True

            if not self._open_device():
                return False

            self._is_running = True
            self._frame_event.clear()
            self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="MavenCameraWorker")
            self._thread.start()
            self._is_active = True
            return True

    def stop(self) -> None:
        """Stop frame acquisition and release hardware handle cleanly."""
        with self._lock:
            self._is_running = False
            self._is_active = False
            self._frame_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
            self._thread = None

        with self._lock:
            if self._cap:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None
            self._latest_frame = None

    def _open_device(self) -> bool:
        """Initialize OpenCV VideoCapture device."""
        try:
            # Force V4L2 backend for Linux stability
            cap = cv2.VideoCapture(self.device_index, cv2.CAP_V4L2)
            if not cap.isOpened():
                # Fallback to default backend
                cap = cv2.VideoCapture(self.device_index)

            if not cap.isOpened():
                self._last_error = f"Cannot open camera index {self.device_index}"
                return False

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
            cap.set(cv2.CAP_PROP_FPS, self.target_fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimal buffer for lowest latency

            self._cap = cap
            self._last_error = None
            return True
        except Exception as e:
            self._last_error = str(e)
            return False

    def _capture_loop(self) -> None:
        """Continuous frame polling with auto-reconnection."""
        while self._is_running:
            if not self._cap or not self._cap.isOpened():
                time.sleep(0.2)
                with self._lock:
                    if not self._is_running:
                        break
                    self._open_device()
                continue

            try:
                ret, frame = self._cap.read()
                if not ret or frame is None or frame.size == 0:
                    self._error_count += 1
                    time.sleep(0.03)
                    if self._error_count > 15:
                        # Reconnect
                        with self._lock:
                            if self._cap:
                                self._cap.release()
                                self._cap = None
                        self._reconnect_attempts += 1
                    continue

                self._error_count = 0
                now = time.time()

                with self._lock:
                    self._latest_frame = frame
                    self._latest_timestamp = now
                    self._frame_count += 1
                self._frame_event.set()

                # Calculate live actual FPS
                self._fps_counter += 1
                if now - self._last_fps_calc_time >= 1.0:
                    self._fps_actual = round(self._fps_counter / (now - self._last_fps_calc_time), 1)
                    self._fps_counter = 0
                    self._last_fps_calc_time = now

            except Exception as e:
                self._last_error = str(e)
                time.sleep(0.05)

    def read_frame(self, timeout_sec: float = 0.0) -> Tuple[bool, Optional[np.ndarray], float]:
        """
        Thread-safe retrieval of the most recent captured video frame.
        Supports optional bounded wait if initial hardware frame is still buffering.
        Returns: (success, frame_bgr, timestamp)
        """
        if timeout_sec > 0:
            with self._lock:
                needs_wait = self._is_running and self._latest_frame is None
            if needs_wait:
                self._frame_event.wait(timeout=timeout_sec)

        with self._lock:
            if not self._is_running or self._latest_frame is None:
                return False, None, 0.0
            return True, self._latest_frame.copy(), self._latest_timestamp

    def get_status(self) -> Dict[str, Any]:
        """Telemetry snapshot of camera hardware."""
        return {
            "device_index": self.device_index,
            "is_active": self._is_active,
            "is_running": self._is_running,
            "actual_fps": self._fps_actual,
            "target_fps": self.target_fps,
            "resolution": f"{self.target_width}x{self.target_height}",
            "frames_captured": self._frame_count,
            "reconnect_attempts": self._reconnect_attempts,
            "last_error": self._last_error,
        }
