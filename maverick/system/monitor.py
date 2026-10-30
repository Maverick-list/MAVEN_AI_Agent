"""Maverick DevOS - Safe System Monitoring & Hardware Telemetry."""

import glob
import os
import platform
import shutil
import socket
import time
from typing import Any, Dict, List, Optional

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def _bytes_to_gb(b: int) -> float:
    """Convert bytes to Gigabytes rounded to 2 decimal places."""
    return round(b / (1024 ** 3), 2)


def _bytes_to_mb(b: int) -> float:
    """Convert bytes to Megabytes rounded to 2 decimal places."""
    return round(b / (1024 ** 2), 2)


def get_cpu_usage() -> Dict[str, Any]:
    """Retrieve CPU utilization percentage, core count, and load averages."""
    core_count = os.cpu_count() or 1
    try:
        load_1m, load_5m, load_15m = os.getloadavg()
    except (OSError, AttributeError):
        load_1m, load_5m, load_15m = 0.0, 0.0, 0.0

    cpu_pct = 0.0
    if _HAS_PSUTIL:
        try:
            cpu_pct = psutil.cpu_percent(interval=0.1)
        except Exception:
            cpu_pct = round((load_1m / core_count) * 100, 1)
    else:
        # Fallback approximation from 1-minute load average normalized by core count
        cpu_pct = round(min(100.0, (load_1m / core_count) * 100), 1)

    return {
        "usage_percent": cpu_pct,
        "cores_logical": core_count,
        "load_average": {
            "1m": round(load_1m, 2),
            "5m": round(load_5m, 2),
            "15m": round(load_15m, 2),
        },
    }


def get_memory_usage() -> Dict[str, Any]:
    """Retrieve system RAM and Swap usage in gigabytes and percentage."""
    if _HAS_PSUTIL:
        try:
            vm = psutil.virtual_memory()
            swap = psutil.swap_memory()
            return {
                "total_gb": _bytes_to_gb(vm.total),
                "used_gb": _bytes_to_gb(vm.used),
                "available_gb": _bytes_to_gb(vm.available),
                "percent": vm.percent,
                "swap_total_gb": _bytes_to_gb(swap.total),
                "swap_used_gb": _bytes_to_gb(swap.used),
                "swap_percent": swap.percent,
            }
        except Exception:
            pass

    # Procfs fallback from /proc/meminfo
    total_kb = 0
    avail_kb = 0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    avail_kb = int(line.split()[1])
        used_kb = max(0, total_kb - avail_kb)
        pct = round((used_kb / total_kb) * 100, 1) if total_kb > 0 else 0.0
        return {
            "total_gb": round(total_kb / (1024 ** 2), 2),
            "used_gb": round(used_kb / (1024 ** 2), 2),
            "available_gb": round(avail_kb / (1024 ** 2), 2),
            "percent": pct,
            "swap_total_gb": 0.0,
            "swap_used_gb": 0.0,
            "swap_percent": 0.0,
        }
    except Exception:
        return {
            "total_gb": 0.0,
            "used_gb": 0.0,
            "available_gb": 0.0,
            "percent": 0.0,
            "swap_total_gb": 0.0,
            "swap_used_gb": 0.0,
            "swap_percent": 0.0,
        }


def get_disk_usage() -> Dict[str, Any]:
    """Retrieve disk utilization for root filesystem and user home directory."""
    try:
        root_usage = shutil.disk_usage("/")
    except Exception:
        root_usage = shutil._ntuple_diskusage(1, 0, 1)

    home_dir = os.path.expanduser("~")
    try:
        home_usage = shutil.disk_usage(home_dir)
    except Exception:
        home_usage = shutil._ntuple_diskusage(1, 0, 1)

    root_total = _bytes_to_gb(root_usage.total)
    root_used = _bytes_to_gb(root_usage.used)
    root_free = _bytes_to_gb(root_usage.free)
    root_pct = round((root_usage.used / root_usage.total) * 100, 1) if root_usage.total > 0 else 0.0

    home_total = _bytes_to_gb(home_usage.total)
    home_used = _bytes_to_gb(home_usage.used)
    home_free = _bytes_to_gb(home_usage.free)
    home_pct = round((home_usage.used / home_usage.total) * 100, 1) if home_usage.total > 0 else 0.0

    return {
        "root": {
            "path": "/",
            "total_gb": root_total,
            "used_gb": root_used,
            "free_gb": root_free,
            "percent": root_pct,
        },
        "home": {
            "path": home_dir,
            "total_gb": home_total,
            "used_gb": home_used,
            "free_gb": home_free,
            "percent": home_pct,
        },
    }


