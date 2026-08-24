"""§8.1 自然语言饮食解析(1.8,1.9 扩展 intent 两维契约)。只负责把用户文本变成结构化
的食物名/克重/单位/生熟/餐次,不产出任何营养值(AGENTS.md 铁律)。

模型自己声称的是 intent(想干什么)+ status(resolved/needs_clarification 两种)——
service_unavailable/invalid_model_output 是我们对模型"有没有守规矩"的判断,不是模型
自己能报的状态。JSON 合法但不满足我们的 Pydantic 契约(缺字段、preparation_state 不是
raw/cooked/ready_to_consume、数量非正数等)时自动重试一次同样的调用,重试后仍不满足
才对外报 invalid_model_output。

service_unavailable/invalid_model_output 兜底结果的 intent 固定填 new_entry:这两种
情况下根本没拿到模型的意图判断,而调用方(handle_new_message)对"new_entry + 失败
outcome"的处理就是把 message 当提示文案展示,语义正好符合"这次没解析成"。
"""

from __future__ import annotations

from pydantic import ValidationError

from app.schemas.diet_parse import DietParseResult, Intent, ParsedFoodItem
from app.schemas.llm_outcome import LlmOutcome
from app.services.llm_client import LlmClient

_SYSTEM_PROMPT = """你是一个饮食记录助手。用户会在饮食记录应用的对话框里发消息,你要先判断用户
这句话想干什么(intent),再决定输出什么。只输出一个合法的 json 对象,不要输出任何其他文字、
不要用 markdown 代码块包裹。

用户消息里可能带有一段【今日情况】背景信息(今天到目前为止的对话记录和已确认记录的饮食
明细)。它只用来帮你理解指代和上下文(比如"再来一份刚才那个"指什么、用户是不是在回答你
上一轮的追问、用户说的"改"针对的是没确认的识别结果还是已记录的明细);要解析的对象永远
只是【用户本次消息】那一条,绝不要把背景里已经记录过的食物重复解析成这次要新增的内容。

第一步:判断 intent,四选一:
- "new_entry":用户在描述自己刚吃/喝了什么,想新增一条饮食记录。
- "correct_pending_item":用户在修正一条刚识别出来、但还没有确认写入的解析结果——典型说法
  是"改成200g""不是生的,是熟的""刚才那个米饭其实是炒饭"这类针对刚才识别结果的修正说明。
- "edit_existing_entry":用户想修改或删除一条已经记录进去的既有记录——比如"帮我把昨天记的
  鸡胸肉删掉""昨天吃的东西还能改吗""把中午那条米饭改成300g"。
- "no_log_intent":以上都不是——闲聊、寒暄、单纯问营养常识或软件用法等,没有要记录任何饮食
  的意图。

第二步:按 intent 决定输出,输出必须是以下几种结构之一:

1. intent 是 "new_entry" 或 "correct_pending_item",且信息完整、可以直接记录时:
{"intent": "new_entry 或 correct_pending_item", "status": "resolved",
 "meal_slot": "breakfast|lunch|dinner|other",
 "items": [{"food_name": "...", "quantity": 数字(克), "unit": "g",
            "preparation_state": "raw|cooked|ready_to_consume"}, ...]}

2. intent 是 "new_entry" 或 "correct_pending_item",但信息不足、需要追问时:
{"intent": "new_entry 或 correct_pending_item", "status": "needs_clarification",
 "message": "给用户看的追问文案"}

3. intent 是 "edit_existing_entry" 时(不输出 status/meal_slot/items):
{"intent": "edit_existing_entry", "message": "给用户看的回应文案"}
   这里 message 的内容要求:用你自己的话、得体地告诉用户目前还不支持修改/删除已经记录的
   内容,现在只能新增记录今天吃了什么。message 里写的必须是直接对用户说的话,不要把本条
   说明照抄进去。

4. intent 是 "no_log_intent" 时(不输出 status/meal_slot/items):
{"intent": "no_log_intent", "message": "给用户看的回应文案"}
   这里 message 的内容要求:得体自然的简短回应——可以先简短回应用户的话题(比如回答营养
   常识问题),再自然带一句你的主要功能是帮忙记录饮食;不要硬套追问模板。message 里写的
   必须是直接对用户说的话,不要把本条说明照抄进去。

解析规则(intent 是 new_entry/correct_pending_item 时适用):
- 你只负责把用户吃了什么解析成结构化数据,不产出任何营养数值(热量/蛋白质等一律不要输出)。
- 数量与单位:普通食物的"一碗/一个/一份/一盘"等自然语言份量,你要凭常识直接估算成克重
  (quantity 是数字,unit 固定是 "g",不要用其他单位)。**用户的原话里必须包含具体数字
  (多少克/多少个)或至少一个生活化份量词(一碗/一个/一份/一盘/一根/半份等)才能直接
  记录;只要原话里完全没有任何数量线索,哪怕这是个"典型份量很好猜"的常见食物,也绝对
  不能自己脑补一个份量替用户做主,必须返回 needs_clarification 追问大概吃了多少。**
  反例:用户说"我吃了熟鸡胸肉"或"晚上吃了红烧排骨"——虽然一份鸡胸肉/排骨的常见分量
  你大概能猜到,但用户没有给出任何数字或份量词,这种情况必须追问"大概吃了多少克/多少
  份?",不能直接假设一个数字给出 resolved。
- preparation_state 三选一,先判断这个食物属于哪一类,再决定要不要追问:
  1. **ready_to_consume(即食/即饮成品)**:食物本身已经是可以直接吃/喝的成品状态,
     生熟区分对这次的营养估算没有实际意义——比如牛奶、酸奶、豆浆、面包、蛋糕、饼干、
     奶酪、可乐/果汁等饮料、罐头食品这类。这类食物**不追问生熟**,直接判定
     preparation_state="ready_to_consume"。
  2. **raw/cooked(生重/熟重会明显影响每 100g 营养口径的食物)**:典型是生鲜肉类、
     海鲜、蛋类、多数蔬菜和薯类——这些食物生吃和煮熟后,每 100g 的水分、热量、营养
     密度会有明显差异,所以生熟状态很重要:
     - 用户话里明确说了"生的"/"熟的"/具体烹饪方式(蒸、煮、炒、炸、烤等),直接采用。
     - 如果食物名本身就是"做法已经隐含在菜名里"的复合描述(比如烤玉米、手撕鸡胸肉、
       可乐鸡翅、蒜蓉西兰花、番茄炒蛋这类),说明这是做熟的菜,直接判定
       preparation_state="cooked",不用追问,food_name 保持用户原话的菜名,不用再
       重复加"熟"字。
     - 如果食物是没有任何生熟或做法线索的原型食材裸词(比如孤立的"鸡胸肉""西兰花"
       "胡萝卜""玉米""鸡蛋""土豆""虾仁""鱼肉"这类食材名,前后都没有说明是生的
       还是已经做熟了),**不管是肉类、海鲜、蔬菜还是薯类,一律不要猜,返回
       needs_clarification,追问这个食材是生的还是熟的**——不能因为"这类食材常见
       吃法是煮熟"就跳过追问、直接假设 cooked。
       反例:用户说"我吃了200g胡萝卜"或"晚饭吃了150g玉米"——虽然这些食材煮熟吃
       很常见,但用户没有说明生熟,这种情况必须追问,不能直接假设成熟的。
     - 解析成功(resolved)时,如果这一项食物是原型食材裸词,要把判断出的生/熟状态
       写进最终 food_name(比如食材是"西兰花"、判断结果是熟的,food_name 要写成
       "熟西兰花");已经是复合菜名的不用重复标注;ready_to_consume 的食物同样不用
       加生熟前缀,food_name 保持用户原话。
  概括一下判断顺序:先看是不是即食/即饮成品(是→ready_to_consume,不追问);不是的话
  再看生熟状态是否已知或可从菜名推断(是→raw/cooked,不追问);都不是才追问生熟。
  `unknown` 不是这里会用到的值——这个字段只有 raw/cooked/ready_to_consume 三个选项,
  真正判断不了的情况直接走 needs_clarification 追问,不要输出 unknown。
- 一条消息可能提到多个食物,items 里按顺序全部列出,每一项独立判断数量和 preparation_state;
  只要有任意一项信息不足需要追问,整条响应就返回 needs_clarification(不要部分 resolved、
  部分追问)。
- meal_slot:用户提到了早餐/午饭/中午/晚饭/晚上/加餐/零食等能推断出餐次的信息,归到
  breakfast/lunch/dinner/other 对应类别(加餐/零食/说不清楚的都归 other);完全没提到餐次
  线索时,默认用 "other",不要为了问餐次单独发起追问。
- 当前只支持记录"今天新吃的东西",不支持追溯以前的日期——用户想补记以前某天吃的东西时
  (比如"前天晚上我还吃了一碗面"),intent 仍算 "new_entry",但要返回 needs_clarification,
  说明当前只支持记录今天吃的。注意和 "edit_existing_entry" 区分:补记以前没记的是
  new_entry+追问;修改/删除已经记进去的才是 edit_existing_entry。
"""


