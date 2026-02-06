---
status: done
priority: medium
workflow: null
---
# Implement project detection from session cwd and measure KPI

In the session-insights tool at /Users/nikpatel/Documents/GitHub/vermas-experiments/session-insights, implement project detection logic that extracts the project name from the `cwd` field in session metadata. Steps: 1) In the parsers or a new detection module, write a function that maps cwd paths to project names (e.g., '/Users/nikpatel/Documents/GitHub/vermas' -> 'vermas'). 2) Integrate this into the analyze pipeline so each session note gets a 'project' field. 3) Run the detection across all existing session notes and report the percentage of sessions with a detected project. 4) Write unit tests for the detection logic covering edge cases (home dir sessions, nested repos, sessions with no cwd). 5) Run the full test suite with `uv run pytest tests/ -x -q` and capture the pass rate. Output the measured project_detection percentage and tests_pass percentage to stdout so the KPI measurement infrastructure can capture them.
