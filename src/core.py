"""Core analysis pipeline for session insights."""

import logging
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from distill.formatters.project import (
    ProjectFormatter,
    group_sessions_by_project,
)
from distill.formatters.weekly import (
    WeeklyDigestFormatter,
    group_sessions_by_week,
)
from distill.parsers import ClaudeParser, CodexParser, VermasParser
from distill.parsers.models import BaseSession


class SessionStats(BaseModel):
    """Statistics about analyzed sessions."""

    total_sessions: int = 0
    total_duration_minutes: float = 0.0
    sources: dict[str, int] = Field(default_factory=dict)
    tools_used: dict[str, int] = Field(default_factory=dict)
    date_range: tuple[datetime, datetime] | None = None
    content_richness_score: float = 0.0
    field_coverage: dict[str, float] = Field(default_factory=dict)


class SessionPattern(BaseModel):
    """Detected patterns in sessions."""

    name: str
    description: str
    occurrences: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    """Result of analyzing a collection of sessions."""

    sessions: list[BaseSession] = Field(default_factory=list)
    stats: SessionStats = Field(default_factory=SessionStats)
    patterns: list[SessionPattern] = Field(default_factory=list)


# Known source directory names
SOURCE_DIRECTORIES: dict[str, str] = {
    "claude": ".claude",
    "codex": ".codex",
    "vermas": ".vermas",
}


def discover_source_roots(
    directory: Path,
    sources: list[str] | None = None,
) -> dict[str, Path]:
    """Find root directories for each source type.

    Args:
        directory: Root directory to scan.
        sources: Filter to specific sources. If None, discover all.

    Returns:
        Dictionary mapping source name to root directory path.
    """
    if sources is None:
        sources = list(SOURCE_DIRECTORIES.keys())

    roots: dict[str, Path] = {}

    for source in sources:
        if source not in SOURCE_DIRECTORIES:
            continue

        source_dir = directory / SOURCE_DIRECTORIES[source]
        if source_dir.exists() and source_dir.is_dir():
            roots[source] = source_dir

    return roots


def discover_sessions(
    directory: Path,
    sources: list[str] | None = None,
    include_home: bool = False,
) -> dict[str, list[Path]]:
    """Discover session directories/roots in a directory.

    This is a compatibility wrapper that returns source roots as single-item lists.
    Prefer using discover_source_roots() for new code.

    Args:
        directory: Root directory to scan.
        sources: Filter to specific sources. If None, discover all.
        include_home: Also scan home directory (~/.claude, ~/.codex, ~/.vermas).

    Returns:
        Dictionary mapping source name to list containing the source root path.
    """
    roots = discover_source_roots(directory, sources)
    result: dict[str, list[Path]] = {source: [path] for source, path in roots.items()}

    if include_home:
        home = Path.home()
        if home != directory:
            home_roots = discover_source_roots(home, sources)
            for source, path in home_roots.items():
                if source in result:
                    if path not in result[source]:
                        result[source].append(path)
                else:
                    result[source] = [path]

    return result


def parse_sessions(root: Path, source: str) -> list[BaseSession]:
    """Parse sessions from a source root directory.

    Dispatches to the appropriate parser based on source type.

    Args:
        root: Root directory for the source (e.g., .claude, .codex, .vermas).
        source: The source type (claude, codex, vermas).

    Returns:
        List of parsed sessions.
    """
    from distill.narrative import enrich_narrative

    sessions: list[BaseSession] = []
    if source == "claude":
        parser = ClaudeParser()
        sessions = list(parser.parse_directory(root))
    elif source == "codex":
        parser = CodexParser()
        sessions = list(parser.parse_directory(root))
    elif source == "vermas":
        parser = VermasParser()
        sessions = list(parser.parse_directory(root))

    # Enrich narratives for all sessions
    for session in sessions:
        enrich_narrative(session)

    return sessions


