"""Tests for interval / age string parsers used by yt-frames and the cache CLI."""

import pytest

from yt_tools.cli import parse_age
from yt_tools.frames import parse_interval


class TestParseInterval:
    def test_bare_seconds(self):
        assert parse_interval("30") == 30.0

    def test_with_s(self):
        assert parse_interval("30s") == 30.0

    def test_minutes(self):
        assert parse_interval("2m") == 120.0

    def test_minutes_min(self):
        assert parse_interval("2min") == 120.0

    def test_hours(self):
        assert parse_interval("1h") == 3600.0

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_interval("foo")


class TestParseAge:
    def test_days(self):
        assert parse_age("7d") == 7.0

    def test_bare_number_is_days(self):
        assert parse_age("3") == 3.0

    def test_hours(self):
        assert parse_age("12h") == 0.5

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_age("bogus")
