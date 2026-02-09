"""CLI interface for session-insights."""

import contextlib
import json
from collections.abc import Generator
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer
from distill.core import (
    AnalysisResult,
    analyze,
    discover_sessions,
    generate_blog_posts,
    generate_intake,
    generate_journal_notes,
    generate_project_notes,
    generate_weekly_notes,
    parse_session_file,
)
from distill.formatters.obsidian import ObsidianFormatter
from distill.models import BaseSession
from distill.parsers.claude import ClaudeParser
from distill.parsers.codex import CodexParser
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(
    name="session-insights",
    help="Analyze AI coding assistant sessions and generate Obsidian notes.",
)

console = Console()
_stderr_console = Console(stderr=True)


@contextlib.contextmanager
def _progress_context(quiet: bool = False) -> Generator[object, None, None]:
    """Yield a Progress context or a no-op depending on quiet flag."""
    if quiet:
        yield None
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            yield progress


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        from distill import __version__

        console.print(f"session-insights {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Session Insights - Analyze AI coding assistant sessions."""
    pass


def _generate_index(
    sessions: list[BaseSession],
    daily_sessions: dict[date, list[BaseSession]],
    result: AnalysisResult,
) -> str:
    """Generate an index.md file linking all sessions.

    Args:
        sessions: All analyzed sessions.
        daily_sessions: Sessions grouped by date.
        result: Analysis result with patterns and stats.

    Returns:
        Markdown content for the index file.
    """
    lines = [
        "---",
        "type: index",
        f"created: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}",
        f"total_sessions: {len(sessions)}",
        "---",
        "",
        "# Session Insights Index",
        "",
        "## Overview",
        "",
        f"- **Total Sessions**: {len(sessions)}",
        f"- **Total Days**: {len(daily_sessions)}",
    ]

    # Add date range if available
    if result.stats.date_range:
        start, end = result.stats.date_range
        lines.append(f"- **Date Range**: {start.date()} to {end.date()}")

    lines.extend(["", "## Sessions by Date", ""])

    # List sessions grouped by date
    for summary_date in sorted(daily_sessions.keys(), reverse=True):
        date_sessions = daily_sessions[summary_date]
        daily_link = f"[[daily/daily-{summary_date.isoformat()}|{summary_date.isoformat()}]]"
        lines.append(f"### {daily_link}")
        lines.append("")

        for session in sorted(date_sessions, key=lambda s: s.start_time):
            time_str = session.start_time.strftime("%H:%M")
            session_link = f"[[sessions/{session.note_name}]]"
            summary = (
                session.summary[:60] + "..."
                if session.summary and len(session.summary) > 60
                else (session.summary or "No summary")
            )
            lines.append(f"- {time_str} - {session_link}: {summary}")

        lines.append("")

    # Add patterns section if available
    if result.patterns:
        lines.extend(["## Detected Patterns", ""])
        for pattern in result.patterns:
            lines.append(f"- {pattern.description}")
        lines.append("")

    return "\n".join(lines)


def _empty_stats_json() -> dict:
    """Return an empty stats JSON structure for when no sessions are found."""
    return {
        "session_count": 0,
        "content_richness_score": 0.0,
        "field_coverage": {},
        "sources": {},
        "total_duration_minutes": 0.0,
        "date_range": None,
        "patterns": [],
    }


def _build_stats_json(sessions: list[BaseSession], result: AnalysisResult) -> dict:
    """Build the stats JSON output from analysis results."""
    date_range = None
    if result.stats.date_range:
        start, end = result.stats.date_range
        date_range = {
            "start": start.isoformat(),
            "end": end.isoformat(),
        }

    return {
        "session_count": result.stats.total_sessions,
        "content_richness_score": result.stats.content_richness_score,
        "field_coverage": {k: round(v, 3) for k, v in result.stats.field_coverage.items()},
        "sources": result.stats.sources,
        "total_duration_minutes": round(result.stats.total_duration_minutes, 1),
        "date_range": date_range,
        "patterns": [
            {"name": p.name, "description": p.description, "occurrences": p.occurrences}
            for p in result.patterns
        ],
    }


def _infer_source_from_path(path: Path) -> str | None:
    """Infer the source type from a file/directory path."""
    for parent in [path] + list(path.parents):
        if parent.name == ".claude":
            return "claude"
        if parent.name == ".codex":
            return "codex"
        if parent.name == ".vermas":
            return "vermas"
    return None


def _parse_single_file(path: Path, source_filter: list[str] | None) -> list[BaseSession]:
    """Parse a single session file using the appropriate parser.

    Uses the parser's single-file method rather than scanning an entire
    source root, so only the specified file is parsed.
    """
    inferred = _infer_source_from_path(path)
    if source_filter and inferred and inferred not in source_filter:
        return []
    src = inferred or "claude"  # default to claude for unknown files

    try:
        if src == "claude":
            parser = ClaudeParser()
            session = parser._parse_session_file(path)
            if parser.parse_errors:
                for err in parser.parse_errors:
                    console.print(f"[yellow]Warning:[/yellow] {err}")
            return [session] if session is not None else []
        elif src == "codex":
            codex_parser = CodexParser()
            session = codex_parser._parse_session_file(path)
            if codex_parser.parse_errors:
                for err in codex_parser.parse_errors:
                    console.print(f"[yellow]Warning:[/yellow] {err}")
            return [session] if session is not None else []
        else:
            # For vermas or unknown, fall back to directory parsing
            return parse_session_file(path, src)
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to parse {path}: {exc}")
        raise typer.Exit(1) from None


def _discover_and_parse(
    directory: Path,
    source: list[str] | None,
    include_global: bool,
    since_date: date | None,
    stats_only: bool,
) -> list[BaseSession]:
    """Discover and parse sessions from a directory."""
    with _progress_context(quiet=stats_only) as progress:
        if progress:
            progress.add_task("Discovering session files...", total=None)
        discovered = discover_sessions(directory, source, include_home=include_global)

    if not discovered:
        if stats_only:
            return []
        console.print("[yellow]No session files found.[/yellow]")
        console.print(f"Searched in: {directory}")
        if source:
            console.print(f"Filtered to sources: {', '.join(source)}")
        return []

    # Report discovery (skip in stats-only for clean JSON output)
    total_files = sum(len(files) for files in discovered.values())
    if not stats_only:
        console.print(f"[green]Found {total_files} session file(s):[/green]")
        for src, files in discovered.items():
            console.print(f"  - {src}: {len(files)} file(s)")

    # Parse sessions with error handling for unparseable files
    all_sessions: list[BaseSession] = []
    parse_errors: list[str] = []

    with _progress_context(quiet=stats_only) as progress:
        task = progress.add_task("Parsing sessions...", total=total_files) if progress else None

        for src, files in discovered.items():
            for file_path in files:
                try:
                    sessions = parse_session_file(file_path, src, since=since_date)
                except Exception as exc:
                    parse_errors.append(f"{file_path}: {exc}")
                    if progress and task is not None:
                        progress.advance(task)
                    continue
                # Filter by date if specified (belt-and-suspenders with mtime pre-filter)
                if since_date:
                    sessions = [s for s in sessions if s.start_time.date() >= since_date]
                all_sessions.extend(sessions)
                if progress and task is not None:
                    progress.advance(task)

    if parse_errors and not stats_only:
        console.print(f"[yellow]Warning: {len(parse_errors)} file(s) could not be parsed:[/yellow]")
        for err in parse_errors[:5]:
            console.print(f"  - {err}")
        if len(parse_errors) > 5:
            console.print(f"  ... and {len(parse_errors) - 5} more")

    return all_sessions


@app.command()
def analyze_cmd(
    directory: Annotated[
        Path,
        typer.Option(
            "--dir",
            "-d",
            help="Directory or session file to analyze.",
            exists=True,
            file_okay=True,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path("."),
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output directory for Obsidian notes. Defaults to ./insights/",
        ),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format. Currently only 'obsidian' is supported.",
        ),
    ] = "obsidian",
    source: Annotated[
        list[str] | None,
        typer.Option(
            "--source",
            "-s",
            help="Filter to specific sources (claude, codex, vermas).",
        ),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option(
            "--since",
            help="Only analyze sessions after this date (YYYY-MM-DD).",
        ),
    ] = None,
    include_conversation: Annotated[
        bool,
        typer.Option(
            "--include-conversation/--no-conversation",
            help="Include full conversation in notes.",
        ),
    ] = False,
    include_global: Annotated[
        bool,
        typer.Option(
            "--global/--no-global",
            help="Also scan home directory (~/.claude, ~/.codex) for sessions.",
        ),
    ] = False,
    stats_only: Annotated[
        bool,
        typer.Option(
            "--stats-only",
            help="Output statistics as JSON without generating Obsidian notes.",
        ),
    ] = False,
) -> None:
    """Analyze session history and generate Obsidian notes.

    Scans the specified directory (or session file) for AI assistant
    session data, runs the full parse-model-format pipeline, and outputs
    statistics including session count, content richness score, and
    field coverage.

    Use --stats-only for JSON statistics without generating notes.
    Use --global to also include sessions from your home directory.
    """
    # Validate format option (only relevant when generating notes)
    if not stats_only and output_format != "obsidian":
        console.print(f"[red]Error:[/red] Unsupported format: {output_format}")
        console.print("Currently only 'obsidian' format is supported.")
        raise typer.Exit(1)

    # Parse since date if provided
    since_date: date | None = None
    if since:
        try:
            since_date = datetime.strptime(since, "%Y-%m-%d").date()
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid date format: {since}")
            console.print("Use YYYY-MM-DD format (e.g., 2024-01-15)")
            raise typer.Exit(1) from None

    # If a file was passed directly, infer the source and parse it
    if directory.is_file():
        all_sessions = _parse_single_file(directory, source)
    else:
        all_sessions = _discover_and_parse(
            directory,
            source,
            include_global,
            since_date,
            stats_only,
        )

    # Filter by date if specified (for single-file path too)
    if since_date and directory.is_file():
        all_sessions = [s for s in all_sessions if s.start_time.date() >= since_date]

    if not all_sessions:
        if stats_only:
            print(json.dumps(_empty_stats_json(), indent=2))
            raise typer.Exit(0)
        console.print("[yellow]No sessions found after parsing.[/yellow]")
        if since_date:
            console.print(f"Date filter: sessions after {since_date}")
        raise typer.Exit(0)

    if not stats_only:
        console.print(f"[green]Parsed {len(all_sessions)} session(s)[/green]")

    # Analyze sessions
    with _progress_context(quiet=stats_only) as progress:
        if progress:
            progress.add_task("Analyzing patterns...", total=None)
        result = analyze(all_sessions)

    # --stats-only: output JSON to stdout and exit
    if stats_only:
        stats_json = _build_stats_json(all_sessions, result)
        print(json.dumps(stats_json, indent=2))
        raise typer.Exit(0)

    # Set default output directory if not provided
    if output is None:
        output = Path("./insights/")

    # Create output directory
    output.mkdir(parents=True, exist_ok=True)
    console.print(f"Output will be written to: {output}")

    # Create subdirectories
    sessions_dir = output / "sessions"
    sessions_dir.mkdir(exist_ok=True)

    # Format and write notes
    formatter = ObsidianFormatter(include_conversation=include_conversation)
    written_count = 0
    daily_sessions: dict[date, list[BaseSession]] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Writing Obsidian notes...", total=len(all_sessions))

        for session in all_sessions:
            # Write session note
            note_content = formatter.format_session(session)
            note_path = sessions_dir / f"{session.note_name}.md"
            note_path.write_text(note_content, encoding="utf-8")
            written_count += 1

            # Collect for daily summary
            session_date = session.start_time.date()
            if session_date not in daily_sessions:
                daily_sessions[session_date] = []
            daily_sessions[session_date].append(session)

            progress.advance(task)

    # Write daily summaries
    daily_dir = output / "daily"
    daily_dir.mkdir(exist_ok=True)

    for summary_date, sessions in daily_sessions.items():
        daily_content = formatter.format_daily_summary(sessions, summary_date)
        daily_path = daily_dir / f"daily-{summary_date.isoformat()}.md"
        daily_path.write_text(daily_content, encoding="utf-8")

    # Write project notes via core pipeline
    project_note_files = generate_project_notes(all_sessions, output)
    project_count = len(project_note_files)

    # Write weekly digest notes via core pipeline
    weekly_note_files = generate_weekly_notes(all_sessions, output)
    weekly_count = len(weekly_note_files)

    # Write index.md linking all sessions
    index_content = _generate_index(all_sessions, daily_sessions, result)
    index_path = output / "index.md"
    index_path.write_text(index_content, encoding="utf-8")

    # Report results
    console.print()
    console.print("[bold green]Analysis complete![/bold green]")
    console.print(f"  Sessions: {written_count}")
    console.print(f"  Daily summaries: {len(daily_sessions)}")
    console.print(f"  Weekly digests: {weekly_count}")
    console.print(f"  Project notes: {project_count}")
    console.print(f"  Output: {output}")

    # Show statistics
    if result.stats.date_range:
        start, end = result.stats.date_range
        console.print(f"  Date range: {start.date()} to {end.date()}")

    console.print(f"  Content richness: {result.stats.content_richness_score:.1%}")

    if result.patterns:
        console.print()
        console.print("[bold]Detected patterns:[/bold]")
        for pattern in result.patterns:
            console.print(f"  - {pattern.description}")