def parse_session_file(path: Path, source: str) -> list[BaseSession]:
    """Parse sessions from a path.

    This is a compatibility wrapper. For source directories, it dispatches
    to the appropriate parser. Prefer using parse_sessions() for new code.

    Args:
        path: Path to a source directory or file.
        source: The source type (claude, codex, vermas).

    Returns:
        List of parsed sessions.
    """
    # If path is a directory, use the new parser-based approach
    if path.is_dir():
        return parse_sessions(path, source)

    # For files, try to find the parent source directory
    # and use the appropriate parser
    parent = path.parent
    if source == "claude":
        # Walk up to find .claude directory
        for p in [parent] + list(parent.parents):
            if p.name == ".claude" or (p / ".claude").exists():
                return parse_sessions(p if p.name == ".claude" else p / ".claude", source)
    elif source == "codex":
        for p in [parent] + list(parent.parents):
            if p.name == ".codex" or (p / ".codex").exists():
                return parse_sessions(p if p.name == ".codex" else p / ".codex", source)
    elif source == "vermas":
        for p in [parent] + list(parent.parents):
            if p.name == ".vermas" or (p / ".vermas").exists():
                return parse_sessions(p if p.name == ".vermas" else p / ".vermas", source)

    return []


def analyze(sessions: list[BaseSession]) -> AnalysisResult:
    """Analyze a collection of sessions.

    Args:
        sessions: List of sessions to analyze.

    Returns:
        Analysis result with statistics and patterns.
    """
    if not sessions:
        return AnalysisResult()

    # Calculate statistics
    stats = _calculate_stats(sessions)

    # Detect patterns
    patterns = _detect_patterns(sessions)

    return AnalysisResult(
        sessions=sessions,
        stats=stats,
        patterns=patterns,
    )


def generate_project_notes(
    sessions: list[BaseSession],
    output_dir: Path,
) -> list[Path]:
    """Generate per-project Obsidian notes from analyzed sessions.

    Groups sessions by project, generates a markdown note for each real
    project (excluding '(unknown)' and '(unassigned)'), and writes them
    to output_dir/projects/.

    Args:
        sessions: All parsed sessions.
        output_dir: Root output directory. Notes go in output_dir/projects/.

    Returns:
        List of written project note file paths.
    """
    projects_dir = output_dir / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    groups = group_sessions_by_project(sessions)
    formatter = ProjectFormatter()
    written: list[Path] = []

    for project_name, project_sessions in groups.items():
        if project_name in ("(unknown)", "(unassigned)"):
            continue
        note_content = formatter.format_project_note(project_name, project_sessions)
        note_name = formatter.note_name(project_name)
        note_path = projects_dir / f"{note_name}.md"
        note_path.write_text(note_content, encoding="utf-8")
        written.append(note_path)

    return written


def generate_weekly_notes(
    sessions: list[BaseSession],
    output_dir: Path,
) -> list[Path]:
    """Generate per-week digest notes from analyzed sessions.

    Groups sessions by ISO week, generates a markdown digest for each
    week, and writes them to output_dir/weekly/.

    Args:
        sessions: All parsed sessions.
        output_dir: Root output directory. Notes go in output_dir/weekly/.

    Returns:
        List of written weekly digest file paths.
    """
    weekly_dir = output_dir / "weekly"
    weekly_dir.mkdir(parents=True, exist_ok=True)

    groups = group_sessions_by_week(sessions)
    formatter = WeeklyDigestFormatter()
    written: list[Path] = []

    for (iso_year, iso_week), week_sessions in groups.items():
        content = formatter.format_weekly_digest(iso_year, iso_week, week_sessions)
        name = formatter.note_name(iso_year, iso_week)
        note_path = weekly_dir / f"{name}.md"
        note_path.write_text(content, encoding="utf-8")
        written.append(note_path)

    return written


# Fields checked for content richness / field coverage
_RICHNESS_FIELDS: list[str] = [
    "summary",
    "messages",
    "tools_used",
    "outcomes",
    "tags",
    "end_time",
]


def compute_richness_score(session: BaseSession) -> float:
    """Compute a content richness score for a single session.

    The score ranges from 0.0 to 1.0 and measures how many key fields
    are populated with meaningful data.

    Args:
        session: The session to score.

    Returns:
        A float between 0.0 and 1.0.
    """
    filled = 0
    total = len(_RICHNESS_FIELDS)

    for field in _RICHNESS_FIELDS:
        value = getattr(session, field, None)
        if value is None:
            continue
        # For strings, check non-empty
        if (
            isinstance(value, str)
            and value
            or isinstance(value, list)
            and len(value) > 0
            or isinstance(value, datetime)
        ):
            filled += 1

    return filled / total if total > 0 else 0.0


