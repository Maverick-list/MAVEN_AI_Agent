"""Maverick DevOS - Command Line Interface."""

import argparse
import json
import sys
from typing import Any, Dict
from maverick.core.config import SPOTIFY_DBUS_DEST
from maverick.core.security import SecurityError, ConfirmationRequiredError
from maverick.desktop.launcher import (
    check_app_status,
    list_all_apps_status,
    launch_app,
)
from maverick.desktop.awareness import (
    get_running_authorized_apps,
    get_active_application_context,
)
from maverick.media.spotify import (
    SpotifyController,
    SpotifyControllerError,
    PlayerNotRunningError,
)
from maverick.browser.client import BrowserClient
from maverick.browser.security import BrowserSecurityError
from maverick.browser.lifecycle import BrowserLifecycleError
from maverick.browser.tabs import TabManagerError
from maverick.browser.navigation import NavigationError
from maverick.browser.page import PageInspectorError
from maverick.browser.interaction import InteractionError
from maverick.browser.cdp import CDPError
from maverick.system.monitor import (
    get_system_summary,
    get_system_resources,
    get_battery_status,
)
from maverick.notifications.manager import NotificationManager
from maverick.activity.logger import ActivityLogger
from maverick.context.engine import ContextEngine

_logger = ActivityLogger()


def output_result(data: Dict[str, Any], pretty: bool = False, exit_code: int = 0) -> None:
    """Print structured JSON output and exit with appropriate code."""
    indent = 2 if pretty else None
    print(json.dumps(data, indent=indent, default=str))
    sys.exit(exit_code)


def handle_app_commands(args: argparse.Namespace) -> None:
    """Handle 'app' and 'apps' subcommands."""
    sub = getattr(args, "app_subcommand", None) or getattr(args, "apps_subcommand", None)

    if sub == "list":
        apps = list_all_apps_status()
        output_result(
            {
                "status": "success",
                "action": "list_apps",
                "count": len(apps),
                "apps": apps,
            },
            pretty=args.pretty,
            exit_code=0,
        )

    elif sub == "running":
        running = get_running_authorized_apps()
        output_result(
            {
                "status": "success",
                "action": "running_apps",
                "count": len(running),
                "apps": running,
            },
            pretty=args.pretty,
            exit_code=0,
        )

    elif sub == "active":
        active_ctx = get_active_application_context()
        output_result(
            {
                "status": "success",
                "action": "active_app_context",
                "context": active_ctx,
            },
            pretty=args.pretty,
            exit_code=0,
        )

    elif sub == "status":
        try:
            status = check_app_status(args.app_id)
            output_result(
                {
                    "status": "success",
                    "action": "app_status",
                    "app": status,
                },
                pretty=args.pretty,
                exit_code=0,
            )
        except SecurityError as sec_err:
            output_result(
                {
                    "status": "error",
                    "code": "SECURITY_VIOLATION",
                    "message": str(sec_err),
                },
                pretty=args.pretty,
                exit_code=1,
            )

    elif sub == "launch":
        try:
            res = launch_app(
                app_id=args.app_id,
                args=args.args,
                confirmed=args.confirmed,
            )
            exit_code = 0 if res.get("status") == "success" else 1
            _logger.log_action("app_launch", args.app_id, res.get("status", "unknown"), args.confirmed, {"args": args.args})
            output_result(res, pretty=args.pretty, exit_code=exit_code)

        except ConfirmationRequiredError as conf_err:
            _logger.log_action("app_launch", conf_err.target, "confirmation_required", False, {"reason": conf_err.reason})
            output_result(
                {
                    "status": "confirmation_required",
                    "code": "CONFIRMATION_REQUIRED",
                    "action": conf_err.action,
                    "target": conf_err.target,
                    "message": str(conf_err),
                    "prompt": f"Explicit confirmation required: {conf_err.reason}. Add '--confirmed' flag to proceed.",
                },
                pretty=args.pretty,
                exit_code=2,
            )

        except SecurityError as sec_err:
            _logger.log_action("app_launch", getattr(args, "app_id", "unknown"), "security_violation", False, {"error": str(sec_err)})
            output_result(
                {
                    "status": "error",
                    "code": "SECURITY_VIOLATION",
                    "message": str(sec_err),
                },
                pretty=args.pretty,
                exit_code=1,
            )


