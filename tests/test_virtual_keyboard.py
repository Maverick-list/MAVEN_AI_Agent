"""
Tests for VirtualKeyboard input synthesis and AT-SPI binding.
"""

import unittest
from unittest.mock import MagicMock, patch

from maverick.vision.virtual_input import VirtualKeyboard
from maverick.vision.virtual_mouse import VirtualKeyboard as ReexportedKeyboard


class TestVirtualKeyboard(unittest.TestCase):
    def setUp(self):
        self.keyboard = VirtualKeyboard(enabled=True)
        self.mock_atspi = MagicMock()
        self.keyboard._atspi = self.mock_atspi
        self.keyboard._atspi_available = True

    def test_reexport_alias(self):
        """Ensure backward compatibility re-export in virtual_mouse."""
        self.assertIs(VirtualKeyboard, ReexportedKeyboard)

    def test_type_text_enabled(self):
        """Synthesize string typing via AT-SPI."""
        self.mock_atspi.generate_keyboard_event.return_value = True
        ok = self.keyboard.type_text("Hello World!")
        self.assertTrue(ok)
        self.mock_atspi.generate_keyboard_event.assert_called_once()
        args, _ = self.mock_atspi.generate_keyboard_event.call_args
        self.assertEqual(args[0], 0)
        self.assertEqual(args[1], "Hello World!")

    def test_type_text_disabled(self):
        """Typing is suppressed when virtual keyboard is disabled."""
        self.keyboard.set_enabled(False)
        ok = self.keyboard.type_text("Hello World!")
        self.assertFalse(ok)
        self.mock_atspi.generate_keyboard_event.assert_not_called()

    def test_press_key(self):
        """Synthesize key press and release sequence."""
        self.mock_atspi.generate_keyboard_event.return_value = True
        ok = self.keyboard.press_key("Return")
        self.assertTrue(ok)
        self.assertEqual(self.mock_atspi.generate_keyboard_event.call_count, 2)

    def test_fallback_when_atspi_missing(self):
        """Safe graceful failure when AT-SPI is not available."""
        self.keyboard._atspi_available = False
        self.keyboard._atspi = None
        ok = self.keyboard.type_text("Test")
        self.assertFalse(ok)

