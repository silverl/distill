---
status: done
priority: medium
workflow: null
---
# Build weekly_digests KPI measurer and verify digest output

In session-insights/src/session_insights/measurers/, create weekly_digests.py with a WeeklyDigestsMeasurer class inheriting from Measurer. It should: (1) check that the output weekly/ folder exists, (2) verify weekly digest files exist for weeks that have sessions, (3) verify each digest contains required sections: 'What Got Done', 'Projects Touched', and 'Tools Most Used' (or equivalent headings), (4) return KPIResult with name='weekly_digests', value=percentage of weeks with valid digests, target=100. Weekly digests appear to already be generated (2 files exist in insights/weekly/). Verify the existing output matches the required format. If sections are missing (e.g., 'Projects Touched' requires project detection to work first), update the weekly formatter in formatters/obsidian.py to include: What Got Done (accomplishments), Projects Touched (unique projects from sessions that week), Tools Most Used (aggregated tool counts), and Challenges Faced. Add unit tests for the measurer. Ensure the formatter handles weeks with zero project-detected sessions gracefully.
