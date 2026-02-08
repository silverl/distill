"""Tests for LinkedIn GDPR export parser."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from distill.intake.config import IntakeConfig, LinkedInIntakeConfig
from distill.intake.models import ContentItem, ContentSource, ContentType
from distill.intake.parsers.linkedin import LinkedInParser, _parse_date, _stable_id


# ── Helpers ──────────────────────────────────────────────────────────────


def _write_csv(path: Path, header: str, rows: list[str]) -> None:
    """Write a CSV file with the given header and rows."""
    content = header + "\n" + "\n".join(rows) + "\n"
    path.write_text(content, encoding="utf-8")


def _make_parser(tmp_path: Path, *, max_items: int = 50) -> LinkedInParser:
    """Create a LinkedInParser pointing at tmp_path."""
    config = IntakeConfig(
        linkedin=LinkedInIntakeConfig(export_path=str(tmp_path)),
        max_items_per_source=max_items,
    )
    return LinkedInParser(config=config)


# ── Configuration ────────────────────────────────────────────────────────


class TestConfiguration:
    def test_is_configured_when_export_path_set(self, tmp_path):
        config = IntakeConfig(
            linkedin=LinkedInIntakeConfig(export_path=str(tmp_path))
        )
        parser = LinkedInParser(config=config)
        assert parser.is_configured is True

    def test_not_configured_when_export_path_empty(self):
        config = IntakeConfig(linkedin=LinkedInIntakeConfig(export_path=""))
        parser = LinkedInParser(config=config)
        assert parser.is_configured is False

    def test_not_configured_default(self):
        config = IntakeConfig()
        parser = LinkedInParser(config=config)
        assert parser.is_configured is False

    def test_source_property(self, tmp_path):
        parser = _make_parser(tmp_path)
        assert parser.source == ContentSource.LINKEDIN


# ── Shares.csv ───────────────────────────────────────────────────────────


class TestParseShares:
    def test_basic_share(self, tmp_path):
        _write_csv(
            tmp_path / "Shares.csv",
            "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl",
            ["2026-01-15 10:00:00,https://linkedin.com/post/1,Great article!,https://example.com/article,"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert items[0].content_type == ContentType.POST
        assert items[0].source == ContentSource.LINKEDIN
        assert "Great article!" in items[0].body
        assert items[0].url == "https://linkedin.com/post/1"

    def test_share_with_shared_url(self, tmp_path):
        _write_csv(
            tmp_path / "Shares.csv",
            "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl",
            ["2026-01-15 10:00:00,https://linkedin.com/post/1,Check this out,https://example.com/shared,"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert "https://example.com/shared" in items[0].body

    def test_share_with_media_url(self, tmp_path):
        _write_csv(
            tmp_path / "Shares.csv",
            "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl",
            ["2026-01-15 10:00:00,https://linkedin.com/post/1,Look at this,,https://media.example.com/img.jpg"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert "https://media.example.com/img.jpg" in items[0].body

    def test_share_title_truncated(self, tmp_path):
        long_text = "A" * 200
        _write_csv(
            tmp_path / "Shares.csv",
            "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl",
            [f"2026-01-15 10:00:00,https://linkedin.com/post/1,{long_text},,"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert len(items[0].title) <= 100


# ── Articles.csv ─────────────────────────────────────────────────────────


class TestParseArticles:
    def test_basic_article(self, tmp_path):
        _write_csv(
            tmp_path / "Articles.csv",
            "Date,Title,Content,ArticleLink",
            ["2026-01-20 14:00:00,My Article,This is my article content about AI,https://linkedin.com/article/1"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert items[0].content_type == ContentType.ARTICLE
        assert items[0].title == "My Article"
        assert "AI" in items[0].body
        assert items[0].url == "https://linkedin.com/article/1"

    def test_article_word_count(self, tmp_path):
        _write_csv(
            tmp_path / "Articles.csv",
            "Date,Title,Content,ArticleLink",
            ["2026-01-20 14:00:00,Title,one two three four five,https://linkedin.com/article/1"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert items[0].word_count == 5

    def test_article_without_url_uses_title_as_id(self, tmp_path):
        _write_csv(
            tmp_path / "Articles.csv",
            "Date,Title,Content,ArticleLink",
            ["2026-01-20 14:00:00,My Title,Content here,"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert items[0].id == _stable_id("My Title")


# ── SavedArticles.csv ────────────────────────────────────────────────────


class TestParseSavedArticles:
    def test_saved_article_is_starred(self, tmp_path):
        _write_csv(
            tmp_path / "SavedArticles.csv",
            "Date,Title,Url",
            ["2026-01-18 09:00:00,Saved Post,https://example.com/saved"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert items[0].is_starred is True
        assert items[0].content_type == ContentType.ARTICLE
        assert items[0].title == "Saved Post"

    def test_saved_article_with_link_column(self, tmp_path):
        _write_csv(
            tmp_path / "SavedArticles.csv",
            "Date,Title,Link",
            ["2026-01-18 09:00:00,Another Saved,https://example.com/saved2"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert items[0].url == "https://example.com/saved2"

    def test_saved_articles_space_filename(self, tmp_path):
        """LinkedIn sometimes uses 'Saved Articles.csv' with a space."""
        _write_csv(
            tmp_path / "Saved Articles.csv",
            "Date,Title,Url",
            ["2026-01-18 09:00:00,Spaced File,https://example.com/spaced"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert items[0].title == "Spaced File"


# ── Reactions.csv ────────────────────────────────────────────────────────


class TestParseReactions:
    def test_basic_reaction(self, tmp_path):
        _write_csv(
            tmp_path / "Reactions.csv",
            "Date,Type,Link",
            ["2026-01-22 08:00:00,LIKE,https://linkedin.com/post/liked1"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert items[0].content_type == ContentType.ARTICLE
        assert "LIKE" in items[0].title
        assert items[0].metadata["reaction_type"] == "LIKE"

    def test_reaction_without_link_skipped(self, tmp_path):
        _write_csv(
            tmp_path / "Reactions.csv",
            "Date,Type,Link",
            ["2026-01-22 08:00:00,LIKE,"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 0


# ── Date parsing ─────────────────────────────────────────────────────────


class TestDateParsing:
    def test_iso_format(self):
        dt = _parse_date("2026-01-15 10:30:00")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.day == 15
        assert dt.tzinfo == timezone.utc

    def test_us_format(self):
        dt = _parse_date("01/15/2026 10:30:00")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.day == 15

    def test_date_only_iso(self):
        dt = _parse_date("2026-01-15")
        assert dt is not None
        assert dt.year == 2026

    def test_date_only_us(self):
        dt = _parse_date("01/15/2026")
        assert dt is not None
        assert dt.month == 1

    def test_empty_string(self):
        assert _parse_date("") is None

    def test_invalid_date(self):
        assert _parse_date("not-a-date") is None

    def test_whitespace_trimmed(self):
        dt = _parse_date("  2026-01-15  ")
        assert dt is not None


# ── Since-date filtering ─────────────────────────────────────────────────


class TestSinceFiltering:
    def test_filters_old_items(self, tmp_path):
        _write_csv(
            tmp_path / "Shares.csv",
            "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl",
            [
                "2025-01-01 10:00:00,https://linkedin.com/old,Old post,,",
                "2026-02-01 10:00:00,https://linkedin.com/new,New post,,",
            ],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 1
        assert "New post" in items[0].body

    def test_default_since_30_days(self, tmp_path):
        old_date = (datetime.now(tz=timezone.utc) - timedelta(days=60)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        recent_date = (datetime.now(tz=timezone.utc) - timedelta(days=1)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        _write_csv(
            tmp_path / "Shares.csv",
            "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl",
            [
                f"{old_date},https://linkedin.com/old,Old post,,",
                f"{recent_date},https://linkedin.com/new,Recent post,,",
            ],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=None)

        assert len(items) == 1
        assert "Recent" in items[0].body

    def test_naive_since_gets_utc(self, tmp_path):
        """A naive datetime for since should be treated as UTC."""
        recent_date = (datetime.now(tz=timezone.utc) - timedelta(days=1)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        _write_csv(
            tmp_path / "Shares.csv",
            "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl",
            [f"{recent_date},https://linkedin.com/post,Hello,,"],
        )
        parser = _make_parser(tmp_path)
        naive_since = datetime(2020, 1, 1)  # naive, no tzinfo
        items = parser.parse(since=naive_since)

        assert len(items) == 1


# ── Missing files ────────────────────────────────────────────────────────


class TestMissingFiles:
    def test_missing_csv_files_returns_empty(self, tmp_path):
        """Empty export directory — no CSVs at all."""
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))
        assert items == []

    def test_missing_export_directory(self):
        config = IntakeConfig(
            linkedin=LinkedInIntakeConfig(export_path="/nonexistent/path")
        )
        parser = LinkedInParser(config=config)
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))
        assert items == []

    def test_partial_csvs_ok(self, tmp_path):
        """Only Shares.csv present — other missing CSVs are skipped."""
        _write_csv(
            tmp_path / "Shares.csv",
            "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl",
            ["2026-01-15 10:00:00,https://linkedin.com/post/1,Hello,,"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert len(items) == 1


# ── Deduplication ────────────────────────────────────────────────────────


class TestDeduplication:
    def test_dedup_across_csvs(self, tmp_path):
        """Same URL in Shares.csv and Reactions.csv should be deduped."""
        _write_csv(
            tmp_path / "Shares.csv",
            "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl",
            ["2026-01-15 10:00:00,https://linkedin.com/shared,My post,,"],
        )
        _write_csv(
            tmp_path / "Reactions.csv",
            "Date,Type,Link",
            ["2026-01-15 10:00:00,LIKE,https://linkedin.com/shared"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        urls = [i.url for i in items]
        assert urls.count("https://linkedin.com/shared") == 1

    def test_different_urls_kept(self, tmp_path):
        _write_csv(
            tmp_path / "Shares.csv",
            "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl",
            [
                "2026-01-15 10:00:00,https://linkedin.com/a,Post A,,",
                "2026-01-16 10:00:00,https://linkedin.com/b,Post B,,",
            ],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert len(items) == 2


# ── Stable IDs ───────────────────────────────────────────────────────────


class TestStableIds:
    def test_id_is_16_chars(self, tmp_path):
        _write_csv(
            tmp_path / "Articles.csv",
            "Date,Title,Content,ArticleLink",
            ["2026-01-20 14:00:00,Test,Body,https://example.com/a"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert len(items[0].id) == 16

    def test_same_input_same_id(self):
        assert _stable_id("hello") == _stable_id("hello")

    def test_different_input_different_id(self):
        assert _stable_id("hello") != _stable_id("world")


# ── Max items limit ──────────────────────────────────────────────────────


class TestMaxItems:
    def test_limits_items(self, tmp_path):
        rows = [
            f"2026-01-{15 + i:02d} 10:00:00,https://linkedin.com/post/{i},Post {i},,"
            for i in range(10)
        ]
        _write_csv(
            tmp_path / "Shares.csv",
            "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl",
            rows,
        )
        parser = _make_parser(tmp_path, max_items=3)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert len(items) == 3


# ── Empty / malformed CSV ────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_csv(self, tmp_path):
        _write_csv(tmp_path / "Shares.csv", "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl", [])
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))
        assert items == []

    def test_csv_header_only(self, tmp_path):
        (tmp_path / "Articles.csv").write_text(
            "Date,Title,Content,ArticleLink\n", encoding="utf-8"
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2020, 1, 1, tzinfo=timezone.utc))
        assert items == []

    def test_share_with_no_url_and_no_commentary_skipped(self, tmp_path):
        _write_csv(
            tmp_path / "Shares.csv",
            "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl",
            ["2026-01-15 10:00:00,,,,"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert items == []

    def test_article_with_no_url_and_no_title_skipped(self, tmp_path):
        _write_csv(
            tmp_path / "Articles.csv",
            "Date,Title,Content,ArticleLink",
            ["2026-01-20 14:00:00,,,"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert items == []

    def test_multiple_csv_types_combined(self, tmp_path):
        _write_csv(
            tmp_path / "Shares.csv",
            "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl",
            ["2026-01-15 10:00:00,https://linkedin.com/share1,Shared post,,"],
        )
        _write_csv(
            tmp_path / "Articles.csv",
            "Date,Title,Content,ArticleLink",
            ["2026-01-20 14:00:00,My Article,Content,https://linkedin.com/article1"],
        )
        _write_csv(
            tmp_path / "SavedArticles.csv",
            "Date,Title,Url",
            ["2026-01-18 09:00:00,Saved,https://example.com/saved"],
        )
        _write_csv(
            tmp_path / "Reactions.csv",
            "Date,Type,Link",
            ["2026-01-22 08:00:00,LIKE,https://linkedin.com/liked"],
        )
        parser = _make_parser(tmp_path)
        items = parser.parse(since=datetime(2026, 1, 1, tzinfo=timezone.utc))

        assert len(items) == 4
        types = {i.content_type for i in items}
        assert ContentType.POST in types
        assert ContentType.ARTICLE in types
