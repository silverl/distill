"""Narrative quality KPI measurer.

Scores session narratives against quality criteria and rejects low-quality
narratives containing raw prompts, XML tags, literal commands, or
insufficient content.
"""

from __future__ import annotations

import re

from distill.measurers.base import KPIResult, Measurer
from distill.parsers.models import BaseSession

# XML tag pattern: matches <tag-name>, </tag-name>, <tag-name attr="val">
_XML_TAG_RE = re.compile(r"</?[a-zA-Z][\w-]*(?:\s[^>]*)?>")

# File path pattern: bare paths like /foo/bar.py or src/foo/bar
_FILE_PATH_RE = re.compile(r"^[\w./\\-]+\.\w{1,5}$")

# Known tool names from Claude Code and similar systems
_TOOL_NAMES = frozenset({
    "Read", "Edit", "Write", "Bash", "Glob", "Grep", "WebFetch", "WebSearch",
    "Task", "TodoRead", "TodoWrite", "NotebookEdit", "AskFollowupQuestion",
    "AttemptCompletion", "ListFiles", "SearchFiles", "ExecuteCommand",
})

# Known literal command patterns (short CLI-style strings)
_COMMAND_PATTERNS = [
    re.compile(r"^(analyze|init|help|run|build|test|start|stop|deploy|status)\b", re.IGNORECASE),
    re.compile(r"^(cd|ls|cat|grep|find|rm|mkdir|cp|mv|echo|pwd)\b", re.IGNORECASE),
    re.compile(r"^/\w+"),  # slash commands like /help, /commit
]

MIN_WORD_COUNT = 10


def score_narrative(text: str) -> tuple[bool, list[str]]:
    """Score a narrative string for quality.

    Returns:
        Tuple of (passes, list_of_failure_reasons).
        If passes is True, the list is empty.
    """
    if not text or not text.strip():
        return False, ["empty_narrative"]

    text = text.strip()
    failures: list[str] = []

    # Check: contains XML tags
    if _XML_TAG_RE.search(text):
        failures.append("contains_xml_tags")

    # Check: under minimum word count
    words = text.split()
    if len(words) < MIN_WORD_COUNT:
        failures.append("too_short")

    # Check: is just a file path
    if _FILE_PATH_RE.match(text):
        failures.append("just_file_path")

    # Check: is just a tool name
    if text.strip() in _TOOL_NAMES:
        failures.append("just_tool_name")

    # Check: is a literal command
    for pattern in _COMMAND_PATTERNS:
        if pattern.match(text) and len(words) <= 3:
            failures.append("literal_command")
            break

    return (len(failures) == 0, failures)


class NarrativeQualityMeasurer(Measurer):
    """Measures percentage of session narratives that pass quality checks.

    Target: 80%+ of narratives should pass.
    """

    KPI_NAME = "narrative_quality"
    TARGET = 80.0

    def __init__(self, sessions: list[BaseSession] | None = None) -> None:
        self._sessions = sessions or []

    def measure(self) -> KPIResult:
        return self.measure_sessions(self._sessions)

    def measure_sessions(self, sessions: list[BaseSession]) -> KPIResult:
        """Score narratives across all provided sessions."""
        if not sessions:
            return KPIResult(
                kpi=self.KPI_NAME,
                value=0.0,
                target=self.TARGET,
                details={"error": "no sessions provided"},
            )

        total = 0
        passed = 0
        failures_summary: dict[str, int] = {}
        per_session: list[dict[str, object]] = []

        for session in sessions:
            narrative = session.narrative
            if not narrative:
                # Try generating from the session
                from distill.narrative import generate_narrative

                narrative = generate_narrative(session)

            ok, reasons = score_narrative(narrative)
            total += 1
            if ok:
                passed += 1

            for reason in reasons:
                failures_summary[reason] = failures_summary.get(reason, 0) + 1

            per_session.append({
                "session_id": session.session_id,
                "passed": ok,
                "failures": reasons,
                "narrative_preview": narrative[:100] if narrative else "",
            })

        value = (passed / total * 100) if total > 0 else 0.0

        return KPIResult(
            kpi=self.KPI_NAME,
            value=round(value, 1),
            target=self.TARGET,
            details={
                "total_sessions": total,
                "passed": passed,
                "failed": total - passed,
                "failure_reasons": failures_summary,
                "per_session": per_session,
            },
        )
