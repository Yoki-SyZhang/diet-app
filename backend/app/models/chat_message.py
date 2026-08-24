from sqlalchemy import Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChatMessage(Base):
    """对话历史(SPEC §6.4)。保留最近 1 个归属日。"""

    __tablename__ = "chat_message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    image_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    # 批次追踪(1.9,tasks/current.md"未完成批次的恢复"):识别结果播报消息
    # kind='recognition' 携带 batch_id + 整批完整预览快照(food_summary_json);
    # 收尾总结 kind='recap' 复用同一 batch_id 表示"这张卡片关闭了"。普通消息三列皆空。
    batch_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    food_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
