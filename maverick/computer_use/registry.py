"""Maverick DevOS - Application Compatibility Registry.

Maintains capability profiles, preferred interaction strategies, keyboard shortcut maps,
and accessibility health ratings for common Linux desktop applications:
- GNOME Files (Nautilus)
- Google Chrome & Mozilla Firefox
- Visual Studio Code
- GNOME Terminal
- LibreOffice
- GNOME Settings (Control Center)
- System File Chooser / Dialogs
- Evince PDF Viewer
- Generic GTK and Qt desktop applications
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import os
import shutil
from typing import Any, Dict, List, Optional


class InteractionMethod(Enum):
    """Primary interaction channels supported by applications."""
    ACCESSIBILITY = "accessibility"        # AT-SPI2 semantic tree (Preferred)
    CLI_NATIVE = "cli_native"              # Direct command line / D-Bus control
    BROWSER_CDP = "browser_cdp"            # Chrome DevTools Protocol
    KEYBOARD_SHORTCUTS = "keyboard_nav"    # Accelerated keyboard navigation
    COORDINATE_INPUT = "coordinate_input"  # Pointer coordinate fallback
    VISUAL_OCR = "visual_ocr"              # Screenshot & optical recognition


class AccessibilityHealth(Enum):
    """Accessibility compliance level of target applications."""
    EXCELLENT = "excellent"    # 100% semantic tree (GTK4, GNOME native apps)
    GOOD = "good"              # Rich accessibility tree (VS Code Electron, Chromium)
    MODERATE = "moderate"      # Partial accessibility (Qt without full bridge)
    LIMITED = "limited"        # Canvas/webgl rendering without accessible DOM
    UNKNOWN = "unknown"


@dataclass
class ApplicationProfile:
    """Detailed compatibility record for a Linux application."""
    app_id: str
    display_name: str
    binary: str
    desktop_file: str
    primary_method: InteractionMethod
    supported_methods: List[InteractionMethod]
    accessibility_health: AccessibilityHealth
    default_shortcuts: Dict[str, str] = field(default_factory=dict)
    quirks: List[str] = field(default_factory=list)
    launch_args: List[str] = field(default_factory=list)
    recommended_strategy: str = "accessibility_first"

    def is_installed(self) -> bool:
        """Check if binary exists in system PATH."""
        return shutil.which(self.binary) is not None or os.path.exists(self.binary)

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to serializable format."""
        d = asdict(self)
        d["primary_method"] = self.primary_method.value
        d["supported_methods"] = [m.value for m in self.supported_methods]
        d["accessibility_health"] = self.accessibility_health.value
        d["is_installed"] = self.is_installed()
        return d


