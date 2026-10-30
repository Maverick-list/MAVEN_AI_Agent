"""Maverick DevOS - Native Linux Desktop Application Shell for Maven JARVIS.

Integrates the Maven Control Center into an authentic Ubuntu desktop application
using PyGObject (GTK 3.0 + WebKit2GTK 4.1).

Features:
- Standalone native desktop window with GNOME HeaderBar.
- WebKit2 view hosting http://127.0.0.1:8765 with zero white-flash dark styling.
- Live backend connection status badge (🟢 CONNECTED / 🟡 CONNECTING / 🔴 OFFLINE).
- Instant mode switching (Normal vs Vision) and Emergency Stop controls.
- Background persistence: closing window hides to background with desktop notification.
- Single-instance activation: relaunching Dash icon restores existing window.
- Graceful offline fallback screen with automatic reconnection polling.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

# GTK and WebKit2 version requirements must precede imports
try:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import Gtk, Gdk, WebKit2, GLib, Gio, GdkPixbuf
    _HAS_GTK_WEBKIT = True
except Exception as _import_err:
    _HAS_GTK_WEBKIT = False
    _IMPORT_ERROR_MSG = str(_import_err)

logger = logging.getLogger("maverick.desktop.app")

APP_ID = "com.maverick.maven.jarvis"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8765"
DEFAULT_WINDOW_WIDTH = 1440
DEFAULT_WINDOW_HEIGHT = 900
MIN_WINDOW_WIDTH = 1024
MIN_WINDOW_HEIGHT = 680

DARK_BG_RGBA = (0.027, 0.039, 0.071, 1.0)  # #070a12
CYAN_ACCENT_HEX = "#00e5ff"

OFFLINE_FALLBACK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Maven JARVIS - Connecting...</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: radial-gradient(circle at 50% 40%, #0d1527 0%, #070a12 80%);
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Ubuntu, sans-serif;
      height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      overflow: hidden;
    }
    .hud-ring {
      width: 140px;
      height: 140px;
      border: 3px solid rgba(0, 229, 255, 0.2);
      border-top: 3px solid #00e5ff;
      border-right: 3px solid #7c3aed;
      border-radius: 50%;
      animation: spin 2s linear infinite;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 28px;
      box-shadow: 0 0 35px rgba(0, 229, 255, 0.3);
    }
    .hud-inner {
      width: 90px;
      height: 90px;
      border: 2px dashed rgba(0, 229, 255, 0.4);
      border-radius: 50%;
      animation: spin-reverse 4s linear infinite;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 32px;
    }
    @keyframes spin { 100% { transform: rotate(360deg); } }
    @keyframes spin-reverse { 100% { transform: rotate(-360deg); } }
    h1 {
      font-size: 26px;
      font-weight: 700;
      letter-spacing: 3px;
      color: #00e5ff;
      text-transform: uppercase;
      margin-bottom: 10px;
      text-shadow: 0 0 15px rgba(0, 229, 255, 0.5);
    }
    p {
      color: #94a3b8;
      font-size: 14px;
      letter-spacing: 1px;
      margin-bottom: 24px;
    }
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 16px;
      background: rgba(245, 158, 11, 0.1);
      border: 1px solid rgba(245, 158, 11, 0.3);
      border-radius: 999px;
      color: #f59e0b;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 1px;
      margin-bottom: 30px;
    }
    .pulse-dot {
      width: 8px;
      height: 8px;
      background: #f59e0b;
      border-radius: 50%;
      box-shadow: 0 0 10px #f59e0b;
      animation: pulse 1.5s infinite;
    }
    @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.85); } }
    .btn {
      background: rgba(0, 229, 255, 0.1);
      color: #00e5ff;
      border: 1px solid rgba(0, 229, 255, 0.4);
      padding: 10px 24px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 1px;
      cursor: pointer;
      transition: all 0.2s ease;
      text-decoration: none;
    }
    .btn:hover {
      background: #00e5ff;
      color: #070a12;
      box-shadow: 0 0 20px rgba(0, 229, 255, 0.5);
    }
  </style>
</head>
<body>
  <div class="hud-ring">
    <div class="hud-inner">⚡</div>
  </div>
  <h1>Maven JARVIS</h1>
  <p>Connecting to Ambient AI Subsystems...</p>
  <div class="status-badge">
    <div class="pulse-dot"></div>
    <span>POLLING LOCAL BACKEND (127.0.0.1:8765)</span>
  </div>
  <button class="btn" onclick="location.reload()">Retry Connection</button>

  <script>
    // Automatic retry check
    setInterval(async () => {
      try {
        const res = await fetch('/api/status', { cache: 'no-store' });
        if (res.ok) {
          window.location.href = '/';
        }
      } catch (err) {
        // Backend not ready yet
      }
    }, 1500);
  </script>
</body>
</html>
"""

