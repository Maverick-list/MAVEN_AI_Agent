"""Comprehensive Unit, Integration & Adversarial Test Suite for Maven JARVIS Phase 2 Intelligent Agent Core.

Validates:
1. Intent Understanding & Classification Engine
2. Multi-tier Context Memory with TTL, LRU bounds & credential scrubbing
3. 5-Tier Risk Classification & Approval Gating
4. Central Cognitive Orchestration (11-phase lifecycle, pause, resume, cancel, e-stop)
5. Specialized Multi-Agent Registry (lazy loading, LRU eviction, idle cleanup)
6. Adversarial edge cases (empty input, ambiguous input, timeouts, max retries, dangerous payloads)
"""

import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from maverick.agent.intent import IntentCategory, IntentClassifier, UserIntent
from maverick.agent.orchestrator import MavenAgentCore
from maverick.agent.security import (
    ActionProvenance,
    AgentSecurityManager,
    ApprovalRecord,
    RiskPolicy,
    RiskTier,
)
from maverick.agent.specialized.base import SpecializedAgent
from maverick.agent.specialized.coding_agent import CodingAgent
from maverick.agent.specialized.document_agent import DocumentAgent
from maverick.agent.specialized.monitoring_agent import SystemMonitoringAgent, MonitoringAgent
from maverick.agent.specialized.planning_agent import PlanningAgent
from maverick.agent.specialized.registry import AgentRegistry
from maverick.agent.specialized.research_agent import ResearchAgent
from maverick.intelligence.memory import ContextMemory, MemoryCategory, RETENTION_POLICIES
from maverick.intelligence.planner import TaskPlan, TaskPlanner, TaskStatus, TaskStep
from maverick.intelligence.tools import ToolDefinition, ToolRegistry, ToolRisk


class TestIntentClassification(unittest.TestCase):
    """Test Intent Understanding & Classification Engine."""

    def setUp(self):
        self.classifier = IntentClassifier()

    def test_conversational_intents(self):
        inputs = [
            "Halo Maven, selamat pagi",
            "Hello Jarvis, how are you today?",
            "Hai apa kabar?",
            "Terima kasih Maven",
        ]
        for text in inputs:
            intent = self.classifier.classify(text)
            self.assertEqual(intent.category, IntentCategory.CONVERSATIONAL, f"Failed for: {text}")
            self.assertFalse(intent.is_ambiguous)

    def test_workflow_task_intents(self):
        inputs = [
            "Maven siapkan environment development untuk CampusLink",
            "Jalankan pipeline testing",
            "Tolong setup dev environment untuk project baru",
        ]
        for text in inputs:
            intent = self.classifier.classify(text)
            self.assertEqual(intent.category, IntentCategory.TASK_EXECUTION, f"Failed for: {text}")

    def test_desktop_interaction_intents(self):
        inputs = [
            "Buka aplikasi Firefox",
            "Klik tombol Save di editor",
            "Tutup window terminal",
            "Launch chrome",
        ]
        for text in inputs:
            intent = self.classifier.classify(text)
            self.assertEqual(intent.category, IntentCategory.DESKTOP_INTERACTION, f"Failed for: {text}")
            self.assertEqual(intent.suggested_agent, "computer_use")

    def test_research_intents(self):
        inputs = [
            "Riset arsitektur microservices untuk Maverick DevOS",
            "Cari informasi tentang implementasi AT-SPI2 di Linux",
            "Analyze and research modern vector database trends",
        ]
        for text in inputs:
            intent = self.classifier.classify(text)
            self.assertEqual(intent.category, IntentCategory.RESEARCH, f"Failed for: {text}")
            self.assertEqual(intent.suggested_agent, "research")

    def test_coding_intents(self):
        inputs = [
            "Analisis kode di maverick/dashboard/server.py",
            "Check syntax maverick/agent/orchestrator.py",
            "Debug code ini",
        ]
        for text in inputs:
            intent = self.classifier.classify(text)
            self.assertEqual(intent.category, IntentCategory.CODING, f"Failed for: {text}")
            self.assertEqual(intent.suggested_agent, "coding")

    def test_document_intents(self):
        inputs = [
            "Buat dokumen laporan arsitektur format markdown",
            "Generate report pdf untuk project audit",
            "Tulis dokumentasi teknis release notes",
        ]
        for text in inputs:
            intent = self.classifier.classify(text)
            self.assertEqual(intent.category, IntentCategory.DOCUMENT, f"Failed for: {text}")
            self.assertEqual(intent.suggested_agent, "document")

    def test_system_control_intents(self):
        inputs = [
            "Emergency stop sekarang",
            "Hentikan semua proses segera",
            "Ganti mode ke low_memory",
            "Status telemetry sistem bagaimana",
        ]
        for text in inputs:
            intent = self.classifier.classify(text)
            self.assertEqual(intent.category, IntentCategory.SYSTEM_CONTROL, f"Failed for: {text}")

    def test_empty_and_ambiguous_intents(self):
        # Empty string
        intent_empty = self.classifier.classify("")
        self.assertEqual(intent_empty.category, IntentCategory.UNKNOWN)
        self.assertTrue(intent_empty.is_ambiguous)

        # Whitespace
        intent_ws = self.classifier.classify("    ")
        self.assertEqual(intent_ws.category, IntentCategory.UNKNOWN)
        self.assertTrue(intent_ws.is_ambiguous)

        # Ambiguous / one word
        intent_amb = self.classifier.classify("sesuatu")
        self.assertEqual(intent_amb.category, IntentCategory.UNKNOWN)
        self.assertTrue(intent_amb.is_ambiguous)


