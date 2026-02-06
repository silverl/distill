---
status: done
priority: medium
workflow: null
---
# Add negative-path CLI tests for robustness

Add comprehensive negative-path tests for the session-insights CLI: (1) malformed input files — truncated JSON, invalid JSONL lines, corrupted session state, (2) missing directories — --dir pointing to non-existent path, --global with no ~/.claude/ directory, (3) permission errors — unreadable session files (use mocking), (4) empty session files — zero-byte files, valid JSON but no sessions, (5) edge cases — very large session files, sessions with no messages, sessions with only system messages. Each test should verify the CLI exits cleanly (exit code 0 with warning, or well-formed error message with non-zero exit code — no tracebacks). Also verify the --global flag correctly discovers sessions from ~/.claude/ and ~/.codex/ home directories using mocked home paths. This targets cli_runs_clean KPI toward 100%.