CSS_STYLING = """
headerbar {
    background: #070a12;
    border-bottom: 1px solid #1e293b;
    padding: 4px 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.6);
}
headerbar .title {
    color: #00e5ff;
    font-weight: 800;
    font-size: 14px;
    letter-spacing: 1.5px;
}
headerbar .subtitle {
    color: #94a3b8;
    font-size: 11px;
    letter-spacing: 0.5px;
}
button.status-badge {
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid #10b981;
    color: #10b981;
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
}
button.status-badge.connecting {
    background: rgba(245, 158, 11, 0.12);
    border-color: #f59e0b;
    color: #f59e0b;
}
button.status-badge.offline {
    background: rgba(239, 68, 68, 0.15);
    border-color: #ef4444;
    color: #ef4444;
}
button.action-btn {
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid #334155;
    color: #cbd5e1;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}
button.action-btn:hover {
    background: #1e293b;
    border-color: #00e5ff;
    color: #00e5ff;
}
button.action-btn.active-vision {
    background: rgba(124, 58, 237, 0.2);
    border-color: #a855f7;
    color: #d8b4fe;
}
button.action-btn.estop {
    background: rgba(239, 68, 68, 0.15);
    border-color: #ef4444;
    color: #ef4444;
}
button.action-btn.estop:hover {
    background: #ef4444;
    color: #ffffff;
}
"""


