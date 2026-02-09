"""Map distill platform names to Postiz integration IDs."""

from __future__ import annotations

import logging

from distill.integrations.postiz import PostizClient, PostizIntegration

logger = logging.getLogger(__name__)

# Map distill platform names to Postiz provider identifiers
_PLATFORM_TO_PROVIDER: dict[str, list[str]] = {
    "twitter": ["x", "twitter"],
    "linkedin": ["linkedin", "linkedin-page"],
    "reddit": ["reddit"],
    "bluesky": ["bluesky"],
    "mastodon": ["mastodon"],
    "facebook": ["facebook", "facebook-page"],
    "instagram": ["instagram"],
    "threads": ["threads"],
    "tiktok": ["tiktok"],
    "youtube": ["youtube"],
    "pinterest": ["pinterest"],
    "slack": ["slack"],
    "discord": ["discord"],
    "telegram": ["telegram"],
}


def resolve_integration_ids(
    client: PostizClient,
    platforms: list[str],
) -> dict[str, list[str]]:
    """Map distill platform names to Postiz integration IDs.

    Calls ``client.list_integrations()`` and matches by provider name.

    Args:
        client: Authenticated Postiz client.
        platforms: List of distill platform names (e.g., ["twitter", "linkedin"]).

    Returns:
        Dict mapping platform name to list of matching integration IDs.
        Platforms with no matching integrations are omitted.
    """
    integrations = client.list_integrations()

    # Build provider -> integrations lookup
    provider_map: dict[str, list[PostizIntegration]] = {}
    for integration in integrations:
        provider_key = integration.provider.lower()
        provider_map.setdefault(provider_key, []).append(integration)

    result: dict[str, list[str]] = {}
    for platform in platforms:
        platform_lower = platform.lower()
        providers = _PLATFORM_TO_PROVIDER.get(platform_lower, [platform_lower])

        matching_ids: list[str] = []
        for provider in providers:
            for integration in provider_map.get(provider, []):
                if integration.id not in matching_ids:
                    matching_ids.append(integration.id)

        if matching_ids:
            result[platform] = matching_ids
        else:
            logger.warning(
                "No Postiz integration found for platform %r (checked providers: %s)",
                platform,
                ", ".join(providers),
            )

    return result
