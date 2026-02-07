"""Configuration models for journal generation."""

from enum import Enum

from pydantic import BaseModel


class JournalStyle(str, Enum):
    """Available journal writing styles."""

    DEV_JOURNAL = "dev-journal"
    TECH_BLOG = "tech-blog"
    TEAM_UPDATE = "team-update"
    BUILDING_IN_PUBLIC = "building-in-public"


class JournalConfig(BaseModel):
    """Configuration for journal entry generation."""

    style: JournalStyle = JournalStyle.DEV_JOURNAL
    max_sessions_per_entry: int = 20
    target_word_count: int = 600
    include_metrics: bool = True
    claude_timeout: int = 120
    model: str | None = None
    memory_window_days: int = 7