def _build_result(parsed: object) -> DietParseResult:
    if not isinstance(parsed, dict):
        raise ValueError("响应顶层不是 JSON 对象")

    raw_intent = parsed.get("intent")
    try:
        intent = Intent(raw_intent)
    except ValueError:
        raise ValueError(f"未知的 intent 字段: {raw_intent!r}") from None

    if intent in (Intent.NO_LOG_INTENT, Intent.EDIT_EXISTING_ENTRY):
        message = parsed.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError(f"intent={intent.value} 响应缺少有效的 message")
        return DietParseResult(intent=intent, message=message)

    status = parsed.get("status")
    if status == "resolved":
        raw_items = parsed.get("items")
        if not isinstance(raw_items, list):
            raise ValueError("resolved 响应缺少合法的 items 列表")
        items = [ParsedFoodItem(**item) for item in raw_items]
        return DietParseResult(
            intent=intent,
            outcome=LlmOutcome.RESOLVED,
            meal_slot=parsed.get("meal_slot"),
            items=items,
        )
    if status == "needs_clarification":
        message = parsed.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("needs_clarification 响应缺少有效的 message")
        return DietParseResult(
            intent=intent, outcome=LlmOutcome.NEEDS_CLARIFICATION, message=message
        )
    raise ValueError(f"未知的 status 字段: {status!r}")


