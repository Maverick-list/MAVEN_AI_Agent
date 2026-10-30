"""Unit and integration tests for Maven Intelligence Endpoints and Verbal Routing."""

import unittest
from unittest.mock import MagicMock, patch

from maverick.dashboard.server import TelemetryHub
from maverick.intelligence.memory import ContextMemory
from maverick.intelligence.planner import TaskPlanner, TaskStatus
from maverick.voice.controller import VoiceController
from maverick.voice.intent import BilingualIntentClassifier


class TestIntelligenceEndpoints(unittest.TestCase):
    """Test suite for Intelligence Layer REST endpoints and TelemetryHub methods."""

    def setUp(self):
        self.mock_tts = MagicMock()
        self.mock_tts.get_status.return_value = {"preferred_engine": "speech_dispatcher"}
        self.hub = TelemetryHub(tts=self.mock_tts)

    def test_submit_plan_and_approve(self):
        # 1. Submit plan
        goal = "siapkan environment development untuk CampusLink"
        res = self.hub.submit_intelligence_plan(goal)
        self.assertEqual(res["status"], "success")
        plan_dict = res["plan"]
        self.assertEqual(plan_dict["goal"], goal)
        self.assertIsNotNone(self.hub.active_plan)

        # Step 3 in CampusLink dev prep requires approval
        self.assertEqual(self.hub.active_plan.status, TaskStatus.AWAITING_APPROVAL)
        self.assertEqual(self.hub.active_plan.awaiting_step_id, 3)

        # 2. Approve step 3
        with patch("maverick.intelligence.tools.launch_app") as mock_launch:
            mock_launch.return_value = {"status": "success", "display_name": "Terminal"}
            approve_res = self.hub.approve_intelligence_step(3)
            self.assertEqual(approve_res["status"], "success")
            self.assertEqual(self.hub.active_plan.status, TaskStatus.COMPLETED)

    def test_reject_intelligence_step(self):
        goal = "siapkan dev environment untuk TestApp"
        self.hub.submit_intelligence_plan(goal)
        self.assertEqual(self.hub.active_plan.status, TaskStatus.AWAITING_APPROVAL)

        reject_res = self.hub.reject_intelligence_step(reason="User cancelled")
        self.assertEqual(reject_res["status"], "success")
        self.assertEqual(self.hub.active_plan.status, TaskStatus.FAILED)

    def test_memory_crud_via_hub(self):
        # Store memory
        res = self.hub.store_memory(
            content="User prefers dark mode across all editors",
            category="preferences",
            tags=["ui", "theme"],
        )
        self.assertEqual(res["status"], "success")
        mem_id = res["memory"]["id"]

        # Search memory
        mems = self.hub.memory.search("dark mode")
        self.assertTrue(any(m["id"] == mem_id for m in mems))

        # Delete memory
        del_res = self.hub.delete_memory(mem_id)
        self.assertEqual(del_res["status"], "success")
        self.assertTrue(del_res["deleted"])

    def test_voice_mute_toggle(self):
        res = self.hub.set_voice_mute(True)
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["muted"])
        self.assertTrue(self.hub.controller.session.is_muted)

        res2 = self.hub.set_voice_mute(False)
        self.assertEqual(res2["status"], "success")
        self.assertFalse(res2["muted"])
        self.assertFalse(self.hub.controller.session.is_muted)

    def test_verbal_memory_and_planner_intents(self):
        # 1. Intent classifier tests
        p1 = BilingualIntentClassifier.classify("Maven, ingat bahwa backend CampusLink menggunakan FastAPI")
        self.assertEqual(p1["intent"], "memory_store")

        p2 = BilingualIntentClassifier.classify("Maven, apa yang kamu ingat tentang CampusLink?")
        self.assertEqual(p2["intent"], "memory_recall")

        p3 = BilingualIntentClassifier.classify("Maven, siapkan environment development untuk CampusLink")
        self.assertEqual(p3["intent"], "task_plan")

        p4 = BilingualIntentClassifier.classify("konfirmasi")
        self.assertEqual(p4["intent"], "confirm")

        p5 = BilingualIntentClassifier.classify("tolak")
        self.assertEqual(p5["intent"], "reject")

        # 2. VoiceController execution test for memory store
        controller = self.hub.controller
        cmd_res = controller.handle_voice_command("Maven, ingat bahwa saya suka teh manis")
        self.assertEqual(cmd_res["status"], "success")
        self.assertEqual(cmd_res["action"], "memory_store")
        self.assertIn("memori", cmd_res["response"].lower())

        # 3. VoiceController execution test for memory recall
        recall_res = controller.handle_voice_command("Maven, apa yang kamu ingat tentang teh?")
        self.assertEqual(recall_res["status"], "success")
        self.assertEqual(recall_res["action"], "memory_recall")
        self.assertIn("teh manis", recall_res["response"].lower())


if __name__ == "__main__":
    unittest.main()
