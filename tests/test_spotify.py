"""Unit tests for Maverick DevOS Spotify & MPRIS Controller."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maverick.media.spotify import (
    SpotifyController,
    SpotifyControllerError,
    PlayerNotRunningError,
)
from maverick.core.security import SecurityError


class TestSpotifyController(unittest.TestCase):
    """Test Spotify MPRIS D-Bus commands and error handling with mocks."""

    def setUp(self):
        self.ctl = SpotifyController(dest="org.mpris.MediaPlayer2.spotify")

    @patch.object(SpotifyController, "list_active_mpris_players")
    def test_is_player_active(self, mock_list):
        mock_list.return_value = ["org.mpris.MediaPlayer2.spotify"]
        self.assertTrue(self.ctl.is_player_active())

        mock_list.return_value = ["org.mpris.MediaPlayer2.other"]
        self.assertFalse(self.ctl.is_player_active())

    @patch.object(SpotifyController, "is_player_active")
    def test_playback_methods_when_not_running(self, mock_active):
        mock_active.return_value = False
        with self.assertRaises(PlayerNotRunningError):
            self.ctl.get_status()

        with self.assertRaises(PlayerNotRunningError):
            self.ctl.play()

        with self.assertRaises(PlayerNotRunningError):
            self.ctl.set_volume(0.5)

    @patch.object(SpotifyController, "is_player_active")
    @patch.object(SpotifyController, "_get_properties_proxy")
    def test_get_status_success(self, mock_props_proxy, mock_active):
        mock_active.return_value = True

        props_mock = MagicMock()
        # Mock Get responses
        def mock_get(sig, iface, prop_name):
            if prop_name == "PlaybackStatus":
                return "Playing"
            elif prop_name == "Volume":
                return 0.85
            elif prop_name == "Metadata":
                return {
                    "xesam:title": "Bohemian Rhapsody",
                    "xesam:artist": ["Queen"],
                    "xesam:album": "A Night at the Opera",
                    "mpris:trackid": "spotify:track:1234567890",
                    "mpris:length": 354000000,
                    "mpris:artUrl": "https://i.scdn.co/image/abc",
                }
            return None

        props_mock.Get.side_effect = mock_get
        mock_props_proxy.return_value = props_mock

        status = self.ctl.get_status()
        self.assertEqual(status["status"], "success")
        self.assertEqual(status["playback_status"], "Playing")
        self.assertEqual(status["volume"], 0.85)
        self.assertEqual(status["volume_percent"], 85)
        self.assertEqual(status["track"]["title"], "Bohemian Rhapsody")
        self.assertEqual(status["track"]["artist"], "Queen")
        self.assertEqual(status["track"]["duration_seconds"], 354.0)
        self.assertEqual(status["track"]["web_url"], "https://open.spotify.com/track/1234567890")

    @patch.object(SpotifyController, "is_player_active")
    @patch.object(SpotifyController, "_get_player_proxy")
    def test_playback_controls(self, mock_player_proxy, mock_active):
        mock_active.return_value = True
        player_mock = MagicMock()
        mock_player_proxy.return_value = player_mock

        res_play = self.ctl.play()
        self.assertEqual(res_play["status"], "success")
        player_mock.Play.assert_called_once()

        res_pause = self.ctl.pause()
        self.assertEqual(res_pause["status"], "success")
        player_mock.Pause.assert_called_once()

        res_next = self.ctl.next_track()
        self.assertEqual(res_next["status"], "success")
        player_mock.Next.assert_called_once()

        res_prev = self.ctl.previous_track()
        self.assertEqual(res_prev["status"], "success")
        player_mock.Previous.assert_called_once()

    @patch.object(SpotifyController, "is_player_active")
    @patch.object(SpotifyController, "_get_properties_proxy")
    def test_set_volume(self, mock_props_proxy, mock_active):
        mock_active.return_value = True
        props_mock = MagicMock()
        mock_props_proxy.return_value = props_mock

        # Percentage (0-100)
        res = self.ctl.set_volume(75)
        self.assertEqual(res["volume"], 0.75)
        self.assertEqual(res["volume_percent"], 75)

        # Float (0.0-1.0)
        res_float = self.ctl.set_volume(0.4)
        self.assertEqual(res_float["volume"], 0.4)
        self.assertEqual(res_float["volume_percent"], 40)

    @patch.object(SpotifyController, "is_player_active")
    @patch.object(SpotifyController, "_get_player_proxy")
    def test_open_uri(self, mock_player_proxy, mock_active):
        mock_active.return_value = True
        player_mock = MagicMock()
        mock_player_proxy.return_value = player_mock

        # Valid URI
        res = self.ctl.open_uri("spotify:track:4cOdK2wGLETKBW3PvgPWqT")
        self.assertEqual(res["status"], "success")
        player_mock.OpenUri.assert_called_with("(s)", "spotify:track:4cOdK2wGLETKBW3PvgPWqT")

        # Invalid URI should be rejected by security
        with self.assertRaises(SecurityError):
            self.ctl.open_uri("file:///path/to/bad")

    @patch.object(SpotifyController, "is_player_active")
    @patch.object(SpotifyController, "_get_properties_proxy")
    def test_get_status_snap_url_extraction(self, mock_props_proxy, mock_active):
        mock_active.return_value = True
        props_mock = MagicMock()
        mock_props_proxy.return_value = props_mock

        # Test extraction with /com/spotify/track/ path
        def mock_get_snap(sig, iface, prop_name):
            if prop_name == "PlaybackStatus":
                return "Paused"
            elif prop_name == "Volume":
                return 0.5
            elif prop_name == "Metadata":
                return {
                    "xesam:title": "Song",
                    "xesam:artist": ["Artist"],
                    "xesam:album": "Album",
                    "mpris:trackid": "/com/spotify/track/abc123xyz",
                    "mpris:length": 100000000,
                    "xesam:url": "https://open.spotify.com/track/abc123xyz",
                }
            return None

        props_mock.Get.side_effect = mock_get_snap
        status_snap = self.ctl.get_status()
        self.assertEqual(status_snap["track"]["web_url"], "https://open.spotify.com/track/abc123xyz")

    @patch.object(SpotifyController, "is_player_active")
    @patch.object(SpotifyController, "_get_player_proxy")
    @patch.object(SpotifyController, "_run_unconfined_gdbus")
    def test_apparmor_access_denied_fallback(self, mock_unconfined, mock_player_proxy, mock_active):
        mock_active.return_value = True
        player_mock = MagicMock()
        # Simulate GLib GError AccessDenied from AppArmor
        player_mock.Play.side_effect = Exception("GDBus.Error:org.freedesktop.DBus.Error.AccessDenied: An AppArmor policy prevents this sender")
        mock_player_proxy.return_value = player_mock

        res = self.ctl.play()
        self.assertEqual(res["status"], "success")
        mock_unconfined.assert_called_once_with(["--method", "org.mpris.MediaPlayer2.Player.Play"])


    def test_unconfined_fallback_boundaries(self):
        # 1. Reject invalid destination
        with self.assertRaises(SecurityError):
            SpotifyController(dest="org.freedesktop.systemd1")

        with self.assertRaises(SecurityError):
            SpotifyController(dest="org.mpris.MediaPlayer2; rm -rf /")

        # 2. Reject unapproved method
        with self.assertRaises(SecurityError):
            self.ctl._validate_unconfined_args(["--method", "org.freedesktop.DBus.Peer.Ping"])

        with self.assertRaises(SecurityError):
            self.ctl._validate_unconfined_args(["--method", "com.malicious.Execute"])

        # 3. Reject extra arguments on parameterless method
        with self.assertRaises(SecurityError):
            self.ctl._validate_unconfined_args(["--method", "org.mpris.MediaPlayer2.Player.Play", "extra_arg"])

        # 4. Reject unauthorized property on Properties.Get
        with self.assertRaises(SecurityError):
            self.ctl._validate_unconfined_args([
                "--method", "org.freedesktop.DBus.Properties.Get",
                "org.mpris.MediaPlayer2.Player", "UnauthorizedProp"
            ])

        # 5. Reject unauthorized property or value on Properties.Set
        with self.assertRaises(SecurityError):
            self.ctl._validate_unconfined_args([
                "--method", "org.freedesktop.DBus.Properties.Set",
                "org.mpris.MediaPlayer2.Player", "PlaybackStatus", "<'Playing'>"
            ])

        with self.assertRaises(SecurityError):
            self.ctl._validate_unconfined_args([
                "--method", "org.freedesktop.DBus.Properties.Set",
                "org.mpris.MediaPlayer2.Player", "Volume", "<@d 999.0>"
            ])

    @patch("subprocess.run")
    def test_unconfined_dbus_timeout_scenario(self, mock_subrun):
        import subprocess
        mock_subrun.side_effect = subprocess.TimeoutExpired(cmd=["gdbus"], timeout=5.0)

        with self.assertRaises(SpotifyControllerError) as ctx:
            self.ctl._run_unconfined_gdbus(["--method", "org.mpris.MediaPlayer2.Player.Play"])
        self.assertIn("failed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
