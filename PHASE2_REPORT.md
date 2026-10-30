# MAVEN JARVIS — Phase 2.2 Security Hardening & Reliability Report

**Date:** 2026-10-30  
**Host Environment:** Ubuntu Linux (ASUS ROG Strix G16, Wayland GNOME, NVIDIA Hybrid GPU)  
**Workspace:** `/home/firza-ilmi/Maverick-DevOS`  
**OpenClaw Gateway:** `127.0.0.1:18789` (`openclaw-gateway.service`, unconfined)  
**Skill Registered:** `jarvis-desktop` (Status: `✓ Ready`, Visible to model: `yes`)  

---

## 1. Security Audit Findings & Remediation

| Finding ID | Severity | Component | Description & Remediation |
| :--- | :--- | :--- | :--- |
| **SEC-01** | **HIGH** | `bin/maverick-ctl` | **Overly broad de-confinement:** The previous wrapper executed the entire Python interpreter under `aa-exec -p unconfined` whenever a subprofile like `vscode (unconfined)` was detected. This de-confined all launched desktop applications (Chrome, terminal, VS Code).<br>**Remediation:** Removed `aa-exec` from `bin/maverick-ctl`. The CLI and all desktop launches now run with full user AppArmor confinement preserved. |
| **SEC-02** | **MEDIUM** | `maverick/media/spotify.py` | **Unbounded unconfined fallback arguments:** The fallback executed `/usr/bin/gdbus` without strict validation of destination, methods, or property values.<br>**Remediation:** Implemented `_validate_unconfined_args()`: strictly validates destination against `^org\.mpris\.MediaPlayer2\.[a-zA-Z0-9_.-]+$`, enforces an allowlist of 9 approved MPRIS methods/properties, validates volume variants `^<@d (0(\.[0-9]+)?\|1(\.0+)?)>$`, and enforces URI regex. Parameterless methods strictly reject any extra arguments. |
| **SEC-03** | **MEDIUM** | `maverick/core/security.py` | **Potential shell metacharacter propagation:** Arguments passed to application launchers lacked an explicit ban on shell metacharacters.<br>**Remediation:** Added global check rejecting `;`, `&`, `|`, `` ` ``, `$`, `\x00`, `\n`, `\r` before any path resolution or command execution. |
| **SEC-04** | **LOW** | `maverick/desktop/launcher.py` | **Process crash on duplicate launch:** Invoking launch on an already-running Spotify instance spawned a secondary Electron process that exited with code 1 due to Chromium single-instance locking.<br>**Remediation:** Added duplicate launch detection. If an application is already running, `launch_app()` returns `status: success, action: already_running` with active PIDs without spawning secondary processes. |

---

## 2. Actual Spotify Live Verification Results

All tests below were performed live against the Spotify instance on the user's Wayland desktop:

| Test Scenario | Executed Command | Live Result |
| :--- | :--- | :--- |
| **Stopped App Launch** | `maverick-ctl app launch spotify` | **Success:** Decoupled process spawned with PID `175013` and arguments `["--no-zygote", "--disable-gpu"]`. |
| **D-Bus Registration** | `gdbus ListNames` | **Success:** `org.mpris.MediaPlayer2.spotify` registered on user session bus. |
| **Duplicate Launch Check** | `maverick-ctl app launch spotify` | **Success:** Returned `action: already_running`, PID `175013`, zero crashes or duplicate windows. |
| **Status & Metadata** | `maverick-ctl spotify status` | **Success:** Returned `playback_status: Paused`, `volume: 0.70`, track *"Tenang"* by *"Judika"*, URL `https://open.spotify.com/track/1TMvBhqekWmWJSxpmUMgFz`. |
| **Live Playback Controls** | `maverick-ctl spotify play`<br>`maverick-ctl spotify next`<br>`maverick-ctl spotify prev`<br>`maverick-ctl spotify pause` | **Success:** State transitioned to `Playing`, skipped next track, returned to previous track, and paused cleanly. |
| **Volume Adjustment** | `maverick-ctl spotify volume 70` | **Success:** Volume updated and verified at 70%. |
| **Unexpected Termination** | `kill -9 <spotify_pid>` | **Success:** `maverick-ctl spotify status` returned `code: PLAYER_NOT_RUNNING` with list of available active players. |

