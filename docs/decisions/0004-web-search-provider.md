# 0004 — 网络搜索 API 供应商选型

**状态**：已接受
**日期**：2026-08-17
**关联**：SPEC §7.9（第④级拆解机制）、[0001](0001-llm-provider.md)（模型路由）、[0002](0002-composed-dish-fallback.md)（第④级兜底策略，定义了 `web_search` 作为第④级三个工具之一）

## 背景

ADR 0002 把第④级拆解机制定为"LLM 拿到 `query_food_base_cn`/`query_usda`/`web_search` 三个工具，按需调用"，但 `web_search` 具体接哪家服务一直是占位项（`backend/.env.example` 里 `WEB_SEARCH_API_KEY` 只有注释、无实际选型）。这次专门核查可用选项。

## 调研发现

### 1. Bing Search API 已彻底停售，不再是选项

微软已于 **2025-08-11** 完全停售 Bing Search APIs；新用户申请入口早在 2025 年 2 月就已关闭，无法再新开 Key。官方推荐的替代方案 Grounding with Bing Search（走 Azure AI Agent）成本比原 API 高 40%–483%，且产品形态是"AI Agent 服务"而非单纯 SERP API。这条路线直接排除。

### 2. 阿里云百炼自带 `enable_search`：架构不吻合，非独立工具

DashScope 支持在请求里设置 `enable_search: true` 开启联网搜索，同账号同 Key，不用新开供应商。但核查后发现两个问题：

- **不是可显式调用的独立工具，而是模型全局开关**：默认由模型自行判断要不要搜索，搜索结果被模型直接揉进最终文本回答，后端拿不到干净的"标题/摘要/URL"结构化数据单独处理。这和 SPEC §7.9/ADR 0002 定的架构——三个工具平级、由 LLM 按需显式调用、每次调用结果单独可观测——不吻合。较新的 Responses API 虽然支持把搜索列进工具列表（`{"type": "web_search"}`），但与我们自己的 `query_food_base_cn`/`query_usda` 工具混用的行为边界文档未详细说明。
- **双重计费**：搜索到的网页内容会拼进 prompt，按标准 token 单价计入输入费用；另外还按调用次数收"工具使用费"（文档未列出具体单价）。
- **数据保留政策未提及**：官方文档对 `enable_search` 功能本身的数据保留/训练政策没有单独说明，与 ADR 0001 对基础文本/视觉调用的核实力度不对等。

### 3. 博查（Bocha）Web Search API：独立第三方，架构和合规都对得上

- **公司背景**：杭州博查搜索科技，完成过《生成式 AI 服务备案》（国内生成式 AI 服务的强制性备案），是 DeepSeek 的官方搜索引擎，腾讯/字节/阿里等大厂也在推荐使用。
- **返回格式**：标准 REST API（`POST https://api.bochaai.com/v1/web-search`），返回结构化的 `name`/`snippet`/`url`/`summary` 字段，可以原样喂给 LLM 作为工具调用结果，和 `query_food_base_cn`/`query_usda` 是同一种"后端发起请求、结果交给 LLM 消化"的调用模式，不破坏现有架构。
- **中文支持**：官方示例和产品定位都是中文自然语言搜索优化，非通用境外 SERP API 的中文兼容。
- **隐私**：提供官方隐私政策页面（open.bochaai.com/privacy-policy）和"无痕模式"（24 小时自动清档）。
- **价格**：¥0.036/次，官方对标 Bing Search API（约 15 美元/千次，约合 ¥0.1+/次），价格约为其 1/3；对本项目"仅第④级单项兜底/校准"这种低频场景，成本可忽略。

## 决策

采用 **博查（Bocha）Web Search API** 作为 SPEC §7.9 第④级的 `web_search` 工具：

- 独立 REST 调用，返回结构化结果交给 `qwen-plus`（走 §7.9 定义的工具调用流程），不采用百炼自带的 `enable_search`。
- 接入时开启博查的"无痕模式"，对齐 SPEC §10 对供应商数据保留政策的要求。
- 排除 Bing（已停售）；不考虑海外通用 SERP API（Serper/Tavily/Google Custom Search 等）——沿用 ADR 0001 已定的"中文/国产优先，海外供应商不在候选范围"边界，这次未展开逐一测试。

## 后果

- `backend/.env.example` 需要把 `WEB_SEARCH_API_KEY` 的注释从"供应商还未选定"改为指向博查；`backend/.env` 需要去 [open.bochaai.com](https://open.bochaai.com/) 注册账号获取真实 Key（我这边权限拒绝直接改 `.env*` 文件，需要你自己操作）。
- **本决策基于官方文档调研，尚未做真实 API 调用验证**——不同于 ADR 0001/0002 那种"文档信息 + 实测双重确认"的验证力度，原因是网络搜索在本项目里只是第④级的最后兜底/校准工具、调用频率低，值不值得在拿到真实 Key 之前先做实测存疑。**建议**：拿到 Key 后先补一次真实调用验证（结构化返回是否符合预期、中文查询效果、无痕模式开关是否生效），再正式接入后端适配层。
- 后端供应商无关适配层（ADR 0001 已定的设计原则）里需要新增一个 `web_search` 适配器，和 USDA/百炼适配器同级维护。
