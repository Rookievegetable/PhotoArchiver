# KNOWN_ISSUES.md — PhotoArchiver 当前未解决问题列表

> **本文档记录项目当前尚未解决的问题。**
>
> 回答：**"目前有哪些问题需要 AI 注意？"**
>
> 动态维护，实时更新。问题解决后**立即删除**，不保留历史记录。
>
> Version: 1.2.1 ｜ Last Updated: 2026-07-24 ｜ Status: Live

---

## ⚠️ 本文档不是什么

| 不是 | 这些应在别处找 |
|---|---|
| 已解决的问题 | 不保留（解决后立即删除） |
| 已裁决的架构决策 / ADR | `ARCHITECTURE_DECISIONS.md` |
| 当前任务 / Step / Roadmap | `PROJECT_STATUS.md` |
| AI �阅读顺序 / 工作流程 | `AI_ONBOARDING.md` |

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

### ISSUE-001 — recognizer.extract 双检测

| 字段 | 值 |
|---|---|
| Status | Open |
| Description | `recognizer.extract` 当前对同一图片做两次检测（detect + extract 内部再 detect），可合并 halve 成本。Step 12 Worker 已接入但 detect/extract 仍分两次调用。**注**：2026-07-24 已修 recognizer 模块 docstring 假缓存声明（"extract reuses a cached detection result"），改回诚实描述——本 ISSUE 主体（双检测）仍未解决，docstring 与 ISSUE 一致不再矛盾。 |
| Impact | Medium —— 性能，每张照片 AI 处理时间翻倍 |
| Temporary Workaround | 无 |
| Planned Resolution | Step 13+ 优化：批量 detect+extract 单次 get，或缓存 detection 结果 |

### ISSUE-002 — 结构化埋点缺失（task_id/folder_id 绑定）

| 字段 | 值 |
|---|---|
| Status | Open |
| Description | 当前日志未绑定 `task_id` / `folder_id` 等结构化上下文，Step 12 Worker 已接入但未补 task_id 绑定，当前无 task_id 概念。难以追溯单批任务全链路。 |
| Impact | Medium —— 可观测性，长任务排障困难 |
| Temporary Workaround | 人工按时间窗与消息内容推断 |
| Planned Resolution | Step 13+ 引入 `logger.bind(task_id=..., folder_id=...)` |

### ISSUE-003 — FaceEmbeddingRepository.list_all 未分页

| 字段 | 值 |
|---|---|
| Status | Open |
| Description | `FaceEmbeddingRepository.list_all` 一次性返回全部 Person embedding，Person 数千时内存压力大。当前量小可接受。 |
| Impact | Low —— 性能，仅大规模数据集触发 |
| Temporary Workaround | 无 |
| Planned Resolution | Step 13+ 加分页或游标接口 |

### ISSUE-004 — SQLAlchemy/Alembic 迁移体系延后

| 字段 | 值 |
|---|---|
| Status | Mitigated |
| Description | roadmap Step 3 要求 SQLAlchemy/Alembic，实际用 sqlite3 + `PRAGMA user_version`（ADR-005）。Schema 演进手工管理，无迁移脚本与回滚。 |
| Impact | Low —— 工程风险，Schema 变更需手写升级逻辑且无回滚 |
| Temporary Workaround | `sqlite_connection.py` 内集中升级逻辑，版本号单调递增 |
| Planned Resolution | roadmap Step 3 收尾或后续阶段引入 SQLAlchemy/Alembic |

### ISSUE-006 — RecognitionResult.id 类型 UUID | None 类型未表达

| 字段 | 值 |
|---|---|
| Status | Open |
| Description | `RecognitionResult.id` 类型签名 `UUID | None`，`__post_init__` 保证非空但类型未表达。**注**：2026-07-24 核验 `domain/entities/recognition.py` 已不再含 `type: ignore` 注释（旧描述"带 `type: ignore`"已失效）——核心问题（类型未表达）仍在，仅 workaround 已移除。 |
| Impact | Low —— 类型安全，静态检查不完整 |
| Temporary Workaround | 无（原 `type: ignore` 注释已删） |
| Planned Resolution | 未来重构改 `UUID` 非 None |

---

## 已知飘带（既有代码 lint 阘带）

### ISSUE-007 — 既有文件 4 个 ruff 未用导入 + 23 个 mypy 类型错

| 字段 | 值 |
|---|---|
| Status | Open |
| Description | Step 8-10 之前文件存在 4 个 ruff 未用导入 + 23 个 mypy 类型错（2026-07-24 实测：`mypy src` 报 23 error；`ruff check src tests` 报 4 错误含 `src/ai/insightface_detector.py` 未用导入）。分布在 `unit_of_work` / `sqlite_unit_of_work` / `application_tasks` / `register_photo_service` / `qt_executor` / `main_window` / `scan_controller` / `app/services.py:188-189`（`ec1c31c` 引入）/ `app/ui_assembly.py:110` 等。非本轮引入。 |
| Impact | Low —— 质量，基线飘带 |
| Temporary Workaround | 不顺带混入 Step 任务，避免污染本轮范围 |
| Planned Resolution | 单独开一轮清理（第 2 期机制 5「lint 阘带清理轮」） |

---

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

### ISSUE-010 — Pillow 集成测试依赖环境装齐

