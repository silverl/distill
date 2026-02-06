---
status: done
priority: medium
workflow: null
---
# Fix project name derivation edge cases to reach 95%+ KPI

Based on the KPI baseline measurements from the previous task, fix remaining project name derivation issues.

Read `KPI_BASELINE.md` to understand the current project_names percentage and which specific projects still have numeric IDs.

In the session-insights codebase (`/Users/nikpatel/Documents/GitHub/vermas-experiments/session-insights`):
1. Find the project name derivation code (likely in parsers/ or a project detection module)
2. Identify WHY some projects still get numeric IDs - check edge cases: monorepos, nested workspaces, symlinked dirs, paths with special characters, Claude project paths like `~/.claude/projects/-Users-nikpatel-Documents-GitHub-vermas/`
3. Add test fixtures for each edge case pattern found
4. Fix the parser to handle all edge cases
5. Run tests to confirm fixes: `uv run pytest tests/ -x -q`
6. Re-run the pipeline on a sample to verify improvement

Target: 95%+ of project notes should have real directory names, not numeric IDs.
