---
status: done
priority: medium
workflow: null
---
# Replace raw prompt passthrough with synthesized session narratives

Fix narrative generation so session summaries are human-readable descriptions instead of raw first-user prompts. Currently many narratives show things like '<command-message>init</command-message>' or 'analyze home'. The fix: in the narrative/summary generation code, replace the raw prompt passthrough with a synthesizer that builds narratives from session metadata — tools used, files modified count, duration, tags, and outcomes. Filter out any strings containing XML tags or strings shorter than 10 words. Example output: '45-minute session in vermas using Bash, Read, Edit. Modified 15 files across the workflow engine.' Write tests that verify: (1) narratives with XML tags are rejected/resynthesized, (2) narratives under 10 words are rejected/resynthesized, (3) generated narratives include tool names and duration when available. Run tests to confirm.
