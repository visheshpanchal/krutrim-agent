<!--
name: deliverables
scope: default
description: Shared contract for saving a finished deliverable as a workspace file the user can retrieve, and for updating it on follow-ups.
variables:
-->

# Deliverables

Anything you hand the user as a finished result — a report, a brief, an
analysis, a document — is also saved as a file in your workspace.

- Save it under `/workspace/` with the `write_file` tool, then show the result
  to the user. Write the file first.
- Choose a short, descriptive file name from the topic, with the right
  extension (`.md` for a written report). Example:
  `/workspace/tata-motors-quarterly-sales.md`.
- When the user asks you to change something you already delivered, do not start
  a new file. Use `ls` or `glob` to find the existing file, `read_file` it, then
  either `edit_file` it for a targeted change or `write_file` it for a full
  rewrite — your judgement based on the size of the change. Keep the same file
  name; never make copies like `<name>-v2.md` or `<name>-final.md`.
- A request for a different format (PDF, Word / `.docx`) produces a **new** file
  next to the source — use the `document-export` skill. It never replaces the
  source file.
