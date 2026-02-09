# Contributing to Distill

Thanks for your interest in contributing to Distill!

## Development Setup

```bash
# Clone the repo
git clone https://github.com/nikspatel007/distill.git
cd distill

# Install dependencies (requires uv: https://docs.astral.sh/uv/)
uv sync --all-extras

# Run tests
uv run pytest tests/ -x -q

# Lint and format
uv run ruff check src/ && uv run ruff format src/

# Type checking
uv run mypy src/ --no-error-summary
```

## Project Structure

```
src/                    # Source code (flat layout, import as distill.*)
  parsers/              # Session parsers (Claude, Codex, VerMAS)
  journal/              # Journal synthesis pipeline
  blog/                 # Blog generation + multi-platform publishing
    publishers/         # Output format publishers (obsidian, ghost, postiz, social)
  intake/               # Content ingestion (RSS, browser, social)
    parsers/            # Content source parsers
    publishers/         # Intake output publishers
  integrations/         # External service integrations (Postiz, Ghost)
  cli.py                # CLI entry point (Typer)
  config.py             # Unified config (.distill.toml + env vars)
  core.py               # Pipeline orchestration
  editorial.py          # Editorial notes store
  memory.py             # Unified cross-pipeline memory
  store.py              # Content store (JSON or pgvector)
tests/                  # Tests mirror source structure
```

## Code Style

- **Python 3.11+** with type hints throughout
- **Pydantic v2** for all models and config
- **ruff** for linting and formatting (line length 100)
- **mypy** strict mode for type checking
- Test files mirror source: `src/blog/foo.py` -> `tests/blog/test_foo.py`

## Making Changes

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Add tests for new functionality
4. Ensure all checks pass:
   ```bash
   uv run pytest tests/ -x -q
   uv run ruff check src/
   uv run ruff format --check src/
   ```
5. Open a pull request

## Adding a New Content Source (Parser)

1. Create `src/intake/parsers/your_source.py` implementing `ContentParser`
2. Add your source to `ContentSource` enum in `src/intake/models.py`
3. Add config model to `src/intake/config.py`
4. Register in `src/intake/parsers/__init__.py`
5. Add CLI flags in `src/cli.py` if needed
6. Write tests in `tests/intake/test_your_source_parser.py`

## Adding a New Publisher

1. Create `src/blog/publishers/your_platform.py` implementing `BlogPublisher`
2. Add to `Platform` enum in `src/blog/config.py`
3. Register in `src/blog/publishers/__init__.py`
4. Write tests in `tests/blog/test_your_platform.py`

## Adding Project Context

Project descriptions live in `.distill.toml` under `[[projects]]`. These are injected into all LLM prompts (journal, blog, social) so the AI can properly describe what each project does. See `src/config.py:ProjectConfig` for the model.

## Adding Editorial Notes

Editorial notes are managed by `src/editorial.py:EditorialStore`. They follow the same JSON-backed pattern as seed ideas (`src/intake/seeds.py`). Notes can target a specific week (`week:2026-W06`), theme (`theme:multi-agent`), or apply globally (empty target).

## Conventions

- Optional dependencies use try/except with `_HAS_X` flags (always define the name in the except block so `@patch()` works in tests)
- LLM calls go through `claude -p` subprocess (not API directly)
- All secrets come from environment variables, never hardcoded
- Configuration: `.distill.toml` < env vars < CLI flags
- Test coverage target: 90%+
- **Port convention**: API server on 4321, Vite dev on 5173, tests on 3001. Never introduce new ports.
- CLI tests must set `NO_COLOR=1` (and remove `FORCE_COLOR`) to avoid ANSI codes breaking assertions

## Reporting Issues

Open an issue on GitHub with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Python version and OS
