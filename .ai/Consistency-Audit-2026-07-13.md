# PhotoArchiver 规则一致性审计报告

> ⚠️ **DEPRECATED — DO NOT READ**
>
> 本文档已废弃，仅保留作历史参考。**新 AI Session 请勿阅读本文。**
>
> **替代文档**：已裁决冲突迁入 `.ai/ARCHITECTURE_DECISIONS.md` R 段；未决冲突迁入 `.ai/KNOWN_ISSUES.md`（ISSUE-011~015）
>
> 废弃日期：2026-07-18 ｜ 废弃裁决：AI Runtime Context 体系建立（`.ai/rules/CONTEXT_HANDOFF_RULES.md`），审计内容已分流至新四文档
>
> 历史正文保留于下方，仅供追溯。

---

> Audit Date: 2026-07-13
> Auditor: AtomCode (GLM-5.2) — Senior Software Architect / Python Engineer / Technical Lead
> Scope: `.ai/rules/` vs `.ai/architecture/` vs `.ai/business/` vs `.ai/context/` vs `docs/` vs 当前代码
> Method: 逐条文本比对 + 代码事实采集（grep / import introspection）

---

## 1. 审计结论总览

| 类别 | 数量 | 严重度分布 |
|---|---|---|
| 冲突（规则 vs 代码 / 规则内部） | 7 | MAJOR ×2，MINOR ×5 |
| 重复（多文档承载同一规则） | 5 | MINOR |
| 过期（文档落后于代码） | 6 | MAJOR ×1，MINOR ×5 |
| 占位空文档（SSOT 缺口） | 11 | MAJOR ×1（批量） |
| 已裁决并修正（本轮） | 3 | — |

**总体判断**：架构骨架一致，但 SSOT 体系存在**批量占位空文档**与**规则落后于代码**两类系统性问题；此前 Onboarding 已处置 3 项（Workers/PySide6、SQLite 目录、行宽），本轮新增 7 项冲突待裁决。

---

## 2. 冲突清单（逐条）

### C-1【MAJOR】`infrastructure/repositories/` vs `infrastructure/database/` 路径分裂

| 位置 | 表述 |
|---|---|
| `architecture-rules.md` §8 ARC-008 | "Repository implementations belong in: `infrastructure/repositories/`" |
| `architecture-rules.md` §14 ARC-014 | "SQLite belongs only in: `infrastructure/database/`" |
| 当前代码 | SQLite 仓储实现位于 `infrastructure/database/`（本轮 #2 已迁移） |

**分析**：两条规则同时陈述仓储实现位置，**互相矛盾**——仓储实现即是 SQLite 代码，按 §8 应在 `repositories/`，按 §14 应在 `database/`。本轮迁移把 SQLite 仓储搬进 `database/`，使代码与 §14 对齐，但与 §8 字面冲突。
**建议**：更新 §8 为 "`infrastructure/repositories/` 用于 InMemory 及非 SQLite 仓储实现；SQLite 仓储实现遵循 §14 位于 `infrastructure/database/`"。**不自行修改，待裁决**。

### C-2【MAJOR】`pydantic` 批准状态过期

| 位置 | 表述 |
|---|---|
| `dependency-rules.md` §13 | `* pydantic (if introduced by project approval)` |
| `requirements/base.txt` | `pydantic==2.11.7`、`pydantic-settings==2.10.1` 已列入 |
| `infrastructure/config/settings.py` | 已 `from pydantic import ...` 并使用 |
| `ai-rules.md` §3 / `README.md` 技术栈 | 未列 pydantic |

**分析**：pydantic 已事实批准并投入使用，但 dependency-rules 仍标 "if introduced"，ai-rules 技术基线漏列。规则落后于代码。
**建议**：将 `pydantic`、`pydantic-settings` 提为 §13 正式批准条目（移除 "if introduced" 修饰），同步加入 `ai-rules.md` §3 Technology Baseline。**不自行修改，待裁决**。

### C-3【MINOR】`config/` 顶层目录不在依赖矩阵

| 位置 | 表述 |
|---|---|
| `architecture-rules.md` §17 ARC-017 | "Configuration loading belongs in: `config/` or `infrastructure/config/`" |
| `dependency-rules.md` §3 Approved Modules / §4 Matrix | 仅列 9 大模块（app/presentation/application/domain/infrastructure/workers/ai/plugins/common），**无 `config/`** |
| 实际代码 | 配置在 `infrastructure/config/`，顶层 `config/` 目录存在但仅放静态配置文件，非 Python 模块 |

