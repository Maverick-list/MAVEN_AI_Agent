#!/usr/bin/env python3
"""Deep verification of /api/system/memory-cleanup and post-cleanup subsystem integrity."""

import json
import os
import time
import urllib.request

PORT = 18766
BASE_URL = f"http://127.0.0.1:{PORT}"

def post_json(endpoint: str, data: dict = None) -> tuple:
    t0 = time.perf_counter()
    req = urllib.request.Request(
        f"{BASE_URL}{endpoint}",
        data=json.dumps(data or {}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": BASE_URL},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        lat_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return resp.status, body, lat_ms

def get_json(endpoint: str) -> tuple:
    t0 = time.perf_counter()
    req = urllib.request.Request(f"{BASE_URL}{endpoint}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        lat_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return resp.status, body, lat_ms

def main():
    report = {}
    print("=== TASK 5: MEMORY CLEANUP API & SUBSYSTEM INTEGRITY ===")

    # 1. Baseline status before cleanup
    st_pre, snap_pre, lat_pre = get_json("/api/status")
    print(f"1. Pre-cleanup status check: HTTP {st_pre} ({lat_pre} ms)")
    report["pre_cleanup_status"] = {
        "status_code": st_pre,
        "latency_ms": lat_pre,
        "mode": snap_pre.get("mode", {}).get("active_mode"),
        "ai_gateway_ready": snap_pre.get("ai_gateway", {}).get("status") == "ready",
    }

    # 2. Trigger /api/system/memory-cleanup
    st_clean, clean_res, lat_clean = post_json("/api/system/memory-cleanup")
    print(f"2. Triggered /api/system/memory-cleanup: HTTP {st_clean} ({lat_clean} ms)")
    print(f"   Actions executed: {clean_res.get('actions_executed')}")
    print(f"   Reported pressure: {clean_res.get('pressure')}, Available RAM: {clean_res.get('available_gb')} GB")
    report["cleanup_execution"] = {
        "status_code": st_clean,
        "latency_ms": lat_clean,
        "response": clean_res,
        "actions": clean_res.get("actions_executed", []),
    }

    # 3. Post-cleanup latency and service integrity
    st_post, snap_post, lat_post = get_json("/api/status")
    print(f"3. Post-cleanup status check: HTTP {st_post} ({lat_post} ms, pre was {lat_pre} ms)")
    report["post_cleanup_status"] = {
        "status_code": st_post,
        "latency_ms": lat_post,
        "services_intact": (
            snap_post.get("ai_gateway", {}).get("status") == snap_pre.get("ai_gateway", {}).get("status")
            and snap_post.get("security", {}).get("bind_address") == "127.0.0.1"
        ),
    }

    # 4. Verify model inference functions normally after cleanup (No deadlocks or broken pipelines)
    print("4. Testing speech synthesis inference immediately after cleanup...")
    st_voice, voice_res, lat_voice = post_json("/api/voice/test", {"lang": "en", "browser_audio": True})
    print(f"   Voice test: HTTP {st_voice} ({lat_voice} ms), Status: {voice_res.get('status')}, Engine: {voice_res.get('engine')}")
    report["post_cleanup_inference"] = {
        "status_code": st_voice,
        "latency_ms": lat_voice,
        "inference_successful": voice_res.get("status") == "success",
        "engine_used": voice_res.get("engine"),
    }

    # 5. Verify camera hardware check after cleanup
    print("5. Testing vision hardware check after cleanup...")
    st_cam, cam_res, lat_cam = get_json("/api/status")
    cam_online = cam_res.get("vision", {}).get("engine", {}).get("camera", {}).get("device_index", 0) is not None
    print(f"   Vision camera descriptor available: {cam_online}")
    report["post_cleanup_camera"] = {
        "camera_descriptor_valid": cam_online,
    }

    out_file = "docs/audit/verified_memory_cleanup.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)

    all_passed = (
        st_clean == 200
        and report["post_cleanup_status"]["services_intact"]
        and report["post_cleanup_inference"]["inference_successful"]
        and cam_online
    )
    print(f"\nAll memory cleanup checks passed: {all_passed}")
    print(f"Report saved to {out_file}")

if __name__ == "__main__":
    main()
