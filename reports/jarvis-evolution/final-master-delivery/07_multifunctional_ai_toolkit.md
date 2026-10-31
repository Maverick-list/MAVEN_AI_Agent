# MAVEN JARVIS — MULTIFUNCTIONAL AI TOOLKIT REPORT
**Subsystem:** Diagnostic, Development & Research Assistant  
**Components:** Document Studio, Codebase AST Explorer, Safe Public Web Research  
**Tool Registry:** 29 Registered Tools with JSONSchema Validation  

---

## 1. Document Studio (`maverick/intelligence/toolkit/documents.py`)
Provides deterministic programmatic file authoring without relying on heavy external dependencies:

| Format | Output Engine | Features | Disk Verification Suite |
|---|---|---|---|
| **PDF** | Native 72 DPI PDF 1.4 Generator | Headers, page numbers, clean margins, multiline wraps | Magic `%PDF-1.4`, `%%EOF` marker, stream length |
| **DOCX** | Structured OpenXML Packager | WordprocessingML `w:document`, `w:p`, `w:r`, `w:t` | ZIP integrity, XML DOM node parsing |
| **Markdown** | GitHub-Flavored CommonMark | Tables, callouts, fenced code blocks, YAML metadata | UTF-8 validation, line-ending consistency |

---

## 2. Codebase AST Explorer (`maverick/intelligence/toolkit/codebase.py`)
Allows Maven to inspect, navigate, and reason about codebases without executing unvetted scripts:
- **`codebase_find_symbols`:** Parses Python abstract syntax trees (`ast.parse`) to extract classes, asynchronous/synchronous methods, docstrings, and line numbers.
- **`codebase_grep`:** Performant regex pattern matching constrained within the user's workspace, ignoring virtualenvs (`.venv`, `node_modules`).
- **Workspace Containment:** Rejects directory traversal (`../../`) and strictly denies scanning root-level sensitive paths (`.ssh`, `.gnupg`, `/etc`).

---

## 3. Web Research Pipeline (`maverick/intelligence/toolkit/research.py`)
- **Safe Public Retrieval:** Leverages Wikipedia OpenSearch and MediaWiki REST summaries to fetch authoritative, verified knowledge with real source URLs.
- **Strict SSRF Guard:** `is_safe_url()` blocks loopback (`127.0.0.1`, `localhost`), link-local (`169.254.0.0/16`), private subnets (`10.0.0.0/8`, `192.168.0.0/16`, `172.16.0.0/12`), and non-HTTP protocols (`file://`, `ftp://`).
- **Anti-Hallucination Policy:** If no search providers are reachable or available, the engine returns `status: unavailable` and explicitly informs the user rather than inventing plausible-sounding synthetic facts.
