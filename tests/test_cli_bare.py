"""Tests for the bare `distill` command (invoke_without_command)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from distill.cli import app

runner = CliRunner(env={"NO_COLOR": "1", "FORCE_COLOR": None})


class TestInitConfig:
    """Tests for _init_config helper."""

    def test_creates_config_when_missing(self, tmp_path: Path) -> None:
        from distill.cli import _init_config

        _init_config(tmp_path)
        config_path = tmp_path / ".distill.toml"
        assert config_path.exists()
        content = config_path.read_text()
        assert 'sources = ["claude", "codex"]' in content
        assert "use_defaults = true" in content

    def test_does_not_overwrite_existing(self, tmp_path: Path) -> None:
        from distill.cli import _init_config

        config_path = tmp_path / ".distill.toml"
        config_path.write_text("# existing config\n")
        _init_config(tmp_path)
        assert config_path.read_text() == "# existing config\n"


class TestBareCommand:
    """Tests for running `distill` without a subcommand."""

    @patch("distill.cli._run_bare_command")
    def test_bare_invocation_calls_run_bare(self, mock_run: MagicMock) -> None:
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    @patch("distill.cli._run_bare_command")
    def test_bare_with_no_run_flag(self, mock_run: MagicMock) -> None:
        result = runner.invoke(app, ["--no-run"])
        assert result.exit_code == 0
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["no_run"] is True

    @patch("distill.cli._run_bare_command")
    def test_bare_with_no_serve_flag(self, mock_run: MagicMock) -> None:
        result = runner.invoke(app, ["--no-serve"])
        assert result.exit_code == 0
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["no_serve"] is True

    @patch("distill.cli._run_bare_command")
    def test_bare_with_custom_port(self, mock_run: MagicMock) -> None:
        result = runner.invoke(app, ["--port", "5555"])
        assert result.exit_code == 0
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["port"] == 5555

    @patch("distill.cli._run_bare_command")
    def test_default_port_is_4321(self, mock_run: MagicMock) -> None:
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["port"] == 4321

    def test_subcommand_does_not_trigger_bare(self) -> None:
        """Running `distill status` should not trigger the bare command flow."""
        result = runner.invoke(app, ["status", "--output", "/tmp/nonexistent"])
        # status command runs (may show dim output for missing data), but no bare command
        assert result.exit_code == 0


class TestSessionSourcesDefault:
    """Test that the default session sources are claude + codex (not vermas)."""

    def test_default_sources(self) -> None:
        from distill.config import SessionsConfig

        config = SessionsConfig()
        assert config.sources == ["claude", "codex"]
        assert "vermas" not in config.sources

    def test_full_config_default(self) -> None:
        from distill.config import DistillConfig

        config = DistillConfig()
        assert config.sessions.sources == ["claude", "codex"]
