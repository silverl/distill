---
status: done
priority: high
---
# foundation-bootstrap

The cycle history shows 3 consecutive failures trying to implement the analyze command directly. The root cause is attempting complex features without stable foundations. This plan takes a DIFFERENT approach: instead of retrying the failed 'implement-analyze-command' task, we break it into 4 smaller, sequential tasks with clear success criteria. Each task is minimal and verifiable. Task 1 (package structure) must succeed before anything else - this was the 'setup-project-structure' that failed in cycle 1. Tasks 2 and 3 can run in parallel once task 1 completes. Task 4 (the actual parser) only runs after the foundations are solid. Using 'session-insights-bootstrap' squad which is designed for foundational setup work. Each task has explicit SUCCESS CRITERIA so agents know exactly when they're done.
