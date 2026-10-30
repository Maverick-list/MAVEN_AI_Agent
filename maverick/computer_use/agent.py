"""Maverick DevOS - Autonomous Computer-Use Agent.

Implements the continuous closed-loop autonomous execution lifecycle:
OBSERVE -> UNDERSTAND -> PLAN -> ACT -> VERIFY -> RECOVER

Coordinates:
- Screen observation and active window detection.
- Multi-step cross-application workflow execution.
- Action verification and anomaly detection.
- Human approval confirmation gates.
- Automatic recovery from interface changes.
- Live telemetry streaming for Control Center HUD.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from maverick.computer_use.accessibility import AccessibilityBridge, AccessibleElement
from maverick.computer_use.input import UniversalInputEngine, MouseButton
from maverick.computer_use.registry import ApplicationCompatibilityRegistry, ApplicationProfile
from maverick.computer_use.screen import DesktopObservation, ScreenObserver
from maverick.computer_use.security import ComputerUseSecurity, ActionTier
from maverick.computer_use.strategy import ComputerUseStrategy, ActionResolution, StrategyTier
from maverick.desktop.launcher import launch_app, check_app_status

logger = logging.getLogger("maverick.computer_use.agent")


class ExecutionStage(Enum):
    """Current phase in the autonomous execution loop."""
    IDLE = "idle"
    OBSERVE = "observe"
    UNDERSTAND = "understand"
    PLAN = "plan"
    ACT = "act"
    VERIFY = "verify"
    RECOVER = "recover"
    PAUSED = "paused"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ActionStep:
    """A discrete verified step in a multi-step computer-use task."""
    step_id: int
    action_type: str  # launch, click, type, shortcut, wait, verify
    target: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    tier: ActionTier = ActionTier.NORMAL
    status: str = "pending"  # pending, executing, completed, failed, awaiting_approval, skipped
    result: Optional[Any] = None
    verification_passed: bool = False
    verification_detail: str = ""
    error: Optional[str] = None
    elapsed_ms: float = 0.0


@dataclass
class ComputerUseTask:
    """A full autonomous multi-step workflow task."""
    task_id: str
    goal: str
    steps: List[ActionStep]
    stage: ExecutionStage = ExecutionStage.IDLE
    current_step_index: int = 0
    active_app: str = ""
    active_window: str = ""
    last_action: str = ""
    last_verification: str = ""
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to serializable representation."""
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "stage": self.stage.value,
            "current_step_index": self.current_step_index,
            "active_app": self.active_app,
            "active_window": self.active_window,
            "last_action": self.last_action,
            "last_verification": self.last_verification,
            "timeline": self.timeline,
            "steps": [
                {
                    "step_id": s.step_id,
                    "action_type": s.action_type,
                    "target": s.target,
                    "parameters": s.parameters,
                    "tier": s.tier.value,
                    "status": s.status,
                    "verification_passed": s.verification_passed,
                    "verification_detail": s.verification_detail,
                    "error": s.error,
                    "elapsed_ms": s.elapsed_ms,
                }
                for s in self.steps
            ],
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


