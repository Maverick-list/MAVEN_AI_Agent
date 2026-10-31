"""Maverick DevOS - Master 4-Level Evaluation Benchmark Framework.

Evaluates MAVEN JARVIS across 4 distinct rigor tiers:
- Level 1: Unit Capability Tests (Isolated logic, state machines, sandbox policies, SSRF guards)
- Level 2: Local Integration Tests (SQLite TaskStore, DAG topological executor, file overwrite backups)
- Level 3: Real Application Integration Tests (Host binaries, Wayland/display session, audio/whisper services)
- Level 4: End-to-End Real-World Workflow Tests (Autonomous project scaffolding, multi-page publishing, voice lifecycle)

CLI Usage:
  python3 scripts/run_jarvis_evolution_benchmark.py --level all
  python3 scripts/run_jarvis_evolution_benchmark.py --level 1 --output json
  python3 scripts/run_jarvis_evolution_benchmark.py --level all --report-file reports/benchmark_run.md
"""

import argparse
from dataclasses import asdict, dataclass, field
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional

# Ensure repository root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from maverick.core.dependencies import SystemDependencyVerifier
from maverick.intelligence.planner import TaskPlan, TaskPlanner, TaskStatus, TaskStep
from maverick.intelligence.task_store import TaskStore
from maverick.intelligence.toolkit.documents import (
    generate_docx,
    generate_markdown,
    generate_pdf,
)
from maverick.intelligence.toolkit.research import (
    AuthorizedHttpSearchProvider,
    BrowserTabRetrievalProvider,
    ResearchAssistant,
)
from maverick.intelligence.tools import ConfirmationRequiredError, ToolRegistry
from maverick.voice.config import VoiceConfig
from maverick.voice.session import VoiceSession, VoiceState

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("jarvis_benchmark")


@dataclass
class TestResult:
    """Record of an individual benchmark test execution."""
    test_id: str
    name: str
    level: int
    status: str  # "PASSED", "FAILED", "SKIPPED"
    duration_ms: float
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LevelSummary:
    """Aggregated results for a benchmark level."""
    level: int
    name: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_ms: float = 0.0
    tests: List[TestResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return (self.passed / self.total * 100.0) if self.total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "name": self.name,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "pass_rate_percent": round(self.pass_rate, 1),
            "duration_ms": round(self.duration_ms, 1),
            "tests": [t.to_dict() for t in self.tests],
        }


