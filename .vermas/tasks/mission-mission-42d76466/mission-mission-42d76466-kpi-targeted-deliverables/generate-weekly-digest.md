---
status: done
priority: medium
workflow: null
---
# Generate weekly digest summaries from session data

Implement a module/command that groups sessions by ISO week and generates a weekly digest markdown file per week in a `weekly/` output folder. Each digest should include: week date range, 'What Got Done' (summarize outcomes across sessions), 'Challenges Faced' (extract from sessions tagged #debugging or with error-related summaries), 'Tools & Techniques' (aggregate tool usage stats), and 'Projects Touched' (list projects from project detection with session counts). Format must match the mission spec. Add a test that verifies correct weekly grouping and output structure. This delivers Mission Deliverable #2 (Weekly Digest) and moves the `weekly_digests` KPI.