---

## 3. Test Suite & Regression Verification (36 Tests)

Command executed:
```bash
cd /home/firza-ilmi/Maverick-DevOS
python3 -m unittest discover -s tests -v
```

Output:
```
test_cli_app_list ............................................ ok
test_cli_app_status .......................................... ok
test_cli_confirmation_gating_exit_code ....................... ok
test_cli_spotify_players ..................................... ok
test_cli_unauthorized_app_exit_code .......................... ok
test_live_authorized_applications_installed .................. ok
test_live_dbus_mpris_query ................................... ok
test_live_desktop_environment ................................ ok
test_live_spotify_mpris_integration .......................... ok
test_check_app_status ........................................ ok
test_is_binary_available ..................................... ok
test_launch_app_confirmation_required ........................ ok
test_launch_app_duplicate_prevention ......................... ok (REGRESSION)
test_launch_app_not_installed ................................ ok
test_launch_app_spotify_default_args ......................... ok
test_launch_app_success ...................................... ok
test_argument_validation_for_browser_safe_url ................ ok
test_argument_validation_for_browser_unsafe_url .............. ok
test_argument_validation_for_code_path ....................... ok
test_argument_validation_for_disallowed_app .................. ok
test_argument_validation_for_spotify_uri ..................... ok
test_command_injection_rejection ............................. ok (REGRESSION)
test_confirmation_gating ..................................... ok
test_get_authorized_app_rejection ............................ ok
test_get_authorized_app_success .............................. ok
test_spotify_unexpected_uris ................................. ok (REGRESSION)
test_apparmor_access_denied_fallback ......................... ok
test_get_status_snap_url_extraction .......................... ok
test_get_status_success ...................................... ok
test_is_player_active ........................................ ok
test_open_uri ................................................ ok
test_playback_controls ....................................... ok
test_playback_methods_when_not_running ....................... ok
test_set_volume .............................................. ok
test_unconfined_dbus_timeout_scenario ........................ ok (REGRESSION)
test_unconfined_fallback_boundaries .......................... ok (REGRESSION)

Ran 36 tests in 0.669s — ALL PASSED (OK)
```

---

## 4. Remaining Risks & Limitations

1. **Snap AppArmor Policy Updates:** If Canonical or the Spotify Snap maintainers alter the `mpris` slot rule (`peer=(label="{plasmashell,unconfined}")`), the scoped `aa-exec -p unconfined` / `systemd-run --user` helper remains the correct sanctioned Linux mechanism to communicate across the boundary without elevated root privileges.
2. **Wayland Global Shortcuts:** Because Wayland compositors prohibit synthetic global key simulation from unprivileged background agents, Spotify must be controlled strictly via D-Bus/MPRIS rather than synthetic hotkeys. This is fully accommodated by our MPRIS layer.
3. **Chromium GPU Hardware Acceleration on Hybrid Graphics:** Spotify Snap crashes if started without `--disable-gpu` on hybrid Intel/NVIDIA setups under Wayland. This is permanently mitigated by the `default_args: ("--no-zygote", "--disable-gpu")` entry in `config.py`.

---

## 5. Git Commits & Modified Files

- **`~/Maverick-DevOS`** Commit: `23ae06e`
  - `bin/maverick-ctl`: Removed broad CLI de-confinement; preserved standard execution confinement.
  - `maverick/core/security.py`: Added global shell metacharacter rejection.
  - `maverick/desktop/launcher.py`: Added duplicate launch prevention returning `already_running`.
  - `maverick/media/spotify.py`: Bound unconfined execution strictly to validated MPRIS methods and property parameters.
  - `tests/`: Added regression test coverage for injection, unexpected URIs, fallback boundaries, timeouts, and duplicate launch prevention.
- **`~/.openclaw/workspace`** Commit: `977c898`
  - `skills/jarvis-desktop/SKILL.md`: Documented error codes (`PLAYER_NOT_RUNNING`, `SECURITY_VIOLATION`, `CONFIRMATION_REQUIRED`) and duplicate launch behavior.
