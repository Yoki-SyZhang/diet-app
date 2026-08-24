"""1.9 对话消息服务:写入字段完整性、归属日过滤(当前归属日,不是 7 天也不是滚动
24 小时)、批次追踪列(batch_id/kind/food_summary_json)的写入与查询。
"""

from datetime import datetime, timezone

from app.services.chat import list_today_chat_messages, record_chat_message

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)  # 上海本地 20:00,归 2026-08-24
YESTERDAY_NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)  # 归 2026-08-23


def test_record_user_message_minimal_fields(db_session):
    message = record_chat_message(db_session, role="user", content="我吃了饭", now_utc=NOW)

    assert message.id is not None
    assert message.date == "2026-08-24"
    assert message.role == "user"
    assert message.content == "我吃了饭"
    assert message.image_ref is None
    assert message.created_at == "2026-08-24T12:00:00+00:00"
    assert message.batch_id is None
    assert message.kind is None
    assert message.food_summary_json is None


def test_record_recognition_message_with_batch_tracking(db_session):
    snapshot = '[{"confirmation_id": "conf-1", "food_name": "熟鸡胸肉"}]'
    message = record_chat_message(
        db_session,
        role="assistant",
        content="我识别到了:熟鸡胸肉 150g",
        batch_id="batch-1",
        kind="recognition",
        food_summary_json=snapshot,
        now_utc=NOW,
    )

    assert message.batch_id == "batch-1"
    assert message.kind == "recognition"
    assert message.food_summary_json == snapshot


def test_record_recap_message_reuses_batch_id(db_session):
    record_chat_message(
        db_session,
        role="assistant",
        content="识别播报",
        batch_id="batch-1",
        kind="recognition",
        food_summary_json="[]",
        now_utc=NOW,
    )
    recap = record_chat_message(
        db_session,
        role="assistant",
        content="已记录熟鸡胸肉150g",
        batch_id="batch-1",
        kind="recap",
        now_utc=NOW,
    )

    assert recap.batch_id == "batch-1"
    assert recap.kind == "recap"
    assert recap.food_summary_json is None


def test_list_today_filters_by_attribution_date(db_session):
    record_chat_message(db_session, role="user", content="昨天的话", now_utc=YESTERDAY_NOW)
    record_chat_message(db_session, role="user", content="今天的话", now_utc=NOW)

    todays = list_today_chat_messages(db_session, now_utc=NOW)

    assert [m.content for m in todays] == ["今天的话"]


def test_list_today_preserves_insertion_order(db_session):
    record_chat_message(db_session, role="user", content="第一句", now_utc=NOW)
    record_chat_message(db_session, role="assistant", content="第二句", now_utc=NOW)
    record_chat_message(db_session, role="user", content="第三句", now_utc=NOW)

    todays = list_today_chat_messages(db_session, now_utc=NOW)

    assert [m.content for m in todays] == ["第一句", "第二句", "第三句"]
    assert [m.role for m in todays] == ["user", "assistant", "user"]
