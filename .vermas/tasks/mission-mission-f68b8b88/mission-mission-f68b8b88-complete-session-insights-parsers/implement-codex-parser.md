---
status: pending
priority: medium
workflow: 
---

# Implement Codex CLI Session Parser

Implement the codex.py parser in src/session_insights/parsers/ to parse .codex/ history directories. Follow the same pattern as the existing claude.py parser: (1) discover session files in .codex/ directories, (2) parse the Codex CLI history format into the unified Session model from models/session.py, (3) extract conversation turns, tool usage, and metadata. Include comprehensive unit tests in tests/parsers/test_codex.py following the same structure as test_claude.py. Target 95%+ test coverage for this module.
