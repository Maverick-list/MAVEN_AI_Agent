#!/usr/bin/env python3
"""
Maverick DevOS - GNOME Global Shortcut Toggle Script for Vision Control Mode.

Bound to Super + Shift + V in GNOME Wayland settings.
Calls the active Maven Control Center API to toggle between NORMAL MODE and VISION CONTROL MODE.
"""

import json
import sys
import urllib.request
import urllib.error

API_URL = "http://127.0.0.1:8765/api/vision/mode/toggle"


def main():
    try:
        req = urllib.request.Request(
            API_URL,
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            mode = data.get("current_mode", "unknown")
            msg = data.get("response") or data.get("message") or f"Switched to {mode}"
            print(f"[Maven Vision Toggle] Mode: {mode.upper()} - {msg}")
            sys.exit(0)
    except urllib.error.URLError:
        # Dashboard not running; fall back to local direct toggle if possible
        try:
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from maverick.vision.vision_controller import VisionController
            vc = VisionController()
            res = vc.mode_manager.toggle_mode()
            print(f"[Maven Vision Toggle (Direct)] Mode: {res.get('current_mode')}")
            sys.exit(0)
        except Exception as e:
            print(f"[Maven Vision Toggle Error] Could not connect to Maven daemon: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()

