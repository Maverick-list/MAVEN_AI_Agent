# Maverick DevOS — Desktop Automation Layer (Phase 2)

Maverick DevOS provides a secure, minimal, and testable desktop control layer for the MAVEN JARVIS assistant running on Ubuntu GNOME under Wayland.

## Features

- **Application Lifecycle & Process Discovery**: Non-invasive status tracking and safe launching for authorized desktop applications (`spotify`, `code`, `claude-desktop`, `chatgpt-desktop`, `gemini-desktop`, `google-chrome`, `firefox`, `nautilus`, `gnome-terminal`).
- **Wayland-Safe Execution**: Decoupled subprocess management (`start_new_session=True`) passing display and session bus environment variables (`WAYLAND_DISPLAY`, `DISPLAY`, `DBUS_SESSION_BUS_ADDRESS`).
- **D-Bus MPRIS Media Controller**: Native integration via GNOME `Gio.DBusProxy` (with fallback to `gdbus`) for Spotify playback controls (Play, Pause, PlayPause, Next, Previous, Stop, Volume, and Spotify URI resolution).
- **Strict Allowlisting & Sanitization**: Zero shell interpolation; rejects unauthorized binaries, command injection patterns, unapproved flags, or invalid paths/URLs.
- **Consequential Action Confirmation Gate**: High-impact actions (e.g., launching terminal emulators, external browsers with arbitrary URLs) return exit code 2 and require an explicit `--confirmed` flag.
- **Structured JSON Interface**: All outputs are formatted as deterministic JSON suitable for agent parsing.
- **OpenClaw Skill Integration**: Registered as `jarvis-desktop` skill (`~/.openclaw/workspace/skills/jarvis-desktop/SKILL.md`).

---

## Directory Structure

```
~/Maverick-DevOS/
├── bin/
│   └── maverick-ctl             # Executable CLI wrapper
├── maverick/
│   ├── core/
│   │   ├── config.py            # Authorized applications registry & D-Bus constants
│   │   └── security.py          # Allowlist validation, URL/URI sanitizer & confirmation gating
│   ├── desktop/
│   │   └── launcher.py          # Process discovery (/proc inspection) & safe launcher
│   ├── media/
│   │   └── spotify.py           # D-Bus MPRIS player proxy & media controls
│   └── cli.py                   # Argument parser & JSON output handler
├── tests/
│   ├── test_security.py         # Unit tests for policy enforcement & argument injection
│   ├── test_launcher.py         # Unit tests with mock Popen & process lookup
│   ├── test_spotify.py          # Unit tests with mock D-Bus MPRIS proxies
│   ├── test_cli.py              # Unit tests for CLI entrypoints & exit codes
│   └── test_integration.py      # Live read-only tests verifying host applications & D-Bus
└── README.md
```

---

## CLI Usage

### Application Management
```bash
# List all authorized applications and running state
maverick-ctl app list --pretty

# Inspect specific application
maverick-ctl app status spotify --pretty

# Launch routine application (e.g. VS Code with directory argument)
maverick-ctl app launch code --args "/home/firza-ilmi/Maverick-DevOS" --pretty

# Launch consequential application (requires --confirmed)
maverick-ctl app launch gnome-terminal --confirmed --pretty
```

### Spotify / MPRIS Control
```bash
# Query playback status and current track
maverick-ctl spotify status --pretty

# Playback controls
maverick-ctl spotify play
maverick-ctl spotify pause
maverick-ctl spotify toggle
maverick-ctl spotify next
maverick-ctl spotify prev

# Set volume (0 - 100 or 0.0 - 1.0)
maverick-ctl spotify volume 80

# Play specific track/playlist URI
maverick-ctl spotify open-uri "spotify:track:4cOdK2wGLETKBW3PvgPWqT"

# List active media players on the session bus
maverick-ctl spotify players --pretty
```

---

## Testing

Run the entire test suite (27 unit and integration tests):
```bash
cd /home/firza-ilmi/Maverick-DevOS
python3 -m unittest discover -s tests -v
```

---

## Security & Consequential Actions Policy

| Action | Allowlist Policy | Confirmation Required |
| :--- | :--- | :--- |
| Querying application status | Allowed for registry IDs | No |
| Querying Spotify / MPRIS | Allowed on session bus | No |
| Spotify playback & volume | Allowed | No |
| Launching Spotify / VS Code / Nautilus / AI Desktops | Allowed for local paths | No |
| Launching Web Browsers (`google-chrome`, `firefox`) | Allowed for HTTPS URLs | **Yes** (`--confirmed`) |
| Launching Terminal (`gnome-terminal`) | Allowed | **Yes** (`--confirmed`) |
| Arbitrary shell binaries | **Blocked** | N/A |
| Path traversal / non-existent target paths | **Blocked** | N/A |

---

## Rollback Instructions

To roll back Phase 2 cleanly:
1. Remove OpenClaw skill:
   ```bash
   rm -rf /home/firza-ilmi/.openclaw/workspace/skills/jarvis-desktop
   rm -f /home/firza-ilmi/.openclaw/skills/jarvis-desktop
   ```
2. Remove Maverick-DevOS repository:
   ```bash
   rm -rf /home/firza-ilmi/Maverick-DevOS
   ```
3. OpenClaw and channel configurations remain unaffected.