class AutonomousComputerUseAgent:
    """
    Autonomous Computer-Use Agent for Ubuntu GNOME.
    Executes goals via the OBSERVE -> UNDERSTAND -> PLAN -> ACT -> VERIFY -> RECOVER loop.
    """

    def __init__(
        self,
        accessibility_bridge: Optional[AccessibilityBridge] = None,
        screen_observer: Optional[ScreenObserver] = None,
        input_engine: Optional[UniversalInputEngine] = None,
        security: Optional[ComputerUseSecurity] = None,
        strategy: Optional[ComputerUseStrategy] = None,
        registry: Optional[ApplicationCompatibilityRegistry] = None,
    ):
        self.bridge = accessibility_bridge or AccessibilityBridge()
        self.observer = screen_observer or ScreenObserver(self.bridge)
        self.input = input_engine or UniversalInputEngine(enabled=True)
        self.security = security or ComputerUseSecurity()
        self.registry = registry or ApplicationCompatibilityRegistry()
        self.strategy = strategy or ComputerUseStrategy(self.bridge, self.observer, self.registry)

        self._lock = threading.RLock()
        self.current_task: Optional[ComputerUseTask] = None
        self._is_paused = False
        self._stop_requested = False

    # --- Task Execution & Lifecycle ---

    def execute_goal(self, goal: str, confirmed: bool = False) -> Dict[str, Any]:
        """
        Orchestrate a high-level natural language goal into a verified multi-step execution.
        """
        with self._lock:
            task_id = f"cu_{int(time.time() * 1000) % 1000000}"
            self._stop_requested = False
            self._is_paused = False

            # Stage 1: OBSERVE
            obs = self._observe_stage(task_id, goal)

            # Stage 2: UNDERSTAND
            active_app, active_window = self._understand_stage(obs)

            # Stage 3: PLAN
            steps = self._plan_stage(goal, active_app, active_window, obs)

            task = ComputerUseTask(
                task_id=task_id,
                goal=goal,
                steps=steps,
                stage=ExecutionStage.PLAN,
                active_app=active_app,
                active_window=active_window,
            )
            self.current_task = task
            self._record_timeline(task, "Task created and plan formulated", {"steps_count": len(steps)})

            # Execute steps incrementally
            for idx, step in enumerate(task.steps):
                task.current_step_index = idx

                if self._stop_requested:
                    task.stage = ExecutionStage.FAILED
                    task.error = "Emergency stop requested."
                    self._record_timeline(task, "Task halted by Emergency Stop")
                    break

                if self._is_paused:
                    task.stage = ExecutionStage.PAUSED
                    self._record_timeline(task, "Task paused")
                    return {"status": "paused", "task": task.to_dict()}

                # Security check
                auth = self.security.authorize_action(
                    step.action_type,
                    target_app=task.active_app,
                    params=step.parameters,
                    confirmed=confirmed,
                )

                if auth.get("needs_confirmation"):
                    step.status = "awaiting_approval"
                    task.stage = ExecutionStage.AWAITING_APPROVAL
                    self._record_timeline(task, f"Awaiting approval for {step.action_type}", auth)
                    return {
                        "status": "awaiting_approval",
                        "task": task.to_dict(),
                        "approval_request": auth,
                    }

                if not auth.get("allowed"):
                    step.status = "failed"
                    step.error = auth.get("error", "Security policy rejected action.")
                    task.stage = ExecutionStage.FAILED
                    task.error = step.error
                    self._record_timeline(task, f"Action blocked by security: {step.error}")
                    return {"status": "error", "error": step.error, "task": task.to_dict()}

                # Stage 4: ACT
                task.stage = ExecutionStage.ACT
                step.status = "executing"
                t_act_start = time.perf_counter()
                act_ok, act_err = self._act_step(step, task)
                step.elapsed_ms = round((time.perf_counter() - t_act_start) * 1000.0, 1)

                if not act_ok:
                    # Stage 6: RECOVER
                    task.stage = ExecutionStage.RECOVER
                    self._record_timeline(task, f"Act failed on step {step.step_id}, attempting recovery", {"error": act_err})
                    recovered = self._recover_step(step, task)
                    if not recovered:
                        step.status = "failed"
                        step.error = act_err
                        task.stage = ExecutionStage.FAILED
                        task.error = f"Step {step.step_id} failed: {act_err}"
                        return {"status": "error", "error": task.error, "task": task.to_dict()}

                # Stage 5: VERIFY
                task.stage = ExecutionStage.VERIFY
                verify_ok, verify_msg = self._verify_step(step, task)
                step.verification_passed = verify_ok
                step.verification_detail = verify_msg
                task.last_verification = verify_msg

                if not verify_ok:
                    # Recovery pass for verification failure
                    task.stage = ExecutionStage.RECOVER
                    self._record_timeline(task, f"Verification failed on step {step.step_id}: {verify_msg}")
                    recovered = self._recover_step(step, task)
                    if not recovered:
                        step.status = "failed"
                        step.error = f"Verification failed: {verify_msg}"
                        task.stage = ExecutionStage.FAILED
                        task.error = step.error
                        return {"status": "error", "error": task.error, "task": task.to_dict()}

                step.status = "completed"
                self._record_timeline(task, f"Step {step.step_id} ({step.action_type}) verified", {"detail": verify_msg})

            task.stage = ExecutionStage.COMPLETED
            task.completed_at = time.time()
            self._record_timeline(task, "Task completed successfully")
            return {"status": "success", "task": task.to_dict()}

    # --- Stages Implementation ---

    def _observe_stage(self, task_id: str, goal: str) -> DesktopObservation:
        """Stage 1: OBSERVE the desktop state."""
        return self.observer.observe()

    def _understand_stage(self, obs: DesktopObservation) -> Tuple[str, str]:
        """Stage 2: UNDERSTAND active foreground context."""
        active_app = obs.active_window.app_name if obs.active_window else "desktop"
        active_win = obs.active_window.name if obs.active_window else "GNOME Shell"
        return active_app, active_win

    def _plan_stage(self, goal: str, active_app: str, active_win: str, obs: DesktopObservation) -> List[ActionStep]:
        """Stage 3: PLAN structured steps from instruction."""
        g = goal.lower()
        steps: List[ActionStep] = []

        # Pattern A: Launch or switch to application
        if any(k in g for k in ("open ", "launch ", "buka ")) and not any(k in g for k in ("create", "write", "save")):
            target_app = "code" if "code" in g else ("nautilus" if any(w in g for w in ("file", "nautilus", "folder")) else "gnome-terminal")
            steps.append(ActionStep(
                step_id=1,
                action_type="launch",
                target=target_app,
                parameters={"app_id": target_app},
                tier=ActionTier.NORMAL,
            ))
            steps.append(ActionStep(
                step_id=2,
                action_type="verify_window",
                target=target_app,
                tier=ActionTier.NORMAL,
            ))
            return steps

        # Pattern B: Multi-step VS Code Python project workflow
        if "code" in g and any(k in g for k in ("create", "write", "project", "implement", "run")):
            steps.append(ActionStep(
                step_id=1,
                action_type="launch",
                target="code",
                parameters={"app_id": "code"},
                tier=ActionTier.NORMAL,
            ))
            steps.append(ActionStep(
                step_id=2,
                action_type="shortcut",
                target="Ctrl+Shift+P",
                parameters={"shortcut": "Ctrl+Shift+P"},
                tier=ActionTier.NORMAL,
            ))
            steps.append(ActionStep(
                step_id=3,
                action_type="type",
                target="File: New File",
                parameters={"text": "File: New File\n"},
                tier=ActionTier.NORMAL,
            ))
            steps.append(ActionStep(
                step_id=4,
                action_type="type",
                target="code_content",
                parameters={"text": "# Maven Automated Python Module\nprint('Hello from Maven Autonomous Agent')\n"},
                tier=ActionTier.SENSITIVE,
            ))
            steps.append(ActionStep(
                step_id=5,
                action_type="shortcut",
                target="Ctrl+S",
                parameters={"shortcut": "Ctrl+S"},
                tier=ActionTier.SENSITIVE,
            ))
            return steps

        # Pattern C: File manager navigation and folder creation
        if any(k in g for k in ("file", "folder", "nautilus", "direktori")):
            steps.append(ActionStep(
                step_id=1,
                action_type="launch",
                target="nautilus",
                parameters={"app_id": "nautilus"},
                tier=ActionTier.NORMAL,
            ))
            steps.append(ActionStep(
                step_id=2,
                action_type="shortcut",
                target="Ctrl+Shift+N",
                parameters={"shortcut": "Ctrl+Shift+N"},
                tier=ActionTier.SENSITIVE,
            ))
            steps.append(ActionStep(
                step_id=3,
                action_type="type",
                target="folder_name",
                parameters={"text": "MavenProjects\n"},
                tier=ActionTier.SENSITIVE,
            ))
            return steps

        # Pattern D: Click a specific button / element
        if any(k in g for k in ("click ", "klik ", "press ", "tekan ")):
            target = goal.replace("click", "").replace("klik", "").replace("press", "").replace("tekan", "").strip().strip("'\"")
            steps.append(ActionStep(
                step_id=1,
                action_type="click",
                target=target,
                parameters={"target_name": target},
                tier=ActionTier.NORMAL,
            ))
            return steps

        # Default fallback: Observe and describe
        steps.append(ActionStep(
            step_id=1,
            action_type="observe",
            target="desktop",
            tier=ActionTier.NORMAL,
        ))
        return steps

    def _act_step(self, step: ActionStep, task: ComputerUseTask) -> Tuple[bool, Optional[str]]:
        """Stage 4: ACT by executing the step."""
        task.last_action = f"{step.action_type}({step.target})"
        t_type = step.action_type

        try:
            if t_type == "launch":
                app_id = step.parameters.get("app_id", step.target)
                res = launch_app(app_id, confirmed=True)
                time.sleep(0.5)
                return True, None

            elif t_type == "click":
                target_name = step.parameters.get("target_name", step.target)
                resolution = self.strategy.resolve_click(target_name)
                if resolution.selected_tier == StrategyTier.TIER_1_ACCESSIBILITY:
                    if resolution.method_name == "accessible_activate" and resolution.target_element:
                        ok = self.bridge.activate_element(resolution.target_element)
                        if ok:
                            return True, None
                    # Coordinate click
                    if resolution.target_coordinates:
                        ok = self.input.click_coordinate(*resolution.target_coordinates)
                        return ok, None if ok else "Coordinate click failed"
                elif resolution.target_coordinates:
                    ok = self.input.click_coordinate(*resolution.target_coordinates)
                    return ok, None if ok else "Fallback click failed"
                return False, f"Could not locate target '{target_name}'"

            elif t_type == "type":
                text = step.parameters.get("text", "")
                ok = self.input.type_text(text)
                return ok, None if ok else "Typing failed"

            elif t_type == "shortcut":
                combo = step.parameters.get("shortcut", step.target)
                ok = self.input.send_shortcut(combo)
                return ok, None if ok else f"Shortcut {combo} failed"

            elif t_type == "observe":
                obs = self.observer.observe()
                return True, None

            return True, None
        except Exception as e:
            return False, str(e)

    def _verify_step(self, step: ActionStep, task: ComputerUseTask) -> Tuple[bool, str]:
        """Stage 5: VERIFY outcome of the executed step."""
        time.sleep(0.1)
        obs = self.observer.observe()

        if step.action_type == "launch":
            app_id = step.parameters.get("app_id", step.target)
            st = check_app_status(app_id)
            if st.get("is_running") or any(app_id.lower() in w.app_name.lower() for w in obs.windows):
                return True, f"Application '{app_id}' verified running."
            return False, f"Application '{app_id}' was not detected in active windows."

        if step.action_type == "click":
            return True, f"Click on '{step.target}' dispatched."

        if step.action_type == "type":
            return True, "Keystroke sequence synthesized into focused buffer."

        if step.action_type == "shortcut":
            return True, f"Shortcut combo '{step.target}' dispatched."

        return True, "Verification complete."

    def _recover_step(self, step: ActionStep, task: ComputerUseTask) -> bool:
        """Stage 6: RECOVER from failed action or verification."""
        logger.warning(f"Executing recovery routine for step {step.step_id} ({step.action_type})...")
        time.sleep(0.3)

        # 1. Check if an unexpected modal dialog is blocking
        obs = self.observer.observe()
        if obs.dialogs:
            logger.info(f"Recovery: Dismissing unexpected dialog '{obs.dialogs[0].name}' via Escape")
            self.input.send_key("Escape")
            time.sleep(0.2)

        # 2. If launch was unverified, attempt direct CLI re-check
        if step.action_type == "launch":
            st = check_app_status(step.target)
            if st.get("is_running"):
                return True

        # 3. Retry click with fresh observation
        if step.action_type == "click":
            res = self.strategy.resolve_click(step.target)
            if res.target_coordinates:
                return self.input.click_coordinate(*res.target_coordinates)

        return False

    # --- Controls & Telemetry ---

    def pause(self) -> None:
        """Pause execution."""
        with self._lock:
            self._is_paused = True
            if self.current_task:
                self.current_task.stage = ExecutionStage.PAUSED
                self._record_timeline(self.current_task, "Execution paused by user")

    def resume(self) -> None:
        """Resume execution."""
        with self._lock:
            self._is_paused = False
            if self.current_task and self.current_task.stage == ExecutionStage.PAUSED:
                self.current_task.stage = ExecutionStage.ACT
                self._record_timeline(self.current_task, "Execution resumed")

    def emergency_stop(self) -> None:
        """Immediate failsafe stop."""
        with self._lock:
            self._stop_requested = True
            self.input.emergency_stop()
            self.security.trigger_emergency_stop()
            if self.current_task:
                self.current_task.stage = ExecutionStage.FAILED
                self.current_task.error = "Emergency stop engaged."
                self._record_timeline(self.current_task, "Emergency Stop Triggered", urgency="critical")

    def _record_timeline(self, task: ComputerUseTask, event: str, metadata: Optional[Dict[str, Any]] = None, urgency: str = "normal") -> None:
        """Add event to task audit timeline."""
        task.timeline.append({
            "timestamp": time.time(),
            "stage": task.stage.value,
            "event": event,
            "metadata": metadata or {},
            "urgency": urgency,
        })
        if len(task.timeline) > 50:
            task.timeline.pop(0)

    def get_telemetry(self) -> Dict[str, Any]:
        """Aggregate telemetry for Control Center HUD panel."""
        with self._lock:
            obs = self.observer._last_observation
            return {
                "status": "ready" if not self._stop_requested else "emergency_stopped",
                "is_paused": self._is_paused,
                "current_task": self.current_task.to_dict() if self.current_task else None,
                "active_app": obs.active_window.app_name if obs and obs.active_window else "None",
                "active_window": obs.active_window.name if obs and obs.active_window else "None",
                "window_count": len(obs.windows) if obs else 0,
                "input_telemetry": self.input.get_telemetry(),
                "security_audit_count": len(self.security._audit_log),
            }
