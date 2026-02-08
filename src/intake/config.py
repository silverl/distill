"""Intake pipeline configuration."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field


class RSSConfig(BaseModel):
    """RSS feed configuration."""

    feeds: list[str] = Field(default_factory=list)
    opml_file: str = ""
    feeds_file: str = ""
    fetch_timeout: int = 30
    max_items_per_feed: int = 50
    max_age_days: int = 7
    extract_full_text: bool = False

    @property
    def is_configured(self) -> bool:
        return bool(self.feeds or self.opml_file or self.feeds_file)


class GmailIntakeConfig(BaseModel):
    """Gmail intake configuration."""

    credentials_file: str = ""
    token_file: str = ""
    query: str = "category:promotions OR label:newsletters"

    @property
    def is_configured(self) -> bool:
        return bool(self.credentials_file)


class RedditIntakeConfig(BaseModel):
    """Reddit intake configuration."""

    client_id: str = ""
    client_secret: str = ""
    username: str = ""
    password: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @classmethod
    def from_env(cls) -> RedditIntakeConfig:
        return cls(
            client_id=os.environ.get("REDDIT_CLIENT_ID", ""),
            client_secret=os.environ.get("REDDIT_CLIENT_SECRET", ""),
            username=os.environ.get("REDDIT_USERNAME", ""),
            password=os.environ.get("REDDIT_PASSWORD", ""),
        )


class BrowserIntakeConfig(BaseModel):
    """Browser history intake configuration."""

    browsers: list[str] = Field(default_factory=lambda: ["chrome"])
    min_visit_duration_seconds: int = 30
    domain_allowlist: list[str] = Field(default_factory=list)
    domain_blocklist: list[str] = Field(
        default_factory=lambda: [
            "google.com",
            "localhost",
            "github.com",
            "stackoverflow.com",
        ]
    )

    @property
    def is_configured(self) -> bool:
        return bool(self.browsers)


class LinkedInIntakeConfig(BaseModel):
    """LinkedIn GDPR export configuration."""

    export_path: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.export_path)


class SubstackIntakeConfig(BaseModel):
    """Substack newsletter configuration."""

    blog_urls: list[str] = Field(default_factory=list)

    @property
    def is_configured(self) -> bool:
        return bool(self.blog_urls)


class YouTubeIntakeConfig(BaseModel):
    """YouTube intake configuration."""

    api_key: str = ""
    credentials_file: str = ""
    token_file: str = ""
    fetch_transcripts: bool = True

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key or self.credentials_file)

    @classmethod
    def from_env(cls) -> YouTubeIntakeConfig:
        return cls(
            api_key=os.environ.get("YOUTUBE_API_KEY", ""),
        )


class TwitterIntakeConfig(BaseModel):
    """Twitter/X intake configuration."""

    export_path: str = ""
    nitter_feeds: list[str] = Field(default_factory=list)

    @property
    def is_configured(self) -> bool:
        return bool(self.export_path or self.nitter_feeds)


class SessionIntakeConfig(BaseModel):
    """Session intake configuration."""

    session_dirs: list[str] = Field(default_factory=list)
    include_global: bool = False
    sources: list[str] = Field(default_factory=lambda: ["claude", "codex"])

    @property
    def is_configured(self) -> bool:
        return True  # sessions are always available locally


class IntakeConfig(BaseModel):
    """Top-level intake configuration."""

    rss: RSSConfig = Field(default_factory=RSSConfig)
    gmail: GmailIntakeConfig = Field(default_factory=GmailIntakeConfig)
    reddit: RedditIntakeConfig = Field(default_factory=RedditIntakeConfig)
    browser: BrowserIntakeConfig = Field(default_factory=BrowserIntakeConfig)
    linkedin: LinkedInIntakeConfig = Field(default_factory=LinkedInIntakeConfig)
    substack: SubstackIntakeConfig = Field(default_factory=SubstackIntakeConfig)
    youtube: YouTubeIntakeConfig = Field(default_factory=YouTubeIntakeConfig)
    twitter: TwitterIntakeConfig = Field(default_factory=TwitterIntakeConfig)
    session: SessionIntakeConfig = Field(default_factory=SessionIntakeConfig)

    model: str | None = None
    claude_timeout: int = 180
    target_word_count: int = 800

    domain_blocklist: list[str] = Field(default_factory=lambda: ["google.com", "localhost"])
    min_word_count: int = 50
    max_items_per_source: int = 50
