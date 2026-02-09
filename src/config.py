"""Unified configuration loaded from .distill.toml, env vars, and CLI flags.

Loading order: defaults → TOML file → env vars → CLI flags.
"""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

CONFIG_FILENAME = ".distill.toml"
CONFIG_SEARCH_PATHS = [
    Path("."),
    Path.home() / ".config" / "distill",
]


class ProjectConfig(BaseModel):
    """Single project description for LLM context injection."""

    name: str
    description: str
    url: str = ""
    tags: list[str] = Field(default_factory=list)


class OutputConfig(BaseModel):
    """[output] section."""

    directory: str = "./insights"


class SessionsConfig(BaseModel):
    """[sessions] section."""

    sources: list[str] = Field(default_factory=lambda: ["claude", "codex"])
    include_global: bool = False
    since_days: int = 2


class JournalSectionConfig(BaseModel):
    """[journal] section."""

    style: str = "dev-journal"
    target_word_count: int = 600
    model: str | None = None
    memory_window_days: int = 7


class BlogSectionConfig(BaseModel):
    """[blog] section."""

    target_word_count: int = 1200
    include_diagrams: bool = True
    model: str | None = None
    platforms: list[str] = Field(default_factory=lambda: ["obsidian"])


class IntakeSectionConfig(BaseModel):
    """[intake] section."""

    feeds_file: str = ""
    opml_file: str = ""
    use_defaults: bool = True
    browser_history: bool = False
    substack_blogs: list[str] = Field(default_factory=list)
    rss_feeds: list[str] = Field(default_factory=list)
    target_word_count: int = 800
    model: str | None = None
    publishers: list[str] = Field(default_factory=lambda: ["obsidian"])


class GhostSectionConfig(BaseModel):
    """[ghost] section."""

    url: str = ""
    admin_api_key: str = ""
    newsletter_slug: str = ""
    auto_publish: bool = True


class RedditSectionConfig(BaseModel):
    """[reddit] section."""

    client_id: str = ""
    client_secret: str = ""
    username: str = ""


class YouTubeSectionConfig(BaseModel):
    """[youtube] section."""

    api_key: str = ""


class PostizSectionConfig(BaseModel):
    """[postiz] section."""

    url: str = ""
    api_key: str = ""
    default_type: str = "draft"
    schedule_enabled: bool = False
    timezone: str = "America/New_York"
    weekly_time: str = "09:00"
    weekly_day: int = 0
    thematic_time: str = "09:00"
    thematic_days: list[int] = Field(default_factory=lambda: [1, 2, 3])
    intake_time: str = "17:00"
    slack_channel: str = ""


class NotificationConfig(BaseModel):
    """[notifications] section."""

    slack_webhook: str = ""
    ntfy_url: str = ""
    ntfy_topic: str = "distill"
    enabled: bool = True

    @property
    def is_configured(self) -> bool:
        return self.enabled and bool(self.slack_webhook or self.ntfy_url)


