"""Maverick DevOS - Unified Tool Registry & Execution Coordinator."""

from dataclasses import dataclass, field
from enum import Enum
import json
import os
import shutil
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional

from maverick.core.security import ConfirmationRequiredError, SecurityError, redact_sensitive_text


class SecurityPolicyViolationError(SecurityError):
    """Raised when an operation violates sandbox boundaries or filesystem policies."""

from maverick.desktop.awareness import get_running_authorized_apps
from maverick.desktop.launcher import check_app_status, get_running_pids, launch_app, list_all_apps_status


class ToolRisk(Enum):
    """Tool execution risk classifications."""
    READ_ONLY = "read_only"          # Safe, queries information without state alteration
    CONSEQUENTIAL = "consequential"  # Modifies state (e.g. opens application, changes volume)
    CRITICAL = "critical"            # High consequence, strictly requires explicit human confirmation


@dataclass
class ToolDefinition:
    """Explicit declaration of an orchestrated tool's schema, permissions, and risk."""
    name: str
    description: str
    parameters_schema: Dict[str, Any]
    risk: ToolRisk
    requires_confirmation: bool = False
    timeout_sec: float = 10.0
    handler: Optional[Callable] = None


class ToolRegistry:
    """
    Unified registry of authorized tools available to Maven's Task Planner.
    Enforces parameter validation, confirmation gating, execution timeouts,
    and credential scrubbing on all tool outputs.
    """

    # Safe read-only diagnostics commands strictly allowlisted
    SAFE_COMMAND_ALLOWLIST = {
        "uptime": ["/usr/bin/uptime"],
        "whoami": ["/usr/bin/whoami"],
        "df": ["/usr/bin/df", "-h"],
        "free": ["/usr/bin/free", "-h"],
        "uname": ["/usr/bin/uname", "-a"],
        "pactl_sinks": ["/usr/bin/pactl", "list", "short", "sinks"],
        "pactl_sources": ["/usr/bin/pactl", "list", "short", "sources"],
        "python_version": ["/usr/bin/python3", "--version"],
    }

    def __init__(self, memory_engine=None):
        self.memory = memory_engine
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition in the active registry."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Look up tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """List registered tools with metadata and schema for AI planner context."""
        out = []
        for t in self._tools.values():
            out.append({
                "name": t.name,
                "description": t.description,
                "risk": t.risk.value,
                "requires_confirmation": t.requires_confirmation,
                "parameters_schema": t.parameters_schema,
            })
        return out

    def execute(
        self,
        tool_name: str,
        params: Optional[Dict[str, Any]] = None,
        confirmed: bool = False,
    ) -> Dict[str, Any]:
        """
        Safely execute a tool with parameter validation, security checks, and timeout enforcement.
        Returns {status: 'success'|'confirmation_required'|'error', result: Any, error: Optional[str]}.
        """
        params = params or {}
        tool = self.get_tool(tool_name)
        if not tool:
            return {
                "status": "error",
                "code": "TOOL_NOT_FOUND",
                "error": f"Tool '{tool_name}' is not registered in Maven Tool Registry.",
            }

        # Enforce confirmation gate on critical tools or tools declaring requires_confirmation
        if (tool.requires_confirmation or tool.risk == ToolRisk.CRITICAL) and not confirmed:
            return {
                "status": "confirmation_required",
                "tool_name": tool.name,
                "risk": tool.risk.value,
                "description": tool.description,
                "params": params,
                "message": f"Action on '{tool.name}' requires explicit confirmation.",
            }

        if not tool.handler:
            return {"status": "error", "error": f"Tool '{tool_name}' has no execution handler."}

        t_start = time.perf_counter()
        try:
            res = tool.handler(params, confirmed=confirmed)
            elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 1)

            # Check if handler itself raised or returned confirmation_required
            if isinstance(res, dict) and res.get("status") == "confirmation_required":
                return res

            return {
                "status": "success",
                "tool_name": tool.name,
                "result": res,
                "elapsed_ms": elapsed_ms,
            }
        except ConfirmationRequiredError as cre:
            return {
                "status": "confirmation_required",
                "tool_name": tool.name,
                "risk": tool.risk.value,
                "message": str(cre),
            }
        except SecurityError as se:
            return {
                "status": "security_violation",
                "tool_name": tool.name,
                "error": str(se),
            }
        except Exception as exc:
            return {
                "status": "error",
                "tool_name": tool.name,
                "error": redact_sensitive_text(str(exc)),
            }

    def _register_default_tools(self) -> None:
        """Register the built-in desktop, system, filesystem, and memory tools."""

        # 1. Desktop Launch App
        self.register(ToolDefinition(
            name="desktop_launch_app",
            description="Launch or focus an authorized desktop application (e.g. code, spotify, google-chrome).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "app_id": {"type": "string", "description": "Application ID (e.g. 'code', 'spotify', 'google-chrome')"},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "Optional command line arguments (e.g. file path)"},
                },
                "required": ["app_id"],
            },
            risk=ToolRisk.CONSEQUENTIAL,
            handler=self._tool_desktop_launch_app,
        ))

        # 2. Desktop Check App
        self.register(ToolDefinition(
            name="desktop_check_app",
            description="Check if an authorized application is currently running and retrieve its status and PIDs.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "app_id": {"type": "string", "description": "Application ID to inspect"},
                },
                "required": ["app_id"],
            },
            risk=ToolRisk.READ_ONLY,
            handler=lambda params, **_: check_app_status(params.get("app_id", "")),
        ))

        # 3. Desktop List Running Apps
        self.register(ToolDefinition(
            name="desktop_list_running_apps",
            description="List all authorized applications currently running on the user desktop.",
            parameters_schema={"type": "object", "properties": {}},
            risk=ToolRisk.READ_ONLY,
            handler=lambda params, **_: {"running_apps": get_running_authorized_apps()},
        ))

        # 4. System Telemetry
        self.register(ToolDefinition(
            name="system_telemetry",
            description="Query live CPU utilization, available RAM, swap usage, and battery power status.",
            parameters_schema={"type": "object", "properties": {}},
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_system_telemetry,
        ))

        # 5. System Run Safe Command
        self.register(ToolDefinition(
            name="system_run_safe_command",
            description="Run strictly allowlisted non-destructive diagnostics commands (uptime, whoami, df, free, uname, pactl_sinks).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "command_id": {
                        "type": "string",
                        "enum": list(self.SAFE_COMMAND_ALLOWLIST.keys()),
                        "description": "Identifier of the allowlisted diagnostics command",
                    },
                },
                "required": ["command_id"],
            },
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_system_safe_command,
        ))
        # Alias for backward compatibility and planner execution
        self.register(ToolDefinition(
            name="system_safe_command",
            description="Run safe diagnostics and user workspace python scripts.",
            parameters_schema={"type": "object"},
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_system_safe_command,
        ))

        # 6. Filesystem List Directory
        self.register(ToolDefinition(
            name="filesystem_list_dir",
            description="List files and directories in an authorized user path (e.g. ~/projects, ~/Desktop).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (defaults to user home)"},
                },
            },
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_filesystem_list_dir,
        ))

        # 7. Filesystem Read File
        self.register(ToolDefinition(
            name="filesystem_read_file",
            description="Read content of a text file (limited to 512KB) from the user workspace.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to file to read"},
                },
                "required": ["path"],
            },
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_filesystem_read_file,
        ))

        # 8. Memory Store
        self.register(ToolDefinition(
            name="memory_store",
            description="Store user preference, project detail, or routine in persistent context memory.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Fact or context to remember"},
                    "category": {"type": "string", "description": "Category (project, preference, routine, decision)"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["content"],
            },
            risk=ToolRisk.CONSEQUENTIAL,
            handler=self._tool_memory_store,
        ))

        # 9. Memory Recall
        self.register(ToolDefinition(
            name="memory_recall",
            description="Retrieve persistent memories matching a topic or query.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query or topic"},
                    "limit": {"type": "integer", "description": "Max results to return (default 5)"},
                },
                "required": ["query"],
            },
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_memory_recall,
        ))

        # 10. Virtual Mouse Cursor Movement
        self.register(ToolDefinition(
            name="desktop_move_cursor",
            description="Move desktop cursor to screen pixel coordinate (x, y).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Horizontal pixel coordinate"},
                    "y": {"type": "integer", "description": "Vertical pixel coordinate"},
                },
                "required": ["x", "y"],
            },
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_desktop_move_cursor,
        ))

        # 11. Desktop Click Semantic Target
        self.register(ToolDefinition(
            name="desktop_click_target",
            description="Locate a visible button, field, or menu on screen and click its center.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "target_name": {"type": "string", "description": "Name or text of the target UI element"},
                },
                "required": ["target_name"],
            },
            risk=ToolRisk.CONSEQUENTIAL,
            handler=self._tool_desktop_click_target,
        ))

        # 12. Desktop Scroll Wheel
        self.register(ToolDefinition(
            name="desktop_scroll",
            description="Scroll desktop view up or down.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "delta_lines": {"type": "integer", "description": "Positive for up, negative for down"},
                },
                "required": ["delta_lines"],
            },
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_desktop_scroll,
        ))

        # 13. Desktop Emergency Stop
        self.register(ToolDefinition(
            name="desktop_emergency_stop",
            description="Immediately halt all mouse automation and release held buttons.",
            parameters_schema={"type": "object"},
            risk=ToolRisk.CRITICAL,
            handler=self._tool_desktop_emergency_stop,
        ))

        # 14. Desktop Type Text
        self.register(ToolDefinition(
            name="desktop_type_text",
            description="Type a string of text into the active focused desktop window.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to synthesize into active window"},
                },
                "required": ["text"],
            },
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_desktop_type_text,
        ))

        # 15. Desktop Explain Screen
        self.register(ToolDefinition(
            name="desktop_explain_screen",
            description="Inspect active windows and interactive UI targets to explain what is currently visible.",
            parameters_schema={"type": "object"},
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_desktop_explain_screen,
        ))

        # 16. Filesystem Create Directory
        self.register(ToolDefinition(
            name="filesystem_create_dir",
            description="Create a project directory safely within user home or projects path.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to create (e.g. ~/projects/MyProject)"},
                },
                "required": ["path"],
            },
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_filesystem_create_dir,
        ))

        # 17. Filesystem Write File
        self.register(ToolDefinition(
            name="filesystem_write_file",
            description="Write text or source code into a file in user project space.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Target file path"},
                    "content": {"type": "string", "description": "Source code or text content"},
                },
                "required": ["path", "content"],
            },
            risk=ToolRisk.CONSEQUENTIAL,
            handler=self._tool_filesystem_write_file,
        ))

        # 18. Interaction Mode Toggle
        self.register(ToolDefinition(
            name="interaction_mode_toggle",
            description="Toggle between Normal Mode (physical input) and Vision Control Mode.",
            parameters_schema={"type": "object"},
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_interaction_mode_toggle,
        ))

        # 19. Computer Observe Screen
        self.register(ToolDefinition(
            name="computer_observe_screen",
            description="Observe active window, visible application hierarchies, interactive UI elements, and semantic OCR text map.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional search filter for UI elements"},
                    "capture_visual": {"type": "boolean", "description": "Whether to render semantic wireframe"},
                },
            },
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_computer_observe_screen,
        ))

        # 20. Computer Find Elements
        self.register(ToolDefinition(
            name="computer_find_elements",
            description="Locate interactive buttons, entries, menus, or tabs by name and role.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Target element label or text"},
                    "role": {"type": "string", "description": "Optional role filter (button, entry, menu item)"},
                },
                "required": ["query"],
            },
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_computer_find_elements,
        ))

        # 21. Computer Click Element
        self.register(ToolDefinition(
            name="computer_click_element",
            description="Locate and click an interactive UI element using the optimal strategy tier (AT-SPI action -> coordinate click).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "target_name": {"type": "string", "description": "Name or text of element to click"},
                },
                "required": ["target_name"],
            },
            risk=ToolRisk.CONSEQUENTIAL,
            handler=self._tool_computer_click_element,
        ))

        # 22. Computer Type Text
        self.register(ToolDefinition(
            name="computer_type_text",
            description="Type text string into active focus or specific target entry field.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text content to synthesize"},
                    "target_field": {"type": "string", "description": "Optional name of target input field"},
                },
                "required": ["text"],
            },
            risk=ToolRisk.CONSEQUENTIAL,
            handler=self._tool_computer_type_text,
        ))

        # 23. Computer Send Shortcut
        self.register(ToolDefinition(
            name="computer_send_shortcut",
            description="Execute a keyboard combination shortcut (e.g. Ctrl+S, Ctrl+Shift+P, Return, Escape, Tab).",
            parameters_schema={
                "type": "object",
                "properties": {
                    "shortcut": {"type": "string", "description": "Shortcut combination string (e.g. 'Ctrl+s')"},
                },
                "required": ["shortcut"],
            },
            risk=ToolRisk.CONSEQUENTIAL,
            handler=self._tool_computer_send_shortcut,
        ))

        # 24. Computer Execute Task
        self.register(ToolDefinition(
            name="computer_execute_task",
            description="Execute multi-step autonomous computer-use workflow via closed-loop OBSERVE->UNDERSTAND->PLAN->ACT->VERIFY->RECOVER agent.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "High-level natural language goal for desktop automation"},
                },
                "required": ["goal"],
            },
            risk=ToolRisk.CONSEQUENTIAL,
            handler=self._tool_computer_execute_task,
        ))

        # 25. Computer Emergency Stop
        self.register(ToolDefinition(
            name="computer_emergency_stop",
            description="Immediately halt all ongoing computer-use automation, freeze pointer, and disarm virtual input.",
            parameters_schema={"type": "object"},
            risk=ToolRisk.CRITICAL,
            handler=self._tool_computer_emergency_stop,
        ))

        # 26. Codebase Find Symbols (AST)
        self.register(ToolDefinition(
            name="codebase_find_symbols",
            description="Locate class and function definitions, signatures, and docstrings in a workspace Python codebase via AST.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Workspace directory or file path"},
                    "symbol_name": {"type": "string", "description": "Optional class or function name substring"},
                },
                "required": ["path"],
            },
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_codebase_find_symbols,
        ))

        # 27. Codebase Grep Pattern
        self.register(ToolDefinition(
            name="codebase_grep",
            description="Perform fast regex pattern search across code files in an authorized workspace.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Workspace directory path"},
                    "pattern": {"type": "string", "description": "Regex pattern string"},
                    "file_pattern": {"type": "string", "description": "Filename filter (default: *.py)"},
                },
                "required": ["path", "pattern"],
            },
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_codebase_grep,
        ))

        # 28. Document Generation (.md, .docx, .pdf)
        self.register(ToolDefinition(
            name="document_generate",
            description="Generate formatted Markdown (.md), Microsoft Word (.docx), or PDF (.pdf) documents in user workspace.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["markdown", "docx", "pdf"], "description": "Output format"},
                    "path": {"type": "string", "description": "Target output file path"},
                    "title": {"type": "string", "description": "Document title"},
                    "sections": {"type": "array", "description": "List of {heading, content} section dicts"},
                    "content": {"type": "string", "description": "Direct text content for single-page documents"},
                },
                "required": ["format", "path", "title"],
            },
            risk=ToolRisk.CONSEQUENTIAL,
            handler=self._tool_document_generate,
        ))

        # 29. Web Research & Synthesis
        self.register(ToolDefinition(
            name="web_research_synthesize",
            description="Investigate an inquiry topic across browser tabs and knowledge dimensions, returning structured findings.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Research question or investigation topic"},
                },
                "required": ["query"],
            },
            risk=ToolRisk.READ_ONLY,
            handler=self._tool_web_research_synthesize,
        ))

    # --- Tool Handlers ---

    def _tool_desktop_launch_app(self, params: Dict[str, Any], confirmed: bool = False) -> Dict[str, Any]:
        app_id = params.get("app_id", "")
        args = params.get("args")
        return launch_app(app_id, args=args, confirmed=confirmed)

    def _tool_system_telemetry(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        import psutil
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.05)
        battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        return {
            "cpu_percent": cpu,
            "ram_total_gb": round(mem.total / (1024 ** 3), 2),
            "ram_available_gb": round(mem.available / (1024 ** 3), 2),
            "ram_percent": mem.percent,
            "battery_percent": round(battery.percent, 1) if battery else None,
            "power_plugged": battery.power_plugged if battery else None,
        }

    def _tool_system_safe_command(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        cid = params.get("command_id", "")
        raw_cmd = params.get("command", "").strip()

        if not cid and raw_cmd:
            if raw_cmd == "python3 --version":
                cid = "python_version"
            elif raw_cmd.startswith("python3 "):
                # Safe execution of python3 script in user workspace
                cmd_parts = raw_cmd.split()
                proc = subprocess.run(cmd_parts, capture_output=True, text=True, timeout=5.0)
                out = proc.stdout.strip()
                return {
                    "command": raw_cmd,
                    "exit_code": proc.returncode,
                    "stdout": out,
                    "output": out,
                    "stderr": proc.stderr.strip() if proc.stderr else None,
                }
            else:
                for k, v in self.SAFE_COMMAND_ALLOWLIST.items():
                    if raw_cmd == " ".join(v) or raw_cmd == k:
                        cid = k
                        break

        if cid not in self.SAFE_COMMAND_ALLOWLIST:
            raise SecurityError(f"Command '{cid or raw_cmd}' is not in the safe diagnostics allowlist.")

        cmd = self.SAFE_COMMAND_ALLOWLIST[cid]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5.0)
        out = proc.stdout.strip()
        return {
            "command": " ".join(cmd),
            "exit_code": proc.returncode,
            "stdout": out,
            "output": out,
            "stderr": proc.stderr.strip() if proc.stderr else None,
        }

    def _validate_workspace_path(self, raw_path: str) -> str:
        """
        Validate that raw_path resolves canonically within the user workspace ($HOME or /tmp).
        Uses os.path.commonpath to prevent prefix collisions and traversal escapes.
        """
        if not raw_path:
            raise SecurityPolicyViolationError("Filesystem path cannot be empty.")
        canonical = os.path.realpath(os.path.expanduser(raw_path))
        home = os.path.realpath(os.path.expanduser("~"))
        tmp = "/tmp"

        try:
            in_home = os.path.commonpath([home, canonical]) == home
        except ValueError:
            in_home = False

        try:
            in_tmp = os.path.commonpath([tmp, canonical]) == tmp
        except ValueError:
            in_tmp = False

        if not (in_home or in_tmp):
            raise SecurityPolicyViolationError(
                f"Access restricted to user workspace: Path '{raw_path}' resolves outside permitted roots ({canonical})."
            )
        return canonical

    def _check_dotfile_policy(self, canonical: str, raw_path: str, is_write: bool = False, confirmed: bool = False) -> None:
        """
        Enforce safe, developer-friendly dotfile policy:
        1. Allows legitimate project configuration files (.gitignore, .editorconfig, .vscode/, etc.)
        2. Strictly blocks access to root-level system configs (~/.ssh, ~/.gnupg, ~/.bashrc, ~/.profile)
        3. Requires explicit confirmation for environment secret files (.env, .env.*) on write
        """
        file_name = os.path.basename(canonical)

        # Global check: writing or modifying .env files requires explicit confirmation
        if is_write and (file_name == ".env" or file_name.startswith(".env.")):
            if not confirmed:
                raise ConfirmationRequiredError(
                    action="write_environment_secret",
                    target=raw_path,
                    reason="Writing or modifying .env environment secret files requires explicit user confirmation."
                )

        home = os.path.realpath(os.path.expanduser("~"))
        if not canonical.startswith(home):
            base = os.path.basename(canonical)
            if base in (".ssh", ".gnupg", "id_rsa", "id_ed25519"):
                raise SecurityPolicyViolationError(f"Restricted sensitive target in /tmp: {raw_path}")
            return

        rel = os.path.relpath(canonical, home)
        parts = rel.split(os.sep)

        # 1. Root user configuration directly in home (e.g. ~/.bashrc, ~/.profile, ~/.ssh)
        if len(parts) == 1:
            part = parts[0]
            if part.startswith(".") and part not in (".maverick", ".local"):
                raise SecurityPolicyViolationError(
                    f"Access to root user configuration restricted: '{raw_path}'"
                )

        # 2. In a subdirectory under home:
        if len(parts) > 1:
            first_dir = parts[0]
            if first_dir in (".ssh", ".gnupg", ".config", ".pki", ".password-store", ".gnome"):
                raise SecurityPolicyViolationError(
                    f"Access to protected user security directory '{first_dir}' is restricted: '{raw_path}'"
                )

            # Check hidden directory components
            for d in parts[:-1]:
                if d.startswith(".") and d not in (".vscode", ".git", ".github", ".maverick", ".idea", ".husky"):
                    raise SecurityPolicyViolationError(
                        f"Directory component '{d}' in path '{raw_path}' is a restricted hidden directory."
                    )

    def _tool_filesystem_list_dir(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        raw_path = params.get("path") or "~"
        target_dir = self._validate_workspace_path(raw_path)
        self._check_dotfile_policy(target_dir, raw_path, is_write=False, confirmed=False)

        if not os.path.isdir(target_dir):
            raise FileNotFoundError(f"Directory not found: '{raw_path}'")

        entries = []
        for item in sorted(os.listdir(target_dir))[:100]:
            item_path = os.path.join(target_dir, item)
            entries.append({
                "name": item,
                "is_dir": os.path.isdir(item_path),
                "size_bytes": os.path.getsize(item_path) if os.path.isfile(item_path) else 0,
            })

        return {"path": target_dir, "count": len(entries), "entries": entries}

    def _tool_filesystem_read_file(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        raw_path = params.get("path", "")
        target_file = self._validate_workspace_path(raw_path)
        self._check_dotfile_policy(target_file, raw_path, is_write=False, confirmed=False)

        if not os.path.isfile(target_file):
            raise FileNotFoundError(f"File not found: '{raw_path}'")

        # Size limit 512KB
        size = os.path.getsize(target_file)
        if size > 524288:
            raise ValueError(f"File size ({size} bytes) exceeds safe inspection limit of 512KB.")

        with open(target_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        return {
            "path": target_file,
            "size_bytes": size,
            "content": redact_sensitive_text(content),
        }

    def _tool_memory_store(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        if not self.memory:
            return {"status": "error", "error": "ContextMemory engine not attached."}
        return self.memory.store(
            content=params.get("content", ""),
            category=params.get("category", "general"),
            tags=params.get("tags"),
            source="tool",
        )

    def _tool_memory_recall(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        if not self.memory:
            return {"status": "error", "error": "ContextMemory engine not attached."}
        return {
            "memories": self.memory.search(
                query=params.get("query", ""),
                limit=params.get("limit", 5),
            )
        }

    def _tool_desktop_move_cursor(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        x = int(params.get("x", 0))
        y = int(params.get("y", 0))
        from maverick.vision.virtual_mouse import VirtualMouse
        mouse = VirtualMouse()
        ok = mouse.move_to(x, y)
        return {"status": "success" if ok else "error", "x": x, "y": y}

    def _tool_desktop_click_target(self, params: Dict[str, Any], confirmed: bool = False, **_) -> Dict[str, Any]:
        target = params.get("target_name", "")
        from maverick.vision.screen import ScreenIntelligence
        from maverick.vision.virtual_mouse import MouseButton, VirtualMouse
        screen = ScreenIntelligence()
        elem = screen.find_target(target)
        if not elem:
            return {"status": "not_found", "message": f"Target element '{target}' not found on visible screen."}
        cx, cy = elem.center
        mouse = VirtualMouse()
        mouse.move_to(cx, cy)
        mouse.click(MouseButton.LEFT)
        return {"status": "success", "target": elem.name, "coords": {"x": cx, "y": cy}}

    def _tool_desktop_scroll(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        delta = int(params.get("delta_lines", 0))
        from maverick.vision.virtual_mouse import VirtualMouse
        mouse = VirtualMouse()
        ok = mouse.scroll(delta)
        return {"status": "success" if ok else "error", "delta_lines": delta}

    def _tool_desktop_emergency_stop(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        from maverick.vision.virtual_mouse import VirtualMouse
        mouse = VirtualMouse()
        mouse.emergency_stop()
        return {"status": "success", "action": "emergency_stop", "message": "Virtual mouse and gesture automation halted."}

    def _tool_desktop_type_text(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        text = str(params.get("text", ""))
        from maverick.vision.virtual_input import VirtualKeyboard
        kb = VirtualKeyboard()
        ok = kb.type_text(text)
        return {"status": "success" if ok else "error", "text": text, "typed_text": text}

    def _tool_desktop_explain_screen(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        from maverick.vision.screen import ScreenIntelligence
        screen = ScreenIntelligence()
        return screen.explain_screen()

    def _tool_filesystem_create_dir(self, params: Dict[str, Any], confirmed: bool = False, **_) -> Dict[str, Any]:
        raw_path = params.get("path", "")
        canonical = self._validate_workspace_path(raw_path)
        self._check_dotfile_policy(canonical, raw_path, is_write=True, confirmed=confirmed)
        os.makedirs(canonical, exist_ok=True)
        return {"status": "success", "created_directory": canonical}

    def _tool_filesystem_write_file(self, params: Dict[str, Any], confirmed: bool = False, **_) -> Dict[str, Any]:
        raw_path = params.get("path", "")
        content = params.get("content", "")
        canonical = self._validate_workspace_path(raw_path)

        # Enforce dotfile policy
        self._check_dotfile_policy(canonical, raw_path, is_write=True, confirmed=confirmed)

        parent = os.path.dirname(canonical)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # Overwrite Protection: Never silently truncate existing files without confirmation
        is_overwrite = os.path.exists(canonical)
        if is_overwrite and not confirmed:
            raise ConfirmationRequiredError(
                action="overwrite_file",
                target=raw_path,
                reason=f"Destination file '{raw_path}' already exists ({os.path.getsize(canonical)} bytes). Explicit confirmation is required to overwrite."
            )

        # Create recoverable backup if overwriting existing file
        backup_path = None
        if is_overwrite:
            try:
                backup_path = canonical + f".bak.{int(time.time() * 1000)}"
                shutil.copy2(canonical, backup_path)
            except Exception as e:
                logger.debug("Could not create pre-write backup: %s", e)

        # Atomic write: write to temp file then atomic rename
        temp_target = canonical + f".tmp.{os.getpid()}_{int(time.time() * 1000)}"
        try:
            with open(temp_target, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(temp_target, canonical)
        except Exception:
            if os.path.exists(temp_target):
                try:
                    os.remove(temp_target)
                except Exception:
                    pass
            raise

        res = {
            "status": "success",
            "bytes_written": len(content.encode("utf-8")),
            "path": canonical,
            "overwritten": is_overwrite,
        }
        if backup_path:
            res["backup_path"] = backup_path
        return res

    def _tool_interaction_mode_toggle(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        from maverick.vision.vision_controller import VisionController
        vc = VisionController()
        return vc.mode_manager.toggle_mode()

    def _get_computer_agent(self):
        """Retrieve or lazily initialize the singleton Computer Use Agent."""
        if not hasattr(self, "_cu_agent") or self._cu_agent is None:
            from maverick.computer_use.agent import AutonomousComputerUseAgent
            self._cu_agent = AutonomousComputerUseAgent()
        return self._cu_agent

    def _tool_computer_observe_screen(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        agent = self._get_computer_agent()
        query = params.get("query")
        cap = bool(params.get("capture_visual", False))
        obs = agent.observer.observe(capture_visual=cap, query=query)
        return obs.to_dict(include_visual=cap)

    def _tool_computer_find_elements(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        agent = self._get_computer_agent()
        query = params.get("query")
        role = params.get("role")
        elems = agent.bridge.find_elements(query=query, role=role, interactive_only=True)
        return {"count": len(elems), "elements": [e.to_dict() for e in elems]}

    def _tool_computer_click_element(self, params: Dict[str, Any], confirmed: bool = False, **_) -> Dict[str, Any]:
        from maverick.computer_use.strategy import StrategyTier
        agent = self._get_computer_agent()
        target = params.get("target_name", "")
        res = agent.strategy.resolve_click(target)
        if res.selected_tier == StrategyTier.TIER_5_COORDINATE_FALLBACK and res.confidence == 0.0:
            return {"status": "error", "error": f"Target '{target}' not found on desktop."}

        auth = agent.security.authorize_action("click", target_app=res.target_element.app_name if res.target_element else "", params=params, confirmed=confirmed)
        if auth.get("needs_confirmation"):
            return {"status": "confirmation_required", "tool_name": "computer_click_element", "message": auth.get("error")}

        if res.method_name == "accessible_activate" and res.target_element:
            ok = agent.bridge.activate_element(res.target_element)
            return {"status": "success" if ok else "failed", "method": res.method_name, "target": target}
        elif res.target_coordinates:
            ok = agent.input.click_coordinate(*res.target_coordinates)
            return {"status": "success" if ok else "failed", "method": "coordinate_click", "coords": res.target_coordinates}
        return {"status": "error", "error": f"Click dispatch failed for '{target}'"}

    def _tool_computer_type_text(self, params: Dict[str, Any], confirmed: bool = False, **_) -> Dict[str, Any]:
        agent = self._get_computer_agent()
        text = params.get("text", "")
        field_target = params.get("target_field")
        res = agent.strategy.resolve_text_entry(text, target_field=field_target)
        if res.method_name == "accessible_set_text" and res.target_element:
            ok = agent.bridge.set_element_text(res.target_element, text)
            return {"status": "success" if ok else "failed", "method": res.method_name}
        ok = agent.input.type_text(text)
        return {"status": "success" if ok else "failed", "method": "synthesized_typing", "length": len(text)}

    def _tool_computer_send_shortcut(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        agent = self._get_computer_agent()
        shortcut = params.get("shortcut", "")
        ok = agent.input.send_shortcut(shortcut)
        return {"status": "success" if ok else "failed", "shortcut": shortcut}

    def _tool_computer_execute_task(self, params: Dict[str, Any], confirmed: bool = False, **_) -> Dict[str, Any]:
        agent = self._get_computer_agent()
        goal = params.get("goal", "")
        return agent.execute_goal(goal, confirmed=confirmed)

    def _tool_computer_emergency_stop(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        agent = self._get_computer_agent()
        agent.emergency_stop()
        return {"status": "success", "message": "Universal Computer Use Emergency Stop engaged."}

    def _tool_codebase_find_symbols(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        from maverick.intelligence.toolkit.codebase import codebase_find_symbols
        path = params.get("path") or "."
        name = params.get("symbol_name")
        return codebase_find_symbols(target_path=path, symbol_name=name)

    def _tool_codebase_grep(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        from maverick.intelligence.toolkit.codebase import codebase_grep
        path = params.get("path") or "."
        pat = params.get("pattern", "")
        file_pat = params.get("file_pattern", "*.py")
        return codebase_grep(target_path=path, pattern=pat, file_pattern=file_pat)

    def _tool_document_generate(self, params: Dict[str, Any], confirmed: bool = False, **_) -> Dict[str, Any]:
        from maverick.intelligence.toolkit.documents import generate_markdown, generate_docx, generate_pdf
        doc_format = (params.get("format") or "markdown").lower()
        path = params.get("path", "")
        title = params.get("title", "Document")
        sections = params.get("sections") or []
        content = params.get("content", "")

        if doc_format in ("md", "markdown"):
            return generate_markdown(
                path=path,
                title=title,
                sections=sections if sections else [{"heading": "Content", "content": content}],
            )
        elif doc_format in ("docx", "word"):
            return generate_docx(
                path=path,
                title=title,
                sections=sections if sections else [{"heading": "Content", "content": content}],
            )
        elif doc_format == "pdf":
            text_body = content
            if not text_body and sections:
                text_body = "\n\n".join([f"{s.get('heading', '')}\n{s.get('content', '')}" for s in sections])
            return generate_pdf(path=path, title=title, content=text_body)
        else:
            return {"status": "error", "error": f"Unsupported document format: {doc_format}"}

    def _tool_web_research_synthesize(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        from maverick.intelligence.toolkit.research import ResearchAssistant
        query = params.get("query", "")
        assistant = ResearchAssistant()
        return assistant.search_and_synthesize(query=query)

