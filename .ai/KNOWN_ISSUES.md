# KNOWN_ISSUES.md — PhotoArchiver 当前未解决问题列表

> **本文档记录项目当前尚未解决的问题。**
>
> 回答：**"目前有哪些问题需要 AI 注意？"**
>
> 动态维护，实时更新。问题解决后**立即删除**，不保留历史记录。
>
> Version: 1.6.0 ｜ Last Updated: 2026-08-26 ｜ Status: Live

---

## ⚠️ 本文档不是什么

| 不是 | 这些应在别处找 |
|---|---|
| 已解决的问题 | 不保留（解决后立即删除） |
| 已裁决的架构决策 / ADR | `ARCHITECTURE_DECISIONS.md` |
| 当前任务 / Step / Roadmap | `PROJECT_STATUS.md` |
| AI 阅读顺序 / 工作流程 | `AI_ONBOARDING.md` |

---

## Issue 格式约定

每个 Issue 至少包含：

| 字段 | 说明 |
|---|---|
| ID | `ISSUE-XXX`，单调递增；问题解决后整条删除（ID 不复用） |
| Description | 问题简述 |
| Status | Open / Mitigated（已有 workaround）/ Resolving（已在某 Step 推进） |
| Impact | 影响范围与严重度（High/Medium/Low） |
| Temporary Workaround | 当前临时规避方式（若有） |
| Planned Resolution | 计划何时/何 Step 解决 |

---

## 未决问题

### ISSUE-018

| 字段 | 值 |
|---|---|
| ID | ISSUE-018 |
| Description | 打包安装态（`pip install` wheel/sdist）下应用不可运行：`alembic.ini` 与 `alembic/versions/` 不随包分发，且 `alembic_runner._ALEMBIC_CFG_PATH` 按仓库布局五层 parent 解析，安装态指向不存在位置 → bootstrap 迁移步骤必失败。受影响范围：Release v1.0.0 资产及一切 pip 安装路径；**仓库 clone 布局运行不受影响**（user-guide 已引导源码方式）。附带发现：face_detection 集成测试 `_ROOT` 错层（parents[2]）致 AI 用例从未真实执行的问题已由同轮提交修复闭环（ISSUE-017，不保留条目）。 |
| Status | Open |
| Impact | Medium——影响分发预期（Release 页挂载 wheel 可能误导安装）；不影响源码运行主路径与 CI 正确性 |
| Temporary Workaround | 按 `docs/user-guide/installation.md` 以源码方式运行；Release 页描述标注待 owner 添加 |
| Planned Resolution | v1.0.1 打包策略小 ADR：alembic 资产纳入 package_data + 迁移路径包相对回退；或经裁决明示维持「源码运行定位」并从 Release 摘除二进制产物 |

## 平台与第三方限制

_当前无未决平台与第三方限制条目。_

## 维护规则

- **问题解决后必须同提交整条删除**，不保留历史（历史在 Git 与审计报告中）。
- 新发现问题实时追加，ID 单调递增，不复用已删除 ID。
- 状态从 `Open` → `Mitigated`（有 workaround）→ `Resolving`（已在某 Step 推进）→ 删除。

---

> 📝 本文件由 AtomCode (GLM-5.2) 于 2026-07-18 基于真实项目状态生成。实时维护，始终保持"当前未解决问题"。

End of KNOWN_ISSUES.md