def compute_field_coverage(sessions: list[BaseSession]) -> dict[str, float]:
    """Compute per-field coverage across all sessions.

    For each richness field, returns the fraction of sessions where
    that field is populated.

    Args:
        sessions: List of sessions to evaluate.

    Returns:
        Dictionary mapping field name to coverage fraction (0.0 to 1.0).
    """
    if not sessions:
        return dict.fromkeys(_RICHNESS_FIELDS, 0.0)

    coverage: dict[str, int] = dict.fromkeys(_RICHNESS_FIELDS, 0)

    for session in sessions:
        for field in _RICHNESS_FIELDS:
            value = getattr(session, field, None)
            if value is None:
                continue
            if (
                isinstance(value, str)
                and value
                or isinstance(value, list)
                and len(value) > 0
                or isinstance(value, datetime)
            ):
                coverage[field] += 1

    n = len(sessions)
    return {field: count / n for field, count in coverage.items()}


def _calculate_stats(sessions: list[BaseSession]) -> SessionStats:
    """Calculate statistics from sessions."""
    total_duration = sum(s.duration_minutes or 0 for s in sessions)

    # Count by source
    sources: Counter[str] = Counter(s.source for s in sessions)

    # Count tools
    tools: Counter[str] = Counter()
    for session in sessions:
        for tool in session.tools_used:
            tools[tool.name] += tool.count

    # Date range
    times = [s.start_time for s in sessions]
    date_range = (min(times), max(times)) if times else None

    # Content richness and field coverage
    richness_scores = [compute_richness_score(s) for s in sessions]
    avg_richness = sum(richness_scores) / len(richness_scores) if richness_scores else 0.0
    field_cov = compute_field_coverage(sessions)

    return SessionStats(
        total_sessions=len(sessions),
        total_duration_minutes=total_duration,
        sources=dict(sources),
        tools_used=dict(tools),
        date_range=date_range,
        content_richness_score=round(avg_richness, 3),
        field_coverage=field_cov,
    )


def _detect_patterns(sessions: list[BaseSession]) -> list[SessionPattern]:
    """Detect patterns in sessions."""
    patterns: list[SessionPattern] = []

    if len(sessions) < 2:
        return patterns

    # Pattern: Peak hours
    hours: Counter[int] = Counter(s.start_time.hour for s in sessions)
    if hours:
        peak_hour = hours.most_common(1)[0]
        patterns.append(
            SessionPattern(
                name="peak_activity_hour",
                description=f"Most sessions occur at {peak_hour[0]}:00",
                occurrences=peak_hour[1],
                metadata={"hour": peak_hour[0]},
            )
        )

    # Pattern: Common tools
    tools: Counter[str] = Counter()
    for session in sessions:
        for tool in session.tools_used:
            tools[tool.name] += tool.count

    if tools:
        top_tools = tools.most_common(3)
        patterns.append(
            SessionPattern(
                name="frequent_tools",
                description=f"Most used tools: {', '.join(t[0] for t in top_tools)}",
                occurrences=sum(t[1] for t in top_tools),
                metadata={"tools": dict(top_tools)},
            )
        )

    # Pattern: Session frequency by day of week
    days: Counter[int] = Counter(s.start_time.weekday() for s in sessions)
    if days:
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        peak_day = days.most_common(1)[0]
        patterns.append(
            SessionPattern(
                name="peak_activity_day",
                description=f"Most active day: {day_names[peak_day[0]]}",
                occurrences=peak_day[1],
                metadata={"day": peak_day[0], "day_name": day_names[peak_day[0]]},
            )
        )

    return patterns


