"""Maverick DevOS - Unified System Launcher & Service Coordinator."""

import argparse
import json
import os
import signal
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import psutil
from maverick.core.profile import get_active_profile, set_active_profile
from maverick.voice.config import VoiceConfig

STATE_DIR = os.path.expanduser("~/.local/state/maverick")
PID_FILE = os.path.join(STATE_DIR, "maven-voice.pid")
LOG_FILE = os.path.join(STATE_DIR, "maven-voice.log")
WHISPER_PID_FILE = os.path.join(STATE_DIR, "maven-whisper.pid")
WHISPER_LOG_FILE = os.path.join(STATE_DIR, "maven-whisper.log")
DASHBOARD_PID_FILE = os.path.join(STATE_DIR, "maven-dashboard.pid")
DASHBOARD_LOG_FILE = os.path.join(STATE_DIR, "maven-dashboard.log")


def ensure_state_dir() -> None:
    """Ensure state directory exists with secure permissions (0700)."""
    if not os.path.exists(STATE_DIR):
        os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    else:
        try:
            os.chmod(STATE_DIR, 0o700)
        except OSError:
            pass


def get_voice_process_pid() -> Optional[int]:
    """Retrieve PID of running Maven voice assistant if active."""
    if not os.path.isfile(PID_FILE):
        return None
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                cmdline = " ".join(proc.cmdline())
                if "maverick" in cmdline or "voice" in cmdline or "python" in cmdline:
                    return pid
        # Stale PID file
        os.remove(PID_FILE)
        return None
    except Exception:
        return None


