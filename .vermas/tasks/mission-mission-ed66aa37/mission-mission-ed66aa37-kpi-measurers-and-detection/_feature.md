---
status: done
priority: high
---
# kpi-measurers-and-detection

Cycle 1 reached only 35% KPI progress because 4 of 5 KPIs have no automated measurers, making progress invisible to the evaluation system. The BaseSession model already has `project` and `narrative` fields, and parsers partially populate `project` from cwd. Weekly digests and project notes are partially generated. The critical gap is: (1) no measurers for project_detection, narrative_quality, project_notes, or weekly_digests, so even existing progress is unmeasured, and (2) narrative field is never populated, and project detection has low yield (only 2 of 9348 sessions). This plan pairs measurer creation with the underlying feature work so each task advances a measurable KPI. Tasks are ordered so measurers come first (they can measure the current baseline of 0/low), then feature work raises the scores.
