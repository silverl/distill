---
status: done
priority: medium
workflow: null
---
# Wire weekly digest formatter into the analyze pipeline

The weekly digest formatter may already exist but is not wired into the CLI analyze command pipeline. Fix this in core.py and/or cli.py so that running 'uv run python -m session_insights analyze --dir <project> --global --output <path>' also creates a 'weekly/' subfolder in the output directory with one markdown file per ISO week (e.g., 'weekly/2026-W05.md'). Each weekly file should aggregate the daily summaries for that week. Ensure the weekly/ folder is created even if there's only one week of data. Add a test that runs the formatter and verifies the weekly/ directory is created with properly named ISO-week files. Run tests to confirm.
