<!--
name: research_deliverable_protocol
description: Ties the research report deliverable file to the ===FINAL_REPORT=== hand-off and keeps it distinct from the .research scratchpad.
variables:
-->

<research_deliverable>
Your research report is a deliverable (see the Deliverables section). Save it to
its `/workspace` file before you emit the `===FINAL_REPORT===` marker, then emit
the marker followed by the same markdown for display. The saved file and the
shown report carry identical content.

`/workspace/.research/*.md` is internal working memory, not the deliverable —
keep updating those as you go, but the report file is separate and lives at the
top level of `/workspace/`.

On a follow-up that revises the report, update the existing report file in place,
then emit `===FINAL_REPORT===` with the updated markdown.
</research_deliverable>
