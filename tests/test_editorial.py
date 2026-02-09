"""Tests for editorial notes store."""

import json
from pathlib import Path

from distill.editorial import EditorialNote, EditorialStore


class TestEditorialStore:
    def test_add_note(self, tmp_path: Path):
        store = EditorialStore(tmp_path)
        note = store.add("Emphasize fan-in pattern")

        assert note.text == "Emphasize fan-in pattern"
        assert note.target == ""
        assert not note.used
        assert len(note.id) == 12

    def test_add_note_with_target(self, tmp_path: Path):
        store = EditorialStore(tmp_path)
        note = store.add("Focus on agent spawning", target="week:2026-W06")

        assert note.target == "week:2026-W06"

    def test_persists_to_disk(self, tmp_path: Path):
        store = EditorialStore(tmp_path)
        store.add("Note 1")
        store.add("Note 2")

        # Reload from disk
        store2 = EditorialStore(tmp_path)
        assert len(store2.list_all()) == 2
        assert store2.list_all()[0].text == "Note 1"

    def test_list_active_returns_unused(self, tmp_path: Path):
        store = EditorialStore(tmp_path)
        n1 = store.add("Active note")
        n2 = store.add("Used note")
        store.mark_used(n2.id)

        active = store.list_active()
        assert len(active) == 1
        assert active[0].id == n1.id

    def test_list_active_filters_by_target(self, tmp_path: Path):
        store = EditorialStore(tmp_path)
        store.add("Global note")
        store.add("Week 6 note", target="week:2026-W06")
        store.add("Week 7 note", target="week:2026-W07")

        active = store.list_active(target="week:2026-W06")
        texts = {n.text for n in active}
        assert "Global note" in texts  # global notes always included
        assert "Week 6 note" in texts
        assert "Week 7 note" not in texts

    def test_list_active_no_target_returns_all_unused(self, tmp_path: Path):
        store = EditorialStore(tmp_path)
        store.add("Global note")
        store.add("Targeted note", target="week:2026-W06")

        active = store.list_active()
        assert len(active) == 2

    def test_mark_used(self, tmp_path: Path):
        store = EditorialStore(tmp_path)
        note = store.add("Will be used")
        store.mark_used(note.id)

        reloaded = EditorialStore(tmp_path)
        assert reloaded.list_all()[0].used is True

    def test_remove(self, tmp_path: Path):
        store = EditorialStore(tmp_path)
        n1 = store.add("Keep this")
        n2 = store.add("Remove this")
        store.remove(n2.id)

        assert len(store.list_all()) == 1
        assert store.list_all()[0].id == n1.id

    def test_render_for_prompt_empty(self, tmp_path: Path):
        store = EditorialStore(tmp_path)
        assert store.render_for_prompt() == ""

    def test_render_for_prompt(self, tmp_path: Path):
        store = EditorialStore(tmp_path)
        store.add("Emphasize the fan-in pattern")
        store.add("Highlight agent spawning")

        rendered = store.render_for_prompt()
        assert "## Editorial Direction" in rendered
        assert "- Emphasize the fan-in pattern" in rendered
        assert "- Highlight agent spawning" in rendered

    def test_render_for_prompt_with_target(self, tmp_path: Path):
        store = EditorialStore(tmp_path)
        store.add("Global note")
        store.add("Week 6 specific", target="week:2026-W06")
        store.add("Week 7 specific", target="week:2026-W07")

        rendered = store.render_for_prompt(target="week:2026-W06")
        assert "Global note" in rendered
        assert "Week 6 specific" in rendered
        assert "Week 7 specific" not in rendered

    def test_render_excludes_used(self, tmp_path: Path):
        store = EditorialStore(tmp_path)
        n1 = store.add("Active")
        n2 = store.add("Used")
        store.mark_used(n2.id)

        rendered = store.render_for_prompt()
        assert "Active" in rendered
        assert "Used" not in rendered

    def test_corrupt_file_starts_fresh(self, tmp_path: Path):
        notes_path = tmp_path / ".distill-notes.json"
        notes_path.write_text("not valid json", encoding="utf-8")

        store = EditorialStore(tmp_path)
        assert len(store.list_all()) == 0

    def test_empty_dir_no_crash(self, tmp_path: Path):
        store = EditorialStore(tmp_path)
        assert len(store.list_all()) == 0
        assert store.render_for_prompt() == ""
