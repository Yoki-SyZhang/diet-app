from sqlalchemy import REAL, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FoodBaseCn(Base):
    """中国食物成分数据(SPEC §4.4.1,维护模型见 ADR 0005)。表内容是当前锁定版本的
    整体重建结果,不是增量缓存:重新导入时对全部当前锁定的本地来源整表覆盖写入,
    不同旧版本的行不会同时留在表里被查询到。(food_code, source_commit) 的唯一约束
    只防同一次导入内部的重复编码,不代表设计上允许新旧版本长期并存。"""

    __tablename__ = "food_base_cn"
    __table_args__ = (
        UniqueConstraint("food_code", "source_commit", name="uq_food_base_cn_code_commit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    food_code: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    food_name: Mapped[str] = mapped_column(Text, nullable=False)
    edible_pct: Mapped[float | None] = mapped_column(REAL, nullable=True)
    kcal_100g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    carb_100g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    protein_100g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    fat_100g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    fiber_100g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    source_commit: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
