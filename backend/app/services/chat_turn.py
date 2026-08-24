"""1.9 编排层(tasks/current.md"LLM 上下文管理"):把"今日对话记录 + 今日明细"拼成
`today_context` 喂给 `parse_diet_text`,并编排新消息/修改重新估算/批次收尾/未完成批次
恢复四个调用点。

上下文最小化原则(SPEC §6.4):每次 LLM 调用只发送完成当前意图所需的信息——
`today_context` 只在"普通录入"环境的新消息解析时携带;修改重新估算/营养估算/批次总结
都刻意不带它。四个调用点之间不共享任何"会话状态",每次都是独立无状态函数调用。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage
from app.models.enums import MealSlot
from app.models.meal_entry import MealEntry
from app.schemas.chat import BatchItemStatus, ConfirmableItem
from app.schemas.diet_parse import Intent, ParsedFoodItem
from app.schemas.food_estimate import ItemEstimateOutcome
from app.schemas.llm_outcome import LlmOutcome
from app.services.chat import list_today_chat_messages, record_chat_message
from app.services.food_estimate import estimate_items
from app.services.llm_client import LlmClient
from app.services.meal_entry_write import list_today_meal_entries
from app.services.nl_parse import parse_diet_text

_MEAL_SLOT_LABELS: dict[str, str] = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "other": "其他",
}

_MISSING = "—"  # 缺失营养素显示"—",不用 0 顶替(AGENTS.md 铁律,喂给模型的数据同样适用)


def meal_slot_label(meal_slot: MealSlot | str) -> str:
    return _MEAL_SLOT_LABELS[str(meal_slot)]


def format_today_conversation(messages: list[ChatMessage]) -> str:
    """纯函数。今日(当前归属日,不是 7 天)全部 chat_message,按发生顺序拼成
    "[用户]/[AI]"轮流的文本;没有对话时返回"(无)"。"""
    if not messages:
        return "(无)"
    prefixes = {"user": "[用户]", "assistant": "[AI]"}
    return "\n".join(f"{prefixes[m.role]} {m.content}" for m in messages)


def _fmt_value(value: float | None) -> str:
    return _MISSING if value is None else format(value, "g")


def format_today_meal_entries_markdown(entries: list[MealEntry]) -> str:
    """纯函数。今日全部 meal_entry → 一张完整 Markdown 表格,列同今日明细 UI
    (餐次/食物/数量/kcal/碳水/蛋白/脂肪/纤维);没有明细时只有表头。"""
    lines = [
        "| 餐次 | 食物 | 数量 | kcal | 碳水(g) | 蛋白质(g) | 脂肪(g) | 纤维(g) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for e in entries:
        lines.append(
            "| "
            + " | ".join(
                [
                    meal_slot_label(e.meal_slot),
                    e.food_name,
                    f"{format(e.quantity, 'g')}{e.unit}",
                    _fmt_value(e.kcal),
                    _fmt_value(e.carb_g),
                    _fmt_value(e.protein_g),
                    _fmt_value(e.fat_g),
                    _fmt_value(e.fiber_g),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def build_today_context(messages: list[ChatMessage], entries: list[MealEntry]) -> str:
    """纯函数。先对话记录、后今日明细表格,顺序固定。每次调用现查现拼,不缓存。"""
    return (
        "今日对话记录:\n"
        f"{format_today_conversation(messages)}\n\n"
        "今日已确认记录的饮食明细:\n"
        f"{format_today_meal_entries_markdown(entries)}"
    )


# ---------------------------------------------------------------------------
# 编排:新消息(普通录入环境)
# ---------------------------------------------------------------------------


@dataclass
class ChatTurnResult:
    user_message: ChatMessage
    assistant_message: ChatMessage
    intent: Intent
    outcome: LlmOutcome | None
    batch_id: str | None  # 产出卡片时才有值
    items: list[ConfirmableItem] = field(default_factory=list)  # 只含估算成功、进卡片的项


def _quantity_label(quantity: float) -> str:
    return f"{format(quantity, 'g')}g"


def _recognition_message_text(
    meal_slot: MealSlot,
    resolved: list[ItemEstimateOutcome],
    failed: list[ItemEstimateOutcome],
) -> str:
    """确定性播报文案:识别到了什么;估算失败的项在这句话里说明原因,不进卡片。"""
    parts: list[str] = []
    if resolved:
        foods = "、".join(
            f"{o.parsed_item.food_name} {_quantity_label(o.parsed_item.quantity)}"
            for o in resolved
        )
        parts.append(
            f"我识别到了({meal_slot_label(meal_slot)}):{foods}。"
            "请在下方卡片里确认或修改。"
        )
    if failed:
        reasons = ";".join(
            f"{o.parsed_item.food_name}({o.message})" for o in failed
        )
        parts.append(f"以下食物这次没能完成估算,不会出现在卡片里:{reasons}。")
    return "\n".join(parts)


async def handle_new_message(
    db: Session, client: LlmClient, user_text: str, *, now_utc: datetime | None = None
) -> ChatTurnResult:
    # ①today_context 先查先拼——此时还没写入这一轮的消息,避免它在 context 和
    # user_text 里重复出现
    messages = list_today_chat_messages(db, now_utc=now_utc)
    entries = list_today_meal_entries(db, now_utc=now_utc)
    today_context = build_today_context(messages, entries)

    # ②先落用户消息(不管后面解析成什么样,用户说过的话都要留在对话里)
    user_message = record_chat_message(db, role="user", content=user_text, now_utc=now_utc)

    # ③解析
    parse_result = await parse_diet_text(client, user_text, today_context=today_context)

    # ④无 outcome 语义的意图:message 就是回应文案
    if parse_result.intent in (Intent.NO_LOG_INTENT, Intent.EDIT_EXISTING_ENTRY):
        assert parse_result.message is not None  # schema 已保证
        assistant_message = record_chat_message(
            db, role="assistant", content=parse_result.message, now_utc=now_utc
        )
        return ChatTurnResult(
            user_message=user_message,
            assistant_message=assistant_message,
            intent=parse_result.intent,
            outcome=None,
            batch_id=None,
        )

    # ⑤解析未成功(追问/服务不可用/契约违规):message 是提示文案
    if parse_result.outcome != LlmOutcome.RESOLVED:
        assert parse_result.message is not None  # schema 已保证
        assistant_message = record_chat_message(
            db, role="assistant", content=parse_result.message, now_utc=now_utc
        )
        return ChatTurnResult(
            user_message=user_message,
            assistant_message=assistant_message,
            intent=parse_result.intent,
            outcome=parse_result.outcome,
            batch_id=None,
        )

    # ⑥resolved:逐项估算,按成功/失败拆分
    assert parse_result.meal_slot is not None  # schema 已保证
    estimates = await estimate_items(client, parse_result.items, parse_result.meal_slot)
    resolved = [o for o in estimates if o.outcome == LlmOutcome.RESOLVED]
    failed = [o for o in estimates if o.outcome != LlmOutcome.RESOLVED]

    content = _recognition_message_text(parse_result.meal_slot, resolved, failed)

    if not resolved:
        # 全部估算失败:播报就是唯一回复,不产出卡片,不进入"解析卡判定中"环境
        assistant_message = record_chat_message(
            db, role="assistant", content=content, now_utc=now_utc
        )
        return ChatTurnResult(
            user_message=user_message,
            assistant_message=assistant_message,
            intent=parse_result.intent,
            outcome=parse_result.outcome,
            batch_id=None,
        )

    # 有至少一项成功:签发 batch_id + 每项 confirmation_id,完整快照随播报消息落库
    batch_id = uuid.uuid4().hex
    confirmable = [
        ConfirmableItem(confirmation_id=uuid.uuid4().hex, outcome=outcome)
        for outcome in resolved
    ]
    food_summary_json = json.dumps(
        [item.model_dump(mode="json") for item in confirmable], ensure_ascii=False
    )
    assistant_message = record_chat_message(
        db,
        role="assistant",
        content=content,
        batch_id=batch_id,
        kind="recognition",
        food_summary_json=food_summary_json,
        now_utc=now_utc,
    )
    return ChatTurnResult(
        user_message=user_message,
        assistant_message=assistant_message,
        intent=parse_result.intent,
        outcome=parse_result.outcome,
        batch_id=batch_id,
        items=confirmable,
    )


# ---------------------------------------------------------------------------
# 编排:修改重新估算(解析卡判定中,批次收尾时逐项调用)
# ---------------------------------------------------------------------------


@dataclass
class ModifyCorrectionResult:
    confirmation_id: str
    success: bool
    outcome: ItemEstimateOutcome | None = None  # success 时有意义
    failure_reason: str | None = None  # 失败时有意义


_PREP_QUANTITY_LABELS = {"raw": "生重", "cooked": "熟重", "ready_to_consume": ""}


def _synthesize_correction_text(
    original_item: ParsedFoodItem, meal_slot: MealSlot, correction_text: str
) -> str:
    prep = _PREP_QUANTITY_LABELS[original_item.preparation_state]
    return (
        f"原来识别的食物:{original_item.food_name},"
        f"{prep}{_quantity_label(original_item.quantity)},"
        f"餐次:{meal_slot_label(meal_slot)}。"
        f"用户对这一项的修正说明:{correction_text}"
    )


async def handle_modify_correction(
    db: Session,
    client: LlmClient,
    original_item: ParsedFoodItem,
    meal_slot: MealSlot,
    correction_text: str,
    confirmation_id: str,
    *,
    now_utc: datetime | None = None,
) -> ModifyCorrectionResult:
    """只关注被修改的这一条目,刻意不带 today_context、不带同批其它食物;全程不写任何
    chat_message——成败都等批次收尾的 recap 一次性说明(tasks/current.md 环境二)。"""
    synthesized = _synthesize_correction_text(original_item, meal_slot, correction_text)
    parse_result = await parse_diet_text(client, synthesized)

    if parse_result.outcome != LlmOutcome.RESOLVED:
        reason = parse_result.message or "没能把这句话理解成对这项食物的修正,请重新描述"
        return ModifyCorrectionResult(
            confirmation_id=confirmation_id, success=False, failure_reason=reason
        )
    if len(parse_result.items) != 1:
        return ModifyCorrectionResult(
            confirmation_id=confirmation_id,
            success=False,
            failure_reason=(
                f"修正结果不明确(解析出 {len(parse_result.items)} 项食物),请重新描述"
            ),
        )

    # meal_slot 固定用传入值:修正的是"这项食物长什么样",不改它属于哪一餐
    estimates = await estimate_items(client, parse_result.items, meal_slot)
    item_outcome = estimates[0]
    if item_outcome.outcome != LlmOutcome.RESOLVED:
        assert item_outcome.message is not None  # schema 已保证
        return ModifyCorrectionResult(
            confirmation_id=confirmation_id,
            success=False,
            failure_reason=item_outcome.message,
        )
    return ModifyCorrectionResult(
        confirmation_id=confirmation_id, success=True, outcome=item_outcome
    )


# ---------------------------------------------------------------------------
# 编排:未完成批次的恢复(纯查询)
# ---------------------------------------------------------------------------


@dataclass
class OpenBatch:
    batch_id: str
    items: list[ConfirmableItem]


def find_open_batch(db: Session, *, now_utc: datetime | None = None) -> OpenBatch | None:
    """今日 chat_message 里找最后一条 kind='recognition':已有同 batch_id 的 recap →
    这批已正常收尾;快照里所有项都已写进今日 meal_entry → 只是 recap 没送达,数据其实
    写完了——两种情况都返回 None,不打扰用户。剩下"识别过但没写完"的项才值得弹提示。"""
    messages = list_today_chat_messages(db, now_utc=now_utc)

    recognition: ChatMessage | None = None
    for message in reversed(messages):
        if message.kind == "recognition":
            recognition = message
            break
    if recognition is None or recognition.batch_id is None:
        return None

    if any(m.kind == "recap" and m.batch_id == recognition.batch_id for m in messages):
        return None

    try:
        raw_items = json.loads(recognition.food_summary_json or "[]")
        items = [ConfirmableItem.model_validate(raw) for raw in raw_items]
    except (json.JSONDecodeError, ValidationError, TypeError):
        # 快照坏了没法重建卡片,当作无未完成批次处理,不让"记录"页因此崩掉
        return None

    written_ids = {
        e.confirmation_id for e in list_today_meal_entries(db, now_utc=now_utc)
    }
    remaining = [item for item in items if item.confirmation_id not in written_ids]
    if not remaining:
        return None
    return OpenBatch(batch_id=recognition.batch_id, items=remaining)


# ---------------------------------------------------------------------------
# 编排:批次收尾总结
# ---------------------------------------------------------------------------

_RECAP_SYSTEM_PROMPT = """你是一个饮食记录助手。刚才用户处理完了一批识别出的食物,下面给你
这批食物的最终结果清单(已记录=真正写进了今天的饮食明细;已放弃=用户决定不记录)。请生成
一句简短、自然、得体的中文总结告诉用户结果,只输出一个合法的 json 对象,结构固定为:
{"summary": "总结文案"}

