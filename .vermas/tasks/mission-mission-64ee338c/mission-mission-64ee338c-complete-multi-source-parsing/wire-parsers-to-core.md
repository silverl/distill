---
status: pending
priority: medium
workflow: 
---

# Wire New Parsers to Core Analysis Pipeline

Update src/session_insights/core.py to register CodexParser and VermasParser alongside ClaudeParser. Modify discover_sessions() to scan all three source directories. Ensure parse_session_file() dispatches to the correct parser based on source type. Add integration tests in tests/integration/test_multi_source.py verifying that a directory with mixed .claude/, .codex/, and .vermas/ sources produces unified AnalysisResult with cross-source correlation.
