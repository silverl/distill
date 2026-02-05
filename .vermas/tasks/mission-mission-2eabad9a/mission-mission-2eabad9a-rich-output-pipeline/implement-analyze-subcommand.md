---
status: done
priority: medium
workflow: null
---
# Implement the analyze subcommand beyond its current stub

The analyze subcommand was called out as the highest-leverage item in prior cycle evaluation. Implement it to: run the full parse-model-format pipeline for a given directory or session, output statistics (session count, content richness score, field coverage), and optionally generate the formatted Obsidian notes. This bridges CLI completeness to content richness and moves cli_runs_clean toward 100%. Ensure the subcommand exits cleanly with proper error handling for missing directories or unparseable sessions.