def generate_journal_notes(
    sessions: list[BaseSession],
    output_dir: Path,
    *,
    target_dates: list[date] | None = None,
    style: str = "dev-journal",
    target_word_count: int = 600,
    force: bool = False,
    dry_run: bool = False,
    model: str | None = None,
) -> list[Path]:
    """Generate journal entries from sessions using LLM synthesis.

    Args:
        sessions: All parsed sessions.
        output_dir: Root output directory. Notes go in output_dir/journal/.
        target_dates: Dates to generate for. If None, generates for all dates.
        style: Journal style name (dev-journal, tech-blog, etc.).
        target_word_count: Target word count for each entry.
        force: Bypass cache and regenerate.
        dry_run: Print context without calling LLM.
        model: Optional Claude model override.

    Returns:
        List of written journal file paths.
    """
    from distill.journal.cache import JournalCache
    from distill.journal.config import JournalConfig, JournalStyle
    from distill.journal.context import prepare_daily_context
    from distill.journal.formatter import JournalFormatter
    from distill.journal.memory import load_memory, save_memory
    from distill.journal.synthesizer import JournalSynthesizer

    config = JournalConfig(
        style=JournalStyle(style),
        target_word_count=target_word_count,
        model=model,
    )
    cache = JournalCache(output_dir)
    synthesizer = JournalSynthesizer(config)
    formatter = JournalFormatter(config)

    # Determine target dates
    if target_dates is None:
        all_dates: set[date] = {s.start_time.date() for s in sessions}
        target_dates = sorted(all_dates)

    written: list[Path] = []
    memory = load_memory(output_dir)

    for target_date in target_dates:
        day_sessions = [s for s in sessions if s.start_time.date() == target_date]
        if not day_sessions:
            continue

        # Check cache
        if not force and cache.is_generated(target_date, config.style, len(day_sessions)):
            continue

        context = prepare_daily_context(day_sessions, target_date, config)
        context.previous_context = memory.render_for_prompt()

        if dry_run:
            # Dry run prints context and skips LLM
            print(context.render_text())
            print("---")
            continue

        prose = synthesizer.synthesize(context)

        # Extract memory from prose (second LLM call)
        try:
            daily_entry, threads = synthesizer.extract_memory(prose, target_date)
            memory.add_entry(daily_entry)
            memory.update_threads(threads)
            memory.prune(config.memory_window_days)
            save_memory(memory, output_dir)
        except Exception:
            logger.warning(
                "Memory extraction failed for %s, continuing without update",
                target_date,
                exc_info=True,
            )

        markdown = formatter.format_entry(context, prose)

        out_path = formatter.output_path(output_dir, context)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")

        cache.mark_generated(target_date, config.style, len(day_sessions))
        written.append(out_path)

    return written


def generate_blog_posts(
    output_dir: Path,
    *,
    post_type: str = "all",
    target_week: str | None = None,
    target_theme: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    include_diagrams: bool = True,
    model: str | None = None,
    target_word_count: int = 1200,
    platforms: list[str] | None = None,
    ghost_config: Any | None = None,
) -> list[Path]:
    """Generate blog posts from existing journal entries.

    Reads journal markdown files and working memory, then synthesizes
    weekly synthesis posts and/or thematic deep-dives.

    Args:
        output_dir: Root output directory (contains journal/ and blog/).
        post_type: "weekly", "thematic", or "all".
        target_week: Specific week like "2026-W06" (weekly only).
        target_theme: Specific theme slug (thematic only).
        force: Bypass state check and regenerate.
        dry_run: Print context without calling LLM.
        include_diagrams: Whether to include Mermaid diagrams.
        model: Optional Claude model override.
        target_word_count: Target word count for posts.
        platforms: List of platform names to publish to. Defaults to ["obsidian"].
        ghost_config: Optional GhostConfig for live Ghost CMS publishing.

    Returns:
        List of written blog post file paths.
    """
    from distill.blog.blog_memory import load_blog_memory, save_blog_memory
    from distill.blog.config import BlogConfig, Platform
    from distill.blog.publishers import create_publisher
    from distill.blog.reader import JournalReader
    from distill.blog.state import (
        BlogState,
        load_blog_state,
        save_blog_state,
    )
    from distill.blog.synthesizer import BlogSynthesizer
    from distill.journal.memory import load_memory

    if platforms is None:
        platforms = ["obsidian"]

    config = BlogConfig(
        target_word_count=target_word_count,
        include_diagrams=include_diagrams,
        model=model,
    )
    reader = JournalReader()
    synthesizer = BlogSynthesizer(config)

    # 1. Read all journal entries
    journal_dir = output_dir / "journal"
    entries = reader.read_all(journal_dir)
    if not entries:
        return []

    # 2. Load working memory, blog state, and blog memory
    memory = load_memory(output_dir)
    state = load_blog_state(output_dir) if not force else BlogState()
    blog_memory = load_blog_memory(output_dir)

    written: list[Path] = []

    # 3. Weekly posts
    if post_type in ("weekly", "all"):
        written.extend(
            _generate_weekly_posts(
                entries=entries,
                memory=memory,
                state=state,
                config=config,
                synthesizer=synthesizer,
                output_dir=output_dir,
                target_week=target_week,
                force=force,
                dry_run=dry_run,
                platforms=platforms,
                blog_memory=blog_memory,
                ghost_config=ghost_config,
            )
        )

    # 4. Thematic posts
    if post_type in ("thematic", "all"):
        written.extend(
            _generate_thematic_posts(
                entries=entries,
                memory=memory,
                state=state,
                config=config,
                synthesizer=synthesizer,
                output_dir=output_dir,
                target_theme=target_theme,
                force=force,
                dry_run=dry_run,
                platforms=platforms,
                blog_memory=blog_memory,
                ghost_config=ghost_config,
            )
        )

    # 5. Save state, blog memory, and regenerate indexes
    if not dry_run:
        save_blog_state(state, output_dir)
        save_blog_memory(blog_memory, output_dir)
        # Generate index for each file publisher
        for platform_name in platforms:
            try:
                p = Platform(platform_name)
                publisher = create_publisher(
                    p, synthesizer=synthesizer, ghost_config=ghost_config
                )
                if not publisher.requires_llm:
                    idx_content = publisher.format_index(output_dir, state)
                    if idx_content:
                        idx_path = publisher.index_path(output_dir)
                        idx_path.parent.mkdir(parents=True, exist_ok=True)
                        idx_path.write_text(idx_content, encoding="utf-8")
            except (ValueError, Exception):
                pass

    return written


