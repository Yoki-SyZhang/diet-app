from sqlalchemy import REAL, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DailySummary(Base):
    """长期库 · 每日汇总(SPEC §4.2)。永久保留;聚合指标任一构成项缺失即整体为 null。"""

    __tablename__ = "daily_summary"

    date: Mapped[str] = mapped_column(Text, primary_key=True)
    total_kcal: Mapped[float | None] = mapped_column(REAL, nullable=True)
    total_carb_g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    total_protein_g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    total_fat_g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    total_fiber_g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    bmr_snapshot: Mapped[float | None] = mapped_column(REAL, nullable=True)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
