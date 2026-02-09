"""Tests for Postiz scheduling helpers."""

from datetime import datetime
from zoneinfo import ZoneInfo

from distill.integrations.postiz import PostizConfig
from distill.integrations.scheduling import (
    next_intake_slot,
    next_thematic_slot,
    next_weekly_slot,
)

ET = ZoneInfo("America/New_York")


def _config(**overrides: object) -> PostizConfig:
    defaults = {
        "url": "https://postiz.test",
        "api_key": "key",
        "schedule_enabled": True,
        "timezone": "America/New_York",
        "weekly_time": "09:00",
        "weekly_day": 0,
        "thematic_time": "09:00",
        "thematic_days": [1, 2, 3],
        "intake_time": "17:00",
    }
    defaults.update(overrides)
    return PostizConfig(**defaults)


class TestNextWeeklySlot:
    def test_next_monday_from_friday(self):
        # Friday Feb 7, 2026 at 10am ET
        ref = datetime(2026, 2, 7, 10, 0, tzinfo=ET)
        result = next_weekly_slot(_config(), ref)
        assert "2026-02-09" in result  # Next Monday
        assert "09:00:00" in result

    def test_same_day_before_time(self):
        # Monday Feb 9, 2026 at 8am ET — before 9am slot
        ref = datetime(2026, 2, 9, 8, 0, tzinfo=ET)
        result = next_weekly_slot(_config(), ref)
        assert "2026-02-09" in result  # Same Monday
        assert "09:00:00" in result

    def test_same_day_after_time(self):
        # Monday Feb 9, 2026 at 10am ET — after 9am slot
        ref = datetime(2026, 2, 9, 10, 0, tzinfo=ET)
        result = next_weekly_slot(_config(), ref)
        assert "2026-02-16" in result  # Next Monday

    def test_custom_day_wednesday(self):
        # Set weekly_day=2 (Wednesday). From Monday Feb 9.
        ref = datetime(2026, 2, 9, 10, 0, tzinfo=ET)
        result = next_weekly_slot(_config(weekly_day=2), ref)
        assert "2026-02-11" in result  # Wednesday

    def test_custom_time(self):
        ref = datetime(2026, 2, 7, 10, 0, tzinfo=ET)
        result = next_weekly_slot(_config(weekly_time="14:30"), ref)
        assert "14:30:00" in result


class TestNextThematicSlot:
    def test_picks_tuesday(self):
        # Monday Feb 9, 2026
        ref = datetime(2026, 2, 9, 10, 0, tzinfo=ET)
        result = next_thematic_slot(_config(), ref)
        # Should pick Tuesday Feb 10
        assert "2026-02-10" in result
        assert "09:00:00" in result

    def test_skips_used_date(self):
        ref = datetime(2026, 2, 9, 10, 0, tzinfo=ET)
        used = {"2026-02-10"}  # Tuesday taken
        result = next_thematic_slot(_config(), ref, used_dates=used)
        # Should skip to Wednesday Feb 11
        assert "2026-02-11" in result

    def test_skips_multiple_used(self):
        ref = datetime(2026, 2, 9, 10, 0, tzinfo=ET)
        used = {"2026-02-10", "2026-02-11", "2026-02-12"}
        result = next_thematic_slot(_config(), ref, used_dates=used)
        # All Tue/Wed/Thu taken, should go to next week's Tuesday
        assert "2026-02-17" in result

    def test_custom_days(self):
        # Only schedule on Fridays (day 4)
        ref = datetime(2026, 2, 9, 10, 0, tzinfo=ET)
        result = next_thematic_slot(_config(thematic_days=[4]), ref)
        assert "2026-02-13" in result  # Friday


class TestNextIntakeSlot:
    def test_today_if_before_time(self):
        # Feb 9, 2026 at 3pm — before 5pm
        ref = datetime(2026, 2, 9, 15, 0, tzinfo=ET)
        result = next_intake_slot(_config(), ref)
        assert "2026-02-09" in result
        assert "17:00:00" in result

    def test_tomorrow_if_after_time(self):
        # Feb 9, 2026 at 6pm — after 5pm
        ref = datetime(2026, 2, 9, 18, 0, tzinfo=ET)
        result = next_intake_slot(_config(), ref)
        assert "2026-02-10" in result
        assert "17:00:00" in result

    def test_custom_time(self):
        ref = datetime(2026, 2, 9, 15, 0, tzinfo=ET)
        result = next_intake_slot(_config(intake_time="20:00"), ref)
        assert "2026-02-09" in result
        assert "20:00:00" in result