**分析**：架构规则允诺 `config/` 为配置位，但依赖矩阵未授权该顶层模块。规则内部不一致。
**建议**：明确 `config/` 仅作静态配置文件目录（非可 import 的 Python 模块），依赖矩阵注释补一行说明；或从 §17 删除 `config/` 选项。**不自行修改，待裁决**。

### C-4【MINOR】Approved libraries 清单缺 watchdog / ONNX Runtime / Pillow / pytest-qt / SQLAlchemy / alembic

| 位置 | 表述 |
|---|---|
| `dependency-rules.md` §13 Approved libraries | 仅列 PySide6 / InsightFace / OpenCV / pandas / openpyxl / loguru / pydantic(conditional) |
| `requirements/base.txt` | 已含 `watchdog==6.0.0`、`SQLAlchemy==2.0.43`、`alembic==1.16.4`、`Pillow==11.3.0` |
| `requirements/dev.txt` | 已含 `pytest-qt==4.5.0` |
| `README.md` 技术栈 | 已列 Pillow、watchdog、ONNX Runtime、pytest-qt、SQLAlchemy、alembic |
| `ai-rules.md` §3 Technology Baseline | 未列上述 6 项 |

**分析**：6 项已在 requirements 与 README 批准，但未进 dependency-rules §13 与 ai-rules §3 的权威清单。规则落后于现实。
**建议**：将 6 项补入 §13 与 §3（Pillow 归 Infrastructure 图片层，watchdog归 Infrastructure filesystem，SQLAlchemy/alembic 归 Infrastructure database，pytest-qt 归 dev-only，ONNX Runtime 归 AI 模型运行时）。**不自行修改，待裁决**。

### C-5【MINOR】`common/logging/` 与 `infrastructure/logging/` 双重位置表述

| 位置 | 表述 |
|---|---|
| `architecture-rules.md` §18 | "Logging belongs in: `common/logging/` or `infrastructure/logging/`" |
| `dependency-rules.md` §4 Matrix | `common` → "Standard Library only"；`infrastructure` → "domain, common" |
| 实际代码 | 日志在 `infrastructure/logging/`，`common/logging/` 未创建 |
| `dependency-rules.md` DEP-071 | "Common MUST NOT depend on any project module"——隐含 common 仅标准库，loguru 是第三方库 |

**分析**：§18 允诺 `common/logging/` 为合法位置，但 DEP-071 禁止 common 导入 loguru（第三方）——**规则内部张力**。且 `common/` 当前为空骨架。
**建议**：从 §18 删除 `common/logging/` 选项，统一为 `infrastructure/logging/`（loguru 属第三方，归 Infrastructure）。**不自行修改，待裁决**。

### C-6【MINOR】`docs/architecture/overview.md` "尚未实现" 列表严重过期

| 位置 | 表述 |
|---|---|
| `docs/architecture/overview.md` §6 当前尚未实现 | 列 "Domain 核心模型 / Repository Interface / Application Use Case / SQLite 仓储 / 文件扫描 / 元数据读取" 等**均未实现** |
| 实际代码 | 上述全部**已实现**（Onboarding 核对） |

**分析**：该文档严重落后于代码，会误导开发者与 AI。Onboarding 已识别，裁决 #5 暂缓至 Phase 1 收尾——此处重录以备追踪。
**建议**：Phase 1 收尾统一更新（按裁决 #5）。**不自行修改**。

### C-7【MINOR】`roadmap.md` Step 3 与当前 Schema 管理方式不一致

| 位置 | 表述 |
|---|---|
| `roadmap.md` Step 3 | 要求 "SQLAlchemy Engine/Session 管理 + Alembic 迁移 + ORM models" |
| 实际代码 | `sqlite3` 直连 + `PRAGMA user_version = 1` 版本管理，**未引入 SQLAlchemy/Alembic** |

**分析**：roadmap 是"未来交付清单"，非强制现状——形式上不算冲突，但 roadmap 未标注 Step 3 为"部分完成/延后"，易误读。
**建议**：在 roadmap.md Step 3 加注 "当前以 sqlite3 + PRAGMA user_version 临时实现，SQLAlchemy/Alembic 推迟到 Phase 2"。**不自行修改，待裁决**。

