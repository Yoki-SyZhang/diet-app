"""1.9 归属日纯函数(SPEC §6.1):边界时刻、时区转换正确性、偏移量可配置。

关键验证点:归属日按"用户所在时区"算,不按服务器系统时区——同一个 UTC 时刻传不同
`timezone_name` 必须得到不同归属日,证明确实做了显式时区转换。
"""

from datetime import datetime, timezone

import pytest

from app.config import settings
from app.services.attribution import attribution_date, utc_now_iso

# Asia/Shanghai = UTC+8,固定无夏令时


def _utc(y, m, d, hh, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc)


class TestAttributionBoundary:
    def test_local_0030_belongs_to_previous_day(self):
        # 上海本地 2026-08-24 00:30 → UTC 2026-08-23 16:30;还没到 02:00 切换点,归前一天
        assert (
            attribution_date(_utc(2026, 8, 23, 16, 30), timezone_name="Asia/Shanghai")
            == "2026-08-23"
        )

    def test_local_0230_belongs_to_same_day(self):
        # 上海本地 2026-08-24 02:30 → 已过切换点,归当天
        assert (
            attribution_date(_utc(2026, 8, 23, 18, 30), timezone_name="Asia/Shanghai")
            == "2026-08-24"
        )

    def test_local_exactly_0200_starts_new_day(self):
        # 切换点本身:本地 02:00:00 整,−2h = 00:00:00,已属于新归属日
        assert (
            attribution_date(_utc(2026, 8, 23, 18, 0, 0), timezone_name="Asia/Shanghai")
            == "2026-08-24"
        )

    def test_local_015959_still_previous_day(self):
        assert (
            attribution_date(_utc(2026, 8, 23, 17, 59, 59), timezone_name="Asia/Shanghai")
            == "2026-08-23"
        )

    def test_cross_month_boundary(self):
        # 上海本地 2026-03-01 01:59 → 归 2026-02-28(2026 非闰年)
        assert (
            attribution_date(_utc(2026, 2, 28, 17, 59), timezone_name="Asia/Shanghai")
            == "2026-02-28"
        )

    def test_cross_year_boundary(self):
        # 上海本地 2026-01-01 01:30 → 归 2025-12-31
        assert (
            attribution_date(_utc(2025, 12, 31, 17, 30), timezone_name="Asia/Shanghai")
            == "2025-12-31"
        )


class TestTimezoneSource:
    def test_same_utc_instant_differs_across_timezones(self):
        # 同一 UTC 时刻:上海已过 02:00 切换点、UTC/芝加哥还没到——归属日必须不同,
        # 证明是显式按传入时区转换,不是读服务器系统时区
        instant = _utc(2026, 8, 23, 18, 0)
        assert attribution_date(instant, timezone_name="Asia/Shanghai") == "2026-08-24"
        assert attribution_date(instant, timezone_name="UTC") == "2026-08-23"
        assert attribution_date(instant, timezone_name="America/Chicago") == "2026-08-23"

    def test_default_timezone_comes_from_settings(self, monkeypatch):
        instant = _utc(2026, 8, 23, 18, 0)
        monkeypatch.setattr(settings, "user_timezone", "Asia/Shanghai")
        assert attribution_date(instant) == "2026-08-24"
        monkeypatch.setattr(settings, "user_timezone", "UTC")
        assert attribution_date(instant) == "2026-08-23"

    def test_non_utc_aware_input_is_converted_not_trusted(self):
        # tz-aware 但非 UTC 的时刻也应先统一换算,结果只取决于绝对时刻
        from zoneinfo import ZoneInfo

        shanghai_wall = datetime(2026, 8, 24, 2, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert (
            attribution_date(shanghai_wall, timezone_name="Asia/Shanghai") == "2026-08-24"
        )

    def test_naive_datetime_rejected(self):
        with pytest.raises(ValueError, match="tz-aware"):
            attribution_date(datetime(2026, 8, 24, 2, 0), timezone_name="Asia/Shanghai")


class TestOffsetHours:
    def test_explicit_offset_moves_boundary(self):
        # 上海本地 03:00:offset=2 → 归当天;offset=4 → 还没到 04:00 切换点,归前一天
        instant = _utc(2026, 8, 23, 19, 0)
        assert (
            attribution_date(instant, timezone_name="Asia/Shanghai", offset_hours=2.0)
            == "2026-08-24"
        )
        assert (
            attribution_date(instant, timezone_name="Asia/Shanghai", offset_hours=4.0)
            == "2026-08-23"
        )

    def test_default_offset_comes_from_settings(self, monkeypatch):
        instant = _utc(2026, 8, 23, 19, 0)  # 上海本地 03:00
        monkeypatch.setattr(settings, "attribution_offset_hours", 2.0)
        assert attribution_date(instant, timezone_name="Asia/Shanghai") == "2026-08-24"
        monkeypatch.setattr(settings, "attribution_offset_hours", 4.0)
        assert attribution_date(instant, timezone_name="Asia/Shanghai") == "2026-08-23"

    def test_zero_offset(self):
        # offset=0 退化成"本地自然日"
        instant = _utc(2026, 8, 23, 17, 0)  # 上海本地 2026-08-24 01:00
        assert (
            attribution_date(instant, timezone_name="Asia/Shanghai", offset_hours=0.0)
            == "2026-08-24"
        )


class TestUtcNowIso:
    def test_formats_utc_iso8601(self):
        assert utc_now_iso(_utc(2026, 8, 24, 3, 4, 5)) == "2026-08-24T03:04:05+00:00"

    def test_converts_aware_non_utc_to_utc(self):
        from zoneinfo import ZoneInfo

        shanghai = datetime(2026, 8, 24, 11, 4, 5, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert utc_now_iso(shanghai) == "2026-08-24T03:04:05+00:00"

    def test_naive_datetime_rejected(self):
        with pytest.raises(ValueError, match="tz-aware"):
            utc_now_iso(datetime(2026, 8, 24, 3, 4, 5))

    def test_default_now_is_utc_aware(self):
        value = utc_now_iso()
        assert value.endswith("+00:00")