# Register the analyze command with a cleaner name
app.command(name="analyze")(analyze_cmd)


@app.command(name="sessions")
def sessions_cmd(
    directory: Annotated[
        Path,
        typer.Option(
            "--dir",
            "-d",
            help="Directory to scan for .claude/ and .codex/ session directories.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path("."),
    include_global: Annotated[
        bool,
        typer.Option(
            "--global/--no-global",
            help="Also scan home directory (~/.claude, ~/.codex) for sessions.",
        ),
    ] = False,
) -> None:
    """Discover sessions and print a JSON summary.

    Scans the specified directory for .claude/ and .codex/ directories,
    uses the existing parsers to extract sessions, and prints a simple
    JSON summary with session count, total messages, and date range.
    Use --global to also include sessions from your home directory.
    """
    claude_parser = ClaudeParser()
    codex_parser = CodexParser()

    claude_sessions: list[BaseSession] = []
    codex_sessions: list[BaseSession] = []

    # Collect directories to scan
    dirs_to_scan = [directory]
    if include_global:
        home = Path.home()
        if home != directory:
            dirs_to_scan.append(home)

    for scan_dir in dirs_to_scan:
        # Find .claude/ directory
        claude_dir = scan_dir / ".claude"
        if claude_dir.exists() and claude_dir.is_dir():
            claude_sessions.extend(claude_parser.parse_directory(claude_dir))

        # Find .codex/ directory
        codex_dir = scan_dir / ".codex"
        if codex_dir.exists() and codex_dir.is_dir():
            codex_sessions.extend(codex_parser.parse_directory(codex_dir))

    # Combine all sessions
    all_sessions = claude_sessions + codex_sessions

    # Calculate summary statistics
    total_sessions = len(all_sessions)
    total_messages = sum(len(s.messages) for s in all_sessions)

    # Calculate date range
    date_range_start: str | None = None
    date_range_end: str | None = None
    if all_sessions:
        timestamps = [s.timestamp for s in all_sessions]
        earliest = min(timestamps)
        latest = max(timestamps)
        date_range_start = earliest.isoformat()
        date_range_end = latest.isoformat()

    # Build summary
    summary = {
        "session_count": total_sessions,
        "total_messages": total_messages,
        "date_range": {
            "start": date_range_start,
            "end": date_range_end,
        },
        "sources": {
            "claude": len(claude_sessions),
            "codex": len(codex_sessions),
        },
    }

    # Output JSON
    console.print(json.dumps(summary, indent=2))


@app.command(name="journal")
def journal_cmd(
    directory: Annotated[
        Path,
        typer.Option(
            "--dir",
            "-d",
            help="Directory to scan for session data.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path("."),
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output directory. Journal notes go in output/journal/.",
        ),
    ] = None,
    style: Annotated[
        str,
        typer.Option(
            "--style",
            "-s",
            help="Writing style: dev-journal, tech-blog, team-update, building-in-public.",
        ),
    ] = "dev-journal",
    target_date: Annotated[
        str | None,
        typer.Option(
            "--date",
            help="Generate for a specific date (YYYY-MM-DD). Defaults to today.",
        ),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option(
            "--since",
            help="Generate for all dates since YYYY-MM-DD.",
        ),
    ] = None,
    source: Annotated[
        list[str] | None,
        typer.Option(
            "--source",
            help="Filter to specific sources (claude, codex, vermas).",
        ),
    ] = None,
    include_global: Annotated[
        bool,
        typer.Option(
            "--global/--no-global",
            help="Also scan home directory for sessions.",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Regenerate even if cached.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Print context without calling LLM.",
        ),
    ] = False,
    words: Annotated[
        int,
        typer.Option(
            "--words",
            help="Target word count for the entry.",
        ),
    ] = 600,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="Override the Claude model (e.g., claude-haiku-4-5-20251001).",
        ),
    ] = None,
) -> None:
    """Generate journal/blog entries from session data using LLM synthesis.

    Discovers sessions, compresses them into structured context, and sends
    the context to Claude CLI for narrative prose synthesis. Output is
    Obsidian-compatible markdown with YAML frontmatter.

    Use --dry-run to preview the context that would be sent to the LLM.
    Use --force to regenerate entries that are already cached.
    """
    from distill.journal.config import JournalStyle

    # Validate style
    valid_styles = [s.value for s in JournalStyle]
    if style not in valid_styles:
        console.print(f"[red]Error:[/red] Unknown style: {style}")
        console.print(f"Valid styles: {', '.join(valid_styles)}")
        raise typer.Exit(1)

    # Parse dates
    since_date: date | None = None
    parsed_target_date: date | None = None

    if target_date:
        try:
            parsed_target_date = datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid date format: {target_date}")
            console.print("Use YYYY-MM-DD format (e.g., 2026-02-05)")
            raise typer.Exit(1) from None

    if since:
        try:
            since_date = datetime.strptime(since, "%Y-%m-%d").date()
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid date format: {since}")
            console.print("Use YYYY-MM-DD format (e.g., 2026-02-05)")
            raise typer.Exit(1) from None

    # Default to today if no date specified
    if parsed_target_date is None and since_date is None:
        parsed_target_date = date.today()

    # Discover and parse sessions
    all_sessions = _discover_and_parse(
        directory,
        source,
        include_global,
        since_date,
        stats_only=False,
    )

    if not all_sessions:
        console.print("[yellow]No sessions found.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[green]Parsed {len(all_sessions)} session(s)[/green]")

    # Determine target dates
    target_dates: list[date] | None = None
    if parsed_target_date:
        target_dates = [parsed_target_date]
    # If --since was used, target_dates stays None (all dates)

    # Set default output directory
    if output is None:
        output = Path("./insights/")

    # Generate journal entries
    with _progress_context(quiet=dry_run) as progress:
        if progress:
            progress.add_task("Generating journal entries...", total=None)

        written = generate_journal_notes(
            all_sessions,
            output,
            target_dates=target_dates,
            style=style,
            target_word_count=words,
            force=force,
            dry_run=dry_run,
            model=model,
        )

    if dry_run:
        return

    if not written:
        console.print(
            "[yellow]No new entries generated (all cached). Use --force to regenerate.[/yellow]"
        )
        return

    console.print()
    console.print(f"[bold green]Generated {len(written)} journal entry/entries:[/bold green]")
    for path in written:
        console.print(f"  {path}")


