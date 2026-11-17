# MAVEN AI Agent — Deployment & Service Management

> **Environment:** Ubuntu Linux 22.04 / 24.04 LTS (systemd User Services)  
> **Production Profiles:** Developer Mode & Background Standalone Daemon  

---

## 1. Systemd User Services

MAVEN is architected to run continuously in the user session without requiring root privileges.

### 1.1 Service Definitions

#### `~/.config/systemd/user/maven-jarvis.service`
Manages the core FastAPI Control Center HUD, cognitive orchestrator, and background voice pipeline:

```ini
[Unit]
Description=Maven JARVIS Holographic Control Center & Agent
After=network.target sound.target
Documentation=https://github.com/Maverick-list/MAVEN_AI_Agent

[Service]
Type=simple
WorkingDirectory=%h/MAVEN_AI_Agent
ExecStart=/usr/bin/python3 -m maverick.cli start --daemon
Restart=on-failure
RestartSec=3
KillMode=mixed
TimeoutStopSec=5
Environment=PYTHONUNBUFFERED=1
Environment=MALLOC_ARENA_MAX=2

[Install]
WantedBy=default.target
```

#### `~/.config/systemd/user/maven-jarvis-gui.service`
Manages the native GTK3 + WebKit2 standalone desktop application shell:

```ini
[Unit]
Description=Maven JARVIS Native Desktop GUI Application
After=maven-jarvis.service
BindsTo=maven-jarvis.service

[Service]
Type=simple
WorkingDirectory=%h/MAVEN_AI_Agent
ExecStart=/usr/bin/python3 -m maverick.desktop.app
Restart=on-failure
RestartSec=3
Environment=GDK_BACKEND=wayland,x11
Environment=WEBKIT_DISABLE_COMPOSITING_MODE=1

[Install]
WantedBy=default.target
```

---

## 2. Managing the Production Services

```bash
# Start MAVEN backend service
systemctl --user start maven-jarvis.service

# Start the native GUI window
systemctl --user start maven-jarvis-gui.service

# Check live service status
systemctl --user status maven-jarvis.service

# View real-time journal logs
journalctl --user -u maven-jarvis.service -f

# Stop all services cleanly
systemctl --user stop maven-jarvis-gui.service maven-jarvis.service
```

---

## 3. Native Debian Packaging (`.deb`)

MAVEN can be built into a standalone Debian package:

```bash
# Build the native .deb installer
python3 scripts/build_deb_package.py

# Install generated package
sudo dpkg -i dist/maven-jarvis_2.2.0_amd64.deb
```
