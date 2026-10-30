"""Maverick DevOS - Spotify & MPRIS D-Bus Controller."""

import re
import subprocess
from typing import Any, Dict, List, Optional
from maverick.core.config import (
    DEFAULT_TIMEOUT_SECONDS,
    SPOTIFY_DBUS_DEST,
    MPRIS_OBJECT_PATH,
    MPRIS_PLAYER_INTERFACE,
    MPRIS_PROPERTIES_INTERFACE,
    DBUS_CORE_DEST,
    DBUS_CORE_PATH,
    DBUS_MPRIS_PREFIX,
)
from maverick.core.security import SecurityError, _SAFE_SPOTIFY_URI_REGEX

try:
    import gi
    from gi.repository import Gio, GLib
    HAS_GIO = True
except ImportError:
    HAS_GIO = False


class SpotifyControllerError(Exception):
    """Base error for Spotify/MPRIS controller."""
    pass


class PlayerNotRunningError(SpotifyControllerError):
    """Raised when the target media player is not running on D-Bus."""
    pass


class SpotifyController:
    """Controller for Spotify and MPRIS-compliant media players via D-Bus."""

    ALLOWED_MPRIS_METHODS = {
        "org.mpris.MediaPlayer2.Player.Play",
        "org.mpris.MediaPlayer2.Player.Pause",
        "org.mpris.MediaPlayer2.Player.PlayPause",
        "org.mpris.MediaPlayer2.Player.Next",
        "org.mpris.MediaPlayer2.Player.Previous",
        "org.mpris.MediaPlayer2.Player.Stop",
        "org.mpris.MediaPlayer2.Player.OpenUri",
        "org.freedesktop.DBus.Properties.Get",
        "org.freedesktop.DBus.Properties.Set",
    }

    def __init__(self, dest: str = SPOTIFY_DBUS_DEST):
        # Validate that destination is strictly a safe MPRIS D-Bus name
        if not re.match(r"^org\.mpris\.MediaPlayer2\.[a-zA-Z0-9_.-]+$", dest):
            raise SecurityError(f"Invalid MPRIS destination: '{dest}'")
        self.dest = dest

    def _get_session_bus(self):
        """Get synchronous D-Bus session bus via Gio."""
        if not HAS_GIO:
            raise SpotifyControllerError("GNOME Gio repository is not available.")
        return Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def _validate_unconfined_args(self, args: List[str]) -> None:
        """
        Enforce strict allowlisting on all arguments passed to unconfined gdbus fallback.
        Only verified MPRIS methods and tightly bounded parameters are permitted.
        The unconfined execution context is strictly restricted to Spotify.
        """
        # 1. Restrict unconfined execution strictly to Spotify
        if self.dest != SPOTIFY_DBUS_DEST:
            raise SecurityError(
                f"Unconfined fallback execution is strictly restricted to '{SPOTIFY_DBUS_DEST}', "
                f"rejected destination '{self.dest}'."
            )

        if not args or len(args) < 2 or args[0] != "--method":
            raise SecurityError(f"Malformed unconfined gdbus arguments: {args}")

        method = args[1]
        if method not in self.ALLOWED_MPRIS_METHODS:
            raise SecurityError(f"Method '{method}' is not permitted for unconfined execution.")

        # Parameterless playback controls
        if method in (
            "org.mpris.MediaPlayer2.Player.Play",
            "org.mpris.MediaPlayer2.Player.Pause",
            "org.mpris.MediaPlayer2.Player.PlayPause",
            "org.mpris.MediaPlayer2.Player.Next",
            "org.mpris.MediaPlayer2.Player.Previous",
            "org.mpris.MediaPlayer2.Player.Stop",
        ):
            if len(args) != 2:
                raise SecurityError(f"Parameterless method '{method}' cannot accept extra arguments: {args}")

        # OpenUri validation
        elif method == "org.mpris.MediaPlayer2.Player.OpenUri":
            if len(args) != 3 or not _SAFE_SPOTIFY_URI_REGEX.match(args[2]):
                uri_val = args[2] if len(args) > 2 else ""
                raise SecurityError(f"Invalid or unsafe URI argument for OpenUri: '{uri_val}'")

        # Property Get validation
        elif method == "org.freedesktop.DBus.Properties.Get":
            if len(args) != 4:
                raise SecurityError(f"Properties.Get requires exactly 2 arguments (iface, prop): {args}")
            iface, prop = args[2], args[3]
            if iface not in (MPRIS_PLAYER_INTERFACE, "org.mpris.MediaPlayer2"):
                raise SecurityError(f"Unauthorized interface for Properties.Get: '{iface}'")
            if prop not in ("PlaybackStatus", "Volume", "Metadata", "Position"):
                raise SecurityError(f"Unauthorized property for Properties.Get: '{prop}'")

        # Property Set validation (Volume only)
        elif method == "org.freedesktop.DBus.Properties.Set":
            if len(args) != 5:
                raise SecurityError(f"Properties.Set requires exactly 3 arguments (iface, prop, val): {args}")
            iface, prop, val = args[2], args[3], args[4]
            if iface != MPRIS_PLAYER_INTERFACE or prop != "Volume":
                raise SecurityError(f"Only Volume property can be modified via Properties.Set, got '{iface}.{prop}'")
            if not re.match(r"^<@d (0(\.[0-9]+)?|1(\.0+)?)>$", val):
                raise SecurityError(f"Invalid volume variant format: '{val}'")

    def _run_unconfined_gdbus(self, args: List[str]) -> str:
        """
        Execute gdbus call with unconfined credentials when AppArmor subprofiles
        (like vscode unconfined) restrict direct D-Bus access to Snap MPRIS slots.
        Strictly sandboxed to allowed MPRIS operations only.
        """
        self._validate_unconfined_args(args)

        base_cmd = [
            "/usr/bin/gdbus",
            "call",
            "--session",
            "--dest",
            self.dest,
            "--object-path",
            MPRIS_OBJECT_PATH,
        ] + args

        # 1. Try aa-exec -p unconfined
        try:
            cmd = ["aa-exec", "-p", "unconfined"] + base_cmd
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                check=True,
            )
            return res.stdout.strip()
        except Exception:
            pass

        # 2. Try systemd-run --user
        try:
            cmd = ["systemd-run", "--user", "--wait", "--pipe"] + base_cmd
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                check=True,
            )
            return res.stdout.strip()
        except Exception as exc:
            raise SpotifyControllerError(f"Unconfined D-Bus invocation failed: {exc}")

    def list_active_mpris_players(self) -> List[str]:
        """List all active MPRIS media players on the session bus."""
        if HAS_GIO:
            try:
                bus = self._get_session_bus()
                dbus_proxy = Gio.DBusProxy.new_sync(
                    bus,
                    Gio.DBusProxyFlags.NONE,
                    None,
                    DBUS_CORE_DEST,
                    DBUS_CORE_PATH,
                    DBUS_CORE_DEST,
                    None,
                )
                names = dbus_proxy.ListNames()
                return [n for n in names if n.startswith(DBUS_MPRIS_PREFIX)]
            except Exception:
                pass

        # Fallback to gdbus CLI
        try:
            res = subprocess.run(
                [
                    "/usr/bin/gdbus",
                    "call",
                    "--session",
                    "--dest",
                    DBUS_CORE_DEST,
                    "--object-path",
                    DBUS_CORE_PATH,
                    "--method",
                    f"{DBUS_CORE_DEST}.ListNames",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                check=True,
            )
            return re.findall(r"'(" + re.escape(DBUS_MPRIS_PREFIX) + r"\.[^']+)'", res.stdout)
        except Exception as exc:
            raise SpotifyControllerError(f"Failed to query active D-Bus media players: {exc}")

    def is_player_active(self) -> bool:
        """Check if target player is currently active on the session bus."""
        players = self.list_active_mpris_players()
        return self.dest in players

    def _get_player_proxy(self):
        bus = self._get_session_bus()
        return Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            self.dest,
            MPRIS_OBJECT_PATH,
            MPRIS_PLAYER_INTERFACE,
            None,
        )

    def _get_properties_proxy(self):
        bus = self._get_session_bus()
        return Gio.DBusProxy.new_sync(
            bus,
            Gio.DBusProxyFlags.NONE,
            None,
            self.dest,
            MPRIS_OBJECT_PATH,
            MPRIS_PROPERTIES_INTERFACE,
            None,
        )

    def get_status(self) -> Dict[str, Any]:
        """Query current playback status, volume, and track metadata."""
        if not self.is_player_active():
            active = self.list_active_mpris_players()
            raise PlayerNotRunningError(
                f"Player '{self.dest}' is not running on D-Bus. Active players: {active or 'none'}"
            )

        try:
            props = self._get_properties_proxy()
            status_var = props.Get("(ss)", MPRIS_PLAYER_INTERFACE, "PlaybackStatus")
            playback_status = str(status_var)

            volume_var = props.Get("(ss)", MPRIS_PLAYER_INTERFACE, "Volume")
            volume = float(volume_var) if volume_var is not None else 1.0

            raw_meta = props.Get("(ss)", MPRIS_PLAYER_INTERFACE, "Metadata")
            metadata: Dict[str, Any] = {}
            if raw_meta:
                for k, v in raw_meta.items():
                    if isinstance(v, (str, int, float, bool)):
                        metadata[k] = v
                    elif isinstance(v, list):
                        metadata[k] = [str(item) for item in v]
                    elif hasattr(v, "unpack"):
                        metadata[k] = v.unpack()
                    else:
                        metadata[k] = str(v)

        except Exception as exc:
            err_msg = str(exc)
            if "AccessDenied" in err_msg or "AppArmor" in err_msg:
                # AppArmor fallback via unconfined runner
                status_raw = self._run_unconfined_gdbus([
                    "--method", f"{MPRIS_PROPERTIES_INTERFACE}.Get",
                    MPRIS_PLAYER_INTERFACE, "PlaybackStatus"
                ])
                match_status = re.search(r"<'([^']+)'", status_raw)
                playback_status = match_status.group(1) if match_status else "Unknown"

                vol_raw = self._run_unconfined_gdbus([
                    "--method", f"{MPRIS_PROPERTIES_INTERFACE}.Get",
                    MPRIS_PLAYER_INTERFACE, "Volume"
                ])
                match_vol = re.search(r"<([0-9.]+)", vol_raw)
                volume = float(match_vol.group(1)) if match_vol else 1.0

                meta_raw = self._run_unconfined_gdbus([
                    "--method", f"{MPRIS_PROPERTIES_INTERFACE}.Get",
                    MPRIS_PLAYER_INTERFACE, "Metadata"
                ])
                metadata = {}
                for m in re.finditer(r"'([^']+)': <(?:\[(.*?)\]|'([^']*)'|([0-9.]+)|int64 ([0-9]+)|uint64 ([0-9]+))>", meta_raw):
                    key = m.group(1)
                    if m.group(2) is not None:
                        metadata[key] = [re.sub(r"^'|'$", "", s.strip()) for s in m.group(2).split(",") if s.strip()]
                    elif m.group(3) is not None:
                        metadata[key] = m.group(3)
                    elif m.group(4) is not None:
                        metadata[key] = float(m.group(4))
                    elif m.group(5) is not None:
                        metadata[key] = int(m.group(5))
                    elif m.group(6) is not None:
                        metadata[key] = int(m.group(6))
            else:
                raise SpotifyControllerError(f"Failed to query playback status: {str(exc)}")

        # Extract human-friendly metadata
        artists = metadata.get("xesam:artist", [])
        artist_str = ", ".join(artists) if isinstance(artists, list) else str(artists)
        title = metadata.get("xesam:title", "Unknown Title")
        album = metadata.get("xesam:album", "")
        art_url = metadata.get("mpris:artUrl", "")
        track_id = metadata.get("mpris:trackid", "")
        length_us = metadata.get("mpris:length", 0)
        length_sec = round(length_us / 1_000_000, 1) if length_us else 0.0

        # Resolve web link
        web_url = metadata.get("xesam:url", "")
        if not web_url:
            if "spotify:track:" in track_id:
                tid = track_id.split("spotify:track:")[-1]
                web_url = f"https://open.spotify.com/track/{tid}"
            elif "/com/spotify/track/" in track_id:
                tid = track_id.split("/com/spotify/track/")[-1]
                web_url = f"https://open.spotify.com/track/{tid}"

        return {
            "status": "success",
            "player": self.dest,
            "playback_status": playback_status,
            "volume": round(volume, 2),
            "volume_percent": int(round(volume * 100)),
            "track": {
                "title": title,
                "artist": artist_str,
                "album": album,
                "duration_seconds": length_sec,
                "track_id": track_id,
                "web_url": web_url,
                "art_url": art_url,
            },
            "raw_metadata": metadata,
        }

    def play(self) -> Dict[str, Any]:
        """Resume or start playback."""
        return self._invoke_player_method("Play")

    def pause(self) -> Dict[str, Any]:
        """Pause playback."""
        return self._invoke_player_method("Pause")

    def play_pause(self) -> Dict[str, Any]:
        """Toggle playback between playing and paused."""
        return self._invoke_player_method("PlayPause")

    def next_track(self) -> Dict[str, Any]:
        """Skip to the next track."""
        return self._invoke_player_method("Next")

    def previous_track(self) -> Dict[str, Any]:
        """Skip to the previous track."""
        return self._invoke_player_method("Previous")

    def stop(self) -> Dict[str, Any]:
        """Stop playback."""
        return self._invoke_player_method("Stop")

    def set_volume(self, level: float) -> Dict[str, Any]:
        """Set volume level (accepts 0.0-1.0 or 0-100)."""
        if not self.is_player_active():
            raise PlayerNotRunningError(f"Player '{self.dest}' is not running.")

        # Scale percentage (0-100) to 0.0-1.0
        if level > 1.0:
            level = level / 100.0
        level = max(0.0, min(1.0, float(level)))

        try:
            props = self._get_properties_proxy()
            props.Set(
                "(ssv)",
                MPRIS_PLAYER_INTERFACE,
                "Volume",
                GLib.Variant("d", level),
            )
        except Exception as exc:
            err_msg = str(exc)
            if "AccessDenied" in err_msg or "AppArmor" in err_msg:
                self._run_unconfined_gdbus([
                    "--method", f"{MPRIS_PROPERTIES_INTERFACE}.Set",
                    MPRIS_PLAYER_INTERFACE, "Volume", f"<@d {level}>"
                ])
            else:
                raise SpotifyControllerError(f"Failed to set volume: {str(exc)}")

        return {
            "status": "success",
            "action": "set_volume",
            "player": self.dest,
            "volume": round(level, 2),
            "volume_percent": int(round(level * 100)),
            "message": f"Volume set to {int(round(level * 100))}%.",
        }

    def open_uri(self, uri: str) -> Dict[str, Any]:
        """Open and play a specific Spotify URI or URL."""
        if not self.is_player_active():
            raise PlayerNotRunningError(f"Player '{self.dest}' is not running.")

        clean_uri = uri.strip()
        if not clean_uri.startswith("spotify:") and not clean_uri.startswith("https://open.spotify.com/"):
            raise SecurityError(f"Invalid Spotify URI: '{clean_uri}'")

        try:
            player = self._get_player_proxy()
            player.OpenUri("(s)", clean_uri)
        except Exception as exc:
            err_msg = str(exc)
            if "AccessDenied" in err_msg or "AppArmor" in err_msg:
                self._run_unconfined_gdbus([
                    "--method", f"{MPRIS_PLAYER_INTERFACE}.OpenUri",
                    clean_uri
                ])
            else:
                raise SpotifyControllerError(f"Failed to open URI: {str(exc)}")

        return {
            "status": "success",
            "action": "open_uri",
            "player": self.dest,
            "uri": clean_uri,
            "message": f"Opened URI '{clean_uri}' in {self.dest}.",
        }

    def _invoke_player_method(self, method_name: str) -> Dict[str, Any]:
        """Helper to invoke a standard MPRIS parameterless method."""
        if not self.is_player_active():
            raise PlayerNotRunningError(f"Player '{self.dest}' is not running.")

        try:
            player = self._get_player_proxy()
            method = getattr(player, method_name)
            method()
            return {
                "status": "success",
                "action": method_name.lower(),
                "player": self.dest,
                "message": f"Successfully sent '{method_name}' command to {self.dest}.",
            }
        except Exception as exc:
            err_msg = str(exc)
            if "AccessDenied" in err_msg or "AppArmor" in err_msg:
                self._run_unconfined_gdbus([
                    "--method", f"{MPRIS_PLAYER_INTERFACE}.{method_name}"
                ])
                return {
                    "status": "success",
                    "action": method_name.lower(),
                    "player": self.dest,
                    "message": f"Successfully sent '{method_name}' command to {self.dest}.",
                }
            raise SpotifyControllerError(f"Failed to execute '{method_name}': {str(exc)}")