@app.command(name="blog")
def blog_cmd(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output directory (contains journal/ and blog/).",
        ),
    ],
    post_type: Annotated[
        str,
        typer.Option(
            "--type",
            "-t",
            help="Post type: weekly, thematic, or all.",
        ),
    ] = "all",
    week: Annotated[
        str | None,
        typer.Option(
            "--week",
            help="Generate a specific week (e.g., 2026-W06). Weekly only.",
        ),
    ] = None,
    theme: Annotated[
        str | None,
        typer.Option(
            "--theme",
            help="Generate a specific theme slug. Thematic only.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Regenerate even if already generated.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview what would be generated without calling LLM.",
        ),
    ] = False,
    no_diagrams: Annotated[
        bool,
        typer.Option(
            "--no-diagrams",
            help="Skip Mermaid diagram generation.",
        ),
    ] = False,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="Override the Claude model.",
        ),
    ] = None,
    words: Annotated[
        int,
        typer.Option(
            "--words",
            help="Target word count for blog posts.",
        ),
    ] = 1200,
    publish: Annotated[
        str | None,
        typer.Option(
            "--publish",
            help="Comma-separated platforms (obsidian,ghost,markdown,twitter,linkedin,reddit).",
        ),
    ] = None,
    ghost_url: Annotated[
        str | None,
        typer.Option(
            "--ghost-url",
            help="Ghost instance URL (or GHOST_URL env var).",
        ),
    ] = None,
    ghost_key: Annotated[
        str | None,
        typer.Option(
            "--ghost-key",
            help="Ghost Admin API key as id:secret (or GHOST_ADMIN_API_KEY env var).",
        ),
    ] = None,
    ghost_newsletter: Annotated[
        str | None,
        typer.Option(
            "--ghost-newsletter",
            help="Ghost newsletter slug for auto-send (or GHOST_NEWSLETTER_SLUG env var).",
        ),
    ] = None,
) -> None:
    """Generate blog posts from existing journal entries.

    Reads journal markdown files and working memory, then synthesizes
    weekly synthesis posts and/or thematic deep-dives with Mermaid
    diagrams. Output is Obsidian-compatible markdown.

    Use --dry-run to preview what would be generated.
    Use --force to regenerate posts that already exist.
    Use --publish to target specific platforms (comma-separated).
    """
    # Validate post type
    valid_types = ("weekly", "thematic", "all")
    if post_type not in valid_types:
        console.print(f"[red]Error:[/red] Unknown type: {post_type}")
        console.print(f"Valid types: {', '.join(valid_types)}")
        raise typer.Exit(1)

    # Parse platforms
    from distill.blog.config import Platform

    if publish:
        platform_names = [p.strip() for p in publish.split(",")]
        valid_platforms = [p.value for p in Platform]
        for pname in platform_names:
            if pname != "all" and pname not in valid_platforms:
                console.print(f"[red]Error:[/red] Unknown platform: {pname}")
                console.print(f"Valid platforms: {', '.join(valid_platforms)}")
                raise typer.Exit(1)
        if "all" in platform_names:
            platform_names = valid_platforms
    else:
        platform_names = ["obsidian"]

    # Build Ghost config from CLI options / env vars
    from distill.blog.config import GhostConfig

    ghost_config = GhostConfig.from_env()
    if ghost_url:
        ghost_config.url = ghost_url
    if ghost_key:
        ghost_config.admin_api_key = ghost_key
    if ghost_newsletter:
        ghost_config.newsletter_slug = ghost_newsletter

    # Check that journal directory exists
    journal_dir = output / "journal"
    if not journal_dir.exists():
        console.print(f"[red]Error:[/red] No journal directory found at {journal_dir}")
        console.print("Run the 'journal' command first to generate journal entries.")
        raise typer.Exit(1)

    with _progress_context(quiet=dry_run) as progress:
        if progress:
            progress.add_task("Generating blog posts...", total=None)

        written = generate_blog_posts(
            output,
            post_type=post_type,
            target_week=week,
            target_theme=theme,
            force=force,
            dry_run=dry_run,
            include_diagrams=not no_diagrams,
            model=model,
            target_word_count=words,
            platforms=platform_names,
            ghost_config=ghost_config if ghost_config.is_configured else None,
        )

    if dry_run:
        return

    if not written:
        console.print("[yellow]No new blog posts generated.[/yellow]")
        console.print("Use --force to regenerate, or check that journal entries exist.")
        return

    console.print()
    console.print(f"[bold green]Generated {len(written)} blog post(s):[/bold green]")
    for path in written:
        console.print(f"  {path}")


