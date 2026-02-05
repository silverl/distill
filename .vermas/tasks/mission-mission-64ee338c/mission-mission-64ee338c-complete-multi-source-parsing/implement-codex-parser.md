---
status: pending
priority: medium
workflow: 
---

# Implement Codex CLI Parser

Create src/session_insights/parsers/codex.py to parse .codex/ session history. Follow the same pattern as the existing claude.py parser: extend BaseSession with CodexSession, implement CodexParser class with discover_sessions() and parse_session_file() methods. The .codex/ format uses JSON files with conversation history. Add to parsers/__init__.py exports. Include unit tests in tests/parsers/test_codex.py with at least 10 test cases covering: session discovery, JSON parsing, timestamp extraction, tool usage tracking, and error handling for malformed files.