class ApplicationCompatibilityRegistry:
    """Registry managing capability profiles and interaction strategies for Linux apps."""

    def __init__(self):
        self._profiles: Dict[str, ApplicationProfile] = {}
        self._register_default_profiles()

    def register(self, profile: ApplicationProfile) -> None:
        """Register or update an application profile."""
        self._profiles[profile.app_id] = profile

    def get_profile(self, identifier: str) -> Optional[ApplicationProfile]:
        """Look up profile by app_id, binary name, or window title substring."""
        if not identifier:
            return None
        clean = identifier.lower().strip()
        # Direct key match
        if clean in self._profiles:
            return self._profiles[clean]
        # Match binary or alias
        for p in self._profiles.values():
            if clean == p.binary.lower() or clean in p.display_name.lower():
                return p
        # Substring match on window title
        for p in self._profiles.values():
            if p.app_id in clean or p.binary in clean:
                return p
        return None

    def list_profiles(self) -> List[Dict[str, Any]]:
        """List all registered application profiles with installation state."""
        return [p.to_dict() for p in self._profiles.values()]

    def _register_default_profiles(self) -> None:
        """Register verified Linux desktop application profiles."""

        # 1. Visual Studio Code
        self.register(ApplicationProfile(
            app_id="code",
            display_name="Visual Studio Code",
            binary="/usr/bin/code",
            desktop_file="code.desktop",
            primary_method=InteractionMethod.ACCESSIBILITY,
            supported_methods=[
                InteractionMethod.ACCESSIBILITY,
                InteractionMethod.KEYBOARD_SHORTCUTS,
                InteractionMethod.CLI_NATIVE,
            ],
            accessibility_health=AccessibilityHealth.GOOD,
            default_shortcuts={
                "command_palette": "Ctrl+Shift+P",
                "quick_open": "Ctrl+P",
                "save": "Ctrl+S",
                "save_all": "Ctrl+K S",
                "close_tab": "Ctrl+W",
                "new_file": "Ctrl+N",
                "terminal_toggle": "Ctrl+`",
                "find": "Ctrl+F",
                "replace": "Ctrl+H",
            },
            quirks=[
                "Chromium/Electron accessibility tree updates asynchronously.",
                "Command palette (Ctrl+Shift+P) is the most deterministic navigation mechanism.",
            ],
            recommended_strategy="hybrid_accessibility_shortcuts",
        ))

        # 2. GNOME Files (Nautilus)
        self.register(ApplicationProfile(
            app_id="nautilus",
            display_name="GNOME Files",
            binary="/usr/bin/nautilus",
            desktop_file="org.gnome.Nautilus.desktop",
            primary_method=InteractionMethod.ACCESSIBILITY,
            supported_methods=[
                InteractionMethod.ACCESSIBILITY,
                InteractionMethod.KEYBOARD_SHORTCUTS,
                InteractionMethod.CLI_NATIVE,
            ],
            accessibility_health=AccessibilityHealth.EXCELLENT,
            default_shortcuts={
                "new_folder": "Ctrl+Shift+N",
                "new_tab": "Ctrl+T",
                "close_window": "Ctrl+W",
                "search": "Ctrl+F",
                "properties": "Alt+Return",
                "delete": "Delete",
                "open_item": "Return",
                "location_entry": "Ctrl+L",
            },
            quirks=[
                "Native GTK4 accessibility tree provides 100% element identification.",
                "Ctrl+L activates direct path text entry for guaranteed directory navigation.",
            ],
            recommended_strategy="accessibility_first",
        ))

        # 3. GNOME Terminal
        self.register(ApplicationProfile(
            app_id="gnome-terminal",
            display_name="GNOME Terminal",
            binary="/usr/bin/gnome-terminal",
            desktop_file="org.gnome.Terminal.desktop",
            primary_method=InteractionMethod.KEYBOARD_SHORTCUTS,
            supported_methods=[
                InteractionMethod.KEYBOARD_SHORTCUTS,
                InteractionMethod.ACCESSIBILITY,
                InteractionMethod.CLI_NATIVE,
            ],
            accessibility_health=AccessibilityHealth.GOOD,
            default_shortcuts={
                "copy": "Ctrl+Shift+C",
                "paste": "Ctrl+Shift+V",
                "new_tab": "Ctrl+Shift+T",
                "new_window": "Ctrl+Shift+N",
                "close_tab": "Ctrl+Shift+W",
                "clear": "Ctrl+L",
                "interrupt": "Ctrl+C",
            },
            quirks=[
                "Clipboard operations require Shift modifier (Ctrl+Shift+C / Ctrl+Shift+V).",
                "Standard Ctrl+C sends SIGINT to terminal processes instead of copying.",
            ],
            recommended_strategy="keyboard_first",
        ))

        # 4. Google Chrome
        self.register(ApplicationProfile(
            app_id="google-chrome",
            display_name="Google Chrome",
            binary="/usr/bin/google-chrome",
            desktop_file="google-chrome.desktop",
            primary_method=InteractionMethod.BROWSER_CDP,
            supported_methods=[
                InteractionMethod.BROWSER_CDP,
                InteractionMethod.ACCESSIBILITY,
                InteractionMethod.KEYBOARD_SHORTCUTS,
            ],
            accessibility_health=AccessibilityHealth.GOOD,
            default_shortcuts={
                "new_tab": "Ctrl+T",
                "close_tab": "Ctrl+W",
                "reopen_tab": "Ctrl+Shift+T",
                "focus_url_bar": "Ctrl+L",
                "reload": "Ctrl+R",
                "find": "Ctrl+F",
                "inspect": "Ctrl+Shift+I",
            },
            quirks=[
                "Use isolated CDP automation profile to avoid disrupting user's main Chrome session.",
                "CDP provides DOM-level precision exceeding accessibility bus.",
            ],
            recommended_strategy="cdp_first",
        ))

        # 5. Mozilla Firefox
        self.register(ApplicationProfile(
            app_id="firefox",
            display_name="Mozilla Firefox",
            binary="/usr/bin/firefox",
            desktop_file="firefox.desktop",
            primary_method=InteractionMethod.ACCESSIBILITY,
            supported_methods=[
                InteractionMethod.ACCESSIBILITY,
                InteractionMethod.KEYBOARD_SHORTCUTS,
            ],
            accessibility_health=AccessibilityHealth.GOOD,
            default_shortcuts={
                "new_tab": "Ctrl+T",
                "close_tab": "Ctrl+W",
                "focus_url_bar": "Ctrl+L",
                "reload": "Ctrl+R",
                "find": "Ctrl+F",
            },
            quirks=[
                "Firefox supports full AT-SPI web content tree when enabled.",
            ],
            recommended_strategy="accessibility_first",
        ))

        # 6. LibreOffice
        self.register(ApplicationProfile(
            app_id="libreoffice",
            display_name="LibreOffice",
            binary="/usr/bin/libreoffice",
            desktop_file="libreoffice-startcenter.desktop",
            primary_method=InteractionMethod.ACCESSIBILITY,
            supported_methods=[
                InteractionMethod.ACCESSIBILITY,
                InteractionMethod.KEYBOARD_SHORTCUTS,
            ],
            accessibility_health=AccessibilityHealth.GOOD,
            default_shortcuts={
                "save": "Ctrl+S",
                "print": "Ctrl+P",
                "find": "Ctrl+F",
                "select_all": "Ctrl+A",
            },
            quirks=[
                "Supports standard Java/UNO accessibility bridge.",
            ],
            recommended_strategy="accessibility_first",
        ))

        # 7. GNOME Control Center (Settings)
        self.register(ApplicationProfile(
            app_id="gnome-control-center",
            display_name="GNOME Settings",
            binary="/usr/bin/gnome-control-center",
            desktop_file="org.gnome.Settings.desktop",
            primary_method=InteractionMethod.ACCESSIBILITY,
            supported_methods=[
                InteractionMethod.ACCESSIBILITY,
                InteractionMethod.KEYBOARD_SHORTCUTS,
            ],
            accessibility_health=AccessibilityHealth.EXCELLENT,
            default_shortcuts={
                "search": "Ctrl+F",
                "close": "Ctrl+W",
            },
            quirks=[
                "Native libadwaita / GTK4 widgets with rich accessibility roles.",
            ],
            recommended_strategy="accessibility_first",
        ))

        # 8. File Chooser & Modal Dialogs
        self.register(ApplicationProfile(
            app_id="file-chooser",
            display_name="File Chooser Dialog",
            binary="builtin",
            desktop_file="",
            primary_method=InteractionMethod.ACCESSIBILITY,
            supported_methods=[
                InteractionMethod.ACCESSIBILITY,
                InteractionMethod.KEYBOARD_SHORTCUTS,
            ],
            accessibility_health=AccessibilityHealth.EXCELLENT,
            default_shortcuts={
                "location_toggle": "Ctrl+L",
                "confirm": "Return",
                "cancel": "Escape",
            },
            quirks=[
                "Pressing Ctrl+L in GTK file choosers reveals path entry for reliable typing.",
            ],
            recommended_strategy="accessibility_first",
        ))

        # 9. Evince PDF Viewer
        self.register(ApplicationProfile(
            app_id="evince",
            display_name="Document Viewer (Evince)",
            binary="/usr/bin/evince",
            desktop_file="org.gnome.Evince.desktop",
            primary_method=InteractionMethod.ACCESSIBILITY,
            supported_methods=[
                InteractionMethod.ACCESSIBILITY,
                InteractionMethod.KEYBOARD_SHORTCUTS,
            ],
            accessibility_health=AccessibilityHealth.GOOD,
            default_shortcuts={
                "find": "Ctrl+F",
                "zoom_in": "Ctrl++",
                "zoom_out": "Ctrl+-",
                "fullscreen": "F11",
            },
            quirks=[],
            recommended_strategy="accessibility_first",
        ))
