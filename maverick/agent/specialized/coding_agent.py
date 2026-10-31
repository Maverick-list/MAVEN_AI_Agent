"""Maverick DevOS - Specialized Coding & AST Navigation Agent."""

import logging
from typing import Any, Dict, Optional, Tuple

from maverick.agent.specialized.base import SpecializedAgent

logger = logging.getLogger("maverick.agent.specialized.coding")


class CodingAgent(SpecializedAgent):
    """Specialized agent performing safe static AST codebase inspection and symbol resolution."""

    def __init__(self):
        super().__init__(
            name="coding_agent",
            agent_type="coding",
            description="Explores codebases, extracts Python AST symbols, and performs regex search.",
            idle_timeout_sec=90.0,
        )

    def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.initialize()
        self.touch()

        if tool_name == "codebase_find_symbols":
            from maverick.intelligence.toolkit.codebase import codebase_find_symbols
            path = parameters.get("path", ".")
            symbol_name = parameters.get("symbol_name")
            res = codebase_find_symbols(path=path, symbol_name=symbol_name)
            return {"status": "success", "result": res}

        if tool_name == "codebase_grep":
            from maverick.intelligence.toolkit.codebase import codebase_grep
            path = parameters.get("path", ".")
            pattern = parameters.get("pattern", "")
            file_glob = parameters.get("file_glob", "*.py")
            max_matches = int(parameters.get("max_matches", 50))
            res = codebase_grep(path=path, pattern=pattern, file_glob=file_glob, max_matches=max_matches)
            return {"status": "success", "result": res}

        if tool_name in ("analyze_ast", "code_analysis"):
            import ast
            code = parameters.get("code")
            path = parameters.get("path")
            if path and not code:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        code = f.read()
                except Exception as e:
                    return {"status": "error", "message": str(e)}
            if code is not None:
                try:
                    tree = ast.parse(code)
                    symbols = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))]
                    return {"status": "success", "symbols": symbols, "node_count": len(list(ast.walk(tree)))}
                except SyntaxError as se:
                    return {"status": "syntax_error", "message": str(se)}

        return {"status": "error", "message": f"Unsupported tool '{tool_name}' for CodingAgent."}

    def verify(
        self,
        tool_name: str,
        result: Any,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        if not isinstance(result, dict) or result.get("status") != "success":
            return False, "Coding action failed or returned error structure."
        return True, None
