"""Maverick DevOS - Semantic Screen Intelligence via GNOME AT-SPI.

Inspects visible application hierarchies, extracts interactive UI targets (buttons, entries, menus),
and calculates center coordinates for precision multimodal voice/vision actions ("Maven, click this").
"""

from dataclasses import asdict, dataclass
import threading
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class UIElement:
    name: str
    role: str
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> Tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


class ScreenIntelligence:
    """
    Semantic desktop observation without continuous screenshot polling.
    Queries the native GNOME accessibility bus for high-fidelity interactive targets.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._atspi = None
        self._init_backend()

    def _init_backend(self) -> None:
        try:
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi
            self._atspi = Atspi
        except Exception:
            self._atspi = None

    def find_target(self, query: str) -> Optional[UIElement]:
        """Search desktop accessibility tree for interactive element matching query text."""
        if not self._atspi:
            return None

        q = query.lower().strip()
        desktop = self._atspi.get_desktop(0)
        if not desktop:
            return None

        for app_idx in range(desktop.get_child_count()):
            try:
                app = desktop.get_child_at_index(app_idx)
                if not app:
                    continue
                match = self._search_node(app, q, depth=0)
                if match:
                    return match
            except Exception:
                continue

        return None

    def _search_node(self, node, query: str, depth: int = 0) -> Optional[UIElement]:
        """Recursive breadth-limited search of accessible UI nodes."""
        if depth > 5:
            return None

        try:
            name = (node.get_name() or "").strip().lower()
            role_name = node.get_role_name() or ""

            # Check if interactive and matches query
            if query in name and role_name in ("push button", "text", "entry", "menu item", "link", "page tab"):
                comp = node.get_component_iface()
                if comp:
                    rect = comp.get_extents(self._atspi.CoordType.SCREEN)
                    if rect.width > 5 and rect.height > 5:
                        return UIElement(
                            name=node.get_name(),
                            role=role_name,
                            x=rect.x,
                            y=rect.y,
                            width=rect.width,
                            height=rect.height,
                        )

            # Search children
            child_count = min(15, node.get_child_count())
            for i in range(child_count):
                child = node.get_child_at_index(i)
                if child:
                    res = self._search_node(child, query, depth + 1)
                    if res:
                        return res
        except Exception:
            pass

        return None

    def get_summary(self) -> Dict[str, Any]:
        """High-level summary of active desktop windows and accessibility state."""
        if not self._atspi:
            return {"status": "unavailable", "reason": "AT-SPI not initialized"}

        apps = []
        try:
            desktop = self._atspi.get_desktop(0)
            if desktop:
                for i in range(desktop.get_child_count()):
                    app = desktop.get_child_at_index(i)
                    if app:
                        name = app.get_name()
                        if name and name not in apps:
                            apps.append(name)
        except Exception as e:
            return {"status": "error", "message": str(e)}

        return {
            "status": "ready",
            "active_applications": apps,
            "element_count": len(apps),
        }

    def explain_screen(self) -> Dict[str, Any]:
        """
        Synthesize a natural language explanation of visible windows and interactive targets
        grounded in the native GNOME accessibility tree.
        """
        if not self._atspi:
            return {
                "status": "unavailable",
                "explanation": "Accessibility inspection is not available in headless mode.",
            }

        desktop = self._atspi.get_desktop(0)
        if not desktop:
            return {"status": "unavailable", "explanation": "No accessible desktop session detected."}

        active_windows = []
        interactive_targets = []

        try:
            for i in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(i)
                if not app:
                    continue
                app_name = (app.get_name() or "").strip()
                if not app_name or app_name in ("gnome-shell", "mutter-x11-frames", "gjs"):
                    continue
                active_windows.append(app_name)

                # Inspect top-level interactive targets
                for j in range(min(8, app.get_child_count())):
                    child = app.get_child_at_index(j)
                    if child:
                        c_name = (child.get_name() or "").strip()
                        c_role = child.get_role_name() or ""
                        if c_name and c_role in ("push button", "text", "entry", "menu bar", "page tab"):
                            interactive_targets.append(f"{c_role} '{c_name}' in {app_name}")
        except Exception:
            pass

        if not active_windows:
            explanation = "Your desktop is currently displaying the GNOME desktop background with no active foreground application windows."
        else:
            win_str = ", ".join(active_windows[:4])
            t_str = f" Visible interactive elements include {', '.join(interactive_targets[:3])}." if interactive_targets else ""
            explanation = f"Currently visible applications on your screen include {win_str}.{t_str}"

        return {
            "status": "success",
            "explanation": explanation,
            "active_windows": active_windows,
            "targets": interactive_targets[:6],
        }
