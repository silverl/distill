"""Tests for seed ideas — raw thoughts as content source."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from distill.intake.models import ContentSource, ContentType
from distill.intake.seeds import SeedIdea, SeedStore, SEEDS_FILENAME


class TestSeedIdea:
    """Test the SeedIdea model."""

    def test_creation(self):
        seed = SeedIdea(text="AI agents are the new APIs")
        assert seed.text == "AI agents are the new APIs"
        assert seed.used is False
        assert seed.used_in is None
        assert len(seed.id) == 12

    def test_auto_generated_id(self):
        s1 = SeedIdea(text="idea 1")
        s2 = SeedIdea(text="idea 2")
        assert s1.id != s2.id

    def test_tags(self):
        seed = SeedIdea(text="test", tags=["ai", "agents"])
        assert seed.tags == ["ai", "agents"]


class TestSeedStore:
    """Test the SeedStore class."""

    def test_add_seed(self, tmp_path):
        store = SeedStore(tmp_path)
        seed = store.add("AI agents are the new APIs")
        assert seed.text == "AI agents are the new APIs"
        assert not seed.used

    def test_add_with_tags(self, tmp_path):
        store = SeedStore(tmp_path)
        seed = store.add("Test idea", tags=["ai", "tools"])
        assert seed.tags == ["ai", "tools"]

    def test_list_unused(self, tmp_path):
        store = SeedStore(tmp_path)
        store.add("Unused idea")
        s2 = store.add("Used idea")
        store.mark_used(s2.id, "digest-2026-02-07")

        unused = store.list_unused()
        assert len(unused) == 1
        assert unused[0].text == "Unused idea"

    def test_list_all(self, tmp_path):
        store = SeedStore(tmp_path)
        store.add("Idea 1")
        s2 = store.add("Idea 2")
        store.mark_used(s2.id, "digest")

        all_seeds = store.list_all()
        assert len(all_seeds) == 2

    def test_mark_used(self, tmp_path):
        store = SeedStore(tmp_path)
        seed = store.add("Test seed")
        store.mark_used(seed.id, "intake-2026-02-07")

        all_seeds = store.list_all()
        assert all_seeds[0].used is True
        assert all_seeds[0].used_in == "intake-2026-02-07"

    def test_mark_used_nonexistent(self, tmp_path):
        store = SeedStore(tmp_path)
        store.add("Test")
        # Should not raise
        store.mark_used("nonexistent-id", "intake")

    def test_remove(self, tmp_path):
        store = SeedStore(tmp_path)
        seed = store.add("To be removed")
        store.add("Keep this")

        store.remove(seed.id)
        assert len(store.list_all()) == 1
        assert store.list_all()[0].text == "Keep this"

    def test_remove_nonexistent(self, tmp_path):
        store = SeedStore(tmp_path)
        store.add("Test")
        store.remove("nonexistent")
        assert len(store.list_all()) == 1

    def test_persistence(self, tmp_path):
        """Seeds should persist across SeedStore instances."""
        store1 = SeedStore(tmp_path)
        store1.add("Persistent idea")

        store2 = SeedStore(tmp_path)
        seeds = store2.list_all()
        assert len(seeds) == 1
        assert seeds[0].text == "Persistent idea"

    def test_persistence_file_format(self, tmp_path):
        store = SeedStore(tmp_path)
        store.add("Test idea")

        data = json.loads((tmp_path / SEEDS_FILENAME).read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["text"] == "Test idea"

    def test_empty_store(self, tmp_path):
        store = SeedStore(tmp_path)
        assert store.list_all() == []
        assert store.list_unused() == []

    def test_corrupt_file(self, tmp_path):
        (tmp_path / SEEDS_FILENAME).write_text("not json!!!", encoding="utf-8")
        store = SeedStore(tmp_path)
        assert store.list_all() == []

    def test_to_content_items(self, tmp_path):
        store = SeedStore(tmp_path)
        store.add("AI agents as APIs", tags=["ai"])
        store.add("Cost of context switching", tags=["productivity"])

        items = store.to_content_items()
        assert len(items) == 2
        assert all(i.source == ContentSource.SEEDS for i in items)
        assert all(i.content_type == ContentType.POST for i in items)

    def test_to_content_items_only_unused(self, tmp_path):
        store = SeedStore(tmp_path)
        s1 = store.add("Unused seed")
        s2 = store.add("Used seed")
        store.mark_used(s2.id, "digest")

        items = store.to_content_items()
        assert len(items) == 1
        assert items[0].title == "Unused seed"

    def test_to_content_items_mapping(self, tmp_path):
        store = SeedStore(tmp_path)
        seed = store.add("My great idea", tags=["tech"])

        items = store.to_content_items()
        item = items[0]
        assert item.id == f"seed-{seed.id}"
        assert item.title == "My great idea"
        assert item.body == "My great idea"
        assert item.tags == ["tech"]
        assert item.source_id == seed.id
        assert item.metadata["seed_id"] == seed.id
        assert item.metadata["seed_type"] == "idea"

    def test_to_content_items_empty(self, tmp_path):
        store = SeedStore(tmp_path)
        assert store.to_content_items() == []

    def test_multiple_add_and_list(self, tmp_path):
        store = SeedStore(tmp_path)
        for i in range(5):
            store.add(f"Idea {i}")
        assert len(store.list_all()) == 5
        assert len(store.list_unused()) == 5

    def test_mark_used_persists(self, tmp_path):
        store1 = SeedStore(tmp_path)
        seed = store1.add("Idea to use")
        store1.mark_used(seed.id, "digest")

        store2 = SeedStore(tmp_path)
        assert store2.list_all()[0].used is True

    def test_remove_persists(self, tmp_path):
        store1 = SeedStore(tmp_path)
        seed = store1.add("To remove")
        store1.add("To keep")
        store1.remove(seed.id)

        store2 = SeedStore(tmp_path)
        assert len(store2.list_all()) == 1

    def test_tag_handling(self, tmp_path):
        store = SeedStore(tmp_path)
        store.add("No tags")
        store.add("With tags", tags=["a", "b", "c"])

        seeds = store.list_all()
        assert seeds[0].tags == []
        assert seeds[1].tags == ["a", "b", "c"]
