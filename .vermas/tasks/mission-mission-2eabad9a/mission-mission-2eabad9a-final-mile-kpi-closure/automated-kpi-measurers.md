---
status: done
priority: medium
workflow: null
---
# Implement automated KPI measurement scripts

Create measurement scripts that replace estimation with actual measurement for each KPI: (1) cli_runs_clean measurer — run the CLI with a matrix of inputs (valid dirs, empty dirs, missing dirs, --global, --output to various paths, malformed sessions mixed with valid ones) and report percentage of runs with clean exit, (2) note_content_richness measurer — run CLI to generate notes, then score each note against a checklist of expected content fields (has timestamps, has duration, has tool list, has outcomes, has VerMAS metadata when applicable, has conversation summary for Claude sessions) and report percentage of fields present across all notes, (3) vermas_task_visibility measurer — parse generated notes for VerMAS sessions and check each expected metadata field (task_description, signals, learnings, cycle_info) is present and non-empty. Each measurer should output a JSON summary with the KPI name, measured value, and target. These scripts should be runnable via pytest or as standalone commands.