def _generate_weekly_posts(
    *,
    entries: list[Any],
    memory: Any,
    state: Any,
    config: Any,
    synthesizer: Any,
    output_dir: Path,
    target_week: str | None,
    force: bool,
    dry_run: bool,
    platforms: list[str],
    blog_memory: Any,
    ghost_config: Any | None = None,
) -> list[Path]:
    """Generate weekly synthesis blog posts."""
    from distill.blog.config import Platform
    from distill.blog.context import prepare_weekly_context
    from distill.blog.diagrams import clean_diagrams
    from distill.blog.publishers import create_publisher
    from distill.blog.state import BlogPostRecord

    written: list[Path] = []

    # Group entries by ISO week
    weeks: dict[tuple[int, int], list[Any]] = {}
    for entry in entries:
        iso = entry.date.isocalendar()
        key = (iso.year, iso.week)
        weeks.setdefault(key, []).append(entry)

    # Filter to target week if specified
    if target_week:
        parts = target_week.split("-W")
        if len(parts) == 2:
            try:
                tw_year, tw_week = int(parts[0]), int(parts[1])
                weeks = {k: v for k, v in weeks.items() if k == (tw_year, tw_week)}
            except ValueError:
                pass

    for (year, week), week_entries in sorted(weeks.items()):
        if len(week_entries) < 2:
            continue

        slug = f"weekly-{year}-W{week:02d}"
        if not force and state.is_generated(slug):
            continue

        context = prepare_weekly_context(week_entries, year, week, memory)

        if dry_run:
            print(f"[DRY RUN] Would generate: {slug}")
            print(f"  Entries: {len(week_entries)}, Sessions: {context.total_sessions}")
            print(f"  Projects: {', '.join(context.projects)}")
            print("---")
            continue

        memory_text = blog_memory.render_for_prompt()
        prose = synthesizer.synthesize_weekly(context, blog_memory=memory_text)
        if config.include_diagrams:
            prose = clean_diagrams(prose)

        # Extract blog memory from canonical prose
        try:
            title = f"Week {year}-W{week:02d}"
            summary = synthesizer.extract_blog_memory(prose, slug, title, "weekly")
            blog_memory.add_post(summary)
        except Exception:
            logger.warning("Blog memory extraction failed for %s", slug)

        # Publish to each platform
        for platform_name in platforms:
            try:
                p = Platform(platform_name)
                publisher = create_publisher(
                    p, synthesizer=synthesizer, ghost_config=ghost_config
                )
                content = publisher.format_weekly(context, prose)
                out_path = publisher.weekly_output_path(output_dir, year, week)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(content, encoding="utf-8")
                written.append(out_path)
                blog_memory.mark_published(slug, platform_name)
            except Exception:
                logger.warning("Failed to publish %s to %s", slug, platform_name, exc_info=True)

        state.mark_generated(
            BlogPostRecord(
                slug=slug,
                post_type="weekly",
                generated_at=datetime.now(),
                source_dates=[e.date for e in week_entries],
                file_path=str(out_path) if written else "",
            )
        )

    return written


