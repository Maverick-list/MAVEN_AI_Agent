#!/usr/bin/env python3
"""Deep verification of HTTP server safety, bounded worker pool, SSE, and timeouts."""

import concurrent.futures
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import psutil

PORT = 18766
BASE_URL = f"http://127.0.0.1:{PORT}"

def get_server_pid():
    out = subprocess.check_output(["lsof", "-ti:18766", "-sTCP:LISTEN"]).decode().strip().split()
    return int(out[0])

def count_dashboard_worker_threads(pid):
    proc = psutil.Process(pid)
    count = 0
    for t in proc.threads():
        # Read thread name from /proc/[pid]/task/[tid]/comm
        comm_path = f"/proc/{pid}/task/{t.id}/comm"
        try:
            with open(comm_path, "r") as f:
                name = f.read().strip()
                if "DashboardWorker" in name:
                    count += 1
        except Exception:
            pass
    return count

def test_bounded_worker_pool():
    pid = get_server_pid()
    print(f"\n1. Testing Bounded Worker Pool (Max Workers = 8)...")
    
    # Send 30 concurrent requests
    def req():
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/status", timeout=5) as r:
                return r.status
        except Exception as exc:
            return str(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as pool:
        futures = [pool.submit(req) for _ in range(30)]
        # Sample worker thread count while requests are processing
        worker_threads = count_dashboard_worker_threads(pid)
        results = [f.result() for f in futures]

    final_workers = count_dashboard_worker_threads(pid)
    print(f"  Worker threads during burst: {worker_threads} (Bounded target <= 12, prior baseline was 100+)")
    print(f"  Worker threads after burst:  {final_workers}")
    print(f"  Requests successful: {results.count(200)} / 30")
    
    return {
        "max_observed_workers": max(worker_threads, final_workers),
        "bounded_strictly": max(worker_threads, final_workers) <= 12,
        "all_succeeded": results.count(200) == 30,
    }

def test_socket_timeout():
    print(f"\n2. Testing Socket Timeout on Inactive / Incomplete Connection...")
    # Open raw TCP connection and send nothing, expecting server to close after 5s timeout
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(8.0)
    s.connect(("127.0.0.1", PORT))
    
    # Send partial request
    s.sendall(b"GET /api/status HTTP/1.1\r\nHost: 127.0.0.1\r\n")
    t0 = time.time()
    closed = False
    try:
        # Wait for server to timeout and close
        while time.time() - t0 < 8.0:
            data = s.recv(1024)
            if not data:
                closed = True
                break
    except socket.timeout:
        closed = False
    finally:
        s.close()
    
    elapsed = round(time.time() - t0, 2)
    print(f"  Socket closed by server after timeout: {closed} (Elapsed: {elapsed}s, expected ~5.0s)")
    return {
        "socket_auto_closed": closed,
        "timeout_elapsed_sec": elapsed,
    }

def test_error_handling_and_cors():
    print(f"\n3. Testing Error Handling & Cross-Origin POST Protection...")
    # 404 Not Found
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/nonexistent")
        with urllib.request.urlopen(req) as r:
            code_404 = r.status
    except urllib.error.HTTPError as e:
        code_404 = e.code

    # 403 Forbidden Origin
    try:
        req = urllib.request.Request(
            f"{BASE_URL}/api/system/mode",
            data=json.dumps({"mode": "normal"}).encode(),
            headers={"Content-Type": "application/json", "Origin": "http://evil-site.com"},
        )
        with urllib.request.urlopen(req) as r:
            code_origin = r.status
    except urllib.error.HTTPError as e:
        code_origin = e.code

    print(f"  404 route handling: HTTP {code_404} (expected 404)")
    print(f"  Cross-origin POST:  HTTP {code_origin} (expected 403)")
    return {
        "status_404_verified": code_404 == 404,
        "status_403_origin_verified": code_origin == 403,
    }

def test_connection_close_header():
    print(f"\n4. Testing Connection: close and Clean Socket Termination...")
    req = urllib.request.Request(f"{BASE_URL}/api/status")
    with urllib.request.urlopen(req, timeout=5) as r:
        conn_hdr = r.headers.get("Connection", "").lower()
    print(f"  Connection header on REST response: '{conn_hdr}' (expected 'close')")
    return {
        "connection_close_present": conn_hdr == "close",
    }

def test_sse_stream_and_disconnect():
    print(f"\n5. Testing SSE Stream and Graceful Client Disconnect...")
    req = urllib.request.Request(f"{BASE_URL}/api/events")
    with urllib.request.urlopen(req, timeout=5) as sse_resp:
        ctype = sse_resp.headers.get("Content-Type", "")
        line1 = sse_resp.readline().decode("utf-8")
        line2 = sse_resp.readline().decode("utf-8")
    
    # Client disconnected here
    print(f"  SSE Content-Type: {ctype}")
    print(f"  SSE Line 1: {line1.strip()}")
    print(f"  SSE Line 2: {line2.strip()[:60]}...")
    
    # Verify server is still completely responsive after SSE disconnect
    with urllib.request.urlopen(f"{BASE_URL}/api/status", timeout=5) as r:
        post_sse_status = r.status
    print(f"  Post-SSE server health check: HTTP {post_sse_status}")
    
    return {
        "sse_content_type": ctype,
        "telemetry_received": "telemetry" in line1,
        "post_disconnect_healthy": post_sse_status == 200,
    }

def main():
    report = {}
    print("=== TASK 4: HTTP SERVER SAFETY & BOUNDED CONCURRENCY ===")
    report["bounded_workers"] = test_bounded_worker_pool()
    report["socket_timeout"] = test_socket_timeout()
    report["error_handling"] = test_error_handling_and_cors()
    report["connection_close"] = test_connection_close_header()
    report["sse_lifecycle"] = test_sse_stream_and_disconnect()

    out_file = "docs/audit/verified_http_safety.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)

    all_passed = (
        report["bounded_workers"]["bounded_strictly"]
        and report["bounded_workers"]["all_succeeded"]
        and report["socket_timeout"]["socket_auto_closed"]
        and report["error_handling"]["status_404_verified"]
        and report["error_handling"]["status_403_origin_verified"]
        and report["connection_close"]["connection_close_present"]
        and report["sse_lifecycle"]["post_disconnect_healthy"]
    )
    print(f"\nAll HTTP safety checks passed: {all_passed}")
    print(f"Report saved to {out_file}")

if __name__ == "__main__":
    main()
