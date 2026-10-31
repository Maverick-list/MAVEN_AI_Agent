# 07 — MULTIFUNCTIONAL AI TOOLKIT & DIAGNOSTICS

## 1. Subsystem Overview

The multifunctional AI toolkit provides Maven with concrete capabilities to inspect code, research topics, synthesize documents, and audit system resources without depending on external cloud tooling or brittle shell scripts.

| Capability | Module | Core Functionality | Safety Boundary |
|:---|:---|:---|:---|
| **Codebase Explorer** | `maverick/intelligence/toolkit/codebase.py` | AST class/function indexing, docstring extraction, regex grep | Read-only; restricted to workspace directories |
| **Web Research Assistant** | `maverick/intelligence/toolkit/research.py` | Multi-source query, semantic extraction, credibility scoring | SSRF IP filter; strict timeout and 2MB payload ceiling |
| **Document Studio** | `maverick/intelligence/toolkit/documents.py` | Native PDF 1.4, DOCX OpenXML, and Markdown authoring | On-disk byte integrity check; restricted directory whitelist |
| **System Diagnostics** | `maverick/system/monitor.py` | CPU/RAM/Battery, service health, sanitized process list | Active secret scrub (tokens, passwords, bearer keys) |

All 4 tool suites are registered as first-class tools in `ToolRegistry` (`maverick/intelligence/tools.py`) and exposed via both the voice pipeline and REST endpoints on the Holographic Control Center.