def get_battery_status() -> Dict[str, Any]:
    """
    Retrieve battery percentage, charging state, and AC adapter connectivity.
    Handles battery-less desktop systems gracefully.
    """
    # 1. Check AC adapter status from sysfs
    ac_online = False
    for adp_path in glob.glob("/sys/class/power_supply/A*/online") + glob.glob("/sys/class/power_supply/ADP*/online"):
        try:
            with open(adp_path, "r", encoding="utf-8") as f:
                if f.read().strip() == "1":
                    ac_online = True
                    break
        except Exception:
            pass

    # 2. Check Battery status from sysfs (/sys/class/power_supply/BAT*)
    battery_nodes = glob.glob("/sys/class/power_supply/BAT*")
    if battery_nodes:
        bat_dir = battery_nodes[0]
        capacity = 0
        status = "Unknown"

        try:
            with open(os.path.join(bat_dir, "capacity"), "r", encoding="utf-8") as f:
                capacity = int(f.read().strip())
        except Exception:
            pass

        try:
            with open(os.path.join(bat_dir, "status"), "r", encoding="utf-8") as f:
                status = f.read().strip()
        except Exception:
            pass

        return {
            "has_battery": True,
            "percent": capacity,
            "status": status,
            "is_charging": status.lower() in ("charging", "full") or ac_online,
            "ac_connected": ac_online,
        }

    # Psutil fallback if sysfs /sys/class/power_supply is restricted
    if _HAS_PSUTIL:
        try:
            bat = psutil.sensors_battery()
            if bat:
                return {
                    "has_battery": True,
                    "percent": round(bat.percent, 1),
                    "status": "Charging" if bat.power_plugged else "Discharging",
                    "is_charging": bool(bat.power_plugged),
                    "ac_connected": bool(bat.power_plugged),
                }
        except Exception:
            pass

    # Desktop workstation with AC power only
    return {
        "has_battery": False,
        "percent": 100,
        "status": "AC_Connected",
        "is_charging": True,
        "ac_connected": ac_online if ac_online else True,
    }


def get_os_session_info() -> Dict[str, Any]:
    """Retrieve operating system distribution, kernel version, and desktop session."""
    os_name = "Linux"
    os_version = ""

    # Read /etc/os-release
    if os.path.isfile("/etc/os-release"):
        try:
            with open("/etc/os-release", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        os_name = line.split("=", 1)[1].strip().strip('"')
                    elif line.startswith("VERSION_ID="):
                        os_version = line.split("=", 1)[1].strip().strip('"')
        except Exception:
            pass

    uname = platform.uname()
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", os.environ.get("DESKTOP_SESSION", "GNOME"))
    session_type = os.environ.get("XDG_SESSION_TYPE", "wayland")
    hostname = socket.gethostname()

    # System uptime
    uptime_seconds = 0
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            uptime_seconds = int(float(f.read().split()[0]))
    except Exception:
        pass

    uptime_hours = round(uptime_seconds / 3600, 1)

    return {
        "os": os_name,
        "version_id": os_version,
        "kernel": f"{uname.system} {uname.release}",
        "architecture": uname.machine,
        "desktop": desktop,
        "session_type": session_type,
        "hostname": hostname,
        "uptime_hours": uptime_hours,
    }


def get_network_status() -> Dict[str, Any]:
    """Check connectivity and list active network interfaces."""
    interfaces: List[Dict[str, Any]] = []
    has_active_connection = False

    # Check network interfaces via sysfs
    for iface_path in glob.glob("/sys/class/net/*"):
        iface_name = os.path.basename(iface_path)
        if iface_name == "lo":
            continue

        operstate = "unknown"
        oper_file = os.path.join(iface_path, "operstate")
        if os.path.isfile(oper_file):
            try:
                with open(oper_file, "r", encoding="utf-8") as f:
                    operstate = f.read().strip()
            except Exception:
                pass

        is_up = (operstate == "up")
        if is_up:
            has_active_connection = True

        interfaces.append({
            "interface": iface_name,
            "status": operstate,
            "is_up": is_up,
        })

    return {
        "connected": has_active_connection,
        "interfaces": interfaces,
    }


def get_system_resources() -> Dict[str, Any]:
    """Consolidated resource telemetry (CPU, RAM, Disk)."""
    return {
        "cpu": get_cpu_usage(),
        "memory": get_memory_usage(),
        "disk": get_disk_usage(),
    }


def get_system_summary() -> Dict[str, Any]:
    """Comprehensive system status report combining resources, battery, OS, and network."""
    return {
        "os_session": get_os_session_info(),
        "resources": get_system_resources(),
        "battery": get_battery_status(),
        "network": get_network_status(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
