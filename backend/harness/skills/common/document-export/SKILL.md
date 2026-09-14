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

The converter is a small script that ships with this skill. The sandbox shell
runs with the workspace as its working directory, so the steps are:

1. **Find the source.** `ls` / `glob` the workspace for the delivered Markdown
   file (e.g. `tata-motors-quarterly-sales.md`). If there is more than one and
   it is ambiguous, ask the user which one.
2. **Stage the converter.** `read_file` `/skills/common/document-export/md_export.py`,
   then `write_file` its exact contents to `/workspace/md_export.py`. (The
   shell cannot reach `/skills/...` directly — only the file tools can — so it
   needs a copy in the workspace.)
3. **Run it** with `execute`, using paths relative to the workspace:
   - PDF:  `python3 md_export.py pdf <name>.md <name>.pdf`
   - DOCX: `python3 md_export.py docx <name>.md <name>.docx`
   Pick the format the user asked for. Keep the base name identical to the
   source.
4. **Verify.** `ls` the workspace and confirm `<name>.pdf` (or `.docx`) is
   there and non-empty. If `execute` returned a non-zero exit code, read the
   output, fix the cause, and retry — do not report success.
5. **Clean up.** `delete` `/workspace/md_export.py` — it is not a deliverable.
6. **Tell the user** the new file name. The Markdown source is unchanged; both
   files are now in the workspace.

## Rules

- The source `.md` is read-only for this task. If the user wants the content
  changed *and* a PDF, revise the Markdown first (per the Deliverables
  contract), then export.
- One output file per request. Do not leave `<name>-v2.pdf` copies around — if
  re-exporting after a revision, overwrite the previous export of the same
  name.
- Only Markdown (`.md` / `.markdown` / `.txt`) sources are supported. The
  converter handles headings, paragraphs, bullet lists and code blocks; complex
  tables or embedded images may render plainly.
