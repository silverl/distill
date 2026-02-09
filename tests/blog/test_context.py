"""Tests for blog context assembly (deterministic, no LLM)."""

from datetime import date

from distill.blog.context import (
    prepare_thematic_context,
    prepare_weekly_context,
)
from distill.blog.reader import JournalEntry
from distill.blog.themes import ThemeDefinition
from distill.journal.memory import MemoryThread, WorkingMemory


def _make_entry(
    day: int = 5,
    sessions: int = 3,
    duration: float = 60.0,
    projects: list[str] | None = None,
    tags: list[str] | None = None,
    prose: str = "Default prose about development work.",
) -> JournalEntry:
    return JournalEntry(
        date=date(2026, 2, day),
        style="dev-journal",
        sessions_count=sessions,
        duration_minutes=duration,
        tags=tags or ["python"],
        projects=projects or ["vermas"],
        prose=prose,
    )


class TestPrepareWeeklyContext:
    def test_basic_assembly(self):
        entries = [_make_entry(day=3), _make_entry(day=4), _make_entry(day=5)]
        ctx = prepare_weekly_context(entries, 2026, 6)

        assert ctx.year == 2026
        assert ctx.week == 6
        assert ctx.week_start == date(2026, 2, 2)
        assert ctx.week_end == date(2026, 2, 8)
        assert len(ctx.entries) == 3

    def test_aggregates_sessions(self):
        entries = [
            _make_entry(day=3, sessions=5, duration=100),
            _make_entry(day=4, sessions=3, duration=50),
        ]
        ctx = prepare_weekly_context(entries, 2026, 6)

        assert ctx.total_sessions == 8
        assert ctx.total_duration_minutes == 150.0

    def test_deduplicates_projects(self):
        entries = [
            _make_entry(day=3, projects=["vermas", "insights"]),
            _make_entry(day=4, projects=["vermas", "other"]),
        ]
        ctx = prepare_weekly_context(entries, 2026, 6)

        assert ctx.projects == ["vermas", "insights", "other"]

    def test_deduplicates_tags(self):
        entries = [
            _make_entry(day=3, tags=["python", "testing"]),
            _make_entry(day=4, tags=["python", "refactoring"]),
        ]
        ctx = prepare_weekly_context(entries, 2026, 6)

        assert "python" in ctx.all_tags
        assert ctx.all_tags.count("python") == 1
        assert "testing" in ctx.all_tags
        assert "refactoring" in ctx.all_tags

    def test_combines_prose_with_day_labels(self):
        entries = [
            _make_entry(day=3, prose="Monday work."),
            _make_entry(day=5, prose="Wednesday work."),
        ]
        ctx = prepare_weekly_context(entries, 2026, 6)

        assert "Monday work." in ctx.combined_prose
        assert "Wednesday work." in ctx.combined_prose
        assert "Tuesday, February 03" in ctx.combined_prose

    def test_includes_working_memory(self):
        entries = [_make_entry(day=3)]
        memory = WorkingMemory()
        memory.threads.append(
            MemoryThread(
                name="branch-merging",
                summary="Still failing",
                first_mentioned=date(2026, 2, 1),
                last_mentioned=date(2026, 2, 3),
                status="open",
            )
        )
        ctx = prepare_weekly_context(entries, 2026, 6, memory=memory)

        assert "branch-merging" in ctx.working_memory
        assert "Still failing" in ctx.working_memory

    def test_empty_memory(self):
        entries = [_make_entry(day=3)]
        ctx = prepare_weekly_context(entries, 2026, 6)
        assert ctx.working_memory == ""

    def test_empty_entries(self):
        ctx = prepare_weekly_context([], 2026, 6)
        assert ctx.total_sessions == 0
        assert ctx.combined_prose == ""

    def test_project_context_and_editorial_notes_default_empty(self):
        entries = [_make_entry(day=3)]
        ctx = prepare_weekly_context(entries, 2026, 6)
        assert ctx.project_context == ""
        assert ctx.editorial_notes == ""

    def test_project_context_and_editorial_notes_settable(self):
        entries = [_make_entry(day=3)]
        ctx = prepare_weekly_context(entries, 2026, 6)
        ctx.project_context = "## Project Context\n\n**VerMAS**: Multi-agent platform"
        ctx.editorial_notes = "## Editorial Direction\n\n- Focus on X"
        assert "VerMAS" in ctx.project_context
        assert "Focus on X" in ctx.editorial_notes


