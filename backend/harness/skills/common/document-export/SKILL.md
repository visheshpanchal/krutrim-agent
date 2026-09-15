---
name: document-export
description: Convert a finished Markdown deliverable in the workspace into a PDF or Word (.docx) file the user can download. Use whenever the user asks for the report / brief / analysis "as a PDF", "as a Word doc", "as a .docx", or a similar different-format request.
license: MIT
---

# Document Export

## When to Use

The user already has a delivered Markdown file (see the Deliverables section)
and asks for it in another format — "make a PDF of that", "send it as a Word
doc", "export the report as .docx". This skill produces a **new** file next to
the Markdown source. It never edits or replaces the source.

Not for: writing the report itself, or exporting something that was never saved
as a workspace file first.

## How to Use

There is no bundled converter — you write a small, disposable Python script
each time, using the library named below for the requested format, and run it
with `execute`. This keeps the conversion current with whatever's actually
installed (or installable) in the run environment, instead of depending on one
fixed script.

1. **Find the source.** `ls` / `glob` the workspace for the delivered Markdown
   file (e.g. `tata-motors-quarterly-sales.md`). If there is more than one and
   it is ambiguous, ask the user which one.
2. **Check the library is already available** before writing anything —
   `execute` a one-line import check:
   - PDF: `python3 -c "import fpdf"`
   - DOCX: `python3 -c "import docx"`
   Exit code `0` means it's already there; skip to step 4.
3. **Install it if missing** — `execute`:
   - PDF: `pip install fpdf2`
   - DOCX: `pip install python-docx`
   If the install itself fails (no network reachable from this environment, or
   the shell policy refuses `pip`), don't retry blindly:
   - PDF: fall back to a dependency-free writer using only the standard
     library (see "Stdlib PDF fallback" below). A plain PDF beats no PDF.
   - DOCX: there is no reasonable stdlib fallback — a `.docx` is a zip of XML
     parts, not something worth hand-rolling. Tell the user DOCX export isn't
     available in this environment right now and offer a PDF or the Markdown
     file instead.
4. **Write the conversion script** to `/workspace/<tmp-name>.py` (any name not
   already in use — `_export.py` is fine). At minimum it must:
   - Parse the Markdown into blocks: headings (`#` … `######`), paragraphs,
     bullet list items (`-`/`*`/`+`), and fenced code blocks (\`\`\`). Flatten
     inline `**bold**` / `*italic*` / `` `code` `` markers and `[text](url)`
     links down to plain text (a link becomes `text (url)`) — none of the
     output formats need real inline markup.
   - **PDF via `fpdf2`**: one `FPDF(format="A4", unit="pt")`, headings
     bold/larger by level, code in a monospace font, bullets prefixed with a
     marker. `fpdf2`'s core fonts (Helvetica/Courier) are **latin-1 only** — a
     real report full of em-dashes, curly quotes, ellipses and arrows will
     raise `FPDFUnicodeEncodingException` and write nothing at all. Down-convert
     smart punctuation to its ASCII equivalent first (`—`/`–` → `-`, `''`` → `'`,
     `""` → `"`, `…` → `...`, `→` → `->`), then drop anything still outside
     latin-1 — *before* handing text to `fpdf2`.
   - **DOCX via `python-docx`**: `Document()`, `doc.add_heading(text,
     level=...)`, `doc.add_paragraph(text)` (style `"List Bullet"` for list
     items), a monospace run for code. `python-docx` is UTF-8 native, so none
     of the latin-1 down-conversion above applies here.
   - Take `<source> <dest>` as CLI args (or hard-code the two paths already
     resolved in step 1) and refuse to run if `dest == source`.
5. **Run it** with `execute`, using paths relative to the workspace (its cwd).
6. **Verify.** `ls` the workspace and confirm the output file exists and is
   non-empty. If `execute` returned a non-zero exit code, read the output, fix
   the cause, and retry — do not report success.
7. **Clean up.** `delete` the script — it is not a deliverable.
8. **Tell the user** the new file name. The Markdown source is unchanged; both
   files are now in the workspace.

### Stdlib PDF fallback (no `fpdf2`, no network)

A minimal valid PDF needs only: a `%PDF-1.4` header, one `/Font` object
(`Helvetica`), one `/Page` object per page whose `stream` holds `BT ... Tj
... ET` text-showing operators, a `/Pages` tree, a `/Catalog`, and an `xref`
table of byte offsets plus a `trailer`. Wrap long lines yourself (~90 chars)
and paginate by counting lines against the page height — there is no
auto-flow without a library. Escape `\`, `(`, `)` inside every `Tj` string.
This is more code than the library path, but needs nothing beyond `pathlib`.

## Rules

- The source `.md` is read-only for this task. If the user wants the content
  changed *and* a PDF, revise the Markdown first (per the Deliverables
  contract), then export.
- One output file per request. Do not leave `<name>-v2.pdf` copies around — if
  re-exporting after a revision, overwrite the previous export of the same
  name.
- Only Markdown (`.md` / `.markdown` / `.txt`) sources are supported. Complex
  tables or embedded images may render plainly.
- Use `fpdf2` for PDF, never `PyPDF2`/`pypdf` — those manipulate *existing*
  PDFs (merge, split, extract text, watermark); they cannot lay out a new
  document from Markdown text.
- If an install fails, fall back or tell the user — don't loop retrying the
  same `pip install`, and don't leave a half-written output file behind.
