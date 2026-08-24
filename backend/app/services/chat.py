"""对话消息读写(1.9,SPEC §6.4)。`chat_message` 是给人看的 UI 展示层,从不整表转发
给模型;"今日"一律指当前归属日(`attribution_date`),不是滚动 24 小时窗口。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage
from app.services.attribution import attribution_date, utc_now_iso


def record_chat_message(
    db: Session,
    *,
    role: Literal["user", "assistant"],
    content: str,
    image_ref: str | None = None,
    batch_id: str | None = None,
    kind: Literal["recognition", "recap"] | None = None,
    food_summary_json: str | None = None,
    now_utc: datetime | None = None,
) -> ChatMessage:
    message = ChatMessage(
        date=attribution_date(now_utc),
        role=role,
        content=content,
        image_ref=image_ref,
        created_at=utc_now_iso(now_utc),
        batch_id=batch_id,
        kind=kind,
        food_summary_json=food_summary_json,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def list_today_chat_messages(db: Session, *, now_utc: datetime | None = None) -> list[ChatMessage]:
    """当前归属日的全部消息,按发生顺序(id 即插入顺序,created_at 同秒时仍稳定)。"""
    today = attribution_date(now_utc)
    return list(
        db.query(ChatMessage).filter(ChatMessage.date == today).order_by(ChatMessage.id).all()
    )
