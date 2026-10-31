"""Unit tests for Maven JARVIS Multi-Functional Tool Expansion."""

import os
import shutil
import tempfile
import unittest
import zipfile

from maverick.intelligence.tools import ToolRegistry, ToolRisk


class TestMultifunctionalTools(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.temp_dir = tempfile.mkdtemp(prefix="maven_tools_test_")
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_registered_expanded_tools(self):
        """Verify the 4 new multifunctional tools are registered."""
        tool_names = [t.name for t in self.registry._tools.values()]
        self.assertIn("codebase_find_symbols", tool_names)
        self.assertIn("codebase_grep", tool_names)
        self.assertIn("document_generate", tool_names)
        self.assertIn("web_research_synthesize", tool_names)

    def test_codebase_find_symbols_ast(self):
        """Verify AST parsing finds classes and functions."""
        sample_code = (
            "class Engine:\n"
            "    '''Engine class docstring'''\n"
            "    def start(self, mode: str):\n"
            "        pass\n\n"
            "def run_diagnostics(verbose: bool = True):\n"
            "    pass\n"
        )
        test_py = os.path.join(self.temp_dir, "sample.py")
        with open(test_py, "w") as f:
            f.write(sample_code)

        res = self.registry.execute("codebase_find_symbols", {"path": self.temp_dir})
        self.assertEqual(res["status"], "success")
        symbols = res["result"]["symbols"]
        names = [s["name"] for s in symbols]
        self.assertIn("Engine", names)
        self.assertIn("start", names)
        self.assertIn("run_diagnostics", names)

    def test_codebase_grep_pattern(self):
        """Verify regex search across files."""
        test_py = os.path.join(self.temp_dir, "module.py")
        with open(test_py, "w") as f:
            f.write("TARGET_CONSTANT = 42\nIGNORED_VAR = 10\n")

        res = self.registry.execute("codebase_grep", {"path": self.temp_dir, "pattern": "TARGET_CONSTANT"})
        self.assertEqual(res["status"], "success")
        matches = res["result"]["matches"]
        self.assertEqual(len(matches), 1)
        self.assertIn("TARGET_CONSTANT", matches[0]["content"])

    def test_document_generate_markdown(self):
        """Verify markdown document generation."""
        target_md = os.path.join(self.temp_dir, "report.md")
        sections = [
            {"heading": "Executive Summary", "content": "Maven operational audit passed."},
            {"heading": "Metrics", "content": "CPU: 1.2%, RAM: 511MB."},
        ]
        res = self.registry.execute(
            "document_generate",
            {"format": "markdown", "path": target_md, "title": "System Report", "sections": sections},
        )
        self.assertEqual(res["status"], "success")
        self.assertTrue(os.path.isfile(target_md))
        with open(target_md) as f:
            text = f.read()
        self.assertIn("# System Report", text)
        self.assertIn("## Executive Summary", text)

    def test_document_generate_docx(self):
        """Verify Microsoft Word .docx generation and zip integrity."""
        target_docx = os.path.join(self.temp_dir, "report.docx")
        sections = [{"heading": "Introduction", "content": "Autonomous assistant architecture."}]
        res = self.registry.execute(
            "document_generate",
            {"format": "docx", "path": target_docx, "title": "Architecture Doc", "sections": sections},
        )
        self.assertEqual(res["status"], "success")
        self.assertTrue(os.path.isfile(target_docx))

        # Verify zip structure of valid docx
        with zipfile.ZipFile(target_docx) as z:
            names = z.namelist()
            self.assertIn("[Content_Types].xml", names)
            self.assertIn("_rels/.rels", names)
            self.assertIn("word/document.xml", names)

    def test_document_generate_pdf(self):
        """Verify PDF 1.4 generation and header structure."""
        target_pdf = os.path.join(self.temp_dir, "summary.pdf")
        res = self.registry.execute(
            "document_generate",
            {"format": "pdf", "path": target_pdf, "title": "PDF Report", "content": "Line 1: Operational\nLine 2: Ready"},
        )
        self.assertEqual(res["status"], "success")
        self.assertTrue(os.path.isfile(target_pdf))
        with open(target_pdf, "rb") as f:
            header = f.read(8)
        self.assertEqual(header, b"%PDF-1.4")

    def test_web_research_synthesize(self):
        """Verify web research topic decomposition and executive synthesis."""
        res = self.registry.execute(
            "web_research_synthesize",
            {"query": "Ubuntu Wayland screen capture performance"},
        )
        self.assertEqual(res["status"], "success")
        result = res["result"]
        self.assertIn("subtopics", result)
        self.assertIn("executive_summary", result)
        self.assertGreater(len(result["subtopics"]), 0)


if __name__ == "__main__":
    unittest.main()
