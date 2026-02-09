"""Tests for _atomic_write in core.py."""

from pathlib import Path
from unittest.mock import patch

import pytest
from distill.core import _atomic_write


class TestAtomicWrite:
    def test_writes_file(self, tmp_path):
        target = tmp_path / "test.md"
        _atomic_write(target, "hello world")
        assert target.read_text() == "hello world"

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "sub" / "dir" / "test.md"
        _atomic_write(target, "content")
        assert target.read_text() == "content"

    def test_overwrites_existing(self, tmp_path):
        target = tmp_path / "test.md"
        target.write_text("old content")
        _atomic_write(target, "new content")
        assert target.read_text() == "new content"

    def test_no_temp_file_left_on_success(self, tmp_path):
        target = tmp_path / "test.md"
        _atomic_write(target, "content")
        # Only the target file should exist, no .tmp files
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "test.md"

    def test_no_partial_write_on_failure(self, tmp_path):
        target = tmp_path / "test.md"
        target.write_text("original")

        # Simulate a write failure by making os.replace fail
        with patch("distill.core.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                _atomic_write(target, "new content that should not appear")

        # Original content should be preserved
        assert target.read_text() == "original"

    def test_encoding_utf8(self, tmp_path):
        target = tmp_path / "test.md"
        _atomic_write(target, "café résumé 日本語")
        assert target.read_text(encoding="utf-8") == "café résumé 日本語"
