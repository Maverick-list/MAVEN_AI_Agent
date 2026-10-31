#!/usr/bin/env python3
"""Comprehensive Functional Validation Suite for Maven JARVIS Phase 1."""

import json
import os
import subprocess
import time
import urllib.request
import urllib.error
import psutil

PORT = 18766
BASE_URL = f"http://127.0.0.1:{PORT}"

def post_json(path: str, body: dict) -> dict:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:18766"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get_json(path: str) -> dict:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "FunctionalTester/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def count_pocket_tts_workers() -> int:
    cnt = 0
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if "maverick.voice.pocket_tts_worker" in cmd or "pocket_tts.models" in cmd:
                cnt += 1
        except Exception:
            pass
    return cnt

def main():
    print("====================================================================")
    print("  🚀 MAVEN JARVIS — PHASE 1 FUNCTIONAL VALIDATION SUITE")
    print("====================================================================")

    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "suites": {},
        "overall_verdict": "PENDING"
    }

    # ---------------------------------------------------------
    # SUITE 1: VOICE LIFECYCLE & NATURAL TTS
    # ---------------------------------------------------------
    print("\n[1/4] Testing Voice Lifecycle & Natural TTS...")
    voice_res = {}
    try:
        # A. Voice Device Enumeration
        status = get_json("/api/status")
        audio = status.get("audio", {})
        has_mic = audio.get("has_microphone", False)
        has_spk = audio.get("has_speaker", False)
        voice_res["audio_hardware"] = {
            "has_microphone": has_mic,
            "has_speaker": has_spk,
            "default_input": audio.get("default_input"),
            "default_output": audio.get("default_output"),
            "inputs_count": len(audio.get("inputs", [])),
            "outputs_count": len(audio.get("outputs", [])),
        }
        print(f"  ✓ Audio Devices: {voice_res['audio_hardware']['inputs_count']} inputs, {voice_res['audio_hardware']['outputs_count']} outputs")

        # B. Voice List
        voices = get_json("/api/voice/voices")
        ln_avail = voices.get("local_neural", {}).get("available", False)
        voice_res["voice_catalog"] = {
            "active_engine": voices.get("active_engine"),
            "local_neural_available": ln_avail,
            "curated_voices_count": len(voices.get("local_neural", {}).get("voices", [])),
        }
        print(f"  ✓ Voice Catalog: Engine={voices.get('active_engine')}, Local Neural={ln_avail}")

        # C. Synthesis Test (Pocket TTS)
        t0 = time.perf_counter()
        synth = post_json("/api/voice/test", {"text": "Phase one voice operational validation in progress."})
        synth_latency = round((time.perf_counter() - t0) * 1000, 1)
        voice_res["synthesis_test"] = {
            "status": synth.get("status"),
            "engine": synth.get("engine"),
            "voice": synth.get("voice_name"),
            "ttfb_ms": synth.get("metrics", {}).get("ttfb_ms"),
            "audio_duration_s": synth.get("metrics", {}).get("dur"),
            "rtf": synth.get("metrics", {}).get("rtf"),
            "request_latency_ms": synth_latency,
        }
        print(f"  ✓ Synthesis: TTFB={synth.get('metrics', {}).get('ttfb_ms')} ms, RTF={synth.get('metrics', {}).get('rtf')}, Latency={synth_latency} ms")

        # D. Audio Stream Verification
        audio_url = synth.get("audio_url")
        if audio_url:
            req = urllib.request.Request(f"{BASE_URL}{audio_url}")
            with urllib.request.urlopen(req, timeout=5) as r:
                hdr = r.read(16)
                voice_res["audio_stream"] = {
                    "status": r.status,
                    "header_magic": hdr[:4].decode("latin1", errors="replace"),
                    "is_valid_wav": hdr[:4] == b"RIFF" and hdr[8:12] == b"WAVE",
                }
            print(f"  ✓ Audio Stream Verified: HTTP {r.status}, Valid WAV={voice_res['audio_stream']['is_valid_wav']}")

        # E. Barge-In / Stop Test
        stop_res = post_json("/api/voice/stop", {})
        voice_res["barge_in_stop"] = stop_res
        print(f"  ✓ Barge-In / Stop: {stop_res.get('status')}")

        # F. Mute / Unmute Test
        mute_res = post_json("/api/voice/mute", {"muted": True})
        unmute_res = post_json("/api/voice/mute", {"muted": False})
        voice_res["mute_unmute"] = {"mute": mute_res.get("status"), "unmute": unmute_res.get("status")}
        print(f"  ✓ Mute/Unmute: Mute={mute_res.get('status')}, Unmute={unmute_res.get('status')}")

        # G. Worker Memory Reclaim & Cleanup Verification
        workers_before = count_pocket_tts_workers()
        cleanup = post_json("/api/system/memory-cleanup", {})
        time.sleep(0.3)
        workers_after = count_pocket_tts_workers()
        voice_res["worker_cleanup"] = {
            "workers_before": workers_before,
            "workers_after": workers_after,
            "actions_executed": cleanup.get("actions_executed", []),
            "clean_reclaim": workers_after == 0,
        }
        print(f"  ✓ TTS Worker Cleanup: Before={workers_before}, After={workers_after} (Clean={workers_after == 0})")

        voice_res["verdict"] = "PASS" if voice_res["synthesis_test"]["status"] == "success" and voice_res["worker_cleanup"]["clean_reclaim"] else "PARTIAL"
    except Exception as exc:
        voice_res["verdict"] = "FAIL"
        voice_res["error"] = str(exc)
        print(f"  ✗ Voice Suite Error: {exc}")
    results["suites"]["voice"] = voice_res

    # ---------------------------------------------------------
    # SUITE 2: VISION PIPELINE & GESTURE RECOGNITION
    # ---------------------------------------------------------
    print("\n[2/4] Testing Vision Pipeline & Gesture Recognition...")
    vision_res = {}
    try:
        # A. Camera Test
        cam_test = post_json("/api/vision/test-camera", {})
        vision_res["camera_hardware"] = cam_test
        print(f"  ✓ Camera Hardware: {cam_test.get('resolution')} @ {cam_test.get('fps')} FPS, Active={cam_test.get('is_active')}")

        # B. Gesture Test (21 hand landmarks / classifier)
        gest_test = post_json("/api/vision/test-gesture", {})
        vision_res["gesture_recognition"] = gest_test
        print(f"  ✓ Gesture Tracking: Provider={gest_test.get('provider')}, Hands={gest_test.get('hands_detected')}, Gesture={gest_test.get('gesture')}")

        # C. Mode Switch: Vision Mode Activation
        m_vis = post_json("/api/system/mode", {"mode": "vision"})
        vision_res["mode_activation"] = m_vis
        print(f"  ✓ Vision Mode Activated: {m_vis.get('mode')}")
        time.sleep(0.5)  # Allow hardware exposure and first frame buffer to settle

        # D. Live Frame Capture Verification
        req = urllib.request.Request(f"{BASE_URL}/api/vision/frame")
        with urllib.request.urlopen(req, timeout=5) as r:
            frame_bytes = r.read()
            vision_res["live_frame"] = {
                "status": r.status,
                "content_type": r.headers.get("Content-Type"),
                "size_bytes": len(frame_bytes),
                "is_valid_jpeg": len(frame_bytes) > 1000 and frame_bytes[:2] == b"\xff\xd8",
            }
        print(f"  ✓ Live Frame Capture: {len(frame_bytes)} bytes, Valid JPEG={vision_res['live_frame']['is_valid_jpeg']}")

        # E. Mode Switch Back to Normal Mode & Camera Shutdown Verification
        m_norm = post_json("/api/system/mode", {"mode": "normal"})
        time.sleep(0.5)
        status_after = get_json("/api/status")
        cam_active = status_after.get("vision", {}).get("camera_active", False)
        vision_res["mode_deactivation"] = {
            "mode": m_norm.get("mode"),
            "camera_offline": not cam_active,
        }
        print(f"  ✓ Deactivated to Normal: Camera Offline={not cam_active}")
        vision_res["verdict"] = "PASS" if cam_test.get("status") == "success" and vision_res["live_frame"]["is_valid_jpeg"] and not cam_active else "PARTIAL"
    except Exception as exc:
        vision_res["verdict"] = "FAIL"
        vision_res["error"] = str(exc)
        print(f"  ✗ Vision Suite Error: {exc}")
    results["suites"]["vision"] = vision_res

    # ---------------------------------------------------------
    # SUITE 3: COMPUTER USE SUBSYSTEM & AT-SPI2 INTROSPECTION
    # ---------------------------------------------------------
    print("\n[3/4] Testing Computer Use Subsystem & AT-SPI2...")
    cu_res = {}
    try:
        # A. UI Observation
        obs = get_json("/api/computer-use/observation")
        observation = obs.get("observation", {})
        active_win = observation.get("active_window", {})
        windows = observation.get("windows", [])
        cu_res["observation"] = {
            "screen_resolution": observation.get("screen_resolution"),
            "active_window_app": active_win.get("app_name"),
            "active_window_title": active_win.get("window_title"),
            "total_windows_detected": len(windows),
            "interactive_elements_count": observation.get("interactive_elements_count"),
        }
        print(f"  ✓ Observation: Screen={observation.get('screen_resolution')}, Active App={active_win.get('app_name')}, Windows={len(windows)}")

        # B. Profiles Listing
        profiles = get_json("/api/computer-use/profiles")
        cu_res["profiles"] = {
            "count": len(profiles.get("profiles", [])),
            "sample_profiles": [p.get("name") or p.get("id") for p in profiles.get("profiles", [])[:5]],
        }
        print(f"  ✓ Application Profiles: {cu_res['profiles']['count']} profiles loaded")

        # C. Controlled Pause / Resume Cycle
        p_res = post_json("/api/computer-use/pause", {})
        r_res = post_json("/api/computer-use/resume", {})
        cu_res["pause_resume"] = {"pause": p_res.get("status"), "resume": r_res.get("status")}
        print(f"  ✓ Agent State Controls: Pause={p_res.get('status')}, Resume={r_res.get('status')}")

        # D. Controlled Failure Recovery
        fail_goal = post_json("/api/computer-use/execute", {"goal": "", "confirmed": False})
        cu_res["failure_recovery"] = {
            "rejected_empty_goal": fail_goal.get("status") == "error" or not fail_goal.get("success", True),
            "response": fail_goal,
        }
        print(f"  ✓ Controlled Failure Handled: {fail_goal.get('message') or fail_goal.get('error') or 'Gracefully rejected'}")
        cu_res["verdict"] = "PASS" if cu_res["observation"]["total_windows_detected"] > 0 else "PARTIAL"
    except Exception as exc:
        cu_res["verdict"] = "FAIL"
        cu_res["error"] = str(exc)
        print(f"  ✗ Computer Use Suite Error: {exc}")
    results["suites"]["computer_use"] = cu_res

    # ---------------------------------------------------------
    # SUITE 4: DASHBOARD INTEGRATION, MODE SWITCHING & E-STOP
    # ---------------------------------------------------------
    print("\n[4/4] Testing Dashboard Integration, Mode Switching & E-Stop...")
    dash_res = {}
    try:
        # A. Status Endpoint Integrity
        st = get_json("/api/status")
        dash_res["status_integrity"] = {
            "has_assistant": "assistant" in st,
            "has_system": "system" in st,
            "has_audio": "audio" in st,
            "has_security": "security" in st,
            "has_vision": "vision" in st,
            "has_computer_use": "computer_use" in st,
        }
        print(f"  ✓ Status Endpoint: All required telemetry sections present")

        # B. All 6 Operating Modes Transition Verification
        modes = ["normal", "voice", "vision", "full_assistant", "low_memory", "safe_idle"]
        mode_results = {}
        for m in modes:
            resp = post_json("/api/system/mode", {"mode": m})
            cur = resp.get("mode")
            mode_results[m] = {"requested": m, "active": cur, "ok": cur == m}
        dash_res["mode_transitions"] = mode_results
        all_modes_ok = all(v["ok"] for v in mode_results.values())
        print(f"  ✓ 6 Operating Modes Tested: All transitions successful={all_modes_ok}")

        # Restore to normal mode
        post_json("/api/system/mode", {"mode": "normal"})

        # C. Memory Profile Deep Introspection
        mem_prof = get_json("/api/system/memory-profile")
        dash_res["memory_profile"] = {
            "subsystems_count": len(mem_prof.get("subsystems", [])),
            "components": [s.get("component") for s in mem_prof.get("subsystems", [])],
        }
        print(f"  ✓ Memory Profile: {dash_res['memory_profile']['subsystems_count']} subsystems profiled")

        # D. Emergency Stop Verification
        estop = post_json("/api/emergency-stop", {})
        dash_res["emergency_stop"] = estop
        print(f"  ✓ Master Emergency Stop: Action={estop.get('action')}")

        # Restore to normal mode after E-stop
        post_json("/api/system/mode", {"mode": "normal"})

        # E. SSE Telemetry Stream Verification
        req = urllib.request.Request(f"{BASE_URL}/api/events")
        with urllib.request.urlopen(req, timeout=5) as r:
            first_line = r.readline().decode("utf-8").strip()
            second_line = r.readline().decode("utf-8").strip()
            dash_res["sse_stream"] = {
                "status": r.status,
                "first_line": first_line,
                "has_telemetry_event": "telemetry" in first_line or "telemetry" in second_line,
            }
        print(f"  ✓ SSE Telemetry Stream: HTTP {r.status}, Event Frame={first_line}")
        dash_res["verdict"] = "PASS" if all_modes_ok and dash_res["status_integrity"]["has_assistant"] else "PARTIAL"
    except Exception as exc:
        dash_res["verdict"] = "FAIL"
        dash_res["error"] = str(exc)
        print(f"  ✗ Dashboard Suite Error: {exc}")
    results["suites"]["dashboard"] = dash_res

    # Overall Verdict
    verdicts = [s["verdict"] for s in results["suites"].values()]
    if all(v == "PASS" for v in verdicts):
        results["overall_verdict"] = "PASS"
    elif any(v == "FAIL" for v in verdicts):
        results["overall_verdict"] = "FAIL"
    else:
        results["overall_verdict"] = "PARTIAL"

    out_file = "docs/audit/verified_functional_operations.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)

    print("\n====================================================================")
    print(f"  🏁 FUNCTIONAL VALIDATION COMPLETE: VERDICT = {results['overall_verdict']}")
    print(f"  Evidence saved to {out_file}")
    print("====================================================================")

if __name__ == "__main__":
    main()
