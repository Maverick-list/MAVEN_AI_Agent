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
        description="Maverick DevOS Desktop Launcher & Spotify Controller",
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

    args = parser.parse_args()

    if args.command == "app":
        handle_app_commands(args)
    elif args.command == "spotify":
        handle_spotify_commands(args)


if __name__ == "__main__":
    main()