def handle_spotify_commands(args: argparse.Namespace) -> None:
    """Handle 'spotify' subcommands."""
    sub = args.spotify_subcommand
    target_player = args.player or SPOTIFY_DBUS_DEST
    ctl = SpotifyController(dest=target_player)

    try:
        if sub == "players":
            players = ctl.list_active_mpris_players()
            output_result(
                {
                    "status": "success",
                    "action": "list_players",
                    "count": len(players),
                    "players": players,
                },
                pretty=args.pretty,
                exit_code=0,
            )

        elif sub == "status":
            status = ctl.get_status()
            output_result(status, pretty=args.pretty, exit_code=0)

        elif sub == "play":
            res = ctl.play()
            _logger.log_action("spotify_control", "play", "success", False, {"player": target_player})
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "pause":
            res = ctl.pause()
            _logger.log_action("spotify_control", "pause", "success", False, {"player": target_player})
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "toggle":
            res = ctl.play_pause()
            _logger.log_action("spotify_control", "toggle", "success", False, {"player": target_player})
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "next":
            res = ctl.next_track()
            _logger.log_action("spotify_control", "next", "success", False, {"player": target_player})
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "prev" or sub == "previous":
            res = ctl.previous_track()
            _logger.log_action("spotify_control", "prev", "success", False, {"player": target_player})
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "stop":
            res = ctl.stop()
            _logger.log_action("spotify_control", "stop", "success", False, {"player": target_player})
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "volume":
            res = ctl.set_volume(args.level)
            _logger.log_action("spotify_control", "volume", "success", False, {"level": args.level})
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "open-uri":
            res = ctl.open_uri(args.uri)
            _logger.log_action("spotify_control", "open-uri", "success", False, {"uri": args.uri})
            output_result(res, pretty=args.pretty, exit_code=0)

    except PlayerNotRunningError as pnr_err:
        output_result(
            {
                "status": "error",
                "code": "PLAYER_NOT_RUNNING",
                "message": str(pnr_err),
                "target": target_player,
            },
            pretty=args.pretty,
            exit_code=1,
        )

    except SpotifyControllerError as sc_err:
        output_result(
            {
                "status": "error",
                "code": "CONTROLLER_ERROR",
                "message": str(sc_err),
                "target": target_player,
            },
            pretty=args.pretty,
            exit_code=1,
        )

    except SecurityError as sec_err:
        output_result(
            {
                "status": "error",
                "code": "SECURITY_VIOLATION",
                "message": str(sec_err),
            },
            pretty=args.pretty,
            exit_code=1,
        )


