---
status: done
priority: high
workflow: null
depends:
- create-package-structure
---
# Implement basic CLI with Click

Implement a working CLI skeleton using Click framework. Build on the package structure from the previous task.

1. In src/session_insights/cli.py:
   - Import click
   - Create main group: @click.group() def main(): pass
   - Add 'analyze' subcommand stub: @main.command() @click.option('--dir', default='.') @click.option('--output', default='vault/') def analyze(dir, output): click.echo(f'Analyzing {dir}, output to {output}')
   - Add 'version' command that prints the version

2. In tests/test_cli.py:
   - Test that 'session-insights --help' returns 0
   - Test that 'session-insights analyze --help' returns 0
   - Test that 'session-insights version' prints version

3. Run tests and ensure they pass

SUCCESS CRITERIA: 'session-insights analyze --dir . --output vault/' prints the expected message without error.