@app.command(name="intake")
def intake_cmd(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output directory. Intake digests go in output/intake/.",
        ),
    ],
    sources: Annotated[
        str | None,
        typer.Option(
            "--sources",
            "-s",
            help=(
                "Comma-separated sources"
                " (rss,browser,substack,linkedin,twitter,reddit,youtube,gmail)."
                " Default: all configured."
            ),
        ),
    ] = None,
    feeds_file: Annotated[
        str | None,
        typer.Option(
            "--feeds-file",
            help="Path to a text file with RSS feed URLs (one per line).",
        ),
    ] = None,
    opml: Annotated[
        str | None,
        typer.Option(
            "--opml",
            help="Path to an OPML file with RSS feed subscriptions.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Re-process all items, ignoring state.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview fetched content without calling LLM.",
        ),
    ] = False,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="Override the Claude model.",
        ),
    ] = None,
    words: Annotated[
        int,
        typer.Option(
            "--words",
            help="Target word count for the digest.",
        ),
    ] = 800,
    publish: Annotated[
        str | None,
        typer.Option(
            "--publish",
            help=(
                "Comma-separated publishers"
                " (obsidian, markdown, ghost, twitter, linkedin, reddit)."
                " Default: obsidian."
            ),
        ),
    ] = None,
    use_defaults: Annotated[
        bool,
        typer.Option(
            "--use-defaults",
            help="Use built-in default RSS feeds (90+ tech/engineering blogs).",
        ),
    ] = False,
    ghost_url: Annotated[
        str | None,
        typer.Option(
            "--ghost-url",
            help="Ghost instance URL (or GHOST_URL env var).",
        ),
    ] = None,
    ghost_key: Annotated[
        str | None,
        typer.Option(
            "--ghost-key",
            help="Ghost Admin API key as id:secret (or GHOST_ADMIN_API_KEY env var).",
        ),
    ] = None,
    ghost_newsletter: Annotated[
        str | None,
        typer.Option(
            "--ghost-newsletter",
            help="Newsletter slug for auto-send (or GHOST_NEWSLETTER_SLUG env var).",
        ),
    ] = None,
    browser_history: Annotated[
        bool,
        typer.Option(
            "--browser-history",
            help="Include browser history (Chrome/Safari) in ingestion.",
        ),
    ] = False,
    substack_blogs: Annotated[
        str | None,
        typer.Option(
            "--substack-blogs",
            help="Comma-separated Substack blog URLs to ingest.",
        ),
    ] = None,
    twitter_export: Annotated[
        str | None,
        typer.Option(
            "--twitter-export",
            help="Path to X/Twitter data export directory.",
        ),
    ] = None,
    linkedin_export: Annotated[
        str | None,
        typer.Option(
            "--linkedin-export",
            help="Path to LinkedIn GDPR data export directory.",
        ),
    ] = None,
    reddit_user: Annotated[
        str | None,
        typer.Option(
            "--reddit-user",
            help="Reddit username (also reads REDDIT_USERNAME env var).",
        ),
    ] = None,
    youtube_api_key: Annotated[
        str | None,
        typer.Option(
            "--youtube-api-key",
            help="YouTube Data API key (also reads YOUTUBE_API_KEY env var).",
        ),
    ] = None,
    gmail_credentials: Annotated[
        str | None,
        typer.Option(
            "--gmail-credentials",
            help="Path to Google OAuth credentials.json for Gmail access.",
        ),
    ] = None,
    include_sessions: Annotated[
        bool,
        typer.Option(
            "--include-sessions/--no-sessions",
            help="Include coding sessions (Claude/Codex) as content source.",
        ),
    ] = False,
    session_dirs: Annotated[
        str | None,
        typer.Option(
            "--session-dirs",
            help="Comma-separated directories to scan for sessions.",
        ),
    ] = None,
    global_sessions: Annotated[
        bool,
        typer.Option(
            "--global-sessions",
            help="Also scan home directory for sessions.",
        ),
    ] = False,
) -> None:
    """Ingest content from external sources and synthesize a daily research digest.

    Fetches RSS feeds (and other configured sources), normalizes content into
    a canonical model, then synthesizes a daily reading digest via Claude.

    Use --feeds-file or --opml to provide your own feed list.
    Use --use-defaults to start with 90+ curated tech/engineering feeds.
    Use --browser-history to include Chrome/Safari browsing history.
    Use --dry-run to preview fetched content without calling the LLM.
    """
    # Resolve sources
    source_list = [s.strip() for s in sources.split(",")] if sources else None

    # Resolve publishers
    publisher_list = [p.strip() for p in publish.split(",")] if publish else None

    # Build Ghost config from CLI options / env vars
    from distill.blog.config import GhostConfig

    gc = GhostConfig.from_env()
    if ghost_url:
        gc.url = ghost_url
    if ghost_key:
        gc.admin_api_key = ghost_key
    if ghost_newsletter:
        gc.newsletter_slug = ghost_newsletter
    intake_ghost_config = gc if gc.is_configured else None

    # Resolve feeds file — use built-in defaults if requested
    resolved_feeds_file = feeds_file
    if use_defaults and not feeds_file and not opml:
        default_path = Path(__file__).parent / "intake" / "default_feeds.txt"
        if default_path.exists():
            resolved_feeds_file = str(default_path)
            console.print(f"[dim]Using default feeds from {default_path}[/dim]")

    with _progress_context(quiet=dry_run) as progress:
        if progress:
            progress.add_task("Ingesting content...", total=None)

        # Parse substack blogs
        substack_blog_list = (
            [u.strip() for u in substack_blogs.split(",") if u.strip()] if substack_blogs else None
        )

        # Parse session dirs
        session_dir_list = (
            [d.strip() for d in session_dirs.split(",") if d.strip()] if session_dirs else None
        )

        written = generate_intake(
            output,
            feeds_file=resolved_feeds_file,
            opml_file=opml,
            sources=source_list,
            force=force,
            dry_run=dry_run,
            model=model,
            target_word_count=words,
            publishers=publisher_list,
            ghost_config=intake_ghost_config,
            browser_history=browser_history,
            substack_blogs=substack_blog_list,
            twitter_export=twitter_export,
            linkedin_export=linkedin_export,
            reddit_user=reddit_user,
            youtube_api_key=youtube_api_key,
            gmail_credentials=gmail_credentials,
            include_sessions=include_sessions,
            session_dirs=session_dir_list,
            global_sessions=global_sessions,
        )

    if dry_run:
        return

    if not written:
        console.print("[yellow]No new content to digest.[/yellow]")
        console.print("Use --force to re-process, or check your feed configuration.")
        return

    console.print()
    console.print(f"[bold green]Generated {len(written)} intake digest(s):[/bold green]")
    for path in written:
        console.print(f"  {path}")