def generate_intake(
    output_dir: Path,
    *,
    feed_urls: list[str] | None = None,
    feeds_file: str | None = None,
    opml_file: str | None = None,
    sources: list[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
    model: str | None = None,
    target_word_count: int = 800,
    publishers: list[str] | None = None,
) -> list[Path]:
    """Ingest content from configured sources and synthesize a daily digest.

    Args:
        output_dir: Root output directory (contains intake/).
        feed_urls: Explicit list of RSS feed URLs.
        feeds_file: Path to a newline-delimited feeds file.
        opml_file: Path to an OPML file with feed URLs.
        sources: List of source names to ingest (e.g. ["rss"]). None = all configured.
        force: Bypass state check and re-process.
        dry_run: Preview context without calling LLM.
        model: Optional Claude model override.
        target_word_count: Target word count for the digest.
        publishers: List of publisher names. Defaults to ["obsidian"].

    Returns:
        List of written output file paths.
    """
    from distill.intake.config import IntakeConfig, RSSConfig
    from distill.intake.context import prepare_daily_context
    from distill.intake.memory import load_intake_memory, save_intake_memory
    from distill.intake.models import ContentItem, ContentSource
    from distill.intake.parsers import create_parser
    from distill.intake.publishers import create_intake_publisher
    from distill.intake.state import (
        IntakeRecord,
        IntakeState,
        load_intake_state,
        save_intake_state,
    )
    from distill.intake.synthesizer import IntakeSynthesizer

    if publishers is None:
        publishers = ["obsidian"]

    # Build config
    rss_config = RSSConfig(
        feeds=feed_urls or [],
        feeds_file=feeds_file or "",
        opml_file=opml_file or "",
    )
    config = IntakeConfig(
        rss=rss_config,
        model=model,
        target_word_count=target_word_count,
    )

    # Determine which sources to run
    if sources is None:
        source_list = [ContentSource.RSS]
    else:
        source_list = [ContentSource(s) for s in sources]

    # Load state
    state = load_intake_state(output_dir) if not force else IntakeState()

    # Fan-in: collect from all configured sources
    all_items: list[ContentItem] = []
    for source in source_list:
        try:
            parser = create_parser(source, config=config)
        except ValueError:
            logger.info("No parser available for %s, skipping", source.value)
            continue
        if not parser.is_configured:
            logger.info("Skipping %s (not configured)", source.value)
            continue

        # When forcing, use epoch to bypass recency filter entirely
        since = state.last_run if not force else datetime(2000, 1, 1, tzinfo=timezone.utc)
        items = parser.parse(since=since)
        # Filter already-processed items
        new_items = [i for i in items if not state.is_processed(i.id)]
        all_items.extend(new_items)
        logger.info("Got %d new items from %s", len(new_items), source.value)

    if not all_items:
        logger.info("No new content items to process")
        return []

    # Enrich items: full-text extraction for short articles, then auto-tag
    from distill.intake.fulltext import enrich_items as enrich_fulltext
    from distill.intake.tagging import enrich_tags

    enrich_fulltext(all_items, min_word_threshold=100, max_concurrent=20)
    logger.info("Full-text enrichment complete")

    enrich_tags(all_items)
    logger.info("Auto-tagging complete")

    # Archive raw items after enrichment
    from distill.intake.archive import archive_items, build_daily_index

    archive_path = archive_items(all_items, output_dir)
    index_path = build_daily_index(all_items, output_dir)
    logger.info("Archived %d items", len(all_items))

    # Cluster items by topic for better LLM context
    from distill.intake.clustering import cluster_items, render_clustered_context

    clusters = cluster_items(all_items, max_clusters=8, min_cluster_size=2)
    if clusters:
        clustered_text = render_clustered_context(clusters, max_items_per_cluster=8)
        logger.info("Clustered %d items into %d topics", len(all_items), len(clusters))
    else:
        clustered_text = ""

    # Build context
    context = prepare_daily_context(all_items, clustered_text=clustered_text)

    if dry_run:
        print(f"[DRY RUN] Would synthesize intake digest for {context.date}")
        print(f"  Items: {context.total_items}")
        print(f"  Sources: {', '.join(context.sources)}")
        print(f"  Sites: {', '.join(context.sites[:10])}")
        print(f"  Word count: {context.total_word_count}")
        print("---")
        print(context.combined_text[:2000])
        return []

    # Synthesize
    memory = load_intake_memory(output_dir)
    memory_text = memory.render_for_prompt()

    synthesizer = IntakeSynthesizer(config)
    prose = synthesizer.synthesize_daily(context, memory_context=memory_text)

    # Fan-out: publish to each enabled target
    written: list[Path] = [archive_path, index_path]
    for pub_name in publishers:
        try:
            publisher = create_intake_publisher(pub_name)
            content = publisher.format_daily(context, prose)
            out_path = publisher.daily_output_path(output_dir, context.date)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            written.append(out_path)
        except Exception:
            logger.warning("Failed to publish intake to %s", pub_name, exc_info=True)

    # Mark items as processed and save state
    from datetime import datetime as dt

    for item in all_items:
        state.mark_processed(
            IntakeRecord(
                item_id=item.id,
                url=item.url,
                title=item.title,
                source=item.source.value,
            )
        )
    state.last_run = dt.now()
    state.prune(keep_days=30)
    save_intake_state(state, output_dir)

    # Update memory
    from distill.intake.memory import DailyIntakeEntry

    memory.add_entry(
        DailyIntakeEntry(
            date=context.date,
            themes=[t for t in context.all_tags[:5]],
            key_items=[i.title for i in all_items[:10] if i.title],
            item_count=len(all_items),
        )
    )
    memory.prune(keep_days=30)
    save_intake_memory(memory, output_dir)

    return written


def _generate_thematic_posts(
    *,
    entries: list[Any],
    memory: Any,
    state: Any,
    config: Any,
    synthesizer: Any,
    output_dir: Path,
    target_theme: str | None,
    force: bool,
    dry_run: bool,
    platforms: list[str],
    blog_memory: Any,
    ghost_config: Any | None = None,
) -> list[Path]:
    """Generate thematic deep-dive blog posts."""
    from distill.blog.config import Platform
    from distill.blog.context import prepare_thematic_context
    from distill.blog.diagrams import clean_diagrams
    from distill.blog.publishers import create_publisher
    from distill.blog.state import BlogPostRecord
    from distill.blog.themes import THEMES, gather_evidence, get_ready_themes

    written: list[Path] = []

    if target_theme:
        # Generate a specific theme
        theme_def = next((t for t in THEMES if t.slug == target_theme), None)
        if theme_def is None:
            return []
        evidence = gather_evidence(theme_def, entries)
        if not evidence:
            return []
        themes_to_generate = [(theme_def, evidence)]
    else:
        # Find all ready themes
        themes_to_generate = get_ready_themes(entries, state)

    for theme, evidence in themes_to_generate:
        if not force and state.is_generated(theme.slug):
            continue

        context = prepare_thematic_context(theme, evidence, memory)

        if dry_run:
            print(f"[DRY RUN] Would generate: {theme.slug}")
            print(f"  Evidence: {len(evidence)} entries")
            print(f"  Date range: {context.date_range[0]} to {context.date_range[1]}")
            print("---")
            continue

        memory_text = blog_memory.render_for_prompt()
        prose = synthesizer.synthesize_thematic(context, blog_memory=memory_text)
        if config.include_diagrams:
            prose = clean_diagrams(prose)

        # Extract blog memory
        try:
            summary = synthesizer.extract_blog_memory(prose, theme.slug, theme.title, "thematic")
            blog_memory.add_post(summary)
        except Exception:
            logger.warning("Blog memory extraction failed for %s", theme.slug)

        # Publish to each platform
        for platform_name in platforms:
            try:
                p = Platform(platform_name)
                publisher = create_publisher(
                    p, synthesizer=synthesizer, ghost_config=ghost_config
                )
                content = publisher.format_thematic(context, prose)
                out_path = publisher.thematic_output_path(output_dir, theme.slug)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(content, encoding="utf-8")
                written.append(out_path)
                blog_memory.mark_published(theme.slug, platform_name)
            except Exception:
                logger.warning(
                    "Failed to publish %s to %s", theme.slug, platform_name, exc_info=True
                )

        state.mark_generated(
            BlogPostRecord(
                slug=theme.slug,
                post_type="thematic",
                generated_at=datetime.now(),
                source_dates=[e.date for e in evidence],
                file_path=str(out_path) if written else "",
            )
        )

    return written
