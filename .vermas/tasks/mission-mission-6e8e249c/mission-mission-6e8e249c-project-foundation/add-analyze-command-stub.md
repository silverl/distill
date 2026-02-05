---
status: done
priority: medium
workflow: null
---
# Add analyze command stub to CLI

Add a stub 'analyze' subcommand that accepts options but doesn't process yet:

1. Update src/session_insights/cli.py to add:
   - @main.command() called 'analyze'
   - Add options: --dir (default '.'), --output (default 'vault/')
   - The command should just print 'Analyzing {dir}, output to {output}' and exit

2. Test by running: uv run python -m session_insights.cli analyze --dir . --output test-vault/

3. Add a test in tests/session_insights/test_cli.py that uses click.testing.CliRunner to invoke the analyze command.

This creates the CLI interface. Actual analysis logic will be added in future tasks.