@app.command(name="run")
def run_cmd(
    directory: Annotated[
        Path,
        typer.Option(
            "--dir",
            "-d",
            help="Directory to scan for session data.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path("."),
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output directory for all generated content.",
        ),
    ] = Path("./insights"),
    include_global: Annotated[
        bool,
        typer.Option(
            "--global/--no-global",
            help="Also scan home directory for sessions.",
        ),
    ] = False,
    use_defaults: Annotated[
        bool,
        typer.Option(
            "--use-defaults",
            help="Use built-in default RSS feeds for intake.",
        ),
    ] = True,
    publish: Annotated[
        str | None,
        typer.Option(
            "--publish",
            help="Comma-separated platforms (obsidian,ghost,markdown). Default: obsidian.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview all steps without calling LLM.",
        ),
    ] = False,
    skip_sessions: Annotated[
        bool,
        typer.Option(
            "--skip-sessions",
            help="Skip session parsing and journal generation.",
        ),
    ] = False,
    skip_intake: Annotated[
        bool,
        typer.Option(
            "--skip-intake",
            help="Skip content ingestion.",
        ),
    ] = False,
    skip_blog: Annotated[
        bool,
        typer.Option(
            "--skip-blog",
            help="Skip blog post generation.",
        ),
    ] = False,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            help="Override the Claude model.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Regenerate everything, ignoring caches.",
        ),
    ] = False,
    since: Annotated[
        str | None,
        typer.Option(
            "--since",
            help="Only process sessions since this date (YYYY-MM-DD). Default: 2 days ago.",
        ),
    ] = None,
    ghost_url: Annotated[
        str | None,
        typer.Option("--ghost-url", help="Ghost instance URL."),
    ] = None,
    ghost_key: Annotated[
        str | None,
        typer.Option("--ghost-key", help="Ghost Admin API key as id:secret."),
    ] = None,
) -> None:
    """Run the full distill pipeline: sessions -> journal -> intake -> blog -> publish.

    This is the single command that orchestrates everything. Ideal for
    daily scheduled runs (e.g., via launchd/cron).

    Only processes the delta: sessions from the last 2 days (or --since),
    new intake items since last run, and any un-generated blog posts.
    Memory and state files provide continuity across runs.
    """
    from datetime import timedelta

    from distill.errors import PipelineReport, save_report

    platform_names = [p.strip() for p in publish.split(",")] if publish else ["obsidian"]

    # Build Ghost config
    from distill.blog.config import GhostConfig

    gc = GhostConfig.from_env()
    if ghost_url:
        gc.url = ghost_url
    if ghost_key:
        gc.admin_api_key = ghost_key
    ghost_cfg = gc if gc.is_configured else None

    all_written: list[Path] = []
    errors: list[str] = []
    report = PipelineReport()

    # Load project context for prompt injection
    from distill.config import load_config as _load_config

    _cfg = _load_config()
    _project_context = _cfg.render_project_context()

    # Delta window: only parse sessions from the --since date or last 2 days
    if force:
        delta_since = None
        target_dates = None
    elif since:
        try:
            delta_since = datetime.strptime(since, "%Y-%m-%d").date()
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid date format: {since}")
            console.print("Use YYYY-MM-DD format (e.g., 2026-02-07)")
            raise typer.Exit(1) from None
        # Generate journal for all dates in the range
        target_dates = None
    else:
        delta_since = date.today() - timedelta(days=2)
        target_dates = [date.today()]

    # Step 1: Discover and parse sessions -> journal
    if not skip_sessions:
        console.print("[bold]Step 1/3: Sessions → Journal[/bold]")
        try:
            all_sessions = _discover_and_parse(
                directory,
                None,
                include_global,
                since_date=delta_since,
                stats_only=False,
            )
            if all_sessions:
                console.print(f"  Found {len(all_sessions)} session(s)")
                written = generate_journal_notes(
                    all_sessions,
                    output,
                    target_dates=target_dates,
                    force=force,
                    dry_run=dry_run,
                    model=model,
                    report=report,
                    project_context=_project_context,
                )
                all_written.extend(written)
                report.items_processed["journal"] = len(written)
                report.mark_stage_complete("journal")
                console.print(f"  [green]Generated {len(written)} journal entry/entries[/green]")
            else:
                console.print("  [yellow]No sessions found[/yellow]")
                report.mark_stage_complete("journal")
        except Exception as exc:
            errors.append(f"Sessions/journal: {exc}")
            report.add_error("journal", str(exc), error_type="stage_error", recoverable=True)
            console.print(f"  [red]Error: {exc}[/red]")
    else:
        console.print("[dim]Step 1/3: Sessions → Journal (skipped)[/dim]")

    # Step 2: Intake — ingest external content
    if not skip_intake:
        console.print("[bold]Step 2/3: Intake → Digest[/bold]")
        try:
            # Resolve feeds file for defaults
            resolved_feeds_file: str | None = None
            if use_defaults:
                default_path = Path(__file__).parent / "intake" / "default_feeds.txt"
                if default_path.exists():
                    resolved_feeds_file = str(default_path)

            written = generate_intake(
                output,
                feeds_file=resolved_feeds_file,
                force=force,
                dry_run=dry_run,
                model=model,
                publishers=platform_names,
                ghost_config=ghost_cfg,
                include_sessions=not skip_sessions,
                session_dirs=[str(directory)],
                global_sessions=include_global,
                report=report,
            )
            all_written.extend(written)
            report.items_processed["intake"] = len(written)
            report.mark_stage_complete("intake")
            console.print(f"  [green]Generated {len(written)} intake output(s)[/green]")
        except Exception as exc:
            errors.append(f"Intake: {exc}")
            report.add_error("intake", str(exc), error_type="stage_error", recoverable=True)
            console.print(f"  [red]Error: {exc}[/red]")
    else:
        console.print("[dim]Step 2/3: Intake → Digest (skipped)[/dim]")

    # Step 3: Blog — generate posts from journal + intake
    if not skip_blog:
        console.print("[bold]Step 3/3: Blog → Publish[/bold]")
        journal_dir = output / "journal"
        if journal_dir.exists():
            try:
                written = generate_blog_posts(
                    output,
                    force=force,
                    dry_run=dry_run,
                    model=model,
                    platforms=platform_names,
                    ghost_config=ghost_cfg,
                    report=report,
                )
                all_written.extend(written)
                report.items_processed["blog"] = len(written)
                report.mark_stage_complete("blog")
                console.print(f"  [green]Generated {len(written)} blog post(s)[/green]")
            except Exception as exc:
                errors.append(f"Blog: {exc}")
                report.add_error("blog", str(exc), error_type="stage_error", recoverable=True)
                console.print(f"  [red]Error: {exc}[/red]")
        else:
            console.print("  [yellow]No journal entries yet — skipping blog[/yellow]")
    else:
        console.print("[dim]Step 3/3: Blog → Publish (skipped)[/dim]")

    # Update unified memory
    if not dry_run:
        try:
            from distill.memory import load_unified_memory, save_unified_memory

            memory = load_unified_memory(output)
            memory.prune(keep_days=30)
            save_unified_memory(memory, output)
        except Exception:
            pass

    # Finalize and save report
    report.outputs_written = [str(p) for p in all_written]
    report.finish()
    if not dry_run:
        with contextlib.suppress(Exception):
            save_report(report, output)

        # Send notifications if configured
        with contextlib.suppress(Exception):
            from distill.config import load_config
            from distill.notifications import send_notification

            cfg = load_config()
            if cfg.notifications.is_configured:
                send_notification(cfg.notifications, report)

    # Summary
    console.print()
    if errors:
        console.print(f"[bold yellow]Pipeline completed with {len(errors)} error(s)[/bold yellow]")
        for err in errors:
            console.print(f"  [red]- {err}[/red]")
    else:
        console.print("[bold green]Pipeline complete![/bold green]")
    console.print(f"  Total outputs: {len(all_written)}")
    console.print(f"  Output directory: {output}")