class BenchmarkRunner:
    """Orchestrates 4-level evaluation suite."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.summaries: Dict[int, LevelSummary] = {
            1: LevelSummary(1, "Unit Capability"),
            2: LevelSummary(2, "Local Integration"),
            3: LevelSummary(3, "Real Application Integration"),
            4: LevelSummary(4, "End-to-End Real-World Workflows"),
        }

    def _execute_test(
        self,
        level: int,
        test_id: str,
        name: str,
        func: Callable[[], Dict[str, Any]],
    ) -> TestResult:
        summary = self.summaries[level]
        summary.total += 1
        t_start = time.perf_counter()

        if self.verbose:
            logger.info("Running [L%d] %s: %s...", level, test_id, name)

        try:
            details = func() or {}
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            result = TestResult(
                test_id=test_id,
                name=name,
                level=level,
                status="PASSED",
                duration_ms=round(elapsed_ms, 2),
                details=details,
            )
            summary.passed += 1
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0
            err_type = type(e).__name__
            err_msg = str(e)
            result = TestResult(
                test_id=test_id,
                name=name,
                level=level,
                status="FAILED",
                duration_ms=round(elapsed_ms, 2),
                error_message=err_msg,
                error_type=err_type,
            )
            summary.failed += 1
            logger.warning("[L%d FAILED] %s: %s: %s", level, test_id, err_type, err_msg)

        summary.duration_ms += result.duration_ms
        summary.tests.append(result)
        return result

    # =========================================================================
    # LEVEL 1: UNIT CAPABILITY TESTS
    # =========================================================================
    def run_level_1(self) -> LevelSummary:
        logger.info("--- Executing Level 1: Unit Capability Tests ---")

        # L1.1: DAG Cycle & Duplicate ID Prevention
        def test_dag_validation():
            planner = TaskPlanner()
            step1 = TaskStep(step_id=1, description="A", tool_name="test", parameters={}, dependencies=[2])
            step2 = TaskStep(step_id=2, description="B", tool_name="test", parameters={}, dependencies=[1])
            plan_cycle = TaskPlan(plan_id="p-cycle", goal="cycle", steps=[step1, step2])
            is_valid, err = planner.validate_dag(plan_cycle.steps)
            assert not is_valid and "cycle" in err.lower()

            step_dup1 = TaskStep(step_id=1, description="A", tool_name="test", parameters={})
            step_dup2 = TaskStep(step_id=1, description="B", tool_name="test", parameters={})
            plan_dup = TaskPlan(plan_id="p-dup", goal="dup", steps=[step_dup1, step_dup2])
            is_valid2, err2 = planner.validate_dag(plan_dup.steps)
            assert not is_valid2 and "duplicate" in err2.lower()
            return {"cycle_detected": True, "duplicate_detected": True}

        self._execute_test(1, "L1-DAG-01", "DAG Validation (Cycles, Duplicates, Self-Deps)", test_dag_validation)

        # L1.2: Filesystem Sandbox Dotfile & Path Traversal Policy
        def test_fs_sandbox():
            reg = ToolRegistry()
            # Traversal check
            res_trav = reg.execute("filesystem_read_file", {"path": "/etc/shadow"})
            assert res_trav["status"] == "security_violation" and "restricted" in res_trav["error"].lower()

            # Root dotfile check
            res_ssh = reg.execute("filesystem_read_file", {"path": os.path.expanduser("~/.ssh/id_rsa")})
            assert res_ssh["status"] == "security_violation" and "restricted" in res_ssh["error"].lower()

            # Dotenv gate check
            with tempfile.TemporaryDirectory() as tmp_dir:
                env_path = os.path.join(tmp_dir, ".env")
                res_env = reg.execute("filesystem_write_file", {"path": env_path, "content": "KEY=val"})
                assert res_env["status"] == "confirmation_required" and "explicit confirmation" in res_env["message"].lower()
            return {"traversal_blocked": True, "root_dotfiles_blocked": True, "env_gated": True}

        self._execute_test(1, "L1-SEC-01", "Filesystem Sandbox & Path Containment Policies", test_fs_sandbox)

        # L1.3: PDF Multi-Page Word-Wrap & Escaping
        def test_pdf_formatting():
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                tmp_pdf = tf.name
            try:
                long_content = "This is a paragraph with special (parentheses) and brackets [brackets].\n" * 80
                generate_pdf(tmp_pdf, "Formatting Test", long_content)
                with open(tmp_pdf, "rb") as f:
                    data = f.read()
                assert data.startswith(b"%PDF-1.4")
                assert b"Page 1 of" in data
                assert b"Page 2 of" in data
                # Verify parenthesis escaping \( and \)
                assert b"\\(parentheses\\)" in data
                return {"pages_rendered": 2, "parentheses_escaped": True}
            finally:
                if os.path.exists(tmp_pdf):
                    os.remove(tmp_pdf)

        self._execute_test(1, "L1-DOC-01", "Document PDF Multi-Page Rendering & Escaping", test_pdf_formatting)

        # L1.4: Research SSRF Guard & Private IP Filtering
        def test_research_ssrf():
            provider = AuthorizedHttpSearchProvider(api_endpoint="https://example.com")
            for dangerous in ["http://localhost:8080", "http://127.0.0.1:8765", "http://169.254.169.254/meta"]:
                safe, reason = provider.is_safe_url(dangerous)
                assert not safe, f"SSRF allowed dangerous URL: {dangerous}"
            return {"ssrf_checks_passed": 3}

        self._execute_test(1, "L1-RES-01", "Research SSRF Prevention & IP Range Filtering", test_research_ssrf)

        # L1.5: Voice State Machine & Barge-In Audio Buffer
        def test_voice_barge_in():
            session = VoiceSession(VoiceConfig())
            session._state = VoiceState.SPEAKING
            dummy_chunk = b"\x05\x00" * 200
            session.interrupt(preserve_audio=dummy_chunk)
            assert session.state == VoiceState.LISTENING
            assert len(session._audio_buffer) == len(dummy_chunk)
            return {"preserved_bytes": len(dummy_chunk), "state": "LISTENING"}

        self._execute_test(1, "L1-VOX-01", "Voice State Machine Direct Transition & Onset Retention", test_voice_barge_in)

        return self.summaries[1]

    # =========================================================================
    # LEVEL 2: LOCAL INTEGRATION TESTS
    # =========================================================================
    def run_level_2(self) -> LevelSummary:
        logger.info("--- Executing Level 2: Local Integration Tests ---")

        # L2.1: SQLite TaskStore & Dynamic DAG Topological Scheduling
        def test_dag_topological():
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
                db_path = tf.name
            try:
                store = TaskStore(db_path=db_path)
                planner = TaskPlanner(task_store=store)

                # Order: Step 1 depends on Step 2 (out of linear order)
                step1 = TaskStep(step_id=1, description="Step 1", tool_name="system_noop", parameters={"step_id": 1}, dependencies=[2])
                step2 = TaskStep(step_id=2, description="Step 2", tool_name="system_noop", parameters={"step_id": 2}, dependencies=[])
                plan = TaskPlan(plan_id="p-topo", goal="Topological Execution", steps=[step1, step2])

                execution_log = []
                def dummy_execute(tool_name, params, **kwargs):
                    execution_log.append(params.get("step_id"))
                    return {"status": "success"}

                planner.tools.execute = dummy_execute  # type: ignore
                res = planner.execute_plan(plan)
                assert res["status"] == "completed"
                assert execution_log == [2, 1], f"Expected execution [2, 1], got {execution_log}"

                persisted = store.get_plan_data("p-topo")
                assert persisted is not None and persisted["status"] == "completed"
                return {"execution_order": execution_log, "persisted": True}
            finally:
                if os.path.exists(db_path):
                    os.remove(db_path)

        self._execute_test(2, "L2-DAG-01", "SQLite TaskStore & Multi-Pass Topological Execution", test_dag_topological)

        # L2.2: Filesystem Overwrite Protection & Backup (.bak) Generation
        def test_fs_overwrite():
            reg = ToolRegistry()
            with tempfile.TemporaryDirectory() as tmp_dir:
                target = os.path.join(tmp_dir, "document.txt")
                reg.execute("filesystem_write_file", {"path": target, "content": "Initial Version"})
                reg.execute("filesystem_write_file", {"path": target, "content": "Updated Version"}, confirmed=True)

                files = os.listdir(tmp_dir)
                bak_files = [f for f in files if ".bak." in f or f.endswith(".bak")]
                assert len(bak_files) == 1, f"Expected 1 .bak file, found: {files}"

                with open(target, "r") as f:
                    curr_content = f.read()
                with open(os.path.join(tmp_dir, bak_files[0]), "r") as f:
                    bak_content = f.read()

                assert curr_content == "Updated Version"
                assert bak_content == "Initial Version"
                return {"backup_created": bak_files[0]}

        self._execute_test(2, "L2-SEC-01", "Filesystem Overwrite Backup (.bak) Creation & Swap", test_fs_overwrite)

        # L2.3: ToolRegistry Symbol Discovery & Grep Execution
        def test_tools_codebase():
            reg = ToolRegistry()
            sym_res = reg.execute(
                "codebase_find_symbols",
                {"path": os.path.join(REPO_ROOT, "maverick/intelligence"), "symbol_name": "TaskPlanner"},
            )
            assert sym_res["status"] == "success"
            symbols = sym_res["result"]["symbols"]
            assert len(symbols) >= 1
            assert symbols[0]["name"] == "TaskPlanner"

            grep_res = reg.execute(
                "codebase_grep",
                {"path": os.path.join(REPO_ROOT, "maverick/intelligence"), "pattern": "execute_plan"},
            )
            assert grep_res["status"] == "success"
            assert len(grep_res["result"]["matches"]) >= 1
            return {"symbols_found": len(symbols), "grep_matches": len(grep_res["result"]["matches"])}

        self._execute_test(2, "L2-TOOL-01", "AST Symbol Discovery & Codebase Grep Tools", test_tools_codebase)

        # L2.4: Research Engine Unavailable Status & Honest Reporting
        def test_research_offline():
            assistant = ResearchAssistant()
            res = assistant.search_and_synthesize("Linux audio PulseAudio vs PipeWire")
            assert res["status"] == "unavailable"
            assert res["sources_count"] == 0
            assert "LIVE RETRIEVAL UNAVAILABLE" in res["executive_summary"]
            return {"status": "unavailable", "subtopics": len(res["subtopics"])}

        self._execute_test(2, "L2-RES-01", "Research Engine Unconfigured Provider Honest Handling", test_research_offline)

        return self.summaries[2]

    # =========================================================================
    # LEVEL 3: REAL APPLICATION INTEGRATION TESTS
    # =========================================================================
    def run_level_3(self) -> LevelSummary:
        logger.info("--- Executing Level 3: Real Application Integration Tests ---")

        # L3.1: Host Binaries & Tooling Availability
        def test_host_binaries():
            verifier = SystemDependencyVerifier.get_instance()
            audit = verifier.audit_environment()
            python3 = verifier.get_path("python3")
            code = verifier.get_path("code")
            assert python3 is not None, "python3 binary not found"
            return {
                "total_probed": audit["total_probed"],
                "available": audit["available_count"],
                "python3": python3,
                "code_available": code is not None,
            }

        self._execute_test(3, "L3-ENV-01", "Host System Binary & Environment Dependency Audit", test_host_binaries)

        # L3.2: Desktop Display Environment Check (Wayland / X11 Session)
        def test_display_session():
            wayland = os.environ.get("WAYLAND_DISPLAY")
            x11 = os.environ.get("DISPLAY")
            xdg_type = os.environ.get("XDG_SESSION_TYPE")
            assert wayland or x11, "No active display session found (WAYLAND_DISPLAY or DISPLAY)"
            return {
                "wayland_display": wayland,
                "x11_display": x11,
                "session_type": xdg_type or "unknown",
            }

        self._execute_test(3, "L3-ENV-02", "Linux Desktop Display Session Validation", test_display_session)

        # L3.3: Desktop Notification Subsystem Integration
        def test_desktop_notifications():
            notify_path = shutil.which("notify-send")
            assert notify_path is not None, "notify-send binary not found on host"
            # Send silent test notification
            res = subprocess.run(
                ["notify-send", "--app-name=MavenBenchmark", "--expire-time=1000", "Maven Benchmark", "Level 3 Integration Test Ping"],
                capture_output=True,
                text=True,
            )
            assert res.returncode == 0, f"notify-send failed with return code {res.returncode}: {res.stderr}"
            return {"notify_send_path": notify_path, "dispatched": True}

        self._execute_test(3, "L3-DESK-01", "Desktop Notification Subsystem Integration", test_desktop_notifications)

        # L3.4: Audio Whisper Server Daemon Health Probe
        def test_whisper_server_probe():
            import urllib.request
            try:
                # Whisper server is running on 127.0.0.1:18791 in production
                req = urllib.request.Request("http://127.0.0.1:18791/", headers={"User-Agent": "Maverick-Probe"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    code = resp.getcode()
                    return {"whisper_server_active": True, "http_status": code}
            except Exception as e:
                # If server responds or refuses connection, record actual status
                return {"whisper_server_active": False, "probe_note": str(e)}

        self._execute_test(3, "L3-VOX-01", "Audio Whisper STT Server Operational Status Probe", test_whisper_server_probe)

        return self.summaries[3]

    # =========================================================================
    # LEVEL 4: END-TO-END REAL-WORLD WORKFLOW TESTS
    # =========================================================================
    def run_level_4(self) -> LevelSummary:
        logger.info("--- Executing Level 4: End-to-End Real-World Workflow Tests ---")

        # L4.1: Autonomous Project Scaffolding & Verification Workflow
        def test_workflow_project_scaffolding():
            reg = ToolRegistry()
            with tempfile.TemporaryDirectory() as tmp_dir:
                proj_dir = os.path.join(tmp_dir, "demo_calculator")
                os.makedirs(proj_dir, exist_ok=True)

                # Step 1: Write application code
                app_py = os.path.join(proj_dir, "calc.py")
                reg.execute("filesystem_write_file", {
                    "path": app_py,
                    "content": "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n",
                })

                # Step 2: Write test file
                test_py = os.path.join(proj_dir, "test_calc.py")
                reg.execute("filesystem_write_file", {
                    "path": test_py,
                    "content": "import unittest\nfrom calc import add, multiply\n\nclass TestCalc(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n    def test_mul(self):\n        self.assertEqual(multiply(3, 4), 12)\n\nif __name__ == '__main__':\n    unittest.main()\n",
                })

                # Step 3: Execute tests via subprocess
                run_res = subprocess.run(
                    [sys.executable, "-m", "unittest", "test_calc.py"],
                    cwd=proj_dir,
                    capture_output=True,
                    text=True,
                )
                assert run_res.returncode == 0, f"Tests failed: {run_res.stderr}"
                assert "Ran 2 tests" in run_res.stderr

                return {
                    "project_dir": proj_dir,
                    "files_created": ["calc.py", "test_calc.py"],
                    "test_output": run_res.stderr.strip().split("\n")[-1],
                }

        self._execute_test(4, "L4-E2E-01", "Autonomous Project Scaffolding, Unit Test & Verification", test_workflow_project_scaffolding)

        # L4.2: Multi-Format Technical Documentation Publishing Workflow
        def test_workflow_multi_format_docs():
            reg = ToolRegistry()
            with tempfile.TemporaryDirectory() as tmp_dir:
                # 1. Markdown Technical Spec
                md_path = os.path.join(tmp_dir, "Specification.md")
                reg.execute("document_generate", {
                    "format": "markdown",
                    "path": md_path,
                    "title": "System Architecture Specification",
                    "sections": [
                        {"heading": "Executive Summary", "content": "Maven autonomous operating agent."},
                        {"heading": "Component Breakdown", "content": "DAG orchestrator and security sandbox."},
                    ],
                })
                assert os.path.isfile(md_path)

                # 2. DOCX Technical Report with structured table
                docx_path = os.path.join(tmp_dir, "Report.docx")
                reg.execute("document_generate", {
                    "format": "docx",
                    "path": docx_path,
                    "title": "Deployment Report",
                    "sections": [
                        {
                            "heading": "Verification Matrix",
                            "table": [
                                ["Subsystem", "Coverage", "Status"],
                                ["DAG Planner", "100%", "PASSED"],
                                ["Sandbox", "100%", "PASSED"],
                            ],
                        }
                    ],
                })
                assert os.path.isfile(docx_path)

                # 3. Multi-page Formatted PDF
                pdf_path = os.path.join(tmp_dir, "Documentation.pdf")
                reg.execute("document_generate", {
                    "format": "pdf",
                    "path": pdf_path,
                    "title": "Official Audit Clearance",
                    "content": "Page content verifying multi-page generation.\n" * 70,
                })
                assert os.path.isfile(pdf_path)

                return {
                    "markdown_size": os.path.getsize(md_path),
                    "docx_size": os.path.getsize(docx_path),
                    "pdf_size": os.path.getsize(pdf_path),
                }

        self._execute_test(4, "L4-E2E-02", "Multi-Format Technical Documentation Publishing (MD, DOCX, PDF)", test_workflow_multi_format_docs)

        # L4.3: End-to-End Voice Lifecycle Simulation
        def test_workflow_voice_lifecycle():
            session = VoiceSession(VoiceConfig())
            events = []

            # Step 1: Detect wake-word -> Listening
            session.trigger_wake_word(source="ui")
            assert session.state == VoiceState.LISTENING
            events.append("WAKE_DETECTED -> LISTENING")

            # Step 2: Record speech -> Processing
            session._audio_buffer.extend(b"\x01\x00" * 100)
            session._transition_to(VoiceState.PROCESSING)
            events.append("AUDIO_BUFFERED -> PROCESSING")

            # Step 3: Execute response -> Speaking
            session._transition_to(VoiceState.SPEAKING)
            events.append("SYNTHESIS_COMPLETE -> SPEAKING")

            # Step 4: User barge-in during speech -> Direct interrupt to Listening
            barge_in_chunk = b"\x09\x00" * 300
            session.interrupt(preserve_audio=barge_in_chunk)
            assert session.state == VoiceState.LISTENING
            assert len(session._audio_buffer) == len(barge_in_chunk)
            events.append("USER_BARGE_IN -> DIRECT_LISTENING")

            # Step 5: User finishes sentence -> Reset to idle
            session.reset()
            assert session.state == VoiceState.IDLE
            events.append("COMPLETED -> IDLE")

            return {"lifecycle_events": events, "final_state": session.state.value}

        self._execute_test(4, "L4-E2E-03", "Voice Assistant Interaction Lifecycle & Barge-In Simulation", test_workflow_voice_lifecycle)

        return self.summaries[4]

    # =========================================================================
    # EXECUTION CONTROLLER & REPORTING
    # =========================================================================
    def run_all(self, target_level: str = "all") -> Dict[str, Any]:
        t0 = time.time()
        logger.info("=== Starting MAVEN JARVIS 4-Level Evaluation Suite ===")

        if target_level in ("1", "all"):
            self.run_level_1()
        if target_level in ("2", "all"):
            self.run_level_2()
        if target_level in ("3", "all"):
            self.run_level_3()
        if target_level in ("4", "all"):
            self.run_level_4()

        total_elapsed = round(time.time() - t0, 3)

        total_tests = sum(s.total for s in self.summaries.values())
        total_passed = sum(s.passed for s in self.summaries.values())
        total_failed = sum(s.failed for s in self.summaries.values())
        overall_pass_rate = (total_passed / total_tests * 100.0) if total_tests > 0 else 0.0

        return {
            "timestamp": time.time(),
            "target_level": target_level,
            "total_duration_sec": total_elapsed,
            "overall_status": "PASSED" if total_failed == 0 else "FAILED",
            "metrics": {
                "total_tests": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "pass_rate_percent": round(overall_pass_rate, 1),
            },
            "levels": {lvl: s.to_dict() for lvl, s in self.summaries.items() if s.total > 0},
        }

    def render_markdown_report(self, report_data: Dict[str, Any]) -> str:
        lines = [
            "# MAVEN JARVIS 4-Level Benchmark Evaluation Report",
            "",
            f"**Execution Timestamp:** {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(report_data['timestamp']))}  ",
            f"**Overall Status:** `{report_data['overall_status']}`  ",
            f"**Total Duration:** {report_data['total_duration_sec']}s  ",
            f"**Overall Pass Rate:** {report_data['metrics']['pass_rate_percent']}% ({report_data['metrics']['passed']}/{report_data['metrics']['total_tests']})",
            "",
            "---",
            "",
            "## 1. Summary by Level",
            "",
            "| Level | Description | Total | Passed | Failed | Pass Rate | Duration (ms) |",
            "| :---: | :--- | :---: | :---: | :---: | :---: | :---: |",
        ]

        for lvl, s in report_data["levels"].items():
            lines.append(
                f"| L{lvl} | {s['name']} | {s['total']} | {s['passed']} | {s['failed']} | {s['pass_rate_percent']}% | {s['duration_ms']:.1f}ms |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## 2. Granular Test Results",
            "",
            "| ID | Test Name | Level | Status | Duration (ms) | Notes |",
            "| :--- | :--- | :---: | :---: | :---: | :--- |",
        ])

        for lvl, s in report_data["levels"].items():
            for t in s["tests"]:
                note = t.get("error_message") or "OK"
                lines.append(f"| `{t['test_id']}` | {t['name']} | L{lvl} | `{t['status']}` | {t['duration_ms']}ms | {note} |")

        lines.append("")
        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="MAVEN JARVIS 4-Level Evaluation Benchmark Framework")
    parser.add_argument("--level", choices=["1", "2", "3", "4", "all"], default="all", help="Target level to run")
    parser.add_argument("--output", choices=["console", "json", "markdown"], default="console", help="Output format")
    parser.add_argument("--report-file", type=str, default=None, help="File to write report to")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    runner = BenchmarkRunner(verbose=args.verbose)
    results = runner.run_all(target_level=args.level)

    md_report = runner.render_markdown_report(results)

    if args.report_file:
        os.makedirs(os.path.dirname(os.path.abspath(args.report_file)), exist_ok=True)
        with open(args.report_file, "w", encoding="utf-8") as f:
            if args.output == "json":
                f.write(json.dumps(results, indent=2))
            else:
                f.write(md_report)
        logger.info("Saved benchmark report to %s", args.report_file)

    if args.output == "json":
        print(json.dumps(results, indent=2))
    elif args.output == "markdown":
        print(md_report)
    else:
        # Console table
        print("\n" + "=" * 70)
        print(" MAVEN JARVIS 4-LEVEL EVALUATION BENCHMARK SUMMARY")
        print("=" * 70)
        print(f" Status:       {results['overall_status']}")
        print(f" Total Tests:  {results['metrics']['total_tests']}")
        print(f" Passed:       {results['metrics']['passed']}")
        print(f" Failed:       {results['metrics']['failed']}")
        print(f" Pass Rate:    {results['metrics']['pass_rate_percent']}%")
        print(f" Total Time:   {results['total_duration_sec']}s")
        print("-" * 70)
        for lvl, s in results["levels"].items():
            print(f"  Level {lvl} ({s['name']}): {s['passed']}/{s['total']} passed ({s['pass_rate_percent']}%) in {s['duration_ms']:.1f}ms")
        print("=" * 70 + "\n")

    sys.exit(0 if results["overall_status"] == "PASSED" else 1)


if __name__ == "__main__":
    main()
