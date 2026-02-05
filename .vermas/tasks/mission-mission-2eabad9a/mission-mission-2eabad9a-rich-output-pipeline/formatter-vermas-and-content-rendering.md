---
status: done
priority: medium
workflow: null
---
# Update ObsidianFormatter to render rich content for both VerMAS and Claude sessions

In ObsidianFormatter.format_session(), add rendering for VerMAS-specific fields when present: task_description (replace 'Task: unknown'), agent signals, learnings, improvements, quality assessment, and cycle info. Also update Claude session rendering to extract and display conversation content: what the user asked, tool usage summaries with purpose, accomplishments, and key decisions made — not just turn counts. Remove the '_Conversation not included._' default for Claude sessions that have message data. This task directly targets the note_content_richness and vermas_task_visibility KPIs which have seen zero/minimal movement across 3 cycles.
