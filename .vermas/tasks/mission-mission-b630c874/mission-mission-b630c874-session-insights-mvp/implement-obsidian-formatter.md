---
status: done
priority: medium
workflow: null
---
# Implement Obsidian markdown formatter

Implement Obsidian-compatible markdown output:

1. Create src/session_insights/formatters/obsidian.py with:
   - ObsidianFormatter class
   - format_session(session: BaseSession) -> str - single session note
   - format_daily_summary(sessions: list[BaseSession], date: date) -> str
   - Include proper frontmatter (YAML metadata block)
   - Use Obsidian-compatible links [[note-name]]
   - Add tags for categorization (#ai-session, #claude, etc.)

2. Create src/session_insights/formatters/templates.py with:
   - Jinja2 or string templates for consistent formatting
   - Session template with: summary, timeline, tools used, outcomes
   - Daily summary template with: sessions list, stats, patterns

3. Add tests/formatters/test_obsidian.py with:
   - Test frontmatter is valid YAML
   - Test links are properly formatted
   - Test markdown renders correctly (no broken syntax)

Target: 100% Obsidian compatibility.
