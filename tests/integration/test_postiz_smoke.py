"""Smoke tests for Postiz integration against a live instance.

Requires POSTIZ_URL and POSTIZ_API_KEY environment variables.
Skipped automatically if not configured.

Run with:
    source .env  # or export POSTIZ_URL / POSTIZ_API_KEY manually
    uv run pytest tests/integration/test_postiz_smoke.py -v
"""

import os

import pytest
from distill.integrations.mapping import resolve_integration_ids
from distill.integrations.postiz import PostizClient, PostizConfig

POSTIZ_URL = os.environ.get("POSTIZ_URL", "")
POSTIZ_API_KEY = os.environ.get("POSTIZ_API_KEY", "")

skip_reason = "POSTIZ_URL and POSTIZ_API_KEY not set"
requires_postiz = pytest.mark.skipif(
    not (POSTIZ_URL and POSTIZ_API_KEY), reason=skip_reason
)


@requires_postiz
class TestPostizSmoke:
    """Live smoke tests against a running Postiz instance."""

    @pytest.fixture
    def client(self) -> PostizClient:
        config = PostizConfig(url=POSTIZ_URL, api_key=POSTIZ_API_KEY)
        return PostizClient(config)

    def test_connection(self, client: PostizClient):
        """Can we connect and authenticate at all?"""
        integrations = client.list_integrations()
        assert isinstance(integrations, list)
        print(f"\n  Connected to Postiz at {POSTIZ_URL}")
        print(f"  Found {len(integrations)} integrations:")
        for i in integrations:
            print(f"    - {i.name} ({i.provider}) [id={i.id}]")

    def test_list_integrations_returns_objects(self, client: PostizClient):
        """Integrations have required fields."""
        integrations = client.list_integrations()
        for integration in integrations:
            assert integration.id, "Integration missing id"
            assert integration.provider, "Integration missing provider"

    def test_resolve_integration_ids(self, client: PostizClient):
        """Platform mapping resolves against live integrations."""
        platforms = ["twitter", "linkedin", "reddit", "bluesky", "mastodon"]
        result = resolve_integration_ids(client, platforms)
        print(f"\n  Resolved platforms: {list(result.keys())}")
        for platform, ids in result.items():
            print(f"    {platform}: {ids}")
        # We don't assert specific platforms exist - depends on what's connected

    def test_create_draft_post(self, client: PostizClient):
        """Can we create a draft post?"""
        integrations = client.list_integrations()
        if not integrations:
            pytest.skip("No integrations connected in Postiz")

        # Use the first available integration
        integration_id = integrations[0].id
        result = client.create_post(
            "Smoke test from distill integration tests. This is a draft and can be deleted.",
            [integration_id],
            post_type="draft",
        )
        print(f"\n  Created draft post: {result}")
        assert isinstance(result, dict)

    def test_publisher_factory_postiz(self):
        """Factory creates Postiz publishers correctly."""
        from distill.blog.publishers import create_publisher
        from distill.blog.publishers.postiz import PostizBlogPublisher
        from distill.intake.publishers import create_intake_publisher
        from distill.intake.publishers.postiz import PostizIntakePublisher

        blog_pub = create_publisher("postiz")
        assert isinstance(blog_pub, PostizBlogPublisher)

        intake_pub = create_intake_publisher("postiz")
        assert isinstance(intake_pub, PostizIntakePublisher)
