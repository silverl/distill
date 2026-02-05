---
status: pending
priority: medium
workflow: 
---

# Implement analyze CLI command with full pipeline

Wire up the full analysis pipeline in the CLI:

1. Implement analyze subcommand in cli.py:
   - `session-insights analyze --dir PATH --output PATH`
   - --dir: Directory to scan for session history (default: current dir)
   - --output: Output directory for Obsidian notes (required)
   - --source: Filter sources (claude, codex, vermas) - optional
   - --since: Only analyze sessions after date - optional

2. Implement core pipeline in src/session_insights/core.py:
   - discover_sessions(directory: Path) -> dict[str, list[Path]]
   - analyze(sessions: list[BaseSession]) -> AnalysisResult
   - AnalysisResult model with: sessions, stats, patterns

3. Integration flow:
   - Discover session files by source
   - Parse each with appropriate parser
   - Format as Obsidian notes
   - Write to output directory

4. Add tests/test_integration.py:
   - End-to-end test with sample data
   - Test CLI exit codes and error messages

Target: Working CLI that produces valid Obsidian notes from .claude/ data.
