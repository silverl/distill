---
status: pending
priority: medium
workflow: 
---

# Implement VerMAS State Parser

Create src/session_insights/parsers/vermas.py to parse .vermas/ workflow state. This includes: mission files, cycle directories, task artifacts, recap files, and agent signals. Create VermasSession extending BaseSession and VermasParser class. Parse workflow executions into sessions with: task descriptions, agent signals (done/approved/blocked), durations, and outcomes. Add unit tests in tests/parsers/test_vermas.py with at least 10 test cases covering: mission discovery, signal parsing, multi-cycle tracking, and error handling.
