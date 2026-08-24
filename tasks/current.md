# 1.9 写入 + 今日明细 UI(feature_demo_04_write_path)

## 这一步做什么(大白话)

现在系统已经能"听懂"用户说的话、估算出营养值,但只是算完就扔了,不存起来、也没有
界面。这一步要把"算出来的结果"真正存进数据库,并且做出手机上能看、能点的界面:

1. 用户在"记录"页底部的输入框里打字,比如"中午一碗米饭、红烧肉两块、清炒西兰花"。
2. 系统读懂 + 估算营养后(**同时会把"今日已经确认记过的东西"也告诉 AI**,让 AI 和
   用户看到的是同一份"今天吃了什么"),先用一条确定性消息告诉用户识别到了什么——
   **如果某样食物估算失败了(比如 AI 服务当时抽风),这句话里会直接说清楚"哪样
   食物没识别出来、为什么",这样的食物不会出现在卡片里**,用户不需要也没法对它
   做什么。只要这批里还有至少一样估算成功的食物,同一条消息下面会弹出一张"解析
   结果"卡片(视觉上像从这条 AI 消息气泡里"长出来"),列出识别成功的每样食物;
   如果这批食物全部估算失败,就不会有卡片,这句播报就是这一轮的全部结果。
3. 卡片里每样食物旁边是**"确认"/"修改"一组互斥按钮,点了先是"本地暂存",还没
   真的存进数据库**:
   - 点"确认"→ 变绿,标记"我要这一项"。再点一次(取消)→ 变回白色。
   - 点"修改"→ 变绿,输入框切到"修改模式"(顶部灰色小字"修改:XX食物…",发送
     按钮变成"确认修改")。打字说怎么改后发送,**这一项下方立刻留一行"修改:你
     说的话…"的小字,数值先不变**——真正的重新估算要等到卡片顶部"确认"时才会
     一起处理(和"追问信息要问清楚才进入解析"是同一种思路:中途不打断,批次
     收尾时再统一算总账)。重新估算的结果出来后,这一项会重新出现在卡片里,回到
     "待处理",数值更新;如果这次修改没能解析成功,数值退回修改前的样子,提示
     "修改失败,请重新描述"。再点一次"修改"(取消,退回待处理)→ 丢弃还没发的
     修改草稿。
   - **真正决定"写不写进数据库"的是卡片最上面的两个按钮:"确认"和"放弃"。**点
     顶部"确认"→ 把所有已经本地暂存"确认"的食物一次性写进数据库,同时把所有
     暂存了"修改"的食物一并送去重新估算(可以分批点,比如先暂存两样点一次顶部
     确认,后面再暂存第三样再点一次)。点顶部"放弃"→ 把所有还没写进数据库的
     食物(不管是待处理、暂存确认还是暂存修改)标记为不记录。这两个顶部按钮在
     有网络请求进行中的时候都会被禁用,防止手快点出竞态问题。
   - 如果什么都没点,又想直接在输入框打字说别的 → 系统会先弹提示:"还有 N 项
     没确认,不确认就不会被记录,确定要放弃吗？"。
   - **这一整批食物的操作全部结束(每一项都变成"已写入"或"已放弃")之后,AI 才会
     回一句总结**(比如"已记录米饭200g、西兰花180g"),不是每点一下按钮就回一句。
     这句话是 AI 现场生成的,不是写死的模板。
4. 只有点了顶部"确认"、真正写进数据库的食物才会出现在"今日明细"表格里。**卡片
   还没处理完的时候,今日明细表格的删除按钮会先禁用**,避免两块界面同时改数据
   打架。如果页面在卡片处理到一半时被刷新或关闭,重新打开"记录"页时系统会检查
   今日有没有识别过、但还没走完的一批食物——有的话会弹一个提示,问要不要接着
   处理(继续会把这批食物重新摆回卡片里;放弃就当这批不记录)。
5. 今日明细表格里每一行都可以删除(前提是没有正在处理中的卡片),点删除会有
   "确定删除？"的二次确认。
6. 如果一句话说得不够清楚,AI 会在对话里追问,追问期间不会出现解析结果卡片,
   直到问清楚了才弹卡片;如果这句话看起来是想改一条已经写进数据库的记录,AI 会
   明确告诉用户现在还不支持这个操作;AI 服务连不上时会明确告诉用户"服务不可用",
   不会假装成功。
7. **写入接口自带"防重复"**:每样食物在被识别出来的那一刻,后端就会为它生成一个
   只在这一项生命周期内使用的幂等键,不管网络抖动导致前端重试几次"确认"写入,
   后端认这个键,同一个键只会真正插入一行,不会因为重试多插几条一样的记录。

这一步**不做**:今日明细表格里"已写入的行"本身不能再改数量(只能新增和删除);
不做拍照识别;不做"常吃食物库"。

---

## 每样食物的状态机

**关键澄清**:单项的"确认"/"修改"、以及输入框发送"确认修改"暂存修正文本,都
只是本地暂存/意图标记,不产生任何网络写入。真正对外发生的动作——写入数据库、
重新估算修改、放弃不写入——全部只发生在卡片**顶部**的"确认"/"放弃"两个按钮上
——"最上面的确认和放弃才是最终态决定者"。这也意味着:一旦顶部"确认"把某项真正
写入数据库,这一项在卡片里就**不再可撤销**了(不再有按钮),想撤销要去下面
"今日明细"表格里删那一行,不在卡片内重复做一套撤销逻辑。

```
                              ┌───────────┐
                   ┌─────────►│  pending  │◄──────────────────────────┐
                   │          │ 待处理(白/白)│                          │
                   │          └─────┬─────┘                           │
                   │                │                                  │
            点已变绿的按钮    ┌──────┴──────┐                            │
              (取消,        │             │                            │
            退回 pending)  点"确认"      点"修改"                        │
                   │          │             │                           │
                   │          ▼             ▼                           │
                   │   ┌────────────┐┌───────────────┐                  │
                   │   │ to_confirm ││   to_modify    │                  │
                   │   │本地暂存(绿)││ 本地暂存(绿),   │                  │
                   │   │不写库,     ││ 输入框切修改模式 │                  │
                   │   │等顶部"确认"││(纯前端态,无请求)│                  │
                   │   └─────┬──────┘└───────┬────────┘                 │
                   │         │                │ 输入框发送"确认修改"       │
                   │         │                │ (纯本地,记下修正文本,     │
                   │         │                │  不发请求)               │
                   │         │                ▼                         │
                   │         │         ┌─────────────────┐              │
                   │         │         │   to_reparse     │              │
                   │         │         │ 已暂存修正文本,   │              │
                   │         │         │ 该项下方留        │              │
                   │         │         │ "修改:原话…"     │              │
                   │         │         │ 等顶部"确认"批量   │              │
                   │         │         │ 触发重新估算       │              │
                   │         │         └────────┬─────────┘              │
                   │         │                  │ 顶部"确认"(批量)         │
                   │         │                  ▼                        │
                   │         │         ┌─────────────────┐               │
                   │         │         │   modifying      │               │
                   │         │         │  后端重新估算中   │               │
                   │         │         └────────┬─────────┘               │
                   │         │                  │                         │
                   │         │      请求结束(不管成功失败,都直接           │
                   │         │      回到 pending,不产生新状态,            │
                   │         │      区别只是附带的展示文字不同):          │
                   │         │        ·成功→更新预览值,该项下方           │
                   │         │          留"修改:原话…"小字保留作溯源       │
                   │         │        ·失败→数值退回修改前,该项下方        │
                   │         │          的"修改:…"替换成"修改失败,        │
                   │         │          请重新描述"(存在 modifyError      │
                   │         │          这个展示字段里,不是新状态)         │
                   │         │                  │                         │
                   │         └─────────────────►回到 pending ◄────────────┘

     ══════ 以上都不写数据库,只是暂存/编辑 ══════

     卡片顶部"确认"(批量:对 to_confirm 项写库,同时对 to_reparse
                    项触发重新估算)
                   │                              卡片顶部"放弃"(批量,影响所有
                   ▼                              还不是 confirmed 的项:pending/
            ┌────────────┐                        to_confirm/to_modify/to_reparse)
            │ confirmed  │◄────── 写入成功(单项失败保留在 to_confirm,             ▼
            │  已写入,   │        附错误提示,可靠顶部"确认"重试)          ┌────────────┐
            │  终态,不可 │                                              │ abandoned  │
            │  在卡片内  │                                              │终态,不写入 │
            │  撤销      │                                              └────────────┘
            └────────────┘
```

