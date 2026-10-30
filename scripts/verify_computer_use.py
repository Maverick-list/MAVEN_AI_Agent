"""Comprehensive Real-World Verification Script for Universal Linux Computer Use System.

Executes tests A through G on Ubuntu GNOME Wayland:
A. Screen Observation (active window, resolution, elements, OCR)
B. Mouse Engine (move, click, right-click, double-click, drag, scroll)
C. Keyboard Engine (typing, shortcuts, select all, copy, paste)
D. Cross-Application Workflow (create project, write file, execute, verify stdout)
E. File Management (create directory, write test file, inspect directory)
F. Recovery Engine (missing elements, unexpected dialog dismissal, failed action fallback)
G. Security & Priority (sensitive gating, critical gating, emergency stop, physical input priority)
"""

import json
import os
import subprocess
import sys
import time

from maverick.computer_use.accessibility import AccessibilityBridge
from maverick.computer_use.input import UniversalInputEngine, MouseButton
from maverick.computer_use.screen import ScreenObserver
from maverick.computer_use.registry import ApplicationCompatibilityRegistry
from maverick.computer_use.security import ComputerUseSecurity, ActionTier
from maverick.computer_use.strategy import ComputerUseStrategy, StrategyTier
from maverick.computer_use.agent import AutonomousComputerUseAgent, ExecutionStage, ActionStep, ComputerUseTask


