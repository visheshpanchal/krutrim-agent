"""The `document-export` skill's helper script (`md_export.py`) — the Markdown
block reader and the PDF / DOCX writers. Loaded from its real on-disk location
so this also pins the script to where the skill mount expects it.
"""

from __future__ import annotations

import importlib.util
import sys
import zipfile

import pytest
from krutrim_agent_management.config import settings

_SKILL_DIR = settings.common_skills_dir / "document-export"


def _load_md_export():
    path = _SKILL_DIR / "md_export.py"
    assert path.is_file(), f"missing helper script: {path}"
    spec = importlib.util.spec_from_file_location("md_export_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass resolves __module__ via sys.modules
    spec.loader.exec_module(module)
    return module


md_export = _load_md_export()

_SAMPLE = """# Tata Motors Quarterly Sales

## Summary

Tata Motors reported **strong** growth, led by [EV demand](https://example.com).

## Findings

- Domestic sales up 12% YoY
- EV penetration reached 9%

```
revenue = 1200
```
"""


def test_skill_frontmatter_loads_and_names_match_the_directory():
    from deepagents.middleware.skills import _parse_skill_metadata

    content = (_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    meta = _parse_skill_metadata(
        content, str(_SKILL_DIR / "SKILL.md"), "document-export"
    )
    assert meta is not None
    assert meta["name"] == "document-export"
    assert meta["description"]


def test_parse_blocks_reads_headings_bullets_and_code():
    blocks = md_export.parse_blocks(_SAMPLE)
    kinds = [b.kind for b in blocks]

    assert kinds.count("h") == 3
    assert kinds.count("li") == 2
    assert "code" in kinds
    # inline markers flattened; link becomes "text (url)"
    summary = next(b for b in blocks if b.kind == "p" and "growth" in b.text)
    assert "**" not in summary.text
    assert "EV demand (https://example.com)" in summary.text
    heading = next(b for b in blocks if b.kind == "h" and b.text.startswith("Tata"))
    assert heading.level == 1


def test_write_docx_produces_a_readable_document(tmp_path):
    out = tmp_path / "report.docx"
    md_export.write_docx(md_export.parse_blocks(_SAMPLE), out)

    assert out.stat().st_size > 0
    with zipfile.ZipFile(out) as zf:  # a .docx is a zip of XML parts
        body = zf.read("word/document.xml").decode("utf-8")
    assert "Tata Motors Quarterly Sales" in body
    assert "Domestic sales up 12% YoY" in body


def test_stdlib_pdf_is_structurally_valid_and_paginates(tmp_path):
    out = tmp_path / "big.pdf"
    big = "# Title\n\n" + "\n\n".join(
        f"Paragraph {i} with enough words to wrap across the page for pagination."
        for i in range(120)
    )
    md_export._write_pdf_stdlib(md_export.parse_blocks(big), out)

    data = out.read_bytes()
    assert data.startswith(b"%PDF-1.4")
    assert data.rstrip().endswith(b"%%EOF")

    xref_at = int(data[data.rfind(b"startxref") :].split(b"\n")[1])
    rows = data[xref_at:].split(b"\n")
    size = int(rows[1].split()[1])
    assert rows[2].split()[2] == b"f"  # the free entry
    offsets = [int(rows[3 + i].split()[0]) for i in range(size - 1)]
    assert all(b"obj" in data[off : off + 10] for off in offsets)
    # more than one /Page across the object table
    assert data.count(b"/Type /Page ") > 1


def test_latin1_downconverts_smart_punctuation():
    src = "Q1 FY27 — April–June ‘EV’ “demand”… up → 9%"
    out = md_export._latin1(src)
    assert out == "Q1 FY27 - April-June 'EV' \"demand\"... up -> 9%"
    assert out.encode("latin-1")  # no residual non-latin-1 char


def test_pdf_handles_a_unicode_report_without_crashing(tmp_path):
    """A real research report is full of em-dashes / curly quotes — fpdf2's
    core fonts are latin-1 and raise `FPDFUnicodeEncodingException` on them.
    `write_pdf` must down-convert first (and fall back to the stdlib writer if
    fpdf still chokes), never leave the caller with no file."""
    report = (
        "# Tata Motors — Q1 FY27\n\n"
        "Revenue rose — driven by ‘EV demand’ and JLR…\n\n"
        "- Domestic sales → up 12%\n"
        "- Margin ≥ 8%\n"
    )
    out = tmp_path / "report.pdf"
    md_export.write_pdf(md_export.parse_blocks(report), out)

    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert data.rstrip().endswith(b"%%EOF")
    assert out.stat().st_size > 400


def test_write_pdf_falls_back_to_stdlib_when_fpdf_raises(tmp_path, monkeypatch):
    boom = RuntimeError("fpdf blew up")
    monkeypatch.setattr(
        md_export, "_write_pdf_fpdf", lambda *_a, **_k: (_ for _ in ()).throw(boom)
    )
    out = tmp_path / "r.pdf"
    md_export.write_pdf(md_export.parse_blocks(_SAMPLE), out)
    assert out.read_bytes().startswith(b"%PDF-1.4")  # the stdlib writer's header


def test_write_pdf_prefers_fpdf_when_available(tmp_path):
    pytest.importorskip("fpdf")
    out = tmp_path / "report.pdf"
    md_export.write_pdf(md_export.parse_blocks(_SAMPLE), out)

    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert data.rstrip().endswith(b"%%EOF")
    assert out.stat().st_size > 400


def test_convert_refuses_to_overwrite_the_source(tmp_path):
    src = tmp_path / "report.md"
    src.write_text(_SAMPLE, encoding="utf-8")
    with pytest.raises(SystemExit):
        md_export.convert("pdf", src, src)


def test_convert_rejects_a_non_markdown_source(tmp_path):
    src = tmp_path / "data.pdf"
    src.write_bytes(b"%PDF-1.4 not markdown")
    with pytest.raises(SystemExit):
        md_export.convert("docx", src, tmp_path / "out.docx")
