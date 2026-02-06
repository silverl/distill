---
status: done
priority: medium
workflow: null
---
# Run final KPI verification to confirm all targets met

After all fixes are applied, run the complete KPI verification again to confirm all targets are met.

1. Run the full pipeline: `cd /Users/nikpatel/Documents/GitHub/vermas-experiments/session-insights && uv run python -m session_insights analyze --dir /Users/nikpatel/Documents/GitHub/vermas --global --output /tmp/kpi-final/`
2. Re-measure ALL KPIs with the same methodology as the baseline:
   - project_names: count real vs numeric (target: 95%+)
   - narrative_quality: score sample of 50+ sessions (target: 80%+)
   - weekly_digests: verify weekly/ folder with ISO-week content (target: 100%)
   - tests_pass: `uv run pytest tests/ -x -q` (target: 100%)
   - coverage: `uv run pytest tests/ --cov=session_insights -q` (target: 90%+)
3. Write `KPI_FINAL.md` with exact measurements and comparison to baseline
4. If any KPI is below target, document specifically what remains to be fixed

This task validates that the mission is actually complete with hard data, not estimates.
