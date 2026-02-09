"""Tests for src/config.py — DistillConfig, TOML loading, CLI overrides."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from distill.config import (
    DistillConfig,
    NotificationConfig,
    load_config,
    merge_cli_overrides,
)


class TestDistillConfigDefaults:
    """Test that DistillConfig has sensible defaults."""

    def test_default_output(self):
        cfg = DistillConfig()
        assert cfg.output.directory == "./insights"

    def test_default_journal(self):
        cfg = DistillConfig()
        assert cfg.journal.style == "dev-journal"
        assert cfg.journal.target_word_count == 600

    def test_default_blog(self):
        cfg = DistillConfig()
        assert cfg.blog.target_word_count == 1200
        assert cfg.blog.include_diagrams is True
        assert cfg.blog.platforms == ["obsidian"]

    def test_default_intake(self):
        cfg = DistillConfig()
        assert cfg.intake.target_word_count == 800
        assert cfg.intake.use_defaults is True

    def test_default_notifications(self):
        cfg = DistillConfig()
        assert cfg.notifications.enabled is True
        assert cfg.notifications.slack_webhook == ""
        assert cfg.notifications.is_configured is False

    def test_default_postiz(self):
        cfg = DistillConfig()
        assert cfg.postiz.url == ""
        assert cfg.postiz.default_type == "draft"


class TestLoadConfig:
    """Test load_config with TOML files."""

    def test_load_from_explicit_path(self, tmp_path):
        toml_path = tmp_path / ".distill.toml"
        toml_path.write_text(
            '[journal]\nstyle = "tech-blog"\ntarget_word_count = 800\n'
        )
        cfg = load_config(toml_path)
        assert cfg.journal.style == "tech-blog"
        assert cfg.journal.target_word_count == 800

    def test_load_missing_path_returns_defaults(self, tmp_path):
        cfg = load_config(tmp_path / "nonexistent.toml")
        assert cfg.journal.style == "dev-journal"

    def test_load_searches_cwd(self, tmp_path, monkeypatch):
        toml_path = tmp_path / ".distill.toml"
        toml_path.write_text('[output]\ndirectory = "/custom/output"\n')
        monkeypatch.chdir(tmp_path)
        # Patch CONFIG_SEARCH_PATHS to include tmp_path
        with patch("distill.config.CONFIG_SEARCH_PATHS", [tmp_path]):
            cfg = load_config()
        assert cfg.output.directory == "/custom/output"

    def test_load_empty_toml(self, tmp_path):
        toml_path = tmp_path / ".distill.toml"
        toml_path.write_text("")
        cfg = load_config(toml_path)
        assert cfg.journal.style == "dev-journal"  # defaults preserved

    def test_load_partial_toml(self, tmp_path):
        toml_path = tmp_path / ".distill.toml"
        toml_path.write_text("[ghost]\nurl = \"https://my-ghost.com\"\n")
        cfg = load_config(toml_path)
        assert cfg.ghost.url == "https://my-ghost.com"
        assert cfg.ghost.admin_api_key == ""  # other defaults preserved

    def test_load_all_sections(self, tmp_path):
        toml_path = tmp_path / ".distill.toml"
        toml_path.write_text(
            "[output]\n"
            'directory = "/out"\n\n'
            "[sessions]\n"
            "include_global = true\n\n"
            "[journal]\n"
            'style = "building-in-public"\n\n'
            "[blog]\n"
            "target_word_count = 2000\n\n"
            "[intake]\n"
            "browser_history = true\n\n"
            "[ghost]\n"
            'url = "https://ghost.example"\n'
            'admin_api_key = "key"\n\n'
            "[reddit]\n"
            'client_id = "rid"\n\n'
            "[youtube]\n"
            'api_key = "ykey"\n\n'
            "[notifications]\n"
            'slack_webhook = "https://hooks.slack.com/test"\n'
        )
        cfg = load_config(toml_path)
        assert cfg.output.directory == "/out"
        assert cfg.sessions.include_global is True
        assert cfg.journal.style == "building-in-public"
        assert cfg.blog.target_word_count == 2000
        assert cfg.intake.browser_history is True
        assert cfg.ghost.url == "https://ghost.example"
        assert cfg.reddit.client_id == "rid"
        assert cfg.youtube.api_key == "ykey"
        assert cfg.notifications.slack_webhook == "https://hooks.slack.com/test"

    def test_invalid_toml_returns_defaults(self, tmp_path):
        toml_path = tmp_path / ".distill.toml"
        toml_path.write_text("this is not valid toml {{{")
        cfg = load_config(toml_path)
        assert cfg.journal.style == "dev-journal"


class TestEnvVarOverrides:
    """Test that environment variables override TOML values."""

    def test_ghost_env_vars(self, tmp_path, monkeypatch):
        toml_path = tmp_path / ".distill.toml"
        toml_path.write_text('[ghost]\nurl = "from-toml"\n')
        monkeypatch.setenv("GHOST_URL", "from-env")
        cfg = load_config(toml_path)
        assert cfg.ghost.url == "from-env"

    def test_slack_webhook_env(self, monkeypatch):
        monkeypatch.setenv("DISTILL_SLACK_WEBHOOK", "https://hooks.slack.com/env")
        with patch("distill.config.CONFIG_SEARCH_PATHS", []):
            cfg = load_config()
        assert cfg.notifications.slack_webhook == "https://hooks.slack.com/env"

    def test_model_env_var_overrides_all_sections(self, monkeypatch):
        monkeypatch.setenv("DISTILL_MODEL", "claude-haiku-4-5-20251001")
        with patch("distill.config.CONFIG_SEARCH_PATHS", []):
            cfg = load_config()
        assert cfg.journal.model == "claude-haiku-4-5-20251001"
        assert cfg.blog.model == "claude-haiku-4-5-20251001"
        assert cfg.intake.model == "claude-haiku-4-5-20251001"

    def test_reddit_env_vars(self, monkeypatch):
        monkeypatch.setenv("REDDIT_CLIENT_ID", "rcid")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "rsecret")
        with patch("distill.config.CONFIG_SEARCH_PATHS", []):
            cfg = load_config()
        assert cfg.reddit.client_id == "rcid"
        assert cfg.reddit.client_secret == "rsecret"

    def test_postiz_env_vars(self, monkeypatch):
        monkeypatch.setenv("POSTIZ_URL", "https://postiz.example")
        monkeypatch.setenv("POSTIZ_API_KEY", "pkey")
        with patch("distill.config.CONFIG_SEARCH_PATHS", []):
            cfg = load_config()
        assert cfg.postiz.url == "https://postiz.example"
        assert cfg.postiz.api_key == "pkey"


class TestMergeCliOverrides:
    """Test CLI flag override merging."""

    def test_override_output_directory(self):
        cfg = DistillConfig()
        merged = merge_cli_overrides(cfg, output_directory="/cli/output")
        assert merged.output.directory == "/cli/output"

    def test_override_journal_style(self):
        cfg = DistillConfig()
        merged = merge_cli_overrides(cfg, journal_style="tech-blog")
        assert merged.journal.style == "tech-blog"

    def test_none_values_ignored(self):
        cfg = DistillConfig()
        merged = merge_cli_overrides(cfg, journal_style=None, blog_words=None)
        assert merged.journal.style == "dev-journal"
        assert merged.blog.target_word_count == 1200

    def test_global_model_override(self):
        cfg = DistillConfig()
        merged = merge_cli_overrides(cfg, model="claude-haiku-4-5-20251001")
        assert merged.journal.model == "claude-haiku-4-5-20251001"
        assert merged.blog.model == "claude-haiku-4-5-20251001"
        assert merged.intake.model == "claude-haiku-4-5-20251001"

    def test_ghost_overrides(self):
        cfg = DistillConfig()
        merged = merge_cli_overrides(
            cfg,
            ghost_url="https://ghost.cli",
            ghost_key="admin:secret",
        )
        assert merged.ghost.url == "https://ghost.cli"
        assert merged.ghost.admin_api_key == "admin:secret"

    def test_postiz_overrides(self):
        cfg = DistillConfig()
        merged = merge_cli_overrides(
            cfg,
            postiz_url="https://postiz.cli",
            postiz_key="pkey",
        )
        assert merged.postiz.url == "https://postiz.cli"
        assert merged.postiz.api_key == "pkey"


class TestAdapters:
    """Test config adapter methods."""

    def test_to_journal_config(self):
        cfg = DistillConfig()
        cfg.journal.style = "tech-blog"
        cfg.journal.target_word_count = 999
        jc = cfg.to_journal_config()
        assert jc.style.value == "tech-blog"
        assert jc.target_word_count == 999

    def test_to_blog_config(self):
        cfg = DistillConfig()
        cfg.blog.target_word_count = 2000
        cfg.blog.include_diagrams = False
        bc = cfg.to_blog_config()
        assert bc.target_word_count == 2000
        assert bc.include_diagrams is False

    def test_to_ghost_config(self):
        cfg = DistillConfig()
        cfg.ghost.url = "https://ghost.test"
        cfg.ghost.admin_api_key = "id:secret"
        gc = cfg.to_ghost_config()
        assert gc.url == "https://ghost.test"
        assert gc.is_configured is True

    def test_to_notification_config(self):
        cfg = DistillConfig()
        cfg.notifications.slack_webhook = "https://hooks.slack.com/x"
        nc = cfg.to_notification_config()
        assert nc.is_configured is True


class TestNotificationConfig:
    """Test NotificationConfig properties."""

    def test_not_configured_by_default(self):
        nc = NotificationConfig()
        assert nc.is_configured is False

    def test_configured_with_slack(self):
        nc = NotificationConfig(slack_webhook="https://hooks.slack.com/x")
        assert nc.is_configured is True

    def test_configured_with_ntfy(self):
        nc = NotificationConfig(ntfy_url="https://ntfy.sh")
        assert nc.is_configured is True

    def test_disabled_overrides_configured(self):
        nc = NotificationConfig(slack_webhook="https://hooks.slack.com/x", enabled=False)
        assert nc.is_configured is False
