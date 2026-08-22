# 1.6-1.8 食物营养查询引擎(feature_demo_03_query_engine)

## Context

Demo 里程碑已完成 1.1-1.5(后端骨架、数据模型、前端空壳、中/美食物库导入)。按
`tasks/STATUS.md` 依赖顺序,下一步是 1.6-1.8,三步合并成一个 PR,交付"食物营养查询
引擎"能力(纯后端,不含 UI,后端契约测试即可验收)。

"Demo/MVP 阶段用 LLM 直接估算 per-100g 营养值代替四级查询链"这一条已经落到了
`main` 的 `docs/product/SPEC.md`(commit 13ccb7a)——这是本计划要实现的既定范围,SPEC
本身就是依据,不需要额外引用其他分支上的文档。四级查询链(§7.2)是 Closed Beta 目标
设计,Demo 阶段不实现;`food_base_cn`/`food_base_us` 虽已导入但本阶段查询不使用
(SPEC §11.1)。

真源:SPEC §4(数据模型)、§6.1(归属日)、§7.1/7.3/7.4/7.6/7.8(食物业务唯一定义 +
Demo 里程碑范围注)、§8.1(自然语言解析契约)、§11.1(Demo 验收标准);ADR 0001(LLM
供应商/模型路由,纯文本统一 `qwen-plus`)。

本版相对上一版的主要修改(你的批注):不再在 Confirm 前算 date/created_at;LLM 结果
从"items+clarify"两态改成四态结果类型;1.8 的 95% 合法结构率需要独立于 pytest 的真实
评测集,不是两次真实调用能证明的;补齐 schema 业务校验、并发部分失败处理、LLM 配置
细节;迁移改成整表重建;SPEC/STATUS 两处过期表述已同步修正。

---

## 一、涉及的数据库字段结构

Demo 的 LLM 直接估算路径**不新增表**,只碰已存在的两张表 + 一个枚举常量:

**`meal_entry`**(短期库,`backend/app/models/meal_entry.py`,SPEC §4.1)——1.9 最终写入
的目标行形状(**本 PR 不写这张表**,只产出 1.9 组装这行所需的营养/来源数据):

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| date | TEXT | 归属日,1.9 在 Confirm 时才计算(见下方取舍 2) |
| meal_slot | CHECK enum | breakfast/lunch/dinner/other |
| food_name | TEXT | 用户确认后的食物名称(做法/生熟保留在名称里) |
| quantity | REAL | 本次克重(Demo 只会是 g) |
| unit | CHECK enum | g / serving |
| kcal / carb_g / protein_g / fat_g / fiber_g | REAL NULL | 本次营养快照,**逐项可空**(但 kcal 需非空才算"可信结果",见执行细节 schema 校验) |
| source_tag | CHECK enum | 现有 `chn_table/usda/decompose_estimate/user_create`,**缺 `llm_estimate`** |
| created_at | TEXT | UTC-0,1.9 在 Confirm 时才计算 |

**`chat_message`**(`backend/app/models/chat_message.py`,SPEC §4.4)——本 PR 不写入,
是 1.9 会用到的下游表,这里不动。

**`backend/app/models/enums.py`**(当前内容):

```python
MEAL_SLOT_VALUES = ("breakfast", "lunch", "dinner", "other")
UNIT_VALUES = ("g", "serving")
SOURCE_TAG_VALUES = ("chn_table", "usda", "decompose_estimate", "user_create")
```

**需要的 schema 变更**:`SOURCE_TAG_VALUES` 加入 `"llm_estimate"`(SPEC §11.1 技术验收
明确要求"LLM 直接估算营养值标注 `source_tag = llm_estimate`")。

**迁移方式**:整表 `drop_table('meal_entry')` + 重新 `create_table('meal_entry', ...)`,
`source_tag` 枚举从一开始就包含 `llm_estimate`,同步重建 `ix_meal_entry_date` 索引——比
SQLite batch 模式下改 CHECK 约束简单可靠。**空表检查写进迁移脚本本身,不是人工跑一次
就完事**:这条迁移会永久留在项目历史里,以后在别的机器上执行 `alembic upgrade head`
时不能指望有人记得先手动核对。`upgrade()`/`downgrade()` 都在动表之前先查
`COUNT(*)`,非空就 `raise RuntimeError` 拒绝执行(`downgrade()` 同样要挡,否则 1.9
写入真实饮食记录之后有人跑 downgrade,会把记录整表删掉):