@app.command(name="status")
def status_cmd(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output directory to inspect.",
        ),
    ] = Path("./insights"),
) -> None:
    """Show the current state of the distill pipeline.

    Displays last run info, journal/blog/intake counts, memory stats,
    content store size, and configured source status.
    """
    from distill.errors import load_report
    from distill.memory import MEMORY_FILENAME

    # Last run report
    report = load_report(output)
    if report:
        ago = ""
        if report.finished_at:
            delta = datetime.now() - report.finished_at
            hours = int(delta.total_seconds() / 3600)
            if hours < 1:
                mins = int(delta.total_seconds() / 60)
                ago = f" ({mins}m ago)"
            else:
                ago = f" ({hours}h ago)"
            finished_str = report.finished_at.strftime("%Y-%m-%d %H:%M")
        else:
            finished_str = report.started_at.strftime("%Y-%m-%d %H:%M")
        err_count = report.error_count
        console.print(f"Last run: {finished_str}{ago} — {err_count} error(s)")
    else:
        console.print("Last run: [dim]no runs recorded[/dim]")

    console.print()

    # Journal entries
    journal_dir = output / "journal"
    if journal_dir.exists():
        journal_files = list(journal_dir.glob("**/*.md"))
        latest = ""
        if journal_files:
            newest = max(journal_files, key=lambda p: p.stat().st_mtime)
            latest = f" (latest: {newest.stem})"
        console.print(f"Journal: {len(journal_files)} entries{latest}")
    else:
        console.print("Journal: [dim]no entries[/dim]")

    # Blog posts
    blog_dir = output / "blog"
    if blog_dir.exists():
        weekly_count = len(list(blog_dir.glob("**/weekly-*.md")))
        thematic_count = len(list(blog_dir.glob("**/*.md"))) - weekly_count
        if thematic_count < 0:
            thematic_count = 0
        console.print(f"Blog:    {weekly_count} weekly + {thematic_count} thematic posts")
    else:
        console.print("Blog:    [dim]no posts[/dim]")

    # Intake
    intake_dir = output / "intake"
    if intake_dir.exists():
        intake_files = list(intake_dir.glob("**/*.md"))
        latest = ""
        if intake_files:
            newest = max(intake_files, key=lambda p: p.stat().st_mtime)
            latest = f" (latest: {newest.stem})"
        console.print(f"Intake:  {len(intake_files)} items{latest}")
    else:
        console.print("Intake:  [dim]no items[/dim]")

    # Memory
    memory_path = output / MEMORY_FILENAME
    if memory_path.exists():
        try:
            import json as _json

            data = _json.loads(memory_path.read_text(encoding="utf-8"))
            entries = len(data.get("entries", []))
            threads = len(data.get("threads", []))
            entities = len(data.get("entities", {}))
            console.print(f"Memory:  {entries} entries, {threads} threads, {entities} entities")
        except (ValueError, KeyError):
            console.print("Memory:  [dim]corrupt[/dim]")
    else:
        console.print("Memory:  [dim]not initialized[/dim]")

    # Content store
    from distill.store import JSON_STORE_FILENAME

    store_path = output / JSON_STORE_FILENAME
    if store_path.exists():
        try:
            data = json.loads(store_path.read_text(encoding="utf-8"))
            count = len(data.get("items", []))
            console.print(f"Store:   {count} items embedded")
        except (ValueError, KeyError):
            console.print("Store:   [dim]corrupt[/dim]")
    else:
        console.print("Store:   [dim]empty[/dim]")

    # Configured sources
    source_checks = {
        "rss": (output / "intake" / "default_feeds.txt").exists()
        or Path(__file__).parent.joinpath("intake", "default_feeds.txt").exists(),
        "browser": True,  # always locally available
        "substack": False,
    }
    # Check config for more sources
    from distill.config import load_config

    with contextlib.suppress(Exception):
        cfg = load_config()
        if cfg.intake.substack_blogs:
            source_checks["substack"] = True
        if cfg.reddit.client_id:
            source_checks["reddit"] = True
        if cfg.youtube.api_key:
            source_checks["youtube"] = True
        if cfg.ghost.url:
            source_checks["ghost"] = True

    parts = []
    for name, configured in source_checks.items():
        mark = "[green]✓[/green]" if configured else "[dim]✗[/dim]"
        parts.append(f"{name} {mark}")
    console.print(f"Sources: {', '.join(parts)}")


