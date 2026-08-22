"""recreate meal_entry with llm_estimate source_tag

Revision ID: 5dfa0f2976f3
Revises: 50b75ce1aba2
Create Date: 2026-08-22 01:01:58.376570

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5dfa0f2976f3'
down_revision: Union[str, Sequence[str], None] = '50b75ce1aba2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    meal_entry 的 source_tag CHECK 约束需要加入 "llm_estimate"(SPEC §11.1)。SQLite 下
    这个约束是通过 sa.Enum(create_constraint=True) 落的真实 CHECK,重建整表比 batch 模式
    改约束更简单可靠。这条迁移会永久留在项目历史里,不能假设执行者会先手动确认表是空
    的——所以在这里做运行时保护:非空就拒绝执行,不静默丢数据。
    """
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT COUNT(*) FROM meal_entry")).scalar_one()
    if count != 0:
        raise RuntimeError(
            "meal_entry 非空(现有 %d 行),拒绝重建;需要人工评估数据后再处理" % count
        )

    op.drop_table("meal_entry")
    op.create_table(
        "meal_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Text(), nullable=False),
        sa.Column(
            "meal_slot",
            sa.Enum(
                "breakfast",
                "lunch",
                "dinner",
                "other",
                name="ck_meal_entry_meal_slot",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("food_name", sa.Text(), nullable=False),
        sa.Column("quantity", sa.REAL(), nullable=False),
        sa.Column(
            "unit",
            sa.Enum(
                "g",
                "serving",
                name="ck_meal_entry_unit",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("kcal", sa.REAL(), nullable=True),
        sa.Column("carb_g", sa.REAL(), nullable=True),
        sa.Column("protein_g", sa.REAL(), nullable=True),
        sa.Column("fat_g", sa.REAL(), nullable=True),
        sa.Column("fiber_g", sa.REAL(), nullable=True),
        sa.Column(
            "source_tag",
            sa.Enum(
                "chn_table",
                "usda",
                "decompose_estimate",
                "llm_estimate",
                "user_create",
                name="ck_meal_entry_source_tag",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("meal_entry", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_meal_entry_date"), ["date"], unique=False)


def downgrade() -> None:
    """Downgrade schema.

    对称保护:1.9 之后 meal_entry 可能已经写入真实饮食记录,downgrade 会把整表删掉
    重建成旧的 4 值枚举,同样先检查非空并拒绝,不静默丢数据。
    """
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT COUNT(*) FROM meal_entry")).scalar_one()
    if count != 0:
        raise RuntimeError(
            "meal_entry 非空(现有 %d 行),拒绝回退(会丢失已写入的饮食记录)" % count
        )

    with op.batch_alter_table("meal_entry", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_meal_entry_date"))
    op.drop_table("meal_entry")
    op.create_table(
        "meal_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Text(), nullable=False),
        sa.Column(
            "meal_slot",
            sa.Enum(
                "breakfast",
                "lunch",
                "dinner",
                "other",
                name="ck_meal_entry_meal_slot",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("food_name", sa.Text(), nullable=False),
        sa.Column("quantity", sa.REAL(), nullable=False),
        sa.Column(
            "unit",
            sa.Enum(
                "g",
                "serving",
                name="ck_meal_entry_unit",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("kcal", sa.REAL(), nullable=True),
        sa.Column("carb_g", sa.REAL(), nullable=True),
        sa.Column("protein_g", sa.REAL(), nullable=True),
        sa.Column("fat_g", sa.REAL(), nullable=True),
        sa.Column("fiber_g", sa.REAL(), nullable=True),
        sa.Column(
            "source_tag",
            sa.Enum(
                "chn_table",
                "usda",
                "decompose_estimate",
                "user_create",
                name="ck_meal_entry_source_tag",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("meal_entry", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_meal_entry_date"), ["date"], unique=False)
