from sqlalchemy import REAL, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FoodBaseCn(Base):
    """中国食物成分数据(SPEC §4.4.1)。按 (food_code, source_commit) 唯一,
    允许不同锁定 commit 的同一 food_code 并存,不强制覆盖旧版本。"""

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