@app.command(name="seed")
def seed_add(
    text: Annotated[
        str,
        typer.Argument(help="Your thought, headline, or topic idea."),
    ],
    tags: Annotated[
        str,
        typer.Option(
            "--tags",
            help="Comma-separated tags.",
        ),
    ] = "",
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output directory (where seeds are stored).",
        ),
    ] = Path("./insights"),
) -> None:
    """Add a seed idea — a raw thought or headline for your next digest."""
    from distill.intake.seeds import SeedStore

    store = SeedStore(output)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    seed = store.add(text, tags=tag_list)
    console.print(f"[green]Seed added:[/green] {seed.text}")
    if tag_list:
        console.print(f"  Tags: {', '.join(tag_list)}")
    console.print(f"  ID: {seed.id}")


@app.command(name="seeds")
def seed_list(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output directory (where seeds are stored).",
        ),
    ] = Path("./insights"),
    show_all: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Show all seeds, including used ones.",
        ),
    ] = False,
) -> None:
    """List your pending seed ideas."""
    from distill.intake.seeds import SeedStore

    store = SeedStore(output)
    seeds = store.list_all() if show_all else store.list_unused()

    if not seeds:
        console.print("[yellow]No seeds found.[/yellow]")
        return

    for seed in seeds:
        status = "[dim](used)[/dim] " if seed.used else ""
        tag_str = f" [dim][{', '.join(seed.tags)}][/dim]" if seed.tags else ""
        console.print(f"  {status}{seed.text}{tag_str}")
        console.print(f"    [dim]ID: {seed.id} | {seed.created_at.date()}[/dim]")


