"""归属日纯函数(SPEC §6.1:业务今日 B = date(本地时间 − 2h);附录"归属日规则速查")。

时间来源是"用户所在时区",不是服务器系统时区:以可靠的 UTC 时刻为准,显式 astimezone
到 `settings.user_timezone` 再减偏移量取 date。如果后端部署在和用户不同时区的机器上
(服务器 UTC、用户在中国),用服务器系统本地墙钟算出来的"本地时间"是服务器所在地的,
归属日会算错——所以这里绝不用 naive datetime、绝不读系统时区。

1.10 结转任务/7 天清理边界应复用同一个 `attribution_date()`,不要重新定义时区/偏移量
逻辑(tasks/current.md)。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import settings


def attribution_date(
    now_utc: datetime | None = None,
    *,
    timezone_name: str | None = None,
    offset_hours: float | None = None,
) -> str:
    """业务今日 B = date(用户所在时区的本地时间 − offset_hours),返回 ISO 日期字符串。

    `now_utc` 必须是 tz-aware 的 UTC 时刻(默认取当前时刻);`timezone_name`/
    `offset_hours` 不传时用 `settings.user_timezone`/`settings.attribution_offset_hours`
    (参数主要供测试注入边界场景)。
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        raise ValueError("now_utc 必须是 tz-aware 的 UTC 时刻,不接受 naive datetime")

    tz = ZoneInfo(timezone_name or settings.user_timezone)
    local = now_utc.astimezone(tz)
    offset = offset_hours if offset_hours is not None else settings.attribution_offset_hours
    return (local - timedelta(hours=offset)).date().isoformat()


def utc_now_iso(now_utc: datetime | None = None) -> str:
    """`created_at` 用的 UTC-0 ISO8601 字符串——唯一真时间,不受时区配置影响。"""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        raise ValueError("now_utc 必须是 tz-aware 的 UTC 时刻,不接受 naive datetime")
    return now_utc.astimezone(timezone.utc).isoformat()
