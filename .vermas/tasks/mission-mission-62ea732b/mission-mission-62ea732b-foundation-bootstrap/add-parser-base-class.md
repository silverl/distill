---
status: done
priority: high
workflow: null
depends:
- create-package-structure
---
# Create base parser interface and test fixture

Create the parser base class and a simple test fixture. This establishes the pattern for all parsers.

1. Create src/session_insights/parsers/__init__.py

2. Create src/session_insights/parsers/base.py:
   - Define SessionData dataclass with: source (str), timestamp (datetime), content (dict)
   - Define abstract BaseParser class with: parse(path: Path) -> list[SessionData]

3. Create tests/fixtures/ directory with sample data:
   - tests/fixtures/.claude/sample_session.json (minimal valid JSON)

4. Create tests/test_parsers.py:
   - Test that BaseParser cannot be instantiated directly
   - Test that SessionData can be created with valid data

SUCCESS CRITERIA: pytest tests/test_parsers.py passes with 100% of tests green.
