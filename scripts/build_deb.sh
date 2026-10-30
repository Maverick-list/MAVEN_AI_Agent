#!/usr/bin/env bash
# Maven JARVIS - Debian (.deb) Package Builder
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${REPO_DIR}/dist/deb"
PKG_ROOT="${DIST_DIR}/package_root"
DEB_NAME="maven-jarvis_1.0.0_amd64.deb"

echo "=== Building Maven JARVIS Debian Package ==="

# Clean build directory
rm -rf "${PKG_ROOT}"
mkdir -p "${PKG_ROOT}/DEBIAN"
mkdir -p "${PKG_ROOT}/usr/bin"
mkdir -p "${PKG_ROOT}/usr/share/applications"
mkdir -p "${PKG_ROOT}/usr/share/icons/hicolor/scalable/apps"
mkdir -p "${PKG_ROOT}/usr/share/icons/hicolor/48x48/apps"
mkdir -p "${PKG_ROOT}/usr/share/icons/hicolor/64x64/apps"
mkdir -p "${PKG_ROOT}/usr/share/icons/hicolor/128x128/apps"
mkdir -p "${PKG_ROOT}/usr/share/icons/hicolor/256x256/apps"

# 1. DEBIAN/control
cat << 'EOF' > "${PKG_ROOT}/DEBIAN/control"
Package: maven-jarvis
Version: 1.0.0
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Firza Ilmi <firza@maverick-devos.local>
Depends: python3, python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1, libnotify-bin
Description: Maven JARVIS - Ambient AI Desktop Assistant & Holographic Control Center
 Standalone native Linux desktop application for Maven JARVIS, featuring
 WebKit2GTK holographic Control Center, ambient voice assistant integration,
 multimodal vision/gesture controls, and telemetry dashboard on Ubuntu GNOME.
EOF

# 2. DEBIAN/postinst
cat << 'EOF' > "${PKG_ROOT}/DEBIAN/postinst"
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    if which update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if which gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
EOF
chmod 755 "${PKG_ROOT}/DEBIAN/postinst"

# 3. DEBIAN/postrm
cat << 'EOF' > "${PKG_ROOT}/DEBIAN/postrm"
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if which update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if which gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
EOF
chmod 755 "${PKG_ROOT}/DEBIAN/postrm"

# 4. usr/bin/maven-jarvis
cat << 'EOF' > "${PKG_ROOT}/usr/bin/maven-jarvis"
#!/usr/bin/env bash
set -e
# Check local source tree first, then fallback to system location
if [[ -d "/home/firza-ilmi/Maverick-DevOS/maverick" ]]; then
    export PYTHONPATH="/home/firza-ilmi/Maverick-DevOS:${PYTHONPATH}"
elif [[ -d "/opt/maven-jarvis" ]]; then
    export PYTHONPATH="/opt/maven-jarvis:${PYTHONPATH}"
fi
export GDK_BACKEND="wayland,x11"
export WEBKIT_DISABLE_COMPOSITING_MODE=0
exec python3 -m maverick.desktop.app "$@"
EOF
chmod 755 "${PKG_ROOT}/usr/bin/maven-jarvis"

# 5. usr/share/applications/maven-jarvis.desktop
cat << 'EOF' > "${PKG_ROOT}/usr/share/applications/maven-jarvis.desktop"
[Desktop Entry]
Version=1.5
Type=Application
Name=Maven JARVIS
GenericName=AI Desktop Assistant
Comment=Ambient Multimodal AI Desktop Assistant & Holographic Control Center
Exec=/usr/bin/maven-jarvis
Icon=maven-jarvis
Terminal=false
Categories=Utility;AudioVideo;
Keywords=maven;jarvis;ai;assistant;voice;vision;gestures;control;
StartupNotify=true
StartupWMClass=com.maverick.maven.jarvis
Actions=NormalMode;VisionMode;

[Desktop Action NormalMode]
Name=Normal Mode (Physical Input)
Exec=python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/vision/mode/deactivate', data=b'{}')"

[Desktop Action VisionMode]
Name=Vision Mode (Hand Gestures)
Exec=python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/vision/mode/activate', data=b'{}')"
EOF

# 6. Icons
cp "${REPO_DIR}/assets/icons/maven-jarvis.svg" "${PKG_ROOT}/usr/share/icons/hicolor/scalable/apps/maven-jarvis.svg"
cp "${REPO_DIR}/assets/icons/maven-jarvis-48.png" "${PKG_ROOT}/usr/share/icons/hicolor/48x48/apps/maven-jarvis.png"
cp "${REPO_DIR}/assets/icons/maven-jarvis-64.png" "${PKG_ROOT}/usr/share/icons/hicolor/64x64/apps/maven-jarvis.png"
cp "${REPO_DIR}/assets/icons/maven-jarvis-128.png" "${PKG_ROOT}/usr/share/icons/hicolor/128x128/apps/maven-jarvis.png"
cp "${REPO_DIR}/assets/icons/maven-jarvis-256.png" "${PKG_ROOT}/usr/share/icons/hicolor/256x256/apps/maven-jarvis.png"

# Build .deb with dpkg-deb
dpkg-deb --build --root-owner-group "${PKG_ROOT}" "${DIST_DIR}/${DEB_NAME}"

# Clean up packaging scratch root
rm -rf "${PKG_ROOT}"

echo "=== Debian Package Successfully Built ==="
echo "Artifact: ${DIST_DIR}/${DEB_NAME}"
ls -lh "${DIST_DIR}/${DEB_NAME}"
