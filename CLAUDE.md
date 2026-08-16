@AGENTS.md

<!-- 关键:不要 @import PRD.md / SPEC.md —— 导入会在每次启动时把整份 1600 行
     全量塞进上下文,烧光预算。它们用"路径引用"即可,让 Claude 按需读。 -->

## Claude Code 专属约定

- 任何 3 步以上或跨多文件的改动:**先进 plan mode**,产出计划我批注确认后再实现;
  一句话能说清的 diff 直接做,不必 plan。
- 改 `backend/**`(尤其结转/归属日/四级查询)时用 plan mode,先读 SPEC 对应章节再动。
- 动 `frontend/**` 前先看 `docs/design/design.md` 的设计规范(见 .claude/rules/frontend.md)。
- 分区细则见 `.claude/rules/`:backend.md / frontend.md / data-model.md 会按路径自动加载。
- 实现完一步:跑测试贴输出 → 我确认 → 覆盖更新 `tasks/STATUS.md`,不新建计划文件。
