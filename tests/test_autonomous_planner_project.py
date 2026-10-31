"""
Tests for Autonomous Project Planning & Execution and Extended Tool Registry.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from maverick.intelligence.planner import Planner, StepStatus
from maverick.intelligence.tools import ToolRegistry, ToolRisk


class TestAutonomousPlannerProject(unittest.TestCase):
    def setUp(self):
        self.planner = Planner()
        self.registry = ToolRegistry()

    def test_plan_autonomous_python_calculator(self):
        """Verify decomposition of 'Maven, create a Python calculator application' into 5 ordered steps."""
        goal = "Maven, create a Python calculator application"
        plan = self.planner.plan(goal)

        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 5)
        self.assertEqual(plan.steps[0].tool_name, "system_safe_command")
        self.assertEqual(plan.steps[1].tool_name, "filesystem_create_dir")
        self.assertEqual(plan.steps[2].tool_name, "filesystem_write_file")
        self.assertEqual(plan.steps[3].tool_name, "system_safe_command")
        self.assertEqual(plan.steps[4].tool_name, "memory_store")

        # Dependency chain verification
        self.assertEqual(plan.steps[0].dependencies, [])
        self.assertEqual(plan.steps[1].dependencies, [1])
        self.assertEqual(plan.steps[2].dependencies, [2])
        self.assertEqual(plan.steps[3].dependencies, [3])
        self.assertEqual(plan.steps[4].dependencies, [4])

    def test_plan_execution_in_sandbox(self):
        """Execute autonomous project generation in a temporary directory sandbox."""
        temp_dir = tempfile.mkdtemp(prefix="maven_test_proj_")
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)

        target_file = os.path.join(temp_dir, "calculator.py")

        # Step 1: Create Dir
        res1 = self.registry.execute("filesystem_create_dir", {"path": temp_dir})
        self.assertEqual(res1["status"], "success")

        # Step 2: Write File
        code = "print('Maven Calculator Test. 2 + 2 =', 2 + 2)\n"
        res2 = self.registry.execute("filesystem_write_file", {"path": target_file, "content": code})
        self.assertEqual(res2["status"], "success")
        self.assertTrue(os.path.isfile(target_file))

        # Step 3: Run command
        res3 = self.registry.execute("system_safe_command", {"command": f"python3 {target_file}"})
        self.assertEqual(res3["status"], "success")
        self.assertIn("4", res3["result"]["output"])

    def test_desktop_type_text_tool(self):
        """Test desktop_type_text tool integration."""
        tool = self.registry.get_tool("desktop_type_text")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.risk, ToolRisk.READ_ONLY)

        with patch("maverick.vision.virtual_input.VirtualKeyboard.type_text", return_value=True):
            res = self.registry.execute("desktop_type_text", {"text": "Artificial Intelligence"})
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["result"]["text"], "Artificial Intelligence")

    def test_desktop_explain_screen_tool(self):
        """Test desktop_explain_screen tool integration."""
        tool = self.registry.get_tool("desktop_explain_screen")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.risk, ToolRisk.READ_ONLY)

        with patch("maverick.vision.screen.ScreenIntelligence.explain_screen", return_value="Active window is Terminal"):
            res = self.registry.execute("desktop_explain_screen", {})
            self.assertEqual(res["status"], "success")
            self.assertIn("Terminal", res["result"])

    def test_interaction_mode_toggle_tool(self):
        """Test interaction_mode_toggle tool integration."""
        tool = self.registry.get_tool("interaction_mode_toggle")
        self.assertIsNotNone(tool)

        with patch("maverick.vision.vision_controller.VisionController") as mock_vc_cls:
            mock_vc = MagicMock()
            mock_vc.mode_manager.toggle_mode.return_value = {"status": "ok", "mode": "vision_active"}
            mock_vc_cls.return_value = mock_vc

            res = self.registry.execute("interaction_mode_toggle", {})
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["result"]["mode"], "vision_active")

    def test_dag_validation_cycle_detection(self):
        """Verify topological sort detects cycles in DAG steps."""
        from maverick.intelligence.planner import TaskStep

        # Valid DAG: 1 -> 2 -> 3
        valid_steps = [
            TaskStep(step_id=1, description="step 1", tool_name="system_telemetry", parameters={}),
            TaskStep(step_id=2, description="step 2", tool_name="system_telemetry", parameters={}, dependencies=[1]),
            TaskStep(step_id=3, description="step 3", tool_name="system_telemetry", parameters={}, dependencies=[2]),
        ]
        ok, err = self.planner.validate_dag(valid_steps)
        self.assertTrue(ok)
        self.assertIsNone(err)

        # Invalid DAG with cycle: 1 -> 2 -> 3 -> 1
        cycle_steps = [
            TaskStep(step_id=1, description="step 1", tool_name="system_telemetry", parameters={}, dependencies=[3]),
            TaskStep(step_id=2, description="step 2", tool_name="system_telemetry", parameters={}, dependencies=[1]),
            TaskStep(step_id=3, description="step 3", tool_name="system_telemetry", parameters={}, dependencies=[2]),
        ]
        ok, err = self.planner.validate_dag(cycle_steps)
        self.assertFalse(ok)
        self.assertIn("Cycle detected", err)

    def test_persistent_task_store_lifecycle(self):
        """Verify plan persistence and recovery via SQLite TaskStore."""
        goal = "Maven, create a Python calculator application"
        plan = self.planner.plan(goal)

        # Verify plan is stored in SQLite
        plan_id = plan.plan_id
        stored_plan = self.planner.store.get_plan_data(plan_id)
        self.assertIsNotNone(stored_plan)
        self.assertEqual(stored_plan["goal"], goal)

        # Clear in-memory dictionary to force SQLite restoration
        self.planner._active_plans.clear()
        restored_plan = self.planner.get_plan(plan_id)
        self.assertIsNotNone(restored_plan)
        self.assertEqual(restored_plan.plan_id, plan_id)
        self.assertEqual(restored_plan.goal, goal)
        self.assertEqual(len(restored_plan.steps), 5)

    def test_step_outcome_verification(self):
        """Verify empirical post-condition outcome checking."""
        from maverick.intelligence.planner import TaskStep
        temp_dir = tempfile.mkdtemp(prefix="maven_verify_")
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)

        test_file = os.path.join(temp_dir, "output.txt")

        # 1. Verification fails when file does not exist
        step_failing = TaskStep(
            step_id=1,
            description="Write output",
            tool_name="filesystem_write_file",
            parameters={},
            verification_criteria={"type": "file_exists", "path": test_file, "min_size_bytes": 5},
        )
        ok, err = self.planner._verify_step_outcome(step_failing)
        self.assertFalse(ok)
        self.assertIn("does not exist", err)

        # 2. Write file and verify passes
        with open(test_file, "w") as f:
            f.write("Hello Maven Verification\n")

        ok, err = self.planner._verify_step_outcome(step_failing)
        self.assertTrue(ok)
        self.assertIsNone(err)
