"""
Tests for DAG Restart Recovery, SQLite Persistence, Partial Plan Resumption, and Plan Cancellation.
"""

import os
import shutil
import tempfile
import unittest
from maverick.intelligence.planner import TaskPlanner, TaskPlan, TaskStep, TaskStatus
from maverick.intelligence.task_store import TaskStore


class TestDAGRestartRecovery(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="maven_test_taskstore_")
        self.db_path = os.path.join(self.temp_dir, "tasks.db")
        self.store = TaskStore(db_path=self.db_path)
        self.planner = TaskPlanner(task_store=self.store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_partial_plan_resumption_no_duplicate_execution(self):
        """
        Verify that when a plan with already-completed steps is re-executed:
        1. Completed steps are NOT executed again.
        2. Pending steps are executed to completion.
        3. Plan reaches COMPLETED safely.
        """
        executed_steps = []
        orig_exec = self.planner.tools.execute

        def tracking_exec(tool_name, params=None, confirmed=False):
            if params and "step_num" in params:
                executed_steps.append(params["step_num"])
            return {"status": "success", "result": {"ok": True}}

        self.planner.tools.execute = tracking_exec
        try:
            # Step 1 is already completed in a prior session
            s1 = TaskStep(step_id=1, description="Step 1", tool_name="system_telemetry", parameters={"step_num": 1}, dependencies=[], status="completed")
            # Step 2 is pending
            s2 = TaskStep(step_id=2, description="Step 2", tool_name="system_telemetry", parameters={"step_num": 2}, dependencies=[1], status="pending")

            plan = TaskPlan(
                plan_id="plan_resume_test",
                goal="Resume test",
                steps=[s1, s2],
                status=TaskStatus.RUNNING,
            )
            self.store.save_plan_data(plan.to_dict())

            # Clear in-memory planner state to simulate fresh process start
            self.planner._active_plans.clear()
            loaded_plan = self.planner.get_plan("plan_resume_test")
            self.assertIsNotNone(loaded_plan)

            res = self.planner.execute_plan(loaded_plan)
            self.assertEqual(res["status"], "completed")

            # Verify Step 1 was NOT re-executed! Only Step 2 executed.
            self.assertEqual(executed_steps, [2])
            self.assertEqual(loaded_plan.status, TaskStatus.COMPLETED)
        finally:
            self.planner.tools.execute = orig_exec

    def test_recover_interrupted_plans_on_startup(self):
        """
        Verify that a plan interrupted mid-execution (crashed with status='running')
        is reconciled by recover_interrupted_plans().
        """
        s1 = TaskStep(step_id=1, description="Step 1", tool_name="system_telemetry", parameters={}, dependencies=[], status="completed")
        s2 = TaskStep(step_id=2, description="Step 2", tool_name="system_telemetry", parameters={}, dependencies=[1], status="running")

        plan = TaskPlan(
            plan_id="plan_crash_interrupted",
            goal="Crash test",
            steps=[s1, s2],
            status=TaskStatus.RUNNING,
        )
        self.store.save_plan_data(plan.to_dict())

        # Simulate fresh process startup sweep
        recovered_ids = self.planner.recover_interrupted_plans()
        self.assertIn("plan_crash_interrupted", recovered_ids)

        reconciled = self.planner.get_plan("plan_crash_interrupted")
        self.assertEqual(reconciled.steps[0].status, "completed")
        # Step 2 was re-marked pending so it can safely be resumed
        self.assertEqual(reconciled.steps[1].status, "pending")
        self.assertIn("Interrupted", reconciled.steps[1].error)

    def test_plan_cancellation(self):
        """Verify cancel_plan cancels active and pending steps and persists CANCELLED status."""
        s1 = TaskStep(step_id=1, description="Step 1", tool_name="system_telemetry", parameters={}, dependencies=[])
        s2 = TaskStep(step_id=2, description="Step 2", tool_name="system_telemetry", parameters={}, dependencies=[1])

        plan = TaskPlan(
            plan_id="plan_cancel_me",
            goal="Cancellation test",
            steps=[s1, s2],
            status=TaskStatus.CREATED,
        )
        self.store.save_plan_data(plan.to_dict())

        ok = self.planner.cancel_plan("plan_cancel_me")
        self.assertTrue(ok)

        stored = self.planner.get_plan("plan_cancel_me")
        self.assertEqual(stored.status, TaskStatus.CANCELLED)
        for s in stored.steps:
            self.assertEqual(s.status, "cancelled")


if __name__ == "__main__":
    unittest.main()

