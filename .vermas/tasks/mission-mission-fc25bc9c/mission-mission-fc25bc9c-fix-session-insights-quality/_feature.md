---
status: done
priority: high
---
# fix-session-insights-quality

Prior mission completed 70 tasks across 5 cycles but KPIs regressed to 45%, indicating the implementations were shallow or incorrect. This plan takes a different approach: fewer, more focused tasks with explicit verification criteria baked into each description. Tasks 1-3 attack the three functional bugs independently (no dependencies, can run in parallel). Task 4 depends on all three to measure coverage accurately after fixes. Task 5 is a programmatic verification gate that checks all 5 KPIs, preventing the pattern of 'tasks complete but KPIs unmet'. Using the 'session-insights' squad which is the most specific match for this project's codebase.
