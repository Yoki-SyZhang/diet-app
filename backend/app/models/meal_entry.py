from sqlalchemy import REAL, Enum, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import MEAL_SLOT_VALUES, SOURCE_TAG_VALUES, UNIT_VALUES


class MealEntry(Base):
    """短期库 · 餐次明细(SPEC §4.1)。保留最近 7 个归属日,结转任务清理。"""

    __tablename__ = "meal_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 幂等键:识别出这一项食物那一刻由后端生成一次,贯穿其整个生命周期(包括修改后),
    # 唯一索引是网络重试防重复插入的数据库层最后防线(1.9,tasks/current.md)
    confirmation_id: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, index=True
    )
    date: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    meal_slot: Mapped[str] = mapped_column(
        Enum(
            *MEAL_SLOT_VALUES,
            name="ck_meal_entry_meal_slot",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
    )
    food_name: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[float] = mapped_column(REAL, nullable=False)
    unit: Mapped[str] = mapped_column(
        Enum(
            *UNIT_VALUES,
            name="ck_meal_entry_unit",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
    )
    kcal: Mapped[float | None] = mapped_column(REAL, nullable=True)
    carb_g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    protein_g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    fat_g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    fiber_g: Mapped[float | None] = mapped_column(REAL, nullable=True)
    source_tag: Mapped[str] = mapped_column(
        Enum(
            *SOURCE_TAG_VALUES,
            name="ck_meal_entry_source_tag",
            native_enum=False,
            create_constraint=True,
        ),
        nullable=False,
    )
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
