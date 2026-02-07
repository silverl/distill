# Distill

Distill raw AI coding sessions into journals, blogs, and multi-platform publications.

## What It Does

Distill reads session data from AI coding assistants (Claude, Codex, VerMAS) and transforms it into structured, publishable content:

1. **Analyze** -- Parse sessions, compute statistics, detect patterns, generate per-project and weekly notes
2. **Journal** -- Synthesize daily journal entries from raw sessions using Claude LLM
3. **Blog** -- Generate weekly synthesis posts and thematic deep-dives from journal entries
4. **Publish** -- Distribute to multiple platforms: Ghost, Substack, Twitter/X, LinkedIn, Reddit, Obsidian, GitHub

## Install

```bash
uv sync
```

## Usage

```bash
# Analyze sessions and generate notes
distill analyze --dir /path/to/project --output ./insights --global

# Generate journal entries
distill journal --dir /path/to/project --output ./insights --since 2026-01-01 --global

# Generate blog posts
distill blog --output ./insights --type all

# List discovered sessions
distill sessions --dir /path/to/project --global
```

## Session Sources

| Source | Location | Format |
|--------|----------|--------|
| Claude | `~/.claude/projects/*/` | JSONL session files |
| Codex | `.codex/` in project dirs | Session directories |
| VerMAS | `.vermas/state/` in project dirs | Mission cycle state |

## Project Structure

```
src/
  analyzers/       # Pattern detection
  blog/            # Blog synthesis pipeline (config, context, prompts, themes, diagrams)
  formatters/      # Output formatters (Obsidian, project notes, weekly digests)
  journal/         # Journal synthesis pipeline (cache, memory, prompts)
  measurers/       # Quality KPI measurers
  models/          # Data models
  parsers/         # Session parsers (Claude, Codex, VerMAS)
  cli.py           # CLI interface (Typer)
  core.py          # Core pipeline orchestration
  narrative.py     # Narrative enrichment
tests/             # Unit + integration tests (645+ tests)
```

## Development

```bash
# Run tests
uv run pytest tests/ -x -q

# Type checking
uv run mypy src/ --no-error-summary

# Lint
uv run ruff check src/ && uv run ruff format src/
```

## License

MIT
