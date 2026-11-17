# MAVEN AI Agent — Developer Guide & Architecture Extension

> **Target Audience:** Core contributors, system architects, and third-party extension developers.

---

## 1. Project Directory Structure

```text
Maverick-DevOS-evolution/
├── assets/                     # Application icons, desktop launchers, SVG branding
├── bin/                        # Shell wrappers and standalone executable entry points
├── dist/                       # Debian packaging definitions and build artifacts
├── docs/                       # Comprehensive technical and architectural documentation
│   └── screenshots/            # Verified visual evidence and application captures
├── maverick/                   # Primary Python module
│   ├── activity/               # Structured audit logging & action tracing
│   ├── agent/                  # Phase 2 Intelligent Agent Core & Cognitive Engine
│   │   ├── intent.py           # Bilingual Intent Understanding & Parameter Extraction
│   │   ├── orchestrator.py     # MavenAgentCore Central 11-Phase Lifecycle
│   │   ├── security.py         # 5-Tier Action Risk Policy & Provenance Tracking
│   │   └── specialized/        # Specialized Agents (Coding, ComputerUse, Monitoring, etc.)
│   ├── browser/                # Headless Chrome DevTools Protocol (CDP) automation
│   ├── computer_use/           # Universal Linux AT-SPI2 Accessibility automation
│   ├── context/                # Multi-modal context aggregation engine
│   ├── dashboard/              # FastAPI HUD backend, static assets, and WebSocket handler
│   ├── desktop/                # Native GTK3 + WebKit2GTK standalone application shell
│   ├── intelligence/           # DAG TaskPlanner, ContextMemory, and ToolRegistry
│   ├── media/                  # Spotify & MPRIS2 media controller
│   ├── system/                 # Linux hardware telemetry, battery, and process monitors
│   ├── vision/                 # MediaPipe hand tracking, gesture kinematics, virtual mouse
│   └── voice/                  # Whisper STT, clap detector, wake word, TTS, voice FSM
├── scripts/                    # Acceptance testing, benchmarking, and trial scripts
├── systemd/                    # Systemd user service definitions
└── tests/                      # Comprehensive Python unittest suite
```

---

## 2. Registering a New Tool in `ToolRegistry`

All actions executable by `MavenAgentCore` and the `TaskPlanner` must be declared in [`maverick/intelligence/tools.py`](../maverick/intelligence/tools.py):

```python
from maverick.intelligence.tools import ToolRisk

def my_custom_tool(param1: str, count: int = 1) -> Dict[str, Any]:
    """Execute custom developer logic."""
    return {"status": "success", "processed": param1, "count": count}

# Register tool within ToolRegistry._register_core_tools():
self.register(
    name="my_custom_tool",
    func=my_custom_tool,
    risk_level=ToolRisk.READ_ONLY, # or ToolRisk.MODERATE_RISK, ToolRisk.HIGH_RISK
    description="Explain what this tool does clearly so the planner understands it.",
    schema={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "Input description"},
            "count": {"type": "integer", "default": 1}
        },
        "required": ["param1"]
    }
)
```

---

## 3. Creating a Specialized Subagent

To add a new autonomous agent to `AgentRegistry`:
1. Subclass `SpecializedAgent` in `maverick/agent/specialized/base.py`:
```python
from maverick.agent.specialized.base import SpecializedAgent

class DatabaseAgent(SpecializedAgent):
    def __init__(self, tool_registry):
        super().__init__(name="database_agent", tool_registry=tool_registry)

    def execute(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        # Implement domain-specific execution
        return self.tool_registry.execute(tool_name, parameters)

    def verify(self, tool_name: str, result: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        # Post-action verification invariant
        if result.get("status") == "success":
            return True, None
        return False, "Database query returned error"
```
2. Register the agent inside `AgentRegistry._init_default_agents()`.

---

## 4. Running the Test Suite & Quality Verification

```bash
# Run the entire unittest suite
python3 -m unittest discover -s tests -p "test_*.py"

# Run a specific subsystem test file
python3 -m unittest tests/test_intelligent_agent_core.py
```