要求:
- 已记录的食物逐个提到名称和克重(比如"已记录米饭200g、西兰花180g");有热量数值时可以
  顺带总热量。
- 有放弃的项就简单带过("其余已放弃"或点名),没有就不提。
- 不要输出营养建议、不要追问、不要 markdown,就一句话到两句话。
"""


def _fallback_recap_text(items: list[BatchItemStatus]) -> str:
    confirmed = [i for i in items if i.state == "confirmed"]
    abandoned = [i for i in items if i.state == "abandoned"]
    parts: list[str] = []
    if confirmed:
        foods = "、".join(
            f"{i.food_name}{_quantity_label(i.quantity)}"
            + (f"(约{format(i.kcal, 'g')}kcal)" if i.kcal is not None else "")
            for i in confirmed
        )
        parts.append(f"已记录:{foods}。")
    if abandoned:
        foods = "、".join(f"{i.food_name}{_quantity_label(i.quantity)}" for i in abandoned)
        parts.append(f"已放弃:{foods}。")
    return "本轮处理完成。" + "".join(parts)


async def recap_batch_status(
    db: Session,
    client: LlmClient,
    batch_id: str,
    meal_slot: MealSlot,
    items: list[BatchItemStatus],
    *,
    now_utc: datetime | None = None,
) -> ChatMessage:
    """整批结束时调用一次(包括"放弃恢复的旧批次"场景)。只带这一批食物的终态列表,
    不带对话历史、不带今日其它食物;LLM 失败时退化成确定性拼装文案,不留白。"""
    status_lines = []
    for item in items:
        if item.state == "confirmed":
            kcal_part = f",约{format(item.kcal, 'g')}kcal" if item.kcal is not None else ""
            status_lines.append(
                f"- {item.food_name} {_quantity_label(item.quantity)}:已记录{kcal_part}"
            )
        else:
            status_lines.append(
                f"- {item.food_name} {_quantity_label(item.quantity)}:已放弃"
            )
    user_prompt = f"餐次:{meal_slot_label(meal_slot)}\n这批食物的最终结果:\n" + "\n".join(
        status_lines
    )

    content: str | None = None
    llm_result = await client.chat_json(system=_RECAP_SYSTEM_PROMPT, user=user_prompt)
    if llm_result.ok and isinstance(llm_result.parsed, dict):
        summary = llm_result.parsed.get("summary")
        if isinstance(summary, str) and summary.strip():
            content = summary.strip()
    if content is None:
        content = _fallback_recap_text(items)

    return record_chat_message(
        db,
        role="assistant",
        content=content,
        batch_id=batch_id,
        kind="recap",
        now_utc=now_utc,
    )
