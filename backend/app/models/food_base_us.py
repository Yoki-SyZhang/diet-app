from sqlalchemy import REAL, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FoodBaseUs(Base):
    """USDA FoodData Central 本地快照导入(SPEC §4.4.2,选型依据见 ADR 0005)。
    fdc_id 是真自然键;表内容随每次重新导入整体重建,不是运行时按需缓存。"""

    __tablename__ = "food_base_us"

    fdc_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    kcal_100g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    carb_100g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    protein_100g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    fat_100g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    fiber_100g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
