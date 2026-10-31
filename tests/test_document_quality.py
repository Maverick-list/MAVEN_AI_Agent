"""
Tests for Document Generation Quality, Multipage PDF Output, DOCX Tables/Lists, and Parenthesis Escaping.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from maverick.intelligence.toolkit.documents import generate_docx, generate_markdown, generate_pdf


class TestDocumentQuality(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="maven_doc_quality_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_short_document_pdf_and_markdown(self):
        """Test 1: Generate a short document in PDF and Markdown."""
        pdf_path = os.path.join(self.temp_dir, "short.pdf")
        md_path = os.path.join(self.temp_dir, "short.md")

        res_pdf = generate_pdf(pdf_path, "Short Report", "This is a brief status summary.")
        self.assertEqual(res_pdf["status"], "success")
        self.assertEqual(res_pdf["pages_count"], 1)

        res_md = generate_markdown(md_path, "Short Report", [{"heading": "Status", "content": "Brief summary."}])
        self.assertEqual(res_md["status"], "success")
        self.assertTrue(os.path.isfile(md_path))

    def test_long_multipage_pdf_generation(self):
        """
        Test 2: Generate a long multipage document (>100 lines)
        Verifies that content is NOT truncated at 50 lines and creates multiple pages.
        """
        pdf_path = os.path.join(self.temp_dir, "long_report.pdf")
        long_sections = []
        for i in range(1, 20):
            long_sections.append(f"## Section {i}\n" + f"This is comprehensive evaluation paragraph #{i}. " * 6)

        full_content = "\n\n".join(long_sections)
        res = generate_pdf(pdf_path, "Master Engineering Specification", full_content)

        self.assertEqual(res["status"], "success")
        # Must be multi-page (at least 2 pages)
        self.assertGreater(res["pages_count"], 1)

        # Extract text via pdftotext
        extracted = subprocess.run(["pdftotext", pdf_path, "-"], capture_output=True, text=True).stdout
        # Verify Section 19 survived (no 50-line truncation!)
        self.assertIn("Section 19", extracted)
        self.assertIn("Page 1 of", extracted)

    def test_indonesian_language_document(self):
        """Test 3: Indonesian document generation in DOCX and PDF."""
        docx_path = os.path.join(self.temp_dir, "laporan_id.docx")
        pdf_path = os.path.join(self.temp_dir, "laporan_id.pdf")

        title = "Laporan Perkembangan Sistem MAVEN JARVIS"
        sections = [
            {
                "heading": "Ringkasan Eksekutif",
                "content": "Sistem operasi kecerdasan buatan telah berhasil diverifikasi dan diuji secara menyeluruh.",
            },
            {
                "heading": "Kinerja dan Keandalan",
                "content": "Tidak ditemukan kegagalan memori atau kebocoran proses pada pengujian harian.",
            },
        ]

        res_docx = generate_docx(docx_path, title, sections)
        self.assertEqual(res_docx["status"], "success")

        res_pdf = generate_pdf(pdf_path, title, sections)
        self.assertEqual(res_pdf["status"], "success")

        extracted_pdf = subprocess.run(["pdftotext", pdf_path, "-"], capture_output=True, text=True).stdout
        self.assertIn("Ringkasan Eksekutif", extracted_pdf)
        self.assertIn("menyeluruh", extracted_pdf)

    def test_parentheses_and_special_characters_preserved(self):
        """
        Test 5: Verify parentheses are escaped correctly in PDF and NOT converted to square brackets [].
        """
        pdf_path = os.path.join(self.temp_dir, "parentheses.pdf")
        title = "Evaluation Report (Version 2.5) - [Production Ready]"
        content = "Step 1 (Inspection): Verify all inputs (mouse & keyboard). Cost: $0 (free)."

        res = generate_pdf(pdf_path, title, content)
        self.assertEqual(res["status"], "success")

        extracted = subprocess.run(["pdftotext", pdf_path, "-"], capture_output=True, text=True).stdout
        # Parentheses must be preserved!
        self.assertIn("(Version 2.5)", extracted)
        self.assertIn("(Inspection)", extracted)
        self.assertIn("(mouse & keyboard)", extracted)
        self.assertNotIn("[Version 2.5]", extracted)

    def test_document_with_tables(self):
        """Test 6: Generate document with tabular data in DOCX and Markdown."""
        docx_path = os.path.join(self.temp_dir, "table_report.docx")
        md_path = os.path.join(self.temp_dir, "table_report.md")

        table_data = [
            ["Subsystem", "Metric", "Status"],
            ["Task Planner", "DAG Topological Order", "PASSED"],
            ["Filesystem", "Overwrite Protection", "PASSED"],
            ["Voice Barge-In", "Speech Retention", "PASSED"],
        ]

        sections = [
            {
                "heading": "Verification Matrix",
                "table": table_data,
                "bullet_list": ["High fidelity test", "100% assertions verified"],
            }
        ]

        res_docx = generate_docx(docx_path, "Verification Matrix", sections)
        self.assertEqual(res_docx["status"], "success")

        # Verify OOXML table structure in docx zip
        with zipfile.ZipFile(docx_path, "r") as zf:
            doc_xml = zf.read("word/document.xml").decode("utf-8")
            self.assertIn("<w:tbl>", doc_xml)
            self.assertIn("DAG Topological Order", doc_xml)
            self.assertIn("•  High fidelity test", doc_xml)

        res_md = generate_markdown(md_path, "Verification Matrix", sections)
        self.assertEqual(res_md["status"], "success")
        with open(md_path, "r", encoding="utf-8") as f:
            md_text = f.read()
            self.assertIn("| Subsystem | Metric | Status |", md_text)

    def test_long_paragraph_wrapping(self):
        """Test 7: Verify long uninterrupted paragraphs wrap lines cleanly without overflowing."""
        pdf_path = os.path.join(self.temp_dir, "wrapped.pdf")
        long_para = "The quick brown fox jumps over the lazy dog. " * 15

        res = generate_pdf(pdf_path, "Line Wrapping Test", long_para)
        self.assertEqual(res["status"], "success")

        extracted = subprocess.run(["pdftotext", pdf_path, "-"], capture_output=True, text=True).stdout
        self.assertIn("The quick brown fox", extracted)


if __name__ == "__main__":
    unittest.main()

