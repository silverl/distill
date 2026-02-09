"""Tests for session parser — sessions as ContentItems."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from distill.intake.config import IntakeConfig, SessionIntakeConfig
from distill.intake.models import ContentSource, ContentType
from distill.intake.parsers.session import SessionParser, _session_to_content_item
from distill.parsers.models import (
    BaseSession,
    SessionOutcome,
    ToolUsageSummary,
    AgentLearning,
    AgentSignal,
)


def _make_session(
    session_id: str = "abc123",
    summary: str = "Implemented new feature",
    narrative: str = "Built a REST API endpoint for user authentication.",
    project: str = "my-project",
    source: str = "claude",
    start_time: datetime | None = None,
    tags: list[str] | None = None,
    tools_used: list[ToolUsageSummary] | None = None,
    outcomes: list[SessionOutcome] | None = None,
    task_description: str = "",
) -> BaseSession:
    if start_time is None:
        start_time = datetime(2026, 2, 7, 10, 0, 0, tzinfo=timezone.utc)
    return BaseSession(
        session_id=session_id,
        summary=summary,
        narrative=narrative,
        project=project,
        source=source,
        start_time=start_time,
        tags=tags or ["feature", "api"],
        tools_used=tools_used or [
            ToolUsageSummary(name="Read", count=10),
            ToolUsageSummary(name="Edit", count=5),
        ],
        outcomes=outcomes or [
            SessionOutcome(
                description="Added auth endpoint",
                files_modified=["src/auth.py", "tests/test_auth.py"],
                success=True,
            )
        ],
        task_description=task_description,
    )


class TestSessionToContentItem:
    """Test BaseSession → ContentItem mapping."""

    def test_basic_mapping(self):
        session = _make_session()
        item = _session_to_content_item(session)

        assert item.source == ContentSource.SESSION
        assert item.content_type == ContentType.POST
        assert item.source_id == "abc123"
        assert item.site_name == "claude"

    def test_title_from_summary(self):
        session = _make_session(summary="Built auth system")
        item = _session_to_content_item(session)
        assert item.title == "Built auth system"

    def test_title_truncation(self):
        long_summary = "x" * 300
        session = _make_session(summary=long_summary)
        item = _session_to_content_item(session)
        assert len(item.title) == 200

    def test_body_from_narrative(self):
        session = _make_session(narrative="Built a REST API endpoint.")
        item = _session_to_content_item(session)
        assert item.body == "Built a REST API endpoint."

    def test_body_fallback_to_summary(self):
        session = _make_session(narrative="", summary="Quick fix")
        item = _session_to_content_item(session)
        assert item.body == "Quick fix"

    def test_excerpt_from_summary(self):
        session = _make_session(summary="Short summary here")
        item = _session_to_content_item(session)
        assert item.excerpt == "Short summary here"

    def test_word_count(self):
        session = _make_session(narrative="one two three four five")
        item = _session_to_content_item(session)
        assert item.word_count == 5

    def test_tags_include_session_tags(self):
        session = _make_session(tags=["feature", "api"])
        item = _session_to_content_item(session)
        assert "feature" in item.tags
        assert "api" in item.tags

    def test_tags_include_tool_names(self):
        session = _make_session(
            tags=["feature"],
            tools_used=[ToolUsageSummary(name="Read", count=5)],
        )
        item = _session_to_content_item(session)
        assert "Read" in item.tags

    def test_tags_include_project(self):
        session = _make_session(project="my-project", tags=[])
        item = _session_to_content_item(session)
        assert "my-project" in item.tags

    def test_tags_skip_unknown_project(self):
        session = _make_session(project="(unknown)", tags=[])
        item = _session_to_content_item(session)
        assert "(unknown)" not in item.tags

    def test_tags_no_duplicate_tool_names(self):
        session = _make_session(
            tags=["Read"],
            tools_used=[ToolUsageSummary(name="Read", count=5)],
        )
        item = _session_to_content_item(session)
        assert item.tags.count("Read") == 1

    def test_published_at_from_start_time(self):
        ts = datetime(2026, 2, 7, 10, 0, 0, tzinfo=timezone.utc)
        session = _make_session(start_time=ts)
        item = _session_to_content_item(session)
        assert item.published_at == ts

    def test_metadata_project(self):
        session = _make_session(project="my-proj")
        item = _session_to_content_item(session)
        assert item.metadata["project"] == "my-proj"

    def test_metadata_tools_used(self):
        session = _make_session(
            tools_used=[ToolUsageSummary(name="Read", count=10)]
        )
        item = _session_to_content_item(session)
        tools = item.metadata["tools_used"]
        assert isinstance(tools, list)
        assert tools[0]["name"] == "Read"
        assert tools[0]["count"] == 10

    def test_metadata_outcomes(self):
        session = _make_session(
            outcomes=[
                SessionOutcome(
                    description="Added feature",
                    files_modified=["a.py"],
                    success=True,
                )
            ]
        )
        item = _session_to_content_item(session)
        outcomes = item.metadata["outcomes"]
        assert outcomes[0]["description"] == "Added feature"
        assert outcomes[0]["success"] is True

    def test_metadata_duration(self):
        session = _make_session()
        session.end_time = datetime(2026, 2, 7, 10, 30, 0, tzinfo=timezone.utc)
        item = _session_to_content_item(session)
        assert item.metadata["duration_minutes"] == 30.0

    def test_metadata_task_description(self):
        session = _make_session(task_description="Build auth module")
        item = _session_to_content_item(session)
        assert item.metadata["task_description"] == "Build auth module"

    def test_metadata_signals(self):
        session = _make_session()
        session.signals = [
            AgentSignal(
                signal_id="s1",
                agent_id="a1",
                role="dev",
                signal="done",
                message="Task complete",
                timestamp=datetime(2026, 2, 7, tzinfo=timezone.utc),
                workflow_id="w1",
            )
        ]
        item = _session_to_content_item(session)
        assert item.metadata["signals"][0]["signal"] == "done"

    def test_metadata_learnings(self):
        session = _make_session()
        session.learnings = [
            AgentLearning(agent="dev", learnings=["Use fixtures"])
        ]
        item = _session_to_content_item(session)
        assert item.metadata["learnings"][0]["learnings"] == ["Use fixtures"]

    def test_id_is_deterministic(self):
        s1 = _make_session(session_id="xyz789")
        s2 = _make_session(session_id="xyz789")
        item1 = _session_to_content_item(s1)
        item2 = _session_to_content_item(s2)
        assert item1.id == item2.id

    def test_different_sessions_different_ids(self):
        s1 = _make_session(session_id="abc")
        s2 = _make_session(session_id="def")
        item1 = _session_to_content_item(s1)
        item2 = _session_to_content_item(s2)
        assert item1.id != item2.id

    def test_empty_session(self):
        session = BaseSession(session_id="empty1")
        item = _session_to_content_item(session)
        assert item.source == ContentSource.SESSION
        assert item.title == "Coding session"
        assert item.word_count == 0

    def test_codex_source(self):
        session = _make_session(source="codex")
        item = _session_to_content_item(session)
        assert item.site_name == "codex"


class TestSessionParser:
    """Test the SessionParser class."""

    def _make_parser(self, **kwargs) -> SessionParser:
        config = IntakeConfig(session=SessionIntakeConfig(**kwargs))
        return SessionParser(config=config)

    def test_source(self):
        parser = self._make_parser()
        assert parser.source == ContentSource.SESSION

    def test_is_configured_always_true(self):
        parser = self._make_parser()
        assert parser.is_configured is True

    @patch("distill.core.discover_sessions")
    @patch("distill.core.parse_sessions")
    def test_parse_discovers_sessions(self, mock_parse, mock_discover, tmp_path):
        mock_discover.return_value = {
            "claude": [tmp_path / ".claude"],
        }
        mock_parse.return_value = [_make_session()]

        parser = self._make_parser(session_dirs=[str(tmp_path)])
        items = parser.parse()

        assert len(items) == 1
        assert items[0].source == ContentSource.SESSION
        mock_discover.assert_called_once()

    @patch("distill.core.discover_sessions")
    @patch("distill.core.parse_sessions")
    def test_parse_filters_by_since(self, mock_parse, mock_discover, tmp_path):
        old_session = _make_session(
            session_id="old",
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        new_session = _make_session(
            session_id="new",
            start_time=datetime(2026, 2, 7, tzinfo=timezone.utc),
        )
        mock_discover.return_value = {"claude": [tmp_path / ".claude"]}
        mock_parse.return_value = [old_session, new_session]

        parser = self._make_parser(session_dirs=[str(tmp_path)])
        since = datetime(2026, 2, 1, tzinfo=timezone.utc)
        items = parser.parse(since=since)

        assert len(items) == 1
        assert items[0].source_id == "new"

    @patch("distill.core.discover_sessions")
    @patch("distill.core.parse_sessions")
    def test_parse_deduplicates(self, mock_parse, mock_discover, tmp_path):
        session = _make_session(session_id="dup123")
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        # discover returns two roots with same source
        mock_discover.return_value = {
            "claude": [dir_a / ".claude-1", dir_a / ".claude-2"]
        }
        mock_parse.return_value = [session]

        parser = self._make_parser(session_dirs=[str(dir_a)])
        items = parser.parse()

        # parse_sessions called twice (once per root), each returns same session
        # Should be deduped to 1
        assert len(items) == 1

    @patch("distill.core.discover_sessions")
    @patch("distill.core.parse_sessions")
    def test_parse_multiple_sources(self, mock_parse, mock_discover, tmp_path):
        claude_session = _make_session(session_id="c1", source="claude")
        codex_session = _make_session(session_id="x1", source="codex")

        mock_discover.return_value = {
            "claude": [tmp_path / ".claude"],
            "codex": [tmp_path / ".codex"],
        }
        mock_parse.side_effect = [[claude_session], [codex_session]]

        parser = self._make_parser(session_dirs=[str(tmp_path)])
        items = parser.parse()

        assert len(items) == 2
        sites = {i.site_name for i in items}
        assert sites == {"claude", "codex"}

    @patch("distill.core.discover_sessions")
    def test_parse_empty_discovery(self, mock_discover, tmp_path):
        mock_discover.return_value = {}
        parser = self._make_parser(session_dirs=[str(tmp_path)])
        items = parser.parse()
        assert items == []

    @patch("distill.core.discover_sessions")
    @patch("distill.core.parse_sessions")
    def test_parse_with_naive_since(self, mock_parse, mock_discover, tmp_path):
        """since without timezone should still work."""
        session = _make_session(
            start_time=datetime(2026, 2, 7, tzinfo=timezone.utc)
        )
        mock_discover.return_value = {"claude": [tmp_path / ".claude"]}
        mock_parse.return_value = [session]

        parser = self._make_parser(session_dirs=[str(tmp_path)])
        # Naive datetime (no tzinfo)
        since = datetime(2026, 2, 1)
        items = parser.parse(since=since)
        assert len(items) == 1


class TestSessionParserFactory:
    """Test factory integration."""

    def test_create_parser(self):
        from distill.intake.parsers import create_parser

        config = IntakeConfig()
        parser = create_parser(ContentSource.SESSION, config=config)
        assert isinstance(parser, SessionParser)

    def test_get_configured_parsers_includes_session(self):
        from distill.intake.parsers import get_configured_parsers

        config = IntakeConfig()
        parsers = get_configured_parsers(config)
        sources = [p.source for p in parsers]
        assert ContentSource.SESSION in sources
