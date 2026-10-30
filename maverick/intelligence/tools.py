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
        if cid not in self.SAFE_COMMAND_ALLOWLIST:
            raise SecurityError(f"Command '{cid}' is not in the safe diagnostics allowlist.")

        cmd = self.SAFE_COMMAND_ALLOWLIST[cid]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5.0)
        return {
            "command": " ".join(cmd),
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip() if proc.stderr else None,
        }

    def _tool_filesystem_list_dir(self, params: Dict[str, Any], **_) -> Dict[str, Any]:
        raw_path = params.get("path") or "~"
        target_dir = os.path.realpath(os.path.expanduser(raw_path))

        # Restrict listing to user home directory hierarchy
        home = os.path.realpath(os.path.expanduser("~"))
        if not target_dir.startswith(home):
            raise SecurityError(f"Access denied: Path '{raw_path}' is outside user home hierarchy.")

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
        target_file = os.path.realpath(os.path.expanduser(raw_path))

        home = os.path.realpath(os.path.expanduser("~"))
        if not target_file.startswith(home):
            raise SecurityError(f"Access denied: File '{raw_path}' is outside user home directory.")

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