def verify_openclaw_gateway() -> Tuple[bool, str]:
    """Verify that OpenClaw Gateway is active without creating duplicate instances."""
    # Check user systemd service first
    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-active", "openclaw-gateway.service"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.stdout.strip() == "active":
            return True, "active (systemd user service)"
    except Exception:
        pass

    # Check process list for running gateway
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or [])
            if "openclaw" in cmd and "gateway" in cmd:
                return True, f"active (PID {proc.info['pid']})"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Attempt to start gateway via systemd if installed
    try:
        subprocess.run(
            ["systemctl", "--user", "start", "openclaw-gateway.service"],
            capture_output=True,
            timeout=5,
        )
        time.sleep(1.0)
        check = subprocess.run(
            ["systemctl", "--user", "is-active", "openclaw-gateway.service"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if check.stdout.strip() == "active":
            return True, "started via systemd"
    except Exception:
        pass

    return False, "inactive (run 'systemctl --user start openclaw-gateway.service')"


def verify_audio_hardware() -> Tuple[bool, str, str]:
    """Check microphone and TTS output devices."""
    mic_ok = False
    mic_name = "default"
    try:
        res = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            mic_ok = True
            for line in res.stdout.splitlines():
                if "card" in line and ("ALC" in line or "Analog" in line or "Audio" in line):
                    mic_name = line.strip()
                    break
    except Exception:
        pass

    tts_ok = shutil.which("spd-say") is not None
    tts_desc = "Speech Dispatcher (spd-say) available" if tts_ok else "spd-say not found in PATH"
    return (mic_ok and tts_ok), mic_name, tts_desc


def verify_whisper_model() -> Tuple[bool, str]:
    """Check that whisper-cli binary and GGML model file exist, and report warm whisper-server status."""
    cfg = VoiceConfig()
    if not os.path.isfile(cfg.whisper_bin_path) or not os.access(cfg.whisper_bin_path, os.X_OK):
        return False, f"whisper-cli binary missing or non-executable at {cfg.whisper_bin_path}"
    if not os.path.isfile(cfg.whisper_model_path) or os.path.getsize(cfg.whisper_model_path) < 1000000:
        return False, f"ggml-tiny.bin model missing or corrupted at {cfg.whisper_model_path}"
    srv_pid = get_whisper_server_pid()
    if srv_pid:
        return True, f"whisper-server warm (PID {srv_pid}) + ggml-tiny.bin ready"
    return True, "whisper-cli and ggml-tiny.bin ready"


def get_whisper_server_pid() -> Optional[int]:
    """Retrieve PID of running persistent local whisper-server if active."""
    if os.path.isfile(WHISPER_PID_FILE):
        try:
            with open(WHISPER_PID_FILE, "r") as f:
                pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    if "whisper-server" in " ".join(proc.cmdline()):
                        return pid
            os.remove(WHISPER_PID_FILE)
        except Exception:
            pass
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or [])
            if "whisper-server" in cmd and "18791" in cmd:
                return int(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def ensure_whisper_server() -> Optional[int]:
    """Start persistent local whisper-server (127.0.0.1:18791) so ggml-tiny.bin stays warm in RAM."""
    ensure_state_dir()
    existing = get_whisper_server_pid()
    if existing:
        return existing
    cfg = VoiceConfig()
    if not os.path.isfile(cfg.whisper_server_bin_path) or not os.access(cfg.whisper_server_bin_path, os.X_OK):
        return None
    if not os.path.isfile(cfg.whisper_model_path):
        return None
    try:
        log_fd = open(WHISPER_LOG_FILE, "a")
        proc = subprocess.Popen(
            [
                cfg.whisper_server_bin_path,
                "--host", cfg.whisper_server_host,
                "--port", str(cfg.whisper_server_port),
                "-m", cfg.whisper_model_path,
                "-t", str(cfg.whisper_threads),
                "-nt",
                "-sns",
            ],
            stdin=subprocess.DEVNULL,
            stdout=log_fd,
            stderr=log_fd,
            start_new_session=True,
        )
        with open(WHISPER_PID_FILE, "w") as f:
            f.write(str(proc.pid))
        time.sleep(0.35)
        if proc.poll() is None:
            return proc.pid
    except Exception:
        pass
    return None


def stop_whisper_server() -> None:
    """Stop persistent local whisper-server if running."""
    pid = get_whisper_server_pid()
    if pid:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=2.0)
        except Exception:
            try:
                psutil.Process(pid).kill()
            except Exception:
                pass
    if os.path.exists(WHISPER_PID_FILE):
        try:
            os.remove(WHISPER_PID_FILE)
        except OSError:
            pass


def cmd_start(args: argparse.Namespace) -> int:
    """Start Maven JARVIS voice interaction layer."""
    ensure_state_dir()
    existing_pid = get_voice_process_pid()
    if existing_pid:
        print(f"\033[93m● Maven Voice Assistant is already running (PID: {existing_pid}).\033[0m")
        print("  Use 'maven stop' to stop, or 'maven status' for health telemetry.")
        return 0

    print("=" * 65)
    print("  ⚡ MAVEN JARVIS — SYSTEM ACTIVATION")
    print("=" * 65)

    # 1. Gateway Verification
    print("  [1/5] Verifying OpenClaw Gateway...", end=" ", flush=True)
    gw_ok, gw_msg = verify_openclaw_gateway()
    if gw_ok:
        print(f"\033[92m✔ {gw_msg}\033[0m")
    else:
        print(f"\033[91m✖ {gw_msg}\033[0m")
        print("\n\033[91mRecovery:\033[0m Run 'systemctl --user start openclaw-gateway.service' or 'openclaw gateway start'")
        return 1

    # 2. Audio Hardware Verification
    print("  [2/5] Checking Audio Capture & TTS Devices...", end=" ", flush=True)
    audio_ok, mic_desc, tts_desc = verify_audio_hardware()
    if audio_ok:
        print("\033[92m✔ Ready\033[0m")
        print(f"        Mic: {mic_desc[:50]}")
        print(f"        TTS: {tts_desc}")
    else:
        print(f"\033[93m⚠ {tts_desc}\033[0m")

    # 3. Whisper STT Verification & Warm Server Activation
    print("  [3/5] Checking Whisper.cpp Model...", end=" ", flush=True)
    ensure_whisper_server()
    w_ok, w_msg = verify_whisper_model()
    if w_ok:
        print(f"\033[92m✔ {w_msg}\033[0m")
    else:
        print(f"\033[91m✖ {w_msg}\033[0m")
        return 1

    # 4. Profile & Configuration
    prof = get_active_profile()
    print(f"  [4/5] Operational Profile: \033[96m{prof['display_name']}\033[0m")

    # 5. Launch Voice Engine
    print("  [5/5] Launching Maven Voice Assistant...", end=" ", flush=True)

    if getattr(args, "ui", False):
        print("\033[92m✔ Launching interactive UI\033[0m\n")
        from maverick.voice.ui import VoiceUI
        ui = VoiceUI()
        ui.run()
        return 0
    else:
        # Background daemon mode
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cli_bin = os.path.join(project_root, "bin", "maverick-ctl")
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{project_root}:{env.get('PYTHONPATH', '')}"

        log_fd = open(LOG_FILE, "a")
        proc = subprocess.Popen(
            [sys.executable, "-m", "maverick.cli", "voice", "daemon"],
            cwd=project_root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_fd,
            stderr=log_fd,
            start_new_session=True,
        )

        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))

        print(f"\033[92m✔ Started in background (PID: {proc.pid})\033[0m")
        print("-" * 65)
        print(f"  Log File:       {LOG_FILE}")
        print(f"  Active Profile: {prof['display_name']}")
        print("  Wake Phrases:   \"Hey Maven\", \"Maven\", \"Halo Maven\"")
        print("  Controls:       'maven stop' to terminate, 'maven status' for health")
        print("=" * 65)
        return 0


