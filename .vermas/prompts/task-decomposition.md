# Task Decomposition Prompt

When a task is complex or has failed previously, decompose it into smaller sub-tasks before execution.

## Decomposition Rules

### When to Decompose
- Task has failed in a previous cycle
- Task involves CLI implementation (HIGH RISK — always decompose)
- Task touches 3+ files or modules
- Task has multiple independent deliverables
- Task estimated duration exceeds one cycle

### CLI Task Decomposition (Mandatory)
CLI-related tasks MUST be split into three layers:
1. **Argument parsing**: Define CLI arguments, flags, and validation
2. **Dispatch logic**: Route parsed arguments to the correct handler
3. **Business logic**: Implement the actual functionality independent of CLI

Each layer should be a separate sub-task that can succeed or fail independently.

### General Decomposition Strategy
1. Identify the smallest unit of work that produces a testable result
2. Order sub-tasks by dependency (what must exist before what)
3. Ensure each sub-task has a clear completion criterion
4. If a sub-task fails, the others should still be independently valuable

### Sub-task Definition
For each sub-task:
- **Deliverable**: One specific, testable output
- **Dependencies**: Which sub-tasks must complete first
- **Completion Criterion**: How to verify this sub-task succeeded
- **Isolation**: Can this sub-task be committed independently? (should be yes)
