# 09 — DOCUMENT STUDIO GENERATION & INTEGRITY VERIFICATION

## 1. Native Generation Engines

`DocumentStudio` provides clean document compilation using only standard Python libraries (`zipfile`, `xml.etree`, binary stream buffers), requiring zero heavy office runtimes:
- **PDF Generation (`generate_pdf`):**
  - Synthesizes standards-compliant PDF 1.4 binary documents with proper catalog dictionary, cross-reference table (`xref`), pages tree, font descriptors (`Helvetica`, `Helvetica-Bold`), and content streams.
- **DOCX Generation (`generate_docx`):**
  - Generates valid OpenXML `.docx` ZIP archives containing `[Content_Types].xml`, `_rels/.rels`, and `word/document.xml` with styled headings, paragraphs, bullet lists, and tables.
- **Markdown Generation (`generate_markdown`):**
  - Generates clean GitHub Flavored Markdown (`.md`) with frontmatter metadata.

---

## 2. On-Disk Verification Function (`verify_generated_document`)

To guarantee against corrupt files or silent truncation:
1. **PDF Verification:**
   - Validates `%PDF-1.` magic byte header at offset 0.
   - Validates `%%EOF` marker in the final 48 bytes.
   - Confirms non-zero byte size.
2. **DOCX Verification:**
   - Validates that the file is an openable ZIP archive.
   - Verifies existence of `word/document.xml`.
   - Parses XML to ensure valid schema and non-zero text (`w:t`) nodes.
3. **Execution Guard:**
   Both `generate_pdf` and `generate_docx` automatically invoke `verify_generated_document(target_path)` before returning. If verification fails, an exception is raised immediately.
4. **Workspace Boundary:**
   Files can only be created inside the user's home directory or `/tmp`, strictly barring sensitive paths (`~/.ssh`, `~/.config`, `~/.gnupg`).