**状态穷尽性**:卡片里的每一项从出现那一刻起就是 `pending`,在
`to_confirm`/`to_modify`/`to_reparse`/`modifying` 之间循环,最终被卡片顶部的
"确认"或"放弃"收成 `confirmed`/`abandoned` 两个终态之一——估算失败的食物从一
开始就不会进入卡片(已经在识别播报消息里说明,见"这一段业务在做什么"第2条),
不需要卡片状态机再处理这类情况。**"卡片这一批操作全部结束"**指的是:所有项都
到达 `confirmed`/`abandoned`——这时才触发一次性的总结(见下方"LLM 上下文管理"
一节)。

**顶部"确认"/"放弃"按钮禁用规则**:只要卡片内有任意网络请求在进行中(顶部
"确认"这次批量动作本身,包含写入和重新估算两类请求),两个顶部按钮都禁用;单项
的确认/修改暂存按钮同样禁用(避免边处理边有新的暂存变化)。

**输入框直接打字(没点"修改")时的判断**:

1. 输入框当前是"修改模式"(有 `modifyingItemId`)→ 这条消息是对那一项的修正
   说明,本地暂存进 `to_reparse`(不发请求,等批次收尾时统一重新估算)。
2. 输入框普通模式,但存在还没到 `confirmed`/`abandoned` 的残留项(`pending`/
   `to_confirm`/`to_modify`/`to_reparse`)→ 弹"还有 N 项未确认,确定放弃吗"
   二次确认;选"放弃并继续"才真正发送,这些残留项转 `abandoned`(等同于点了
   顶部"放弃")。
3. 都不是 → 正常发送新消息。

---

## UI 还原:对照原型图,以及本轮的行为调整

设计以 [`docs/design/ui-bundle/DietPhone.dc.html`](../docs/design/ui-bundle/DietPhone.dc.html)
"记录"tab 为准。

- **今日明细卡片**:照抄原型(列头、四个固定餐次分组、展开/收起、空分组浅色)。
  **有未处理完的解析结果卡片时,每一行的删除按钮禁用**(灰态,不可点),防止两块
  界面同时改数据。
- **解析结果卡片**:整体框架照抄原型(浅绿描边、每项两行展示),视觉上像从上方
  assistant 消息气泡向下"长出来"(不留缝隙,细节留给实现阶段调)。
  - 顶部:原有"确认"是**批量提交所有暂存确认项 + 触发所有暂存修改项重新估算**
    的统一入口,新增**"放弃"**按钮(次级/幽灵样式,和"确认"并排);两者在有网络
    请求进行中时禁用。
  - 每项食物:"确认"/"修改"互斥双态按钮(白/绿,点已变绿的取消)。
  - 暂存修改后:该项下方多一行"修改:{用户输入前10字}…"(此时数值还是修改前的
    旧值,要等顶部"确认"触发重新估算才更新);重新估算完成后:数值更新,
    "修改:…"小字保留作溯源;重新估算失败:数值退回修改前,"修改:…"替换成
    "修改失败,请重新描述"。
  - 该批某一项顶部批量写入失败:该项保留暂存态(绿,"确认"),附一行"写入失败,
    可重试"(下次点顶部"确认"会重新尝试这一项,靠幂等键保证不会重复插入)。

| 原型里有                | Demo 阶段怎么处理          | 为什么                               |
| ----------------------- | -------------------------- | ------------------------------------ |
| "今日明细/常吃食物"分栏 | 不做,固定今日明细          | `food_favorite` 是 MVP 才建的表    |
| 输入胶囊拍照按钮        | 不做                       | 照片入口是 MVP+ 范围(§11.1)         |
| 顶部"摄入/目标/Δ"      | UI 做,目标/Δ 暂时"—"占位 | 依赖 1.11 BMR/1.12 运动消耗,现在没有 |

---

## LLM 上下文管理(两种环境,各自喂给模型什么)

原则来自 SPEC §6.4:"每次 LLM 调用只发送完成当前意图所需的消息、图片和结构化状态,
不默认把 7 天完整历史全部发送给第三方"——**`chat_message` 表里的对话历史是给人看
的 UI 展示层,从来不会被整表转发给模型**。

"记录"页在任意时刻处于两种互斥的环境之一,LLM 该带什么上下文由**所处环境**决定,
不是零散地按"调用了哪个函数"判断:

### 环境一:普通录入(默认态)

**RecordTab 没有"未结束"的解析卡片时**处于这个环境。

**`parse_diet_text` 的触发条件/输入/输出**:

- **触发条件**:普通录入环境下用户发的**每一条**消息都会触发一次调用,没有额外的
  "先判断是不是想记录饮食"的前置分类步骤——判断"这句话到底想干什么、能不能解析
  出结构化结果"本身就是 `parse_diet_text` 这一次调用要做的事,不是调用它之前的
  另一道关卡。
- **输入**:`client`、这一轮的原始文本 `user_text`、以及 `today_context`(见下)。
- **输出**:`DietParseResult{intent, outcome, meal_slot, items, message}`。
  `intent` 四选一(`new_entry`/`correct_pending_item`/`edit_existing_entry`/
  `no_log_intent`,详见"零、intent/outcome 两维契约"),`outcome` 只在
  `intent` 是"要解析出结构化食物信息"(`new_entry`/`correct_pending_item`)时
  才有意义,四选一(`resolved`/`needs_clarification`/`service_unavailable`/
  `invalid_model_output`);`intent` 是 `no_log_intent`/`edit_existing_entry`
  时 `outcome` 为 `None`,`message` 直接是得体的回应文案。`handle_new_message`
  的编排逻辑先按 `intent` 分支,`intent=new_entry` 时再按 `outcome` 分支。

**`today_context` 装什么**(两块拼在一起的完整信息):

1. **今日完整对话记录**——当前归属日(不是 7 天)全部 `chat_message`,按发生顺序
   拼成"[用户]/[AI]"轮流的文本;这次设计的前提是聊天记录本身只保留一天,所以
   "完整"和"够短"不矛盾,不需要再做摘要压缩。
2. **今日明细,解析成一张完整的 Markdown 表格**——当前归属日全部 `meal_entry`,
   列同今日明细 UI(餐次/食物/数量/kcal/碳水/蛋白/脂肪/纤维),缺失营养素显示
   `—`,不用 `0` 顶替(AGENTS.md 铁律同样适用于喂给模型的这份数据,不只是数据库
   和 UI)。

**退出时机**:这次解析 `intent=new_entry` 且 `outcome=resolved` 且产出至少一个
**估算成功**的 item → 立刻进入"解析卡判定中"环境。如果全部估算失败,或者
`intent`/`outcome` 落在其它任何分支,不产出卡片,仍然留在"普通录入"环境,下一条
消息还是带完整 `today_context` 的正常解析(这也是"追问会循环"的原因——每一轮
回答都还在这个环境里,而且因为对话记录本身就在 today_context 里,模型天然能看到
前面问过什么,不需要额外拼接"上一轮问了什么")。

### 环境二:解析卡判定中

**存在未结束的解析卡片期间**处于这个环境。这段时间里,输入框发"确认修改"只是把
修正文本本地暂存进 `to_reparse`,不触发任何 LLM 调用;真正的"修改重新估算"调用
发生在卡片顶部"确认"点击那一刻,对所有暂存了修改的项各自独立发一次请求——每次
都**只关注被修改的这一条目**(原来识别的食物名/生熟/克重 + 用户这次的修正说明),
完全不带 `today_context`,也不带同一批里其它食物的信息。这是有意收窄的:这一步
要回答的问题就是"这项食物改成什么样了",给它今天吃了什么这类更大范围的信息没有
帮助,反而可能把模型带偏。这些调用**不写任何 chat_message**——不管重新估算成功
还是失败,过程中都不产生对话气泡,统一等这批全部结束时由收尾总结一次性说明。

这个环境里,输入框直接打字(没点"修改")**不会**触发一次带 today_context 的新
解析——会先被"未确认放弃"弹窗拦住(见"输入框直接打字时的判断"),只有真的选择
"放弃并继续"、让卡片结束、退出这个环境后,新消息才会以"普通录入"环境的方式(带
today_context)重新解析。

**退出时机**:卡片"全部结束"——所有项都到达 `confirmed`/`abandoned`(卡片顶部
"确认"/"放弃"处理完;这一次点击里同时写库和触发重新估算,重新估算出来的项会先
回到 `pending` 等下一次顶部确认,不算这次就"结束")。这一刻:①触发一次性的
`recap_batch_status` 总结(这条总结本身也会作为一条 assistant `chat_message` 被
写入,和识别结果播报消息共用同一个 `batch_id`);②回到"普通录入"环境——下一条
新消息的 `today_context` 会自动包含刚刚这一轮新写入的食物(今日明细表格部分)和
这条总结消息(对话记录部分),因为 `today_context` 每次都是现查
`list_today_chat_messages`+`list_today_meal_entries` 现拼的,不是缓存的。

### 两个环境之外:两个不算"环境切换"的具体动作

