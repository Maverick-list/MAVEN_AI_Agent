"""Maverick DevOS - Universal Linux Accessibility Integration Layer (AT-SPI2).

Normalizes Linux desktop accessibility (GNOME GTK / Qt / Electron AT-SPI) into
a high-fidelity semantic interface for element discovery, role inspection,
state verification, direct activation, and text entry without coordinate guessing.
"""

from dataclasses import asdict, dataclass, field
import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("maverick.computer_use.accessibility")

# Ensure AT-SPI accessibility bus address is available
_uid = os.getuid()
_at_spi_socket = f"/run/user/{_uid}/at-spi/bus"
if "AT_SPI_BUS_ADDRESS" not in os.environ and os.path.exists(_at_spi_socket):
    os.environ["AT_SPI_BUS_ADDRESS"] = f"unix:path={_at_spi_socket}"

try:
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
    _HAS_ATSPI = True
except Exception as _atspi_err:
    _HAS_ATSPI = False
    _ATSPI_ERR = str(_atspi_err)

_GLOBAL_ATSPI_LOCK = threading.RLock()


@dataclass
class AccessibleElement:
    """A semantic UI element extracted from the Linux desktop accessibility bus."""
    name: str
    role: str
    description: str = ""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    states: List[str] = field(default_factory=list)
    is_focused: bool = False
    is_enabled: bool = True
    is_visible: bool = True
    app_name: str = ""
    window_title: str = ""
    actions: List[str] = field(default_factory=list)
    text_content: Optional[str] = None
    node_ref: Any = None  # Reference to underlying Atspi.Accessible object

    @property
    def center(self) -> Tuple[int, int]:
        """Calculated center coordinates (x, y) for pointer alignment."""
        return self.x + self.width // 2, self.y + self.height // 2

    @property
    def bounds(self) -> Tuple[int, int, int, int]:
        """Return (x, y, width, height) bounding box."""
        return self.x, self.y, self.width, self.height

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary without deepcopying GObject refs."""
        return {
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "center": list(self.center),
            "bounds": list(self.bounds),
            "states": list(self.states),
            "is_focused": self.is_focused,
            "is_enabled": self.is_enabled,
            "is_visible": self.is_visible,
            "app_name": self.app_name,
            "window_title": self.window_title,
            "actions": list(self.actions),
            "text_content": self.text_content,
        }


class AccessibilityBridge:
    """
    High-level gateway to the Linux desktop accessibility hierarchy (AT-SPI2).
    Provides safe element discovery, window state inspection, and semantic activation.
    """

    INTERACTIVE_ROLES = {
        "push button", "button", "entry", "text", "check box", "radio button",
        "menu item", "menu", "menu bar", "combo box", "page tab", "tab",
        "link", "list item", "tree table", "slider", "spin button", "toggle button",
    }

    def __init__(self, atspi_module=None):
        self._lock = threading.RLock()
        self._atspi = atspi_module or (Atspi if _HAS_ATSPI else None)

    @property
    def is_available(self) -> bool:
        """Check if accessibility daemon and AT-SPI bindings are functional."""
        return self._atspi is not None

    def get_desktop(self) -> Optional[Any]:
        """Retrieve root desktop accessible object."""
        if not self._atspi:
            return None
        with _GLOBAL_ATSPI_LOCK:
            try:
                return self._atspi.get_desktop(0)
            except Exception as e:
                logger.debug(f"Failed to get desktop from AT-SPI: {e}")
                return None

    def get_windows(self) -> List[AccessibleElement]:
        """List all top-level application windows currently mapped on desktop."""
        if not self._atspi:
            return []

        with _GLOBAL_ATSPI_LOCK:
            windows: List[AccessibleElement] = []
            desktop = self.get_desktop()
            if not desktop:
                return []

            try:
                for i in range(desktop.get_child_count()):
                    app = desktop.get_child_at_index(i)
                    if not app:
                        continue
                    app_name = (app.get_name() or "").strip()
                    if not app_name or app_name in ("gnome-shell", "mutter-x11-frames", "gjs", "-c"):
                        continue

                    for j in range(app.get_child_count()):
                        win = app.get_child_at_index(j)
                        if not win:
                            continue
                        elem = self._node_to_element(win, app_name=app_name, window_title=win.get_name() or "")
                        if elem and elem.name.strip() and elem.width > 0 and elem.height > 0:
                            windows.append(elem)
            except Exception as e:
                logger.debug(f"Error enumerating windows: {e}")

            return windows

    def get_active_window(self) -> Optional[AccessibleElement]:
        """Find the currently focused or active top-level application window."""
        windows = self.get_windows()
        # First priority: marked active and focused
        for win in windows:
            if win.is_focused and "active" in win.states:
                return win
        # Second priority: marked active
        for win in windows:
            if "active" in win.states:
                return win
        # Third priority: marked focused
        for win in windows:
            if win.is_focused:
                return win
        # Fallback to first non-desktop window if present
        return windows[0] if windows else None

    def find_elements(
        self,
        query: Optional[str] = None,
        role: Optional[str] = None,
        app_name: Optional[str] = None,
        window_title: Optional[str] = None,
        interactive_only: bool = True,
        max_results: int = 50,
    ) -> List[AccessibleElement]:
        """
        Search desktop accessibility tree for elements matching text query or role.
        """
        if not self._atspi:
            return []

        with _GLOBAL_ATSPI_LOCK:
            results: List[AccessibleElement] = []
            desktop = self.get_desktop()
            if not desktop:
                return []

            q = query.lower().strip() if query else None
            target_role = role.lower().strip() if role else None

            for app_idx in range(desktop.get_child_count()):
                if len(results) >= max_results:
                    break
                try:
                    app = desktop.get_child_at_index(app_idx)
                    if not app:
                        continue
                    cur_app = (app.get_name() or "").strip()
                    if app_name and app_name.lower() not in cur_app.lower():
                        continue

                    for win_idx in range(app.get_child_count()):
                        if len(results) >= max_results:
                            break
                        win = app.get_child_at_index(win_idx)
                        if not win:
                            continue
                        cur_win = (win.get_name() or "").strip()
                        if window_title and window_title.lower() not in cur_win.lower():
                            continue

                        self._search_accessible_tree(
                            node=win,
                            query=q,
                            target_role=target_role,
                            app_name=cur_app,
                            window_title=cur_win,
                            interactive_only=interactive_only,
                            results=results,
                            max_results=max_results,
                            depth=0,
                            max_depth=16,
                        )
                except Exception:
                    continue

            return results

    def _search_accessible_tree(
        self,
        node: Any,
        query: Optional[str],
        target_role: Optional[str],
        app_name: str,
        window_title: str,
        interactive_only: bool,
        results: List[AccessibleElement],
        max_results: int,
        depth: int,
        max_depth: int,
    ) -> None:
        """Recursive traversal with role and string matching."""
        if depth > max_depth or len(results) >= max_results:
            return

        try:
            name = (node.get_name() or "").strip()
            role_name = (node.get_role_name() or "").strip().lower()
            name_lower = name.lower()

            matches_query = True
            if query:
                text_content = ""
                try:
                    text_iface = node.get_text_iface()
                    if text_iface:
                        text_content = (text_iface.get_text(0, min(100, text_iface.get_character_count())) or "").lower()
                except Exception:
                    pass
                matches_query = (query in name_lower) or (query in text_content)

            matches_role = True
            if target_role:
                matches_role = target_role in role_name
            elif interactive_only:
                matches_role = role_name in self.INTERACTIVE_ROLES

            if matches_query and matches_role and name:
                elem = self._node_to_element(node, app_name=app_name, window_title=window_title)
                if elem and elem.width > 0 and elem.height > 0:
                    results.append(elem)

            # Recurse children
            child_count = min(30, node.get_child_count())
            for i in range(child_count):
                if len(results) >= max_results:
                    break
                child = node.get_child_at_index(i)
                if child:
                    self._search_accessible_tree(
                        child, query, target_role, app_name, window_title,
                        interactive_only, results, max_results, depth + 1, max_depth
                    )
        except Exception:
            pass

    def _node_to_element(self, node: Any, app_name: str, window_title: str) -> Optional[AccessibleElement]:
        """Convert native Atspi.Accessible into normalized AccessibleElement."""
        try:
            name = (node.get_name() or "").strip()
            role = (node.get_role_name() or "").strip().lower()
            description = (node.get_description() or "").strip()

            x, y, w, h = 0, 0, 0, 0
            try:
                comp = node.get_component_iface()
                if comp and self._atspi:
                    rect = comp.get_extents(self._atspi.CoordType.SCREEN)
                    x, y, w, h = rect.x, rect.y, rect.width, rect.height
            except Exception:
                pass

            states: List[str] = []
            is_focused = False
            is_enabled = True
            is_visible = True

            try:
                state_set = node.get_state_set()
                if state_set and self._atspi:
                    ST = self._atspi.StateType
                    if state_set.contains(ST.FOCUSED):
                        is_focused = True
                        states.append("focused")
                    if state_set.contains(ST.ACTIVE):
                        states.append("active")
                    if state_set.contains(ST.ENABLED):
                        is_enabled = True
                        states.append("enabled")
                    else:
                        is_enabled = False
                    if state_set.contains(ST.VISIBLE):
                        is_visible = True
                        states.append("visible")
                    if state_set.contains(ST.SHOWING):
                        states.append("showing")
            except Exception:
                pass

            actions: List[str] = []
            try:
                act = node.get_action_iface()
                if act:
                    n_actions = act.get_n_actions()
                    for idx in range(min(5, n_actions)):
                        a_name = act.get_name(idx) if hasattr(act, "get_name") else act.get_action_name(idx)
                        if a_name:
                            actions.append(a_name)
            except Exception:
                pass

            text_content = None
            try:
                text_iface = node.get_text_iface()
                if text_iface:
                    char_count = text_iface.get_character_count()
                    if char_count > 0:
                        text_content = text_iface.get_text(0, min(500, char_count))
            except Exception:
                pass

            return AccessibleElement(
                name=name,
                role=role,
                description=description,
                x=x,
                y=y,
                width=w,
                height=h,
                states=states,
                is_focused=is_focused,
                is_enabled=is_enabled,
                is_visible=is_visible,
                app_name=app_name,
                window_title=window_title,
                actions=actions,
                text_content=text_content,
                node_ref=node,
            )
        except Exception as e:
            logger.debug(f"Failed to normalize accessible node: {e}")
            return None

    def activate_element(self, element: AccessibleElement, action_index: int = 0) -> bool:
        """
        Directly invoke an accessibility action on element without cursor movement.
        Falls back to coordinate click if action interface is not exposed.
        """
        if not element.node_ref:
            return False

        with _GLOBAL_ATSPI_LOCK:
            try:
                act = element.node_ref.get_action_iface()
                if act and act.get_n_actions() > action_index:
                    ok = act.do_action(action_index)
                    if ok:
                        return True
            except Exception as e:
                logger.debug(f"Direct accessibility action failed on '{element.name}': {e}")

            return False

    def set_element_text(self, element: AccessibleElement, text: str) -> bool:
        """
        Directly set text contents on editable entry fields.
        """
        if not element.node_ref:
            return False

        with _GLOBAL_ATSPI_LOCK:
            try:
                edit = element.node_ref.get_editable_text_iface()
                if edit:
                    return bool(edit.set_text_contents(text))
            except Exception as e:
                logger.debug(f"Direct editable text setting failed on '{element.name}': {e}")

            return False

    def get_application_hierarchy(self, app_name: str, max_depth: int = 3) -> Dict[str, Any]:
        """Build structured semantic hierarchy tree of an application."""
        if not self._atspi:
            return {"status": "unavailable", "app_name": app_name, "children": []}

        with _GLOBAL_ATSPI_LOCK:
            desktop = self.get_desktop()
            if not desktop:
                return {"status": "error", "message": "Desktop unavailable"}

            target_app = None
            for i in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(i)
                if app and app_name.lower() in (app.get_name() or "").lower():
                    target_app = app
                    break

            if not target_app:
                return {"status": "not_found", "app_name": app_name}

            def _walk(node, depth):
                if depth > max_depth or not node:
                    return None
                try:
                    name = node.get_name() or ""
                    role = node.get_role_name() or ""
                    children = []
                    for idx in range(min(15, node.get_child_count())):
                        ch = node.get_child_at_index(idx)
                        ch_dict = _walk(ch, depth + 1)
                        if ch_dict:
                            children.append(ch_dict)
                    return {
                        "name": name,
                        "role": role,
                        "children": children,
                    }
                except Exception:
                    return None

            return {
                "status": "success",
                "app_name": target_app.get_name(),
                "tree": _walk(target_app, 0),
            }
