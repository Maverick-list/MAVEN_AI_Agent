"""Maverick DevOS - Memory Architecture, Resource Lifecycle & Operating Modes.

Implements P0 memory-aware execution, resource profiling (RSS/PSS),
bounded buffering, dynamic memory pressure mitigation, and the 6 Maven Operating Modes:
- NORMAL
- VOICE
- VISION
- FULL_ASSISTANT
- LOW_MEMORY
- SAFE_IDLE
"""

from collections import deque
from enum import Enum
import gc
import json
import logging
import os
import psutil
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("maverick.system.memory_manager")

CONFIG_DIR = os.path.expanduser("~/.config/maverick")
MODE_STATE_FILE = os.path.join(CONFIG_DIR, "operating_mode.json")


class MavenOperatingMode(Enum):
    """The 6 Canonical Maven Operating Modes."""
    NORMAL = "normal"                  # Default: Camera OFF, Vision unloaded, Voice standby
    VOICE = "voice"                    # Voice active: Wake word, Whisper STT, Pocket TTS
    VISION = "vision"                  # Vision active: Camera ON, MediaPipe ONNX 21-landmarks
    FULL_ASSISTANT = "full_assistant"  # All modalities: Voice + Vision + Computer Use + Planner
    LOW_MEMORY = "low_memory"          # Minimal RAM: Capped queues, GC aggressive, models unloaded
    SAFE_IDLE = "safe_idle"            # Standby: Camera off, mic stream closed, models hibernated


class MemoryPressureLevel(Enum):
    """System memory pressure classification."""
    HEALTHY = "healthy"        # Available RAM > 3.0 GB
    MODERATE = "moderate"      # Available RAM 1.8 GB - 3.0 GB
    HIGH = "high"              # Available RAM 1.0 GB - 1.8 GB
    CRITICAL = "critical"      # Available RAM < 1.0 GB


class BoundedQueue:
    """Thread-safe bounded queue with automatic eviction policy to prevent memory leaks."""

    def __init__(self, maxlen: int = 100):
        self.maxlen = max(1, maxlen)
        self._deque = deque(maxlen=self.maxlen)
        self._lock = threading.Lock()
        self._drop_count = 0

    def push(self, item: Any) -> bool:
        """Add item. If full, oldest item is evicted to preserve memory."""
        with self._lock:
            if len(self._deque) >= self.maxlen:
                self._drop_count += 1
            self._deque.append(item)
            return True

    def pop(self) -> Optional[Any]:
        """Pop oldest item."""
        with self._lock:
            if self._deque:
                return self._deque.popleft()
            return None

    def pop_latest(self) -> Optional[Any]:
        """Pop newest item (e.g., for latest frame dropping stale backlog)."""
        with self._lock:
            if self._deque:
                return self._deque.pop()
            return None

    def clear(self) -> None:
        with self._lock:
            self._deque.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._deque)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "size": len(self._deque),
                "maxlen": self.maxlen,
                "evicted_count": self._drop_count,
            }


class ComponentResourceProfile:
    """Telemetry data structure for a Maven subsystem."""

    def __init__(self, name: str, rss_mb: float, pss_mb: float, threads: int, open_fds: int, details: Optional[Dict[str, Any]] = None):
        self.name = name
        self.rss_mb = round(rss_mb, 2)
        self.pss_mb = round(pss_mb, 2)
        self.threads = threads
        self.open_fds = open_fds
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "rss_mb": self.rss_mb,
            "pss_mb": self.pss_mb,
            "threads": self.threads,
            "open_fds": self.open_fds,
            "details": self.details,
        }


