# Changelog

All notable changes to this project will be documented in this file.

## [0.5.0] - 2026-02-08

### Added

- **Unified pipeline** (`distill run`): single command orchestrates sessions, journal, intake, and blog
- **Multi-source intake**: RSS, browser history, Substack, LinkedIn, Twitter/X, Reddit, YouTube, Gmail parsers
- **Seed ideas**: `distill seed` / `distill seeds` for capturing raw thoughts that feed into content
- **Editorial notes**: `distill note` / `distill notes` for steering LLM content focus per-week or per-theme
- **Project context**: `[[projects]]` in `.distill.toml` injects project descriptions into all LLM prompts
- **Postiz integration**: social media scheduling via self-hosted Postiz (Twitter/X, LinkedIn, Reddit, Bluesky, Mastodon)
- **Ghost CMS publisher**: newsletter publishing via Ghost Admin API
- **Multi-platform blog publishing**: obsidian, ghost, markdown, twitter, linkedin, reddit publishers
- **Unified memory**: cross-pipeline memory with entity tracking, trend detection, and migration from legacy stores
- **Vector store**: optional pgvector + sentence-transformers for semantic similarity search
- **Intelligence pipeline**: LLM-based entity extraction and content classification
- **Blog prompt engineering**: essay-style structure, example dedup via BlogMemory, reader context bridging
- **CI pipeline**: GitHub Actions with lint, format, type check, tests across Python 3.11-3.13 on Ubuntu + macOS

### Changed

- Configuration unified under `.distill.toml` with env var and CLI flag overlays
- Blog synthesis uses three-layer prompt improvement (structure, dedup, bridging)
- Session parsers wrapped as intake sources via `SessionParser`

### Fixed

- mypy configuration for flat source layout (src/ -> distill)
- ruff lint and format compliance across all source files
- GitHub URLs corrected in project metadata and documentation