class TestPrepareThematicContext:
    def test_basic_assembly(self):
        theme = ThemeDefinition(
            slug="test-theme",
            title="Test Theme",
            keywords=["test"],
            thread_patterns=["test"],
        )
        entries = [
            _make_entry(day=3, prose="Evidence about test."),
            _make_entry(day=5, prose="More test evidence."),
        ]
        ctx = prepare_thematic_context(theme, entries)

        assert ctx.theme.slug == "test-theme"
        assert ctx.evidence_count == 2
        assert ctx.date_range == (date(2026, 2, 3), date(2026, 2, 5))

    def test_combines_evidence(self):
        theme = ThemeDefinition(slug="t", title="T", keywords=[], thread_patterns=[])
        entries = [
            _make_entry(day=3, prose="First evidence."),
            _make_entry(day=5, prose="Second evidence."),
        ]
        ctx = prepare_thematic_context(theme, entries)

        assert "First evidence." in ctx.combined_evidence
        assert "Second evidence." in ctx.combined_evidence

    def test_finds_relevant_threads(self):
        theme = ThemeDefinition(
            slug="t",
            title="T",
            keywords=[],
            thread_patterns=["merge", "branch"],
        )
        entries = [_make_entry(day=3)]
        memory = WorkingMemory()
        memory.threads.extend([
            MemoryThread(
                name="merge-failures",
                summary="Ongoing issues",
                first_mentioned=date(2026, 2, 1),
                last_mentioned=date(2026, 2, 3),
            ),
            MemoryThread(
                name="unrelated-thread",
                summary="Something else",
                first_mentioned=date(2026, 2, 1),
                last_mentioned=date(2026, 2, 3),
            ),
        ])

        ctx = prepare_thematic_context(theme, entries, memory=memory)

        assert len(ctx.relevant_threads) == 1
        assert ctx.relevant_threads[0].name == "merge-failures"

    def test_empty_evidence(self):
        theme = ThemeDefinition(slug="t", title="T", keywords=[], thread_patterns=[])
        ctx = prepare_thematic_context(theme, [])

        assert ctx.evidence_count == 0
        assert ctx.combined_evidence == ""

    def test_sorts_evidence_by_date(self):
        theme = ThemeDefinition(slug="t", title="T", keywords=[], thread_patterns=[])
        entries = [
            _make_entry(day=5, prose="Later."),
            _make_entry(day=3, prose="Earlier."),
        ]
        ctx = prepare_thematic_context(theme, entries)

        # Combined evidence should be chronological
        earlier_pos = ctx.combined_evidence.index("Earlier.")
        later_pos = ctx.combined_evidence.index("Later.")
        assert earlier_pos < later_pos

    def test_thematic_project_context_and_editorial_notes_default_empty(self):
        theme = ThemeDefinition(slug="t", title="T", keywords=[], thread_patterns=[])
        entries = [_make_entry(day=3)]
        ctx = prepare_thematic_context(theme, entries)
        assert ctx.project_context == ""
        assert ctx.editorial_notes == ""

    def test_thematic_project_context_settable(self):
        theme = ThemeDefinition(slug="t", title="T", keywords=[], thread_patterns=[])
        entries = [_make_entry(day=3)]
        ctx = prepare_thematic_context(theme, entries)
        ctx.project_context = "## Project Context\n\n**Distill**: Content pipeline"
        assert "Distill" in ctx.project_context