def handle_browser_commands(args: argparse.Namespace) -> None:
    """Handle 'browser' subcommands."""
    from maverick.core.profile import is_feature_enabled

    sub = args.browser_subcommand
    client = BrowserClient()

    if sub != "status" and not is_feature_enabled("chrome_cdp_automation"):
        output_result(
            {
                "status": "error",
                "code": "FEATURE_DISABLED_IN_PROFILE",
                "message": "Chrome CDP automation is disabled in the active 'LIGHT' profile. Switch to DEVELOPER profile via 'maverick-ctl profile developer' or 'maven profile developer'.",
            },
            pretty=args.pretty,
            exit_code=1,
        )

    try:
        if sub == "status":
            res = client.status()
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "start":
            res = client.start(headless=args.headless, open_url=args.url)
            _logger.log_action("browser_start", "chrome", res.get("status", "unknown"), False)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "stop":
            res = client.stop()
            _logger.log_action("browser_stop", "chrome", "success", False)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "tabs":
            tabs = client.tabs()
            output_result(
                {
                    "status": "success",
                    "action": "list_tabs",
                    "count": len(tabs),
                    "tabs": tabs,
                },
                pretty=args.pretty,
                exit_code=0,
            )

        elif sub == "open":
            res = client.open_tab(url=args.url)
            _logger.log_action("browser_open_tab", args.url, "success", False)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "close-tab":
            res = client.close_tab(tab_id=args.tab)
            _logger.log_action("browser_close_tab", str(args.tab), "success", False)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "activate-tab":
            res = client.activate_tab(tab_id=args.tab)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "navigate":
            res = client.navigate(url=args.url, tab_id=args.tab)
            _logger.log_action("browser_navigate", args.url, "success", False)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "reload":
            res = client.reload(ignore_cache=args.ignore_cache, tab_id=args.tab)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "back":
            res = client.back(tab_id=args.tab)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "forward":
            res = client.forward(tab_id=args.tab)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "inspect":
            res = client.inspect(tab_id=args.tab)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "screenshot":
            res = client.screenshot(output_path=args.output, tab_id=args.tab)
            _logger.log_action("browser_screenshot", res.get("file_path", ""), "success", False)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "click":
            res = client.click(selector=args.selector, tab_id=args.tab, confirmed=args.confirmed)
            _logger.log_action("browser_click", args.selector, "success", args.confirmed)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "fill":
            res = client.fill(selector=args.selector, value=args.value, tab_id=args.tab, confirmed=args.confirmed)
            _logger.log_action("browser_fill", args.selector, "success", args.confirmed, {"chars": len(args.value)})
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "scroll":
            res = client.scroll(direction=args.direction, amount=args.amount, tab_id=args.tab)
            output_result(res, pretty=args.pretty, exit_code=0)

    except ConfirmationRequiredError as conf_err:
        _logger.log_action("browser_action", conf_err.target, "confirmation_required", False, {"action": conf_err.action})
        output_result(
            {
                "status": "confirmation_required",
                "code": "CONFIRMATION_REQUIRED",
                "action": conf_err.action,
                "target": conf_err.target,
                "message": str(conf_err),
                "prompt": f"Explicit confirmation required: {conf_err.reason}. Add '--confirmed' flag to proceed.",
            },
            pretty=args.pretty,
            exit_code=2,
        )

    except (BrowserSecurityError, SecurityError) as sec_err:
        _logger.log_action("browser_security", "violation", "error", False, {"error": str(sec_err)})
        output_result(
            {
                "status": "error",
                "code": "SECURITY_VIOLATION",
                "message": str(sec_err),
            },
            pretty=args.pretty,
            exit_code=1,
        )

    except (
        BrowserLifecycleError,
        TabManagerError,
        NavigationError,
        PageInspectorError,
        InteractionError,
        CDPError,
    ) as browser_err:
        output_result(
            {
                "status": "error",
                "code": type(browser_err).__name__,
                "message": str(browser_err),
            },
            pretty=args.pretty,
            exit_code=1,
        )


def handle_system_commands(args: argparse.Namespace) -> None:
    """Handle 'system' subcommands."""
    sub = args.system_subcommand

    if sub == "status":
        res = get_system_summary()
        output_result(res, pretty=args.pretty, exit_code=0)

    elif sub == "resources":
        res = get_system_resources()
        output_result({"status": "success", "resources": res}, pretty=args.pretty, exit_code=0)

    elif sub == "battery":
        res = get_battery_status()
        output_result({"status": "success", "battery": res}, pretty=args.pretty, exit_code=0)


def handle_notification_commands(args: argparse.Namespace) -> None:
    """Handle 'notifications' subcommands."""
    sub = args.notifications_subcommand
    nm = NotificationManager()

    if sub == "status":
        res = nm.get_status()
        output_result(res, pretty=args.pretty, exit_code=0)

    elif sub == "send":
        res = nm.send_notification(
            title=args.title,
            body=args.body or "",
            urgency=args.urgency,
            category=args.category,
        )
        _logger.log_action("notification_sent", args.title, res.get("status", "unknown"), False, {"category": args.category})
        output_result(res, pretty=args.pretty, exit_code=0)


def handle_context_command(args: argparse.Namespace) -> None:
    """Handle 'context' command."""
    ce = ContextEngine()
    ctx = ce.get_context()
    output_result(ctx, pretty=args.pretty, exit_code=0)


def handle_activity_commands(args: argparse.Namespace) -> None:
    """Handle 'activity' subcommands."""
    sub = args.activity_subcommand

    if sub == "recent":
        records = _logger.get_recent_activity(limit=args.limit)
        output_result(
            {
                "status": "success",
                "action": "recent_activity",
                "count": len(records),
                "records": records,
            },
            pretty=args.pretty,
            exit_code=0,
        )

    elif sub == "clear":
        res = _logger.clear()
        output_result(res, pretty=args.pretty, exit_code=0)


