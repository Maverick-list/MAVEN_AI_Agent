"""Unit and integration tests for Maven JARVIS Native Linux Desktop Application."""

import os
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from maverick.desktop.app import (
    APP_ID,
    DEFAULT_BACKEND_URL,
    DEFAULT_WINDOW_WIDTH,
    DEFAULT_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    MIN_WINDOW_HEIGHT,
    OFFLINE_FALLBACK_HTML,
    _find_icon_path,
    check_gui_available,
    send_desktop_notification,
    _HAS_GTK_WEBKIT,
)

if _HAS_GTK_WEBKIT:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import Gtk, WebKit2
    from maverick.desktop.app import MavenJarvisApp, MavenJarvisWindow


class TestDesktopAppStatic(unittest.TestCase):
    """Test desktop application configuration, constants, and utilities."""

    def test_app_constants(self):
        """Verify standard application ID and default geometry."""
        self.assertEqual(APP_ID, "com.maverick.maven.jarvis")
        self.assertEqual(DEFAULT_BACKEND_URL, "http://127.0.0.1:8765")
        self.assertEqual(DEFAULT_WINDOW_WIDTH, 1440)
        self.assertEqual(DEFAULT_WINDOW_HEIGHT, 900)
        self.assertEqual(MIN_WINDOW_WIDTH, 1024)
        self.assertEqual(MIN_WINDOW_HEIGHT, 680)

    def test_find_icon_path(self):
        """Verify icon locator discovers installed or repository icon."""
        icon_path = _find_icon_path()
        self.assertIsNotNone(icon_path)
        self.assertTrue(os.path.isfile(icon_path))
        self.assertTrue(icon_path.endswith(".png"))

    def test_check_gui_available(self):
        """Verify display check reads WAYLAND_DISPLAY or DISPLAY."""
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ""}):
            self.assertTrue(check_gui_available())
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "", "DISPLAY": ":0"}):
            self.assertTrue(check_gui_available())
        with patch.dict(os.environ, {"WAYLAND_DISPLAY": "", "DISPLAY": ""}):
            self.assertFalse(check_gui_available())

    def test_offline_fallback_html(self):
        """Verify offline HTML includes cyberpunk styling and auto-retry."""
        self.assertIn("Maven JARVIS", OFFLINE_FALLBACK_HTML)
        self.assertIn("POLLING LOCAL BACKEND", OFFLINE_FALLBACK_HTML)
        self.assertIn("setInterval", OFFLINE_FALLBACK_HTML)
        self.assertIn("/api/status", OFFLINE_FALLBACK_HTML)

    @patch("subprocess.run")
    def test_send_desktop_notification(self, mock_run):
        """Verify notify-send execution parameters."""
        send_desktop_notification("Test Title", "Test Message", urgency="critical")
        self.assertTrue(mock_run.called)
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[0], "notify-send")
        self.assertIn("Test Title", call_args)
        self.assertIn("Test Message", call_args)
        self.assertIn("-u", call_args)
        self.assertIn("critical", call_args)


