---
status: done
priority: medium
workflow: null
---
# Run programmatic KPI verification and record exact baselines

This is the CRITICAL first task. Run the full session-insights analyze pipeline on real data and measure each KPI with exact numbers:

1. Run: `cd /Users/nikpatel/Documents/GitHub/vermas-experiments/session-insights && uv run python -m session_insights analyze --dir /Users/nikpatel/Documents/GitHub/vermas --global --output /tmp/kpi-baseline/`
2. Count project files with real names vs numeric IDs (e.g., `project-vermas.md` = real, `project-11.md` = numeric). Calculate percentage with real names.
3. Sample 50+ session notes and count how many have quality narratives (>10 words, no XML tags, no raw prompts) vs raw prompts. Calculate percentage.
4. Check if `weekly/` folder exists and contains ISO-week files with actual content (not empty stubs). Record count and whether content is meaningful.
5. Run `uv run pytest tests/ -x -q` and record pass/fail count.
6. Run `uv run pytest tests/ --cov=session_insights --cov-report=term-missing -q` and record coverage percentage and uncovered modules.

Write results to a file `KPI_BASELINE.md` in the project root with exact numbers for each KPI:
- project_names: X% (N real / M total)
- narrative_quality: X% (N quality / M sampled)
- weekly_digests: exists=yes/no, files=N, content_quality=description
- tests_pass: X/Y passing
- coverage: X%

This data drives ALL subsequent tasks. Do NOT fix anything - only measure and record.
