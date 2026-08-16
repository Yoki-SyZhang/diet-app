---
paths:
  - "frontend/**/*.{ts,tsx,css,html,json}"
---

# Frontend rules

- 修改 UI 前先读取 `docs/design/design.md` 和 PRD 对应功能范围。
- 手机竖屏 PWA 是唯一正式布局；电脑浏览器复用同一组件结构，不增加宽屏专属页面。
- 前端不直接访问 SQLite，不持有后端 API Key，不重复实现后端营养和结转规则。
- 涉及写入的交互必须呈现明确的成功、失败或待确认状态，不能伪成功。