class TestContextMemoryLifecycle(unittest.TestCase):
    """Test Multi-tier Context Memory with TTL, LRU bounds & credential scrubbing."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory = ContextMemory(storage_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_all_canonical_categories_storage(self):
        categories = [
            MemoryCategory.SHORT_TERM_CONVERSATION,
            MemoryCategory.ACTIVE_TASK,
            MemoryCategory.USER_PREFERENCES,
            MemoryCategory.PROJECT_CONTEXT,
            MemoryCategory.TASK_HISTORY,
            MemoryCategory.VERIFIED_KNOWLEDGE,
            MemoryCategory.GENERAL,
        ]
        for cat in categories:
            entry = self.memory.store(
                content=f"Test entry for category {cat.value}",
                category=cat,
                tags=[cat.value, "test"],
            )
            self.assertIn("id", entry)
            self.assertEqual(entry["category"], cat.value)

        # Check all stored
        all_mem = self.memory.list_all(limit=50)
        self.assertGreaterEqual(len(all_mem), len(categories))

    def test_credential_scrubbing(self):
        sensitive_content = "User config: api_key='sk-ant-live1234567890abcdef' password='SuperSecretPassword123!'"
        entry = self.memory.store(content=sensitive_content, category=MemoryCategory.USER_PREFERENCES)
        # Verify stored content does not contain raw secrets
        self.assertNotIn("sk-ant-live1234567890abcdef", entry["content"])
        self.assertNotIn("SuperSecretPassword123!", entry["content"])
        self.assertIn("[REDACTED", entry["content"])

    def test_category_specific_helpers(self):
        self.memory.store("Active task is deploying v2.0", category=MemoryCategory.ACTIVE_TASK)
        self.memory.store("User prefers dark theme", category=MemoryCategory.USER_PREFERENCES)
        self.memory.store("Project root is /home/user/app", category=MemoryCategory.PROJECT_CONTEXT)

        active = self.memory.get_active_task()
        self.assertIsNotNone(active)
        self.assertIn("deploying v2.0", active["content"])

        prefs = self.memory.get_preferences()
        self.assertEqual(len(prefs), 1)
        self.assertIn("dark theme", prefs[0]["content"])

        proj = self.memory.get_project_context()
        self.assertEqual(len(proj), 1)
        self.assertIn("/home/user/app", proj[0]["content"])

    def test_lru_and_capacity_enforcement(self):
        # ACTIVE_TASK has max_entries=5
        for i in range(10):
            self.memory.store(f"Active task step {i}", category=MemoryCategory.ACTIVE_TASK)

        # Check total active tasks bounded by policy
        tasks = [m for m in self.memory.list_all(limit=50) if m["category"] == MemoryCategory.ACTIVE_TASK.value]
        self.assertLessEqual(len(tasks), RETENTION_POLICIES[MemoryCategory.ACTIVE_TASK]["max_entries"])

    def test_ttl_pruning(self):
        entry = self.memory.store("Short-lived conversation item", category=MemoryCategory.SHORT_TERM_CONVERSATION)
        # Manually backdate expires_at
        with self.memory._lock:
            data = self.memory._read_store()
            if entry["id"] in data.get("memories", {}):
                data["memories"][entry["id"]]["expires_at"] = time.time() - 100
                self.memory._write_store(data)

        pruned = self.memory.prune_expired()
        self.assertGreaterEqual(pruned, 1)

        # Verify pruned item is gone
        remaining_ids = [m["id"] for m in self.memory.list_all(limit=50)]
        self.assertNotIn(entry["id"], remaining_ids)

    def test_wipe_all_and_category_filtering(self):
        self.memory.store("Pref 1", category=MemoryCategory.USER_PREFERENCES)
        self.memory.store("Pref 2", category=MemoryCategory.USER_PREFERENCES)
        self.memory.store("Task 1", category=MemoryCategory.TASK_HISTORY)

        # Wipe only preferences
        wiped_prefs = self.memory.wipe_all(category=MemoryCategory.USER_PREFERENCES)
        self.assertEqual(wiped_prefs, 2)
        self.assertEqual(len(self.memory.get_preferences()), 0)

        # Task history should remain
        self.assertEqual(len(self.memory.list_all(limit=10)), 1)

        # Wipe all remaining
        wiped_rest = self.memory.wipe_all()
        self.assertEqual(wiped_rest, 1)
        self.assertEqual(len(self.memory.list_all(limit=10)), 0)


class TestSecurityAndRiskPolicy(unittest.TestCase):
    """Test 5-Tier Risk Classification & Approval Gating."""

    def setUp(self):
        self.security = AgentSecurityManager()

    def test_5_tier_classification_mapping(self):
        # Read-only tools
        self.assertEqual(RiskPolicy.classify("read_file", {"path": "/tmp/test"}), RiskTier.READ_ONLY)
        self.assertEqual(RiskPolicy.classify("search_files", {"dir": "/tmp"}), RiskTier.READ_ONLY)
        self.assertEqual(RiskPolicy.classify("system_status", {}), RiskTier.READ_ONLY)

        # Reversible tools
        self.assertEqual(RiskPolicy.classify("move_cursor", {"x": 100, "y": 200}), RiskTier.REVERSIBLE)
        self.assertEqual(RiskPolicy.classify("hover", {"target": "btn"}), RiskTier.REVERSIBLE)

        # Moderate risk tools
        self.assertEqual(RiskPolicy.classify("launch_app", {"app": "gedit"}), RiskTier.MODERATE_RISK)
        self.assertEqual(RiskPolicy.classify("click_element", {"x": 100, "y": 200}), RiskTier.MODERATE_RISK)

        # High risk tools
        self.assertEqual(RiskPolicy.classify("write_file", {"path": "/tmp/test.txt"}), RiskTier.HIGH_RISK)
        self.assertEqual(RiskPolicy.classify("terminal_execute", {"cmd": "git push"}), RiskTier.HIGH_RISK)

        # Destructive tools
        self.assertEqual(RiskPolicy.classify("terminal_execute", {"cmd": "rm -rf /tmp/test"}), RiskTier.DESTRUCTIVE)
        self.assertEqual(RiskPolicy.classify("terminal_execute", {"cmd": "sudo apt install package"}), RiskTier.DESTRUCTIVE)
        self.assertEqual(RiskPolicy.classify("delete_file", {"path": "/tmp/a.txt"}), RiskTier.DESTRUCTIVE)

    def test_approval_requirement_logic(self):
        self.assertFalse(RiskPolicy.requires_approval(RiskTier.READ_ONLY))
        self.assertFalse(RiskPolicy.requires_approval(RiskTier.REVERSIBLE))
        self.assertFalse(RiskPolicy.requires_approval(RiskTier.MODERATE_RISK))
        self.assertTrue(RiskPolicy.requires_approval(RiskTier.HIGH_RISK))
        self.assertTrue(RiskPolicy.requires_approval(RiskTier.DESTRUCTIVE))

    def test_gated_action_evaluation_unconfirmed(self):
        prov = ActionProvenance(action_id="act_1", initiator="test")
        allowed, tier, reason = self.security.evaluate_action(
            action_name="terminal_execute",
            parameters={"cmd": "rm -rf /home/user/junk"},
            provenance=prov,
            confirmed=False,
        )
        self.assertFalse(allowed)
        self.assertEqual(tier, RiskTier.DESTRUCTIVE)
        self.assertIn("requires user confirmation", reason.lower())

    def test_gated_action_evaluation_confirmed(self):
        prov = ActionProvenance(action_id="act_2", initiator="test")
        allowed, tier, reason = self.security.evaluate_action(
            action_name="terminal_execute",
            parameters={"cmd": "rm -rf /home/user/junk"},
            provenance=prov,
            confirmed=True,
        )
        self.assertTrue(allowed)
        self.assertEqual(tier, RiskTier.DESTRUCTIVE)
        self.assertIsNone(reason)

    def test_emergency_stop_blocks_all_actions(self):
        prov = ActionProvenance(action_id="act_3", initiator="test")
        self.security.engage_emergency_stop()
        self.assertTrue(self.security.is_emergency_stopped)

        # Even read_only action must be blocked
        allowed, tier, reason = self.security.evaluate_action(
            action_name="read_file",
            parameters={"path": "/etc/hosts"},
            provenance=prov,
            confirmed=True,
        )
        self.assertFalse(allowed)
        self.assertIn("emergency stop", reason.lower())

        # Release e-stop
        self.security.release_emergency_stop()
        self.assertFalse(self.security.is_emergency_stopped)
        allowed, tier, reason = self.security.evaluate_action(
            action_name="read_file",
            parameters={"path": "/etc/hosts"},
            provenance=prov,
        )
        self.assertTrue(allowed)


class TestSpecializedAgentsAndRegistry(unittest.TestCase):
    """Test Multi-Agent Extensibility Layer & LRU Registry."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory = ContextMemory(storage_dir=self.temp_dir)
        self.registry = AgentRegistry(memory=self.memory, max_active_agents=3, idle_timeout_sec=0.5)

    def tearDown(self):
        self.registry.shutdown_all()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_lazy_loading_and_agent_types(self):
        expected_types = {"research", "coding", "computer_use", "document", "monitoring", "planning"}
        available = set(self.registry.list_available_agent_types())
        self.assertTrue(expected_types.issubset(available))

        # Initially no active agents
        self.assertEqual(len(self.registry.list_active_agents()), 0)

        # Request coding agent
        agent = self.registry.get_agent("coding")
        self.assertIsNotNone(agent)
        self.assertIsInstance(agent, CodingAgent)
        active_types = [a["agent_type"] for a in self.registry.list_active_agents()]
        self.assertIn("coding", active_types)

    def test_agent_execution_and_verification(self):
        agent = self.registry.get_agent("coding")
        # Run AST check on valid python code
        res = agent.execute("analyze_ast", {"code": "def add(a, b): return a + b\n"})
        self.assertEqual(res["status"], "success")

        verified, err = agent.verify("analyze_ast", res)
        self.assertTrue(verified)
        self.assertIsNone(err)

    def test_lru_eviction_when_capacity_exceeded(self):
        # max_active_agents is 3
        a1 = self.registry.get_agent("coding")
        a2 = self.registry.get_agent("research")
        a3 = self.registry.get_agent("document")
        self.assertEqual(len(self.registry.list_active_agents()), 3)

        # Access 4th agent: triggers eviction of least recently used
        a4 = self.registry.get_agent("monitoring")
        self.assertLessEqual(len(self.registry.list_active_agents()), 3)
        active_types = [a["agent_type"] for a in self.registry.list_active_agents()]
        self.assertIn("monitoring", active_types)

    def test_idle_agent_auto_cleanup(self):
        agent = self.registry.get_agent("planning")
        active_types = [a["agent_type"] for a in self.registry.list_active_agents()]
        self.assertIn("planning", active_types)

        # Wait past idle timeout (0.5s)
        time.sleep(0.6)
        evicted = self.registry.cleanup_idle_agents()
        self.assertGreaterEqual(evicted, 1)
        active_types_after = [a["agent_type"] for a in self.registry.list_active_agents()]
        self.assertNotIn("planning", active_types_after)


