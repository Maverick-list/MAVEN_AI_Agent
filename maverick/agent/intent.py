"""Maverick DevOS - Intent Understanding & Classification Engine."""

from dataclasses import asdict, dataclass, field
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("maverick.agent.intent")


class IntentCategory(str, Enum):
    """Categorization for incoming user commands."""
    CONVERSATIONAL = "conversational"          # Natural dialogue, smalltalk, greetings, queries
    TASK_EXECUTION = "task_execution"          # Multi-step workflows, projects, environments
    WORKFLOW_TASK = "task_execution"           # Alias for workflow tasks
    DESKTOP_INTERACTION = "desktop_interaction" # UI manipulation: click, type, focus, switch
    RESEARCH = "research"                      # Web search, information synthesis, fact retrieval
    CODING = "coding"                          # Code navigation, symbol lookup, refactoring, AST
    DOCUMENT = "document"                      # Document generation: Markdown, PDF, DOCX
    SYSTEM_CONTROL = "system_control"          # Volume, mode changes, diagnostics, emergency stop
    UNKNOWN = "unknown"                        # Unrecognized or ambiguous intents


@dataclass
class UserIntent:
    """Structured representation of interpreted user intent and parameters."""
    raw_text: str
    category: IntentCategory
    action: str
    target: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.95
    is_ambiguous: bool = False
    clarification_needed: Optional[str] = None
    suggested_tools: List[str] = field(default_factory=list)
    suggested_agent: str = "orchestrator"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        return d


