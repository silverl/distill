"""Postiz REST client for social media scheduling and posting.

Postiz (https://postiz.com) is a self-hosted social media scheduler
supporting 20+ platforms. This client uses urllib.request (no new deps).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import ssl
import urllib.request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _split_thread(content: str) -> list[dict[str, object]]:
    """Split thread content into separate tweet entries.

    Supports two formats:
    - ``---`` delimiters between tweets (preferred)
    - Numbered tweets (``1/ ...``, ``2/ ...``) as fallback
    """
    stripped = content.strip()

    # Primary: split on --- delimiter lines
    if re.search(r'^\s*---\s*$', stripped, re.MULTILINE):
        parts = re.split(r'\n\s*---\s*\n', stripped)
        tweets = [p.strip() for p in parts if p.strip()]
        if len(tweets) > 1:
            return [{"content": t, "image": []} for t in tweets]

    # Fallback: numbered tweets (1/ ... 2/ ...)
    parts = re.split(r'\n*(?=\d+[/)]\s)', stripped)
    tweets = [re.sub(r'^\d+[/)]\s*', '', p).strip() for p in parts if p.strip()]
    if len(tweets) > 1:
        return [{"content": t, "image": []} for t in tweets]

    # Single post
    return [{"content": stripped, "image": []}]


class PostizConfig(BaseModel):
    """Configuration for the Postiz integration."""

    url: str = ""
    api_key: str = ""
    default_type: str = "draft"  # "draft" | "schedule" | "now"
    slack_channel: str = ""  # Slack channel name (optional)
    schedule_enabled: bool = False
    timezone: str = "America/New_York"
    weekly_time: str = "09:00"
    weekly_day: int = 0  # Monday
    thematic_time: str = "09:00"
    thematic_days: list[int] = [1, 2, 3]  # Tue, Wed, Thu
    intake_time: str = "17:00"

    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.api_key)

    def resolve_post_type(self) -> str:
        """Return 'schedule' if scheduling is enabled, else the default type."""
        if self.schedule_enabled:
            return "schedule"
        return self.default_type

    @classmethod
    def from_env(cls) -> PostizConfig:
        """Create config from environment variables."""
        schedule_raw = os.environ.get("POSTIZ_SCHEDULE_ENABLED", "")
        schedule_enabled = schedule_raw.lower() in ("true", "1", "yes")

        thematic_days_raw = os.environ.get("POSTIZ_THEMATIC_DAYS", "")
        thematic_days = [1, 2, 3]
        if thematic_days_raw:
            thematic_days = [int(d.strip()) for d in thematic_days_raw.split(",") if d.strip()]

        return cls(
            url=os.environ.get("POSTIZ_URL", ""),
            api_key=os.environ.get("POSTIZ_API_KEY", ""),
            default_type=os.environ.get("POSTIZ_DEFAULT_TYPE", "draft"),
            slack_channel=os.environ.get("POSTIZ_SLACK_CHANNEL", ""),
            schedule_enabled=schedule_enabled,
            timezone=os.environ.get("POSTIZ_TIMEZONE", "America/New_York"),
            weekly_time=os.environ.get("POSTIZ_WEEKLY_TIME", "09:00"),
            weekly_day=int(os.environ.get("POSTIZ_WEEKLY_DAY", "0")),
            thematic_time=os.environ.get("POSTIZ_THEMATIC_TIME", "09:00"),
            thematic_days=thematic_days,
            intake_time=os.environ.get("POSTIZ_INTAKE_TIME", "17:00"),
        )


class PostizIntegration(BaseModel):
    """A connected platform account in Postiz."""

    id: str
    name: str
    provider: str
    identifier: str = ""
    profile: str | None = ""


class PostizClient:
    """Thin REST client for the Postiz API.

    Auth: ``Authorization: {apiKey}`` header (raw key, not Bearer).
    Rate limit: 30 req/hour.
    """

    def __init__(self, config: PostizConfig | None = None) -> None:
        self._config = config or PostizConfig.from_env()
        if not self._config.is_configured:
            raise ValueError("Postiz not configured (set POSTIZ_URL and POSTIZ_API_KEY)")
        self._base_url = self._config.url.rstrip("/")
        # Skip TLS verification for localhost (self-signed Caddy certs)
        parsed = urlparse(self._base_url)
        if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
            self._ssl_context: ssl.SSLContext | None = ssl.create_default_context()
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE
        else:
            self._ssl_context = None

    def list_integrations(self) -> list[PostizIntegration]:
        """List all connected platform accounts.

        GET /integrations

        Returns:
            List of PostizIntegration objects.
        """
        data = self._request("GET", "/integrations")
        integrations: list[PostizIntegration] = []
        items = data if isinstance(data, list) else data.get("integrations", [])
        for item in items:
            integrations.append(
                PostizIntegration(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    provider=item.get("providerIdentifier", item.get("provider", "")) or item.get("identifier", ""),
                    identifier=item.get("identifier", ""),
                    profile=item.get("profile", ""),
                )
            )
        return integrations

    def create_post(
        self,
        content: str,
        integration_ids: list[str],
        *,
        post_type: str | None = None,
        scheduled_at: str | None = None,
        provider_type: str | None = None,
    ) -> dict[str, object]:
        """Create a post (draft, scheduled, or immediate).

        POST /posts

        Args:
            content: Post content text.
            integration_ids: List of Postiz integration IDs to post to.
            post_type: "draft", "schedule", or "now". Uses config default.
            scheduled_at: ISO datetime for scheduled posts.
            provider_type: Platform type for settings (e.g., "slack", "x").
                Auto-detected from first integration if not provided.

        Returns:
            API response dict.
        """
        from datetime import datetime, timezone

        ptype = post_type or self._config.default_type

        # Look up integration details for provider type and profile
        integrations = self.list_integrations()
        integ_lookup = {i.id: i for i in integrations}

        posts = []
        for iid in integration_ids:
            integ = integ_lookup.get(iid)
            prov = provider_type or (integ.provider if integ else "") or ""
            settings: dict[str, object] = {"__type": prov}
            # X requires who_can_reply_post
            if prov == "x":
                settings["who_can_reply_post"] = "everyone"
            # Slack requires a channel field — use config, fall back to profile
            if prov == "slack":
                channel = self._config.slack_channel or (integ.profile if integ else "")
                if channel:
                    settings["channel"] = channel
            # X threads: split numbered tweets into separate value entries
            if prov == "x":
                value = _split_thread(content)
            else:
                value = [{"content": content, "image": []}]
            post: dict[str, object] = {
                "integration": {"id": iid},
                "value": value,
                "settings": settings,
            }
            posts.append(post)

        date_str = scheduled_at or datetime.now(timezone.utc).isoformat()
        body: dict[str, object] = {
            "type": ptype,
            "shortLink": False,
            "tags": [],
            "date": date_str,
            "posts": posts,
        }

        return self._request("POST", "/posts", body=body)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Make an authenticated request to the Postiz API.

        Args:
            method: HTTP method.
            path: API path (e.g., "/posts").
            body: Optional JSON body.

        Returns:
            Parsed JSON response.

        Raises:
            PostizAPIError: On HTTP errors.
        """
        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body else None

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": self._config.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method=method,
        )

        try:
            with urllib.request.urlopen(req, timeout=30, context=self._ssl_context) as resp:
                resp_data = resp.read().decode("utf-8")
                if resp_data:
                    return json.loads(resp_data)
                return {}
        except HTTPError as exc:
            resp_body = ""
            with contextlib.suppress(Exception):
                resp_body = exc.read().decode("utf-8")
            raise PostizAPIError(
                status=exc.code,
                message=f"Postiz API error: {exc.code} {exc.reason}",
                body=resp_body,
            ) from exc
        except URLError as exc:
            raise PostizAPIError(
                status=0,
                message=f"Postiz connection error: {exc.reason}",
            ) from exc


class PostizAPIError(Exception):
    """Error from the Postiz API."""

    def __init__(
        self,
        status: int = 0,
        message: str = "",
        body: str = "",
    ) -> None:
        self.status = status
        self.body = body
        super().__init__(message)