class TestMavenAgentCoreOrchestration(unittest.TestCase):
    """Test Central Cognitive Orchestration (11-phase lifecycle, control, e-stop)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory = ContextMemory(storage_dir=self.temp_dir)
        self.tools = ToolRegistry()
        self.planner = TaskPlanner(tools=self.tools, memory=self.memory)
        self.core = MavenAgentCore(
            memory=self.memory,
            tool_registry=self.tools,
            planner=self.planner,
        )

    def tearDown(self):
        self.core.emergency_stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_conversational_cycle(self):
        res = self.core.process_instruction("Halo Maven, selamat siang!")
        self.assertIn(res["status"], ("success", "completed"))
        self.assertEqual(res["intent"]["category"], "conversational")
        self.assertIn("message", res)

        # Verify short term conversation memory was recorded
        recent = self.memory.list_all(limit=10)
        self.assertTrue(any("Halo Maven" in m["content"] for m in recent))

    def test_workflow_task_approval_gate(self):
        # CampusLink dev prep step 3 requires approval
        res = self.core.process_instruction("siapkan environment development untuk CampusLink")
        self.assertEqual(res["status"], "awaiting_approval")
        self.assertIsNotNone(self.core.active_plan)
        self.assertEqual(self.core.active_plan.status, TaskStatus.AWAITING_APPROVAL)
        step_id = self.core.active_plan.awaiting_step_id
        self.assertEqual(step_id, 3)

        # Approve step with mock launch_app
        with patch("maverick.intelligence.tools.launch_app") as mock_launch:
            mock_launch.return_value = {"status": "success", "display_name": "Terminal"}
            appr = self.core.approve_step(step_id=step_id)
            self.assertEqual(appr["status"], "success")
            self.assertEqual(self.core.active_plan.status, TaskStatus.COMPLETED)

    def test_workflow_task_rejection(self):
        self.core.process_instruction("siapkan dev environment untuk TestApp")
        self.assertEqual(self.core.active_plan.status, TaskStatus.AWAITING_APPROVAL)

        rej = self.core.reject_step(reason="User rejected deployment")
        self.assertEqual(rej["status"], "success")
        self.assertEqual(rej["action"], "rejected")
        self.assertEqual(self.core.active_plan.status, TaskStatus.FAILED)
        self.assertIn("User rejected", self.core.active_plan.error_details)

    def test_pause_and_resume_plan(self):
        # Create a multi-step plan
        plan = TaskPlan(
            plan_id="plan_pause_1",
            goal="Test pause and resume",
            steps=[
                TaskStep(step_id=1, description="Status check 1", tool_name="system_status", parameters={}),
                TaskStep(step_id=2, description="Status check 2", tool_name="system_status", parameters={}),
            ],
            status=TaskStatus.RUNNING,
        )
        self.core.active_plan = plan

        # Pause
        p_res = self.core.pause_task()
        self.assertEqual(p_res["status"], "success")
        self.assertEqual(self.core.active_plan.status, TaskStatus.PAUSED)

        # Resume
        r_res = self.core.resume_task()
        self.assertEqual(r_res["status"], "success")
        self.assertEqual(self.core.active_plan.status, TaskStatus.COMPLETED)

    def test_cancel_task(self):
        plan = TaskPlan(
            plan_id="plan_cancel_1",
            goal="Cancelable task",
            steps=[TaskStep(step_id=1, description="Status check", tool_name="system_status", parameters={})],
            status=TaskStatus.RUNNING,
        )
        self.core.active_plan = plan

        c_res = self.core.cancel_task(reason="Abort requested")
        self.assertEqual(c_res["status"], "success")
        self.assertEqual(self.core.active_plan.status, TaskStatus.CANCELLED)

    def test_emergency_stop_lifecycle(self):
        plan = TaskPlan(
            plan_id="plan_estop_1",
            goal="Emergency target",
            steps=[TaskStep(step_id=1, description="Status check", tool_name="system_status", parameters={})],
            status=TaskStatus.RUNNING,
        )
        self.core.active_plan = plan

        stop_res = self.core.emergency_stop()
        self.assertEqual(stop_res["status"], "success")
        self.assertTrue(self.core.security.is_emergency_stopped)
        self.assertEqual(self.core.active_plan.status, TaskStatus.CANCELLED)

        # Subsequent instruction fails due to emergency stop
        res_blocked = self.core.process_instruction("Jalankan task baru")
        self.assertIn(res_blocked["status"], ("emergency_stopped", "emergency_blocked"))


class TestAdversarialAndResilience(unittest.TestCase):
    """Test adversarial inputs, tool failures, timeouts, and security edge cases."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory = ContextMemory(storage_dir=self.temp_dir)
        self.tools = ToolRegistry()
        self.planner = TaskPlanner(tools=self.tools, memory=self.memory)
        self.core = MavenAgentCore(
            memory=self.memory,
            tool_registry=self.tools,
            planner=self.planner,
        )

    def tearDown(self):
        self.core.emergency_stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_empty_and_whitespace_instructions(self):
        res1 = self.core.process_instruction("")
        self.assertEqual(res1["status"], "ambiguous")

        res2 = self.core.process_instruction("   \n\t   ")
        self.assertEqual(res2["status"], "ambiguous")

    def test_ambiguous_one_word_instruction(self):
        res = self.core.process_instruction("sesuatu")
        self.assertEqual(res["status"], "ambiguous")
        self.assertIn("clarification_needed", res["intent"])

    def test_max_retries_exhaustion(self):
        # Register a failing tool
        def fail_tool(*args, **kwargs):
            raise RuntimeError("Hardware connection dropped")

        self.tools.register(ToolDefinition(
            name="broken_tool",
            description="Broken test tool",
            parameters_schema={"type": "object"},
            risk=ToolRisk.READ_ONLY,
            handler=fail_tool,
        ))

        plan = TaskPlan(
            plan_id="plan_fail_1",
            goal="Failing execution test",
            steps=[TaskStep(step_id=1, description="Attempt broken tool", tool_name="broken_tool", parameters={}, max_retries=2)],
        )

        exec_res = self.planner.execute_plan(plan)
        self.assertEqual(exec_res["status"], "failed")
        self.assertEqual(plan.status, TaskStatus.FAILED)
        self.assertEqual(plan.steps[0].retries_left, 0)
        self.assertIn("Hardware connection dropped", plan.steps[0].error)

    def test_dangerous_destructive_command_blocking(self):
        dangerous_commands = [
            "rm -rf /",
            "rm -rf ~/*",
            "sudo rm -rf /etc",
            "mkfs.ext4 /dev/sda1",
            "dd if=/dev/zero of=/dev/sda",
        ]
        for cmd in dangerous_commands:
            tier = RiskPolicy.classify("terminal_execute", {"cmd": cmd})
            self.assertEqual(tier, RiskTier.DESTRUCTIVE, f"Failed to mark as destructive: {cmd}")
            self.assertTrue(RiskPolicy.requires_approval(tier))


if __name__ == "__main__":
    unittest.main()