@unittest.skipUnless(_HAS_GTK_WEBKIT and check_gui_available(), "GTK/WebKit2 or Display not available")
class TestDesktopAppWindow(unittest.TestCase):
    """Test native GTK3 Window creation, widgets, and lifecycle."""

    @classmethod
    def setUpClass(cls):
        # Initialize GTK with test application ID
        cls.app = MavenJarvisApp(backend_url="http://127.0.0.1:8765")
        cls.app.set_application_id("com.maverick.maven.jarvis.test")
        cls.app.register()

    def setUp(self):
        self.window = MavenJarvisWindow(self.app, backend_url="http://127.0.0.1:8765")

    def tearDown(self):
        self.window._poller_active = False
        self.window.destroy()

    def test_window_properties(self):
        """Verify window title, size, and header bar."""
        self.assertEqual(self.window.get_title(), "Maven JARVIS")
        self.assertIsNotNone(self.window.headerbar)
        self.assertEqual(self.window.headerbar.get_title(), "Maven JARVIS")
        self.assertEqual(self.window.headerbar.get_subtitle(), "Ambient AI Desktop Assistant")

    def test_headerbar_widgets(self):
        """Verify action buttons and badges exist on HeaderBar."""
        self.assertIsNotNone(self.window.status_btn)
        self.assertIsNotNone(self.window.mode_btn)
        self.assertIsNotNone(self.window.estop_btn)
        self.assertIsNotNone(self.window.refresh_btn)
        self.assertIsNotNone(self.window.menu_btn)

    def test_status_update(self):
        """Verify status badge updates between online and offline."""
        self.window._update_connection_status(True)
        self.assertTrue(self.window.is_connected)
        self.assertIn("CONNECTED", self.window.status_btn.get_label())

        self.window._update_connection_status(False)
        self.assertFalse(self.window.is_connected)
        self.assertIn("OFFLINE", self.window.status_btn.get_label())

    def test_mode_update(self):
        """Verify mode button label and styles update dynamically."""
        self.window._update_mode_button("NORMAL")
        self.assertEqual(self.window.active_mode, "NORMAL")
        self.assertIn("NORMAL", self.window.mode_btn.get_label())

        self.window._update_mode_button("VISION")
        self.assertEqual(self.window.active_mode, "VISION")
        self.assertIn("VISION", self.window.mode_btn.get_label())

    @patch("maverick.desktop.app.send_desktop_notification")
    def test_delete_event_hides_window(self, mock_notif):
        """Verify close button hides window instead of destroying it."""
        mock_event = MagicMock()
        ret = self.window._on_delete_event(self.window, mock_event)
        self.assertTrue(ret)  # Cancel destruction
        self.assertFalse(self.window.get_visible())
        self.assertTrue(mock_notif.called)


class TestDesktopPackaging(unittest.TestCase):
    """Test desktop file specification, icon hierarchy, and Debian package."""

    def test_desktop_file_exists(self):
        """Verify .desktop file exists in repository and user applications."""
        repo_desktop = "/home/firza-ilmi/Maverick-DevOS/assets/desktop/maven-jarvis.desktop"
        user_desktop = os.path.expanduser("~/.local/share/applications/maven-jarvis.desktop")
        self.assertTrue(os.path.isfile(repo_desktop))
        self.assertTrue(os.path.isfile(user_desktop))

        with open(repo_desktop, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Name=Maven JARVIS", content)
            self.assertIn("StartupWMClass=com.maverick.maven.jarvis", content)
            self.assertIn("Icon=maven-jarvis", content)

    def test_icons_hierarchy(self):
        """Verify required icons exist across standard resolutions."""
        icons_dir = "/home/firza-ilmi/Maverick-DevOS/assets/icons"
        expected = [
            "maven-jarvis.svg",
            "maven-jarvis.png",
            "maven-jarvis-48.png",
            "maven-jarvis-64.png",
            "maven-jarvis-128.png",
            "maven-jarvis-256.png",
        ]
        for name in expected:
            path = os.path.join(icons_dir, name)
            self.assertTrue(os.path.isfile(path), f"Missing icon: {path}")

    def test_debian_package_artifact(self):
        """Verify built Debian package exists and has correct metadata."""
        deb_path = "/home/firza-ilmi/Maverick-DevOS/dist/deb/maven-jarvis_1.0.0_amd64.deb"
        self.assertTrue(os.path.isfile(deb_path), "Debian package not found")

        # Run dpkg-deb -I
        result = subprocess.run(["dpkg-deb", "-I", deb_path], capture_output=True, text=True, check=True)
        self.assertIn("Package: maven-jarvis", result.stdout)
        self.assertIn("Version: 1.0.0", result.stdout)
        self.assertIn("Architecture: amd64", result.stdout)
        self.assertIn("gir1.2-gtk-3.0", result.stdout)
        self.assertIn("gir1.2-webkit2-4.1", result.stdout)

        # Run dpkg-deb -c
        result_c = subprocess.run(["dpkg-deb", "-c", deb_path], capture_output=True, text=True, check=True)
        self.assertIn("./usr/bin/maven-jarvis", result_c.stdout)
        self.assertIn("./usr/share/applications/maven-jarvis.desktop", result_c.stdout)
        self.assertIn("./usr/share/icons/hicolor/scalable/apps/maven-jarvis.svg", result_c.stdout)
        self.assertIn("./usr/share/icons/hicolor/256x256/apps/maven-jarvis.png", result_c.stdout)


if __name__ == "__main__":
    unittest.main()
