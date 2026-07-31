# KNOWN_ISSUES.md — PhotoArchiver 当前未解决问题列表

> **本文档记录项目当前尚未解决的问题。**
>
> 回答：**"目前有哪些问题需要 AI 注意？"**
>
> 动态维护，实时更新。问题解决后**立即删除**，不保留历史记录。
>
> Version: 1.3.0 ｜ Last Updated: 2026-07-26 ｜ Status: Live

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

## 技术债（Technical Debt）

### ISSUE-003 — FaceEmbeddingRepository.list_all 未分页

| 字段 | 值 |
|---|---|
| Status | Open |
| Description | `FaceEmbeddingRepository.list_all` 一次性返回全部 Person embedding，Person 数千时内存压力大。当前量小可接受。 |
| Impact | Low —— 性能，仅大规模数据集触发 |
| Temporary Workaround | 无 |
| Planned Resolution | Step 13+ 加分页或游标接口 |

## 平台与第三方限制

### ISSUE-008 — buffalo_l 模型包未下载，集成测试 8 skip

| 字段 | 值 |
|---|---|
| Status | Mitigated |
| Description | `buffalo_l` 模型包未下载（ADR-012 禁止自动下载），集成测试 8 条 skip 全因缺模型。CI 需预跑 `python scripts/download_models.py`。 |
| Impact | Low —— 测试覆盖，AI 闭环未在 CI 验证 |
| Temporary Workaround | 本地或 CI 预跑 download_models.py |
| Planned Resolution | CI 流水线补模型下载步骤；或加容器化 runner |

### ISSUE-009 — PySide6 / pytest-qt 阘带导致 UI 集成测试 skip

| 字段 | 值 |
|---|---|
| Status | Mitigated |
| Description | 部分集成测试在缺 PySide6 或 pytest-qt 环境 时 skip。venv 未装齐时 UI smoke test 跑不起来。 |
| Impact | Low —— 测试覆盖，UI 集成未在精简环境验证 |
| Temporary Workaround | 安装 `requirements/dev.txt` 全套 |
| Planned Resolution | 文档明确 dev 环境必装项；CI 装齐 |

## 维护规则

## 维护规则

- **问题解决后必须同提交整条删除**，不保留历史（历史在 Git 与审计报告中）。
- 新发现问题实时追加，ID 单调递增，不复用已删除 ID。
- 状态从 `Open` → `Mitigated`（有 workaround）→ `Resolving`（已在某 Step 推进）→ 删除。

---

> 📝 本文件由 AtomCode (GLM-5.2) 于 2026-07-18 基于真实项目状态生成。实时维护，始终保持"当前未解决问题"。

End of KNOWN_ISSUES.md
