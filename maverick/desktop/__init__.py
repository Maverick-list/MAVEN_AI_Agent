"""Maverick DevOS Desktop Launcher & Native Application Shell."""

from typing import Any


def run_desktop_app(*args: Any, **kwargs: Any) -> Any:
    """Lazy wrapper to launch desktop application without cyclic runpy warnings."""
    from maverick.desktop.app import run_desktop_app as _run
    return _run(*args, **kwargs)


def check_gui_available(*args: Any, **kwargs: Any) -> bool:
    """Check if display environment is active."""
    from maverick.desktop.app import check_gui_available as _check
    return _check(*args, **kwargs)


__all__ = ["run_desktop_app", "check_gui_available"]
