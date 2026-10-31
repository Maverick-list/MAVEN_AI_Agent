"""Maverick DevOS - Specialized Document Generation Agent."""

import logging
import os
from typing import Any, Dict, Optional, Tuple

from maverick.agent.specialized.base import SpecializedAgent

logger = logging.getLogger("maverick.agent.specialized.document")


class DocumentAgent(SpecializedAgent):
    """Specialized agent generating structured Markdown, DOCX, and PDF documents."""

    def __init__(self):
        super().__init__(
            name="document_agent",
            agent_type="document",
            description="Generates publication-quality Markdown (.md), Word (.docx), and PDF (.pdf) documents.",
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

        from maverick.intelligence.toolkit.documents import generate_markdown, generate_docx, generate_pdf

        doc_type = str(parameters.get("format") or parameters.get("type", "markdown")).lower()
        title = str(parameters.get("title", "Generated Report"))
        content = parameters.get("content", "")
        out_path = parameters.get("output_path")

        if "pdf" in doc_type:
            path = out_path or f"~/Desktop/{title.replace(' ', '_')}.pdf"
            path = os.path.realpath(os.path.expanduser(path))
            generate_pdf(title=title, content=content, output_path=path)
            return {"status": "success", "format": "pdf", "path": path}

        elif "docx" in doc_type:
            path = out_path or f"~/Desktop/{title.replace(' ', '_')}.docx"
            path = os.path.realpath(os.path.expanduser(path))
            generate_docx(title=title, content=content, output_path=path)
            return {"status": "success", "format": "docx", "path": path}

        else:
            path = out_path or f"~/Desktop/{title.replace(' ', '_')}.md"
            path = os.path.realpath(os.path.expanduser(path))
            generate_markdown(title=title, content=content, output_path=path)
            return {"status": "success", "format": "markdown", "path": path}

    def verify(
        self,
        tool_name: str,
        result: Any,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        if not isinstance(result, dict) or result.get("status") != "success":
            return False, "Document generation action did not return success status."
        path = result.get("path")
        if not path or not os.path.isfile(path) or os.path.getsize(path) == 0:
            return False, f"Document verification failed: output file '{path}' is missing or empty."
        return True, None
