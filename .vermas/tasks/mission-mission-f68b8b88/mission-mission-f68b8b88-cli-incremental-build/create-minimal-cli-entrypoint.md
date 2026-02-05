---
status: done
priority: medium
workflow: null
---
# Create minimal CLI entry point that prints version

Create the absolute minimal CLI: src/session_insights/cli.py with a single Click command that prints 'session-insights v0.1.0'. No subcommands, no argument parsing beyond --version. Test by running `uv run session-insights --version`. Add a single pytest test that verifies the CLI can be invoked. This proves the basic wiring works before adding complexity. Signal done when `uv run session-insights` executes without error.
