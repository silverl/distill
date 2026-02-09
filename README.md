# Distill

Distill raw AI coding sessions into journals, blogs, and multi-platform publications.

Distill reads session data from AI coding assistants (Claude, Codex, VerMAS), ingests content from RSS feeds, browser history, and social platforms, then synthesizes everything into publishable content using Claude LLM.

## What It Does

```
Raw sessions (.claude/, .codex/)     External content (RSS, browser, social)
              \                              /
               \                            /
            ┌──────────────────────────────────┐
            │         distill run              │
            │                                  │
            │  1. Parse sessions               │
            │  2. Generate journal entries      │
            │  3. Ingest external content       │
            │  4. Synthesize daily digest       │
            │  5. Generate blog posts           │
            │  6. Publish everywhere            │
            └──────────────────────────────────┘
                           |
              ┌────────────┼────────────┐
              ▼            ▼            ▼
          Obsidian       Ghost      Social
          (local)     (newsletter)  (drafts)
```

**Pipeline steps:**

1. **Analyze** -- Parse sessions, compute statistics, detect patterns
2. **Journal** -- Synthesize daily journal entries from raw sessions via LLM
3. **Intake** -- Ingest RSS feeds, browser history, social saves into a daily digest
4. **Blog** -- Generate weekly synthesis posts and thematic deep-dives
5. **Publish** -- Distribute to Obsidian, Ghost CMS, Twitter/X, LinkedIn, Reddit via Postiz

## Quickstart

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) (`claude` command) for LLM synthesis

### Install

```bash
git clone https://github.com/nikspatel007/distill.git
cd distill
uv sync
```

For optional sources (Reddit, YouTube, Gmail):
```bash
uv sync --extra reddit        # Reddit saved/upvoted
uv sync --extra google         # YouTube + Gmail
uv sync --all-extras           # Everything
```

### First Run

```bash
# Analyze your AI coding sessions (no LLM needed)
distill analyze --dir . --output ./insights --global

# Generate a journal entry for today
distill journal --dir . --output ./insights --global

# Ingest RSS feeds and generate a daily digest
distill intake --output ./insights --use-defaults

# Run the full pipeline (sessions + intake + blog)
distill run --dir . --output ./insights --use-defaults
```

### Daily Automation

Run the full pipeline automatically every morning:

**macOS (launchd):**
```bash
# Edit the plist with your paths
cp scripts/daily-intake.sh ~/distill-daily.sh
# Set environment variables or edit the script:
export DISTILL_PROJECT_DIR="$HOME/distill"
export DISTILL_OUTPUT_DIR="$HOME/Documents/Obsidian Vault"
```

See `scripts/daily-intake.sh` for a ready-to-use template.

**Linux (cron):**
```bash
# Run at 7am daily
0 7 * * * cd ~/distill && uv run python -m distill run --dir $HOME --output ~/insights --use-defaults
```

## Commands

| Command | Description |
|---------|-------------|
| `distill analyze` | Parse sessions, compute stats, generate Obsidian notes |
| `distill journal` | Synthesize daily journal entries via LLM |
| `distill blog` | Generate blog posts from journal entries |
| `distill intake` | Ingest external content (RSS, browser, social) |
| `distill run` | Full pipeline: sessions + journal + intake + blog |
| `distill seed` | Add a seed idea for future content |
| `distill seeds` | List pending seed ideas |
| `distill note` | Add an editorial note to steer content focus |
| `distill notes` | List active editorial notes |
| `distill status` | Show pipeline state (last run, counts, configured sources) |
| `distill sessions` | List discovered sessions as JSON |

Run `distill <command> --help` for detailed options.

## Content Sources

### Session Sources

| Source | Location | What It Captures |
|--------|----------|------------------|
| Claude | `~/.claude/projects/*/` | Claude Code session JSONL files |
| Codex | `.codex/sessions/` | Codex CLI session rollouts |
| VerMAS | `.vermas/state/` | Multi-agent workflow executions |

### Intake Sources

| Source | Flag / Config | What It Captures |
|--------|---------------|------------------|
| RSS | `--use-defaults` or `--feeds-file` | 90+ curated tech blogs, or your own feeds |
| Browser | `--browser-history` | Chrome and Safari browsing history |
| Substack | `--substack-blogs URL,URL` | Substack newsletter feeds |
| Reddit | `--reddit-user NAME` | Saved and upvoted posts (requires API creds) |
| YouTube | `--youtube-api-key KEY` | Watch history + transcripts |
| Gmail | `--gmail-credentials FILE` | Newsletter emails (via Google OAuth) |
| LinkedIn | `--linkedin-export DIR` | GDPR data export (shares, articles, saved) |
| Twitter/X | `--twitter-export DIR` | Data export + nitter RSS feeds |