```python
def upgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT COUNT(*) FROM meal_entry")).scalar_one()
    if count != 0:
        raise RuntimeError("meal_entry 非空,拒绝重建;需要人工评估数据后再处理")
    op.drop_table('meal_entry')
    op.create_table('meal_entry', ...)  # source_tag 含 llm_estimate
    # 重建 ix_meal_entry_date

def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT COUNT(*) FROM meal_entry")).scalar_one()
    if count != 0:
        raise RuntimeError("meal_entry 非空,拒绝回退(会丢失已写入的饮食记录)")
    op.drop_table('meal_entry')
    op.create_table('meal_entry', ...)  # 原 4 值枚举
```

测试用 `migrated_engine`(临时 SQLite)验证新表字段/可空性/三个 CHECK 约束,以及
非空表时 `upgrade()`/`downgrade()` 确实 raise。**对真实 `backend/data/dietapp.db` 执行
`alembic upgrade head` 挪到实现顺序的最后一步**,等 1.6-1.8 全部代码和测试都在临时库
上跑通之后再做(你已批准这条迁移可以实跑,但没必要在其他功能还没写完时就提前动
真实表)。

---

## 二、1.6-1.8 整体框架逻辑

### 范围边界(为什么 1.6-1.8 不含持久化/API/UI,也不含 date/created_at)

`tasks/STATUS.md` 1.9 的交付物明确列了"直接写入路径的持久化层、`chat_message` 写入、
今日明细查询 API"。据此本 PR 把 1.6-1.8 做成**纯 service 层**:接收输入、调用 LLM、
算营养,产出 `ConfirmationPreview`(见下),但不真正 `db.add()`/`commit()`,不建 FastAPI
路由,不写 `chat_message`,**也不计算 `date`/`created_at`**——归属日和 UTC 时间戳必须
是"用户点 Confirm 那一刻"的值,在预览生成阶段(可能早于 Confirm 数秒到数分钟)提前算好
会不准。1.9 负责:接这些纯函数、在 Confirm 时统一算 `date`(归属日公式)和
`created_at`(UTC now)、组装真正的 `MealEntry`、接 DB 事务、API 路由和前端。

### 端到端管线(Demo 版,今天只做"新增")

```
用户文本
   │
   ▼
① NL 解析(1.8, §8.1)──────────── qwen-plus,一次调用(schema 违规重试一次)
   │  对每个食物判断 preparation_state(生/熟):
   │    - 用户话里明确说了生/熟 → 直接采用;
   │    - 食物是"做法已经隐含在菜名里"的复合描述(如烤玉米、手撕鸡胸肉、可乐鸡翅、
   │      蒜蓉西兰花)→ 视为已解析,不用追问;
   │    - 食物是原型食材裸词(如鸡胸肉、西兰花、胡萝卜、玉米、鸡蛋)且没有任何生熟
   │      线索 → 不猜测,整条响应判定为 needs_clarification。
   │  解析成功时同步规范化 food_name:原型食材裸词把"生/熟"写进最终名称(如"西兰花"
   │  +熟→"熟西兰花");已经带做法的复合菜名保持原样,不重复标注。
   │  产出 DietParseResult{ outcome, meal_slot?, items?, message? }(四态,见下方"结果
   │  类型")
   │
   ├─ outcome ≠ resolved → 停,把 message 返回给用户(不进入②)。四种非 resolved 语义
   │  不同(需要追问 / 服务不可用 / 模型没遵守契约),前端怎么分别展示留给 1.9,但 1.8
   │  必须先把这三种区分开,不能统一变成"追问"。
   │
   ▼ outcome = resolved(此时每项 preparation_state 必为 raw 或 cooked)
② 逐项 LLM 直接估算(1.7, §7.2 Demo 分支 + §7.4)── qwen-plus,每个 item 一次调用,并发
   │  产出每项 FoodEstimate{ outcome, nutrients?, confidence?, confidence_reason?,
   │  message? };outcome=resolved 时要求 kcal_100g 非 null(全 null 不算"拿到可信
   │  结果",见下方取舍 7),source_tag 固定标 "llm_estimate"
   │  失败项(service_unavailable/invalid_model_output)不阻塞同批其他项,也不静默
   │  丢弃——每项各自的 outcome 都保留在结果列表里(见下方取舍 8)
   │
   ▼
③ 单位与营养计算(1.6, §7.3)──────── 纯函数,不调 LLM,只处理 outcome=resolved 的项
   │  quantity_g × per_100g / 100,任一 per_100g 字段为 null → 该字段结果为 null(不当 0)
   │
   ▼
④ 组装成 ItemEstimateOutcome 列表(1.7,本 PR 终态产出)
   │  每项 { parsed_item, outcome, preview: ConfirmationPreview | None, message }
   │  resolved 项的 preview = { food_name, quantity, unit, meal_slot, 计算出的营养
   │  快照, source_tag=llm_estimate, confidence, confidence_reason, warning="可能不准" }
   │  → 不含 date、不含 created_at;到这里为止都不落库(AGENTS.md 铁律:未拿到可信
   │    营养结果前不写 meal_entry)
   │
   ▼
⑤ Confirm(用户确认,1.9 才接 API/UI)
      → 1.9 对每个用户确认的 preview 计算 date(归属日)、created_at(UTC now),
        组装真正的 MealEntry,db.add() + commit;部分项失败时是否允许其余项继续
        Confirm,是 1.9 的交互策略,本 PR 不预设
```