---

## 3. 重复清单（多文档承载同一规则）

> `.ai/README.md` §15 已声明 "These responsibilities MUST remain separate"，但实际仍存在重复。

| # | 重复内容 | 出现位置 | 建议 |
|---|---|---|---|
| D-1 | 业务工作流（Import→Scan→Detect→Recognize→Match→Archive→Export） | `PROJECT_CONTEXT.md` §Business Workflow、`ai-rules.md` §4、`architecture-rules.md` §21、`ui-rules.md` §27、`worker-rules.md` §4、`README.md` 标准业务流程、`docs/architecture/overview.md` §5 | 共 7 处重述。**保留 `ai-rules.md` §4 为 SSOT**，其余改为交叉引用 |
| D-2 | 技术栈清单 | `ai-rules.md` §3、`dependency-rules.md` §13、`README.md` 技术栈、`.ai/README.md` §2、各 Placeholder 文档头部 | 共 5 处。**保留 `dependency-rules.md` §13 为 SSOT**，其余交叉引用 |
| D-3 | 分层架构图（Presentation→Application→Domain←Infrastructure） | `START_HERE.md`、`PROJECT_CONTEXT.md`、`architecture-rules.md` §2、`dependency-rules.md` §2、`README.md`、`docs/architecture/overview.md` §2、`docs/deployment/project-structure.md` §6 | 共 7 处。**保留 `architecture-rules.md` §2 为 SSOT** |
| D-4 | 模块职责清单（app/presentation/application/domain/...） | `PROJECT_CONTEXT.md` §Module Responsibilities、`architecture-rules.md` §3、`docs/deployment/project-structure.md` §5、`README.md` 项目结构 | 共 4 处。**保留 `architecture-rules.md` §3 为 SSOT** |
| D-5 | 审查清单（Review Checklist） | `ai-rules.md` §21、`coding-rules.md` §15、`architecture-rules.md` §23、`dependency-rules.md` §19、`worker-rules.md` §27、`ui-rules.md` §28、`review-rules.md` §22、`git-rules.md` §19 | 共 8 处，各载大同小异的 checklist。**保留 `review-rules.md` §22 为总 SSOT**，各专项规则仅保留该专项条目 |

**处置原则**：按 `.ai/rules/README.md` §15 "responsibilities MUST remain separate"，每条规则只在一个权威位置落正文，其余位置改为 "See §X of `<authoritative-file>`" 交叉引用。**本轮仅记录，不动文件，待裁决**。

---

## 4. 过期清单（文档落后于代码）

| # | 位置 | 过期内容 | 实际现状 | 严重度 |
|---|---|---|---|---|
| E-1 | `docs/architecture/overview.md` §6 | 列 Domain/Repository/UseCase/SQLite/扫描/元数据"尚未实现" | 全部已实现 | MAJOR（同 C-6） |
| E-2 | `README.md` 待实现列表 | 未列 "Excel 人员导入 / Worker 基类" 已完成项 | roadmap 已标完成 | MINOR |
| E-3 | `dependency-rules.md` §13 | pydantic 标 "if introduced" | 已投入使用 | MINOR（同 C-2） |
| E-4 | `ai-rules.md` §3 | 技术基线漏 pydantic / Pillow / watchdog / SQLAlchemy / alembic / pytest-qt / ONNX | 均已在 requirements | MINOR（同 C-4） |
| E-5 | `.ai/architecture/*.md`、`.ai/business/{workflow,requirements}.md`、`.ai/context/project-status.md`、`.ai/prompts/*.md`、`.ai/templates/module-template.md` | 11 个文件均为 "(Placeholder for complete handbook...)" | SSOT 严重不完整 | MAJOR（批量） |
| E-6 | `architecture-rules.md` §8 | "Repository implementations belong in `infrastructure/repositories/`" | SQLite 仓储已迁至 `infrastructure/database/` | MINOR（同 C-1） |

---

## 5. 已裁决并修正（本轮 Onboarding）