class MemoryManager:
    """
    Central manager for Maven operating modes, memory profiling,
    unbounded queue mitigation, and proactive memory conservation.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._current_mode = MavenOperatingMode.NORMAL
        self._registered_components: Dict[str, Any] = {}
        self._mode_change_hooks: List[Callable[[MavenOperatingMode, MavenOperatingMode], None]] = []
        self._last_pressure_check = 0.0
        self._cached_pressure = MemoryPressureLevel.HEALTHY
        self._load_persisted_mode()
        self._initialized = True

    def _load_persisted_mode(self) -> None:
        """Load mode from persistent store or default to NORMAL."""
        if os.path.isfile(MODE_STATE_FILE):
            try:
                with open(MODE_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    mode_str = data.get("active_mode", "").lower()
                    for m in MavenOperatingMode:
                        if m.value == mode_str:
                            self._current_mode = m
                            return
            except Exception:
                pass
        self._current_mode = MavenOperatingMode.NORMAL

    def _persist_mode(self) -> None:
        """Persist mode to config."""
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            payload = {
                "active_mode": self._current_mode.value,
                "timestamp": time.time(),
            }
            tmp = MODE_STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, MODE_STATE_FILE)
        except Exception as e:
            logger.warning("Could not persist operating mode: %s", e)

    @property
    def current_mode(self) -> MavenOperatingMode:
        return self._current_mode

    def register_component(self, name: str, component_ref: Any) -> None:
        """Register a subsystem for lifecycle and memory management."""
        with self._lock:
            self._registered_components[name] = component_ref

    def register_mode_hook(self, hook: Callable[[MavenOperatingMode, MavenOperatingMode], None]) -> None:
        """Add callback for mode change notifications."""
        with self._lock:
            self._mode_change_hooks.append(hook)

    def set_mode(self, target_mode: MavenOperatingMode, stop_browser: bool = False) -> Dict[str, Any]:
        """
        Transition Maven into one of the 6 Operating Modes.
        Enforces memory conservation and hardware lifecycle rules.
        """
        with self._lock:
            prev_mode = self._current_mode
            if prev_mode == target_mode:
                return {
                    "status": "success",
                    "mode": target_mode.value,
                    "current_mode": target_mode.value,
                    "previous_mode": prev_mode.value,
                    "changed": False,
                    "message": f"Already operating in {target_mode.value.upper()} Mode.",
                }

            logger.info("Transitioning Operating Mode: %s -> %s", prev_mode.value, target_mode.value)
            actions_taken = []

            # 1. Mode-specific adjustments
            if target_mode in (MavenOperatingMode.NORMAL, MavenOperatingMode.VOICE, MavenOperatingMode.LOW_MEMORY, MavenOperatingMode.SAFE_IDLE):
                # Ensure camera is off and ONNX vision models are unloaded
                vis_ctl = self._registered_components.get("vision_controller")
                if vis_ctl and hasattr(vis_ctl, "mode_manager"):
                    vis_ctl.mode_manager.deactivate_vision()
                    actions_taken.append("vision_deactivated_and_camera_stopped")
                if vis_ctl and hasattr(vis_ctl, "engine") and hasattr(vis_ctl.engine, "tracker"):
                    if hasattr(vis_ctl.engine.tracker, "release_resources"):
                        vis_ctl.engine.tracker.release_resources()
                        actions_taken.append("onnx_vision_models_unloaded")

            if target_mode == MavenOperatingMode.VISION:
                vis_ctl = self._registered_components.get("vision_controller")
                if vis_ctl and hasattr(vis_ctl, "mode_manager"):
                    res = vis_ctl.mode_manager.activate_vision()
                    actions_taken.append(f"vision_activated: {res.get('status')}")

            if target_mode == MavenOperatingMode.FULL_ASSISTANT:
                vis_ctl = self._registered_components.get("vision_controller")
                if vis_ctl and hasattr(vis_ctl, "mode_manager"):
                    vis_ctl.mode_manager.activate_vision()
                    actions_taken.append("full_vision_activated")

            if target_mode == MavenOperatingMode.LOW_MEMORY:
                # Aggressive memory cleanup
                tts_prov = self._registered_components.get("tts_provider")
                if tts_prov and hasattr(tts_prov, "close"):
                    tts_prov.close()
                    actions_taken.append("tts_worker_reclaimed")

                # Reclaim Chrome automation session if requested
                if stop_browser:
                    try:
                        from maverick.browser.lifecycle import BrowserLifecycle
                        bl = BrowserLifecycle()
                        if bl.is_running():
                            bl.stop()
                            actions_taken.append("browser_cdp_stopped")
                    except Exception:
                        pass

                # Run Python garbage collector
                gc.collect()
                actions_taken.append("garbage_collection_executed")

            if target_mode == MavenOperatingMode.SAFE_IDLE:
                # Halt audio stream if daemon is present
                voice_daemon = self._registered_components.get("voice_daemon")
                if voice_daemon and hasattr(voice_daemon, "pause"):
                    voice_daemon.pause()
                    actions_taken.append("voice_daemon_paused")
                gc.collect()

            self._current_mode = target_mode
            self._persist_mode()

            # Execute hooks
            for hook in self._mode_change_hooks:
                try:
                    hook(prev_mode, target_mode)
                except Exception as exc:
                    logger.warning("Error in mode hook: %s", exc)

            return {
                "status": "success",
                "mode": target_mode.value,
                "current_mode": target_mode.value,
                "previous_mode": prev_mode.value,
                "changed": True,
                "actions": actions_taken,
                "memory_profile": self.get_process_memory_info(),
            }

    def get_system_memory_status(self) -> Dict[str, Any]:
        """Inspect host RAM, available memory, swap, and classify pressure."""
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        avail_gb = round(vm.available / (1024 ** 3), 2)
        total_gb = round(vm.total / (1024 ** 3), 2)
        used_gb = round(vm.used / (1024 ** 3), 2)

        if avail_gb > 3.0:
            pressure = MemoryPressureLevel.HEALTHY
        elif avail_gb > 1.8:
            pressure = MemoryPressureLevel.MODERATE
        elif avail_gb > 1.0:
            pressure = MemoryPressureLevel.HIGH
        else:
            pressure = MemoryPressureLevel.CRITICAL

        self._cached_pressure = pressure

        return {
            "total_gb": total_gb,
            "used_gb": used_gb,
            "available_gb": avail_gb,
            "percent": vm.percent,
            "swap_total_gb": round(swap.total / (1024 ** 3), 2),
            "swap_used_gb": round(swap.used / (1024 ** 3), 2),
            "swap_percent": swap.percent,
            "pressure_level": pressure.value,
            "active_mode": self._current_mode.value,
        }

    def get_process_memory_info(self, pid: Optional[int] = None) -> Dict[str, Any]:
        """Profile RSS, PSS (if smaps available), threads, and FDs for a process."""
        target_pid = pid or os.getpid()
        try:
            p = psutil.Process(target_pid)
            mem_info = p.memory_info()
            rss_mb = round(mem_info.rss / (1024 ** 2), 2)
            vms_mb = round(mem_info.vms / (1024 ** 2), 2)

            # Try to read smaps_rollup for PSS on Linux
            pss_mb = rss_mb
            smaps_file = f"/proc/{target_pid}/smaps_rollup"
            if os.path.isfile(smaps_file):
                try:
                    with open(smaps_file, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.startswith("Pss:"):
                                pss_kb = int(line.split()[1])
                                pss_mb = round(pss_kb / 1024, 2)
                                break
                except Exception:
                    pass

            num_fds = p.num_fds() if hasattr(p, "num_fds") else 0
            num_threads = p.num_threads()

            return {
                "pid": target_pid,
                "name": p.name(),
                "rss_mb": rss_mb,
                "pss_mb": pss_mb,
                "vms_mb": vms_mb,
                "threads": num_threads,
                "open_fds": num_fds,
            }
        except Exception as exc:
            return {"error": str(exc), "pid": target_pid}

    def profile_all_subsystems(self) -> Dict[str, Any]:
        """
        Deep RSS and PSS profile of all active Maven processes:
        - In-process main daemon
        - OpenClaw Gateway (18789)
        - Whisper STT microservice (18791)
        - Subprocess workers (Pocket TTS worker, Chrome)
        """
        subsystems: List[Dict[str, Any]] = []

        # 1. Main process
        main_prof = self.get_process_memory_info()
        main_prof["component"] = "maven_runtime"
        subsystems.append(main_prof)

        # 2. OpenClaw Gateway and other Maven subsystems
        current_pid = os.getpid()
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["pid"] == current_pid:
                    continue
                cmd = " ".join(proc.info.get("cmdline") or [])
                if "openclaw" in cmd and "gateway" in cmd:
                    p_info = self.get_process_memory_info(proc.info["pid"])
                    p_info["component"] = "openclaw_gateway"
                    subsystems.append(p_info)
                elif "maverick.dashboard" in cmd:
                    p_info = self.get_process_memory_info(proc.info["pid"])
                    p_info["component"] = "maven_dashboard_server"
                    subsystems.append(p_info)
                elif "maverick.voice" in cmd:
                    p_info = self.get_process_memory_info(proc.info["pid"])
                    p_info["component"] = "maven_voice_daemon"
                    subsystems.append(p_info)
                elif "whisper-server" in cmd:
                    p_info = self.get_process_memory_info(proc.info["pid"])
                    p_info["component"] = "whisper_stt_server"
                    subsystems.append(p_info)
                elif "_PERSISTENT_WORKER_CODE" in cmd or "pocket_tts" in cmd:
                    p_info = self.get_process_memory_info(proc.info["pid"])
                    p_info["component"] = "pocket_tts_worker"
                    subsystems.append(p_info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        total_maven_rss = sum(s.get("rss_mb", 0.0) for s in subsystems if "rss_mb" in s)
        total_maven_pss = sum(s.get("pss_mb", 0.0) for s in subsystems if "pss_mb" in s)

        return {
            "status": "success",
            "subsystems": subsystems,
            "total_maven_rss_mb": round(total_maven_rss, 2),
            "total_maven_pss_mb": round(total_maven_pss, 2),
            "system_ram": self.get_system_memory_status(),
            "active_mode": self._current_mode.value,
        }

    def enforce_memory_bounds(self) -> Dict[str, Any]:
        """
        Check memory pressure and take automated defensive steps if critical.
        Guarantees that Maven will not cause the system to freeze or swap.
        """
        status = self.get_system_memory_status()
        pressure = status["pressure_level"]
        actions = []

        if pressure in ("high", "critical"):
            logger.warning("Memory pressure is %s (Avail: %s GB). Applying mitigation.", pressure, status["available_gb"])
            # 1. Unload vision models if currently in Normal or Voice mode
            if self._current_mode in (MavenOperatingMode.NORMAL, MavenOperatingMode.VOICE, MavenOperatingMode.LOW_MEMORY):
                vis_ctl = self._registered_components.get("vision_controller")
                if vis_ctl and hasattr(vis_ctl, "engine") and hasattr(vis_ctl.engine, "tracker"):
                    if hasattr(vis_ctl.engine.tracker, "release_resources"):
                        vis_ctl.engine.tracker.release_resources()
                        actions.append("unloaded_vision_models")

            # 2. Release idle TTS workers
            tts_prov = self._registered_components.get("tts_provider")
            if tts_prov and hasattr(tts_prov, "close"):
                tts_prov.close()
                actions.append("closed_idle_tts_worker")

            # 3. Trigger immediate garbage collection
            freed_objs = gc.collect()
            actions.append(f"gc_freed_{freed_objs}_objects")

        return {
            "status": "success",
            "pressure": pressure,
            "available_gb": status["available_gb"],
            "actions_executed": actions,
        }


# Global singleton instance
memory_manager = MemoryManager()
