"""当前归属日路由。纯读、不碰数据库。

归属日一律走 `services/attribution.attribution_date()`,这里不重新写时区/偏移逻辑
(SPEC §6.1;1.10 结转任务同样复用它)。
"""

from fastapi import APIRouter

from app.schemas.today import TodayOut
from app.services.attribution import attribution_date

router = APIRouter(tags=["today"])


@router.get("/today", response_model=TodayOut)
def get_today() -> TodayOut:
    return TodayOut(date=attribution_date())
