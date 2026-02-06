---
status: done
priority: medium
workflow: null
---
# Run full analyze command and verify all 5 KPIs pass programmatically

Create a verification script or test that runs the full analyze pipeline and checks all 5 KPIs: (1) Project names are real words not numeric — scan projects/ folder and assert no filenames match 'project-\d+.md' pattern, (2) Narrative quality — sample at least 20 session notes and assert narratives exceed 10 words and contain no XML tags, (3) Weekly digests — assert weekly/ directory exists and contains at least one ISO-week file, (4) All tests pass — run 'uv run pytest tests/ -x -q' and assert exit code 0, (5) Coverage >= 90% — run pytest with --cov and parse the output. This task is the final gate — if any KPI fails, document exactly which one and why in the output.