- `estimate_items`(1.7,营养估算,不变):不是环境划分的一部分,是"解析卡判定中"
  环境内部、紧跟在 resolved 的 parse 后面自动触发的一个步骤。每个食物一次独立
  调用,只带食物名+生熟状态,不带对话历史、不带今日已确认食物、不带同批其它食物。
- `recap_batch_status`(批次总结):是"解析卡判定中"环境**退出那一刻**触发的收尾
  动作,只带这一批食物的终态列表(名称/克重/`confirmed`+kcal 或 `abandoned`),
  不带对话历史、不带今日其它历史食物。

### 汇总表

| 调用点                                         | 所属环境                        | 送进去的内容                                                         | 明确不送的                                                                          |
| ---------------------------------------------- | ------------------------------- | -------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `parse_diet_text`(新消息)                    | 普通录入                        | 用户原始文本 +`today_context`(今日完整对话记录 + 今日明细 md 表格) | 7 天历史(只保留/只用今日一天);卡片内部中间状态(pending/to_confirm 等还没写库的东西) |
| `parse_diet_text`(修改重新估算,复用同一函数) | 解析卡判定中,批次收尾时批量触发 | "原来识别的+这次修正"合成文本                                        | `today_context`(不含对话记录、不含今日明细);同批其它食物                          |
| `estimate_items`                             | 解析卡判定中(内部步骤)          | 单个食物名+生熟状态                                                  | 对话历史;今日明细;同批其它食物                                                      |
| `recap_batch_status`                         | 解析卡判定中→普通录入(退出时)  | 这一批食物的终态列表                                                 | 对话历史;今日明细                                                                   |

**为什么这样划分**:核心是"只给当前这个具体任务刚好够用的信息",不是"能给的都
给"——一是 SPEC §6.4 本身的要求(不送 7 天完整历史给第三方,现在只保留一天,天然
满足这条);二是实际效果上无关信息越多模型越容易被带偏(比如把"今天吃了什么"错
当成"这次要记录什么"混进解析结果,这也是"修改重新估算"和"营养估算"两处仍然坚持
不带 today_context 的原因——它们的任务范围本来就该收得比"新消息"窄)。四个调用点
之间完全不共享"上下文对象"或"会话状态"——每次都是一次独立、无状态的函数调用,
所需的一切通过参数显式传入,和 1.6-1.8 已经建立的纯函数/无状态服务风格一致;
"环境"只是描述 RecordTab 前端状态机当前所处的阶段,不是后端维护的会话概念。

---

## 用户旅程(整体)

```
【发一条新消息】→(按上面"输入框直接打字时的判断"三条规则路由)
        │
        ▼ 走新消息流程
   POST /chat/messages { text }
        ├─ 网络/后端连不上 ──► [发送失败,可重试]
        ▼ 看 intent
        ├─ no_log_intent ──► 只出现一条回应气泡,循环回普通录入
        ├─ edit_existing_entry ──► 回一句"暂不支持修改已有记录"的提示气泡,
        │                          循环回普通录入
        └─ new_entry ─► 看 outcome
              ├─ needs_clarification ──► 只出现追问气泡,循环直到 resolved 才弹卡片
              ├─ service_unavailable / invalid_model_output ──► 对应提示气泡
              └─ resolved ─► 播报识别结果(估算失败的项在这句话里说明原因,不进
                              卡片);若有至少一项估算成功 ─► 出现【解析结果卡片】,
                              各项初始 pending,走"每样食物的状态机";若全部失败
                              ─► 没有卡片,直接留在普通录入环境
                              → (有卡片时)全部到终态后,追加一条总结气泡

【今日明细表格删除一行】(无未处理卡片时才可操作)
点删除 → "确定删除？" → 确定 → [删除中…] → 成功/失败

【重新打开"记录"页】
挂载时查一次是否存在识别过、但没走完的上一批(见"未完成批次的恢复"一节)
        ├─ 没有 ──► 正常进入普通录入环境
        └─ 有 ──► 弹"上次有 N 项识别结果没有处理完,是否继续?"
              ├─ 继续 ──► 用保存的完整预览重建【解析结果卡片】,回到 pending 接着走
              └─ 放弃 ──► 这些项标记 abandoned,进入普通录入环境
```

---

## Context(技术背景)

1.6-1.8 已交付纯 service 层:文本解析→逐项 LLM 估算→营养计算,产出
`ConfirmationPreview`,但不落库、不接 API、不接 UI。本步接上真正的写入、查询、
删除,以及确认/修改/放弃/总结的完整交互闭环,并补上幂等写入保护和刷新后的批次
恢复。

范围边界:`daily_summary`/结转/A1 图表的目标值和运动消耗联动是 1.10-1.12 的范围。

真源:SPEC §6.1(归属日公式)、§6.4(chat_message 最小字段 + LLM 上下文最小化原则)、
§7.6(未拿到可信结果前不写 meal_entry)、§7.8(source_tag)、§2.1 组件B、§11.1。
AGENTS.md 铁律:不加 `user_id`;缺失营养素用 `null` 不用 `0`;未拿可信结果前不写
`meal_entry`。

**迁移**:本步需要**一个新的 Alembic migration**——给 `meal_entry` 加幂等键列,
给 `chat_message` 加批次追踪用的列,详见下方"幂等写入"和"未完成批次的恢复"两节。

**intent/outcome 两维契约**:本步还要动一处 1.6-1.8 里已经合并进 `main` 的
代码——`DietParseResult` 新增一个 `intent` 字段,详见下一节。这不是本步的写入/
UI 范围,但是设计整条状态机时发现的一个真实的契约缺陷,顺手在本步一起改掉。

---

## 零、intent/outcome 两维契约

**这一步要解决的问题**:用户发的一句话,系统要先分清楚两件独立的事——"用户想
干什么"(新增一条饮食记录?修正一条还没写库的识别结果?改一条已经写库的记录?
还是根本没有记录意图,只是在闲聊/问常识)和"如果是要解析出食物信息,这次解析
成不成功"。这两件事如果揉进同一个扁平的 outcome 里,枚举会越堆越乱,而且"用户
想干什么"和"这次解析成不成功"其实是两个正交的维度,揉在一起会让评测数据集标注
的时候很难一致判断。所以拆成两个字段,各自负责一件事。

**schema**:

- `backend/app/schemas/diet_parse.py`:`DietParseResult` 有 `intent`/`outcome`
  两个字段:
  ```
  intent(DietParseResult 上,四态)
  ├─ new_entry              新增饮食
  ├─ correct_pending_item   修正尚未写入的解析结果(只在"修改重新估算"这条
  │                          调用路径里由模型自我确认这个值,`handle_new_message`
  │                          走的"新消息"路径不会主动按这个值分支)
  ├─ edit_existing_entry    修改已有记录——分类目的是让模型能识别出"这是在说
  │                          改已有记录",从而生成得体的"暂不支持修改已有记录"
  │                          回应,而不是被误判成 needs_clarification 或硬套成
  │                          新增食物解析;这个操作本身现在不支持,后续里程碑
  │                          再做
  └─ no_log_intent          没有记录意图(闲聊、单纯问营养常识、寒暄等)

  outcome(只在 intent 是"要解析出结构化食物信息"的情况下才有意义;
  intent=no_log_intent 或 edit_existing_entry 时 outcome 为 None,message
  直接给出得体的回应文案)
  ├─ resolved
  ├─ needs_clarification
  ├─ service_unavailable
  └─ invalid_model_output
  ```

  `model_validator` 约束:`intent∈{new_entry, correct_pending_item}` 时
  `outcome` 必须非空,并且沿用原来的"`resolved`⇒items/meal_slot 非空且
  message None;其余⇒items 空且 message 非空"这条形状约束;
  `intent∈{no_log_intent, edit_existing_entry}` 时 `outcome` 必须是 `None`,
  `message` 非空、`items` 空。
- `backend/app/services/nl_parse.py`:prompt 教模型先判断 intent 再判断
  outcome——先看这句话是在说"新增吃了什么"、"修正一个刚识别出来但还没确认写库
  的东西"、"想改一条已经记过的记录",还是"跟饮食记录无关";确定是前两者之一,
  才继续判断信息是否完整、能不能解析出结构化结果。
- `handle_new_message` 先按 `intent` 分支:`no_log_intent`/`edit_existing_entry`
  → 直接把 `message` 当 assistant 回复,不产出卡片;`new_entry` → 再按
  `outcome` 走解析/估算流程。

**评测数据集**:`tests/backend/eval/food_text_parse_dataset.csv` 有
`expected_intent`/`expected_outcome` 两列,`backend/scripts/eval_nl_parse.py`
分别统计两个维度的准确率;`tests/backend/test_demo_03_nl_parse.py` 覆盖 intent
四态的用例。跑一次 `eval_nl_parse.py`(真实 LLM 调用,产生费用),贴出数字给你
确认结构合法率 ≥95%。`tasks/STATUS.md` 1.8 行的描述和评测数字同步更新(本步最后
"覆盖更新 STATUS.md"那一步一并做)。

