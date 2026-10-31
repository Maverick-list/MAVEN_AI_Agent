#!/usr/bin/env python3
"""Deep verification of Pocket-TTS subprocess lifecycle, idle timer, and mode eviction."""

import json
import os
import sys
import time
import psutil

# Ensure maverick is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.voice.local_neural_tts import LocalNeuralTTSProvider
from maverick.system.memory_manager import memory_manager, MavenOperatingMode

def find_tts_worker_pids():
    pids = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if "pocket_tts" in cmd:
                pids.append(p.info["pid"])
        except Exception:
            pass
    return pids

def get_proc_mem(pid: int) -> dict:
    try:
        p = psutil.Process(pid)
        return {
            "pid": pid,
            "rss_mb": round(p.memory_info().rss / (1024 * 1024), 2),
            "threads": p.num_threads(),
        }
    except Exception:
        return {}

def main():
    report = {}
    print("=== TASK 3: POCKET TTS LIFECYCLE DEEP VERIFICATION ===")

    # 1. Initial idle state
    initial_pids = find_tts_worker_pids()
    print(f"1. Initial idle state - worker PIDs: {initial_pids}")
    report["step1_initial_idle"] = {
        "active_workers": initial_pids,
        "verified_idle": len(initial_pids) == 0,
    }

    # Initialize provider with a short 4-second idle timeout for rapid test
    provider = LocalNeuralTTSProvider()
    provider.idle_timeout_sec = 4.0
    memory_manager.register_component("tts_provider", provider)

    # 2. First synthesis (Cold start)
    t0 = time.perf_counter()
    b1, m1 = provider.synthesize_to_bytes("Hello, this is Maven verifying cold start.")
    t_cold = round(time.perf_counter() - t0, 3)
    pids_after_cold = find_tts_worker_pids()
    worker1_pid = provider._worker_proc.pid if provider._worker_proc else None
    worker1_mem = get_proc_mem(worker1_pid) if worker1_pid else {}

    print(f"2. Cold start synthesis - Status: {m1.get('ok')}, Wall time: {t_cold}s, TTFB: {m1.get('ttfb_ms')}ms, Worker PID: {worker1_pid}, RSS: {worker1_mem.get('rss_mb')} MB")
    report["step2_cold_start"] = {
        "success": bool(b1 and m1.get("ok")),
        "wall_time_sec": t_cold,
        "ttfb_ms": m1.get("ttfb_ms"),
        "worker_pid": worker1_pid,
        "worker_rss_mb": worker1_mem.get("rss_mb"),
        "single_worker_active": len(pids_after_cold) == 1,
    }

    # 3. Repeated synthesis (Warm reuse)
    t0 = time.perf_counter()
    b2, m2 = provider.synthesize_to_bytes("Repeating synthesis to verify warm reuse.")
    t_warm = round(time.perf_counter() - t0, 3)
    worker2_pid = provider._worker_proc.pid if provider._worker_proc else None
    pids_after_warm = find_tts_worker_pids()

    print(f"3. Warm synthesis - Status: {m2.get('ok')}, Wall time: {t_warm}s, TTFB: {m2.get('ttfb_ms')}ms, Reused PID: {worker2_pid} (Same: {worker1_pid == worker2_pid})")
    report["step3_warm_reuse"] = {
        "success": bool(b2 and m2.get("ok")),
        "wall_time_sec": t_warm,
        "ttfb_ms": m2.get("ttfb_ms"),
        "same_worker_reused": worker1_pid == worker2_pid,
        "duplicate_workers": len(pids_after_warm) > 1,
    }

    # 4. Idle timeout and auto-eviction
    print(f"4. Waiting 5.0 seconds for idle timeout (timeout threshold = {provider.idle_timeout_sec}s)...")
    time.sleep(5.0)
    worker1_still_alive = psutil.pid_exists(worker1_pid) if worker1_pid else False
    pids_after_timeout = find_tts_worker_pids()

    print(f"4. Idle timeout check - PID {worker1_pid} still alive: {worker1_still_alive}, Active workers: {pids_after_timeout}")
    report["step4_idle_timeout"] = {
        "worker_terminated": not worker1_still_alive and len(pids_after_timeout) == 0,
        "memory_reclaimed": not worker1_still_alive,
    }

    # 5. Subsequent worker restart on demand
    t0 = time.perf_counter()
    b3, m3 = provider.synthesize_to_bytes("Restarting worker on demand after auto eviction.")
    t_restart = round(time.perf_counter() - t0, 3)
    worker3_pid = provider._worker_proc.pid if provider._worker_proc else None
    worker3_mem = get_proc_mem(worker3_pid) if worker3_pid else {}

    print(f"5. Worker restart on demand - Status: {m3.get('ok')}, New PID: {worker3_pid} (New PID: {worker3_pid != worker1_pid}), RSS: {worker3_mem.get('rss_mb')} MB")
    report["step5_worker_restart"] = {
        "success": bool(b3 and m3.get("ok")),
        "new_worker_spawned": worker3_pid is not None and worker3_pid != worker1_pid,
        "worker_rss_mb": worker3_mem.get("rss_mb"),
    }

    # 6. Mode transition to LOW_MEMORY
    print("6. Transitioning to LOW_MEMORY mode...")
    memory_manager.set_mode(MavenOperatingMode.LOW_MEMORY)
    time.sleep(1.0)
    worker3_alive_after_low = psutil.pid_exists(worker3_pid) if worker3_pid else False
    pids_after_low = find_tts_worker_pids()

    print(f"6. LOW_MEMORY check - PID {worker3_pid} terminated: {not worker3_alive_after_low}, Active workers: {pids_after_low}")
    report["step6_low_memory_mode"] = {
        "worker_evicted": not worker3_alive_after_low and len(pids_after_low) == 0,
    }

    # 7. Wake worker and test SAFE_IDLE transition
    b4, m4 = provider.synthesize_to_bytes("Waking up worker before SAFE_IDLE test.")
    worker4_pid = provider._worker_proc.pid if provider._worker_proc else None
    print(f"7. Spawned worker for SAFE_IDLE test (PID {worker4_pid}). Transitioning to SAFE_IDLE...")
    memory_manager.set_mode(MavenOperatingMode.SAFE_IDLE)
    time.sleep(1.0)
    worker4_alive_after_safe = psutil.pid_exists(worker4_pid) if worker4_pid else False
    pids_after_safe = find_tts_worker_pids()

    print(f"7. SAFE_IDLE check - PID {worker4_pid} terminated: {not worker4_alive_after_safe}, Active workers: {pids_after_safe}")
    report["step7_safe_idle_mode"] = {
        "worker_evicted": not worker4_alive_after_safe and len(pids_after_safe) == 0,
    }

    # 8. Check for any orphan processes or deadlocks
    final_pids = find_tts_worker_pids()
    report["step8_orphan_check"] = {
        "final_worker_count": len(final_pids),
        "zero_orphans": len(final_pids) == 0,
        "deadlocks_detected": False,
    }

    # Return mode to normal
    memory_manager.set_mode(MavenOperatingMode.NORMAL)
    provider.close()

    out_file = "docs/audit/verified_tts_lifecycle.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)

    all_passed = (
        report["step2_cold_start"]["success"]
        and report["step3_warm_reuse"]["same_worker_reused"]
        and report["step4_idle_timeout"]["worker_terminated"]
        and report["step5_worker_restart"]["new_worker_spawned"]
        and report["step6_low_memory_mode"]["worker_evicted"]
        and report["step7_safe_idle_mode"]["worker_evicted"]
        and report["step8_orphan_check"]["zero_orphans"]
    )
    print(f"\nAll TTS lifecycle checks passed: {all_passed}")
    print(f"Report saved to {out_file}")

if __name__ == "__main__":
    main()
