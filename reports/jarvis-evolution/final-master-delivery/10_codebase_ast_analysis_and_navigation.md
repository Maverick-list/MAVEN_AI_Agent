# 10 — CODEBASE AST ANALYSIS & NAVIGATION

## 1. Static AST Parsing vs Code Execution

To protect developer systems, Maven parses and inspects Python repositories statically using the standard library `ast` module. At no point does it import or execute untrusted target scripts.

### Core Capabilities
1. **Symbol Extraction (`codebase_find_symbols`):**
   - Recurses through Python files within a given directory tree.
   - Extracts `ClassDef`, `FunctionDef`, and `AsyncFunctionDef` nodes.
   - Captures line numbers, end line numbers, argument lists, and docstrings.
   - Supports filtering by symbol name or substring.
2. **Regex Grep (`codebase_grep`):**
   - Performs line-by-line regex search matching specific patterns across codebase files.
   - Honors `.gitignore` exclusion rules (`node_modules`, `.git`, `__pycache__`, `.venv`).
   - Limits output to bounded chunks preventing memory exhaustion on massive codebases.

---

## 2. Security Boundaries & Path Verification

- Target path must reside within the user's workspace or `/tmp`.
- Traversals targeting `/proc`, `/sys`, `/etc`, or `/root` are blocked with `PermissionError`.
- Verified in `tests/test_multifunctional_tools.py`: 100% detection of classes, methods, and symbols without executing target files.
