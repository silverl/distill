"""Tests for intake content archiving."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from distill.intake.archive import archive_items, build_daily_index
from distill.intake.models import ContentItem, ContentSource, ContentType


def _make_item(
    title: str = "Test Article",
    url: str = "https://example.com/test",
    body: str = "This is a test article body with some content.",
    site_name: str = "Example Blog",
    author: str = "Test Author",
    source: ContentSource = ContentSource.RSS,
    tags: list[str] | None = None,
    word_count: int = 100,
) -> ContentItem:
    return ContentItem(
        id=f"test-{hash(title + url) % 10000}",
        url=url,
        title=title,
        body=body,
        excerpt=body[:100],
        word_count=word_count,
        author=author,
        site_name=site_name,
        source=source,
        content_type=ContentType.ARTICLE,
        tags=tags or ["test"],
        published_at=datetime(2026, 2, 7, 10, 0),
    )


class TestArchiveItems:
    """Tests for archive_items()."""

    def test_creates_archive_file(self, tmp_path: Path) -> None:
        items = [_make_item()]
        path = archive_items(items, tmp_path, target_date=date(2026, 2, 7))
        assert path.exists()
        assert path.name == "2026-02-07.json"
        assert path.parent.name == "archive"

    def test_archive_json_structure(self, tmp_path: Path) -> None:
        items = [_make_item(), _make_item(title="Second", url="https://example.com/2")]
        path = archive_items(items, tmp_path, target_date=date(2026, 2, 7))

        data = json.loads(path.read_text())
        assert data["date"] == "2026-02-07"
        assert data["item_count"] == 2
        assert len(data["items"]) == 2

    def test_archive_item_fields(self, tmp_path: Path) -> None:
        item = _make_item(title="My Article", author="Jane", site_name="Cool Blog")
        path = archive_items([item], tmp_path, target_date=date(2026, 2, 7))

        data = json.loads(path.read_text())
        archived = data["items"][0]
        assert archived["title"] == "My Article"
        assert archived["author"] == "Jane"
        assert archived["site_name"] == "Cool Blog"
        assert archived["source"] == "rss"
        assert archived["url"] == "https://example.com/test"

    def test_archive_preserves_body(self, tmp_path: Path) -> None:
        long_body = "A" * 5000
        item = _make_item(body=long_body)
        path = archive_items([item], tmp_path, target_date=date(2026, 2, 7))

        data = json.loads(path.read_text())
        assert data["items"][0]["body"] == long_body

    def test_defaults_to_today(self, tmp_path: Path) -> None:
        path = archive_items([_make_item()], tmp_path)
        assert path.name == f"{date.today().isoformat()}.json"

    def test_creates_directories(self, tmp_path: Path) -> None:
        deep_dir = tmp_path / "a" / "b" / "c"
        path = archive_items([_make_item()], deep_dir, target_date=date(2026, 2, 7))
        assert path.exists()

    def test_empty_items(self, tmp_path: Path) -> None:
        path = archive_items([], tmp_path, target_date=date(2026, 2, 7))
        data = json.loads(path.read_text())
        assert data["item_count"] == 0
        assert data["items"] == []


class TestBuildDailyIndex:
    """Tests for build_daily_index()."""

    def test_creates_index_file(self, tmp_path: Path) -> None:
        items = [_make_item()]
        path = build_daily_index(items, tmp_path, target_date=date(2026, 2, 7))
        assert path.exists()
        assert path.name == "raw-2026-02-07.md"
        assert path.parent.name == "raw"

    def test_index_has_frontmatter(self, tmp_path: Path) -> None:
        items = [_make_item()]
        path = build_daily_index(items, tmp_path, target_date=date(2026, 2, 7))
        content = path.read_text()
        assert "date: 2026-02-07" in content
        assert "type: intake-raw-index" in content
        assert "items: 1" in content

    def test_index_groups_by_site(self, tmp_path: Path) -> None:
        items = [
            _make_item(title="A1", url="https://a.com/1", site_name="Blog A"),
            _make_item(title="A2", url="https://a.com/2", site_name="Blog A"),
            _make_item(title="B1", url="https://b.com/1", site_name="Blog B"),
        ]
        path = build_daily_index(items, tmp_path, target_date=date(2026, 2, 7))
        content = path.read_text()
        assert "## Blog A (2)" in content
        assert "## Blog B (1)" in content

    def test_index_contains_titles_and_links(self, tmp_path: Path) -> None:
        items = [_make_item(title="Great Post", url="https://example.com/great")]
        path = build_daily_index(items, tmp_path, target_date=date(2026, 2, 7))
        content = path.read_text()
        assert "[Great Post](https://example.com/great)" in content

    def test_index_contains_author_and_date(self, tmp_path: Path) -> None:
        items = [_make_item(author="Alice")]
        path = build_daily_index(items, tmp_path, target_date=date(2026, 2, 7))
        content = path.read_text()
        assert "by Alice" in content

    def test_index_contains_excerpts(self, tmp_path: Path) -> None:
        items = [_make_item(body="This is important content about testing.")]
        path = build_daily_index(items, tmp_path, target_date=date(2026, 2, 7))
        content = path.read_text()
        assert "This is important content" in content

    def test_index_contains_tags(self, tmp_path: Path) -> None:
        items = [_make_item(tags=["python", "testing", "ci"])]
        path = build_daily_index(items, tmp_path, target_date=date(2026, 2, 7))
        content = path.read_text()
        assert "python" in content

    def test_index_handles_missing_fields(self, tmp_path: Path) -> None:
        item = ContentItem(
            id="minimal",
            source=ContentSource.RSS,
        )
        path = build_daily_index([item], tmp_path, target_date=date(2026, 2, 7))
        content = path.read_text()
        assert "(untitled)" in content

    def test_defaults_to_today(self, tmp_path: Path) -> None:
        path = build_daily_index([_make_item()], tmp_path)
        assert path.name == f"raw-{date.today().isoformat()}.md"

    def test_sorts_sites_by_count(self, tmp_path: Path) -> None:
        items = [
            _make_item(title="X1", url="https://x.com/1", site_name="Few"),
            _make_item(title="Y1", url="https://y.com/1", site_name="Many"),
            _make_item(title="Y2", url="https://y.com/2", site_name="Many"),
            _make_item(title="Y3", url="https://y.com/3", site_name="Many"),
        ]
        path = build_daily_index(items, tmp_path, target_date=date(2026, 2, 7))
        content = path.read_text()
        # "Many" (3 items) should appear before "Few" (1 item)
        assert content.index("## Many") < content.index("## Few")
