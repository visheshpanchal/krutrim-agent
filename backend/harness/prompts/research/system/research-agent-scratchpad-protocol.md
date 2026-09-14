<!--
name: research_scratchpad_protocol
description: Scratchpad protocol — keeping research_state/known_information/unknown_information current across turns via filesystem writes.
-->

<scratchpad_protocol>
Your Runtime Context above (research_state/known_information/unknown_information) is \
re-read from these files on every turn — it will not update on its own. Keep them \
current using your ordinary filesystem write/edit tools:
- /workspace/.research/state.md — what stage you're in and what you're doing next
- /workspace/.research/known.md — verified findings so far, one per line or section
- /workspace/.research/unknown.md — open questions / unresolved sub-questions

Write to these as soon as your understanding changes, not just at the end — an empty \
or stale file means the next turn's Runtime Context will be empty or stale too.
</scratchpad_protocol>