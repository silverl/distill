---
status: pending
priority: medium
workflow: 
---

# Create project structure and CLI skeleton

Create the foundational project structure for session-insights:

1. Create src/session_insights/ directory with:
   - __init__.py with version info
   - cli.py with Click-based CLI skeleton (main entry point, analyze subcommand)
   - parsers/__init__.py (empty module for now)
   - analyzers/__init__.py (empty module for now)
   - formatters/__init__.py (empty module for now)

2. Create pyproject.toml with:
   - Project metadata (name: session-insights)
   - Dependencies: click, pydantic>=2.0
   - Dev dependencies: pytest, pytest-cov
   - Entry point: session-insights = session_insights.cli:main

3. Create basic tests/test_cli.py with smoke test for CLI

4. Verify CLI works: `uv run session-insights --help`
