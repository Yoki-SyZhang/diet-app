---
paths:
  - "backend/**/models/**/*.py"
  - "backend/**/schemas/**/*.py"
  - "backend/**/migrations/**/*"
  - "backend/**/*.sql"
---

# Data model rules

- 数据模型以 `docs/product/SPEC.md` §4 为真源，生命周期和事务边界以 §6 为真源。
- 这是单用户系统，业务表不得增加 `user_id`。
- 缺失营养素保持 `null`，不得用 `0` 代替未知值。
- Schema 或迁移变更必须同步验证结转、补录、备份与恢复影响；执行真实迁移前必须取得用户确认。
