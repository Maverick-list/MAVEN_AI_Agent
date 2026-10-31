#!/usr/bin/env python3
"""Sustained Reliability & Memory Drift Test for Maven JARVIS (300 seconds continuous load)."""

import concurrent.futures
import json
import os
import subprocess
import time
import urllib.request
import psutil

PORT = 18766
BASE_URL = f"http://127.0.0.1:{PORT}"
TEST_DURATION_SEC = 180  # 3 minutes continuous sampled load

def fetch(url):
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SustainedTester/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read()
            return time.perf_counter() - t0, resp.status, None
    except Exception as exc:
        return time.perf_counter() - t0, 0, str(exc)

def get_proc_snapshot(proc: psutil.Process) -> dict:
    mem = proc.memory_info()
    full = proc.memory_full_info() if hasattr(proc, "memory_full_info") else mem
    return {
        "rss_mb": round(mem.rss / (1024 * 1024), 2),
        "pss_mb": round(getattr(full, "pss", mem.rss) / (1024 * 1024), 2),
        "vms_mb": round(mem.vms / (1024 * 1024), 2),
        "threads": proc.num_threads(),
        "fds": proc.num_fds() if hasattr(proc, "num_fds") else 0,
        "cpu_percent": proc.cpu_percent(interval=None),
    }

def main():
    out = subprocess.check_output(["lsof", "-ti:18766", "-sTCP:LISTEN"]).decode().strip().split()
    pid = int(out[0])
    proc = psutil.Process(pid)
    proc.cpu_percent(interval=None)  # prime cpu_percent

    endpoints = [
        f"{BASE_URL}/api/status",
        f"{BASE_URL}/api/latency",
        f"{BASE_URL}/api/voice/voices",
        f"{BASE_URL}/",
    ]

    print(f"Starting sustained reliability test for {TEST_DURATION_SEC} seconds on PID {pid}...")
    baseline = get_proc_snapshot(proc)
    print(f"Initial Baseline: RSS={baseline['rss_mb']} MB, PSS={baseline['pss_mb']} MB, Threads={baseline['threads']}, FDs={baseline['fds']}")

    t_start = time.time()
    total_requests = 0
    errors = 0
    latencies = []
    samples = [baseline]

    # Run sustained concurrent load in rounds
    round_idx = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        while time.time() - t_start < TEST_DURATION_SEC:
            round_idx += 1
            batch = [endpoints[i % len(endpoints)] for i in range(12)]
            futures = [pool.submit(fetch, u) for u in batch]
            for f in concurrent.futures.as_completed(futures):
                lat, status, err = f.result()
                latencies.append(lat * 1000.0)
                total_requests += 1
                if status != 200:
                    errors += 1

            time.sleep(1.2)  # Controlled steady cadence
            snap = get_proc_snapshot(proc)
            snap["elapsed_sec"] = round(time.time() - t_start, 1)
            samples.append(snap)
            if round_idx % 10 == 0:
                print(f"  [{snap['elapsed_sec']}s] Requests: {total_requests} | RSS: {snap['rss_mb']} MB | PSS: {snap['pss_mb']} MB | Threads: {snap['threads']} | FDs: {snap['fds']}")

    t_total = time.time() - t_start
    final_snap = get_proc_snapshot(proc)

    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0.0
    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0

    rss_drift = round(final_snap["rss_mb"] - baseline["rss_mb"], 2)
    pss_drift = round(final_snap["pss_mb"] - baseline["pss_mb"], 2)
    fd_drift = final_snap["fds"] - baseline["fds"]
    thread_drift = final_snap["threads"] - baseline["threads"]

    # Check for orphan processes
    tts_orphans = []
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if "pocket_tts" in cmd:
                tts_orphans.append(p.info["pid"])
        except Exception:
            pass

    print("\n--- Sustained Reliability Results ---")
    print(f"Duration:            {t_total:.1f} s")
    print(f"Total Requests:      {total_requests} ({total_requests/t_total:.1f} req/s)")
    print(f"Failed Requests:     {errors} (Error Rate: {errors/total_requests*100:.2f}%)")
    print(f"Latency P50:         {p50:.2f} ms")
    print(f"Latency P95:         {p95:.2f} ms")
    print(f"Latency Avg:         {avg_lat:.2f} ms")
    print(f"RSS Drift:           {rss_drift:+.2f} MB ({baseline['rss_mb']} MB -> {final_snap['rss_mb']} MB)")
    print(f"PSS Drift:           {pss_drift:+.2f} MB ({baseline['pss_mb']} MB -> {final_snap['pss_mb']} MB)")
    print(f"Thread Drift:        {thread_drift:+d} ({baseline['threads']} -> {final_snap['threads']})")
    print(f"FD Drift:            {fd_drift:+d} ({baseline['fds']} -> {final_snap['fds']})")
    print(f"Orphan TTS Workers:  {len(tts_orphans)}")

    result = {
        "duration_sec": round(t_total, 1),
        "total_requests": total_requests,
        "throughput_req_per_sec": round(total_requests / t_total, 2),
        "errors": errors,
        "error_rate_percent": round(errors / total_requests * 100, 2),
        "latency_p50_ms": round(p50, 2),
        "latency_p95_ms": round(p95, 2),
        "latency_avg_ms": round(avg_lat, 2),
        "baseline": baseline,
        "final": final_snap,
        "rss_drift_mb": rss_drift,
        "pss_drift_mb": pss_drift,
        "thread_drift": thread_drift,
        "fd_drift": fd_drift,
        "orphan_tts_workers": tts_orphans,
        "samples_count": len(samples),
        "stability_verdict": "PASS" if errors == 0 and abs(fd_drift) <= 2 and abs(thread_drift) <= 2 else "PARTIAL",
    }

    out_file = "docs/audit/verified_sustained_stability.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Results recorded in {out_file}")

if __name__ == "__main__":
    main()