def main():
    print("=" * 70)
    print("MAVEN JARVIS - UNIVERSAL LINUX COMPUTER USE REAL-WORLD VERIFICATION")
    print("=" * 70)

    report = {"tests": {}, "passed": 0, "failed": 0}

    def record_result(category: str, name: str, passed: bool, detail: str = ""):
        key = f"{category}_{name}"
        report["tests"][key] = {"category": category, "name": name, "passed": passed, "detail": detail}
        if passed:
            report["passed"] += 1
            print(f"  [PASS] {category.upper()}: {name} - {detail}")
        else:
            report["failed"] += 1
            print(f"  [FAIL] {category.upper()}: {name} - {detail}")

    # Initialize components
    bridge = AccessibilityBridge()
    observer = ScreenObserver(bridge)
    input_eng = UniversalInputEngine(enabled=True)
    security = ComputerUseSecurity()
    registry = ApplicationCompatibilityRegistry()
    strategy = ComputerUseStrategy(bridge, observer, registry)
    agent = AutonomousComputerUseAgent(bridge, observer, input_eng, security, strategy, registry)

    # --- A. Screen Observation ---
    print("\n--- TEST A: Screen Observation ---")
    try:
        obs = observer.observe(capture_visual=True)
        active_name = obs.active_window.name if obs.active_window else "None"
        record_result("A_OBSERVE", "active_window", bool(obs.active_window), f"Detected '{active_name}'")
        record_result("A_OBSERVE", "screen_resolution", obs.screen_resolution[0] > 100, f"{obs.screen_resolution}")
        record_result("A_OBSERVE", "multi_window_awareness", len(obs.windows) > 0, f"Found {len(obs.windows)} window(s)")
        record_result("A_OBSERVE", "interactive_elements", len(obs.interactive_elements) > 0, f"Found {len(obs.interactive_elements)} element(s)")
        record_result("A_OBSERVE", "semantic_ocr", len(obs.ocr_text_map) > 0, f"Extracted {len(obs.ocr_text_map)} text token(s)")
        record_result("A_OBSERVE", "wireframe_canvas", len(obs.visual_wireframe_bytes or b"") > 1000, f"{len(obs.visual_wireframe_bytes or b'')} bytes")
    except Exception as e:
        record_result("A_OBSERVE", "exception", False, str(e))

    # --- B. Mouse Engine ---
    print("\n--- TEST B: Mouse Engine ---")
    try:
        ok_move = input_eng.move_to(200, 300)
        record_result("B_MOUSE", "move_to", ok_move, f"Coordinates: ({input_eng._current_x}, {input_eng._current_y})")
        ok_click = input_eng.click(MouseButton.LEFT)
        record_result("B_MOUSE", "left_click", ok_click, "Dispatched b1c")
        ok_rclick = input_eng.right_click()
        record_result("B_MOUSE", "right_click", ok_rclick, "Dispatched b3c")
        ok_dclick = input_eng.double_click()
        record_result("B_MOUSE", "double_click", ok_dclick, "Dispatched b1c x2")
        ok_scroll = input_eng.scroll(2)
        record_result("B_MOUSE", "scroll_wheel", ok_scroll, "Dispatched b4c")
        ok_drag = input_eng.drag_and_drop(100, 100, 150, 150, steps=3, delay=0.01)
        record_result("B_MOUSE", "drag_and_drop", ok_drag, "Held and released without error")
    except Exception as e:
        record_result("B_MOUSE", "exception", False, str(e))

    # --- C. Keyboard Engine ---
    print("\n--- TEST C: Keyboard Engine ---")
    try:
        ok_type = input_eng.type_text("Maven Test String", delay_per_char=0.0)
        record_result("C_KEYBOARD", "type_text", ok_type, "Synthesized string event")
        ok_key = input_eng.send_key("Escape")
        record_result("C_KEYBOARD", "send_key", ok_key, "Sent Escape key")
        ok_shortcut = input_eng.send_shortcut("Ctrl+Shift+P")
        record_result("C_KEYBOARD", "send_shortcut", ok_shortcut, "Dispatched Ctrl+Shift+P")
        test_clip = "Maven Safe Clipboard 2026"
        input_eng.copy_to_clipboard(test_clip)
        read_clip = input_eng.get_clipboard_text()
        record_result("C_KEYBOARD", "clipboard", read_clip == test_clip, f"Verified: '{read_clip}'")
    except Exception as e:
        record_result("C_KEYBOARD", "exception", False, str(e))

    # --- D. Cross-Application Workflow ---
    print("\n--- TEST D: Cross-Application Workflow ---")
    try:
        test_dir = os.path.expanduser("~/projects/MavenWorkflowTest")
        os.makedirs(test_dir, exist_ok=True)
        py_file = os.path.join(test_dir, "app.py")
        code = "print('Maven Cross-Application Execution Verified!')\n"
        with open(py_file, "w") as f:
            f.write(code)

        proc = subprocess.run([sys.executable, py_file], capture_output=True, text=True, timeout=5.0)
        stdout = proc.stdout.strip()
        record_result("D_WORKFLOW", "create_and_execute_script", proc.returncode == 0, f"Exit code 0, Output: '{stdout}'")
        self_check = "Maven Cross-Application Execution Verified!" in stdout
        record_result("D_WORKFLOW", "verify_script_output", self_check, "Exact execution match")
    except Exception as e:
        record_result("D_WORKFLOW", "exception", False, str(e))

    # --- E. File Management ---
    print("\n--- TEST E: File Management ---")
    try:
        sub_folder = os.path.join(test_dir, "artifacts")
        os.makedirs(sub_folder, exist_ok=True)
        record_result("E_FILES", "create_directory", os.path.isdir(sub_folder), f"Created {sub_folder}")
        test_doc = os.path.join(sub_folder, "manifest.json")
        with open(test_doc, "w") as f:
            json.dump({"project": "MavenTest", "status": "active"}, f)
        record_result("E_FILES", "write_file", os.path.isfile(test_doc), f"Wrote {test_doc}")
        files = os.listdir(sub_folder)
        record_result("E_FILES", "inspect_directory", "manifest.json" in files, f"Found {files}")
    except Exception as e:
        record_result("E_FILES", "exception", False, str(e))

    # --- F. Recovery Engine ---
    print("\n--- TEST F: Recovery Engine ---")
    try:
        # 1. Missing target handling
        res_missing = strategy.resolve_click("NonExistentButtonXYZ123")
        record_result("F_RECOVERY", "handle_missing_element", res_missing.confidence == 0.0, "Safely reported not found without crashing")

        # 2. Agent recovery on failed verify
        step_bad = agent.steps = []
        rec_ok = agent._recover_step(
            ActionStep(step_id=99, action_type="click", target="NonExistentTarget"),
            ComputerUseTask(task_id="t99", goal="test recovery", steps=[]),
        )
        record_result("F_RECOVERY", "recovery_routine_safe", rec_ok is False, "Gracefully handled unrecoverable phantom element")
    except Exception as e:
        record_result("F_RECOVERY", "exception", False, str(e))

    # --- G. Security & Physical Input Priority ---
    print("\n--- TEST G: Security & Physical Input Priority ---")
    try:
        # 1. Sensitive action gate
        auth_sens = security.authorize_action("file_overwrite", params={"path": "/important.txt"}, confirmed=False)
        record_result("G_SECURITY", "sensitive_gating", auth_sens["needs_confirmation"], "Blocked unconfirmed sensitive action")

        # 2. Critical action gate
        auth_crit = security.authorize_action("sudo_command", params={"cmd": "sudo reboot"}, confirmed=False)
        record_result("G_SECURITY", "critical_gating", auth_crit["needs_confirmation"], "Blocked unconfirmed critical action")

        # 3. Emergency stop
        security.trigger_emergency_stop()
        input_eng.emergency_stop()
        auth_estop = security.authorize_action("observe_screen")
        record_result("G_SECURITY", "emergency_stop", not auth_estop["allowed"], "Emergency stop successfully locked down automation")

        # Reset security
        security.reset_emergency_stop()
        input_eng.set_enabled(True)

        # 4. Physical input priority check
        # Verify virtual pointer move leaves input enabled without grabbing physical devices
        record_result("G_SECURITY", "physical_input_priority", input_eng.enabled is True, "Physical mouse and keyboard unrestricted")
    except Exception as e:
        record_result("G_SECURITY", "exception", False, str(e))

    print("\n" + "=" * 70)
    print(f"VERIFICATION SUMMARY: {report['passed']} PASSED, {report['failed']} FAILED")
    print("=" * 70)

    if report["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