class DistillConfig(BaseModel):
    """Top-level configuration model for the entire distill pipeline."""

    output: OutputConfig = Field(default_factory=OutputConfig)
    sessions: SessionsConfig = Field(default_factory=SessionsConfig)
    journal: JournalSectionConfig = Field(default_factory=JournalSectionConfig)
    blog: BlogSectionConfig = Field(default_factory=BlogSectionConfig)
    intake: IntakeSectionConfig = Field(default_factory=IntakeSectionConfig)
    ghost: GhostSectionConfig = Field(default_factory=GhostSectionConfig)
    reddit: RedditSectionConfig = Field(default_factory=RedditSectionConfig)
    youtube: YouTubeSectionConfig = Field(default_factory=YouTubeSectionConfig)
    postiz: PostizSectionConfig = Field(default_factory=PostizSectionConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    projects: list[ProjectConfig] = Field(default_factory=list)

    def render_project_context(self) -> str:
        """Render project descriptions for LLM prompt injection."""
        if not self.projects:
            return ""
        lines = ["## Project Context", ""]
        for p in self.projects:
            lines.append(f"**{p.name}**: {p.description}")
            if p.url:
                lines.append(f"  URL: {p.url}")
        return "\n".join(lines)

    def to_journal_config(self) -> object:
        """Convert to JournalConfig for the journal pipeline."""
        from distill.journal.config import JournalConfig, JournalStyle

        return JournalConfig(
            style=JournalStyle(self.journal.style),
            target_word_count=self.journal.target_word_count,
            model=self.journal.model,
            memory_window_days=self.journal.memory_window_days,
        )

    def to_blog_config(self) -> object:
        """Convert to BlogConfig for the blog pipeline."""
        from distill.blog.config import BlogConfig

        return BlogConfig(
            target_word_count=self.blog.target_word_count,
            include_diagrams=self.blog.include_diagrams,
            model=self.blog.model,
        )

    def to_intake_config(self) -> object:
        """Convert to IntakeConfig for the intake pipeline."""
        from distill.intake.config import IntakeConfig, RSSConfig

        return IntakeConfig(
            rss=RSSConfig(
                feeds_file=self.intake.feeds_file,
                opml_file=self.intake.opml_file,
            ),
            model=self.intake.model,
            target_word_count=self.intake.target_word_count,
        )

    def to_ghost_config(self) -> object:
        """Convert to GhostConfig for Ghost CMS publishing."""
        from distill.blog.config import GhostConfig

        return GhostConfig(
            url=self.ghost.url,
            admin_api_key=self.ghost.admin_api_key,
            newsletter_slug=self.ghost.newsletter_slug,
            auto_publish=self.ghost.auto_publish,
        )

    def to_notification_config(self) -> NotificationConfig:
        """Return the notification config section."""
        return self.notifications


def load_config(path: str | Path | None = None) -> DistillConfig:
    """Load configuration from a TOML file.

    Search order:
    1. Explicit path (if provided)
    2. .distill.toml in CWD
    3. ~/.config/distill/config.toml

    Then overlay environment variables.

    Args:
        path: Explicit path to a TOML file.

    Returns:
        Merged DistillConfig.
    """
    data: dict[str, object] = {}

    if path is not None:
        toml_path = Path(path)
        if toml_path.exists():
            data = _load_toml(toml_path)
        else:
            logger.warning("Config file not found: %s", toml_path)
    else:
        for search_dir in CONFIG_SEARCH_PATHS:
            candidate = search_dir / CONFIG_FILENAME
            if candidate.exists():
                data = _load_toml(candidate)
                logger.info("Loaded config from %s", candidate)
                break
        # Also check ~/.config/distill/config.toml
        global_config = Path.home() / ".config" / "distill" / "config.toml"
        if not data and global_config.exists():
            data = _load_toml(global_config)
            logger.info("Loaded config from %s", global_config)

    config = DistillConfig.model_validate(data) if data else DistillConfig()

    # Overlay environment variables
    config = _apply_env_vars(config)

    return config


def merge_cli_overrides(config: DistillConfig, **cli_kwargs: object) -> DistillConfig:
    """Overlay explicitly-set CLI flags onto the config.

    Only overrides values where the CLI flag was explicitly provided
    (i.e., not None).

    Args:
        config: Base config.
        **cli_kwargs: CLI flag values. Keys use dot notation flattened
            with underscores (e.g., ``output_directory``, ``journal_style``).

    Returns:
        Updated config with CLI overrides applied.
    """
    data = config.model_dump()

    mapping: dict[str, tuple[str, str]] = {
        "output_directory": ("output", "directory"),
        "journal_style": ("journal", "style"),
        "journal_words": ("journal", "target_word_count"),
        "journal_model": ("journal", "model"),
        "blog_words": ("blog", "target_word_count"),
        "blog_model": ("blog", "model"),
        "blog_platforms": ("blog", "platforms"),
        "intake_words": ("intake", "target_word_count"),
        "intake_model": ("intake", "model"),
        "intake_feeds_file": ("intake", "feeds_file"),
        "ghost_url": ("ghost", "url"),
        "ghost_key": ("ghost", "admin_api_key"),
        "ghost_newsletter": ("ghost", "newsletter_slug"),
        "postiz_url": ("postiz", "url"),
        "postiz_key": ("postiz", "api_key"),
        "model": ("journal", "model"),  # global --model override
    }

    for key, value in cli_kwargs.items():
        if value is None:
            continue
        if key in mapping:
            section, field = mapping[key]
            data[section][field] = value
        # Global model overrides all sections
        if key == "model" and value is not None:
            for section in ("journal", "blog", "intake"):
                data[section]["model"] = value

    return DistillConfig.model_validate(data)


def _load_toml(path: Path) -> dict[str, object]:
    """Load a TOML file and return the data dict."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        logger.warning("Failed to parse %s: %s", path, exc)
        return {}


def _apply_env_vars(config: DistillConfig) -> DistillConfig:
    """Apply environment variable overrides to config."""
    data = config.model_dump()

    env_mapping: dict[str, tuple[str, str]] = {
        "DISTILL_OUTPUT_DIR": ("output", "directory"),
        "DISTILL_MODEL": ("journal", "model"),
        "GHOST_URL": ("ghost", "url"),
        "GHOST_ADMIN_API_KEY": ("ghost", "admin_api_key"),
        "GHOST_NEWSLETTER_SLUG": ("ghost", "newsletter_slug"),
        "REDDIT_CLIENT_ID": ("reddit", "client_id"),
        "REDDIT_CLIENT_SECRET": ("reddit", "client_secret"),
        "REDDIT_USERNAME": ("reddit", "username"),
        "YOUTUBE_API_KEY": ("youtube", "api_key"),
        "DISTILL_SLACK_WEBHOOK": ("notifications", "slack_webhook"),
        "DISTILL_NTFY_URL": ("notifications", "ntfy_url"),
        "DISTILL_NTFY_TOPIC": ("notifications", "ntfy_topic"),
        "POSTIZ_URL": ("postiz", "url"),
        "POSTIZ_API_KEY": ("postiz", "api_key"),
        "POSTIZ_SLACK_CHANNEL": ("postiz", "slack_channel"),
    }

    for env_var, (section, field) in env_mapping.items():
        value = os.environ.get(env_var)
        if value is not None:
            data[section][field] = value

    # Postiz scheduling env vars (non-string types)
    sched_raw = os.environ.get("POSTIZ_SCHEDULE_ENABLED")
    if sched_raw is not None:
        data["postiz"]["schedule_enabled"] = sched_raw.lower() in ("true", "1", "yes")
    tz_raw = os.environ.get("POSTIZ_TIMEZONE")
    if tz_raw is not None:
        data["postiz"]["timezone"] = tz_raw
    for key, field in [
        ("POSTIZ_WEEKLY_TIME", "weekly_time"),
        ("POSTIZ_THEMATIC_TIME", "thematic_time"),
        ("POSTIZ_INTAKE_TIME", "intake_time"),
    ]:
        val = os.environ.get(key)
        if val is not None:
            data["postiz"][field] = val
    day_raw = os.environ.get("POSTIZ_WEEKLY_DAY")
    if day_raw is not None:
        data["postiz"]["weekly_day"] = int(day_raw)
    tdays_raw = os.environ.get("POSTIZ_THEMATIC_DAYS")
    if tdays_raw is not None:
        data["postiz"]["thematic_days"] = [
            int(d.strip()) for d in tdays_raw.split(",") if d.strip()
        ]

    # Global model env var overrides all sections
    global_model = os.environ.get("DISTILL_MODEL")
    if global_model:
        for section in ("journal", "blog", "intake"):
            data[section]["model"] = global_model

    return DistillConfig.model_validate(data)
