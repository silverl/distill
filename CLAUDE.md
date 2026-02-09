# Distill

Content pipeline that transforms raw AI coding sessions into publishable content across multiple platforms.

## Project Structure

```
src/
  analyzers/                  # Pattern detection from session data
  blog/                       # Blog synthesis pipeline
    config.py                 # BlogConfig, BlogPostType, Platform, GhostConfig
    context.py                # WeeklyBlogContext, ThematicBlogContext preparation
    diagrams.py               # Mermaid diagram generation for blog posts
    formatter.py              # Thin re-export: ObsidianPublisher as BlogFormatter
    prompts.py                # LLM prompts for blog synthesis
    reader.py                 # Journal entry reader + IntakeDigestEntry for blog input
    state.py                  # BlogState tracking (what's been generated)
    synthesizer.py            # BlogSynthesizer - LLM-based content generation
    themes.py                 # Theme detection and thematic post generation
    blog_memory.py            # BlogMemory/BlogPostSummary for cross-referencing
    publishers/               # Multi-platform output
      base.py                 # BlogPublisher ABC
      obsidian.py             # Obsidian wiki links
      ghost.py                # Ghost CMS markdown
      markdown.py             # Plain markdown
      postiz.py               # Postiz social media scheduler
      twitter.py, linkedin.py, reddit.py  # Social publishers
  formatters/                 # Output formatters
    obsidian.py               # Obsidian markdown (wiki links, frontmatter)
    project.py                # Per-project note formatter
    templates.py              # Formatting templates
    weekly.py                 # Weekly digest formatter
  intake/                     # Content ingestion pipeline
    parsers/                  # Source parsers (RSS, browser, substack, etc.)
    publishers/               # Intake output publishers
    config.py                 # Per-source config models
    models.py                 # ContentItem, ContentSource, ContentType
    seeds.py                  # SeedStore + SeedIdea
    intelligence.py           # LLM entity extraction + classification
    context.py                # Intake context partitioning
  integrations/               # External service integrations
    postiz.py                 # Postiz API client
    scheduling.py             # Postiz scheduling helpers
  journal/                    # Journal synthesis pipeline
    cache.py                  # Journal entry caching (skip regeneration)
    config.py                 # JournalConfig (style, word count, model)
    context.py                # DailyContext preparation for LLM synthesis
    formatter.py              # Journal markdown formatting
    memory.py                 # Working memory (cross-session context)
    prompts.py                # Journal generation prompts
    synthesizer.py            # JournalSynthesizer - LLM journal generation
  measurers/                  # Quality KPI measurers
  models/                     # Core data models (Insight, etc.)
  parsers/                    # Session parsers (Claude, Codex, VerMAS)
  cli.py                      # CLI entry point (Typer app)
  config.py                   # Unified config (.distill.toml + env vars)
  core.py                     # Pipeline orchestration (analyze, generate_*, blog)
  editorial.py                # EditorialStore - user steering notes
  memory.py                   # UnifiedMemory (cross-pipeline, entity tracking)
  store.py                    # JsonStore / PgvectorStore
  embeddings.py               # Sentence-transformer embeddings (optional)
  narrative.py                # Narrative enrichment for session summaries
tests/                        # 1700+ tests (unit + integration)
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
uv run python -m distill run --dir . --output ./insights --use-defaults
uv run python -m distill note "Emphasize X this week" --target "week:2026-W06"
```

## Key Architecture

### Pipeline Flow
```
Raw sessions (.claude/, .codex/, .vermas/)
    -> Parsers (claude.py, codex.py, vermas.py) -> BaseSession models
    -> Analyzers (pattern detection, statistics)
    -> Formatters (Obsidian notes, project notes, weekly digests)
    -> Journal synthesizer (LLM: sessions -> daily journal entries)
        + project context from .distill.toml
    -> Blog synthesizer (LLM: journal entries -> weekly/thematic blog posts)
        + project context + editorial notes
    -> Publishers (Obsidian, Ghost, Postiz, social)
```

### Configuration
- `.distill.toml` loaded by `config.py:load_config()` (CWD then ~/.config/distill/)
- `ProjectConfig` in `[[projects]]` — injected into all LLM prompts
- `EditorialStore` in `.distill-notes.json` — user steering notes
- Environment variables overlay TOML values
- CLI flags overlay everything

### LLM Integration
- Journal and blog synthesis call Claude via subprocess (`claude -p`)
- `BlogSynthesizer` and `JournalSynthesizer` both use `subprocess.run`
- Prompts are in `blog/prompts.py` and `journal/prompts.py`
- Project context and editorial notes injected into rendered prompts
- Configurable model and timeout via config objects

### Blog Pipeline
- `core.py:generate_blog_posts()` orchestrates blog generation
- Loads `DistillConfig` for project context, `EditorialStore` for notes
- Reads journal entries via `blog/reader.py`
- Builds context via `blog/context.py` (WeeklyBlogContext, ThematicBlogContext)
- Detects themes via `blog/themes.py`
- Synthesizes via `blog/synthesizer.py`
- Publishes via `blog/publishers/` (fan-out to multiple platforms)
- Tracks state via `blog/state.py` (avoids re-generating existing posts)

### Intake Pipeline
- Fan-in: 8 source parsers -> canonical ContentItem
- Enrichment: full-text extraction, auto-tagging, entity extraction
- Optional: sentence-transformer embeddings + pgvector store
- Synthesis: LLM daily digest
- Fan-out: publishers (obsidian, ghost, postiz)

## Conventions

- **Python 3.11+**, managed with `uv`
- **Pydantic v2** for all models and validation
- **Typer** for CLI (app instance in `cli.py`)
- **Strict mypy** type checking
- **ruff** for linting and formatting (line length 100)
- Test files mirror source structure: `src/.../foo.py` -> `tests/.../test_foo.py`
- Optional deps: try/except with `_HAS_X` flag, define name in except block
- Coverage target: 90%+

## Known Issues

- `test_verify_all_kpis.py` depends on local data files and may fail in clean clones
