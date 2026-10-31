#!/usr/bin/env python3
"""Independent Physical Memory Verification for Maven JARVIS across all 6 modes."""

import json
import os
import subprocess
import time
import urllib.request
import psutil

PORT = 18766
BASE_URL = f"http://127.0.0.1:{PORT}"

def get_proc_smaps_and_status(pid: int) -> dict:
    """Read kernel /proc/[pid]/smaps_rollup and /proc/[pid]/status for precise metrics."""
    res = {
        "pid": pid,
        "rss_mb": 0.0,
        "pss_mb": 0.0,
        "uss_mb": 0.0,
        "vmsize_mb": 0.0,
        "vmpeak_mb": 0.0,
        "vmhwm_mb": 0.0,
        "threads": 0,
        "fds": 0,
    }
    try:
        proc = psutil.Process(pid)
        res["threads"] = proc.num_threads()
        res["fds"] = proc.num_fds() if hasattr(proc, "num_fds") else 0
        res["name"] = proc.name()
    except Exception:
        pass

    # Read /proc/[pid]/status
    status_path = f"/proc/{pid}/status"
    if os.path.isfile(status_path):
        try:
            with open(status_path, "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        k, v = parts[0].strip(), parts[1].strip()
                        if k == "VmSize":
                            res["vmsize_mb"] = round(float(v.split()[0]) / 1024.0, 2)
                        elif k == "VmPeak":
                            res["vmpeak_mb"] = round(float(v.split()[0]) / 1024.0, 2)
                        elif k == "VmHWM":
                            res["vmhwm_mb"] = round(float(v.split()[0]) / 1024.0, 2)
                        elif k == "VmRSS":
                            res["rss_mb"] = round(float(v.split()[0]) / 1024.0, 2)
        except Exception:
            pass

    # Read /proc/[pid]/smaps_rollup for accurate PSS and USS
    smaps_path = f"/proc/{pid}/smaps_rollup"
    if os.path.isfile(smaps_path):
        try:
            private_clean = 0.0
            private_dirty = 0.0
            with open(smaps_path, "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        k, v = parts[0].strip(), parts[1].strip()
                        if k == "Rss":
                            res["rss_mb"] = round(float(v.split()[0]) / 1024.0, 2)
                        elif k == "Pss":
                            res["pss_mb"] = round(float(v.split()[0]) / 1024.0, 2)
                        elif k == "Private_Clean":
                            private_clean = float(v.split()[0]) / 1024.0
                        elif k == "Private_Dirty":
                            private_dirty = float(v.split()[0]) / 1024.0
            res["uss_mb"] = round(private_clean + private_dirty, 2)
        except Exception:
            pass

    return res

def post_json(endpoint: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": BASE_URL},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get_system_ram() -> dict:
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return {
        "total_mb": round(vm.total / (1024 * 1024), 2),
        "available_mb": round(vm.available / (1024 * 1024), 2),
        "used_mb": round(vm.used / (1024 * 1024), 2),
        "percent": vm.percent,
        "swap_total_mb": round(sw.total / (1024 * 1024), 2),
        "swap_used_mb": round(sw.used / (1024 * 1024), 2),
        "swap_percent": sw.percent,
    }

def main():
    # Identify listening dashboard PID
    out = subprocess.check_output(["lsof", "-ti:18766", "-sTCP:LISTEN"]).decode().strip().split()
    dash_pid = int(out[0])

    modes = ["normal", "voice", "vision", "full_assistant", "low_memory", "safe_idle", "normal"]
    results = {}

    print(f"Independent Physical Memory Verification starting...")
    print(f"Target Dashboard Server PID: {dash_pid}")

    for mode in modes:
        print(f"\nEvaluating mode: {mode.upper()}...")
        switch_res = post_json("/api/system/mode", {"mode": mode})
        time.sleep(1.2)  # Allow hardware/models to settle

        dash_mem = get_proc_smaps_and_status(dash_pid)
        sys_ram = get_system_ram()

        # Check if camera is active
        cam_running = False
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/status", timeout=5) as r:
                snap = json.loads(r.read().decode("utf-8"))
                cam_running = snap.get("vision", {}).get("engine", {}).get("camera", {}).get("is_running", False)
        except Exception:
            pass

        record = {
            "mode": mode,
            "switch_status": switch_res.get("status"),
            "switch_actions": switch_res.get("actions", []),
            "camera_hardware_active": cam_running,
            "dashboard_metrics": dash_mem,
            "system_ram": sys_ram,
        }
        results[mode] = record
        print(f"  Mode: {mode.upper()} | RSS: {dash_mem['rss_mb']} MB | PSS: {dash_mem['pss_mb']} MB | USS: {dash_mem['uss_mb']} MB | VmPeak: {dash_mem['vmpeak_mb']} MB | Threads: {dash_mem['threads']} | Camera: {cam_running}")

    out_file = "docs/audit/verified_physical_memory_by_mode.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nVerification complete. Results saved to {out_file}")

if __name__ == "__main__":
    main()