| # | 内容 | 裁决 | 状态 |
|---|---|---|---|
| R-1 | Workers 导入 PySide6.QtCore | 更新 DEP-040 + WRK-002 | ✅ 已执行并验证 |
| R-2 | SQLite 目录归属 | 迁移至 `infrastructure/database/` | ✅ 已执行并验证 |
| R-3 | COD-005 行宽 88 vs pyproject 100 | 统一为 100 | ✅ 已执行并验证 |

### 5.1 Phase 2 Step 11 裁决落代码（2026-07-18）

| # | 裁决内容 | 落地 |
|---|---|---|
| S11-1 | `AppSettings.archive_root` 独立字段（不复用 `output_root`） | ✅ settings 加 `archive_root: Path \| None` + `archive_conflict_strategy: str`（默认 skip），`.env.example` 加 `ARCHIVE_ROOT=` / `ARCHIVE_CONFLICT_STRATEGY=skip` |
| S11-2 | `Archive` 不解析 EXIF——新增 `Photo.captured_at` / `PhotoMetadata.captured_at` 领域字段，由导入阶段 PillowPhotoMetadataReader 统一填充（EXIF DateTimeOriginal → mtime 链式降级），Archive 只消费领域数据 | ✅ Domain 加字段，PillowPhotoMetadataReader 加 EXIF 读取（tag id 36868），Schema `photos` 加 `captured_at TEXT` 列（PRAGMA v3 → v4） |
| S11-3 | 拆 `ArchivePlanner` → `ArchivePlan` → `ArchiveExecutor`，CLI/UI/测试共用同一套归档计划；`--dry-run` 落 DRY_RUN 状态 + ArchiveRecord 落库可预审 | ✅ Application 层三段拆分 + DTO 闭环（ArchivePlanItem/ArchivePlan/ArchiveOutcome/ArchiveResult）+ Executor 落 ArchiveRecord + CLI `archive --dry-run` 旗 |

**新增 Domain 公开 API**：`ArchivePath`（值对象）、`ArchiveRecord` + `ArchiveStatus`（实体）、`ArchiveRecordRepository`（仓储 Protocol）、`RecognitionRepository.list_approved_by_person`（Protocol 扩展）。
**Schema 改动**：PRAGMA `user_version` v3 → v4，`photos.captured_at TEXT` 列 + `archive_records` 表（6 列 + 2 索引）。

---

## 6. 待裁决事项

请逐条裁决以下 7 项（C-1 ~ C-7）；D-1~D-5 与 E-1~E-6 的处置依你整体偏好（是否本轮启动"SSOT 收敛"或推迟到 Phase 1 收尾）：

1. **C-1**：`architecture-rules.md` §8 vs §14 仓储位置矛盾——更新 §8 加 SQLite 例外条款？
2. **C-2**：`pydantic`/`pydantic-settings` 升为正式批准库并补入 `ai-rules.md` §3？
3. **C-3**：`config/` 顶层目录在依赖矩阵中的地位——补注释还是删 §17 选项？
4. **C-4**：6 项遗漏库（watchdog/ONNX/Pillow/pytest-qt/SQLAlchemy/alembic）补入 §13 与 §3？
5. **C-5**：`common/logging/` 选项从 §18 删除，统一为 `infrastructure/logging/`？
6. **C-6 / E-1 / E-2**：是否提前至本轮更新 `docs/architecture/overview.md` 与 `README.md`（违反裁决 #5 "Phase 1 收尾"）？
7. **C-7**：`roadmap.md` Step 3 加注 SQLAlchemy/Alembic 延后说明？
8. **D-1~D-5**：是否本轮启动 SSOT 收敛（每条规则只在一处落正文，其余改交叉引用）？
9. **E-5**：11 个 Placeholder 文档——本轮填充还是推迟？

---

## 7. 统一规则索引（Single Source of Truth）

> 以下为本次审计建立的权威索引。**每条规则仅此一处为正文 SSOT**，其他文档应交叉引用本表或对应权威文件。

### 7.1 规则文件 SSOT 映射