### 结果类型(四态,取代原来的"items+clarify"两态)

```python
class LlmOutcome(str, Enum):
    RESOLVED = "resolved"                      # 成功
    NEEDS_CLARIFICATION = "needs_clarification" # 用户需要补信息,或输入和记录饮食无关
    SERVICE_UNAVAILABLE = "service_unavailable" # 网络/超时/限流/API Key 缺失或无效
    INVALID_MODEL_OUTPUT = "invalid_model_output" # JSON 非法或不满足契约,重试一次后仍失败
```

三种非 resolved 场景语义不同,不能都塞进"追问":
- **needs_clarification**:用户没说清楚(缺克重、原型食材没说生熟)、或这句话根本
  不像在记录饮食(闲聊、单纯问热量常识但没有记录意图)——`message` 是给用户看的
  追问/说明文案。
- **service_unavailable**:网络断开、超时、DashScope 429/5xx 重试耗尽、
  `DASHSCOPE_API_KEY` 缺失或无效——`message` 应该是"服务暂时不可用",不能让用户
  以为是自己没说清楚(SPEC §10"LLM 不可用时禁止提交业务写入并显示可恢复错误")。
- **invalid_model_output**:模型返回的 JSON 语法错误或不满足我们的契约字段——
  `nl_parse`/`food_estimate` 内部先自动重试一次同样的调用,重试后仍不满足才对外
  报这个状态,不静默失败、不当成 needs_clarification。

`llm_client.chat_json` 负责区分"网络/HTTP 层错误"(→ service_unavailable)和
"响应体不是合法 JSON"(→ invalid_model_output 的一种输入);429/5xx 在 `llm_client`
内部先做有限次数重试(见执行细节配置项),重试耗尽才把失败结果交给上层。
"JSON 合法但不满足我们的 Pydantic 契约"这一层校验在 `nl_parse`/`food_estimate`
里做(它们才知道目标 schema 是什么),失败同样重试一次。

`FoodEstimate`/`DietParseResult`/`ConfirmationPreview` 的具体字段定义见执行细节。

### 关键设计取舍(会体现在代码里)

1. **`preparation_state` 字段本身不落库,但会体现在 food_name 文本里**:SPEC §4.1
   明确 `meal_entry` 不存 `preparation_state`,它只是①→②之间的临时上下文,放在
   Pydantic schema 里传递,不进 `app/models/enums.py`(那个文件只放真正落成 DB CHECK
   约束的枚举)。原型食材裸词(鸡胸肉/西兰花/胡萝卜/玉米/鸡蛋等,没有组合进复合菜名)
   解析出生熟后,①阶段把"生/熟"写进最终 `food_name`(如"熟鸡胸肉");已带做法的复合
   菜名保持原样,不重复标注。判断逻辑写进 1.8 的 prompt 交给 LLM 做,不写死关键词表。