class IntentClassifier:
    """Interprets raw natural language text into actionable UserIntent with parameter extraction."""

    # 1. System Control & Diagnostic Patterns
    SYS_MODE_PATTERNS = [
        (re.compile(r"\b(?:ganti|ubah|set|switch)\s+(?:mode\s+ke\s+|mode\s+)?(normal|voice|vision|full_assistant|low_memory|safe_idle)\b", re.I), "set_mode"),
        (re.compile(r"\bmode\s+(normal|voice|vision|full assistant|low memory|safe idle)\b", re.I), "set_mode"),
    ]

    SYS_DIAG_PATTERNS = [
        (re.compile(r"\b(ram|memory|memori)\s*(?:usage|status|penggunaan)?\b", re.I), "system_ram"),
        (re.compile(r"\b(cpu|prosesor)\s*(?:usage|status|penggunaan)?\b", re.I), "system_cpu"),
        (re.compile(r"\b(disk|storage|penyimpanan)\s*(?:usage|status)?\b", re.I), "system_disk"),
        (re.compile(r"\b(battery|baterai|daya)\s*(?:status)?\b", re.I), "system_battery"),
        (re.compile(r"\b(status\s+sistem|system\s+status|diagnostics|telemetry)\b", re.I), "system_status"),
        (re.compile(r"\b(emergency\s+stop|stop\s+all|halt|darurat|hentikan\s+semua\s+proses)\b", re.I), "emergency_stop"),
    ]

    # 2. Research & Web Patterns
    RESEARCH_PATTERNS = [
        re.compile(r"\b(?:search|find\s+information|research|investigate|cari\s+informasi|riset|analyze\s+and\s+research)\s+(?:about|on|for)?\s*(.+)", re.I),
        re.compile(r"\bwhat\s+is\s+the\s+latest\s+(?:on|about)\s*(.+)", re.I),
    ]

    # 3. Coding & Codebase Patterns
    CODING_PATTERNS = [
        (re.compile(r"\b(?:find\s+symbols?|lookup\s+symbol|cari\s+simbol)\s+(?:in|for)?\s*([a-zA-Z0-9_\.]+)", re.I), "codebase_find_symbols"),
        (re.compile(r"\b(?:grep|search\s+code|cari\s+kode)\s+(?:for)?\s*[\"']?([^\"']+)[\"']?", re.I), "codebase_grep"),
        (re.compile(r"\b(?:create|build|buat)\s+(?:a\s+)?python\s+(?:project|app|application|proyek)\s*(?:named|bernama)?\s*([a-zA-Z0-9_]+)?", re.I), "create_python_project"),
        (re.compile(r"\b(?:analisis|analisa|analyze|review|check|syntax|ast|debug|optimize)\s+(?:syntax\s+|ast\s+|kode\s+|code\s+)?([a-zA-Z0-9_/\.\-]+)?", re.I), "code_analysis"),
    ]

    # 4. Document Generation Patterns
    DOCUMENT_PATTERNS = [
        (re.compile(r"\b(?:generate|create|buat|export|tulis)\s+(?:a\s+)?(?:dokumen|file|laporan|report|dokumentasi)?\s*(?:laporan|report|dokumentasi|arsitektur|format)?\s*(pdf|docx|markdown|laporan|report|dokumentasi)?\b", re.I), "generate_document"),
    ]

    # 5. Desktop Interaction Patterns
    DESKTOP_PATTERNS = [
        (re.compile(r"\b(?:launch|open|buka|start)\s+(?:aplikasi\s+)?(code|vs\s*code|spotify|chrome|google\s*chrome|gnome-terminal|terminal|calculator|kalkulator|firefox|browser)\b", re.I), "app_launch"),
        (re.compile(r"\b(?:close|tutup|kill)\s+(?:window\s+)?(code|spotify|chrome|terminal|calculator|firefox)\b", re.I), "app_close"),
        (re.compile(r"\b(?:click|tekan|klik)\s+(?:tombol\s+|on\s+)?(.+)", re.I), "ui_click"),
        (re.compile(r"\b(?:type|ketik|tulis)\s+[\"']?([^\"']+)[\"']?", re.I), "ui_type"),
    ]

    # 6. Task Workflow Patterns
    WORKFLOW_PATTERNS = [
        (re.compile(r"\b(?:prepare|siapkan|setup)\s+(?:(?:dev|development)\s+environment|environment\s+(?:dev|development))\s*(?:for|untuk)?\s*([a-zA-Z0-9_-]+)?", re.I), "prepare_dev_environment"),
        (re.compile(r"\b(?:jalankan|run)\s+(?:pipeline\s+)?(testing|build|test|deploy)\b", re.I), "run_pipeline"),
    ]

    def classify(self, raw_input: str, context: Optional[Dict[str, Any]] = None) -> UserIntent:
        """Classify input text into structured UserIntent."""
        text = (raw_input or "").strip()

        # A. Empty / Whitespace check
        if not text:
            return UserIntent(
                raw_text="",
                category=IntentCategory.UNKNOWN,
                action="empty_input",
                is_ambiguous=True,
                clarification_needed="Instruction cannot be empty. Please state what you would like to do.",
                confidence=0.0,
            )

        # Normalize wake word prefixes if present ("Maven, ...", "Jarvis, ...")
        cleaned = re.sub(r"^(?:maven|jarvis)[\s,:]*", "", text, flags=re.IGNORECASE).strip()
        lower = cleaned.lower() if cleaned else text.lower()

        # B. Emergency Stop Fast-Path
        if any(term in lower for term in ("emergency stop", "stop all", "halt", "berhenti darurat", "estop", "hentikan semua proses")):
            return UserIntent(
                raw_text=text,
                category=IntentCategory.SYSTEM_CONTROL,
                action="emergency_stop",
                confidence=1.0,
                suggested_tools=["emergency_stop_all"],
                suggested_agent="monitoring",
            )

        # C. System Mode Switches
        for pat, act in self.SYS_MODE_PATTERNS:
            m = pat.search(cleaned)
            if m:
                target_mode = m.group(2 if m.lastindex >= 2 else 1).replace(" ", "_").lower()
                return UserIntent(
                    raw_text=text,
                    category=IntentCategory.SYSTEM_CONTROL,
                    action=act,
                    target=target_mode,
                    parameters={"mode": target_mode},
                    confidence=0.98,
                    suggested_tools=["set_operating_mode"],
                    suggested_agent="monitoring",
                )

        # D. System Diagnostics
        for pat, act in self.SYS_DIAG_PATTERNS:
            if pat.search(cleaned):
                return UserIntent(
                    raw_text=text,
                    category=IntentCategory.SYSTEM_CONTROL,
                    action=act,
                    confidence=0.95,
                    suggested_tools=["system_telemetry"],
                    suggested_agent="monitoring",
                )

        # E. Workflow & Multi-Step Task Patterns
        for pat, act in self.WORKFLOW_PATTERNS:
            m = pat.search(cleaned)
            if m:
                target_proj = m.group(1).strip() if (m.lastindex and m.group(1)) else "default_workspace"
                return UserIntent(
                    raw_text=text,
                    category=IntentCategory.TASK_EXECUTION,
                    action=act,
                    target=target_proj,
                    parameters={"project": target_proj},
                    confidence=0.95,
                    suggested_tools=["filesystem_list_dir", "desktop_launch_app"],
                    suggested_agent="planning",
                )

        # F. Research Patterns
        for pat in self.RESEARCH_PATTERNS:
            m = pat.search(cleaned)
            if m:
                topic = m.group(1).strip()
                return UserIntent(
                    raw_text=text,
                    category=IntentCategory.RESEARCH,
                    action="web_research_synthesize",
                    target=topic,
                    parameters={"topic": topic},
                    confidence=0.92,
                    suggested_tools=["web_research_synthesize"],
                    suggested_agent="research",
                )

        # G. Document Generation Patterns
        for pat, act in self.DOCUMENT_PATTERNS:
            m = pat.search(cleaned)
            if m:
                doc_type = m.group(1).lower() if (m.lastindex and m.group(1)) else "markdown"
                fmt = "pdf" if "pdf" in doc_type else ("docx" if "docx" in doc_type else "markdown")
                return UserIntent(
                    raw_text=text,
                    category=IntentCategory.DOCUMENT,
                    action=act,
                    target=fmt,
                    parameters={"format": fmt, "title": "Generated Report"},
                    confidence=0.91,
                    suggested_tools=["document_generate"],
                    suggested_agent="document",
                )

        # H. Coding Patterns
        for pat, act in self.CODING_PATTERNS:
            m = pat.search(cleaned)
            if m:
                param_val = m.group(1).strip() if (m.lastindex and m.group(1)) else ""
                params = {"symbol_name": param_val} if act == "codebase_find_symbols" else {"pattern": param_val}
                return UserIntent(
                    raw_text=text,
                    category=IntentCategory.CODING,
                    action=act,
                    target=param_val,
                    parameters=params,
                    confidence=0.93,
                    suggested_tools=[act],
                    suggested_agent="coding",
                )

        # I. Desktop UI / Computer Use Patterns
        for pat, act in self.DESKTOP_PATTERNS:
            m = pat.search(cleaned)
            if m:
                target_val = m.group(1).strip() if m.lastindex else ""
                app_id = "code" if "code" in target_val.lower() else target_val.lower()
                return UserIntent(
                    raw_text=text,
                    category=IntentCategory.DESKTOP_INTERACTION,
                    action=act,
                    target=app_id,
                    parameters={"app_id": app_id, "target": target_val},
                    confidence=0.94,
                    suggested_tools=["desktop_launch_app" if act == "app_launch" else "computer_use_execute"],
                    suggested_agent="computer_use",
                )

        # J. Ambiguity detection for single-word, unclassifiable tokens
        words = cleaned.split()
        greeting_words = {"halo", "hai", "hello", "hi", "help", "bantuan", "thanks", "terimakasih", "terima"}
        if len(words) == 1 and lower not in greeting_words:
            return UserIntent(
                raw_text=text,
                category=IntentCategory.UNKNOWN,
                action="ambiguous_query",
                is_ambiguous=True,
                clarification_needed=f"Instruksi '{text}' kurang jelas. Apa yang ingin Anda lakukan?",
                confidence=0.3,
            )

        # K. Default Conversational Query
        return UserIntent(
            raw_text=text,
            category=IntentCategory.CONVERSATIONAL,
            action="general_conversation",
            confidence=0.80,
            suggested_agent="orchestrator",
        )