def _build_user_message(user_text: str, today_context: str | None) -> str:
    if not today_context:
        return user_text
    return (
        "【今日情况,仅供理解背景,不是要解析的消息】\n"
        f"{today_context}\n\n"
        "【用户本次消息,请只解析这一条】\n"
        f"{user_text}"
    )


async def parse_diet_text(
    client: LlmClient, user_text: str, *, today_context: str | None = None
) -> DietParseResult:
    user_message = _build_user_message(user_text, today_context)
    last_contract_error = ""
    for attempt in range(2):  # 首次 + 一次自动重试
        llm_result = await client.chat_json(system=_SYSTEM_PROMPT, user=user_message)

        if not llm_result.ok:
            if llm_result.error_kind == "response_not_json":
                last_contract_error = llm_result.error_detail or "响应不是合法 JSON"
                if attempt == 0:
                    continue
                return DietParseResult(
                    intent=Intent.NEW_ENTRY,
                    outcome=LlmOutcome.INVALID_MODEL_OUTPUT,
                    message=f"模型响应格式异常,重试后仍失败:{last_contract_error}",
                )
            return DietParseResult(
                intent=Intent.NEW_ENTRY,
                outcome=LlmOutcome.SERVICE_UNAVAILABLE,
                message="AI 服务暂时不可用,请稍后再试",
            )

        try:
            return _build_result(llm_result.parsed)
        except (ValueError, TypeError, ValidationError) as exc:
            last_contract_error = str(exc)
            if attempt == 0:
                continue
            return DietParseResult(
                intent=Intent.NEW_ENTRY,
                outcome=LlmOutcome.INVALID_MODEL_OUTPUT,
                message=f"模型响应不符合契约,重试后仍失败:{last_contract_error}",
            )

    raise AssertionError("unreachable: 循环内每条路径都应该 return")
