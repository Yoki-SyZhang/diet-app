"""1.9 today_context 三个纯函数:对话顺序/角色前缀、明细表格列与缺失值口径
(显示"—"不是 0/空,AGENTS.md 铁律同样适用于喂给模型的数据)、两部分拼装顺序固定。
不碰数据库——ChatMessage/MealEntry 直接内存构造。
"""

from app.models.chat_message import ChatMessage
from app.models.meal_entry import MealEntry
from app.services.chat_turn import (
    build_today_context,
    format_today_conversation,
    format_today_meal_entries_markdown,
)


def _msg(role: str, content: str) -> ChatMessage:
    return ChatMessage(
        date="2026-08-24", role=role, content=content, created_at="2026-08-24T12:00:00+00:00"
    )


def _entry(**overrides) -> MealEntry:
    payload = dict(
        confirmation_id="conf-1",
        date="2026-08-24",
        meal_slot="lunch",
        food_name="熟鸡胸肉",
        quantity=150.0,
        unit="g",
        kcal=247.5,
        carb_g=0.0,
        protein_g=46.5,
        fat_g=5.3,
        fiber_g=None,
        source_tag="llm_estimate",
        created_at="2026-08-24T12:00:00+00:00",
    )
    payload.update(overrides)
    return MealEntry(**payload)


class TestFormatConversation:
    def test_roles_and_order(self):
        text = format_today_conversation(
            [_msg("user", "我吃了饭"), _msg("assistant", "识别到了"), _msg("user", "好的")]
        )
        assert text == "[用户] 我吃了饭\n[AI] 识别到了\n[用户] 好的"

    def test_empty_conversation(self):
        assert format_today_conversation([]) == "(无)"


class TestFormatMealEntriesMarkdown:
    def test_header_columns(self):
        table = format_today_meal_entries_markdown([])
        header = table.splitlines()[0]
        for col in ("餐次", "食物", "数量", "kcal", "碳水", "蛋白质", "脂肪", "纤维"):
            assert col in header

    def test_row_values_and_missing_shown_as_dash(self):
        table = format_today_meal_entries_markdown([_entry()])
        row = table.splitlines()[2]
        assert "| 午餐 | 熟鸡胸肉 | 150g | 247.5 | 0 | 46.5 | 5.3 | — |" == row

    def test_zero_is_zero_not_dash(self):
        # 确定为零(carb_g=0)显示 0;缺失(None)显示 —;两者绝不混淆
        table = format_today_meal_entries_markdown([_entry(carb_g=0.0, fiber_g=None)])
        row = table.splitlines()[2]
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert cells[4] == "0"
        assert cells[7] == "—"

    def test_multiple_rows_keep_input_order(self):
        table = format_today_meal_entries_markdown(
            [
                _entry(food_name="早餐蛋", meal_slot="breakfast"),
                _entry(food_name="午饭肉", meal_slot="lunch"),
            ]
        )
        lines = table.splitlines()
        assert "早餐蛋" in lines[2]
        assert "午饭肉" in lines[3]


class TestBuildTodayContext:
    def test_both_sections_present_in_fixed_order(self):
        context = build_today_context([_msg("user", "我吃了饭")], [_entry()])
        convo_pos = context.index("今日对话记录:")
        table_pos = context.index("今日已确认记录的饮食明细:")
        assert convo_pos < table_pos
        assert "[用户] 我吃了饭" in context
        assert "熟鸡胸肉" in context

    def test_empty_inputs_still_render_sections(self):
        context = build_today_context([], [])
        assert "今日对话记录:" in context
        assert "(无)" in context
        assert "今日已确认记录的饮食明细:" in context
        assert "| 餐次 |" in context