| 规则类别 | 权威文件 | 规则编号区 | 状态 |
|---|---|---|---|
| AI 行为 | `.ai/rules/ai-rules.md` | AI-001 ~ AI-023 | Stable 1.0.0 |
| 编码标准 | `.ai/rules/coding-rules.md` | COD-001 ~ COD-123 | Stable 1.0.1 ✅本轮 |
| 架构约束 | `.ai/rules/architecture-rules.md` | ARC-001 ~ ARC-024 | Stable 1.0.0 |
| 依赖规则 | `.ai/rules/dependency-rules.md` | DEP-001 ~ DEP-071 | Stable 1.0.1 ✅本轮 |
| UI 规则 | `.ai/rules/ui-rules.md` | UI-001 ~ UI-029 | Stable 1.0.0 |
| Worker 规则 | `.ai/rules/worker-rules.md` | WRK-001 ~ WRK-028 | Stable 1.0.1 ✅本轮 |
| Git 规则 | `.ai/rules/git-rules.md` | GIT-001 ~ GIT-025 | Stable 1.0.0 |
| 审查规则 | `.ai/rules/review-rules.md` | REV-001 ~ REV-026 | Stable 1.0.0 |
| 规则元规则 | `.ai/rules/README.md` | — | Stable 1.0.0 |

### 7.2 主题 SSOT 映射

| 主题 | 权威位置 | 备注 |
|---|---|---|
| 业务工作流 | `.ai/rules/ai-rules.md` §4 | 其余 6 处应交叉引用（D-1） |
| 技术栈清单 | `.ai/rules/dependency-rules.md` §13 | 其余 4 处应交叉引用（D-2） |
| 分层架构图 | `.ai/rules/architecture-rules.md` §2 | 其余 6 处应交叉引用（D-3） |
| 模块职责 | `.ai/rules/architecture-rules.md` §3 | 其余 3 处应交叉引用（D-4） |
| Review Checklist 总表 | `.ai/rules/review-rules.md` §22 | 各专项规则仅保留专项条目（D-5） |
| 项目当前进度 | `docs/roadmap/phase-1-core-workflow.md` | README §当前开发进度应交叉引用 |
| 配置项详解 | `docs/development/configuration.md` | README §配置应交叉引用 |
| 目录结构详解 | `docs/deployment/project-structure.md` | README §项目结构应交叉引用 |

### 7.3 代码模块 SSOT 映射

| 模块 | 权威接口位置 | 实现位置 | 规则约束 |
|---|---|---|---|
| Domain entities | `domain/entities/__init__.py` | 同目录 | ARC-003、DEP-020~023 |
| Domain value objects | `domain/value_objects/__init__.py` | 同目录 | ARC-003、DEP-022 |
| Domain repository 接口 | `domain/repositories/__init__.py` | 同目录 | ARC-008、DEP-013、DEP-023 |
| Domain services | `domain/services/` | **未创建（pending）** | ARC-009 §9 |
| Application commands/dtos/ports/use_cases/services | `application/__init__.py` | 同目录子包 | ARC-002、DEP-010~013 |
| Infrastructure config | `infrastructure/config/settings.py` | 同目录 | ARC-017、DEP-030~033 |
| Infrastructure logging | `infrastructure/logging/configuration.py` | 同目录 | ARC-018（待删 common/logging 选项，C-5） |
| Infrastructure filesystem | `infrastructure/filesystem/` | 同目录 | ARC-015 |
| Infrastructure image | `infrastructure/image/` | **未创建（pending）** | ARC-016 |
| Infrastructure database | `infrastructure/database/` | 同目录（✅本轮迁移） | ARC-014、DEP-012 |
| Infrastructure repositories | `infrastructure/repositories/` | 同目录（InMemory only） | ARC-008（待澄清与 §14 关系，C-1） |
| Infrastructure services | `infrastructure/services/` | **未创建（pending）** | ARC-009 §9 |
| Infrastructure exporters | `infrastructure/exporters/` | **未创建（pending）** | roadmap Step 14 |
| Workers | `workers/__init__.py` | 同目录 | ARC-005、DEP-040~042、WRK-001~028 |
| AI | `ai/__init__.py` | 仅占位 | ARC-006、DEP-050~052 |
| Presentation views | `presentation/views/main_window.py` | 同目录 | ARC-011、UI-001~002 |
| Presentation controllers | `presentation/controllers/` | **未创建（pending）** | ARC-010 §10、UI-001 §8 |
| Presentation widgets | `presentation/widgets/` | **未创建（pending）** | UI-001 §7 |
| Common | `common/__init__.py` | 仅占位 | ARC-008、DEP-070~071 |
| Plugins | `plugins/__init__.py` | 仅占位 | ARC-007、DEP-060~062 |