**Git 流程说明**:AGENTS.md 要求"碰共享地基(SPEC §4/§5/§7)要单独开分支先合,再
通知其他分支 rebase"。`DietParseResult`/`parse_diet_text` 严格说也是共享地基,但
目前除了当前这个 `feature_demo_04_write_path` 分支之外没有其它并行分支在依赖这份
契约,没有谁需要被通知 rebase——这版计划打算直接在当前分支里、作为本步最靠前的一
个子步骤做这个改动,不单独开分支/PR,减少流程开销。如果你更想按字面规则走"先出一
个小 PR 单独合这个契约改动,再开 1.9 分支",告诉我,我会调整实现顺序。

---

## 一、后端服务层

### 术语约定:"今日"/"一天" = 当前归属日,不是滚动 24 小时窗口

本文档以及代码里所有"今日"/"今天"/"一天"(`list_today_meal_entries`/
`list_today_chat_messages`/`today_context`/"对话历史只加载一天"等)指的都是
**当前归属日**——`attribution_date(now)` 算出来的那个日期字符串,过滤条件永远是
`date == attribution_date(now)`。**不是**"从当前时刻往前滚动 24 小时"。两者在
归属日边界附近差异很明显:比如本地时间凌晨 1 点,过去 24 小时里跨了两个自然日,
但当前归属日只有一个(前一天,因为还没到本地 2 点的切换点)——所有"今日 XX"的
查询都应该按归属日这一个确定的日期字符串过滤,不是按时间窗口过滤。

### 归属日:时间来源是"用户所在时区",不是服务器系统时区

正确做法:**以服务器可靠的 UTC 时刻为准,显式转换成用户所在时区**,而不是依赖
操作系统的时区设置——如果后端部署在和用户不同时区的机器/云主机上(比如服务器是
UTC,用户在中国),用服务器系统本地墙钟算出来的"本地时间"其实是服务器所在地的
时间,不是用户的,归属日会算错。

```python
# backend/app/config.py 新增
user_timezone: str = "Asia/Shanghai"   # IANA 时区名,Demo 阶段固定配置。
    # 跨时区旅行(用户出差换时区)是 §9.4 RC 范围,本步不处理;但"服务器和用户
    # 本来就不在同一个时区"这个更基础的问题,必须现在就处理对。
attribution_offset_hours: float = 2.0
```

```python
# backend/app/services/attribution.py(新,纯函数)
from zoneinfo import ZoneInfo

def attribution_date(now_utc: datetime | None = None, *,
                      timezone_name: str | None = None,
                      offset_hours: float | None = None) -> str:
    """业务今日 B = date(用户所在时区的本地时间 − offset_hours)。now_utc 必须是
    tz-aware 的 UTC 时刻(默认 datetime.now(timezone.utc)),显式 astimezone 到
    settings.user_timezone(或测试传入的 timezone_name)再减偏移量取 date。不用
    服务器系统时区,不用 naive datetime。"""
    now_utc = now_utc or datetime.now(timezone.utc)
    tz = ZoneInfo(timezone_name or settings.user_timezone)
    local = now_utc.astimezone(tz)
    offset = offset_hours if offset_hours is not None else settings.attribution_offset_hours
    return (local - timedelta(hours=offset)).date().isoformat()

def utc_now_iso(now_utc: datetime | None = None) -> str:
    """created_at:UTC-0 ISO8601,唯一真时间,不受时区配置影响。"""
```

1.10 做结转任务/7 天清理边界时应复用同一个 `attribution_date()`,不要重新定义
时区/偏移量逻辑。

### 批次归属日一致性

卡片顶部"确认"是对多样食物各自独立发请求(见"已决定的设计取舍"),如果每个
请求都在服务端各自读"当前时刻"算归属日,网络排队可能让同一次点击触发的写入被
拆进两个不同的归属日(比如恰好跨过本地 02:00 的切换点)。所以归属日的时间来源
是**由前端在触发这次批量动作的那一刻生成一次 UTC 时间戳,同一批所有请求(每个
`POST /meal-entries` + 随后的 `POST /chat/messages/recap`)都携带这同一个值**;
后端不自己读当前时刻,`confirm_meal_entry`/`recap_batch_status` 都从请求里取
这个 `now_utc` 传给 `attribution_date()`。1.10 结转任务同样应该遵守"同一批写入
共享同一个时刻"这个原则,不在同一个结转批次里对不同的行分别读当前时刻。

### 幂等写入(呼应"防止网络重试造成重复记录")

**新增迁移**(revision 名称实现时用 `alembic revision` 生成,承接
`5dfa0f2976f3`):给 `meal_entry` 加一列 `confirmation_id`(每一项食物在被识别
出来那一刻由后端生成一次、贯穿其整个生命周期——包括改过之后——的幂等键),加
唯一索引;同一个 revision 里也给 `chat_message` 加 `batch_id`/`kind`/
`food_summary_json` 三列(详见"未完成批次的恢复"一节)。表当前应为空(和上一次
迁移一样,`upgrade()`/`downgrade()` 先查各表 `COUNT(*)`,非空 raise 拒绝执行,
这个安全模式延续下来)。

```python
def upgrade() -> None:
    bind = op.get_bind()
    for table in ("meal_entry", "chat_message"):
        count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        if count != 0:
            raise RuntimeError(f"{table} 非空,拒绝变更;需要人工评估数据后再处理")
    op.add_column('meal_entry', sa.Column('confirmation_id', sa.Text(), nullable=False))
    op.create_index('ix_meal_entry_confirmation_id', 'meal_entry',
                     ['confirmation_id'], unique=True)
    op.add_column('chat_message', sa.Column('batch_id', sa.Text(), nullable=True))
    op.add_column('chat_message', sa.Column('kind', sa.Text(), nullable=True))
    op.add_column('chat_message', sa.Column('food_summary_json', sa.Text(), nullable=True))

def downgrade() -> None:
    # 同样先查 COUNT(*) 非空则 raise,再依次 drop 新增的列/索引
    ...
```

```python
# backend/app/services/meal_entry_write.py
def confirm_meal_entry(db: Session, preview: ConfirmationPreview,
                        confirmation_id: str, *, now_utc: datetime) -> MealEntry:
    """幂等:先按 confirmation_id 查找,命中直接返回已有记录(不重复插入,这是
    应用层兜底);confirmation_id 列上的唯一索引是数据库层最后一道防线——插入时
    如果撞上唯一索引冲突(并发的真实网络重试导致两次插入几乎同时发生),捕获
    IntegrityError、rollback 后按 confirmation_id 重新查一次并返回该记录,不让
    这种场景从"幂等返回旧记录"退化成向上抛异常。命中 kcal is None 且是"首次见到
    这个 id"才 raise UntrustedNutritionError——如果这个 id 之前已经成功写过
    (说明当年校验通过了),重放请求直接返回旧记录,不用再校验一遍。now_utc 是
    这次批量确认动作的统一时刻(见"批次归属日一致性"),用来算这一行的归属日。"""
    existing = db.query(MealEntry).filter_by(confirmation_id=confirmation_id).one_or_none()
    if existing is not None:
        return existing
    if preview.nutrients.kcal is None:
        raise UntrustedNutritionError(...)
    try:
        entry = MealEntry(..., confirmation_id=confirmation_id,
                           date=attribution_date(now_utc))
        db.add(entry); db.commit(); db.refresh(entry)
        return entry
    except IntegrityError:
        db.rollback()
        return db.query(MealEntry).filter_by(confirmation_id=confirmation_id).one()
```

`confirmation_id` 由后端在 `handle_new_message` 识别出 resolved 项那一刻为
每一项生成一次(和 `batch_id` 一起,见"未完成批次的恢复"一节),随 API 响应
返回给前端;前端不自己生成,后续不管暂存/取消暂存/修改/顶部批量提交重试,始终
原样携带这个后端签发的值。取消已写入的记录走"今日明细"表格的
`DELETE /meal-entries/{id}`(天然幂等,重复删不存在的 id 就是 404,不需要额外
处理)。`confirmed` 是卡片内的终态,没有任何路径能在卡片内让同一个
`confirmation_id` 被复用去写第二行;如果用户想再记一次同样的食物,只能重新
打字,那会走一次新的识别,生成一个全新的 `PendingItem` 和全新的
`confirmation_id`。

### 未完成批次的恢复(呼应"刷新/关闭页面后重新打开")