## Configuration

Distill can be configured through a `.distill.toml` file, environment variables, or CLI flags. Settings are applied in order: defaults < TOML file < env vars < CLI flags.

### Config File (`.distill.toml`)

Place a `.distill.toml` file in your project root or at `~/.config/distill/config.toml`. This is the recommended way to configure Distill for repeated use.

```toml
[output]
directory = "./insights"

[sessions]
sources = ["claude", "codex", "vermas"]
include_global = false
since_days = 2

[journal]
style = "dev-journal"          # dev-journal, tech-blog, team-update, building-in-public
target_word_count = 600
# model = "claude-sonnet-4-5-20250929"   # override LLM model

[blog]
target_word_count = 1200
include_diagrams = true
platforms = ["obsidian"]       # obsidian, ghost, markdown, twitter, linkedin, reddit

[intake]
use_defaults = true            # use built-in 90+ RSS feeds
# feeds_file = "my-feeds.txt"
# opml_file = "subscriptions.opml"
browser_history = false
# substack_blogs = ["https://example.substack.com"]

# ─── Project Descriptions ─────────────────────────────────────────
# These get injected into LLM prompts so the AI knows what each
# project is when writing about your sessions. Without this, the
# LLM sees names like "vermas" but can't describe what they do.

[[projects]]
name = "VerMAS"
description = "Multi-agent orchestration platform where AI agents collaborate through structured meetings and workflows."
url = "https://github.com/user/vermas"
tags = ["multi-agent", "orchestration"]

[[projects]]
name = "Distill"
description = "Content pipeline that transforms AI coding sessions into publishable content across platforms."
tags = ["content-pipeline", "AI"]

# ─── Ghost CMS (newsletter) ───────────────────────────────────────
# [ghost]
# url = "https://your-ghost-instance.com"
# admin_api_key = "your-key-id:your-secret"
# newsletter_slug = "your-newsletter"

# ─── Postiz (social media scheduling) ─────────────────────────────
# [postiz]
# url = "https://localhost:6106/api/public/v1"
# api_key = "your-postiz-key"
# schedule_enabled = true
# timezone = "America/New_York"

# ─── Reddit API (content ingestion) ───────────────────────────────
# [reddit]
# client_id = "your-client-id"
# client_secret = "your-client-secret"
# username = "your-username"

# ─── YouTube API ──────────────────────────────────────────────────
# [youtube]
# api_key = "your-api-key"
```

### Environment Variables

All optional. Copy `.env.example` to `.env` and fill in what you need.

| Variable | Purpose |
|----------|---------|
| `GHOST_URL` | Ghost CMS instance URL |
| `GHOST_ADMIN_API_KEY` | Ghost Admin API key (`id:secret` format) |
| `GHOST_NEWSLETTER_SLUG` | Ghost newsletter for auto-send |
| `REDDIT_CLIENT_ID` | Reddit API app client ID |
| `REDDIT_CLIENT_SECRET` | Reddit API app secret |
| `REDDIT_USERNAME` | Reddit username |
| `YOUTUBE_API_KEY` | YouTube Data API key |
| `POSTIZ_URL` | Postiz API URL |
| `POSTIZ_API_KEY` | Postiz API key |
| `DISTILL_MODEL` | Override LLM model for all synthesis |

### Publishing Platforms

Use `--publish` to target platforms (comma-separated):

```bash
# Publish to Obsidian (default)
distill blog --output ./insights --publish obsidian

# Publish to multiple platforms
distill blog --output ./insights --publish obsidian,ghost,markdown

# Social media content generation (via Postiz)
distill blog --output ./insights --publish postiz
```

| Platform | Output |
|----------|--------|
| `obsidian` | Obsidian-compatible markdown with wiki links and frontmatter |
| `ghost` | Ghost CMS markdown (publishes via API if configured) |
| `markdown` | Plain markdown with relative links |
| `twitter` | Thread format (5-8 tweets) |
| `linkedin` | Professional post with engagement hooks |
| `reddit` | Discussion post with TL;DR |
| `postiz` | Pushes drafts to Postiz for review/scheduling across all connected platforms |

### Seed Ideas

Drop raw thoughts that get woven into your daily digest and blog posts:

```bash
distill seed "AI agents are the new APIs"
distill seed "The cost of context switching in deep work" --tags "productivity,focus"
distill seeds              # List pending seeds
distill seeds --all        # Include used seeds
```

### Editorial Notes

Steer what the LLM emphasizes in generated content. Notes can target a specific week, theme, or apply globally:

