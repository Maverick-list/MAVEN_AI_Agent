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


def output_result(data: Dict[str, Any], pretty: bool = False, exit_code: int = 0) -> None:
    """Print structured JSON output and exit with appropriate code."""
    indent = 2 if pretty else None
    print(json.dumps(data, indent=indent, default=str))
    sys.exit(exit_code)


def handle_app_commands(args: argparse.Namespace) -> None:
    """Handle 'app' subcommands."""
    sub = args.app_subcommand

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
            output_result(res, pretty=args.pretty, exit_code=exit_code)

        except ConfirmationRequiredError as conf_err:
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
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "pause":
            res = ctl.pause()
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "toggle":
            res = ctl.play_pause()
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "next":
            res = ctl.next_track()
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "prev" or sub == "previous":
            res = ctl.previous_track()
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "stop":
            res = ctl.stop()
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "volume":
            res = ctl.set_volume(args.level)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "open-uri":
            res = ctl.open_uri(args.uri)
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
    sub = args.browser_subcommand
    client = BrowserClient()

    try:
        if sub == "status":
            res = client.status()
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "start":
            res = client.start(headless=args.headless, open_url=args.url)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "stop":
            res = client.stop()
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
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "close-tab":
            res = client.close_tab(tab_id=args.tab)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "activate-tab":
            res = client.activate_tab(tab_id=args.tab)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "navigate":
            res = client.navigate(url=args.url, tab_id=args.tab)
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
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "click":
            res = client.click(selector=args.selector, tab_id=args.tab, confirmed=args.confirmed)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "fill":
            res = client.fill(selector=args.selector, value=args.value, tab_id=args.tab, confirmed=args.confirmed)
            output_result(res, pretty=args.pretty, exit_code=0)

        elif sub == "scroll":
            res = client.scroll(direction=args.direction, amount=args.amount, tab_id=args.tab)
            output_result(res, pretty=args.pretty, exit_code=0)

    except ConfirmationRequiredError as conf_err:
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


def main() -> None:
    """Main CLI entry point."""
    # Base parser for shared options like --pretty
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Format JSON output with indentation",
    )

    parser = argparse.ArgumentParser(
        prog="maverick-ctl",
        description="Maverick DevOS Desktop Launcher, Spotify & Browser Controller",
        parents=[base_parser],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. App command parser
    app_parser = subparsers.add_parser("app", help="Manage desktop applications", parents=[base_parser])
    app_subs = app_parser.add_subparsers(dest="app_subcommand", required=True)

    app_subs.add_parser("list", help="List all authorized desktop applications", parents=[base_parser])
    
    app_status_parser = app_subs.add_parser("status", help="Check status of an application", parents=[base_parser])
    app_status_parser.add_argument("app_id", help="Authorized application ID")

    app_launch_parser = app_subs.add_parser("launch", help="Launch an authorized application", parents=[base_parser])
    app_launch_parser.add_argument("app_id", help="Authorized application ID")
    app_launch_parser.add_argument("--args", nargs="*", default=None, help="Optional arguments for the app")
    app_launch_parser.add_argument(
        "--confirmed",
        action="store_true",
        help="Explicitly confirm consequential launches (required for browsers, terminals)",
    )

    # Base parser for spotify options like --player
    spotify_base = argparse.ArgumentParser(add_help=False, parents=[base_parser])
    spotify_base.add_argument(
        "--player",
        default=None,
        help="Specific MPRIS destination (defaults to org.mpris.MediaPlayer2.spotify)",
    )

    # 2. Spotify command parser
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

    # Base parser for browser options like --tab
    browser_base = argparse.ArgumentParser(add_help=False, parents=[base_parser])
    browser_base.add_argument(
        "--tab",
        default=None,
        help="Target tab ID (defaults to first/active page tab)",
    )

    # 3. Browser command parser
    browser_parser = subparsers.add_parser("browser", help="Control Chrome automation browser via CDP", parents=[browser_base])
    browser_subs = browser_parser.add_subparsers(dest="browser_subcommand", required=True)

    browser_subs.add_parser("status", help="Check browser automation and CDP status", parents=[browser_base])
    
    start_parser = browser_subs.add_parser("start", help="Launch isolated Chrome automation session", parents=[browser_base])
    start_parser.add_argument("--headless", action="store_true", help="Launch in headless mode")
    start_parser.add_argument("--url", default=None, help="Initial URL to open")

    browser_subs.add_parser("stop", help="Gracefully stop Chrome automation session", parents=[browser_base])
    browser_subs.add_parser("tabs", help="List open browser tabs", parents=[browser_base])

    open_parser = browser_subs.add_parser("open", help="Open a new tab", parents=[browser_base])
    open_parser.add_argument("url", nargs="?", default="about:blank", help="URL to open (defaults to about:blank)")

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

    scroll_parser = browser_subs.add_parser("scroll", help="Scroll page up, down, top, or bottom", parents=[browser_base])
    scroll_parser.add_argument("--direction", default="down", choices=["up", "down", "top", "bottom"], help="Scroll direction")
    scroll_parser.add_argument("--amount", type=int, default=500, help="Scroll pixels (default 500)")

    args = parser.parse_args()

    if args.command == "app":
        handle_app_commands(args)
    elif args.command == "spotify":
        handle_spotify_commands(args)
    elif args.command == "browser":
        handle_browser_commands(args)


if __name__ == "__main__":
    main()
