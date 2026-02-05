---
status: done
priority: medium
workflow: null
---
# Add integration tests asserting rich content in formatted output

Add integration tests that run the full pipeline (parse → unified model → format) for both Claude and VerMAS session types. Tests should assert: (1) output notes contain non-empty content sections, (2) VerMAS notes include task description, signals, and learnings when present in source data, (3) Claude notes include conversation summaries and tool usage when message data exists, (4) the analyze subcommand runs cleanly and returns correct exit codes. Use fixture data representative of real sessions. These tests provide automated measurement for note_content_richness and cli_runs_clean KPIs. Target test_coverage KPI of 90%.
