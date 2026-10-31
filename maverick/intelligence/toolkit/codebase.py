"""Maverick DevOS - Codebase Exploration & Python AST Navigation Tool.

Performs static analysis of Python codebases using the standard library `ast` module.
Extracts classes, methods, docstrings, function signatures, and locates symbol definitions
without executing untrusted code or requiring heavy third-party language servers.
"""

import ast
import fnmatch
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("maverick.intelligence.tools.codebase")


class SymbolVisitor(ast.NodeVisitor):
    """AST visitor collecting classes, functions, and method signatures."""

    def __init__(self, rel_path: str):
        self.rel_path = rel_path
        self.symbols: List[Dict[str, Any]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        doc = ast.get_docstring(node) or ""
        bases = [ast.unparse(b) for b in node.bases] if hasattr(ast, "unparse") else []
        self.symbols.append({
            "type": "class",
            "name": node.name,
            "line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "file": self.rel_path,
            "bases": bases,
            "docstring": doc.strip().split("\n")[0] if doc else None,
        })
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node, is_async=False)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_function(node, is_async=True)
        self.generic_visit(node)

    def _record_function(self, node: Any, is_async: bool) -> None:
        doc = ast.get_docstring(node) or ""
        args = [arg.arg for arg in node.args.args]
        self.symbols.append({
            "type": "async_function" if is_async else "function",
            "name": node.name,
            "line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "file": self.rel_path,
            "arguments": args,
            "docstring": doc.strip().split("\n")[0] if doc else None,
        })


def codebase_find_symbols(
    target_path: str,
    symbol_name: Optional[str] = None,
    max_results: int = 50,
) -> Dict[str, Any]:
    """
    Search Python files in target_path for class and function symbols.
    """
    canonical_root = os.path.realpath(os.path.expanduser(target_path))
    home = os.path.realpath(os.path.expanduser("~"))

    if not (canonical_root == home or canonical_root.startswith(home + "/") or canonical_root.startswith("/tmp/")):
        raise PermissionError(f"Access denied: Path '{target_path}' is outside user workspace.")

    if not os.path.exists(canonical_root):
        raise FileNotFoundError(f"Path not found: '{target_path}'")

    matched_symbols: List[Dict[str, Any]] = []

    files_to_scan = []
    if os.path.isfile(canonical_root) and canonical_root.endswith(".py"):
        files_to_scan.append(canonical_root)
    elif os.path.isdir(canonical_root):
        for root, dirs, files in os.walk(canonical_root):
            # Skip hidden folders and virtual environments
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", ".venv", "__pycache__", "build", "dist")]
            for f in files:
                if f.endswith(".py"):
                    files_to_scan.append(os.path.join(root, f))
                    if len(files_to_scan) >= 100:
                        break
            if len(files_to_scan) >= 100:
                break

    for fpath in files_to_scan:
        rel = os.path.relpath(fpath, canonical_root)
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                tree = ast.parse(f.read(), filename=rel)
            visitor = SymbolVisitor(rel)
            visitor.visit(tree)

            for sym in visitor.symbols:
                if not symbol_name or symbol_name.lower() in sym["name"].lower():
                    matched_symbols.append(sym)
                    if len(matched_symbols) >= max_results:
                        break
        except Exception:
            continue

        if len(matched_symbols) >= max_results:
            break

    return {
        "status": "success",
        "root": canonical_root,
        "scanned_files": len(files_to_scan),
        "symbol_count": len(matched_symbols),
        "symbols": matched_symbols,
    }


def codebase_grep(
    target_path: str,
    pattern: str,
    file_pattern: str = "*.py",
    max_matches: int = 50,
) -> Dict[str, Any]:
    """
    Regex grep search across files matching file_pattern in target_path.
    """
    canonical_root = os.path.realpath(os.path.expanduser(target_path))
    home = os.path.realpath(os.path.expanduser("~"))

    if not (canonical_root == home or canonical_root.startswith(home + "/") or canonical_root.startswith("/tmp/")):
        raise PermissionError(f"Access denied: Path '{target_path}' is outside user workspace.")

    if not os.path.exists(canonical_root):
        raise FileNotFoundError(f"Path not found: '{target_path}'")

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as re_err:
        return {"status": "error", "error": f"Invalid regex pattern: {re_err}"}

    matches: List[Dict[str, Any]] = []

    files_to_search = []
    if os.path.isfile(canonical_root):
        files_to_search.append(canonical_root)
    else:
        for root, dirs, files in os.walk(canonical_root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("venv", ".venv", "__pycache__", "build", "dist")]
            for f in files:
                if fnmatch.fnmatch(f, file_pattern):
                    files_to_search.append(os.path.join(root, f))
                    if len(files_to_search) >= 200:
                        break
            if len(files_to_search) >= 200:
                break

    for fpath in files_to_search:
        rel = os.path.relpath(fpath, canonical_root)
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    if regex.search(line):
                        matches.append({
                            "file": rel,
                            "line": lineno,
                            "content": line.strip()[:140],
                        })
                        if len(matches) >= max_matches:
                            break
        except Exception:
            continue

        if len(matches) >= max_matches:
            break

    return {
        "status": "success",
        "pattern": pattern,
        "matches_count": len(matches),
        "matches": matches,
    }