识别出 resolved 项那一刻,除了给每项生成 `confirmation_id`,后端还会为这一整批
生成一个 `batch_id`(这张卡片的身份标识),随 API 响应一起返回。这批食物的识别
结果——每项完整的预览数据(不只是食物名/克重这类摘要,是能直接重建卡片的完整
快照)连同各自的 `confirmation_id` 和这个 `batch_id`——会整份写进播报这批识别
结果的那条 assistant `chat_message` 里(`kind='recognition'`,
`food_summary_json` 装这份快照)。卡片收尾时,`recap_batch_status` 写的总结
消息复用同一个 `batch_id`,`kind='recap'`,代表"这张卡片关闭了"。

`find_open_batch(db, *, now_utc=None) -> OpenBatch | None` 是一个纯查询函数:
今日 `chat_message` 里找最后一条 `kind='recognition'` 的消息;如果同一个
`batch_id` 已经有一条 `kind='recap'` 的消息,返回 `None`(这批已经正常收尾)。
否则,把这条 recognition 消息的 `food_summary_json` 逐项和今日 `meal_entry`
的 `confirmation_id` 集合做精确的 in/not-in 判断——已经命中的项(已经写库了)
过滤掉,剩下"识别过但没写进 meal_entry"的项;如果一项不剩(比如只是收尾那次
recap 请求没送达,数据其实已经全部写完,这种情况下也返回 `None`,不用额外提示,
呼应下面"批次收尾的解耦"一段),否则返回 `OpenBatch{batch_id, items}`。这个
函数本身是纯函数、可以直接单元测试,判断逻辑不依赖前端怎么用它。

`RecordTab` 挂载时(在已有的"拉今日聊天记录+今日明细"基础上)调一次
`GET /chat/messages/open-batch`。返回非空时弹一个对话框:"上次有 N 项识别结果
没有处理完,是否继续?",按钮是"继续"/"放弃":

- **继续**:纯前端操作,不需要额外请求——用返回的完整预览数据把这些 item 重建
  成 `PendingItem`(状态回 `pending`,直接复用已经签发过的 `confirmation_id`),
  重新弹出解析结果卡片,`batch_id` 也带回 `RecordTab` 状态,这批之后仍走正常的
  顶部确认/放弃→recap 流程,复用同一个 `batch_id` 关闭它。如果丢失前用户已经
  点了"修改"但还没到批次收尾(处于 `to_reparse`),恢复出来的是修改前的原始
  预览值,未提交的修改草稿不会被恢复。
- **放弃**:调一次已有的 `POST /chat/messages/recap`(带上这个 `batch_id`,
  items 全标 `abandoned`),复用下面"批次收尾"用的 `recap_batch_status`,不需要
  新增写入端点。这条 recap 消息一写,下次挂载时 `find_open_batch` 判断"是否已有
  同 `batch_id` 的 `kind=recap`"就会认为这批已收尾,不会重复弹提示。

### `backend/app/services/chat.py`(新)

```python
def record_chat_message(db, *, role: Literal["user", "assistant"], content: str,
                         image_ref: str | None = None, batch_id: str | None = None,
                         kind: Literal["recognition", "recap"] | None = None,
                         food_summary_json: str | None = None,
                         now_utc=None) -> ChatMessage: ...
def list_today_chat_messages(db, *, now_utc=None) -> list[ChatMessage]: ...
```

### `backend/app/services/meal_entry_write.py`(其余部分不变)

```python
def list_today_meal_entries(db, *, now_utc=None) -> list[MealEntry]:
    """WHERE date=今日归属日,按 MEAL_SLOT_VALUES 顺序分组排序。两个用途:①今日
    明细查询 API;②chat_turn 里给 LLM 当 today_context。"""

def delete_todays_meal_entry(db, entry_id: int, *, now_utc=None) -> bool:
    """找不到,或 entry.date != 今日归属日 → False。"""
```

### `nl_parse.py` 的改动(1.8 已交付函数,扩展签名,向后兼容)

```python
async def parse_diet_text(client: LlmClient, user_text: str, *,
                           today_context: str | None = None) -> DietParseResult: ...
```

### `backend/app/services/chat_turn.py`(新,编排层)

```python
def format_today_conversation(messages: list[ChatMessage]) -> str:
    """纯函数。今日(当前归属日,不是 7 天)全部 chat_message,按发生顺序拼成
    "[用户]/[AI]"轮流的文本。"""

def format_today_meal_entries_markdown(entries: list[MealEntry]) -> str:
    """纯函数。今日全部 meal_entry → 一张完整 Markdown 表格,列同今日明细 UI
    (餐次/食物/数量/kcal/碳水/蛋白/脂肪/纤维);缺失营养素显示 `—`,不用 `0`
    顶替(AGENTS.md 铁律,喂给模型的数据也要遵守,不只是数据库和 UI)。"""

def build_today_context(messages: list[ChatMessage], entries: list[MealEntry]) -> str:
    """把上面两块拼成一个字符串(先对话记录、后今日明细表格),作为
    parse_diet_text 的 today_context 参数。"""

async def handle_new_message(db, client, user_text, *, now_utc=None) -> ChatTurnResult:
    """①先查 list_today_chat_messages(db)/list_today_meal_entries(db)、
    build_today_context(...)(这时候还不含这一轮,因为还没写入,避免这一轮的
    文本在 today_context 和 user_text 里重复出现一遍)。
    ②record_chat_message(user, content=user_text)。
    ③parse_diet_text(client, user_text, today_context=...),拿到 intent+outcome。
    ④intent 是 no_log_intent/edit_existing_entry → assistant=message,写
    chat_message,items=[]。
    ⑤intent 是 new_entry 且 outcome 非 resolved → assistant=message,写
    chat_message,items=[]。
    ⑥intent 是 new_entry 且 outcome=resolved → estimate_items;把结果按
    `outcome.outcome==resolved` 拆成两份:resolved 的那份生成一个 batch_id +
    各自的 confirmation_id,包成 ConfirmableItem 列表;失败的那份连同各自的
    失败原因,写进这条确定性播报消息的文字里("我识别到了……;以下未能识别:
    ……")。这条 assistant 消息写 chat_message 时,如果 resolved 列表非空,
    `kind='recognition'`、`batch_id` 是这批的 id、`food_summary_json` 是完整
    的 ConfirmableItem 快照;如果 resolved 列表为空(全部估算失败),这条消息
    就是唯一的回复,不带 kind/batch_id。返回的 items 只包含 resolved 的那份
    (连同 batch_id),全部失败时 items 为空、不产出 batch_id。"""

async def handle_modify_correction(db, client, original_item, meal_slot,
                                    correction_text, confirmation_id,
                                    *, now_utc=None) -> ModifyCorrectionResult:
    """批次收尾(顶部"确认")时,对每个 to_reparse 项各自独立调用一次。不新开
    LLM 契约,复用 parse_diet_text,合成"原来识别的+这次修正"的文本。恰好 1 项
    且 outcome=resolved → estimate 该项,meal_slot 固定用传入值,返回新的
    ItemEstimateOutcome(confirmation_id 不变,原样带回);否则判定这项修正
    失败,返回失败原因。**不写任何 chat_message**——不管成功失败,这次调用
    全程不产生对话气泡,统一等批次收尾的 recap 一次性说明。"""

def find_open_batch(db, *, now_utc=None) -> OpenBatch | None:
    """纯查询,见"未完成批次的恢复"一节。"""

async def recap_batch_status(db, client, batch_id: str, meal_slot: MealSlot,
                              items: list[BatchItemStatus], *, now_utc=None) -> ChatMessage:
    """整批结束时调用一次(包括"放弃恢复的旧批次"这个场景)。items 只含终态
    (confirmed/abandoned)。序列化后调 LlmClient.chat_json 生成一句总结,JSON
    契约 `{"summary": "..."}`。调用失败(网络/JSON 不合法)时退化成确定性拼装
    文案,不留白,同样写 chat_message,`kind='recap'`,复用传入的 `batch_id`、
    用 `now_utc` 算归属日。"""
```

### 估算失败项的播报

`estimate_items` 本来就按 item 返回 `list[ItemEstimateOutcome]`,失败项
`outcome != resolved`、`preview is None`、`message` 非空。`handle_new_message`
在生成识别结果播报消息时就已经按 `outcome.outcome == resolved` 把这批分成两份:
只有 resolved 的那份会被包成 `ConfirmableItem`、进入卡片状态机;失败的那份连同
各自的失败原因,直接写进这条播报消息的文字里播报掉,不再等前端消费。如果这批
全部失败,播报消息就是这一轮唯一的回复,不会有卡片,也就不会进入"解析卡判定中"
环境——这批不需要收尾总结,因为没有任何东西留在"待处理"。

---

## 二、后端 API 路由

**`backend/app/routers/chat.py`**

