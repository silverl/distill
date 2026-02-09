"""Tests for unified memory system."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from distill.memory import (
    DailyEntry,
    EntityRecord,
    MemoryThread,
    PublishedRecord,
    UnifiedMemory,
    load_unified_memory,
    save_unified_memory,
)


class TestUnifiedMemory:
    """Test UnifiedMemory model."""

    def test_empty_memory(self):
        memory = UnifiedMemory()
        assert memory.entries == []
        assert memory.threads == []
        assert memory.entities == {}
        assert memory.published == []

    def test_add_entry(self):
        memory = UnifiedMemory()
        entry = DailyEntry(
            date=date(2026, 2, 7),
            sessions=["Built auth module"],
            reads=["AI agents article"],
            themes=["auth", "AI"],
        )
        memory.add_entry(entry)
        assert len(memory.entries) == 1
        assert memory.entries[0].date == date(2026, 2, 7)

    def test_add_entry_replaces_same_date(self):
        memory = UnifiedMemory()
        memory.add_entry(DailyEntry(date=date(2026, 2, 7), themes=["old"]))
        memory.add_entry(DailyEntry(date=date(2026, 2, 7), themes=["new"]))
        assert len(memory.entries) == 1
        assert memory.entries[0].themes == ["new"]

    def test_entries_sorted(self):
        memory = UnifiedMemory()
        memory.add_entry(DailyEntry(date=date(2026, 2, 5)))
        memory.add_entry(DailyEntry(date=date(2026, 2, 3)))
        memory.add_entry(DailyEntry(date=date(2026, 2, 7)))
        dates = [e.date for e in memory.entries]
        assert dates == [date(2026, 2, 3), date(2026, 2, 5), date(2026, 2, 7)]


class TestMemoryThreads:
    """Test thread tracking."""

    def test_update_threads_new(self):
        memory = UnifiedMemory()
        threads = [
            MemoryThread(
                name="Auth refactor",
                summary="Refactoring auth",
                first_seen=date(2026, 2, 5),
                last_seen=date(2026, 2, 7),
            )
        ]
        memory.update_threads(threads)
        assert len(memory.threads) == 1
        assert memory.threads[0].name == "Auth refactor"

    def test_update_threads_existing(self):
        memory = UnifiedMemory()
        memory.threads = [
            MemoryThread(
                name="Auth refactor",
                summary="Old summary",
                first_seen=date(2026, 2, 5),
                last_seen=date(2026, 2, 5),
                mention_count=1,
            )
        ]
        memory.update_threads([
            MemoryThread(
                name="Auth refactor",
                summary="Updated summary",
                first_seen=date(2026, 2, 5),
                last_seen=date(2026, 2, 7),
            )
        ])
        assert len(memory.threads) == 1
        assert memory.threads[0].summary == "Updated summary"
        assert memory.threads[0].mention_count == 2


class TestEntityTracking:
    """Test entity registry."""

    def test_track_new_entity(self):
        memory = UnifiedMemory()
        memory.track_entity("distill", "project", date(2026, 2, 7), "main project")

        key = "project:distill"
        assert key in memory.entities
        assert memory.entities[key].mention_count == 1

    def test_track_existing_entity(self):
        memory = UnifiedMemory()
        memory.track_entity("python", "technology", date(2026, 2, 5))
        memory.track_entity("python", "technology", date(2026, 2, 7))

        key = "technology:python"
        assert memory.entities[key].mention_count == 2
        assert memory.entities[key].last_seen == date(2026, 2, 7)

    def test_track_entity_context(self):
        memory = UnifiedMemory()
        memory.track_entity("distill", "project", date(2026, 2, 7), "Built session parser")
        assert memory.entities["project:distill"].context == ["Built session parser"]


class TestPublished:
    """Test published record tracking."""

    def test_add_published(self):
        memory = UnifiedMemory()
        memory.add_published(
            PublishedRecord(
                slug="weekly-2026-W06",
                title="Week 6 Review",
                post_type="weekly",
                date=date(2026, 2, 7),
                platforms=["obsidian"],
            )
        )
        assert len(memory.published) == 1

    def test_add_published_replaces(self):
        memory = UnifiedMemory()
        memory.add_published(
            PublishedRecord(
                slug="weekly-2026-W06",
                title="Week 6",
                post_type="weekly",
                date=date(2026, 2, 7),
                platforms=["obsidian"],
            )
        )
        memory.add_published(
            PublishedRecord(
                slug="weekly-2026-W06",
                title="Week 6 Updated",
                post_type="weekly",
                date=date(2026, 2, 7),
                platforms=["obsidian", "ghost"],
            )
        )
        assert len(memory.published) == 1
        assert memory.published[0].title == "Week 6 Updated"


class TestRenderForPrompt:
    """Test rendering memory for LLM prompts."""

    def test_empty_memory(self):
        memory = UnifiedMemory()
        assert memory.render_for_prompt() == ""

    def test_render_all(self):
        memory = UnifiedMemory()
        memory.add_entry(DailyEntry(
            date=date(2026, 2, 7),
            sessions=["Built auth"],
            reads=["AI article"],
            themes=["auth"],
            insights=["Key insight"],
        ))
        memory.threads = [
            MemoryThread(
                name="Auth",
                summary="Working on auth",
                first_seen=date(2026, 2, 5),
                last_seen=date(2026, 2, 7),
            )
        ]
        text = memory.render_for_prompt()
        assert "Memory Context" in text
        assert "Built auth" in text
        assert "AI article" in text
        assert "Ongoing Threads" in text

    def test_render_sessions_focus(self):
        memory = UnifiedMemory()
        memory.add_entry(DailyEntry(
            date=date(2026, 2, 7),
            sessions=["Built auth"],
            reads=["AI article"],
        ))
        text = memory.render_for_prompt(focus="sessions")
        assert "Built auth" in text
        assert "AI article" not in text

    def test_render_intake_focus(self):
        memory = UnifiedMemory()
        memory.add_entry(DailyEntry(
            date=date(2026, 2, 7),
            sessions=["Built auth"],
            reads=["AI article"],
        ))
        text = memory.render_for_prompt(focus="intake")
        assert "AI article" in text
        assert "Built auth" not in text

    def test_render_blog_focus_includes_published(self):
        memory = UnifiedMemory()
        memory.add_entry(DailyEntry(date=date(2026, 2, 7), themes=["test"]))
        memory.add_published(PublishedRecord(
            slug="weekly-W06",
            title="Week 6",
            post_type="weekly",
            date=date(2026, 2, 7),
            platforms=["obsidian"],
        ))
        text = memory.render_for_prompt(focus="blog")
        assert "Recently Published" in text
        assert "Week 6" in text


class TestPruning:
    """Test memory pruning."""

    def test_prune_old_entries(self):
        memory = UnifiedMemory()
        memory.add_entry(DailyEntry(date=date(2026, 1, 1)))
        memory.add_entry(DailyEntry(date=date(2026, 2, 7)))
        memory.prune(keep_days=10)
        assert len(memory.entries) == 1
        assert memory.entries[0].date == date(2026, 2, 7)

    def test_prune_resolved_threads(self):
        memory = UnifiedMemory()
        memory.add_entry(DailyEntry(date=date(2026, 2, 7)))
        memory.threads = [
            MemoryThread(
                name="Old thread",
                summary="Resolved",
                first_seen=date(2026, 1, 1),
                last_seen=date(2026, 1, 5),
                status="resolved",
            ),
            MemoryThread(
                name="Active thread",
                summary="Still going",
                first_seen=date(2026, 2, 5),
                last_seen=date(2026, 2, 7),
                status="active",
            ),
        ]
        memory.prune(keep_days=10)
        assert len(memory.threads) == 1
        assert memory.threads[0].name == "Active thread"

    def test_prune_empty(self):
        memory = UnifiedMemory()
        memory.prune()  # Should not raise


class TestPersistence:
    """Test save and load."""

    def test_save_and_load(self, tmp_path):
        memory = UnifiedMemory()
        memory.add_entry(DailyEntry(
            date=date(2026, 2, 7),
            sessions=["Built session parser"],
            themes=["coding"],
        ))
        memory.threads = [
            MemoryThread(
                name="Auth",
                summary="Auth work",
                first_seen=date(2026, 2, 5),
                last_seen=date(2026, 2, 7),
            )
        ]
        save_unified_memory(memory, tmp_path)

        loaded = load_unified_memory(tmp_path)
        assert len(loaded.entries) == 1
        assert loaded.entries[0].sessions == ["Built session parser"]
        assert len(loaded.threads) == 1

    def test_load_empty(self, tmp_path):
        memory = load_unified_memory(tmp_path)
        assert isinstance(memory, UnifiedMemory)
        assert memory.entries == []

    def test_load_corrupt(self, tmp_path):
        (tmp_path / ".distill-memory.json").write_text("not json!", encoding="utf-8")
        memory = load_unified_memory(tmp_path)
        assert isinstance(memory, UnifiedMemory)


class TestMigration:
    """Test migration from existing memory files."""

    def test_migrate_journal_memory(self, tmp_path):
        journal_dir = tmp_path / "journal"
        journal_dir.mkdir()
        journal_data = {
            "entries": [
                {
                    "date": "2026-02-07",
                    "themes": ["coding"],
                    "key_insights": ["Insight 1"],
                    "decisions_made": ["Decision 1"],
                    "open_questions": ["Question 1"],
                    "tomorrow_intentions": [],
                }
            ],
            "threads": [
                {
                    "name": "Auth work",
                    "summary": "Building auth",
                    "first_mentioned": "2026-02-05",
                    "last_mentioned": "2026-02-07",
                    "status": "open",
                }
            ],
        }
        (journal_dir / ".working-memory.json").write_text(
            json.dumps(journal_data), encoding="utf-8"
        )

        memory = load_unified_memory(tmp_path)
        assert len(memory.entries) == 1
        assert memory.entries[0].themes == ["coding"]
        assert len(memory.threads) == 1

    def test_migrate_intake_memory(self, tmp_path):
        intake_dir = tmp_path / "intake"
        intake_dir.mkdir()
        intake_data = {
            "entries": [
                {
                    "date": "2026-02-07",
                    "themes": ["AI"],
                    "key_items": ["Article 1", "Article 2"],
                    "item_count": 10,
                }
            ],
            "threads": [],
        }
        (intake_dir / ".intake-memory.json").write_text(
            json.dumps(intake_data), encoding="utf-8"
        )

        memory = load_unified_memory(tmp_path)
        assert len(memory.entries) == 1
        assert memory.entries[0].reads == ["Article 1", "Article 2"]

    def test_migrate_blog_memory(self, tmp_path):
        blog_dir = tmp_path / "blog"
        blog_dir.mkdir()
        blog_data = {
            "posts": [
                {
                    "slug": "weekly-2026-W06",
                    "title": "Week 6",
                    "post_type": "weekly",
                    "date": "2026-02-07",
                    "platforms_published": ["obsidian"],
                    "key_points": [],
                    "themes_covered": [],
                }
            ]
        }
        (blog_dir / ".blog-memory.json").write_text(
            json.dumps(blog_data), encoding="utf-8"
        )

        memory = load_unified_memory(tmp_path)
        assert len(memory.published) == 1
        assert memory.published[0].slug == "weekly-2026-W06"

    def test_migrate_all_three(self, tmp_path):
        """Migration merges entries from journal and intake for same date."""
        # Journal memory
        journal_dir = tmp_path / "journal"
        journal_dir.mkdir()
        (journal_dir / ".working-memory.json").write_text(json.dumps({
            "entries": [{"date": "2026-02-07", "themes": ["coding"], "key_insights": ["Insight"]}],
            "threads": [],
        }), encoding="utf-8")

        # Intake memory
        intake_dir = tmp_path / "intake"
        intake_dir.mkdir()
        (intake_dir / ".intake-memory.json").write_text(json.dumps({
            "entries": [{"date": "2026-02-07", "themes": ["AI"], "key_items": ["Article"]}],
            "threads": [],
        }), encoding="utf-8")

        memory = load_unified_memory(tmp_path)
        # Should have merged into one entry for 2026-02-07
        assert len(memory.entries) == 1
        assert memory.entries[0].reads == ["Article"]