@app.command(name="note")
def note_add(
    text: Annotated[
        str,
        typer.Argument(help="Editorial direction or emphasis for content generation."),
    ],
    target: Annotated[
        str,
        typer.Option(
            "--target",
            help="Target scope (e.g., 'week:2026-W06', 'theme:multi-agent'). Empty = global.",
        ),
    ] = "",
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output directory (where notes are stored).",
        ),
    ] = Path("./insights"),
) -> None:
    """Add an editorial note to guide content generation."""
    from distill.editorial import EditorialStore

    store = EditorialStore(output)
    note = store.add(text, target=target)
    console.print(f"[green]Note added:[/green] {note.text}")
    if target:
        console.print(f"  Target: {target}")
    console.print(f"  ID: {note.id}")


@app.command(name="notes")
def note_list(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output directory (where notes are stored).",
        ),
    ] = Path("./insights"),
    show_all: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Show all notes, including used ones.",
        ),
    ] = False,
) -> None:
    """List active editorial notes."""
    from distill.editorial import EditorialStore

    store = EditorialStore(output)
    notes = store.list_all() if show_all else store.list_active()

    if not notes:
        console.print("[yellow]No editorial notes found.[/yellow]")
        return

    for note in notes:
        status = "[dim](used)[/dim] " if note.used else ""
        target_str = f" [dim][{note.target}][/dim]" if note.target else ""
        console.print(f"  {status}{note.text}{target_str}")
        console.print(f"    [dim]ID: {note.id} | {note.created_at.date()}[/dim]")


if __name__ == "__main__":
    app()