| Method | Path                          | Request                     | Response                     |
| ------ | ----------------------------- | --------------------------- | ---------------------------- |
| POST   | `/chat/messages`            | `ChatMessageIn`           | `ChatTurnResponse`         |
| POST   | `/chat/messages/modify`     | `ModifyCorrectionRequest` | `ModifyCorrectionResponse` |
| POST   | `/chat/messages/recap`      | `RecapRequest`            | `RecapResponse`            |
| GET    | `/chat/messages/today`      | —                          | `list[ChatMessageOut]`     |
| GET    | `/chat/messages/open-batch` | —                          | `OpenBatchOut \| None`      |

```python
class ChatMessageIn(BaseModel):
    text: str = Field(min_length=1)

class ConfirmableItem(BaseModel):
    confirmation_id: str
    outcome: ItemEstimateOutcome   # 复用 1.7 原 schema,不改动它本身

class ChatTurnResponse(BaseModel):
    user_message: ChatMessageOut
    assistant_message: ChatMessageOut
    intent: Intent
    outcome: LlmOutcome | None
    batch_id: str | None              # 产出卡片时才有值
    items: list[ConfirmableItem]      # 只含估算成功、进了卡片的项

class ModifyCorrectionRequest(BaseModel):
    confirmation_id: str = Field(min_length=1)
    original_item: ParsedFoodItem
    meal_slot: MealSlot
    correction_text: str = Field(min_length=1)

class ModifyCorrectionResponse(BaseModel):
    confirmation_id: str
    success: bool
    outcome: ItemEstimateOutcome | None   # success 时有意义
    failure_reason: str | None            # 失败时有意义

class BatchItemStatus(BaseModel):
    food_name: str
    quantity: float
    state: Literal["confirmed", "abandoned"]
    kcal: float | None = None       # confirmed 时有意义

class RecapRequest(BaseModel):
    batch_id: str
    meal_slot: MealSlot
    items: list[BatchItemStatus] = Field(min_length=1)
    now_utc: datetime

class RecapResponse(BaseModel):
    assistant_message: ChatMessageOut

class OpenBatchOut(BaseModel):
    batch_id: str
    items: list[ConfirmableItem]
```

**`backend/app/routers/meal_entries.py`**

| Method | Path                         | Request                                                        | Response                                                |
| ------ | ---------------------------- | -------------------------------------------------------------- | ------------------------------------------------------- |
| POST   | `/meal-entries`            | `ConfirmMealEntryRequest{confirmation_id, preview, now_utc}` | `MealEntryOut`,201(幂等命中时也是 201,内容是已有记录) |
| GET    | `/meal-entries/today`      | —                                                             | `list[MealEntryOut]`                                  |
| DELETE | `/meal-entries/{entry_id}` | —                                                             | 204;找不到/非今日 → 404                                |

```python
class ConfirmMealEntryRequest(BaseModel):
    confirmation_id: str = Field(min_length=1)
    preview: ConfirmationPreview   # 复用 1.7 原 schema,不改动它本身
    now_utc: datetime              # 这次批量确认动作的统一时刻

class MealEntryOut(BaseModel):
    id: int; confirmation_id: str; date: str; meal_slot: MealSlot
    food_name: str; quantity: float; unit: Unit
    kcal: float | None; carb_g: float | None; protein_g: float | None
    fat_g: float | None; fiber_g: float | None
    source_tag: SourceTag; created_at: str
```

`UntrustedNutritionError` → 422。Router 只做请求→服务函数→响应模型转换。

### LLM client 依赖注入(不变)

复用已有 `create_dashscope_client(client: httpx.AsyncClient)` 工厂;`main.py` 加
`lifespan` 管理共享 `httpx.AsyncClient`;新增 `backend/app/dependencies.py` 的
`get_llm_client`。

---

## 三、改动/新增文件清单

**后端**:`config.py`(改,加 `user_timezone`/`attribution_offset_hours`)、
`services/attribution.py`、`services/chat.py`、`services/meal_entry_write.py`
(含幂等逻辑)、`services/chat_turn.py`(含 `find_open_batch`)、`schemas/chat.py`
(含 `ConfirmableItem`/`ModifyCorrectionRequest`/`ModifyCorrectionResponse`/
`RecapRequest`/`OpenBatchOut` 等)、`schemas/diet_parse.py`(改,加 `intent`
字段)、`schemas/meal_entry.py`(含 `ConfirmMealEntryRequest`)、
`dependencies.py`;`services/nl_parse.py`(改,加 `today_context` + intent
判断的 prompt);`main.py`(改);
`migrations/versions/<新revision>_add_confirmation_id_and_batch_tracking.py`
(新,`meal_entry` 加 `confirmation_id`,`chat_message` 加
`batch_id`/`kind`/`food_summary_json`);`tests/backend/conftest.py`(改,
新增 `migrated_client` fixture);`tests/backend/test_demo_04_llm_live.py`
(新,真实 LLM API 测试,见"四、后端测试")。

**前端**:`types/diet.ts`、`lib/chat.ts`、`lib/mealEntries.ts`、
`components/ChatInputBar.tsx`、`components/ChatHistory.tsx`、
`components/ConfirmationCard.tsx`(顶部确认/放弃;每项确认/修改互斥双态)、
`components/UnconfirmedGuardDialog.tsx`(泛化成通用二次确认对话框,"还有未确认
项"和"是否继续上一批"两处复用)、`components/TodayEntryList.tsx`(卡片存在时
删除按钮禁用)、`components/MealEntryRow.tsx`、`components/RecordTab.tsx`
(状态机归属地+挂载检测);`App.tsx`。样式加进 `global.css`+`tokens.css`,不
新建 per-component CSS 文件。

---

## 四、后端测试(`tests/backend/test_demo_04_*.py`)

- `test_demo_04_attribution.py`:用 `now_utc` + `timezone_name` 参数验证边界
  (如 UTC 时刻在 `Asia/Shanghai` 本地是 00:30/02:30/02:00:00 整点、跨月跨年);
  验证不同 `timezone_name` 传入得到不同归属日(证明确实按时区转换,不是读服务器
  系统时区);`offset_hours`/`Settings.attribution_offset_hours` 改成非默认值时
  边界跟着变。
- `test_demo_04_meal_entry_idempotency.py`(新,单独成文件,这是本步的关键正确性
  保证):相同 `confirmation_id` 调用 `confirm_meal_entry` 两次 → 只插入一行,
  第二次返回值等于第一次;不同 `confirmation_id` → 两行;数据库层唯一索引冲突
  场景(绕过应用层校验、并发插入同一个 `confirmation_id`)验证会被捕获并优雅
  返回已有记录,不抛异常;不同 `now_utc` 传入得到不同归属日的写入行为。HTTP 层
  `test_demo_04_meal_entries_router.py` 里补一个"重复 POST 相同 confirmation_id
  → 第二次仍 201 但不新增行"的场景。
- `test_demo_04_chat_service.py`:`record_chat_message`/`list_today_chat_messages`
  写入与归属日过滤,含 `batch_id`/`kind`/`food_summary_json` 的写入与查询。
- `test_demo_04_context_builders.py`(新):`format_today_conversation`——顺序
  正确、角色前缀正确;`format_today_meal_entries_markdown`——表格列正确、缺失
  营养素显示 `—` 不是 `0`/空;`build_today_context` 两部分都在、顺序固定。
- `test_demo_04_nl_parse_context.py`:`today_context` 传入/不传的 prompt 差异,
  1.8 原测试回归。
- `test_demo_04_chat_turn.py`:
  - `handle_new_message`:intent 四态 × outcome 四态的组合;new_entry+resolved
    场景下 `today_context` 正确进 prompt 且**不含这一轮刚发的消息本身**(避免
    和 user_text 重复);今日已有对话+已有明细的场景下,两部分都出现在传给
    stub client 的 prompt 里;`estimate_items` 部分失败时,失败项出现在播报
    消息文字里、不出现在返回的 items 里;全部失败时 items 为空、不产出
    batch_id。
  - `handle_modify_correction`:确认不带 today_context、不写 chat_message,
    成功/失败两种返回。
  - `find_open_batch`:今日无 recognition 消息 → None;有 recognition 且同
    batch_id 已有 recap → None;有 recognition 无 recap 但 food_summary_json
    里所有 confirmation_id 都已在 meal_entry 里 → None;部分未命中 → 返回
    缺失的那些项。
  - `recap_batch_status`:传入 confirmed/abandoned 混合的终态列表,stub client
    返回合法总结/失败两种情况(失败时走确定性兜底文案),写入的消息带正确的
    batch_id。
- `test_demo_04_meal_entry_write.py`:`list_today_meal_entries`/
  `delete_todays_meal_entry` 的过滤、防御性拒绝(幂等相关测试移到独立文件)。
