---
status: pending
priority: medium
workflow: 
---

# Render VerMAS-specific fields and Claude conversation content in Obsidian notes

Update the obsidian formatter's format_session() to render VerMAS-specific fields when present: task description section, agent signals timeline, learnings/improvements bullets, quality assessment rating, and cycle info. Also improve Claude session rendering: extract user questions, tool usage with rationale, key decisions made, and accomplishments summary — replacing the '_Conversation not included._' placeholder. For each content type, add a quality check: timestamps must be formatted, durations calculated, agent interactions captured with detail. Write tests that assert generated note content contains expected sections and field values. This directly targets note_content_richness KPI toward 90%.
