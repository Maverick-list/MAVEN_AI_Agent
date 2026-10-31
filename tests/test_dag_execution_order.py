"""
Tests for DAG Execution Order Resolution and Topological Scheduling.
Validates that out-of-order step lists, diamond dependencies, and independent tasks
are executed in correct topological order.
"""

import unittest
from maverick.intelligence.planner import TaskPlanner, TaskPlan, TaskStep, TaskStatus


class TestDAGExecutionOrder(unittest.TestCase):
    def setUp(self):
        self.planner = TaskPlanner()

    def test_out_of_order_linear_chain(self):
        """
        Verify A -> B -> C executes in correct order C -> B -> A
        even when submitted as [A, B, C].
        """
        execution_order = []

        # Hook telemetry execution to track order
        orig_exec = self.planner.tools.execute

        def tracking_exec(tool_name, params=None, confirmed=False):
            if params and "step_tag" in params:
                execution_order.append(params["step_tag"])
            return {"status": "success", "result": {"ok": True}}

        self.planner.tools.execute = tracking_exec
        try:
            s_a = TaskStep(step_id=1, description="Task A", tool_name="system_telemetry", parameters={"step_tag": "A"}, dependencies=[2])
            s_b = TaskStep(step_id=2, description="Task B", tool_name="system_telemetry", parameters={"step_tag": "B"}, dependencies=[3])
            s_c = TaskStep(step_id=3, description="Task C", tool_name="system_telemetry", parameters={"step_tag": "C"}, dependencies=[])

            plan = TaskPlan(
                plan_id="plan_order_linear",
                goal="Test out of order linear",
                steps=[s_a, s_b, s_c],
                status=TaskStatus.CREATED,
            )

            res = self.planner.execute_plan(plan)
            self.assertEqual(res["status"], "completed")
            self.assertEqual(plan.status, TaskStatus.COMPLETED)
            self.assertEqual(execution_order, ["C", "B", "A"])
            for s in plan.steps:
                self.assertEqual(s.status, "completed")
        finally:
            self.planner.tools.execute = orig_exec

    def test_resolve_execution_order_method(self):
        """Verify resolve_execution_order returns correct topologically sorted step objects."""
        s1 = TaskStep(step_id=1, description="Step 1", tool_name="system_telemetry", parameters={}, dependencies=[2])
        s2 = TaskStep(step_id=2, description="Step 2", tool_name="system_telemetry", parameters={}, dependencies=[3])
        s3 = TaskStep(step_id=3, description="Step 3", tool_name="system_telemetry", parameters={}, dependencies=[])

        ordered = self.planner.resolve_execution_order([s1, s2, s3])
        ordered_ids = [s.step_id for s in ordered]
        self.assertEqual(ordered_ids, [3, 2, 1])

    def test_diamond_dependencies(self):
        r"""
        Verify Diamond DAG:
             A
            / \
           B   C
            \ /
             D
        Order: A -> B and C -> D.
        """
        execution_order = []
        orig_exec = self.planner.tools.execute

        def tracking_exec(tool_name, params=None, confirmed=False):
            if params and "step_tag" in params:
                execution_order.append(params["step_tag"])
            return {"status": "success", "result": {"ok": True}}

        self.planner.tools.execute = tracking_exec
        try:
            # Submitted in scrambled order: D, C, B, A
            s_d = TaskStep(step_id=4, description="D", tool_name="system_telemetry", parameters={"step_tag": "D"}, dependencies=[2, 3])
            s_c = TaskStep(step_id=3, description="C", tool_name="system_telemetry", parameters={"step_tag": "C"}, dependencies=[1])
            s_b = TaskStep(step_id=2, description="B", tool_name="system_telemetry", parameters={"step_tag": "B"}, dependencies=[1])
            s_a = TaskStep(step_id=1, description="A", tool_name="system_telemetry", parameters={"step_tag": "A"}, dependencies=[])

            plan = TaskPlan(
                plan_id="plan_diamond",
                goal="Diamond DAG test",
                steps=[s_d, s_c, s_b, s_a],
                status=TaskStatus.CREATED,
            )

            res = self.planner.execute_plan(plan)
            self.assertEqual(res["status"], "completed")
            self.assertEqual(execution_order[0], "A")
            self.assertIn(execution_order[1], ("B", "C"))
            self.assertIn(execution_order[2], ("B", "C"))
            self.assertEqual(execution_order[3], "D")
        finally:
            self.planner.tools.execute = orig_exec

    def test_multiple_independent_parallel_tasks(self):
        """Tasks with no dependencies should all execute cleanly."""
        s1 = TaskStep(step_id=10, description="Task 1", tool_name="system_telemetry", parameters={}, dependencies=[])
        s2 = TaskStep(step_id=20, description="Task 2", tool_name="system_telemetry", parameters={}, dependencies=[])
        s3 = TaskStep(step_id=30, description="Task 3", tool_name="system_telemetry", parameters={}, dependencies=[])

        plan = TaskPlan(
            plan_id="plan_independent",
            goal="Independent tasks",
            steps=[s1, s2, s3],
            status=TaskStatus.CREATED,
        )

        res = self.planner.execute_plan(plan)
        self.assertEqual(res["status"], "completed")
        for s in plan.steps:
            self.assertEqual(s.status, "completed")


if __name__ == "__main__":
    unittest.main()
