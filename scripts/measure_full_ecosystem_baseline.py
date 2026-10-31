#!/usr/bin/env python3
"""Establish complete system and ecosystem baseline for Maven JARVIS Phase 1."""

import json
import os
import subprocess
import time
import psutil

def get_proc_full_metrics(pid: int) -> dict:
    res = {
        "pid": pid,
        "name": "",
        "cmdline": "",
        "rss_mb": 0.0,
        "pss_mb": 0.0,
        "uss_mb": 0.0,
        "vmsize_mb": 0.0,
        "vmpeak_mb": 0.0,
        "vmhwm_mb": 0.0,
        "threads": 0,
        "fds": 0,
        "cpu_percent": 0.0,
    }
    try:
        proc = psutil.Process(pid)
        res["name"] = proc.name()
        res["cmdline"] = " ".join(proc.cmdline()[:4])
        res["threads"] = proc.num_threads()
        res["fds"] = proc.num_fds() if hasattr(proc, "num_fds") else 0
        res["cpu_percent"] = proc.cpu_percent(interval=0.1)
    except Exception:
        return res

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

    # Read /proc/[pid]/smaps_rollup
    smaps_path = f"/proc/{pid}/smaps_rollup"
    if os.path.isfile(smaps_path):
        try:
            clean, dirty = 0.0, 0.0
            with open(smaps_path, "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        k, v = parts[0].strip(), parts[1].strip()
                        if k == "Pss":
                            res["pss_mb"] = round(float(v.split()[0]) / 1024.0, 2)
                        elif k == "Private_Clean":
                            clean = float(v.split()[0]) / 1024.0
                        elif k == "Private_Dirty":
                            dirty = float(v.split()[0]) / 1024.0
            res["uss_mb"] = round(clean + dirty, 2)
        except Exception:
            pass

    return res

def get_system_environment() -> dict:
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    temp_c = None
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_c = round(float(f.read().strip()) / 1000.0, 1)
    except Exception:
        pass

    return {
        "ram_total_mb": round(vm.total / (1024 * 1024), 2),
        "ram_available_mb": round(vm.available / (1024 * 1024), 2),
        "ram_used_mb": round(vm.used / (1024 * 1024), 2),
        "ram_percent": vm.percent,
        "swap_total_mb": round(sw.total / (1024 * 1024), 2),
        "swap_used_mb": round(sw.used / (1024 * 1024), 2),
        "swap_percent": sw.percent,
        "thermal_temp_c": temp_c,
    }

def main():
    print("=== COLLECTING COMPLETE MAVEN ECOSYSTEM BASELINE ===")
    env_info = get_system_environment()

    # Discover relevant ecosystem PIDs
    dashboard_pids = []
    try:
        out = subprocess.check_output(["lsof", "-ti:18766", "-sTCP:LISTEN"]).decode().strip().split()
        dashboard_pids = [int(p) for p in out if p]
    except Exception:
        pass

    openclaw_pids = []
    try:
        out = subprocess.check_output(["lsof", "-ti:18789"]).decode().strip().split()
        openclaw_pids = [int(p) for p in out if p]
    except Exception:
        pass

    whisper_pids = []
    try:
        out = subprocess.check_output(["lsof", "-ti:18791"]).decode().strip().split()
        whisper_pids = [int(p) for p in out if p]
    except Exception:
        pass

    all_pids_to_check = set(dashboard_pids + openclaw_pids + whisper_pids)

    # Search psutil for any additional maven or pocket_tts processes
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if any(term in cmd for term in ["maverick", "pocket_tts", "openclaw"]):
                all_pids_to_check.add(p.info["pid"])
        except Exception:
            pass

    ecosystem = []
    maven_rss = 0.0
    maven_pss = 0.0
    maven_uss = 0.0
    openclaw_rss = 0.0
    openclaw_pss = 0.0
    openclaw_uss = 0.0

    for pid in sorted(all_pids_to_check):
        m = get_proc_full_metrics(pid)
        cmd = m["cmdline"].lower()
        if "openclaw" in cmd or pid in openclaw_pids:
            m["ownership"] = "external_openclaw_gateway_trial"
            openclaw_rss += m["rss_mb"]
            openclaw_pss += m["pss_mb"]
            openclaw_uss += m["uss_mb"]
        elif "maverick" in cmd or "pocket_tts" in cmd or pid in dashboard_pids:
            m["ownership"] = "maven_owned_service"
            maven_rss += m["rss_mb"]
            maven_pss += m["pss_mb"]
            maven_uss += m["uss_mb"]
        else:
            m["ownership"] = "other_related"
        ecosystem.append(m)

    baseline = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "system_environment": env_info,
        "maven_owned_summary": {
            "total_rss_mb": round(maven_rss, 2),
            "total_pss_mb": round(maven_pss, 2),
            "total_uss_mb": round(maven_uss, 2),
        },
        "openclaw_trial_summary": {
            "total_rss_mb": round(openclaw_rss, 2),
            "total_pss_mb": round(openclaw_pss, 2),
            "total_uss_mb": round(openclaw_uss, 2),
        },
        "grand_total_ecosystem_rss_mb": round(maven_rss + openclaw_rss, 2),
        "processes": ecosystem,
    }

    out_file = "docs/audit/verified_ecosystem_baseline.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(baseline, f, indent=2)

    print(f"\nBaseline Telemetry Summary:")
    print(f"  System Total RAM:        {env_info['ram_total_mb']} MB")
    print(f"  System Available RAM:    {env_info['ram_available_mb']} MB ({env_info['ram_percent']}% used)")
    print(f"  System Swap:             {env_info['swap_used_mb']} / {env_info['swap_total_mb']} MB")
    print(f"  CPU Temp:                {env_info['thermal_temp_c']} C")
    print(f"  Maven-Owned RSS:         {round(maven_rss, 2)} MB (PSS: {round(maven_pss, 2)} MB, USS: {round(maven_uss, 2)} MB)")
    print(f"  OpenClaw Trial RSS:      {round(openclaw_rss, 2)} MB (PSS: {round(openclaw_pss, 2)} MB, USS: {round(openclaw_uss, 2)} MB)")
    print(f"  Grand Total Ecosystem:   {round(maven_rss + openclaw_rss, 2)} MB")
    print(f"Baseline saved to {out_file}")

if __name__ == "__main__":
    main()
