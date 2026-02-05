# Mission: Session Insights

Build a CLI utility that analyzes AI coding assistant session history and produces structured Obsidian notes with insights, patterns, and learnings.

## Vision

Developers use multiple AI coding assistants (Claude Code, Codex CLI, etc.). Each creates session history in their own format (`.claude/`, `.codex/`, `.vermas/`). This utility unifies that history into human-readable Obsidian notes that reveal:

- What was built and when
- What approaches worked vs. failed
- Patterns across sessions
- Learnings to carry forward
- Task completion rates and quality

## Scope

### Input Sources
- `.claude/` - Claude Code sessions, conversations, tool usage
- `.codex/` - OpenAI Codex CLI history
- `.vermas/` - VerMAS workflows, tasks, events, recaps, memory

### Output Format
- Obsidian-compatible markdown notes
- Daily/weekly summaries
- Project-level insights
- Cross-session pattern analysis
- Actionable learnings

## Success KPIs

| KPI | Target | How Measured |
|-----|--------|--------------|
| Parse Success Rate | 95%+ | Sessions parsed without error |
| Insight Quality | Useful | Human review of generated notes |
| Obsidian Compatibility | 100% | Notes render correctly in Obsidian |
| Cross-Source Correlation | Yes | Links sessions across .claude/.codex/.vermas |
| Test Coverage | 90%+ | pytest --cov |
| Usable CLI | Yes | `session-insights analyze --dir . --output vault/` |

## Deliverables

1. **CLI Tool**: `session-insights` command with subcommands
2. **Parsers**: For each source format (.claude, .codex, .vermas)
3. **Analyzers**: Pattern detection, success/failure analysis
4. **Formatters**: Obsidian markdown generation
5. **Tests**: Comprehensive test suite
6. **Documentation**: README with usage examples

## Technical Approach

```
src/
  session_insights/
    cli.py           # Entry point
    parsers/
      claude.py      # Parse .claude/ sessions
      codex.py       # Parse .codex/ history
      vermas.py      # Parse .vermas/ state
    analyzers/
      patterns.py    # Cross-session patterns
      quality.py     # Success/failure analysis
      timeline.py    # Temporal analysis
    formatters/
      obsidian.py    # Generate Obsidian notes
    models/
      session.py     # Unified session model
      insight.py     # Insight/learning model
tests/
  unit/
  integration/
```

## Iteration Cycles

This project will be built through multiple agent collaboration cycles:

1. **Cycle 1**: Core parsers - read and structure raw data
2. **Cycle 2**: Unified model - normalize across sources
3. **Cycle 3**: Basic analysis - extract key metrics
4. **Cycle 4**: Pattern detection - find cross-session insights
5. **Cycle 5**: Obsidian output - generate notes
6. **Cycle 6**: CLI polish - user-friendly interface
7. **Cycle N**: Iterate until shipped

Each cycle includes: Plan → Implement → Test → Review → Learn

## Constraints

- Python 3.11+
- Minimal dependencies (prefer stdlib)
- Must work offline (no API calls for analysis)
- Obsidian notes must be standalone (no plugins required)

## Definition of Done

- [ ] CLI installs and runs: `pip install -e . && session-insights --help`
- [ ] Parses real .claude/ .codex/ .vermas/ directories
- [ ] Generates Obsidian vault with useful insights
- [ ] Tests pass with 90%+ coverage
- [ ] README documents usage
- [ ] Dogfooding: Use it to analyze this project's own sessions