### 7.4 依赖矩阵 SSOT（含本轮修正）

| Module | May Depend On | Source |
|---|---|---|
| app | presentation, application, common | DEP-040 matrix |
| presentation | application, common | DEP-001 |
| application | domain, common | DEP-010 |
| domain | common（仅标准库，DEP-071） | DEP-020~023 |
| infrastructure | domain, common | DEP-030~033 |
| workers | application, common, **PySide6.QtCore (threading only)** ✅本轮 | DEP-040 + R-1 |
| ai | infrastructure, domain, common | DEP-050 |
| plugins | application, common | DEP-060 |
| common | Standard Library only | DEP-071 |

### 7.5 技术栈 SSOT（含本轮修正）

| 技术 | 批准状态 | Source |
|---|---|---|
| Python 3.11 | ✅ Approved | ai-rules §3、pyproject.toml |
| PySide6 | ✅ Approved | ai-rules §3、dependency §13 |
| SQLite | ✅ Approved | ai-rules §3、dependency §13 |
| OpenCV | ✅ Approved | ai-rules §3、dependency §13 |
| InsightFace | ✅ Approved | ai-rules §3、dependency §13 |
| pandas | ✅ Approved | ai-rules §3、dependency §13 |
| openpyxl | ✅ Approved | ai-rules §3、dependency §13 |
| Loguru | ✅ Approved | ai-rules §3、dependency §13 |
| pytest | ✅ Approved | ai-rules §3、dependency §13 |
| Ruff | ✅ Approved | ai-rules §3 |
| MyPy | ✅ Approved | ai-rules §3 |
| pathlib | ✅ Approved | ai-rules §3 |
| pydantic / pydantic-settings | ⚠️ Conditional（待 C-2 升为正式） | dependency §13 |
| Pillow | ⚠️ Missing in §13（待 C-4 补） | requirements/base.txt |
| SQLAlchemy / alembic | ⚠️ Missing in §13（待 C-4 补） | requirements/base.txt |
| watchdog | ⚠️ Missing in §13（待 C-4 补） | requirements/base.txt |
| pytest-qt | ⚠️ Missing in §13（待 C-4 补，dev-only） | requirements/dev.txt |
| ONNX Runtime | ⚠️ Missing in §13（待 C-4 补，AI runtime） | README.md |

### 7.6 审查清单 SSOT

| 审查类别 | 权威位置 |
|---|---|
| 总表 | `review-rules.md` §22 |
| 架构专项 | `architecture-rules.md` §23 |
| 依赖专项 | `dependency-rules.md` §19 |
| 编码专项 | `coding-rules.md` §15 |
| UI 专项 | `ui-rules.md` §28 |
| Worker 专项 | `worker-rules.md` §27 |
| Git 专项 | `git-rules.md` §19 |
| AI 专项 | `ai-rules.md` §21 |

---

## 8. 审计方法论

- **证据采集**：`read_file` 读取 9 个 rules + 4 个 docs + `.ai/architecture|business|context|prompts|templates` 全部；`grep` 跑 12 类模式；`python -c` introspection 取 5 个包的 `__all__`；`bash` 查 git status / compileall / pytest。
- **比对维度**：(1) 规则内部一致性 (2) 规则 vs 代码 (3) 规则 vs docs (4) 重复承载 (5) 占位空文档。
- **未触文件**：本轮纯审计，未修改任何源码或规则文件（R-1/R-2/R-3 为此前 Onboarding 已执行并验证的独立裁决）。
- **验证手段**：报告内每条冲突均附 ≥2 个证据位置与"实际现状"字段，可独立复核。

---

## 9. 建议处置优先级

| 优先级 | 事项 | 理由 |
|---|---|---|
| P0（本轮） | C-1、C-2、C-4、C-5 | 规则落后于代码/规则内部矛盾，每次开发都会被误引 |
| P1（Phase 1 收尾） | C-6/E-1/E-2、C-7 | 与裁决 #5 对齐，统一文档校准 |
| P2（可延后） | D-1~D-5 SSOT 收敛 | 工作量大但不影响正确性，需整体规划 |
| P3（按模块推进时） | E-5 Placeholder 填充 | 随各模块实现逐步补内容，避免空写 |

---

End of Audit Report.
