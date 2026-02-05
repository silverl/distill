---
status: done
priority: medium
workflow: null
---
# Implement Claude session parser

Implement parser for .claude/ session history:

1. Create src/session_insights/parsers/claude.py with:
   - ClaudeSession Pydantic model (session_id, timestamp, messages, tool_calls, summary)
   - ClaudeParser class with parse_directory(path: Path) -> list[ClaudeSession]
   - Handle .claude/projects/*/sessions/*.json or similar structure
   - Extract: conversation turns, tool usage, timestamps, outcomes

2. Create src/session_insights/parsers/models.py with:
   - BaseSession abstract model (common fields across sources)
   - Message model (role, content, timestamp)
   - ToolUsage model (tool_name, arguments, result)

3. Add tests/parsers/test_claude.py with:
   - Test parsing valid session files
   - Test handling missing/malformed data gracefully
   - Test with sample .claude/ data structure

Target: 95%+ parse success rate on valid sessions.