def handle_voice_commands(args: argparse.Namespace) -> None:
    """Handle 'voice' subcommands."""
    import shutil
    from maverick.voice.audio import list_audio_devices
    from maverick.voice.config import VoiceConfig
    from maverick.voice.controller import VoiceController
    from maverick.voice.tts import SpeechDispatcherTTS
    from maverick.voice.ui import VoiceUI

    sub = args.voice_subcommand

    if sub == "status":
        devs = list_audio_devices()
        cfg = VoiceConfig()
        from maverick.voice.stt import WhisperCppSTTProvider
        whisper_stt = WhisperCppSTTProvider(cfg)
        output_result(
            {
                "status": "success",
                "audio_devices": devs,
                "stt": {
                    "engine": "whisper.cpp",
                    "available": whisper_stt.is_available(),
                    "model_path": cfg.whisper_model_path,
                    "language": cfg.stt_language,
                },
                "tts": {
                    "engine": cfg.tts_engine,
                    "voice": cfg.tts_voice,
                    "available": shutil.which("spd-say") is not None,
                },
                "wake_words": cfg.wake_words,
                "listening_timeout_seconds": cfg.listening_timeout_seconds,
                "model_id": cfg.model_id,
            },
            pretty=args.pretty,
            exit_code=0,
        )

    elif sub == "speak":
        tts = SpeechDispatcherTTS()
        ok = tts.speak(args.text, wait=True)
        output_result(
            {
                "status": "success" if ok else "error",
                "action": "speak",
                "text": args.text,
            },
            pretty=args.pretty,
            exit_code=0 if ok else 1,
        )

    elif sub == "command":
        ctl = VoiceController()
        res = ctl.handle_voice_command(args.text, confirmed=args.confirmed)
        exit_code = 2 if res.get("status") == "confirmation_required" else (0 if res.get("status") in ("success", "empty") else 1)
        output_result(res, pretty=args.pretty, exit_code=exit_code)

    elif sub in ("listen", "ui"):
        ui = VoiceUI()
        ui.run()

    elif sub == "daemon":
        from maverick.voice.daemon import VoiceDaemon
        daemon = VoiceDaemon()
        daemon.run()


def handle_profile_commands(args: argparse.Namespace) -> None:
    """Handle 'profile' subcommands (status, light, developer)."""
    from maverick.core.profile import get_active_profile, set_active_profile
    sub = getattr(args, "profile_subcommand", "status")

    if sub == "status":
        res = get_active_profile()
        output_result(res, pretty=args.pretty, exit_code=0)
    elif sub == "light":
        res = set_active_profile("light")
        output_result(res, pretty=args.pretty, exit_code=0 if res.get("status") == "success" else 1)
    elif sub == "developer":
        res = set_active_profile("developer")
        output_result(res, pretty=args.pretty, exit_code=0 if res.get("status") == "success" else 1)