def _find_icon_path() -> Optional[str]:
    """Find the best available application icon path."""
    candidates = [
        "/home/firza-ilmi/.local/share/icons/hicolor/256x256/apps/maven-jarvis.png",
        os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/maven-jarvis.png"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "icons", "maven-jarvis-256.png"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "icons", "maven-jarvis.png"),
        "/usr/share/icons/hicolor/256x256/apps/maven-jarvis.png",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def send_desktop_notification(title: str, message: str, urgency: str = "normal") -> None:
    """Send a non-intrusive desktop notification via notify-send."""
    icon_path = _find_icon_path() or "maven-jarvis"
    try:
        cmd = ["notify-send", "-a", "Maven JARVIS", "-u", urgency, "-i", icon_path, title, message]
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        logger.debug(f"notify-send failed: {exc}")


if _HAS_GTK_WEBKIT:
    class MavenJarvisWindow(Gtk.ApplicationWindow):
        """Native GTK3 Application Window for Maven JARVIS."""

        def __init__(self, app: Gtk.Application, backend_url: str = DEFAULT_BACKEND_URL):
            super().__init__(application=app, title="Maven JARVIS")
            self.app = app
            self.backend_url = backend_url.rstrip("/")
            self.is_connected = False
            self.active_mode = "NORMAL"
            self._poller_active = True

            self.set_default_size(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
            self.set_size_request(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
            self.set_position(Gtk.WindowPosition.CENTER)

            # Setup Window Icon
            self._setup_icon()

            # Build HeaderBar and WebView
            self._build_headerbar()
            self._build_webview()
            self._apply_css()

            # Window Event Handlers
            self.connect("delete-event", self._on_delete_event)
            self.connect("key-press-event", self._on_key_press)

            # Initial status check and periodic background poller
            self._trigger_health_poll()
            GLib.timeout_add_seconds(2, self._trigger_health_poll)

        def _setup_icon(self) -> None:
            """Configure application window icon."""
            icon_path = _find_icon_path()
            if icon_path and os.path.isfile(icon_path):
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(icon_path)
                    self.set_icon(pixbuf)
                    Gtk.Window.set_default_icon(pixbuf)
                except Exception as err:
                    logger.warning(f"Failed to load icon pixbuf from {icon_path}: {err}")
            else:
                self.set_icon_name("maven-jarvis")

        def _build_headerbar(self) -> None:
            """Build GNOME HeaderBar with title, indicators, and controls."""
            self.headerbar = Gtk.HeaderBar()
            self.headerbar.set_show_close_button(True)
            self.headerbar.set_title("Maven JARVIS")
            self.headerbar.set_subtitle("Ambient AI Desktop Assistant")

            # Status Badge Button
            self.status_btn = Gtk.Button(label="🟡 CONNECTING...")
            self.status_btn.get_style_context().add_class("status-badge")
            self.status_btn.get_style_context().add_class("connecting")
            self.status_btn.set_tooltip_text(f"Backend: {self.backend_url}\nClick to probe/reconnect.")
            self.status_btn.connect("clicked", self._on_status_clicked)
            self.headerbar.pack_start(self.status_btn)

            # Mode Toggle Button (Normal / Vision)
            self.mode_btn = Gtk.Button(label="⇄ NORMAL")
            self.mode_btn.get_style_context().add_class("action-btn")
            self.mode_btn.set_tooltip_text("Toggle between Normal (Physical) and Vision (Hand Gestures) mode")
            self.mode_btn.connect("clicked", self._on_mode_toggle_clicked)
            self.headerbar.pack_start(self.mode_btn)

            # Emergency Stop Button
            self.estop_btn = Gtk.Button(label="🛑 E-STOP")
            self.estop_btn.get_style_context().add_class("action-btn")
            self.estop_btn.get_style_context().add_class("estop")
            self.estop_btn.set_tooltip_text("Emergency Stop: Immediately freeze virtual input and disarm vision")
            self.estop_btn.connect("clicked", self._on_estop_clicked)
            self.headerbar.pack_start(self.estop_btn)

            # Refresh Button
            self.refresh_btn = Gtk.Button()
            refresh_icon = Gtk.Image.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
            self.refresh_btn.set_image(refresh_icon)
            self.refresh_btn.set_tooltip_text("Reload Control Center (Ctrl+R / F5)")
            self.refresh_btn.get_style_context().add_class("action-btn")
            self.refresh_btn.connect("clicked", lambda _: self.reload_webview())
            self.headerbar.pack_end(self.refresh_btn)

            # App Menu Button
            self.menu_btn = Gtk.MenuButton()
            menu_icon = Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON)
            self.menu_btn.set_image(menu_icon)
            self.menu_btn.set_tooltip_text("Application Options")
            self.menu_btn.get_style_context().add_class("action-btn")
            self._build_menu()
            self.headerbar.pack_end(self.menu_btn)

            self.set_titlebar(self.headerbar)

        def _build_menu(self) -> None:
            """Build application drop-down menu."""
            menu = Gtk.Menu()

            item_reload = Gtk.MenuItem(label="Reload Interface (Ctrl+R)")
            item_reload.connect("activate", lambda _: self.reload_webview())
            menu.append(item_reload)

            item_fs = Gtk.MenuItem(label="Toggle Fullscreen (F11)")
            item_fs.connect("activate", lambda _: self._toggle_fullscreen())
            menu.append(item_fs)

            menu.append(Gtk.SeparatorMenuItem())

            item_vision = Gtk.MenuItem(label="Toggle Vision Mode (Super+Shift+V)")
            item_vision.connect("activate", lambda _: self._on_mode_toggle_clicked(None))
            menu.append(item_vision)

            item_estop = Gtk.MenuItem(label="Trigger Emergency Stop")
            item_estop.connect("activate", lambda _: self._on_estop_clicked(None))
            menu.append(item_estop)

            menu.append(Gtk.SeparatorMenuItem())

            item_hide = Gtk.MenuItem(label="Hide to Background (Ctrl+W)")
            item_hide.connect("activate", lambda _: self._hide_to_background())
            menu.append(item_hide)

            item_quit = Gtk.MenuItem(label="Quit Maven Desktop (Ctrl+Q)")
            item_quit.connect("activate", lambda _: self.app.quit())
            menu.append(item_quit)

            menu.show_all()
            self.menu_btn.set_popup(menu)

        def _build_webview(self) -> None:
            """Initialize WebKit2 WebView with dark styling and accelerated canvas."""
            # Settings
            settings = WebKit2.Settings()
            settings.set_enable_developer_extras(True)
            settings.set_enable_webgl(True)
            if hasattr(settings, "set_enable_smooth_scrolling"):
                settings.set_enable_smooth_scrolling(True)

            self.webview = WebKit2.WebView.new_with_settings(settings)

            # Prevent white flashing: Dark background
            bg_rgba = Gdk.RGBA(*DARK_BG_RGBA)
            self.webview.set_background_color(bg_rgba)

            # WebKit Signals
            self.webview.connect("load-failed", self._on_load_failed)

            # Scrolled container
            self.scrolled = Gtk.ScrolledWindow()
            self.scrolled.add(self.webview)
            self.add(self.scrolled)

            # Initial load
            self.load_url(self.backend_url)

        def _apply_css(self) -> None:
            """Apply dark cyberpunk GTK styling."""
            css_provider = Gtk.CssProvider()
            try:
                css_provider.load_from_data(CSS_STYLING.encode("utf-8"))
                screen = Gdk.Screen.get_default()
                if screen:
                    Gtk.StyleContext.add_provider_for_screen(
                        screen,
                        css_provider,
                        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
                    )
            except Exception as err:
                logger.warning(f"Failed to apply GTK CSS styling: {err}")

        def load_url(self, url: str) -> None:
            """Load the specified URL into WebKit."""
            self.webview.load_uri(url)

        def reload_webview(self) -> None:
            """Reload the WebKit web view."""
            self.webview.reload()

        def _on_load_failed(self, webview, load_event, failing_uri, error) -> bool:
            """Display styled offline/connecting screen when backend is unreachable."""
            # Ignore harmless navigation cancellations (e.g. reload or redirect)
            if hasattr(WebKit2, "NetworkError") and getattr(error, "code", None) == WebKit2.NetworkError.CANCELLED:
                return False
            logger.info(f"WebKit load-failed for {failing_uri}: {error.message}")
            self.webview.load_html(OFFLINE_FALLBACK_HTML, self.backend_url)
            self._update_connection_status(False)
            return True

        def _toggle_fullscreen(self) -> None:
            """Toggle window fullscreen."""
            state = self.get_window().get_state() if self.get_window() else 0
            if state & Gdk.WindowState.FULLSCREEN:
                self.unfullscreen()
            else:
                self.fullscreen()

        def _on_key_press(self, widget, event) -> bool:
            """Handle keyboard shortcuts."""
            key = event.keyval
            ctrl = bool(event.state & Gdk.ModifierType.CONTROL_MASK)

            if key == Gdk.KEY_F5 or (ctrl and key in (Gdk.KEY_r, Gdk.KEY_R)):
                self.reload_webview()
                return True
            if key == Gdk.KEY_F11:
                self._toggle_fullscreen()
                return True
            if ctrl and key in (Gdk.KEY_w, Gdk.KEY_W):
                self._hide_to_background()
                return True
            if ctrl and key in (Gdk.KEY_q, Gdk.KEY_Q):
                self.app.quit()
                return True
            if key == Gdk.KEY_Escape:
                state = self.get_window().get_state() if self.get_window() else 0
                if state & Gdk.WindowState.FULLSCREEN:
                    self.unfullscreen()
                    return True
            return False

        def _on_delete_event(self, widget, event) -> bool:
            """Intercept close button: hide to background to keep assistant alive."""
            self._hide_to_background()
            return True  # Prevent window destruction

        def _hide_to_background(self) -> None:
            """Hide window and notify user that Maven remains active in background."""
            self.hide()
            send_desktop_notification(
                "Maven JARVIS Active",
                "Running in the background. Say 'Maven' or click launcher to reopen.",
            )

        def _on_status_clicked(self, widget) -> None:
            """Manual status probe on click."""
            threading.Thread(target=self._query_backend_status, daemon=True).start()

        def _on_mode_toggle_clicked(self, widget) -> None:
            """Send POST request to toggle vision mode."""
            def _post():
                try:
                    req = urllib.request.Request(
                        f"{self.backend_url}/api/vision/mode/toggle",
                        data=b"{}",
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        mode = res.get("current_mode") or res.get("active_mode") or "normal"
                        GLib.idle_add(self._update_mode_button, mode)
                except Exception as err:
                    logger.warning(f"Failed to toggle mode: {err}")
            threading.Thread(target=_post, daemon=True).start()

        def _on_estop_clicked(self, widget) -> None:
            """Send POST request to trigger emergency stop."""
            def _post():
                try:
                    req = urllib.request.Request(
                        f"{self.backend_url}/api/vision/emergency-stop",
                        data=b"{}",
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        send_desktop_notification("EMERGENCY STOP TRIGGERED", "Vision input immediately disarmed.", "critical")
                        self._trigger_health_poll()
                except Exception as err:
                    logger.warning(f"Failed to trigger emergency stop: {err}")
            threading.Thread(target=_post, daemon=True).start()

        def _trigger_health_poll(self) -> bool:
            """GLib timer callback to query backend status in background thread."""
            if not self._poller_active:
                return False
            threading.Thread(target=self._query_backend_status, daemon=True).start()
            return True

        def _query_backend_status(self) -> None:
            """Query /api/status from backend daemon."""
            url = f"{self.backend_url}/api/status"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "MavenDesktop/1.0"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        vision_info = data.get("vision", {})
                        mode = vision_info.get("mode", "NORMAL")
                        GLib.idle_add(self._update_ui_state, True, mode)
                        return
            except Exception:
                pass
            GLib.idle_add(self._update_ui_state, False, "NORMAL")

        def _update_ui_state(self, is_connected: bool, mode: str) -> None:
            """Update status badge and mode button on the GTK main loop."""
            self._update_connection_status(is_connected)
            self._update_mode_button(mode)

        def _update_connection_status(self, is_connected: bool) -> None:
            """Update connection indicator label and styling."""
            was_connected = self.is_connected
            self.is_connected = is_connected

            ctx = self.status_btn.get_style_context()
            ctx.remove_class("connecting")
            ctx.remove_class("offline")

            if is_connected:
                self.status_btn.set_label("🟢 CONNECTED")
                self.status_btn.set_tooltip_text(f"Connected to {self.backend_url}\nClick to refresh.")
                # If we just regained connection from offline, reload webview
                if not was_connected:
                    self.load_url(self.backend_url)
            else:
                ctx.add_class("offline")
                self.status_btn.set_label("🔴 OFFLINE")
                self.status_btn.set_tooltip_text(f"Cannot reach {self.backend_url}\nClick to retry.")

        def _update_mode_button(self, mode: str) -> None:
            """Update mode button label and styling."""
            is_vision = "vision" in str(mode).lower()
            self.active_mode = "VISION" if is_vision else "NORMAL"
            ctx = self.mode_btn.get_style_context()
            if is_vision:
                ctx.add_class("active-vision")
                self.mode_btn.set_label("⇄ VISION")
                self.mode_btn.set_tooltip_text("Current Mode: VISION (Gestures Active)\nClick to switch to NORMAL.")
            else:
                ctx.remove_class("active-vision")
                self.mode_btn.set_label("⇄ NORMAL")
                self.mode_btn.set_tooltip_text("Current Mode: NORMAL (Physical Control)\nClick to switch to VISION.")


    class MavenJarvisApp(Gtk.Application):
        """Maven JARVIS Standalone GTK3 Application."""

        def __init__(self, backend_url: str = DEFAULT_BACKEND_URL):
            super().__init__(
                application_id=APP_ID,
                flags=Gio.ApplicationFlags.FLAGS_NONE,
            )
            self.backend_url = backend_url
            self.window: Optional[MavenJarvisWindow] = None

        def do_activate(self) -> None:
            """Handle application activation (Dash click or command invocation)."""
            if self.window is None:
                self.window = MavenJarvisWindow(self, backend_url=self.backend_url)
                self.window.show_all()
            else:
                # Present existing window if already running
                self.window.show_all()
                self.window.deiconify()
                self.window.present()

        def do_startup(self) -> None:
            """Perform application startup initialization."""
            Gtk.Application.do_startup(self)


def check_gui_available() -> bool:
    """Check if graphical display is available."""
    return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))


def run_desktop_app(backend_url: str = DEFAULT_BACKEND_URL, argv: Optional[list] = None) -> int:
    """Launch the Maven JARVIS native desktop application."""
    if not _HAS_GTK_WEBKIT:
        print(f"Error: Missing GTK3 / WebKit2GTK dependencies: {_IMPORT_ERROR_MSG}", file=sys.stderr)
        return 1

    if not check_gui_available():
        print(
            "Error: No graphical display detected ($DISPLAY or $WAYLAND_DISPLAY is unset).\n"
            "Maven JARVIS desktop requires an active desktop session.\n"
            "To view the Control Center via browser, start the server and navigate to http://127.0.0.1:8765",
            file=sys.stderr,
        )
        return 1

    app = MavenJarvisApp(backend_url=backend_url)
    args = argv or [sys.argv[0]]
    return app.run(args)


def main() -> None:
    """Entry point when executed directly."""
    import argparse
    parser = argparse.ArgumentParser(description="Maven JARVIS Native Linux Desktop Application")
    parser.add_argument("--url", default=DEFAULT_BACKEND_URL, help=f"Backend URL (default: {DEFAULT_BACKEND_URL})")
    args, unknown = parser.parse_known_args()
    sys.exit(run_desktop_app(backend_url=args.url, argv=[sys.argv[0]] + unknown))


if __name__ == "__main__":
    main()
