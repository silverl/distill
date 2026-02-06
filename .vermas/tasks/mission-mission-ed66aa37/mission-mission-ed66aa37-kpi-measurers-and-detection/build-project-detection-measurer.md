---
status: done
priority: medium
workflow: null
---
# Build project_detection KPI measurer and fix parser detection

In session-insights/src/session_insights/measurers/, create project_detection.py with a ProjectDetectionMeasurer class inheriting from Measurer (see base.py). It should: (1) load all parsed sessions, (2) count how many have a non-empty `project` field that is NOT '(unknown)' or '(unassigned)', (3) return a KPIResult with name='project_detection', value=percentage, target=95. Then fix the actual detection: in parsers/claude.py, ensure `project` is robustly extracted from `cwd` — the current logic at lines 197-202 uses Path(cwd).name which fails for paths like '/' or home dirs. Add fallback: if cwd contains a known project directory pattern (e.g., GitHub/X, Projects/X), extract X. In parsers/vermas.py, extract project from the working_directory or project_dir fields in the VerMAS state. Add unit tests in tests/ for the measurer and the improved detection logic. Target: measurer runs and reports a real percentage; detection covers >90% of sessions that have a cwd set.
