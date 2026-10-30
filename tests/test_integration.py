"""Live Read-Only Integration Tests on ASUS ROG Strix G16 Ubuntu GNOME."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.desktop.launcher import list_all_apps_status, check_app_status
from maverick.media.spotify import SpotifyController


class TestLiveIntegration(unittest.TestCase):
    """
    Safe, read-only integration tests that verify real OS environment,
    installed binaries, and session bus connectivity without launching apps.
    """

    def test_live_desktop_environment(self):
        # Verify Wayland or X11 session runtime directory
        uid = os.getuid()
        runtime_dir = f"/run/user/{uid}"
        self.assertTrue(os.path.isdir(runtime_dir))
        bus_path = f"/run/user/{uid}/bus"
        self.assertTrue(os.path.exists(bus_path))

    def test_live_authorized_applications_installed(self):
        # Check that core applications discovered in Phase 1 exist
        status_list = list_all_apps_status()
        status_by_id = {s["id"]: s for s in status_list}

        # Check VS Code
        self.assertIn("code", status_by_id)
        self.assertTrue(status_by_id["code"]["installed"])

        # Check Spotify
        self.assertIn("spotify", status_by_id)
        self.assertTrue(status_by_id["spotify"]["installed"])

        # Check Google Chrome
        self.assertIn("google-chrome", status_by_id)
        self.assertTrue(status_by_id["google-chrome"]["installed"])

        # Check Nautilus
        self.assertIn("nautilus", status_by_id)
        self.assertTrue(status_by_id["nautilus"]["installed"])

    def test_live_dbus_mpris_query(self):
        # Query active players on real session bus without failing if no music is playing
        ctl = SpotifyController()
        players = ctl.list_active_mpris_players()
        self.assertIsInstance(players, list)

    def test_live_spotify_mpris_integration(self):
        ctl = SpotifyController()
        if ctl.is_player_active():
            status = ctl.get_status()
            self.assertEqual(status["status"], "success")
            self.assertEqual(status["player"], "org.mpris.MediaPlayer2.spotify")
            self.assertIn("playback_status", status)
            self.assertIn("track", status)


if __name__ == "__main__":
    unittest.main()
