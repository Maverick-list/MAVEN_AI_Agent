"""
Tests for DAG Failure Handling, Validation, Cascaded Blocking, and Completion Invariants.
Validates that invalid graphs are rejected, failures cascade cleanly, and false completions are prevented.
"""

import unittest
from maverick.intelligence.planner import TaskPlanner, TaskPlan, TaskStep, TaskStatus


class TestDAGFailureHandling(unittest.TestCase):
    def setUp(self):
        self.planner = TaskPlanner()

    def test_duplicate_task_id_rejection(self):
        """Verify plans with duplicate step IDs are rejected by DAG validation."""
        s1 = TaskStep(step_id=1, description="Step 1", tool_name="system_telemetry", parameters={})
        s2 = TaskStep(step_id=1, description="Duplicate Step 1", tool_name="system_telemetry", parameters={})

        ok, err = self.planner.validate_dag([s1, s2])
        self.assertFalse(ok)
        self.assertIn("Duplicate step ID", err)

        plan = TaskPlan(plan_id="plan_dup", goal="Duplicate ID test", steps=[s1, s2])
        res = self.planner.execute_plan(plan)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(plan.status, TaskStatus.FAILED)

    def test_self_dependency_rejection(self):
        """Verify step depending on itself is rejected."""
        s1 = TaskStep(step_id=1, description="Self dep", tool_name="system_telemetry", parameters={}, dependencies=[1])
        ok, err = self.planner.validate_dag([s1])
        self.assertFalse(ok)
        self.assertIn("self-dependency", err)

    def test_nonexistent_dependency_rejection(self):
        """Verify reference to non-existent dependency ID is rejected."""
        s1 = TaskStep(step_id=1, description="Missing dep", tool_name="system_telemetry", parameters={}, dependencies=[99])
        ok, err = self.planner.validate_dag([s1])
        self.assertFalse(ok)
        self.assertIn("non-existent dependency", err)

    def test_cycle_detection(self):
        """Verify cyclic graphs are detected and rejected."""
        s1 = TaskStep(step_id=1, description="A", tool_name="system_telemetry", parameters={}, dependencies=[2])
        s2 = TaskStep(step_id=2, description="B", tool_name="system_telemetry", parameters={}, dependencies=[1])
        ok, err = self.planner.validate_dag([s1, s2])
        self.assertFalse(ok)
        self.assertIn("Cycle detected", err)

    def test_cascaded_blocking_on_dependency_failure(self):
        """
        Verify that when an upstream task fails:
        1. Downstream dependent tasks are marked 'blocked'.
        2. Downstream tasks are NOT executed.
        3. Plan fails and is NEVER marked completed.
        """
        s_upstream = TaskStep(
            step_id=1,
            description="Failing Step",
            tool_name="system_safe_command",
            parameters={"command": "disallowed_command_xyz"},
            dependencies=[],
        )
        s_downstream1 = TaskStep(
            step_id=2,
            description="Child Step",
            tool_name="system_telemetry",
            parameters={},
            dependencies=[1],
        )
        s_downstream2 = TaskStep(
            step_id=3,
            description="Grandchild Step",
            tool_name="system_telemetry",
            parameters={},
            dependencies=[2],
        )

        plan = TaskPlan(
            plan_id="plan_cascade_fail",
            goal="Cascaded failure test",
            steps=[s_upstream, s_downstream1, s_downstream2],
            status=TaskStatus.CREATED,
        )

        res = self.planner.execute_plan(plan)
        self.assertEqual(res["status"], "failed")
        self.assertEqual(plan.status, TaskStatus.FAILED)

        # Upstream step failed
        self.assertEqual(s_upstream.status, "failed")
        # Direct and transitive dependents blocked
        self.assertEqual(s_downstream1.status, "blocked")
        self.assertIn("Blocked", s_downstream1.error)
        self.assertEqual(s_downstream2.status, "blocked")
        self.assertIn("Blocked", s_downstream2.error)

    def test_completion_invariant_prevent_false_completion(self):
        """
        Ensure completion invariant rejects plans where any step remains pending or blocked.
        """
        s1 = TaskStep(step_id=1, description="Step 1", tool_name="system_telemetry", parameters={}, dependencies=[])
        s2 = TaskStep(step_id=2, description="Step 2 (blocked)", tool_name="system_telemetry", parameters={}, dependencies=[999])

        plan = TaskPlan(plan_id="plan_inv", goal="Invariant test", steps=[s1, s2])
        res = self.planner.execute_plan(plan)
        self.assertEqual(res["status"], "failed")
        self.assertNotEqual(plan.status, TaskStatus.COMPLETED)

    def test_step_retry_behavior(self):
        """Verify steps with retries_left retry upon transient verification failure."""
        attempts = 0

        def flaky_verify(step):
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                return False, "Transient timeout"
            return True, None

        self.planner._verify_step_outcome = flaky_verify

        step = TaskStep(
            step_id=1,
            description="Flaky step",
            tool_name="system_telemetry",
            parameters={},
            dependencies=[],
            verification_criteria={"type": "custom"},
            retries_left=2,
        )

        plan = TaskPlan(plan_id="plan_retry", goal="Retry test", steps=[step])
        res = self.planner.execute_plan(plan)
        self.assertEqual(res["status"], "completed")
        self.assertEqual(step.status, "completed")
        self.assertEqual(step.retries_left, 1)  # 1 retry consumed


if __name__ == "__main__":
    unittest.main()