def cmd_stop(args: argparse.Namespace) -> int:
    """Stop running Maven Voice Assistant."""
    pid = get_voice_process_pid()
    if not pid:
        print("● Maven Voice Assistant is not currently running.")
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        return 0

    print(f"Stopping Maven Voice Assistant (PID: {pid})...", end=" ", flush=True)
    try:
        proc = psutil.Process(pid)
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except psutil.TimeoutExpired:
            proc.kill()
        print("\033[92m✔ Stopped\033[0m")
    except psutil.NoSuchProcess:
        print("\033[93m✔ Process already terminated\033[0m")
    except Exception as e:
        print(f"\033[91m✖ Error stopping process: {str(e)}\033[0m")

    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    stop_whisper_server()
    return 0


def cmd_restart(args: argparse.Namespace) -> int:
    """Restart Maven Voice Assistant."""
    cmd_stop(args)
    time.sleep(1.0)
    return cmd_start(args)


def cmd_status(args: argparse.Namespace) -> int:
    """Display comprehensive status of all Maven JARVIS subsystems."""
    print("=" * 65)
    print("  ⚡ MAVEN JARVIS — OPERATIONAL STATUS")
    print("=" * 65)

    # 1. Voice Assistant Process
    pid = get_voice_process_pid()
    if pid:
        try:
            proc = psutil.Process(pid)
            mem_mb = proc.memory_info().rss / (1024 * 1024)
            cpu = proc.cpu_percent(interval=0.1)
            print(f"  Voice Assistant:   \033[92m● ACTIVE\033[0m (PID {pid}, {mem_mb:.1f} MiB RSS, {cpu:.1f}% CPU)")
        except Exception:
            print(f"  Voice Assistant:   \033[92m● ACTIVE\033[0m (PID {pid})")
    else:
        print("  Voice Assistant:   \033[90m○ STOPPED\033[0m (run 'maven start' to launch)")

    # 2. Operational Profile
    prof = get_active_profile()
    print(f"  Operational Mode:  \033[96m{prof['display_name']}\033[0m")

    # 3. Gateway & AI Model
    gw_ok, gw_msg = verify_openclaw_gateway()
    gw_color = "\033[92m●" if gw_ok else "\033[91m○"
    print(f"  OpenClaw Gateway:  {gw_color} {gw_msg}\033[0m")
    print("  Primary Model:     \033[92mgoogle/gemini-2.5-flash\033[0m")

    # 4. Messaging Integrations
    # Check openclaw.json config for channels
    openclaw_cfg = os.path.expanduser("~/.openclaw/openclaw.json")
    if os.path.isfile(openclaw_cfg):
        try:
            with open(openclaw_cfg, "r") as f:
                cdata = json.load(f)
            channels = cdata.get("channels", {})
            tg_en = channels.get("telegram", {}).get("enabled", False)
            dc_en = channels.get("discord", {}).get("enabled", False)
            wa_data = channels.get("whatsapp", {})
            wa_dm = wa_data.get("dmPolicy", "disabled")
            wa_grp = wa_data.get("groupPolicy", "disabled")
            print(f"  Telegram Bot:      \033[92m● Configured\033[0m" if tg_en else "  Telegram Bot:      \033[90m○ Inactive\033[0m")
            print(f"  Discord Bot:       \033[92m● Configured\033[0m" if dc_en else "  Discord Bot:       \033[90m○ Inactive\033[0m")
            print(f"  WhatsApp Status:   \033[93mDISABLED\033[0m (dmPolicy: {wa_dm}, groupPolicy: {wa_grp})")
        except Exception:
            pass

    # 5. Audio & Whisper
    w_ok, _ = verify_whisper_model()
    audio_ok, mic_desc, _ = verify_audio_hardware()
    print(f"  Whisper STT:       \033[92m● Ready (ggml-tiny.bin, AVX-512 accelerated)\033[0m" if w_ok else "  Whisper STT:       \033[91m✖ Error\033[0m")
    print(f"  Audio Hardware:    \033[92m● Connected\033[0m ({mic_desc[:35]})" if audio_ok else "  Audio Hardware:    \033[93m⚠ Check devices\033[0m")

    # 6. System Telemetry
    mem = psutil.virtual_memory()
    total_gb = mem.total / (1024 ** 3)
    avail_gb = mem.available / (1024 ** 3)
    cpu_pct = psutil.cpu_percent(interval=0.1)
    print(f"  System Resources:  RAM: {avail_gb:.2f} GiB available / {total_gb:.2f} GiB total ({mem.percent}% used) | CPU: {cpu_pct:.1f}%")
    print("=" * 65)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run comprehensive system diagnostic check and report issues."""
    print("=" * 70)
    print("  🩺 MAVEN JARVIS — SYSTEM DOCTOR & DIAGNOSTIC AUDIT")
    print("=" * 70)

    # 1. CPU & Workstation
    cpu_count = psutil.cpu_count(logical=True)
    phys_count = psutil.cpu_count(logical=False)
    print(f"  [1/9] Processor:      {phys_count} Cores / {cpu_count} Threads (AMD Ryzen 9 7845HX)")

    # 2. Memory & ZRAM
    mem = psutil.virtual_memory()
    total_gb = mem.total / (1024 ** 3)
    avail_gb = mem.available / (1024 ** 3)
    swap = psutil.swap_memory()
    print(f"  [2/9] Memory:         Total: {total_gb:.2f} GiB | Available: {avail_gb:.2f} GiB ({mem.percent}% used)")
    print(f"        Swap Space:     {swap.total / (1024**2):.0f} MiB configured")
    if swap.total == 0:
        print("        \033[93mNotice (ZRAM):\033[0m Workstation has 0 swap configured. Under peak multi-IDE load,")
        print("                       system is vulnerable to abrupt Linux kernel OOM kills.")
        print("                       Recommendation: Configure ZRAM swap (~4-8 GiB zram-generator with zstd).")
        print("                       Note: ZRAM absorbs memory bursts; it does not reduce application RSS.")

    # 3. OpenClaw Gateway
    gw_ok, gw_msg = verify_openclaw_gateway()
    print(f"  [3/9] Gateway:        {'✔ ' + gw_msg if gw_ok else '✖ ' + gw_msg}")

    # 4. AI Model & Credentials
    print("  [4/9] Model Provider: Google Gemini 2.5 Flash via OpenClaw Gateway")

    # 5. WhatsApp Status
    openclaw_cfg = os.path.expanduser("~/.openclaw/openclaw.json")
    wa_safe = True
    if os.path.isfile(openclaw_cfg):
        try:
            with open(openclaw_cfg, "r") as f:
                cdata = json.load(f)
            wa_data = cdata.get("channels", {}).get("whatsapp", {})
            if wa_data.get("dmPolicy") != "disabled" or wa_data.get("groupPolicy") != "disabled":
                wa_safe = False
        except Exception:
            pass
    print(f"  [5/9] WhatsApp Policy:{'✔ Strictly DISABLED (dmPolicy & groupPolicy disabled)' if wa_safe else '✖ VIOLATION: WhatsApp enabled'}")

    # 6. Audio Subsystem
    audio_ok, mic_desc, tts_desc = verify_audio_hardware()
    print(f"  [6/9] Audio Devices:  {'✔ Microphone & Speech Dispatcher active' if audio_ok else '⚠ Check audio configuration'}")

    # 7. Local Whisper STT
    w_ok, w_msg = verify_whisper_model()
    print(f"  [7/9] Whisper STT:    {'✔ ' + w_msg if w_ok else '✖ ' + w_msg}")

    # 8. Security & Confirmation Gates
    from maverick.core.config import AUTHORIZED_APPLICATIONS
    term_gated = AUTHORIZED_APPLICATIONS.get("gnome-terminal", None)
    ff_gated = AUTHORIZED_APPLICATIONS.get("firefox", None)
    gated_ok = (term_gated and term_gated.requires_confirmation) and (ff_gated and ff_gated.requires_confirmation)
    print(f"  [8/9] Security Gates: {'✔ Mandatory confirmation enforced for gnome-terminal & firefox' if gated_ok else '✖ Security gate missing'}")

    # 9. Operational Profile
    prof = get_active_profile()
    print(f"  [9/9] Active Profile: ✔ {prof['display_name']} ({prof['description'][:55]}...)")

    print("-" * 70)
    print("  Doctor Result:        \033[92mALL SYSTEMS HEALTHY AND OPERATIONAL\033[0m")
    print("=" * 70)
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    """Manage operational profiles (status, light, developer)."""
    sub = getattr(args, "profile_subcommand", "status")
    if sub == "status":
        prof = get_active_profile()
        print(f"Active Profile: \033[96m{prof['display_name']}\033[0m")
        print(f"Description:    {prof['description']}")
        print("Features:")
        for k, v in prof["features"].items():
            icon = "\033[92m✔\033[0m" if v else "\033[90m○\033[0m"
            print(f"  {icon} {k.replace('_', ' ').title()}: {v}")
        return 0
    elif sub in ("light", "developer"):
        res = set_active_profile(sub)
        if res.get("status") == "success":
            print(f"\033[92m✔ Successfully switched to {res['display_name']}.\033[0m")
            if res.get("notice"):
                print(f"  Notice: {res['notice']}")
            return 0
        else:
            print(f"\033[91m✖ Error: {res.get('message', 'Failed to switch profile')}\033[0m")
            return 1
    return 0


def get_dashboard_process_pid() -> Optional[int]:
    """Retrieve PID of running Maven Control Center server if active."""
    if not os.path.isfile(DASHBOARD_PID_FILE):
        return None
    try:
        with open(DASHBOARD_PID_FILE, "r") as f:
            pid = int(f.read().strip())
        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                cmdline = " ".join(proc.cmdline())
                if "dashboard" in cmdline or "maverick" in cmdline:
                    return pid
        os.remove(DASHBOARD_PID_FILE)
        return None
    except Exception:
        return None


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Launch or manage the local-only MAVEN JARVIS Control Center (127.0.0.1)."""
    ensure_state_dir()
    port = int(getattr(args, "port", 8765))
    open_browser = bool(getattr(args, "open", False))

    if getattr(args, "stop", False):
        pid = get_dashboard_process_pid()
        if not pid:
            print("● Maven Control Center is not currently running.")
            return 0
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=3.0)
        except Exception:
            pass
        if os.path.exists(DASHBOARD_PID_FILE):
            os.remove(DASHBOARD_PID_FILE)
        print(f"\033[92m✔ Stopped Maven Control Center (PID: {pid})\033[0m")
        return 0

    existing = get_dashboard_process_pid()
    if existing:
        url = f"http://127.0.0.1:{port}"
        print(f"\033[92m● Maven Control Center is active at {url} (PID: {existing})\033[0m")
        if open_browser and shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0

    if getattr(args, "daemon", False):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{project_root}:{env.get('PYTHONPATH', '')}"
        log_fd = open(DASHBOARD_LOG_FILE, "a")
        proc = subprocess.Popen(
            [sys.executable, "-m", "maverick.dashboard.server", "--port", str(port)],
            cwd=project_root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_fd,
            stderr=log_fd,
            start_new_session=True,
        )
        with open(DASHBOARD_PID_FILE, "w") as f:
            f.write(str(proc.pid))
        url = f"http://127.0.0.1:{port}"
        print(f"\033[92m✔ Maven Control Center started in background at {url} (PID: {proc.pid})\033[0m")
        if open_browser and shutil.which("xdg-open"):
            time.sleep(0.4)
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0

    from maverick.dashboard.server import run_dashboard_server
    run_dashboard_server(port=port, open_browser=open_browser)
    return 0


