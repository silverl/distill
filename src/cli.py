"""CLI interface for session-insights."""

import contextlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from distill.core import (
    AnalysisResult,
    analyze,
    compute_field_coverage,
    compute_richness_score,
    discover_sessions,
    generate_blog_posts,
    generate_journal_notes,
    generate_project_notes,
    generate_weekly_notes,
    parse_session_file,
)
from distill.formatters.obsidian import ObsidianFormatter
from distill.models import BaseSession
from distill.parsers.claude import ClaudeParser
from distill.parsers.codex import CodexParser

app = typer.Typer(
    name="session-insights",
    help="Analyze AI coding assistant sessions and generate Obsidian notes.",
)

console = Console()
_stderr_console = Console(stderr=True)


@contextlib.contextmanager
def _progress_context(quiet: bool = False):
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
            summary = session.summary[:60] + "..." if session.summary and len(session.summary) > 60 else (session.summary or "No summary")
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


def _build_stats_json(
    sessions: list[BaseSession], result: AnalysisResult
) -> dict:
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
        "field_coverage": {
            k: round(v, 3) for k, v in result.stats.field_coverage.items()
        },
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


def _parse_single_file(
    path: Path, source_filter: list[str] | None
) -> list[BaseSession]:
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
        raise typer.Exit(1)


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
        if progress:
            task = progress.add_task("Parsing sessions...", total=total_files)
        else:
            task = None

        for src, files in discovered.items():
            for file_path in files:
                try:
                    sessions = parse_session_file(file_path, src)
                except Exception as exc:
                    parse_errors.append(f"{file_path}: {exc}")
                    if progress and task is not None:
                        progress.advance(task)
                    continue
                # Filter by date if specified
                if since_date:
                    sessions = [
                        s for s in sessions if s.start_time.date() >= since_date
                    ]
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
        Optional[Path],
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
            raise typer.Exit(1)

    # If a file was passed directly, infer the source and parse it
    if directory.is_file():
        all_sessions = _parse_single_file(directory, source)
    else:
        all_sessions = _discover_and_parse(
            directory, source, include_global, since_date, stats_only,
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
        Optional[Path],
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
            raise typer.Exit(1)

    if since:
        try:
            since_date = datetime.strptime(since, "%Y-%m-%d").date()
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid date format: {since}")
            console.print("Use YYYY-MM-DD format (e.g., 2026-02-05)")
            raise typer.Exit(1)

    # Default to today if no date specified
    if parsed_target_date is None and since_date is None:
        parsed_target_date = date.today()

    # Discover and parse sessions
    all_sessions = _discover_and_parse(
        directory, source, include_global, since_date, stats_only=False,
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
        console.print("[yellow]No new entries generated (all cached). Use --force to regenerate.[/yellow]")
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
) -> None:
    """Generate blog posts from existing journal entries.

    Reads journal markdown files and working memory, then synthesizes
    weekly synthesis posts and/or thematic deep-dives with Mermaid
    diagrams. Output is Obsidian-compatible markdown.

    Use --dry-run to preview what would be generated.
    Use --force to regenerate posts that already exist.
    """
    # Validate post type
    valid_types = ("weekly", "thematic", "all")
    if post_type not in valid_types:
        console.print(f"[red]Error:[/red] Unknown type: {post_type}")
        console.print(f"Valid types: {', '.join(valid_types)}")
        raise typer.Exit(1)

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


if __name__ == "__main__":
    app()
