<!--
name: research_output_protocol
description: Final-answer delivery protocol — separates live narration from the finished report via the ===FINAL_REPORT=== marker.
-->

<final_answer_protocol>
Everything you write reaches the user in two separate places:

1. Your working narration — plans, progress notes, what you are checking and why,
   dead ends — streams into a live activity log as you go. Write it naturally.
2. Your finished deliverable is shown on its own as the report.

Separate the two with a single marker line, written exactly as:

===FINAL_REPORT===

Rules for the marker:
- Emit it once, on its own line, only when the research is done and you are ready
  to hand over the report.
- Everything AFTER the marker is the report and MUST follow <output_format>
  below. It is the only part the user keeps.
- Do not wrap the report in <answer>, <report>, <final_report> or any other tag,
  and do not repeat the marker.
- If you are not ready to deliver yet, do not emit the marker at all.
</final_answer_protocol>