- `test_demo_04_chat_router.py`:`POST /chat/messages`(intent/outcome 各
  分支)、`POST /chat/messages/modify`(成功/失败)、
  `GET /chat/messages/open-batch`(有/无未完成批次)、`POST /chat/messages/recap`
  正常/LLM 失败;空文本 422。
- `test_demo_04_meal_entries_router.py`:POST(含幂等重复场景)/GET/DELETE 正常/
  异常路径。

### `tests/backend/conftest.py` 新增 fixture(不变)

```python
@pytest.fixture
def migrated_client(tmp_path, monkeypatch) -> Iterator[MigratedClient]: ...
```

### 迁移测试

`test_demo_04_schema_migration.py`:`migrated_engine` 验证 `meal_entry` 新列/
唯一索引、`chat_message` 三个新列都存在;`upgrade()`/`downgrade()` 非空表时
拒绝执行(沿用上一次迁移的测试模式)。

### 真实 LLM API 测试(`test_demo_04_llm_live.py`)

和 1.8 的 `test_demo_03_llm_live.py` 同一套约定(`llm_live` marker,默认不跑,
`pytest -m llm_live` 显式触发,`DASHSCOPE_API_KEY` 未配置则跳过)——上面列的
`test_demo_04_chat_turn.py`/`test_demo_04_chat_router.py` 全部用 stub client,
只验证"代码逻辑对不对",不验证"真实模型返回的 JSON 形状我们的 Pydantic 契约接
不接得住"。1.9 新增了三处会实际改变 prompt/契约形状的 LLM 调用点,这个文件对
每一处各跑一次真实调用,验证能拿到合法结构,不是重复 `eval_nl_parse.py` 的正式
准确率评测:

- `parse_diet_text` 带 `today_context`(非空的今日对话+今日明细)真实调用一次,
  验证 `intent`/`outcome` 都是合法枚举值,且约束成立(`intent` 是
  `new_entry`/`correct_pending_item` 时 `outcome` 非空,`no_log_intent`/
  `edit_existing_entry` 时 `outcome` 为 `None` 且 `message` 非空)——intent/
  outcome 两维契约上线后第一次跟真实模型对齐,最容易在这里发现"模型返回的
  字段名/取值和 Pydantic schema 对不上"这类问题,stub client 测不出来。
- `handle_modify_correction` 用真实的"原识别项+修正文本"合成输入调一次,验证
  返回的是合法 `ItemEstimateOutcome` 或者有意义的 `failure_reason`,不是抛
  异常或返回不满足契约的结构。
- `recap_batch_status` 用一份真实的终态列表(2-3 项 confirmed/abandoned 混合)
  调一次,验证 `LlmClient.chat_json` 按 `{"summary": "..."}` 契约真实返回,或者
  在真实网络条件下也能正确触发确定性兜底文案(不留白)。

这三处都只做"结构/契约合法性"断言,不断言具体文案内容(具体语义准确率不是这个
文件的职责,那是 `eval_nl_parse.py` 数据集要做的事)。

---

## 五、前端组件实现

### `RecordTab.tsx`(状态机归属地)

```ts
type ItemUiState =
  | 'pending' | 'to_confirm' | 'to_modify' | 'to_reparse' | 'modifying'
  | 'confirmed' | 'abandoned'

interface PendingItem {
  clientItemId: string
  confirmationId: string          // 后端签发,原样携带,贯穿整个生命周期
  outcome: ItemEstimateOutcome    // 当前预览值
  uiState: ItemUiState
  writtenEntryId: number | null   // confirmed 后记录,仅展示用
  pendingModifyNote: string | null   // to_reparse 时展示的"修改:…"草稿文本
  modifyError: string | null
  writeError: string | null       // 顶部批量提交这一项失败时的提示
}
```

- 挂载时拉今日聊天记录 + 今日明细各一次,再调一次
  `GET /chat/messages/open-batch`;返回非空时弹"上次有 N 项识别结果没有处理
  完,是否继续?"对话框(见"未完成批次的恢复"一节),选继续则用返回的完整
  预览重建 `PendingItem` 并弹卡片,选放弃则调 `POST /chat/messages/recap`
  (全部标 abandoned)。
- `batchId: string | null`(当前卡片的批次 id,新建卡片时来自
  `ChatTurnResponse.batch_id`,恢复旧批次时来自 open-batch 响应);
  `modifyingItemId: string | null`;`cardBusy: boolean`(顶部批量提交/批量重新
  估算或任意一项 `modifying` 时为 true,期间顶部两个按钮和所有单项按钮禁用)。
- 顶部"确认":对所有 `to_confirm` 的项发 `POST /meal-entries`(带上这次生成的
  `now_utc`);对所有 `to_reparse` 的项发 `POST /chat/messages/modify`(状态先
  转 `modifying`)——这两类请求共用同一次点击生成的 `now_utc`。`to_confirm`
  成功→`confirmed`+记 `writtenEntryId`+append 进 `todayEntries`,失败→留在
  `to_confirm`+记 `writeError`。`to_reparse` 请求返回后统一转回 `pending`:
  成功→更新 `outcome`、`pendingModifyNote` 保留作溯源;失败→`outcome` 退回
  修改前的值、`pendingModifyNote` 替换成 `modifyError` 展示的失败原因。
- 顶部"放弃":所有 `pending`/`to_confirm`/`to_modify`/`to_reparse` 的项→
  `abandoned`(纯本地,无网络请求)。
