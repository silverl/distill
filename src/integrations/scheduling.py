"""Scheduling helpers for Postiz post timing.

Pure functions that compute the next available time slot for each post type
based on PostizConfig scheduling settings. Uses ``zoneinfo.ZoneInfo`` (stdlib).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from distill.integrations.postiz import PostizConfig


def _parse_time(time_str: str) -> time:
    """Parse an 'HH:MM' string into a ``time`` object."""
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))


def next_weekly_slot(config: PostizConfig, reference: datetime | None = None) -> str:
    """Compute the next weekly post slot as an ISO datetime string.

    Returns the next occurrence of ``config.weekly_day`` at ``config.weekly_time``
    in the configured timezone. If the slot is in the past for this week,
    advances to next week.

    Args:
        config: Postiz configuration with scheduling fields.
        reference: Reference datetime (defaults to now in config timezone).

    Returns:
        ISO 8601 datetime string with timezone offset.
    """
    tz = ZoneInfo(config.timezone)
    now = reference or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)

    target_time = _parse_time(config.weekly_time)

    # Days until target weekday (0=Mon)
    days_ahead = config.weekly_day - now.weekday()
    if days_ahead < 0:
        days_ahead += 7

    target = now.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)
    target += timedelta(days=days_ahead)

    # If same day but time already passed, go to next week
    if days_ahead == 0 and target <= now:
        target += timedelta(weeks=1)

    return target.isoformat()


def next_thematic_slot(
    config: PostizConfig,
    reference: datetime | None = None,
    used_dates: set[str] | None = None,
) -> str:
    """Compute the next thematic post slot, skipping already-used dates.

    Cycles through ``config.thematic_days`` (e.g. Tue/Wed/Thu) and picks the
    next available day that isn't in ``used_dates``.

    Args:
        config: Postiz configuration with scheduling fields.
        reference: Reference datetime (defaults to now in config timezone).
        used_dates: Set of ISO date strings (YYYY-MM-DD) already scheduled.

    Returns:
        ISO 8601 datetime string with timezone offset.
    """
    tz = ZoneInfo(config.timezone)
    now = reference or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)

    used = used_dates or set()
    target_time = _parse_time(config.thematic_time)

    # Search up to 4 weeks ahead
    for day_offset in range(1, 29):
        candidate = now + timedelta(days=day_offset)
        if candidate.weekday() not in config.thematic_days:
            continue
        date_str = candidate.strftime("%Y-%m-%d")
        if date_str in used:
            continue
        slot = candidate.replace(
            hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0
        )
        return slot.isoformat()

    # Fallback: search further ahead (up to 8 weeks)
    for day_offset in range(29, 57):
        candidate = now + timedelta(days=day_offset)
        if candidate.weekday() not in config.thematic_days:
            continue
        date_str = candidate.strftime("%Y-%m-%d")
        if date_str in used:
            continue
        slot = candidate.replace(
            hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0
        )
        return slot.isoformat()

    # Last resort: tomorrow at thematic time
    fallback = now + timedelta(days=1)
    fallback = fallback.replace(
        hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0
    )
    return fallback.isoformat()


def next_intake_slot(config: PostizConfig, reference: datetime | None = None) -> str:
    """Compute the next intake digest slot (same-day evening or next day).

    If the configured intake time hasn't passed yet today, schedules for today.
    Otherwise, schedules for tomorrow at the intake time.

    Args:
        config: Postiz configuration with scheduling fields.
        reference: Reference datetime (defaults to now in config timezone).

    Returns:
        ISO 8601 datetime string with timezone offset.
    """
    tz = ZoneInfo(config.timezone)
    now = reference or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)

    target_time = _parse_time(config.intake_time)
    slot = now.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)

    if slot <= now:
        slot += timedelta(days=1)

    return slot.isoformat()
