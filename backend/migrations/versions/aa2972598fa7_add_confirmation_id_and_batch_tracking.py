"""add confirmation_id and batch tracking

Revision ID: aa2972598fa7
Revises: 5dfa0f2976f3
Create Date: 2026-08-24 02:35:30.512757

1.9 写入路径(tasks/current.md):

- `meal_entry.confirmation_id`(唯一索引)——每一项食物在被识别出来那一刻由后端生成
  一次、贯穿其整个生命周期的幂等键;网络重试重复 POST 时数据库层兜底防重复插入。
- `chat_message.batch_id`/`kind`/`food_summary_json`——识别结果播报消息
  (kind='recognition')携带整批完整预览快照,收尾总结(kind='recap')复用同一
  batch_id,支撑"刷新后恢复未完成批次"(find_open_batch)。

两张表此刻应为空(1.9 之前没有任何写入路径)。沿用上一条迁移的安全模式:非空就
拒绝执行,不静默丢数据。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa2972598fa7'
down_revision: Union[str, Sequence[str], None] = '5dfa0f2976f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("meal_entry", "chat_message")


def _refuse_if_nonempty(action: str) -> None:
    bind = op.get_bind()
    for table in _TABLES:
        count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        if count != 0:
            raise RuntimeError(
                f"{table} 非空(现有 {count} 行),拒绝{action};需要人工评估数据后再处理"
            )


def upgrade() -> None:
    """Upgrade schema."""
    _refuse_if_nonempty("变更")

    # SQLite 不允许 ADD COLUMN 带 NOT NULL(即使表为空),batch 模式重建整表绕开这个限制
    with op.batch_alter_table("meal_entry", schema=None) as batch_op:
        batch_op.add_column(sa.Column("confirmation_id", sa.Text(), nullable=False))
        batch_op.create_index(
            "ix_meal_entry_confirmation_id", ["confirmation_id"], unique=True
        )

    op.add_column("chat_message", sa.Column("batch_id", sa.Text(), nullable=True))
    op.add_column("chat_message", sa.Column("kind", sa.Text(), nullable=True))
    op.add_column("chat_message", sa.Column("food_summary_json", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    _refuse_if_nonempty("回退")

    op.drop_column("chat_message", "food_summary_json")
    op.drop_column("chat_message", "kind")
    op.drop_column("chat_message", "batch_id")

    with op.batch_alter_table("meal_entry", schema=None) as batch_op:
        batch_op.drop_index("ix_meal_entry_confirmation_id")
        batch_op.drop_column("confirmation_id")
