"""Maverick DevOS - Core Configuration and Authorized Application Registry."""

from dataclasses import dataclass
from typing import Dict, List, Optional
import os

# Default timeout for system commands / D-Bus calls in seconds
DEFAULT_TIMEOUT_SECONDS: float = 5.0

# D-Bus Names and Object Paths for MPRIS
DBUS_MPRIS_PREFIX = "org.mpris.MediaPlayer2"
SPOTIFY_DBUS_DEST = f"{DBUS_MPRIS_PREFIX}.spotify"
MPRIS_OBJECT_PATH = "/org/mpris/MediaPlayer2"
MPRIS_PLAYER_INTERFACE = f"{DBUS_MPRIS_PREFIX}.Player"
MPRIS_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
DBUS_CORE_DEST = "org.freedesktop.DBus"
DBUS_CORE_PATH = "/org/freedesktop/DBus"


@dataclass(frozen=True)
class AuthorizedApp:
    id: str
    display_name: str
    binary_path: str
    desktop_file: str
    category: str
    allow_args: bool
    requires_confirmation: bool
    description: str


# Strict Allowlist of Authorized Applications on this Ubuntu GNOME Desktop
AUTHORIZED_APPLICATIONS: Dict[str, AuthorizedApp] = {
    "spotify": AuthorizedApp(
        id="spotify",
        display_name="Spotify",
        binary_path="/snap/bin/spotify",
        desktop_file="spotify_spotify.desktop",
        category="media",
        allow_args=True,  # e.g., Spotify URIs
        requires_confirmation=False,
        description="Music streaming player",
    ),
    "code": AuthorizedApp(
        id="code",
        display_name="Visual Studio Code",
        binary_path="/usr/bin/code",
        desktop_file="code.desktop",
        category="editor",
        allow_args=True,  # e.g., folder paths
        requires_confirmation=False,
        description="Code editor and IDE",
    ),
    "google-chrome": AuthorizedApp(
        id="google-chrome",
        display_name="Google Chrome",
        binary_path="/usr/bin/google-chrome",
        desktop_file="google-chrome.desktop",
        category="browser",
        allow_args=True,  # URLs only
        requires_confirmation=True,  # Opening external URLs requires confirmation
        description="Web browser",
    ),
    "firefox": AuthorizedApp(
        id="firefox",
        display_name="Mozilla Firefox",
        binary_path="/usr/bin/firefox",
        desktop_file="firefox_firefox.desktop",
        category="browser",
        allow_args=True,
        requires_confirmation=True,
        description="Web browser",
    ),
    "claude-desktop": AuthorizedApp(
        id="claude-desktop",
        display_name="Claude Desktop",
        binary_path="/usr/bin/claude-desktop",
        desktop_file="com.anthropic.Claude.desktop",
        category="ai",
        allow_args=False,
        requires_confirmation=False,
        description="Claude AI desktop application",
    ),
    "chatgpt-desktop": AuthorizedApp(
        id="chatgpt-desktop",
        display_name="ChatGPT Desktop",
        binary_path="/snap/bin/chatgpt-desktop",
        desktop_file="chatgpt-desktop_chatgpt-desktop.desktop",
        category="ai",
        allow_args=False,
        requires_confirmation=False,
        description="ChatGPT AI desktop application",
    ),
    "gemini-desktop": AuthorizedApp(
        id="gemini-desktop",
        display_name="Google Gemini Desktop",
        binary_path="/snap/bin/gemini-desktop",
        desktop_file="gemini-desktop_gemini-desktop.desktop",
        category="ai",
        allow_args=False,
        requires_confirmation=False,
        description="Gemini AI desktop application",
    ),
    "nautilus": AuthorizedApp(
        id="nautilus",
        display_name="Files (Nautilus)",
        binary_path="/usr/bin/nautilus",
        desktop_file="org.gnome.Nautilus.desktop",
        category="file-manager",
        allow_args=True,  # folder path only
        requires_confirmation=False,
        description="GNOME file manager",
    ),
    "gnome-terminal": AuthorizedApp(
        id="gnome-terminal",
        display_name="GNOME Terminal",
        binary_path="/usr/bin/gnome-terminal",
        desktop_file="org.gnome.Terminal.desktop",
        category="terminal",
        allow_args=False,  # Uncontrolled terminal execution is gated
        requires_confirmation=True,
        description="Terminal emulator",
    ),
}
