"""Tests for date range resolution and formatting helpers."""

import datetime as dt
import argparse
import pytest

from mattermost_tldr.cli import date_range_from_args, ts_to_datetime, format_time, format_day_header

# 2026-02-20 is a Friday
FIXED_TODAY = dt.date(2026, 2, 20)


class FrozenDate(dt.date):
    """Subclass of date with a fixed today()."""

    @classmethod
    def today(cls):
        return FIXED_TODAY


@pytest.fixture(autouse=True)
def freeze_today(monkeypatch):
    monkeypatch.setattr("mattermost_tldr.cli.date", FrozenDate)


def make_args(**kwargs):
    defaults = dict(today=False, yesterday=False, this_week=False, last_week=False, days=None, hours=None)
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# date_range_from_args
# ---------------------------------------------------------------------------

class TestDateRangeFromArgs:
    def test_today(self):
        start, end = date_range_from_args(make_args(today=True), {})
        assert start == FIXED_TODAY
        assert end == FIXED_TODAY

    def test_yesterday(self):
        start, end = date_range_from_args(make_args(yesterday=True), {})
        expected = FIXED_TODAY - dt.timedelta(days=1)
        assert start == end == expected

    def test_this_week(self):
        # 2026-02-20 is Friday (weekday=4), so Monday is 2026-02-16
        start, end = date_range_from_args(make_args(this_week=True), {})
        assert start == dt.date(2026, 2, 16)
        assert end == FIXED_TODAY

    def test_last_week(self):
        # Last Monday: 2026-02-09, last Sunday: 2026-02-15
        start, end = date_range_from_args(make_args(last_week=True), {})
        assert start == dt.date(2026, 2, 9)
        assert end == dt.date(2026, 2, 15)

    def test_days(self):
        start, end = date_range_from_args(make_args(days=3), {})
        assert start == FIXED_TODAY - dt.timedelta(days=2)
        assert end == FIXED_TODAY

    def test_days_one(self):
        start, end = date_range_from_args(make_args(days=1), {})
        assert start == end == FIXED_TODAY

    def test_config_fallback_both_dates(self):
        config = {"date_from": "2026-02-01", "date_to": "2026-02-10"}
        start, end = date_range_from_args(make_args(), config)
        assert start == dt.date(2026, 2, 1)
        assert end == dt.date(2026, 2, 10)

    def test_config_fallback_date_to_defaults_to_today(self):
        config = {"date_from": "2026-02-01"}
        start, end = date_range_from_args(make_args(), config)
        assert start == dt.date(2026, 2, 1)
        assert end == FIXED_TODAY

    def test_no_date_and_no_config_exits(self):
        with pytest.raises(SystemExit):
            date_range_from_args(make_args(), {})

    def test_invalid_config_date_exits(self):
        with pytest.raises(SystemExit):
            date_range_from_args(make_args(), {"date_from": "not-a-date"})

    def test_invalid_config_date_to_exits(self):
        with pytest.raises(SystemExit):
            date_range_from_args(make_args(), {"date_from": "2026-02-01", "date_to": "bad"})


# ---------------------------------------------------------------------------
# ts_to_datetime
# ---------------------------------------------------------------------------

class TestTsToDatetime:
    def test_epoch(self):
        result = ts_to_datetime(0)
        assert result == dt.datetime(1970, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc)

    def test_known_timestamp(self):
        expected = dt.datetime(2026, 2, 20, 12, 30, 0, tzinfo=dt.timezone.utc)
        ts_ms = int(expected.timestamp() * 1000)
        result = ts_to_datetime(ts_ms)
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 20
        assert result.hour == 12
        assert result.minute == 30

    def test_returns_utc(self):
        result = ts_to_datetime(0)
        assert result.tzinfo == dt.timezone.utc


# ---------------------------------------------------------------------------
# format_time
# ---------------------------------------------------------------------------

class TestFormatTime:
    def test_pads_single_digit_hour(self):
        d = dt.datetime(2026, 2, 20, 9, 5, 0, tzinfo=dt.timezone.utc)
        assert format_time(d) == "09:05"

    def test_noon(self):
        d = dt.datetime(2026, 2, 20, 12, 0, 0, tzinfo=dt.timezone.utc)
        assert format_time(d) == "12:00"

    def test_midnight(self):
        d = dt.datetime(2026, 2, 20, 0, 0, 0, tzinfo=dt.timezone.utc)
        assert format_time(d) == "00:00"

    def test_end_of_day(self):
        d = dt.datetime(2026, 2, 20, 23, 59, 0, tzinfo=dt.timezone.utc)
        assert format_time(d) == "23:59"


# ---------------------------------------------------------------------------
# format_day_header
# ---------------------------------------------------------------------------

class TestFormatDayHeader:
    def test_friday(self):
        assert format_day_header(dt.date(2026, 2, 20)) == "Friday, 2026-02-20"

    def test_monday(self):
        assert format_day_header(dt.date(2026, 2, 16)) == "Monday, 2026-02-16"

    def test_includes_zero_padded_month_and_day(self):
        assert format_day_header(dt.date(2026, 1, 5)) == "Monday, 2026-01-05"