```bash
# Global note (applies to all content)
distill note "Emphasize the fan-in architecture pattern"

# Target a specific week
distill note "Highlight the VerMAS agent spawning milestone" --target "week:2026-W06"

# Target a theme
distill note "Focus on testing strategies" --target "theme:testing-patterns"

# List active notes
distill notes

# List all notes (including used)
distill notes --all
```

Editorial notes are consumed during blog generation and included in LLM prompts alongside project context.

## Output Structure

After running `distill run`, your output directory looks like:

```
insights/
  journal/                    # Daily journal entries
    journal-2026-02-08.md
  blog/                       # Blog posts
    obsidian/                  # Obsidian-formatted posts
      weekly-2026-W06.md
      content-pipeline.md     # Thematic deep-dive
    ghost/                     # Ghost CMS formatted
    reading-list/              # Weekly reading list posts
  intake/                      # Daily research digests
    obsidian/
      digest-2026-02-08.md
    archive/                   # Raw ingested items
  sessions/                    # Individual session notes
  daily/                       # Daily session summaries
  projects/                    # Per-project notes
  weekly/                      # Weekly session digests
```

## Project Structure

```
src/
  analyzers/           # Pattern detection from session data
  blog/                # Blog synthesis pipeline
    publishers/        # Multi-platform output (obsidian, ghost, postiz, social)
  formatters/          # Output formatters (Obsidian, project notes, weekly)
  intake/              # Content ingestion pipeline
    parsers/           # Source parsers (RSS, browser, social platforms)
    publishers/        # Intake output publishers
  integrations/        # External service integrations (Postiz, Ghost)
  journal/             # Journal synthesis pipeline
  parsers/             # Session parsers (Claude, Codex, VerMAS)
  cli.py               # CLI entry point (Typer)
  config.py            # Unified config (.distill.toml loader)
  core.py              # Pipeline orchestration
  editorial.py         # Editorial notes store
  memory.py            # Unified cross-pipeline memory
  store.py             # Content store (JSON or pgvector)
  embeddings.py        # Sentence-transformer embeddings (optional)
tests/                 # 1700+ tests
scripts/               # Automation templates
```

## How It Works

### Pipeline Architecture

Distill follows a **fan-in / fan-out** pattern:

**Fan-in:** Multiple sources (sessions, RSS, browser history, social platforms) are parsed into a canonical `ContentItem` model. Each source has its own parser implementing the `ContentParser` interface.

**Processing:** Items go through enrichment (full-text extraction, auto-tagging), intelligence (LLM-based entity extraction and classification), and optional embedding for similarity search.

**Synthesis:** Enriched items are compressed into structured context (`DailyContext`, `WeeklyBlogContext`, etc.) and sent to Claude for narrative prose generation.

**Fan-out:** Generated prose is formatted for each target platform through `BlogPublisher` implementations. Each publisher adapts the canonical prose to platform-specific conventions (wiki links for Obsidian, API calls for Ghost, thread format for Twitter).

### Memory System

Distill maintains continuity across runs through several memory layers:

- **Working Memory** -- Rolling window of recent themes, threads, and insights (7-day default)
- **Blog Memory** -- Tracks previously published posts to avoid repetition and enable cross-referencing
- **Unified Memory** -- Merges all memory sources into a single store with entity tracking and trend detection
- **Content Store** -- Embedded items for semantic similarity search (optional, uses sentence-transformers)

### LLM Integration

All LLM calls go through the Claude CLI (`claude -p`) as a subprocess. This keeps the codebase free of API key management and lets you use whatever Claude model your CLI is configured with. Override with `--model` or `DISTILL_MODEL` env var.

### Project Context

When you define projects in `.distill.toml`, their descriptions are injected into every LLM prompt. This means when the LLM writes about a session in "vermas", it knows VerMAS is a multi-agent orchestration platform -- not just an opaque project name.

## Development

```bash
# Install with dev dependencies
uv sync --all-extras

# Run tests
uv run pytest tests/ -x -q

# Lint and format
uv run ruff check src/ && uv run ruff format src/

# Type checking
uv run mypy src/ --no-error-summary
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## Troubleshooting

**Claude CLI not found**: Distill calls `claude -p` for LLM synthesis. Install from [Claude Code docs](https://docs.anthropic.com/en/docs/claude-code). The `analyze` and `intake` commands work without it (no LLM needed for parsing).

**Running a subset of tests**: Some tests depend on local data or optional dependencies:
```bash
# Skip data-dependent tests
uv run pytest tests/ -x -q --ignore=tests/test_verify_all_kpis.py

# Run only blog tests
uv run pytest tests/blog/ -x -q
```

**mypy shows cascading errors**: The flat source layout (`src/` mapped to `distill` via setuptools) prevents mypy from resolving internal imports. The `pyproject.toml` configuration suppresses these false positives. All imports resolve correctly at runtime.

## License

[MIT](LICENSE)