2. **`date`/`created_at` 不在 1.6-1.8 计算,由 1.9 在 Confirm 时统一算**:预览生成
   和用户点 Confirm 之间可能有延迟,提前算的时间戳/归属日会不准。`ConfirmationPreview`
   不含这两个字段。
3. **Demo 只产出 `unit="g"`**:`serving` 只在命中个人常吃食谱(`food_favorite`)时才
   合法(§7.1),而 `food_favorite` 是 MVP 才建的表。①的 NL 解析 prompt 直接限定只输出
   g,不给模型 serving 选项。
4. **不实现"总重→可食部克重"(可食率)转换**:`edible_pct` 的换算绑定在
   `food_base_cn` 查询链路上(SPEC §4.4.1/§7.1),Demo 完全不查那张表,没有 `edible_pct`
   数据源可用。"一个带壳鸡蛋"这类描述由①NL 解析阶段的 LLM 直接估算成"可食部克重"
   输出(§8.1 本来就要求"自然语言份量在本次解析中估算为 g"),不在 1.6 计算引擎里
   单独做二段换算。`STATUS.md` 1.6 行已同步改掉"可食率仅在'总重'输入时应用"的过期
   表述,注明留到 Closed Beta。
5. **原型食材裸词需要追问生熟,复合菜名不需要**:①阶段的 LLM 先判断该食物是"原型
   食材裸词"还是"做法已隐含在菜名里的复合描述"。原型食材(鸡胸肉、鸡腿、胡萝卜、
   鸡蛋等)且用户没说生熟 → `needs_clarification`,不进入②;复合菜名(烤玉米、手撕
   鸡胸肉、可乐鸡翅、蒜蓉西兰花等)→ 视为已解析,直接进入②。Demo 阶段
   `preparation_state` 实际只会是 `raw`/`cooked` 两个值。
6. **②的 LLM 调用按 item 并发,不批量合并成一次调用**:单用户场景一条消息通常没几个
   食物,按 item 独立调用逻辑最简单,和"失败项独立标记、不阻塞其他项"的设计天然契合;
   `llm_client.py` 内置并发信号量防止打爆 DashScope。
7. **estimate 结果要求 `kcal_100g` 非空才算 `resolved`**:五项营养全为 null 不算"拿到
   可信营养结果"(AGENTS.md 铁律),也没法进 A1 热量趋势。若模型返回全 null,该项按
   `invalid_model_output`(重试一次后仍全 null)处理,不产出 `preview`,交给上层决定要不要
   对这一项单独追问。其余四项营养素允许 null(不影响 outcome 判定)。
8. **并发估算的部分失败**:`estimate_items` 返回 `list[ItemEstimateOutcome]`,与输入
   items 一一对应、顺序保持,失败项(某一项 service_unavailable/invalid_model_output)
   不会被静默丢弃、也不会产生可写入的 `preview`,但不阻塞同批其他成功项的计算。"部分
   成功时能不能继续 Confirm"是交互策略,留给 1.9 的 Confirm UI 决定,本 PR 不预设。
9. **契约测试主体用 stub LLM client,不打真实网络**:`nl_parse`/`food_estimate` 接收
   一个满足 `LlmClient` Protocol 的 client 依赖,主体测试注入假 client 返回预置 JSON
   (四种 outcome 各覆盖),保证 `pytest` 默认不需要网络、不产生费用就能稳定跑绿。
10. **1.8 的 95% 合法结构率用独立评测集验证,不进普通 `pytest`**:两次真实调用只能
    证明"接口现在能通",不能代表 95% 这个统计指标。评测集/执行方式见执行细节。
