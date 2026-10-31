"""Maverick DevOS - Intelligent Agent Core & Central Orchestrator.

Implements the unified 11-phase autonomous cognitive lifecycle:
USER INPUT -> INTENT UNDERSTANDING -> CONTEXT RETRIEVAL -> TASK PLANNING ->
RISK CLASSIFICATION -> APPROVAL GATE -> TOOL EXECUTION -> OBSERVATION ->
RESULT VERIFICATION -> MEMORY UPDATE -> USER RESPONSE
"""

from dataclasses import asdict
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from maverick.agent.intent import IntentClassifier, IntentCategory, UserIntent
from maverick.agent.security import AgentSecurityManager, RiskPolicy, RiskTier, ActionProvenance
from maverick.agent.specialized.registry import AgentRegistry
from maverick.intelligence.memory import ContextMemory, MemoryCategory
from maverick.intelligence.planner import TaskPlan, TaskPlanner, TaskStatus, TaskStep
from maverick.intelligence.tools import ToolRegistry

logger = logging.getLogger("maverick.agent.orchestrator")


class MavenAgentCore:
    """
    Central cognitive orchestration core of Maven JARVIS.
    Unifies intent classification, persistent memory retrieval, DAG task planning,
    risk gating, specialized agent dispatching, and post-action verification.
    """

    def __init__(
        self,
        memory: Optional[ContextMemory] = None,
        tool_registry: Optional[ToolRegistry] = None,
        planner: Optional[TaskPlanner] = None,
        security_manager: Optional[AgentSecurityManager] = None,
        agent_registry: Optional[AgentRegistry] = None,
    ):
        self.memory = memory or ContextMemory()
        self.tools = tool_registry or ToolRegistry(memory_engine=self.memory)
        self.planner = planner or TaskPlanner(tool_registry=self.tools, memory=self.memory)
        self.security = security_manager or AgentSecurityManager()
        self.agents = agent_registry or AgentRegistry(max_active_agents=4)
        self.intent_classifier = IntentClassifier()

        self._lock = threading.RLock()
        self.active_plan: Optional[TaskPlan] = None
        self._last_turn_metrics: Dict[str, Any] = {}

    # -------------------------------------------------------------
    # 1. PRIMARY COGNITIVE LIFECYCLE
    # -------------------------------------------------------------

    def process_instruction(
        self,
        instruction: str,
        confirmed: bool = False,
        source: str = "user",
    ) -> Dict[str, Any]:
        """
        Execute the unified 11-phase cognitive cycle for a user instruction.
        """
        t0 = time.perf_counter()
        raw_text = (instruction or "").strip()

        # Phase 1: Input Validation
        if not raw_text:
            return {
                "status": "ambiguous",
                "message": "Instruction cannot be empty. Please specify a task or query.",
                "category": IntentCategory.CONVERSATIONAL.value,
                "elapsed_ms": 0.1,
            }

        # Check Global Emergency Stop
        if self.security.is_emergency_stopped:
            return {
                "status": "emergency_blocked",
                "message": "Execution blocked: Global Emergency Stop is currently engaged.",
                "elapsed_ms": 0.2,
            }

        # Phase 2: Intent Understanding
        intent: UserIntent = self.intent_classifier.classify(raw_text)
        if intent.is_ambiguous:
            return {
                "status": "ambiguous",
                "message": intent.clarification_needed or "Instruction is ambiguous.",
                "intent": intent.to_dict(),
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
            }

        # Fast-path Emergency Stop intent
        if intent.action == "emergency_stop":
            self.emergency_stop()
            return {
                "status": "emergency_stopped",
                "message": "Emergency Stop engaged. All active processes and vision devices halted.",
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
            }

        # Phase 3: Context Retrieval
        retrieved_context = self.memory.search(raw_text, limit=3)
        context_prompt = self.memory.format_context_prompt(raw_text, limit=3)

        # Record turn in short-term conversation memory
        self.memory.store(
            content=f"User: {raw_text}",
            category=MemoryCategory.SHORT_TERM_CONVERSATION,
            source=source,
        )

        # Route specialized agent fast-path for single-action research/coding/document/monitoring
        if intent.category in (IntentCategory.RESEARCH, IntentCategory.CODING, IntentCategory.DOCUMENT, IntentCategory.SYSTEM_CONTROL):
            return self._handle_specialized_intent(intent, confirmed=confirmed, t0=t0)

        # Phase 4: Task Planning
        plan = self.planner.plan(raw_text)
        with self._lock:
            self.active_plan = plan

        # Phase 5: Risk Classification & Phase 6: Approval Gate
        for step in plan.steps:
            risk_tier = RiskPolicy.classify(step.tool_name, step.parameters)
            step.risk_tier = risk_tier.value
            if RiskPolicy.requires_approval(risk_tier):
                step.requires_approval = True

        # Phase 7 to 10: Execution, Observation, Verification, Memory Update
        exec_res = self.planner.execute_plan(plan, approved_step_id=plan.steps[0].step_id if confirmed else None)

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        self._last_turn_metrics = {
            "intent": intent.to_dict(),
            "elapsed_ms": elapsed_ms,
            "status": exec_res.get("status"),
        }

        # Phase 11: User Response Synthesis
        return self._format_agent_response(plan, exec_res, intent, elapsed_ms)

    def _handle_specialized_intent(
        self,
        intent: UserIntent,
        confirmed: bool = False,
        t0: float = 0.0,
    ) -> Dict[str, Any]:
        """Dispatch directly to a specialized agent for focused domain operations."""
        agent_type = intent.suggested_agent
        agent = self.agents.get_agent(agent_type)
        if not agent:
            # Fallback to standard planner
            plan = self.planner.plan(intent.raw_text)
            exec_res = self.planner.execute_plan(plan)
            return self._format_agent_response(plan, exec_res, intent, round((time.perf_counter() - t0) * 1000, 1))

        # Risk check
        action_name = intent.suggested_tools[0] if intent.suggested_tools else intent.action
        prov = ActionProvenance(
            action_id=f"act_{int(time.time()*1000)}",
            initiator="user_direct",
            parent_agent=agent.name,
        )
        allowed, tier, reason = self.security.evaluate_action(
            action_name=action_name,
            parameters=intent.parameters,
            provenance=prov,
            confirmed=confirmed,
        )
        if not allowed:
            return {
                "status": "awaiting_approval",
                "action": action_name,
                "risk_tier": tier.value,
                "reason": reason,
                "parameters": intent.parameters,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
            }

        # Tool execution
        res = agent.execute(tool_name=action_name, parameters=intent.parameters)
        verified, v_err = agent.verify(tool_name=action_name, result=res)
        if not verified:
            res["verification_error"] = v_err
            res["status"] = "verification_failed"

        # Memory update
        self.memory.store(
            content=f"Executed {action_name}: {intent.target or ''} -> {res.get('status')}",
            category=MemoryCategory.TASK_HISTORY,
            source="agent_core",
        )

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "status": res.get("status", "success"),
            "agent_used": agent.name,
            "intent": intent.to_dict(),
            "result": res,
            "verified": verified,
            "elapsed_ms": elapsed_ms,
        }

    # -------------------------------------------------------------
    # 2. APPROVAL, PAUSE, CANCEL & CONTROL
    # -------------------------------------------------------------

    def approve_step(self, plan_id: Optional[str] = None, step_id: Optional[int] = None) -> Dict[str, Any]:
        """Approve a gated step in the active or specified plan and resume execution."""
        with self._lock:
            plan = self.active_plan
            if not plan:
                return {"status": "error", "message": "No active plan to approve."}
            if plan_id and plan.plan_id != plan_id:
                return {"status": "error", "message": f"Plan ID mismatch: active is {plan.plan_id}"}

            target_step = step_id or plan.awaiting_step_id
            if not target_step:
                return {"status": "error", "message": "No step is currently awaiting approval."}

            exec_res = self.planner.execute_plan(plan, approved_step_id=target_step)
            return {
                "status": "success",
                "approved_step_id": target_step,
                "execution": exec_res,
                "plan": plan.to_dict(),
            }

    def reject_step(self, plan_id: Optional[str] = None, step_id: Optional[int] = None, reason: str = "User rejected") -> Dict[str, Any]:
        """Reject a gated step and cascade blocking to dependents."""
        with self._lock:
            plan = self.active_plan
            if not plan:
                return {"status": "error", "message": "No active plan to reject."}

            target_step = step_id or plan.awaiting_step_id
            for s in plan.steps:
                if s.step_id == target_step:
                    s.status = "failed"
                    s.error = f"Rejected by user: {reason}"
                    break

            plan.status = TaskStatus.FAILED
            plan.error_details = f"Step {target_step} rejected by user: {reason}"
            return {
                "status": "success",
                "action": "rejected",
                "rejected_step_id": target_step,
                "plan": plan.to_dict(),
            }

    def pause_task(self) -> Dict[str, Any]:
        """Pause execution of the active plan."""
        with self._lock:
            if not self.active_plan:
                return {"status": "error", "message": "No active plan to pause."}
            ok = self.active_plan.pause()
            return {"status": "success" if ok else "ignored", "action": "paused", "plan": self.active_plan.to_dict()}

    def resume_task(self) -> Dict[str, Any]:
        """Resume execution of a paused plan."""
        with self._lock:
            if not self.active_plan:
                return {"status": "error", "message": "No active plan to resume."}
            ok = self.active_plan.resume()
            if ok:
                exec_res = self.planner.execute_plan(self.active_plan)
                return {"status": "success", "action": "resumed", "execution": exec_res, "plan": self.active_plan.to_dict()}
            return {"status": "error", "message": "Plan is not paused."}

    def cancel_task(self, reason: str = "User cancelled") -> Dict[str, Any]:
        """Cancel the active plan."""
        with self._lock:
            if not self.active_plan:
                return {"status": "error", "message": "No active plan to cancel."}
            self.active_plan.cancel(reason=reason)
            return {"status": "success", "action": "cancelled", "plan": self.active_plan.to_dict()}

    def emergency_stop(self) -> Dict[str, Any]:
        """Trigger emergency stop: lock security down, stop active plan, halt specialized agents."""
        with self._lock:
            self.security.engage_emergency_stop()
            if self.active_plan:
                self.active_plan.cancel(reason="Global Emergency Stop engaged")
            self.agents.shutdown_all()
            return {"status": "success", "action": "emergency_stop_all_engaged"}

    # -------------------------------------------------------------
    # 3. HELPER RESPONSE FORMATTING
    # -------------------------------------------------------------

    def _format_agent_response(
        self,
        plan: TaskPlan,
        exec_res: Dict[str, Any],
        intent: UserIntent,
        elapsed_ms: float,
    ) -> Dict[str, Any]:
        st = exec_res.get("status")
        if st == "awaiting_approval":
            msg = f"Task '{plan.goal}' requires approval for step {exec_res.get('awaiting_step_id')}: {exec_res.get('description')} ({exec_res.get('tool_name')})"
        elif st == "completed":
            msg = f"Task completed successfully: {plan.goal}"
        elif st == "failed":
            msg = f"Task execution failed: {exec_res.get('error') or 'Encountered unresolvable error'}"
        else:
            msg = f"Task status: {st}"

        return {
            "status": st or "success",
            "message": msg,
            "intent": intent.to_dict(),
            "execution": exec_res,
            "plan": plan.to_dict(),
            "elapsed_ms": elapsed_ms,
        }

    def get_telemetry(self) -> Dict[str, Any]:
        """Collect telemetry for Control Center dashboard."""
        with self._lock:
            plan_data = self.active_plan.to_dict() if self.active_plan else None
            return {
                "active_plan": plan_data,
                "emergency_stop_engaged": self.security.is_emergency_stopped,
                "active_specialized_agents": self.agents.list_active_agents(),
                "available_agent_types": self.agents.list_available_agent_types(),
                "last_turn_metrics": self._last_turn_metrics,
            }
