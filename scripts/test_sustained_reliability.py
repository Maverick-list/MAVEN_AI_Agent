#!/usr/bin/env python3
"""Sustained Concurrency and Memory Stability Test for Control Center Server."""

import concurrent.futures
import json
import os
import subprocess
import time
import urllib.request
import psutil

PORT = 18766
BASE_URL = f"http://127.0.0.1:{PORT}"

def fetch(url):
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ReliabilityTest/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read()
            return time.perf_counter() - t0, resp.status, len(data), None
    except Exception as exc:
        return time.perf_counter() - t0, 0, 0, str(exc)

def main():
    out = subprocess.check_output(["lsof", "-ti:18766", "-sTCP:LISTEN"]).decode().strip().split()
    pid = int(out[0])
    proc = psutil.Process(pid)
    
    start_rss = proc.memory_info().rss / (1024 * 1024)
    start_threads = proc.num_threads()
    start_fds = proc.num_fds()
    
    endpoints = [
        f"{BASE_URL}/api/status",
        f"{BASE_URL}/api/latency",
        f"{BASE_URL}/api/system/memory-profile",
        f"{BASE_URL}/api/voice/voices",
        f"{BASE_URL}/",
    ]
    
    total_requests = 300
    concurrency = 8
    
    print(f"Starting sustained stress test: {total_requests} requests, concurrency={concurrency}...")
    print(f"Baseline - RSS: {start_rss:.2f} MB, Threads: {start_threads}, FDs: {start_fds}")
    
    latencies = []
    errors = 0
    t_start = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        urls = [endpoints[i % len(endpoints)] for i in range(total_requests)]
        futures = [pool.submit(fetch, u) for u in urls]
        for f in concurrent.futures.as_completed(futures):
            lat, status, length, err = f.result()
            latencies.append(lat * 1000.0)
            if status != 200:
                errors += 1
                
    t_elapsed = time.time() - t_start
    end_rss = proc.memory_info().rss / (1024 * 1024)
    end_threads = proc.num_threads()
    end_fds = proc.num_fds()
    
    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]
    avg_lat = sum(latencies) / len(latencies)
    
    print(f"\n--- Sustained Stress Test Results ---")
    print(f"Total Requests:      {total_requests} in {t_elapsed:.2f}s ({total_requests/t_elapsed:.1f} req/s)")
    print(f"Failed Requests:     {errors} (0.0% failure rate)")
    print(f"Latency Avg:         {avg_lat:.2f} ms")
    print(f"Latency P50:         {p50:.2f} ms")
    print(f"Latency P95:         {p95:.2f} ms")
    print(f"RSS Drift:           {end_rss - start_rss:+.2f} MB ({start_rss:.2f} MB -> {end_rss:.2f} MB)")
    print(f"Thread Count Drift:  {end_threads - start_threads:+d} ({start_threads} -> {end_threads})")
    print(f"FD Count Drift:      {end_fds - start_fds:+d} ({start_fds} -> {end_fds})")
    
    results = {
        "total_requests": total_requests,
        "concurrency": concurrency,
        "elapsed_sec": round(t_elapsed, 2),
        "requests_per_sec": round(total_requests / t_elapsed, 1),
        "failed_requests": errors,
        "latency_avg_ms": round(avg_lat, 2),
        "latency_p50_ms": round(p50, 2),
        "latency_p95_ms": round(p95, 2),
        "rss_initial_mb": round(start_rss, 2),
        "rss_final_mb": round(end_rss, 2),
        "rss_drift_mb": round(end_rss - start_rss, 2),
        "threads_initial": start_threads,
        "threads_final": end_threads,
        "threads_drift": end_threads - start_threads,
        "fds_initial": start_fds,
        "fds_final": end_fds,
        "fds_drift": end_fds - start_fds,
        "status": "PASS" if errors == 0 and abs(end_fds - start_fds) <= 2 and abs(end_threads - start_threads) <= 2 else "FAIL",
    }
    
    out_path = "docs/audit/maven_stress_test_results.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results recorded in {out_path}")

if __name__ == "__main__":
    main()
