---
status: done
priority: medium
workflow: null
---
# Unify BaseSession into a single model with all fields

Merge the two incompatible BaseSession classes (parsers/models.py and models/__init__.py) into ONE canonical BaseSession class that includes ALL fields: messages, tool_calls, outcomes, tools_used, turns, task_description, signals, learnings, improvements, quality_assessment, cycle_info. Remove the duplicate class. Update the compatibility properties so they return real data instead of empty lists. Update ALL imports across parsers, formatters, and CLI to use the unified model. Run existing tests to confirm nothing breaks.
