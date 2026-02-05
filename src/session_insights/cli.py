"""CLI interface for session-insights."""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from session_insights.core import (
    AnalysisResult,
    analyze,
    discover_sessions,
    parse_session_file,
)
from session_insights.formatters.obsidian import ObsidianFormatter
from session_insights.models import BaseSession

app = typer.Typer(
    name="session-insights",
    help="Analyze AI coding assistant sessions and generate Obsidian notes.",
)

console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        from session_insights import __version__

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


@app.command()
def analyze_cmd(
    directory: Annotated[
        Path,
        typer.Option(
            "--dir",
            "-d",
            help="Directory to scan for session history.",
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
            help="Output directory for Obsidian notes. Defaults to ./insights/",
        ),
    ] = None,
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
) -> None:
    """Analyze session history and generate Obsidian notes.

    Scans the specified directory for AI assistant session files and generates
    Obsidian-compatible markdown notes.
    """
    # Set default output directory if not provided
    if output is None:
        output = Path("./insights/")

    # Parse since date if provided
    since_date: date | None = None
    if since:
        try:
            since_date = datetime.strptime(since, "%Y-%m-%d").date()
        except ValueError:
            console.print(f"[red]Error:[/red] Invalid date format: {since}")
            console.print("Use YYYY-MM-DD format (e.g., 2024-01-15)")
            raise typer.Exit(1)

    # Create output directory if it doesn't exist and confirm
    output.mkdir(parents=True, exist_ok=True)
    console.print(f"Output will be written to: {output}")

    # Discover sessions
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Discovering session files...", total=None)
        discovered = discover_sessions(directory, source)

    if not discovered:
        console.print("[yellow]No session files found.[/yellow]")
        console.print(f"Searched in: {directory}")
        if source:
            console.print(f"Filtered to sources: {', '.join(source)}")
        raise typer.Exit(0)

    # Report discovery
    total_files = sum(len(files) for files in discovered.values())
    console.print(f"[green]Found {total_files} session file(s):[/green]")
    for src, files in discovered.items():
        console.print(f"  - {src}: {len(files)} file(s)")

    # Parse sessions
    all_sessions: list[BaseSession] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Parsing sessions...", total=total_files)

        for src, files in discovered.items():
            for file_path in files:
                sessions = parse_session_file(file_path, src)
                # Filter by date if specified
                if since_date:
                    sessions = [
                        s for s in sessions if s.start_time.date() >= since_date
                    ]
                all_sessions.extend(sessions)
                progress.advance(task)

    if not all_sessions:
        console.print("[yellow]No sessions found after parsing.[/yellow]")
        if since_date:
            console.print(f"Date filter: sessions after {since_date}")
        raise typer.Exit(0)

    console.print(f"[green]Parsed {len(all_sessions)} session(s)[/green]")

    # Analyze sessions
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Analyzing patterns...", total=None)
        result = analyze(all_sessions)

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

    # Report results
    console.print()
    console.print("[bold green]Analysis complete![/bold green]")
    console.print(f"  Sessions: {written_count}")
    console.print(f"  Daily summaries: {len(daily_sessions)}")
    console.print(f"  Output: {output}")

    # Show statistics
    if result.stats.date_range:
        start, end = result.stats.date_range
        console.print(f"  Date range: {start.date()} to {end.date()}")

    if result.patterns:
        console.print()
        console.print("[bold]Detected patterns:[/bold]")
        for pattern in result.patterns:
            console.print(f"  - {pattern.description}")


# Register the analyze command with a cleaner name
app.command(name="analyze")(analyze_cmd)


if __name__ == "__main__":
    app()
