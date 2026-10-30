"""
Maverick DevOS - Backward-compatible virtual mouse facade.
Re-exports VirtualMouse and MouseButton from virtual_input.
"""

from maverick.vision.virtual_input import MouseButton, VirtualKeyboard, VirtualMouse

__all__ = ["MouseButton", "VirtualMouse", "VirtualKeyboard"]
