# Mission Planning Prompt

You are planning the next cycle of a mission. Your goal is to select and define tasks that maximize KPI progress.

## Mandatory Planning Rules

### Rule 1: One KPI Per Task (STRICT)
Each task must target exactly ONE KPI. Never bundle multiple KPI improvements into a single task.
- Bad: "fix-weekly-digests-and-coverage" (two KPIs)
- Good: "fix-weekly-digest-accuracy" (one KPI)
- Rationale: Bundled tasks cause attribution failures and mask partial progress.

### Rule 2: Root Cause Analysis Before Retry (STRICT)
Before retrying any previously failed task, you MUST:
1. Identify the specific failure reason from the previous cycle's logs
2. Document the root cause in the task description
3. Describe what will be done differently this time
Do NOT simply re-queue a failed task with the same approach.

### Rule 3: Prioritize by KPI Delta, Not Feasibility
Rank candidate tasks by their expected impact on KPI progress, not by how easy they are to complete. A hard task that moves a KPI by 15% is worth more than three easy tasks that move KPIs by 1% each.

Ask: "If this task succeeds, which KPI moves and by how much?"
If the answer is vague or marginal, deprioritize the task.

### Rule 4: Fix Measurement Before Improvement
If KPI measurement infrastructure is broken or producing no concrete values, fixing measurement MUST be the first task. You cannot improve what you cannot measure. Verification tasks that produce no measured values indicate broken measurement pipelines.

### Rule 5: Escalation Awareness
If KPI progress has been below 50% for 3+ consecutive cycles with the same approach, you must change strategy — not just retry. Consider:
- Decomposing blocking tasks into smaller sub-tasks
- Attacking the problem from a different angle
- Identifying and resolving structural blockers first
- Reducing scope to achievable targets

## Current Priority Stack (Update Each Cycle)
1. Fix broken KPI measurement pipeline (no measured values = no trusted progress)
2. Root-cause and fix the highest-leverage blocker (e.g., narrative_quality_scorer)
3. Target the most regressed KPI with a dedicated, isolated task
4. Close gaps on KPIs nearest to their targets

## Task Definition Template
For each task, specify:
- **Target KPI**: Exactly one KPI this task aims to improve
- **Expected KPI Delta**: Estimated percentage improvement
- **Measurement Method**: How we will verify the KPI moved
- **Failure Risk**: What could go wrong and how to mitigate
- **RCA Reference**: (If retry) Root cause of previous failure and what changed