11. **"结构合法率"和"语义准确率"是两个不同指标,不能混在一起**:模型可能返回完全
    合法的 JSON、但把"吃了一个鸡蛋"错误判成 `resolved`(该问生熟却没问)——这种情况
    结构合法,但判断错了。SPEC §11.1"文本解析合法结构率 ≥95%"字面上说的是**结构**
    这一层,不是语义判断对不对。所以:
    - **结构合法**=响应能被 JSON 解析且满足 `DietParseResult` 的 Pydantic 契约(含
      outcome-字段联动校验),不管最终 outcome 判成 resolved 还是
      needs_clarification 都算合法——只有 `invalid_model_output` 才算不合法。
    - **语义准确**=resolved/needs_clarification 的判断是否符合数据集标注的
      `expected_outcome`,这是质量信号,SPEC 没有单独定数字门槛,但评测脚本要报出来
      供你判断 prompt 好不好。
    - 评测脚本据此分别报三个数:**首次响应结构合法率**、**自动重试后的最终结构合法
      率**(这个对应 SPEC 的 95% 门槛)、**语义准确率**;`service_unavailable`(infra
      抖动,不是模型质量问题)单独计数、不进两个合法率/准确率的分母。

---

## 三、执行细节

### Pydantic schema 校验(不只是字段类型)

- `quantity`:`gt=0`(0g 不生成记录)、`allow_inf_nan=False`。
- 五项营养字段(`NutrientPer100g`/`NutrientSet`):存在时必须 `>= 0` 且有限(拒绝
  负数、NaN、±inf),缺失仍是 `None`,不是 0。
- `food_name`、`confidence_reason`、`message`:非空字符串时 `min_length=1`(不接受
  空串顶替"没有内容")。
- `confidence`:固定 `Literal["low","medium","high"]`。
- `DietParseResult`/`FoodEstimate`/`ItemEstimateOutcome` 用 `model_validator(mode="after")`
  强制 outcome 和字段联动一致:`resolved` ⇒ 载荷字段非空且 `message is None`;其余三种
  ⇒ 载荷字段为空且 `message` 非空。
- `FoodEstimate.outcome=resolved` 额外要求 `nutrients.kcal_100g is not None`(取舍 7)。

### 改动/新增文件清单

| 文件 | 改动 |
|---|---|
| `backend/app/config.py` | `Settings` 新增:`dashscope_api_key: str \| None = None`(**可空**,见下方"LLM 配置细节")、`dashscope_base_url`(已有默认值)、`llm_text_model: str = "qwen-plus"`、`llm_connect_timeout_seconds: float = 5.0`、`llm_total_timeout_seconds: float = 30.0`、`llm_max_concurrency: int = 4`、`llm_max_retries: int = 2` |
| `backend/app/models/enums.py` | `SOURCE_TAG_VALUES` 加 `"llm_estimate"` |
| `backend/migrations/versions/<新revision>_recreate_meal_entry_with_llm_estimate.py` | `down_revision='50b75ce1aba2'`;`upgrade()`/`downgrade()` 各自先查 `COUNT(*)`,非空 raise 拒绝执行,为空才 `drop_table` + `create_table`(source_tag 枚举含 `llm_estimate`)+ 重建 `ix_meal_entry_date`;`downgrade()` 对称还原成 4 值枚举 |
| `backend/app/schemas/llm_outcome.py`(新) | `LlmOutcome` 枚举,`nl_parse`/`food_estimate` 共用 |
| `backend/app/schemas/nutrition.py`(新) | `NutrientPer100g`、`NutrientSet`,五项营养 `float \| None`,带上方数值校验 |
| `backend/app/schemas/diet_parse.py`(新) | `ParsedFoodItem`(food_name/quantity/unit: `Literal["g"]`/preparation_state: `Literal["raw","cooked"]`)、`DietParseResult`(outcome/meal_slot?/items?/message?,四态联动校验) |
| `backend/app/schemas/food_estimate.py`(新) | `FoodEstimate`、`ConfirmationPreview`(不含 date/created_at,`source_tag` 复用完整 `SOURCE_TAG_VALUES` 而非写死 `llm_estimate`,便于 Closed Beta 换查询链时复用同一形状)、`ItemEstimateOutcome` |
| `backend/app/services/llm_client.py`(新,1.8 基础设施) | `LlmClient` Protocol + `DashScopeClient` 实现(第一个也是当前唯一实现);`chat_json` 优先用 `response_format` 做 JSON Schema/Object 约束,但响应始终再过 Pydantic 校验,不假设约束模式能替代校验;429/5xx 在内部按 `llm_max_retries` 重试;网络错误/超时/API Key 缺失/非 200 → 统一走"失败"通道并标出错误类别(网络类 vs 响应非 JSON 类),不抛异常给调用方 |
| `backend/app/services/nutrition_calc.py`(新,1.6) | `compute_nutrient_snapshot(per_100g: NutrientPer100g, quantity_g: float) -> NutrientSet`,纯函数、null 传播,不做可食率换算(取舍 4) |
| `backend/app/services/nl_parse.py`(新,1.8) | `async def parse_diet_text(client: LlmClient, user_text: str) -> DietParseResult`;prompt 只允许 g;prompt 内编码"原型食材裸词无生熟线索→needs_clarification,复合菜名→已解析""无关输入→needs_clarification"规则;JSON/契约违规 → 自动重试一次,仍失败才判 `invalid_model_output` |
| `backend/app/services/food_estimate.py`(新,1.7) | `async def estimate_food(client, food_name, preparation_state) -> FoodEstimate`(含 kcal 非空校验+重试一次逻辑);`async def estimate_items(client, items) -> list[ItemEstimateOutcome]`(并发、内部调用 1.6 的 `compute_nutrient_snapshot`,失败项不丢弃) |

