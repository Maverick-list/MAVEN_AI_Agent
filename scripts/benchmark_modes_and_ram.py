#!/usr/bin/env python3
"""Comprehensive RAM, Process, and Mode Lifecycle Benchmark for Maven JARVIS."""

import json
import os
import subprocess
import time
import urllib.request
import psutil

PORT = 18766
BASE_URL = f"http://127.0.0.1:{PORT}"

def post_json(endpoint: str, data: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": BASE_URL},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))

def get_json(endpoint: str) -> dict:
    with urllib.request.urlopen(f"{BASE_URL}{endpoint}", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

def get_proc_metrics(pid: int) -> dict:
    try:
        proc = psutil.Process(pid)
        mem_info = proc.memory_info()
        mem_full = proc.memory_full_info() if hasattr(proc, "memory_full_info") else mem_info
        return {
            "pid": pid,
            "name": proc.name(),
            "rss_mb": round(mem_info.rss / (1024 * 1024), 2),
            "pss_mb": round(getattr(mem_full, "pss", mem_info.rss) / (1024 * 1024), 2),
            "vms_mb": round(mem_info.vms / (1024 * 1024), 2),
            "threads": proc.num_threads(),
            "fds": proc.num_fds() if hasattr(proc, "num_fds") else 0,
        }
    except Exception as exc:
        return {"error": str(exc), "pid": pid}

def get_openclaw_metrics() -> dict:
    # Find OpenClaw gateway processes on 18789
    pids = []
    try:
        out = subprocess.check_output(["lsof", "-ti:18789"]).decode().strip().split()
        pids = [int(p) for p in out if p]
    except Exception:
        pass
    
    total_rss = 0.0
    total_pss = 0.0
    workers = []
    for p in set(pids):
        m = get_proc_metrics(p)
        if "rss_mb" in m:
            total_rss += m["rss_mb"]
            total_pss += m["pss_mb"]
            workers.append(m)
    return {
        "pids": list(set(pids)),
        "total_rss_mb": round(total_rss, 2),
        "total_pss_mb": round(total_pss, 2),
        "workers": workers,
    }

def run_benchmark():
    # 1. Discover Dashboard Daemon PID
    out = subprocess.check_output(["lsof", "-ti:18766", "-sTCP:LISTEN"]).decode().strip().split()
    dashboard_pid = int(out[0])
    
    modes = ["normal", "voice", "vision", "full_assistant", "low_memory", "safe_idle", "normal"]
    results = {}
    
    for mode in modes:
        print(f"\n--- Testing Mode: {mode.upper()} ---")
        t0 = time.time()
        res = post_json("/api/system/mode", {"mode": mode})
        time.sleep(1.0) # Settle
        
        status = get_json("/api/status")
        profile = get_json("/api/system/memory-profile")
        dashboard_proc = get_proc_metrics(dashboard_pid)
        openclaw = get_openclaw_metrics()
        
        camera_active = False
        try:
            cam_info = status.get("vision", {}).get("engine", {}).get("camera", {})
            camera_active = bool(cam_info.get("is_running", False))
        except Exception:
            pass
        
        # Check for warm TTS worker
        tts_worker_proc = None
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmd = " ".join(p.info.get("cmdline") or [])
                if "pocket_tts" in cmd:
                    tts_worker_proc = get_proc_metrics(p.info["pid"])
                    break
            except Exception:
                pass
        
        snapshot = {
            "mode": mode,
            "switch_response": res,
            "transition_time_sec": round(time.time() - t0, 3),
            "active_mode_reported": status.get("mode", {}).get("active_mode"),
            "camera_active": camera_active,
            "dashboard_process": dashboard_proc,
            "tts_worker_process": tts_worker_proc,
            "openclaw_gateway": openclaw,
            "memory_profile_api": profile,
            "system_available_gb": status.get("system", {}).get("memory", {}).get("available_gb"),
        }
        results[mode] = snapshot
        print(f"Mode: {mode.upper()} | Dashboard RSS: {dashboard_proc.get('rss_mb')} MB | Threads: {dashboard_proc.get('threads')} | Camera: {camera_active}")

    # 2. Test TTS synthesis, idle auto-reclaim, and forced cleanup
    print("\n--- Testing Pocket-TTS Synthesis & Auto-Reclaim Lifecycle ---")
    voice_res = post_json("/api/voice/test", {"lang": "en", "browser_audio": True})
    print("Voice test status:", voice_res.get("status"), "Engine:", voice_res.get("engine"))
    time.sleep(1.0)
    
    tts_active_proc = None
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if "pocket_tts" in cmd:
                tts_active_proc = get_proc_metrics(p.info["pid"])
                break
        except Exception:
            pass
    print("TTS Worker Active RSS:", tts_active_proc.get("rss_mb") if tts_active_proc else "None")
    
    # Trigger memory cleanup
    print("Calling /api/system/memory-cleanup (force reclaim)...")
    cleanup_res = post_json("/api/system/memory-cleanup", {})
    time.sleep(1.0)
    
    tts_post_cleanup = None
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if "pocket_tts" in cmd:
                tts_post_cleanup = get_proc_metrics(p.info["pid"])
                break
        except Exception:
            pass
    print("TTS Worker Post-Cleanup:", "Still running (ERROR)" if tts_post_cleanup else "Successfully terminated (FREED)")
    
    post_cleanup_dash = get_proc_metrics(dashboard_pid)
    print(f"Dashboard RSS post-cleanup: {post_cleanup_dash.get('rss_mb')} MB")
    
    results["tts_lifecycle"] = {
        "voice_test_result": voice_res,
        "tts_active_metrics": tts_active_proc,
        "cleanup_result": cleanup_res,
        "tts_worker_terminated": bool(tts_post_cleanup is None),
        "dashboard_post_cleanup": post_cleanup_dash,
    }
    
    out_path = "docs/audit/maven_ram_benchmark_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nBenchmark completed successfully! Results written to {out_path}")

if __name__ == "__main__":
    run_benchmark()
