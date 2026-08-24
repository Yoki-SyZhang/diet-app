from pydantic import BaseModel


class TodayOut(BaseModel):
    """当前归属日(SPEC §6.1)。前端拿它显示"你正在记哪一天",不自己算——偏移量和
    时区是后端配置,前端复算就成了第二份结转规则。

    1.11/1.12 的 kcal 目标和今日 Δ 也归这个接口,到时候在这里加字段。
    """

    date: str
