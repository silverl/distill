---
status: done
priority: critical
workflow: null
---
# Create minimal Python package structure

Create the foundational Python package structure for session-insights. This is a MINIMAL setup task:

1. Create directory structure:
   - src/session_insights/__init__.py (with __version__ = '0.1.0')
   - src/session_insights/cli.py (stub with 'def main(): pass')
   - tests/__init__.py
   - tests/test_cli.py (single test that imports the package)

2. Create pyproject.toml with:
   - name = 'session-insights'
   - version = '0.1.0'
   - dependencies = ['click>=8.0']
   - [project.scripts] session-insights = 'session_insights.cli:main'

3. Verify the package can be installed with 'pip install -e .'

SUCCESS CRITERIA: Running 'python -c "import session_insights"' works without error.