### LLM 配置细节(回应"Settings 导入即失败"的问题)

`config.py` 当前 `Settings()` 在模块导入时立即构造(`app/config.py:20`)。如果新增一个
必填的 `dashscope_api_key: str`,没配 Key 的环境(比如只想跑健康检查/无关单测的机器)
会连 `app.main` 都导入不了。改成:

- `dashscope_api_key: str | None = None`,`Settings` 本身永远能构造成功。
- Key 只在 `DashScopeClient` 真正发起请求前检查;缺失时直接返回
  `outcome=service_unavailable`(不发请求、不抛异常),`message` 提示服务未配置。
- 模型 alias 进配置(`llm_text_model`,默认 `qwen-plus`,对齐 ADR 0001 的"模型选择该在
  配置层"原则),超时/并发/重试次数同样配置化,不写死在代码里。

### 测试与评测(NN=03,`tests/backend/`)

**普通 `pytest`(全部 stub,免费、稳定,默认必须全绿)**:

- `test_demo_03_schema_source_tag.py` —— `migrated_engine` 验证 `meal_entry` 重建后
  字段/可空性/三个 CHECK 约束(含 `llm_estimate`)。
- `test_demo_03_nutrition_calc.py` —— null 传播、`quantity_g` 边界、营养值非负校验。
- `test_demo_03_llm_client.py` —— `httpx.MockTransport` 覆盖:200+合法 JSON、200+非法
  JSON、非 200(含 429/5xx 触发重试再耗尽)、网络异常、Key 缺失,全部落到结构化失败
  结果而不是抛异常。
- `test_demo_03_nl_parse.py` —— stub client 覆盖四态各自的触发条件:resolved(完整
  信息)、needs_clarification(缺克重/原型食材无生熟线索/无关输入)、
  service_unavailable(client 返回该错误)、invalid_model_output(畸形 JSON,验证重试
  一次的行为);food_name 规范化(裸词加生/熟前缀,复合菜名不重复加);prompt 侧只产出
  `unit="g"`。
- `test_demo_03_food_estimate.py` —— stub client 覆盖:五项营养都有值、部分营养为
  null(null 传播)、kcal 全 null 判 `invalid_model_output`、置信度/来源标注正确、
  `estimate_items` 对多项里的部分失败不丢项也不阻塞其他项。

**独立评测(不进默认 `pytest`,显式触发才跑,产生真实调用费用)**:

- `pyproject.toml` 注册 `llm_live` marker,`addopts` 默认排除(`-m "not llm_live"`),
  只有 `pytest -m llm_live` 才会执行。
- `tests/backend/test_demo_03_llm_live.py`(标 `llm_live`)—— 少量真实 DashScope 调用,
  验证这个 PR 自己写的 prompt/解析代码在真实环境下能跑通、拿到合法 JSON(不是重复
  ADR 0001 已验证过的"供应商本身能不能用")。
- `tests/backend/eval/food_text_parse_dataset.csv`(新)—— 针对 §8.1 NL 解析、单轮
  文本、约 100 条,覆盖 9 类:单个食物 / 一餐多个食物 / 碗·个·盘等自然份量 / 明确
  生重或熟重 / 缺数量 / 缺生熟 / 中式复合菜 / 加餐及其他餐次 / 模糊或无关输入(不含
  多轮追问场景,那部分留给 1.9 用真实交互测)。每行标 `expected_outcome`
  (resolved/needs_clarification)用于自动判分。
- `backend/scripts/eval_nl_parse.py`(新)—— 读数据集、真实调用 `parse_diet_text`(内部
  已含一次自动重试逻辑),按取舍 11 的定义分别统计并输出**三个指标**:首次响应结构
  合法率、自动重试后的最终结构合法率(**对应 SPEC §11.1 的 95% 门槛**)、语义准确率
  (resolved/needs_clarification 是否匹配 `expected_outcome`);`service_unavailable`
  样本单独计数、不进上述比率的分母。失败/不合格样本(输入、期望、实际 outcome、原始
  响应)存到 `tests/backend/eval/results/<timestamp>_nl_parse.json`(比照
  `test_food_query_method_eval` 分支 `tests/food_query_logic/results/` 的留痕方式,
  不是照搬其实现)。**完成 1.8 前至少正式跑一次并把三个指标贴出来**,核对最终结构
  合法率是否达到 ≥95%。

### 实现顺序

1. `tasks/current.md` 已覆盖写入本版计划。
2. `config.py` 加 LLM 配置项(Key 可空)。
3. `enums.py` 加 `llm_estimate`;写迁移脚本(`upgrade()`/`downgrade()` 内置空表
   `COUNT(*)` 检查,非空 raise),只在临时 SQLite(`migrated_engine` fixture)跑通,
   **不碰真实库**。
4. `schemas/llm_outcome.py`、`schemas/nutrition.py` → `services/nutrition_calc.py` + 测试
   (1.6,无外部依赖,先做)。
5. `services/llm_client.py`(`LlmClient` Protocol + `DashScopeClient`)+ 测试(1.8 基础
   设施)。
6. `schemas/diet_parse.py` → `services/nl_parse.py` + `test_demo_03_nl_parse.py`(1.8)。
7. `schemas/food_estimate.py` → `services/food_estimate.py` + `test_demo_03_food_estimate.py`
   (1.7,依赖 4/5)。
8. `pyproject.toml` 注册 `llm_live` marker;`test_demo_03_llm_live.py`。
9. `conda activate vibe-coding && pytest`(默认排除 `llm_live`)跑全量,贴输出;
   `ruff check backend && mypy` 过一遍。
10. `tests/backend/eval/food_text_parse_dataset.csv` + `backend/scripts/eval_nl_parse.py`,
    正式跑一次评测,贴出首次结构合法率/最终结构合法率/语义准确率三个数字。
11. 以上全部通过、你确认后,才对真实 `backend/data/dietapp.db` 执行
    `alembic upgrade head`(迁移脚本自带空表校验,执行前仍会先跑一次只读 `COUNT(*)`
    做操作前确认),贴出执行结果。
12. 覆盖更新 `tasks/STATUS.md` 对应三行为完成状态(不新建计划文件)。

### 验证方式

- `conda activate vibe-coding && pytest` 全绿(默认不含 `llm_live`,不产生真实调用
  费用)。
- `pytest -m llm_live` 单独跑通(需要 `backend/.env` 配好 `DASHSCOPE_API_KEY`)。
- `backend/scripts/eval_nl_parse.py` 至少正式跑一次,**最终结构合法率**(重试后)
  达到 ≥95%(或贴出实际数字与差距,供你决定是否需要调整 prompt);同时贴出首次结构
  合法率和语义准确率作为参考,这两个不设硬性门槛。
- `ruff check backend && mypy` 无新增报错。
- 本 PR 不含 API/UI,不做手动浏览器验证;端到端验证留给 1.9。
