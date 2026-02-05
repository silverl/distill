---
status: pending
priority: medium
workflow: 
---

# Expose all VerMAS task metadata through unified BaseSession

The VerMAS parser extracts task_description, signals, learnings, improvements, and cycle_info but these fields are not fully exposed through the unified BaseSession model to downstream consumers. Audit parsers/models.py and ensure: (1) task_description is always populated from parsed VerMAS state files, (2) signals list includes all agent signals (done, approved, needs_revision) with timestamps, (3) learnings and improvements arrays are populated from cycle evaluation data, (4) cycle_info (cycle number, quality rating) is available. Add/fix compatibility properties so the formatter can access all metadata. Write unit tests for each field with real VerMAS session fixture data including edge cases (missing fields, older formats without learnings). This directly targets vermas_task_visibility KPI from 65% toward 100%.
