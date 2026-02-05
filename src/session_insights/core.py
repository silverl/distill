"""Core analysis pipeline for session insights."""

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from session_insights.parsers import ClaudeParser, CodexParser, VermasParser
from session_insights.parsers.models import BaseSession


class SessionStats(BaseModel):
    """Statistics about analyzed sessions."""

    total_sessions: int = 0
    total_duration_minutes: float = 0.0
    sources: dict[str, int] = Field(default_factory=dict)
    tools_used: dict[str, int] = Field(default_factory=dict)
    date_range: tuple[datetime, datetime] | None = None


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
    if source == "claude":
        parser = ClaudeParser()
        return list(parser.parse_directory(root))
    elif source == "codex":
        parser = CodexParser()
        return list(parser.parse_directory(root))
    elif source == "vermas":
        parser = VermasParser()
        return list(parser.parse_directory(root))

    return []


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
    times = [s.start_time for s in sessions if s.start_time is not None]
    date_range = (min(times), max(times)) if times else None

    return SessionStats(
        total_sessions=len(sessions),
        total_duration_minutes=total_duration,
        sources=dict(sources),
        tools_used=dict(tools),
        date_range=date_range,
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