- 每次顶部"确认"/"放弃"完成后检查:是否全部到达 `confirmed`/`abandoned`?
  是→用这次批量动作的 `now_utc` 调一次 `POST /chat/messages/recap`(带上
  `batchId`),卡片标记"已结束"——这个标记不等 recap 请求的网络结果,只要
  items 状态本地已经全部到终态就立刻解锁(解除"今日明细禁用删除"和"未确认
  放弃弹窗"的判断范围);recap 请求本身用一个一次性标记保证同一张卡片生命
  周期里只发一次,失败就放弃,不重试、不阻塞 UI。
- 今日明细的删除按钮:只要存在"未结束"的卡片(有任意项不在
  `confirmed`/`abandoned`)就禁用。

### `ConfirmationCard.tsx`

顶部"解析结果 · {餐次}"+kcal 合计(只算 confirmed/to_confirm 预估值)+"确认"+
"放弃"(禁用态受 `cardBusy` 控制)。每项渲染"确认"/"修改"互斥双态按钮 + 对应的
留痕/错误小字(`pendingModifyNote`/`modifyError`/`writeError`)。

### `ChatInputBar.tsx`

输入框在 modify 模式下发送"确认修改"是纯本地操作(把 `correction_text` 记进
对应 `PendingItem` 的 `pendingModifyNote`、状态转 `to_reparse`),不发网络
请求。

### `UnconfirmedGuardDialog.tsx`(泛化)

原本只用于"输入框直接打字但有未确认项"的二次确认,现在同一个组件(或同一套
视觉样式)也用于"是否继续上一批"的对话框,文案按场景传入。

### `TodayEntryList.tsx` + `MealEntryRow.tsx`

新增:接收 `disabled: boolean`(来自 RecordTab 的"是否存在未结束卡片"),为 true
时所有行的删除按钮渲染为禁用态。其余同前一版(分组/小计/合计/空态/删除二次确认;
顶部摄入/目标/Δ 区块,目标/Δ 占位)。

### 新增 token(取自原型/design.md 已有色值)

---

## 六、前端测试(`frontend/src/tests/demo_04_*.test.tsx`)

- `demo_04_chat_input.test.tsx`:同前一版,补"modify 模式下发送确认修改不触发
  网络请求,只本地记录 pendingModifyNote"的用例。
- `demo_04_confirmation_card.test.tsx`:确认/修改互斥双态;顶部确认同时处理
  `to_confirm` 写入和 `to_reparse` 重新估算;顶部确认只处理
  `to_confirm`/`to_reparse` 项、留下的 `pending` 不受影响;顶部放弃只影响非
  终态项;`cardBusy` 时所有按钮禁用;单项写入失败后保留 `to_confirm` + 显示
  错误,可通过再次点顶部确认重试;重新估算成功/失败后的展示文字
  (`pendingModifyNote`/`modifyError`)。
- `demo_04_unconfirmed_guard.test.tsx`:同前一版。
- `demo_04_today_entry_list.test.tsx`:分组/小计/合计/空态;存在未结束卡片时
  删除按钮禁用,卡片结束后恢复可用。
- `demo_04_record_tab_flow.test.tsx`(集成):发送→估算部分失败(失败项只出现
  在播报文字里,不出现在卡片中)+部分成功→暂存两项确认+暂存一项修改→点顶部
  确认(写入已暂存的两项,同时触发修改项重新估算)→修改项重新出现在卡片、再次
  确认→点顶部确认(写入第三项)→断言**只在全部到终态后出现一条**总结气泡(不是
  每步一条);needs_clarification 循环到 resolved 才出现卡片;全部估算失败时
  不出现卡片,只有播报气泡;刷新后 `GET /chat/messages/open-batch` 返回未
  完成批次,弹继续/放弃对话框,选继续重建卡片、选放弃调 recap 关闭。

`demo_01_app.test.tsx` 不需要改。

---

## 七、实现顺序

1. 本计划已覆盖写入 `tasks/current.md`。
2. **intent/outcome 两维契约**(见"零、intent/outcome 两维契约"):
   `diet_parse.py` 加 `intent` 字段;`nl_parse.py` 更新 prompt;更新
   `tests/backend/test_demo_03_nl_parse.py` 用例;`pytest` 跑一遍确认 1.8 相关
   测试仍全绿。
3. 重新标注 `tests/backend/eval/food_text_parse_dataset.csv`(新增
   `expected_intent` 列),重新跑一次 `backend/scripts/eval_nl_parse.py`,
   贴出新的结构合法率/两个维度准确率数字给你确认(这一步产生真实 LLM 调用
   费用)。
4. `config.py` 加 `user_timezone`/`attribution_offset_hours`;
   `services/attribution.py` + 测试(时区+偏移量两个维度的边界测试)。
5. 迁移:`meal_entry` 加 `confirmation_id` 列+唯一索引,`chat_message` 加
   `batch_id`/`kind`/`food_summary_json` 三列 + 迁移测试(只在临时 SQLite 上
   跑,不碰真实库)。
6. `schemas/chat.py`(含 `ConfirmableItem`/`ModifyCorrectionRequest`/
   `ModifyCorrectionResponse`/`RecapRequest`/`OpenBatchOut` 等)、
   `schemas/meal_entry.py`(含 `ConfirmMealEntryRequest`)。
7. `services/chat.py`、`services/meal_entry_write.py`(含幂等逻辑 +
   insert-or-select-on-conflict)+ `test_demo_04_meal_entry_idempotency.py`。
8. `services/nl_parse.py` 加 `today_context`;`services/chat_turn.py` 的
   `format_today_conversation`/`format_today_meal_entries_markdown`/
   `build_today_context` + 测试(含 1.8 回归)。
9. `services/chat_turn.py` 其余函数(`handle_new_message`/
   `handle_modify_correction`/`find_open_batch`/`recap_batch_status`)+
   测试。
10. `dependencies.py` + `main.py`(lifespan/共享 httpx.AsyncClient/路由挂载)。
11. `routers/chat.py`(含 `/modify`、`/recap`、`/open-batch`)、
    `routers/meal_entries.py`。
12. `tests/backend/conftest.py` 加 `migrated_client`。
13. `test_demo_04_chat_router.py`、`test_demo_04_meal_entries_router.py`
    (含幂等重复 POST 场景)。
14. `conda activate vibe-coding && pytest` 全绿(含 1.8 回归)贴输出;
    `ruff check backend && mypy`。
15. **`test_demo_04_llm_live.py`**(见"四、后端测试"的真实 LLM API 测试小节)+
    显式跑一次 `pytest -m llm_live`,贴输出确认三处真实调用(带 today_context
    的 parse_diet_text、handle_modify_correction、recap_batch_status)都拿到
    合法结构(这一步产生真实 LLM 调用费用)。
16. `tokens.css`/`global.css` 补样式。
17. `types/diet.ts` → `lib/chat.ts`/`lib/mealEntries.ts`。
18. 叶子组件:`ConfirmationCard.tsx`(+测试)、`MealEntryRow.tsx`(disabled
    支持)、`UnconfirmedGuardDialog.tsx`(泛化成通用二次确认对话框)。
19. 组合组件:`TodayEntryList.tsx`(+测试,disabled 联动)、`ChatInputBar.tsx`
    (+测试)、`ChatHistory.tsx`。
20. `RecordTab.tsx`(状态机 + cardBusy + 批次收尾判定 + 挂载检测未完成批次)+
    `demo_04_unconfirmed_guard.test.tsx` + `demo_04_record_tab_flow.test.tsx`。
21. `App.tsx` 接入 `RecordTab`。
22. `cd frontend && npm test` 全绿;`npm run lint`。
23. **手动浏览器冒烟测试**——本项目第一次真的往 `backend/data/dietapp.db`(或
    开发副本)写业务行:完整走一遍"发送→部分估算失败(播报说明、不进卡片)→
    暂存确认+暂存修改→顶部确认(写入+触发重新估算)→修改项重新出现、再次确认→
    顶部确认(写入)→今日明细刷新且期间删除按钮曾被禁用→顶部放弃剩余项→出现
    一条(且只有一条)总结气泡→今日明细删除"闭环,并触发一次放弃弹窗、一次
    needs_clarification 循环、一次 no_log_intent(闲聊)、一次刷新页面后的
    "是否继续上一批"提示。**按 AGENTS.md/backend.md,需要你明确同意后才执行**,
    届时确认用真实库(测完清理)还是开发副本,同时确认这一步会正式跑
    `alembic upgrade head`(含新的 confirmation_id/batch_id 等迁移)。
24. 覆盖更新 `tasks/STATUS.md`:1.8 行的描述("四态"改"intent×outcome 两维")
    和评测数字同步更新,1.9 行标记为完成状态。

---

## 八、验证方式 / Definition of Done

- `conda activate vibe-coding && pytest` 全绿(含 1.8 既有测试回归)。
- `ruff check backend && mypy` 无新增报错。
- `cd frontend && npm test` 全绿;`npm run lint` 无新增报错。
- `backend/scripts/eval_nl_parse.py` 重新跑一次,贴出 intent/outcome 两个
  维度的准确率数字(结构合法率仍需 ≥95%)。
- `pytest -m llm_live` 跑过至少一次(`test_demo_04_llm_live.py`),带
  today_context 的 `parse_diet_text`、`handle_modify_correction`、
  `recap_batch_status` 三处真实 LLM 调用都返回合法结构,贴输出。
- 手动浏览器验证端到端闭环(含部分估算失败播报、写入幂等重试、修改延后到
  批次收尾重新估算、今日明细禁用联动、一次性总结气泡、no_log_intent/
  edit_existing_entry 分支、刷新后未完成批次的继续/放弃),需你确认后执行,
  含一次真实 `alembic upgrade head`。
- 不引入 `daily_summary`/结转任务本身的代码。

---

## 已决定、供你在批注里覆盖的设计取舍

- **幂等键生命周期绑定"这一项食物",不是绑定"这一次 HTTP 请求"**:改过之后
  复用同一个 `confirmation_id`,因为修改前后逻辑上是"同一项决策",不是两个
  独立的写入意图;`confirmation_id` 和 `batch_id` 都由后端在识别出结果那一刻
  签发,前端只原样携带,不自己生成。
- **顶部批量写入用 N 次独立 POST,不是一个新的批量端点**:复用现有单项端点,
  单项失败不阻塞其它项(和 1.7 `estimate_items` 的"单项失败不拖累其他项"保持
  同一设计哲学),也不用为批量事务单独设计一套 API;同一批请求共用同一个前端
  生成的 `now_utc`,避免网络排队跨过归属日边界导致同一批被拆进两天。
- **`user_timezone` 是静态配置,不支持用户出差跨时区**:那是 §9.4 RC 范围;
  本步解决的是"服务器和用户本来就不在同一个时区"这个更基础的正确性问题,不是
  完整的多时区支持;`now_utc` 目前只是内部传参用的 UTC 时刻,不对用户暴露本地
  时间的展示层——等后面身体数据/设置类步骤做出"用户可见的本地时间"概念时,再
  考虑要不要加一个展示层转换,本步不做。
- **修改的真正重新估算推迟到顶部"确认"时批量处理,过程不产生任何对话气泡**:
  和"追问信息要问清楚才解析"是同一种"中途不打断"的思路——用户在输入框发送
  "确认修改"只是本地暂存意图,不等于要立刻打断当前节奏去问一次 AI;批次收尾
  时的总结会把这批发生的一切(包括修改是否成功)一次性讲清楚。
- **估算失败的食物从一开始就不进卡片,直接在识别播报里说明**:卡片只承载
  "用户需要对它做决定"的项;估算失败的食物没有任何值得决定的东西,留在卡片
  里除了占地方、拖慢"这批何时算处理完"的判断,没有实际作用。
- **刷新/关闭页面导致的未完成批次,靠后端签发的 batch_id/confirmation_id
  做精确恢复,不靠前端本地持久化**:识别结果的完整快照落在 `chat_message`
  这张表里(随应用本身持久化,不依赖浏览器本地存储),"这批有没有写完"是一个
  后端可以直接回答的问题(`find_open_batch`),前端只负责在挂载时问一次、
  展示结果。
