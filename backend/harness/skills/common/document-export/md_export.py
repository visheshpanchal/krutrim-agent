"""Convert a Markdown workspace file to PDF or DOCX, writing a new file next to
the source. The source Markdown is never modified.

    python3 md_export.py pdf  /workspace/report.md  /workspace/report.pdf
    python3 md_export.py docx /workspace/report.md  /workspace/report.docx

DOCX uses `python-docx`. PDF uses `fpdf2` when it is importable and otherwise a
small built-in writer that needs nothing beyond the standard library, so the
command works in a bare environment and produces nicer output where the extra
converters are installed.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_PAGE_W, _PAGE_H = 595, 842  # A4 points
_MARGIN = 56
_LEADING = 14
_WRAP = 92  # characters per line for the stdlib PDF writer


@dataclass
class Block:
    kind: str  # "h" | "p" | "li" | "code"
    text: str
    level: int = 0  # heading level for "h"


def parse_blocks(markdown_text: str) -> list[Block]:
    """A deliberately small Markdown reader — headings, paragraphs, bullet
    items, fenced code. Inline emphasis / code markers are flattened to plain
    text and links become ``text (url)``; enough for a research report."""
    blocks: list[Block] = []
    para: list[str] = []
    in_code = False
    code: list[str] = []

    def flush_para() -> None:
        if para:
            blocks.append(Block("p", _inline(" ".join(para))))
            para.clear()

    for raw in markdown_text.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            if in_code:
                blocks.append(Block("code", "\n".join(code)))
                code.clear()
            else:
                flush_para()
            in_code = not in_code
            continue
        if in_code:
            code.append(raw)
            continue
        if not line.strip():
            flush_para()
            continue
        if line.lstrip().startswith("#"):
            flush_para()
            stripped = line.lstrip()
            level = len(stripped) - len(stripped.lstrip("#"))
            blocks.append(Block("h", _inline(stripped[level:].strip()), min(level, 6)))
            continue
        bullet = line.lstrip()
        if bullet[:2] in ("- ", "* ") or bullet[:2] == "+ ":
            flush_para()
            blocks.append(Block("li", _inline(bullet[2:].strip())))
            continue
        para.append(line.strip())

    if in_code and code:
        blocks.append(Block("code", "\n".join(code)))
    flush_para()
    return blocks


# The PDF writers (fpdf2 core fonts + the stdlib writer) only speak latin-1.
# A research report is full of em-dashes, curly quotes, ellipses and arrows;
# without this fpdf2 raises `FPDFUnicodeEncodingException` and no file is
# written. DOCX is untouched -- python-docx emits UTF-8 and handles all of this.
_LATIN1_MAP = {
    **dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212", "-"),
    **dict.fromkeys("\u2018\u2019\u201a\u201b\u2032", "'"),
    **dict.fromkeys("\u201c\u201d\u201e\u201f\u2033", '"'),
    **dict.fromkeys("\u2022\u2023\u2043\u25aa\u25cf\u25e6", "-"),
    **dict.fromkeys("\u00a0\u202f\u2009", " "),
    "\u2026": "...",
    "\u2192": "->",
    "\u2190": "<-",
    "\u2194": "<->",
    "\u21d2": "=>",
    "\u2260": "!=",
    "\u2264": "<=",
    "\u2265": ">=",
    "\u2122": "(TM)",
    "\u2030": "%o",
    "\u200b": "",
    "\ufeff": "",
}


def _latin1(text: str) -> str:
    """Down-convert to what the PDF core fonts can render: smart punctuation to
    its ASCII equivalent, then drop anything still outside latin-1."""
    for uni, repl in _LATIN1_MAP.items():
        if uni in text:
            text = text.replace(uni, repl)
    return text.encode("latin-1", "ignore").decode("latin-1")


def _inline(text: str) -> str:
    """Flatten inline Markdown to plain text."""
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "[":
            close = text.find("]", i)
            if close != -1 and text[close + 1 : close + 2] == "(":
                end = text.find(")", close)
                if end != -1:
                    label = text[i + 1 : close]
                    url = text[close + 2 : end]
                    out.append(f"{label} ({url})" if url and url != label else label)
                    i = end + 1
                    continue
        if ch in "*_`" and text[i : i + 2] not in ("**", "__"):
            i += 1
            continue
        if text[i : i + 2] in ("**", "__"):
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# ── DOCX (python-docx) ────────────────────────────────────────────────────


def write_docx(blocks: list[Block], out_path: Path) -> None:
    from docx import Document  # optional dependency, resolved at call time

    doc = Document()
    for block in blocks:
        if block.kind == "h":
            doc.add_heading(block.text, level=min(block.level, 9))
        elif block.kind == "li":
            doc.add_paragraph(block.text, style="List Bullet")
        elif block.kind == "code":
            para = doc.add_paragraph()
            run = para.add_run(block.text)
            run.font.name = "Courier New"
        else:
            doc.add_paragraph(block.text)
    doc.save(str(out_path))


# ── PDF ──────────────────────────────────────────────────────────────────


def write_pdf(blocks: list[Block], out_path: Path) -> None:
    blocks = [Block(b.kind, _latin1(b.text), b.level) for b in blocks]
    try:
        _write_pdf_fpdf(blocks, out_path)
    except ImportError:
        _write_pdf_stdlib(blocks, out_path)
    except Exception:  # noqa: BLE001 - fpdf present but choked; a plain PDF still beats none
        _write_pdf_stdlib(blocks, out_path)


def _write_pdf_fpdf(blocks: list[Block], out_path: Path) -> None:
    from fpdf import FPDF  # optional dependency, resolved at call time

    pdf = FPDF(format="A4", unit="pt")
    pdf.set_auto_page_break(auto=True, margin=_MARGIN)
    pdf.add_page()
    pdf.set_margins(_MARGIN, _MARGIN, _MARGIN)
    width = _PAGE_W - 2 * _MARGIN

    for block in blocks:
        if block.kind == "h":
            pdf.ln(8)
            pdf.set_font("Helvetica", "B", max(18 - 2 * (block.level - 1), 11))
            pdf.multi_cell(width, _LEADING + 4, block.text)
            pdf.ln(2)
        elif block.kind == "code":
            pdf.set_font("Courier", "", 9)
            for row in block.text.splitlines() or [""]:
                pdf.multi_cell(width, _LEADING - 2, row)
            pdf.ln(2)
        elif block.kind == "li":
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(width, _LEADING, f"·  {block.text}")  # latin-1 middle dot
        else:
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(width, _LEADING, block.text)
            pdf.ln(3)

    pdf.output(str(out_path))


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for hard in text.split("\n"):
        if not hard:
            lines.append("")
            continue
        current = ""
        for word in hard.split(" "):
            if current and len(current) + 1 + len(word) > width:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        lines.append(current)
    return lines


def _pdf_escape(text: str) -> str:
    ascii_text = text.encode("latin-1", "replace").decode("latin-1")
    return ascii_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_pdf_stdlib(blocks: list[Block], out_path: Path) -> None:
    """Minimal, dependency-free PDF: Helvetica text flowed across A4 pages."""
    lines: list[tuple[str, int]] = []  # (text, font_size)
    for block in blocks:
        if block.kind == "h":
            size = max(18 - 2 * (block.level - 1), 11)
            lines.append(("", 6))
            lines.extend((seg, size) for seg in _wrap(block.text, _WRAP))
            lines.append(("", 4))
        elif block.kind == "code":
            lines.extend((f"    {row}", 9) for row in block.text.splitlines() or [""])
            lines.append(("", 4))
        elif block.kind == "li":
            wrapped = _wrap(block.text, _WRAP - 3)
            for idx, seg in enumerate(wrapped):
                lines.append((f"·  {seg}" if idx == 0 else f"   {seg}", 11))
        else:
            lines.extend((seg, 11) for seg in _wrap(block.text, _WRAP))
            lines.append(("", 4))

    per_page = max(int((_PAGE_H - 2 * _MARGIN) / _LEADING), 1)
    pages = [lines[i : i + per_page] for i in range(0, len(lines), per_page)] or [[]]

    objects: list[bytes] = []

    def add(obj: bytes) -> int:
        objects.append(obj)
        return len(objects)

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    for page in pages:
        y = _PAGE_H - _MARGIN
        parts = ["BT", "/F1 11 Tf", f"{_MARGIN} {y} Td", f"{_LEADING} TL"]
        for text, size in page:
            parts.append(f"/F1 {size} Tf")
            parts.append(f"({_pdf_escape(text)}) Tj")
            parts.append("T*")
        parts.append("ET")
        stream = "\n".join(parts).encode("latin-1")
        content_id = add(
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
        )
        page_ids.append(
            add(
                b"<< /Type /Page /Parent 0 0 R /MediaBox [0 0 %d %d] "
                b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                % (_PAGE_W, _PAGE_H, font_id, content_id)
            )
        )

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    pages_id = add(
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")
    )
    for pid in page_ids:
        objects[pid - 1] = objects[pid - 1].replace(
            b"/Parent 0 0 R", b"/Parent %d 0 R" % pages_id
        )
    catalog_id = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("latin-1"))

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("latin-1") + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin-1")
    out_path.write_bytes(bytes(out))


# ── entry point ─────────────────────────────────────────────────────────


def convert(fmt: str, source: Path, dest: Path) -> None:
    if fmt not in ("pdf", "docx"):
        raise SystemExit(f"format must be 'pdf' or 'docx', got {fmt!r}")
    if source.suffix.lower() not in (".md", ".markdown", ".txt"):
        raise SystemExit(f"source must be a Markdown file, got {source.name!r}")
    if not source.is_file():
        raise SystemExit(f"no such file: {source}")
    if dest.resolve() == source.resolve():
        raise SystemExit("refusing to overwrite the source file")

    blocks = parse_blocks(source.read_text(encoding="utf-8"))
    if fmt == "docx":
        write_docx(blocks, dest)
    else:
        write_pdf(blocks, dest)
    print(f"wrote {dest}")


def main(argv: list[str]) -> None:
    if len(argv) != 3:
        raise SystemExit(
            "usage: python3 md_export.py <pdf|docx> <source.md> <dest.(pdf|docx)>"
        )
    convert(argv[0], Path(argv[1]), Path(argv[2]))


if __name__ == "__main__":
    main(sys.argv[1:])
