---
status: pending
priority: medium
workflow: 
---

# Implement Pattern Detection Analyzer

Create the analyzers module in src/session_insights/analyzers/. Implement pattern.py with: (1) SuccessFailureAnalyzer - detect patterns in what approaches worked vs failed, (2) TimelineAnalyzer - identify work patterns over time (daily/weekly), (3) CrossSessionCorrelator - find related sessions across .claude/.codex/.vermas sources. Each analyzer should take a list of Session objects and return Insight objects (from models/insight.py). Include unit tests in tests/analyzers/test_pattern.py.
