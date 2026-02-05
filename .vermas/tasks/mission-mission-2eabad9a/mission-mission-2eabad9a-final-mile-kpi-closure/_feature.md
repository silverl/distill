---
status: pending
priority: high
---

# final-mile-kpi-closure

Cycle history shows steady improvement (25→45→55→68%) with cycle 4 rated 'excellent'. The remaining 32% gap maps to three specific KPIs: vermas_task_visibility (65%), note_content_richness (below 90%), and cli_runs_clean (below 100%). Tasks are designed to directly target each gap: task 1 fixes the data exposure layer (vermas_task_visibility), task 2 fixes rendering for both VerMAS and Claude content (note_content_richness), task 3 adds robustness testing (cli_runs_clean), and task 4 replaces estimation with automated measurement so we can verify actual KPI values. Dependencies ensure formatter work happens after parser fixes, and measurement runs after all content improvements. Using the 'session-insights' squad which has been executing successfully in recent cycles. No failed tasks to avoid — all prior cycles completed their tasks, we just need new targeted work.
