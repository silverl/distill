---
status: pending
priority: medium
workflow: 
---

# Implement VerMAS State Parser

Implement the vermas.py parser in src/session_insights/parsers/ to parse .vermas/ state directories. Parse workflow YAML, task state, event logs, recaps, and memory files. Follow the established parser pattern from claude.py: (1) discover .vermas/ directories and their subdirectories (workflows/, tasks/, events/, memory/), (2) parse each file type into the unified Session model, (3) extract task completion status, agent interactions, and learnings. Include unit tests in tests/parsers/test_vermas.py.
