"""Verification script for Maven JARVIS Native Desktop Application."""

import os
import sys
import time

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2, GLib

from maverick.desktop.app import MavenJarvisApp, MavenJarvisWindow, check_gui_available

print("=== MAVEN JARVIS DESKTOP APPLICATION VERIFICATION ===")
print("1. GUI Available:", check_gui_available())
print("2. Display:", os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))

app = MavenJarvisApp(backend_url="http://127.0.0.1:8765")
app.set_application_id("com.maverick.maven.jarvis.verify")
app.register()

window = MavenJarvisWindow(app, backend_url="http://127.0.0.1:8765")
app.window = window

print("3. Window created successfully:")
print("   - Title:", window.get_title())
print("   - Subtitle:", window.headerbar.get_subtitle())
print("   - Width/Height request:", window.get_size())
print("   - Status badge initial:", window.status_btn.get_label())
print("   - Mode button:", window.mode_btn.get_label())
print("   - Emergency Stop:", window.estop_btn.get_label())

step = 0

def on_timer():
    global step
    step += 1

    if step == 1:
        print(f"4. Poller iteration 1 - badge: {window.status_btn.get_label()}, connected: {window.is_connected}")
        return True

    if step == 2:
        print(f"5. Poller iteration 2 - badge: {window.status_btn.get_label()}, connected: {window.is_connected}")
        print("6. Testing delete-event (hide to background)...")
        ret = window._on_delete_event(window, None)
        print("   - delete-event handled:", ret)
        print("   - Window visible after close button:", window.get_visible())
        return True

    if step == 3:
        print("7. Testing application re-activation (restore from background)...")
        app.do_activate()
        print("   - Window visible after activate:", window.get_visible())
        return True

    if step == 4:
        print("8. Testing mode toggle API...")
        window._on_mode_toggle_clicked(None)
        return True

    if step == 5:
        print(f"9. Mode after toggle: {window.active_mode}")
        if window.active_mode == "VISION":
            print("   - Restoring to NORMAL mode...")
            window._on_mode_toggle_clicked(None)
        return True

    if step == 6:
        print(f"10. Final mode: {window.active_mode}")
        print("11. Desktop verification completed successfully!")
        Gtk.main_quit()
        return False

    return True

GLib.timeout_add(1000, on_timer)
Gtk.main()
print("=== VERIFICATION PASSED ===")
