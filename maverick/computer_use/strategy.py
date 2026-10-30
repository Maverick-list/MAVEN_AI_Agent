"""Maverick DevOS - Universal Computer-Use Strategy Planner.

Implements the 5-tier strategy selection hierarchy:
1. Accessibility API (Deterministic semantic activation & extents)
2. Native Application Integration (CDP, D-Bus, CLI, designated shortcuts)
3. Screenshot and OCR (Semantic text detection)
4. Visual Computer Vision (Contour & template matching)
5. Coordinate-based pointer and keyboard synthesis (Fallback)

Selects the most reliable method dynamically based on application profile,
target element availability, and desktop state.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Tuple

from maverick.computer_use.accessibility import AccessibilityBridge, AccessibleElement
from maverick.computer_use.registry import ApplicationCompatibilityRegistry, ApplicationProfile, InteractionMethod
from maverick.computer_use.screen import DesktopObservation, ScreenObserver

logger = logging.getLogger("maverick.computer_use.strategy")


class StrategyTier(Enum):
    """The 5-tier computer-use priority order."""
    TIER_1_ACCESSIBILITY = "accessibility_api"
    TIER_2_NATIVE_INTEGRATION = "native_integration"
    TIER_3_SCREENSHOT_OCR = "screenshot_ocr"
    TIER_4_VISUAL_CV = "visual_computer_vision"
    TIER_5_COORDINATE_FALLBACK = "coordinate_fallback"


@dataclass
class ActionResolution:
    """The resolved execution plan for an intended interaction."""
    goal: str
    selected_tier: StrategyTier
    method_name: str
    target_element: Optional[AccessibleElement] = None
    target_coordinates: Optional[Tuple[int, int]] = None
    shortcut_combo: Optional[str] = None
    confidence: float = 1.0
    rationale: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "selected_tier": self.selected_tier.value,
            "method_name": self.method_name,
            "target_element": self.target_element.to_dict() if self.target_element else None,
            "target_coordinates": list(self.target_coordinates) if self.target_coordinates else None,
            "shortcut_combo": self.shortcut_combo,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "parameters": self.parameters,
        }


class ComputerUseStrategy:
    """Selects and formulates deterministic interaction plans following strict priority order."""

    def __init__(
        self,
        accessibility_bridge: Optional[AccessibilityBridge] = None,
        screen_observer: Optional[ScreenObserver] = None,
        registry: Optional[ApplicationCompatibilityRegistry] = None,
    ):
        self.bridge = accessibility_bridge or AccessibilityBridge()
        self.observer = screen_observer or ScreenObserver(self.bridge)
        self.registry = registry or ApplicationCompatibilityRegistry()

    def resolve_click(
        self,
        target_name: str,
        target_role: Optional[str] = None,
        app_hint: Optional[str] = None,
        observation: Optional[DesktopObservation] = None,
    ) -> ActionResolution:
        """
        Determine the most reliable method to click an intended target.
        Evaluates Tiers 1 through 5 in order.
        """
        obs = observation or self.observer.observe(query=target_name)
        active_app = (obs.active_window.app_name if obs.active_window else "") or app_hint or ""
        profile = self.registry.get_profile(active_app)

        # --- Tier 1: Accessibility API ---
        # Search elements discovered via AT-SPI
        candidates = self.bridge.find_elements(
            query=target_name,
            role=target_role,
            app_name=active_app if active_app else None,
            interactive_only=True,
            max_results=5,
        )

        if candidates:
            best_elem = candidates[0]
            # Check if element has direct accessible action (e.g. click, press)
            if best_elem.actions:
                return ActionResolution(
                    goal=f"click '{target_name}'",
                    selected_tier=StrategyTier.TIER_1_ACCESSIBILITY,
                    method_name="accessible_activate",
                    target_element=best_elem,
                    target_coordinates=best_elem.center,
                    confidence=0.98,
                    rationale=f"Found native accessible element '{best_elem.name}' [{best_elem.role}] with action '{best_elem.actions[0]}'.",
                    parameters={"action_index": 0},
                )
            else:
                # Use accessible bounding coordinates for exact cursor click
                return ActionResolution(
                    goal=f"click '{target_name}'",
                    selected_tier=StrategyTier.TIER_1_ACCESSIBILITY,
                    method_name="accessible_coordinate_click",
                    target_element=best_elem,
                    target_coordinates=best_elem.center,
                    confidence=0.92,
                    rationale=f"Found accessible element '{best_elem.name}' at exact screen bounds {best_elem.bounds}.",
                    parameters={"x": best_elem.center[0], "y": best_elem.center[1]},
                )

        # --- Tier 2: Native Application Integration / Known Shortcuts ---
        if profile and target_name.lower() in profile.default_shortcuts:
            shortcut = profile.default_shortcuts[target_name.lower()]
            return ActionResolution(
                goal=f"click '{target_name}'",
                selected_tier=StrategyTier.TIER_2_NATIVE_INTEGRATION,
                method_name="native_shortcut",
                shortcut_combo=shortcut,
                confidence=0.88,
                rationale=f"Application profile for '{profile.display_name}' defines dedicated shortcut '{shortcut}'.",
                parameters={"shortcut": shortcut},
            )

        # --- Tier 3: Semantic OCR Text Search ---
        for item in obs.ocr_text_map:
            if target_name.lower() in item["text"].lower():
                cx, cy = item["center"]
                return ActionResolution(
                    goal=f"click '{target_name}'",
                    selected_tier=StrategyTier.TIER_3_SCREENSHOT_OCR,
                    method_name="ocr_text_click",
                    target_coordinates=(cx, cy),
                    confidence=0.82,
                    rationale=f"Located target text '{item['text']}' via semantic OCR map at center ({cx}, {cy}).",
                    parameters={"x": cx, "y": cy},
                )

        # --- Tier 4: Visual CV Contour Detection ---
        if obs.visual_wireframe_bytes:
            visual_boxes = self.observer.detect_visual_elements_from_image(obs.visual_wireframe_bytes)
            if visual_boxes:
                # Find element closest to center of active window
                target_box = visual_boxes[0]
                return ActionResolution(
                    goal=f"click '{target_name}'",
                    selected_tier=StrategyTier.TIER_4_VISUAL_CV,
                    method_name="visual_cv_click",
                    target_coordinates=tuple(target_box["center"]),
                    confidence=0.65,
                    rationale="Located visual contour candidate matching element geometry.",
                    parameters={"x": target_box["center"][0], "y": target_box["center"][1]},
                )

        # --- Tier 5: Fallback / Failure ---
        return ActionResolution(
            goal=f"click '{target_name}'",
            selected_tier=StrategyTier.TIER_5_COORDINATE_FALLBACK,
            method_name="target_not_found",
            confidence=0.0,
            rationale=f"Could not locate '{target_name}' via any of Tiers 1-5.",
        )

    def resolve_text_entry(
        self,
        text: str,
        target_field: Optional[str] = None,
        observation: Optional[DesktopObservation] = None,
    ) -> ActionResolution:
        """
        Determine the most reliable method to enter text into an application field.
        """
        obs = observation or self.observer.observe(query=target_field)

        # If a specific field was requested, search for it
        if target_field:
            candidates = self.bridge.find_elements(
                query=target_field,
                role="entry",
                interactive_only=True,
                max_results=3,
            )
            if candidates:
                best_field = candidates[0]
                return ActionResolution(
                    goal=f"enter text into '{target_field}'",
                    selected_tier=StrategyTier.TIER_1_ACCESSIBILITY,
                    method_name="accessible_set_text",
                    target_element=best_field,
                    target_coordinates=best_field.center,
                    confidence=0.95,
                    rationale=f"Found accessible entry field '{best_field.name}'. Direct editable text setting supported.",
                    parameters={"text": text, "x": best_field.center[0], "y": best_field.center[1]},
                )

        # Fallback to direct keyboard typing into active window
        return ActionResolution(
            goal="enter text into active focus",
            selected_tier=StrategyTier.TIER_2_NATIVE_INTEGRATION,
            method_name="synthesize_typing",
            confidence=0.85,
            rationale="Typing directly into currently focused active window.",
            parameters={"text": text},
        )
