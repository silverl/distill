---
status: pending
priority: medium
workflow: 
---

# Wire Analyzers to CLI and Achieve 90% Coverage

Update cli.py to use the new analyzers in the analyze command. Add --analyze flag to run pattern detection after parsing. Update Obsidian formatter to include analyzer output (patterns, learnings, correlations). Run full test suite and add any missing tests to achieve 90%+ coverage target. Verify end-to-end: session-insights analyze --dir . --output vault/ --analyze produces Obsidian notes with insights.