| 字段 | 值 |
|---|---|
| Status | Mitigated |
| Description | 真实图片元数据相关集成测试依赖 Pillow；venv 未装 Pillow 时测试缺 `pytest.importorskip("PIL")` 会 FAILED（非 skipped）。既有环境问题，非代码缺陷。 |
| Impact | Low —— 测试，未装 Pillow 时报错而非跳过 |
| Temporary Workaround | 装齐 `requirements/base.txt` |
| Planned Resolution | 补 `pytest.importorskip("PIL")` 或装齐依赖 |

---

## 待裁决的规则/文档冲突（非 ADR，未落地）

> 权威审计：`.ai/Consistency-Audit-2026-07-13.md`。本节列待裁决项，裁决后或并入 `ARCHITECTURE_DECISIONS.md` R 段，或从本文删除。

### ISSUE-011 — config/ 顶层目录在 architecture-rules §17 允诺但依赖矩阵未授权

| 字段 | 值 |
|---|---|
| Status | Mitigated |
| Description | `config/` 顶层目录在 `architecture-rules.md` §17 Configuration Rules 允诺，但依赖矩阵未列。本轮（2026-07-24）SSOT 收敛已在 ARC §4 ARC-009 补录表收口：标注 `config/` 为"仅静态配置文件目录，非 Python 模块，不进 DEP §4 矩阵"。 |
| Impact | Low —— 文档一致性 |
| Temporary Workaround | 无 |
| Planned Resolution | 本轮已修，保留 Mitigated 状态待下轮复审确认 |

### ISSUE-012 — docs/architecture/overview.md §6 "尚未实现" 列表均已实现

| 字段 | 值 |
|---|---|
| Status | Mitigated |
| Description | `docs/architecture/overview.md` §6 标"尚未实现"的列表均已实现，文档漂移。本轮（2026-07-19）已刷新 §6/§7 为 Step 13 收尾状态 + PROJECT_STATUS 唯一权威指针。 |
| Impact | Low —— 文档一致性 |
| 爆炸半径 | `docs/architecture/overview.md` §6/§7（已修）；同属漂移的 `README.md` 开头段/已完成/待实现/下阶段、`docs/roadmap/phase-1-core-workflow.md`、`docs/development/getting-started.md` §11 FAQ 均已同轮刷新 |
| Temporary Workaround | 无 |
| Planned Resolution | 本轮已修，保留 Mitigated 状态待下轮复审确认；若 §6 再次漂移按 `audit-methodology.md` 复审 |

### ISSUE-013 — README.md 待实现列表未列已完成项

| 字段 | 值 |
|---|---|
| Status | Mitigated |
| Description | `README.md` 待实现列表未反映已完成项（如缩略图、AI、归档、UI），文档漂移。本轮（2026-07-19）已刷新开头段 + 已完成/待实现/下阶段段为 Step 13 收尾状态 + PROJECT_STATUS 唯一权威指针。 |
| Impact | Low —— 文档一致性 |
| 爆炸半径 | `README.md` 开头段/已完成/待实现/下阶段（已修）；同属漂移的 `docs/architecture/overview.md` §6/§7、`docs/roadmap/phase-1-core-workflow.md`、`docs/development/getting-started.md` §11 FAQ 均已同轮刷新 |
| Temporary Workaround | 无 |
| Planned Resolution | 本轮已修，保留 Mitigated 状态待下轮复审确认 |

### ISSUE-014 — 5 处规则重复承载（SSOT 缺口）

| 字段 | 值 |
|---|---|
| Status | Mitigated |
| Description | 5 处规则重复承载：业务工作流 / 技术栈 / 分层图 / 模块职责 / Review Checklist。审计 D-1~D-5。本轮（2026-07-24）SSOT 收敛已落地 7 主题归属裁决（技术栈→DEP §13、分层图+矩阵→DEP §2/§4、模块职责→ARC §4、业务工作流→roadmap §2、Review Checklist→review §22、print禁令→COD-050/051、命名/导入→coding-rules），其余承载处改指针；ai-rules.md 从 479 行降至 311 行。 |
| Impact | Low —— 维护成本，多处同步易漂移 |
| Temporary Workaround | 无（收敛已落地） |
| Planned Resolution | 本轮已修，保留 Mitigated 状态待下轮复审确认；待裁决1-4（占位/废弃物理删除/roadmap合并/编号补齐）需授权后才能进一步收敛 |

### ISSUE-015 — 11 个 .ai/ 文档为 Placeholder 占位

| 字段 | 值 |
|---|---|
| Status | Open |
| Description | `.ai/architecture/`、`.ai/business/{workflow,requirements}.md`、`.ai/context/project-status.md`、`.ai/prompts/`、`.ai/templates/` 等 11 个文档为 Placeholder 占位空文档。SSOT 不完整。 |
| Impact | Low —— AI 协作时这些文档无法提供实质指引 |
| Temporary Workaround | 本 AI Runtime Context 四文档已替代部分占位职责 |
| Planned Resolution | 随模块推进逐步填充，或统一收敛到新 AI Runtime Context（P3） |

---

## 维护规则

- **问题解决后立即整条删除**，不保留历史（历史在 Git 与审计报告中）。
- 新发现问题实时追加，ID 单调递增，不复用已删除 ID。
- 状态从 `Open` → `Mitigated`（有 workaround）→ `Resolving`（已在某 Step 推进）→ 删除。
- 仅记录当前未决，禁止记录已解决、ADR、当前任务、聊天记录。

---

> 📝 本文件由 AtomCode (GLM-5.2) 于 2026-07-18 基于真实项目状态生成。实时维护，始终保持"当前未解决问题"。

End of KNOWN_ISSUES.md
