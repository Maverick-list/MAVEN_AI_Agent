"""Unit and integration tests for Maven Intelligence Layer (Memory, Tools, Planner)."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from maverick.intelligence.memory import ContextMemory
from maverick.intelligence.tools import ToolDefinition, ToolRegistry, ToolRisk
from maverick.intelligence.planner import TaskPlan, TaskPlanner, TaskStatus, TaskStep


class TestContextMemory(unittest.TestCase):
    """Test suite for persistent context memory."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.store_path = os.path.join(self.tmp_dir.name, "memory.json")
        self.memory = ContextMemory(store_path=self.store_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_store_and_retrieve_memory(self):
        """Storing and retrieving memory records."""
        rec = self.memory.store(
            content="CampusLink project is located at ~/projects/CampusLink",
            category="project",
            tags=["campuslink", "frontend", "react"],
        )
        self.assertIn("id", rec)
        self.assertEqual(rec["category"], "project")

        fetched = self.memory.get(rec["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["content"], rec["content"])
        self.assertEqual(fetched["access_count"], 1)

    def test_semantic_and_tag_search_ranking(self):
        """Search returns relevant matches ranked by token and tag overlap."""
        self.memory.store("User prefers dark theme and electric cyan accents", category="preference", tags=["theme", "ui"])
        self.memory.store("CampusLink backend uses FastAPI and PostgreSQL", category="project", tags=["campuslink", "backend"])
        self.memory.store("CampusLink frontend uses React and Tailwind", category="project", tags=["campuslink", "frontend"])

        # Query about campuslink
        results = self.memory.search("CampusLink frontend", limit=2)
        self.assertEqual(len(results), 2)
        self.assertIn("React", results[0]["content"])

    def test_secret_scrubbing_hygiene(self):
        """Never persist raw API keys or passwords in memory."""
        secret_input = "Remember my token is sk_test_mock_token_12345678 and password=SuperSecret"
        rec = self.memory.store(secret_input, category="context")

        self.assertNotIn("sk_test_mock_token_12345678", rec["content"])
        self.assertIn("REDACTED", rec["content"])

    def test_update_and_delete(self):
        """Update and delete memory records."""
        rec = self.memory.store("Initial observation", category="notes")
        mem_id = rec["id"]

        updated = self.memory.update(mem_id, "Updated observation", tags=["revised"])
        self.assertTrue(updated)
        self.assertEqual(self.memory.get(mem_id)["content"], "Updated observation")

        deleted = self.memory.delete(mem_id)
        self.assertTrue(deleted)
        self.assertIsNone(self.memory.get(mem_id))


class TestToolRegistry(unittest.TestCase):
    """Test suite for unified tool orchestration registry."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.store_path = os.path.join(self.tmp_dir.name, "memory.json")
        self.memory = ContextMemory(store_path=self.store_path)
        self.registry = ToolRegistry(memory_engine=self.memory)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_list_tools_schema(self):
        """Verify tool schemas are registered and queryable."""
        tools = self.registry.list_tools()
        names = {t["name"] for t in tools}
        self.assertIn("desktop_launch_app", names)
        self.assertIn("system_telemetry", names)
        self.assertIn("filesystem_list_dir", names)
        self.assertIn("memory_store", names)

    def test_execute_system_telemetry(self):
        """Executing read-only telemetry tool."""
        res = self.registry.execute("system_telemetry")
        self.assertEqual(res["status"], "success")
        self.assertIn("ram_available_gb", res["result"])
        self.assertIn("cpu_percent", res["result"])

    def test_disallowed_command_rejected(self):
        """Disallowed commands outside allowlist must raise security violation."""
        res = self.registry.execute("system_run_safe_command", params={"command_id": "rm_rf"})
        self.assertEqual(res["status"], "security_violation")

    def test_confirmation_required_enforced(self):
        """Critical or confirmation-gated tools must halt if unconfirmed."""
        # Custom critical tool
        custom_tool = ToolDefinition(
            name="format_disk",
            description="Destructive action",
            parameters_schema={},
            risk=ToolRisk.CRITICAL,
            handler=lambda params, **_: "Formatted",
        )
        self.registry.register(custom_tool)

        # Without confirmation -> confirmation_required
        res_unconfirmed = self.registry.execute("format_disk", confirmed=False)
        self.assertEqual(res_unconfirmed["status"], "confirmation_required")

        # With confirmation -> success
        res_confirmed = self.registry.execute("format_disk", confirmed=True)
        self.assertEqual(res_confirmed["status"], "success")
        self.assertEqual(res_confirmed["result"], "Formatted")


class TestTaskPlanner(unittest.TestCase):
    """Test suite for intelligent multi-step task planning."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.store_path = os.path.join(self.tmp_dir.name, "memory.json")
        self.memory = ContextMemory(store_path=self.store_path)
        self.tools = ToolRegistry(memory_engine=self.memory)
        self.planner = TaskPlanner(tool_registry=self.tools, memory=self.memory)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_plan_development_environment_setup(self):
        """Decompose complex instruction into ordered actionable steps."""
        plan = self.planner.plan("Maven, siapkan environment development untuk CampusLink")
        self.assertEqual(len(plan.steps), 3)
        self.assertEqual(plan.steps[0].tool_name, "filesystem_list_dir")
        self.assertEqual(plan.steps[1].tool_name, "desktop_launch_app")
        self.assertEqual(plan.steps[2].tool_name, "desktop_launch_app")
        self.assertTrue(plan.steps[2].requires_approval)

    def test_execute_plan_with_approval_gate(self):
        """Plan execution halts at approval gate and resumes upon approval."""
        plan = self.planner.plan("siapkan environment development untuk CampusLink")

        with patch.object(self.tools, "execute") as mock_exec:
            # Step 1: list dir -> success
            # Step 2: launch code -> success
            # Step 3: launch terminal -> requires approval
            mock_exec.side_effect = [
                {"status": "success", "result": {"count": 5}},
                {"status": "success", "result": {"status": "success"}},
                {"status": "success", "result": {"status": "success"}},
            ]

            # First run: executes steps 1 and 2, then halts at step 3
            res1 = self.planner.execute_plan(plan)
            self.assertEqual(res1["status"], "awaiting_approval")
            self.assertEqual(res1["awaiting_step_id"], 3)
            self.assertEqual(plan.status, TaskStatus.AWAITING_APPROVAL)

            # Second run with explicit approval for step 3
            res2 = self.planner.execute_plan(plan, approved_step_id=3)
            self.assertEqual(res2["status"], "completed")
            self.assertEqual(plan.status, TaskStatus.COMPLETED)
            self.assertIsNotNone(plan.final_summary)


if __name__ == "__main__":
    unittest.main()

