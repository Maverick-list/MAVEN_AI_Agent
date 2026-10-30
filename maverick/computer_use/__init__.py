"""Maverick DevOS - Universal Linux Computer Use System.

Provides comprehensive Linux desktop automation across Ubuntu GNOME Wayland:
- AccessibilityBridge (AT-SPI2 normalized tree, roles, states, direct actions)
- ScreenObserver (Active window, multi-window tree, OCR map, wireframe rendering)
- UniversalInputEngine (Mouse & keyboard synthesizer, shortcuts, clipboard)
- ApplicationCompatibilityRegistry (Known app capabilities, quirks, shortcuts)
- ComputerUseStrategy (5-tier priority resolution: AT-SPI -> Native -> OCR -> CV -> Coordinates)
- ComputerUseSecurity (Normal, Sensitive, Critical policy & audit trail)
- AutonomousComputerUseAgent (OBSERVE -> UNDERSTAND -> PLAN -> ACT -> VERIFY -> RECOVER)
"""

from maverick.computer_use.accessibility import AccessibilityBridge, AccessibleElement
from maverick.computer_use.input import UniversalInputEngine, MouseButton
from maverick.computer_use.registry import ApplicationCompatibilityRegistry, ApplicationProfile, InteractionMethod, AccessibilityHealth
from maverick.computer_use.screen import ScreenObserver, DesktopObservation
from maverick.computer_use.security import ComputerUseSecurity, ActionTier
from maverick.computer_use.strategy import ComputerUseStrategy, ActionResolution, StrategyTier
from maverick.computer_use.agent import AutonomousComputerUseAgent, ExecutionStage, ActionStep, ComputerUseTask

__all__ = [
    "AccessibilityBridge",
    "AccessibleElement",
    "UniversalInputEngine",
    "MouseButton",
    "ApplicationCompatibilityRegistry",
    "ApplicationProfile",
    "InteractionMethod",
    "AccessibilityHealth",
    "ScreenObserver",
    "DesktopObservation",
    "ComputerUseSecurity",
    "ActionTier",
    "ComputerUseStrategy",
    "ActionResolution",
    "StrategyTier",
    "AutonomousComputerUseAgent",
    "ExecutionStage",
    "ActionStep",
    "ComputerUseTask",
]