def main() -> None:
    """Main CLI entry point."""
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Format JSON output with indentation",
    )

    parser = argparse.ArgumentParser(
        prog="maverick-ctl",
        description="Maverick DevOS Desktop Intelligence & Controller",
        parents=[base_parser],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. App command parser
    app_parser = subparsers.add_parser("app", help="Manage desktop applications", parents=[base_parser])
    app_subs = app_parser.add_subparsers(dest="app_subcommand", required=True)
    app_subs.add_parser("list", help="List all authorized desktop applications", parents=[base_parser])
    app_subs.add_parser("running", help="List running authorized applications", parents=[base_parser])
    app_subs.add_parser("active", help="Get active application context", parents=[base_parser])

    app_status_parser = app_subs.add_parser("status", help="Check status of an application", parents=[base_parser])
    app_status_parser.add_argument("app_id", help="Authorized application ID")

    app_launch_parser = app_subs.add_parser("launch", help="Launch an authorized application", parents=[base_parser])
    app_launch_parser.add_argument("app_id", help="Authorized application ID")
    app_launch_parser.add_argument("--args", nargs="*", default=None, help="Optional arguments for the app")
    app_launch_parser.add_argument("--confirmed", action="store_true", help="Confirm consequential launches")

    # Apps alias (plural)
    apps_parser = subparsers.add_parser("apps", help="Alias for 'app' command", parents=[base_parser])
    apps_subs = apps_parser.add_subparsers(dest="apps_subcommand", required=True)
    apps_subs.add_parser("running", help="List running authorized applications", parents=[base_parser])
    apps_subs.add_parser("active", help="Get active application context", parents=[base_parser])
    apps_subs.add_parser("list", help="List all authorized desktop applications", parents=[base_parser])

    # 2. Spotify command parser
    spotify_base = argparse.ArgumentParser(add_help=False, parents=[base_parser])
    spotify_base.add_argument("--player", default=None, help="Specific MPRIS destination")
    spotify_parser = subparsers.add_parser("spotify", help="Control Spotify and MPRIS media players", parents=[spotify_base])
    spotify_subs = spotify_parser.add_subparsers(dest="spotify_subcommand", required=True)

    spotify_subs.add_parser("status", help="Get current playback status, volume, and track", parents=[spotify_base])
    spotify_subs.add_parser("play", help="Resume or start playback", parents=[spotify_base])
    spotify_subs.add_parser("pause", help="Pause playback", parents=[spotify_base])
    spotify_subs.add_parser("toggle", help="Toggle between play and pause", parents=[spotify_base])
    spotify_subs.add_parser("next", help="Skip to next track", parents=[spotify_base])
    spotify_subs.add_parser("prev", help="Return to previous track", parents=[spotify_base])
    spotify_subs.add_parser("stop", help="Stop playback", parents=[spotify_base])
    spotify_subs.add_parser("players", help="List active MPRIS media players", parents=[spotify_base])

    vol_parser = spotify_subs.add_parser("volume", help="Set player volume", parents=[spotify_base])
    vol_parser.add_argument("level", type=float, help="Volume level (0.0 - 1.0 or 0 - 100)")
    uri_parser = spotify_subs.add_parser("open-uri", help="Open Spotify URI or track URL", parents=[spotify_base])
    uri_parser.add_argument("uri", help="Spotify track/album/playlist URI")

    # 3. Browser command parser
    browser_base = argparse.ArgumentParser(add_help=False, parents=[base_parser])
    browser_base.add_argument("--tab", default=None, help="Target tab ID")
    browser_parser = subparsers.add_parser("browser", help="Control Chrome automation browser via CDP", parents=[browser_base])
    browser_subs = browser_parser.add_subparsers(dest="browser_subcommand", required=True)

    browser_subs.add_parser("status", help="Check browser automation and CDP status", parents=[browser_base])
    start_parser = browser_subs.add_parser("start", help="Launch isolated Chrome automation session", parents=[browser_base])
    start_parser.add_argument("--headless", action="store_true", help="Launch in headless mode")
    start_parser.add_argument("--url", default=None, help="Initial URL to open")
    browser_subs.add_parser("stop", help="Gracefully stop Chrome automation session", parents=[browser_base])
    browser_subs.add_parser("tabs", help="List open browser tabs", parents=[browser_base])

    open_parser = browser_subs.add_parser("open", help="Open a new tab", parents=[browser_base])
    open_parser.add_argument("url", nargs="?", default="about:blank", help="URL to open")
    browser_subs.add_parser("close-tab", help="Close the target tab", parents=[browser_base])
    act_parser = browser_subs.add_parser("activate-tab", help="Focus the target tab", parents=[browser_base])
    act_parser.add_argument("tab_id", help="Tab ID to activate")
    nav_parser = browser_subs.add_parser("navigate", help="Navigate target tab to a URL", parents=[browser_base])
    nav_parser.add_argument("url", help="Target URL (http/https/about:blank)")
    reload_parser = browser_subs.add_parser("reload", help="Reload the target tab", parents=[browser_base])
    reload_parser.add_argument("--ignore-cache", action="store_true", help="Bypass browser cache")
    browser_subs.add_parser("back", help="Navigate backward in history", parents=[browser_base])
    browser_subs.add_parser("forward", help="Navigate forward in history", parents=[browser_base])
    browser_subs.add_parser("inspect", help="Inspect visible text, title, and metadata", parents=[browser_base])

    shot_parser = browser_subs.add_parser("screenshot", help="Capture tab screenshot", parents=[browser_base])
    shot_parser.add_argument("--output", default=None, help="Destination PNG file path")
    click_parser = browser_subs.add_parser("click", help="Click an element by CSS selector", parents=[browser_base])
    click_parser.add_argument("selector", help="CSS selector of element to click")
    click_parser.add_argument("--confirmed", action="store_true", help="Confirm consequential interactions")
    fill_parser = browser_subs.add_parser("fill", help="Fill text into an element", parents=[browser_base])
    fill_parser.add_argument("selector", help="CSS selector of input/textarea")
    fill_parser.add_argument("value", help="Text to fill")
    fill_parser.add_argument("--confirmed", action="store_true", help="Confirm consequential interactions")
    scroll_parser = browser_subs.add_parser("scroll", help="Scroll page", parents=[browser_base])
    scroll_parser.add_argument("--direction", default="down", choices=["up", "down", "top", "bottom"])
    scroll_parser.add_argument("--amount", type=int, default=500)

    # 4. System command parser
    system_parser = subparsers.add_parser("system", help="Monitor system resources, battery, and telemetry", parents=[base_parser])
    system_subs = system_parser.add_subparsers(dest="system_subcommand", required=True)
    system_subs.add_parser("status", help="Get comprehensive system summary", parents=[base_parser])
    system_subs.add_parser("resources", help="Get CPU, RAM, and Disk metrics", parents=[base_parser])
    system_subs.add_parser("battery", help="Get battery and charging status", parents=[base_parser])

    # 5. Notifications command parser
    notif_parser = subparsers.add_parser("notifications", help="Desktop notification manager", parents=[base_parser])
    notif_subs = notif_parser.add_subparsers(dest="notifications_subcommand", required=True)
    notif_subs.add_parser("status", help="Check notification service status", parents=[base_parser])
    send_notif = notif_subs.add_parser("send", help="Send a safe desktop notification", parents=[base_parser])
    send_notif.add_argument("title", help="Notification title")
    send_notif.add_argument("body", nargs="?", default="", help="Notification body text")
    send_notif.add_argument("--urgency", default="normal", choices=["low", "normal", "critical"])
    send_notif.add_argument("--category", default="system", choices=list(nm_categories := ["system", "media", "browser", "task", "alert", "social"]))

    # 6. Context command parser
    subparsers.add_parser("context", help="Get unified structured context snapshot for Maven JARVIS", parents=[base_parser])

    # 7. Activity command parser
    activity_parser = subparsers.add_parser("activity", help="Inspect and manage auditable activity logs", parents=[base_parser])
    activity_subs = activity_parser.add_subparsers(dest="activity_subcommand", required=True)
    recent_act = activity_subs.add_parser("recent", help="Show recent Maven actions", parents=[base_parser])
    recent_act.add_argument("--limit", type=int, default=10, help="Number of records to show")
    activity_subs.add_parser("clear", help="Clear Maven's activity log file", parents=[base_parser])

    # 8. Voice command parser
    voice_parser = subparsers.add_parser("voice", help="Voice interaction layer and speech synthesis", parents=[base_parser])
    voice_subs = voice_parser.add_subparsers(dest="voice_subcommand", required=True)
    voice_subs.add_parser("status", help="Check microphone, speaker, and TTS subsystem status", parents=[base_parser])
    
    speak_parser = voice_subs.add_parser("speak", help="Synthesize and speak text via local TTS", parents=[base_parser])
    speak_parser.add_argument("text", help="Text to speak")

    cmd_parser = voice_subs.add_parser("command", help="Execute a voice command via router", parents=[base_parser])
    cmd_parser.add_argument("text", help="Voice command transcript")
    cmd_parser.add_argument("--confirmed", action="store_true", help="Confirm consequential actions")

    voice_subs.add_parser("listen", help="Launch interactive voice session UI", parents=[base_parser])
    voice_subs.add_parser("ui", help="Launch interactive voice session UI", parents=[base_parser])
    voice_subs.add_parser("daemon", help="Run background voice assistant daemon", parents=[base_parser])

    # 9. Profile command parser
    profile_parser = subparsers.add_parser("profile", help="Manage operational profiles (light / developer)", parents=[base_parser])
    profile_subs = profile_parser.add_subparsers(dest="profile_subcommand", required=True)
    profile_subs.add_parser("status", help="Get current active profile and features", parents=[base_parser])
    profile_subs.add_parser("light", help="Switch to LIGHT mode (everyday laptop use)", parents=[base_parser])
    profile_subs.add_parser("developer", help="Switch to DEVELOPER mode (CDP, context engine, diagnostics)", parents=[base_parser])

    args = parser.parse_args()

    if args.command in ("app", "apps"):
        handle_app_commands(args)
    elif args.command == "spotify":
        handle_spotify_commands(args)
    elif args.command == "browser":
        handle_browser_commands(args)
    elif args.command == "system":
        handle_system_commands(args)
    elif args.command == "notifications":
        handle_notification_commands(args)
    elif args.command == "context":
        handle_context_command(args)
    elif args.command == "activity":
        handle_activity_commands(args)
    elif args.command == "voice":
        handle_voice_commands(args)
    elif args.command == "profile":
        handle_profile_commands(args)


if __name__ == "__main__":
    main()
