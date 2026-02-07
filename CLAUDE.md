# Distill

Content pipeline that transforms raw AI coding sessions into publishable content across multiple platforms.

## Project Structure

```
src/
  analyzers/                  # Pattern detection from session data
  blog/                       # Blog synthesis pipeline
    config.py                 # BlogConfig, post types
    context.py                # WeeklyBlogContext, ThematicBlogContext preparation
    diagrams.py               # Mermaid diagram generation for blog posts
    formatter.py              # Obsidian blog formatting
    prompts.py                # LLM prompts for blog synthesis
    reader.py                 # Journal entry reader for blog input
    state.py                  # BlogState tracking (what's been generated)
    synthesizer.py            # BlogSynthesizer - LLM-based content generation
    themes.py                 # Theme detection and thematic post generation
  formatters/                 # Output formatters
    obsidian.py               # Obsidian markdown (wiki links, frontmatter)
    project.py                # Per-project note formatter
    templates.py              # Formatting templates
    weekly.py                 # Weekly digest formatter
  journal/                    # Journal synthesis pipeline
    cache.py                  # Journal entry caching (skip regeneration)
    config.py                 # JournalConfig (style, word count, model)
    context.py                # Context preparation for LLM synthesis
    formatter.py              # Journal markdown formatting
    memory.py                 # Working memory (cross-session context)
    prompts.py                # Journal generation prompts
    synthesizer.py            # JournalSynthesizer - LLM journal generation
  measurers/                  # Quality KPI measurers
  models/                     # Core data models (Insight, etc.)
  parsers/                    # Session parsers (Claude, Codex, VerMAS)
  cli.py                      # CLI entry point (Typer app)
  core.py                     # Pipeline orchestration (analyze, generate_*, blog)
  narrative.py                # Narrative enrichment for session summaries
tests/                        # 645+ tests (unit + integration)
```

## Essential Commands

```bash
# Run all tests
uv run pytest tests/ -x -q

# Run specific test file
uv run pytest tests/blog/test_formatter.py -x -q

# Type checking
uv run mypy src/ --no-error-summary

# Lint and format
uv run ruff check src/ && uv run ruff format src/

# Run the CLI
uv run python -m distill analyze --dir . --output ./insights
uv run python -m distill journal --dir . --output ./insights --global
uv run python -m distill blog --output ./insights --type all
```

## Key Architecture

### Pipeline Flow
```
Raw sessions (.claude/, .codex/, .vermas/)
    -> Parsers (claude.py, codex.py, vermas.py) -> BaseSession models
    -> Analyzers (pattern detection, statistics)
    -> Formatters (Obsidian notes, project notes, weekly digests)
    -> Journal synthesizer (LLM: sessions -> daily journal entries)
    -> Blog synthesizer (LLM: journal entries -> weekly/thematic blog posts)
```

### LLM Integration
- Journal and blog synthesis call Claude via subprocess (`claude` CLI)
- `BlogSynthesizer` and `JournalSynthesizer` both use `subprocess.run` with `--print` flag
- Prompts are in `blog/prompts.py` and `journal/prompts.py`
- Configurable model and timeout via config objects

### Blog Pipeline
- `core.py:generate_blog_posts()` orchestrates blog generation
- Reads journal entries via `blog/reader.py`
- Builds context via `blog/context.py` (WeeklyBlogContext, ThematicBlogContext)
- Detects themes via `blog/themes.py`
- Synthesizes via `blog/synthesizer.py`
- Formats output via `blog/formatter.py`
- Tracks state via `blog/state.py` (avoids re-generating existing posts)

## Conventions

- **Python 3.11+**, managed with `uv`
- **Pydantic v2** for all models and validation
- **Typer** for CLI (app instance in `cli.py`)
- **Strict mypy** type checking
- **ruff** for linting and formatting (line length 100)
- Test files mirror source structure: `src/.../foo.py` -> `tests/.../test_foo.py`
- Coverage target: 90%+

## Known Issues

- `test_verify_all_kpis.py` depends on local data files and may fail in clean clones