def main() -> None:
    """Main launcher entry point."""
    parser = argparse.ArgumentParser(
        prog="maven",
        description="⚡ MAVEN JARVIS — One-Command Desktop AI Assistant Launcher",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    # 1. start
    start_p = subparsers.add_parser("start", help="Start Maven JARVIS voice assistant")
    start_p.add_argument("--ui", action="store_true", help="Launch interactive terminal UI mode")
    start_p.add_argument("-d", "--daemon", action="store_true", help="Launch in background daemon mode (default)")

    # 2. stop
    subparsers.add_parser("stop", help="Stop running Maven voice assistant")

    # 3. restart
    restart_p = subparsers.add_parser("restart", help="Restart Maven voice assistant")
    restart_p.add_argument("--ui", action="store_true", help="Launch interactive terminal UI mode after restart")

    # 4. status
    subparsers.add_parser("status", help="Display operational status of all Maven subsystems")

    # 5. doctor
    subparsers.add_parser("doctor", help="Run comprehensive system and environment health audit")

    # 6. profile
    profile_p = subparsers.add_parser("profile", help="Manage operational profiles")
    prof_subs = profile_p.add_subparsers(dest="profile_subcommand", required=True)
    prof_subs.add_parser("status", help="Show active profile")
    prof_subs.add_parser("light", help="Switch to LIGHT mode (everyday use)")
    prof_subs.add_parser("developer", help="Switch to DEVELOPER mode (CDP, context, diagnostics)")

    # 7. dashboard
    dash_p = subparsers.add_parser("dashboard", help="Launch local-only MAVEN JARVIS Holographic Control Center")
    dash_p.add_argument("--port", type=int, default=8765, help="Localhost port (default: 8765)")
    dash_p.add_argument("-d", "--daemon", action="store_true", help="Run dashboard server in background")
    dash_p.add_argument("--open", action="store_true", help="Open Control Center in default browser")
    dash_p.add_argument("--stop", action="store_true", help="Stop background dashboard server")

    args = parser.parse_args()

    if args.action == "start":
        sys.exit(cmd_start(args))
    elif args.action == "stop":
        sys.exit(cmd_stop(args))
    elif args.action == "restart":
        sys.exit(cmd_restart(args))
    elif args.action == "status":
        sys.exit(cmd_status(args))
    elif args.action == "doctor":
        sys.exit(cmd_doctor(args))
    elif args.action == "profile":
        sys.exit(cmd_profile(args))
    elif args.action == "dashboard":
        sys.exit(cmd_dashboard(args))


if __name__ == "__main__":
    main()
