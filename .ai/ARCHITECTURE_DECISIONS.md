# ARCHITECTURE_DECISIONS.md — PhotoArchiver 架构决策记录（ADR Register）

> **本文档是已确认架构决策的唯一寄存器（Architecture Decision Register）。**
>
> 回答：**"哪些架构决策已经确定，AI 不得重新设计？"**
>
> 这是整个 AI Runtime Context 中最重要的稳定文档之一。长期保留，不会因版本变化删除。
>
> Version: 1.0.2 ｜ Status: Stable ｜ Last Updated: 2026-07-26

---

## ⚠️ 本文档不是什么

| 不是 | 这些应在别处找 |
|---|---|
| 当前 Bug / TODO / 临时讨论 / 未确定方案 / AI 建议 | `KNOWN_ISSUES.md` |
| 当前任务 / Step / Roadmap 详细内容 | `PROJECT_STATUS.md` |
| AI 阅读顺序 / 工作流程 | `AI_ONBOARDING.md` |

**只有已经确认的决策。** 禁止记录未确定方案或 AI 建议。

---

## ADR 格式约定

每个 ADR 至少包含：

| 字段 | 说明 |
|---|---|
| 编号 | `ADR-XXX`，单调递增，不复用 |
| 标题 | 一句话决策主题 |
| 状态 | Proposed / Accepted / Superseded / Deprecated |
| 决策 | 已确认的决策正文 |
| 理由 | 为何如此裁决 |
| 影响范围 | 涉及模块/层/接口 |

---

## Phase 1 架构决策

### ADR-001 — 采用 DDD + Clean Architecture + 分层架构

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | 项目采用 Domain-Driven Design、Clean Architecture、严格分层、依赖倒置、Protocol First。分层为 `presentation/` → `application/` → `domain/` ← `infrastructure/`，外加 `workers/`、`ai/`、`plugins/`、`common/`。 |
| 理由 | 长期可维护的企业级桌面应用需要架构中心化于 Domain，依赖向内，避免框架耦合。 |
| 影响范围 | 全项目，权威规则见 `.ai/rules/architecture-rules.md` |

### ADR-002 — 依赖方向不可逆

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | `Presentation → Application → Domain ← Infrastructure`；`Workers → Application`；`AI → Infrastructure, Domain`；`Plugins → Application`；`Common → Standard Library only`。禁止跨层 shortcut。 |
| 理由 | 防止 UI 直接耦合技术细节，保证 Domain 纯净与可测。 |
| 影响范围 | 所有 import，权威矩阵见 `.ai/rules/dependency-rules.md` |

### ADR-003 — Domain 层零框架依赖

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | `domain/` 禁止导入 PySide6、OpenCV、InsightFace、sqlite3、pandas、SQLAlchemy、numpy 等任何框架。Domain 仅含 Entity/ValueObject/Repository Protocol/Exception。 |
| 理由 | Domain 是架构中心，必须可在无任何第三方环境下单测。 |
| 影响范围 | `src/photo_archiver/domain/` |

### ADR-004 — SQLite 仅在 infrastructure/database/

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | 所有 sqlite3/SQLAlchemy 代码只能出现在 `infrastructure/database/`，仓储实现走 `infrastructure/database/sqlite_*_repository.py`。 |
| 理由 | 集中技术适配，避免 SQL 泄漏到 Application/Domain。 |
| 影响范围 | `infrastructure/database/`（`architecture-rules.md` §14 Database Rules） |

### ADR-005 — SQLAlchemy/Alembic 延后，当前用 sqlite3 + PRAGMA user_version（已废弃）

| 字段 | 值 |
|---|---|
| 状态 | **Superseded**（被 ADR-024 新版取代：Alembic 迁移体系，2026-07-25 落地） |
| 决策 | Step 3 不引入 SQLAlchemy/Alembic，改用 sqlite3 + `PRAGMA user_version` 管理 Schema 版本。SQLAlchemy/Alembic 迁移体系推迟到 roadmap Step 3 收尾或后续阶段。 |
| 理由 | 当前 Schema 简单，PRAGMA 版本号足够；避免过早引入迁移体系增加维护成本。 |
| 影响范围 | `infrastructure/database/sqlite_connection.py`；审计记录 C-7 |

### ADR-006 — Protocol First：仓储与端口用 typing.Protocol 定义

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | 所有仓储与端口接口用 Python `typing.Protocol` 在 `domain/repositories/` 或 `application/ports/` 定义，Infrastructure 实现协议，不反向泄漏。 |
| 理由 | 依赖倒置的具体落地，支持静态类型检查与 mock 测试。 |
| 影响范围 | `domain/repositories/`、`application/ports/`、所有 Infrastructure 仓储实现 |

### ADR-007 — Workers 仅可导入 PySide6.QtCore

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | `workers/` 仅允许导入 `PySide6.QtCore`（线程原语 QThread/Signal/Slot），禁止导入 QtWidgets/QtGui。Worker 通过 Qt Signals 与 UI 通信，不直接操作 Widget。 |
| 理由 | 后台任务需要 Qt 事件循环原语，但不应耦合 UI 控件。 |
| 影响范围 | `workers/`（DEP-040、WRK-002） |

### ADR-008 — 统一 Loguru 日志，禁止 print()

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | 所有运行时信息用 Loguru，禁止 `print()`。日志配置在 `infrastructure/logging/configuration.py`，控制台 + 文件双输出，轮转 10MB/保留 30 天。 |
| 理由 | 集中可观测性，便于诊断与审计。 |
| 影响范围 | 全项目（COD-050/051） |

---

## Phase 2 架构决策

### ADR-009 — recognition_results 表 Schema

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | `recognition_results` 表字段：`id, photo_id, person_id, status, confidence, created_at`，外键到 `photos` 与 `people`。`status` 用 `MatchStatus` 枚举（pending/approved/rejected）。 |
| 理由 | 持久化识别结果与用户复核状态，支持审计与回溯。 |
| 影响范围 | Schema v2→v3；`infrastructure/database/sqlite_recognition_repository.py` |

### ADR-010 — 归档目录命名规则

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | 归档目录结构：`{archive_root}/{person_name}/{event_or_date}/{original_name}`。`archive_root` 走独立配置 `AppSettings.archive_root`，不复用 `output_root`。 |
| 理由 | 语义清晰，归档根独立于输出根，避免耦合。 |
| 影响范围 | `application/services/archive_path_builder_service.py`；`.env.example` 加 `ARCHIVE_ROOT=` |

### ADR-011 — 路径冲突策略

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | 归档路径冲突默认 `skip`，可通过 `AppSettings.archive_conflict_strategy` 配置 `overwrite` 或 `rename`。 |
| 理由 | 默认安全不覆盖用户文件，同时保留配置灵活性。 |
| 影响范围 | `application/services/archive_executor.py`；`.env.example` 加 `ARCHIVE_CONFLICT_STRATEGY=skip` |

### ADR-012 — AI 模型文件位置与下载策略

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | 模型文件位于 `resources/models/`，不提交 Git，走 `scripts/download_models.py` 手动下载。`ensure_runtime_directories` 不创建 `model_path` 目录，由 loader/download_models.py 自管。禁止自动下载。 |
| 理由 | 模型包大，避免误入版本控制；显式下载便于 CI 与离线环境。 |
| 影响范围 | `resources/models/`、`scripts/download_models.py`、`infrastructure/ai/insightface_loader.py` |

### ADR-013 — 缩略图缓存目录

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | 缩略图缓存目录固定 `data/cache/thumbnails/`，跳过已存在缩略图。 |
| 理由 | 集中缓存，避免重复生成。 |
| 影响范围 | `application/services/thumbnail_service.py`、`infrastructure/image/` |

### ADR-014 — ai 层职责拆分

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | `ai/` 只做检测/识别/匹配，不做业务决策；模型加载与路径探测归 `infrastructure/ai/InsightFaceLoader`。DEP-050 合规。 |
| 理由 | 分离 AI 能力与基础设施关注点，避免 ai 层持有模型生命周期细节。 |
| 影响范围 | `ai/`、`infrastructure/ai/` |

### ADR-015 — FaceEmbedding 持 tuple 不持 numpy

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | Domain 层 `FaceEmbedding` 值对象持有 `tuple[float, ...]`，不持有 numpy 数组，Domain 零框架依赖。 |
| 理由 | Domain 不应依赖 numpy；tuple 不可变且可哈希，适合值对象。 |
| 影响范围 | `domain/value_objects/face_embedding.py`（或对应实体） |

### ADR-016 — Embedding 序列化用 JSON 非 pickle

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | Embedding 持久化序列化用 JSON，禁止 pickle。 |
| 理由 | SEC-030：`pickle.loads` 是任意代码执行向量，安全红线。 |
| 影响范围 | `infrastructure/database/sqlite_face_embedding_repository.py` |

### ADR-017 — 匹配策略固定 1:N Top-1

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | 人脸匹配固定 1:N Top-1 策略，`max(boxes, key=confidence)` 锁定检测置信度最高的脸。Top-K/多候选留后续版本。 |
| 理由 | 简化首版匹配逻辑，满足当前业务；多候选引入交互复杂度，延后。 |
| 影响范围 | `application/services/match_persons_service.py`、`ai/similarity_matcher.py` |

### ADR-018 — MatchResult.box 字段类型 FaceBox | None

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | `MatchResult.box` 字段类型为 `FaceBox | None`，无人脸时 `box=None`，契约诚实。 |
| 理由 | 避免用空 FaceBox 哨兵值掩盖无人脸场景，类型签名应如实表达可空性。 |
| 影响范围 | `domain/entities/`（MatchResult） |

### ADR-019 — update_status 返回 int（受影响行数）

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | 仓储 `update_status` 方法返回 `int`（受影响行数），service 检查返回 0 防并发删除静默失败。 |
| 理由 | 静默失败难以诊断，显式行数让 service 层可判断并发竞争。 |
| 影响范围 | `domain/repositories/`、`infrastructure/database/sqlite_recognition_repository.py`、`application/services/review_recognition_service.py` |

### ADR-020 — ArchivePlanner → ArchivePlan → ArchiveExecutor 三段拆分

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | 归档流程拆为三段：`ArchivePlanner`（生成 `ArchivePlan`）→ `ArchiveExecutor`（执行 Plan）。CLI/UI/测试共用同一套归档计划。`--dry-run` 旗标在 Executor 内落 DRY_RUN 状态 + `ArchiveRecord` 入库，可预审整批归档计划。 |
| 理由 | 计划与执行分离便于 dry-run 预审、测试复用、UI 预览；避免 Service 既规划又执行的双职责。 |
| 影响范围 | `application/services/{archive_planner,archive_executor,archive_photos_service}.py`、`application/dtos/archive.py`、`main.py` 的 `archive` subparser |

### ADR-021 — captured_at 领域字段统一在导入阶段填充

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | 新增 `Photo.captured_at` + `PhotoMetadata.captured_at` 领域字段，由 `PillowPhotoMetadataReader` 在导入阶段统一填充（EXIF DateTimeOriginal → 文件 mtime 链式降级）。ArchiveService 不直接解析 EXIF，只消费领域数据。`ArchivePathBuilder` 在缺 `captured_at` 时落 `unknown-date` 占位段。 |
| 理由 | EXIF 解析是基础设施关注点，不应泄漏到 Application；领域字段统一后所有下游消费方无需各自解析。 |
| 影响范围 | `domain/entities/photo.py`、`domain/value_objects/photo_metadata.py`、`infrastructure/image/PillowPhotoMetadataReader`（EXIF 读取）、`application/services/archive_path_builder_service.py` |

### ADR-022 — AppSettings 新增独立 archive_root + archive_conflict_strategy

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | 新增独立 `AppSettings.archive_root`（默认 None）与 `AppSettings.archive_conflict_strategy`（默认 skip），不复用既有 `output_root`。`.env.example` 加 `ARCHIVE_ROOT=` / `ARCHIVE_CONFLICT_STRATEGY=skip`。 |
| 理由 | 语义更清晰，归档根与输出根职责不同，避免配置耦合。 |
| 影响范围 | `infrastructure/config/settings.py`、`.env.example` |

### ADR-023 — Git：每 Step 完成后独立提交

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | 每个 Step 完成后独立提交，提交信息遵循 Conventional Commits（`feat:`/`fix:`/`docs:` 等）。每个 commit 代表单一逻辑变更。 |
| 理由 | 可追溯、可回滚，便于审计与 bisect。 |
| 影响范围 | 全项目（GIT-006） |

### ADR-024 — 数据库 Schema 版本管理走 Alembic 迁移体系

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | Schema 迁移由 Alembic 管理（`alembic/` 目录 + `alembic.ini`）。当前版本 `001_initial_v4`。`sqlite_connection.py` 的 `initialize_schema()` 继续 `CREATE TABLE IF NOT EXISTS` 创建表结构，`alembic_runner.run_alembic_migrations()` 在每次启动时自动 `upgrade head` 确保迁移脚本未执行。Schema 版本不再依赖 `PRAGMA user_version` 手工维护——但 `initialize_schema()` 在新数据库上仍写 `PRAGMA user_version = 4` 保持与旧代码兼容。 |
| 理由 | ADR-005 的"延后"条件已满足：Schema 已稳定（v4），需要可追溯、可回滚的迁移脚本。Alembic 已在 `requirements/base.txt` 批准保留。 |
| 影响范围 | `alembic/`、`alembic.ini`、`infrastructure/database/alembic_runner.py`、`bootstrap.py`（集成 `run_alembic_migrations()`）；废弃 ADR-024 旧版本（用 `PRAGMA user_version` 单调递增管理的决策） |

### ADR-025 — FaceBoxEmbedding 归属 Domain 层（跨用例复用值对象）

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | `FaceBoxEmbedding`（`FaceBox` + `FaceEmbedding` 组合体）归属 `domain/value_objects/`，不作 Application DTO 处理。 |
| 理由 | 三点：(1) 字段 `FaceBox` 与 `FaceEmbedding` 均为既有合规 Domain 值对象，组合体本身不含框架依赖、零 numpy（符合 DEP-020/ADR-015），归 Domain 不破任何依赖规则。(2) 「检测绑定值对象」的语义并非 AI 实现专属——未来若新增「手工标注 + 嵌入」「外部嵌入源 + 检测框」等用例，`FaceBoxEmbedding` 同样表达「一张人脸在某一刻的检测位置与嵌入向量」这一跨用例的 Domain 概念，非 Issue-001 单一性能优化的临时载体。(3) 放 Application DTO 会使「检测与嵌入绑定」这一 Domain 概念被 Application 编排细节吞没，调用方需反向依赖 Application 层取值类型，违反 DIP（DEP-013 Application 用接口、DEP-023 Domain 定义接口不实现）。性能优化的实现细节（`detect_with_embeddings` 单次 `analysis.get`）属 AI 层适配，不应倒推决定 Domain 值对象归属。 |
| 影响范围 | `domain/value_objects/face_box_embedding.py`、`domain/value_objects/__init__.py`、`domain/__init__.py`；不迁移、不改公开 API。 |
| 反驳驳回 | Review MAJOR-2 提出「FaceBoxEmbedding 为适配 InsightFace API 形状而生，应迁 `application/dts/`」——驳回：该论断以「值对象的存在动机」判定归属而非以「字段语义 + 依赖合规 + 跨用例复用性」判定，与 DDD 值对象判定标准不符。值对象归属取决于它是否表达 Domain 概念且不持框架依赖，而非首次出现的用例在哪层。 |

### ADR-026 — 阶段 1 PluginContext 公共边界加固（公开 API 破坏性变更）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（前置门拍板 2026-08-11，定稿草案 `docs/development/phase1-adr-draft.md`） |
| 决策 | 阶段 1 将 B5 PluginContext 收敛为稳定插件公共边界——四项拍板：(1) `ContextAwarePlugin(Plugin)` 继承关系——新标准插件须同时实现 `set_context(context) + enable() + disable() + actions() + execute_action()`，mypy 静态守护完整，`enable(context)` 旧签名作兼容路径 Deprecated 保留一个版本；(2) Plugin DTO 边界——`PluginPhotoQuery.match_status` 3 态（pending/approved/rejected，与 Domain `MatchStatus(str, Enum)` 一致），`PluginPhotoSummary.match_status` 4 态含 none（RecognitionResult 不存在即未注册审核），Query 不含 none 与 Domain 三态一致，stats 插件取 none 数量取全集后客户端过滤；(3) `PluginReport` 单元格 `str | int | float` 混合——宿主渲染层做格式化（数值列右对齐/排序/国际化数量格式），插件给结构化数据；(4) `ActionResult` 收紧——`payload: Any` 改为 `report: PluginReport | None`，废止 `str(payload)` 兜底渲染。PluginContext 协议不再导入 Domain（加固 DEP-060 Plugins → Application only）。不改 Schema、不加依赖、不实现插件写操作。 |
| 理由 | B5 v2 落地三项公开 API 债务——插件间接依赖 Domain（`PhotoSearchCriteria`/`Photo`/`DuplicateReport`）、`ActionResult.payload: Any` 无类型守护、`enable(context)` 签名混淆生命周期与上下文注入。阶段 1 收敛为稳定公共边界。四项裁决点经前置门拍板：MAJOR-1 Protocol 继承选 A（mypy 静态守护完整）、MAJOR-2 "none" 语义选 A（实测 Domain `MatchStatus` 三态无 none，none 是插件层聚合概念）、MAJOR-3 单元格类型选 A（宿主管渲染职责正切）、MAJOR-4 执行顺序调 Protocol-first（先契约后实现减少跨步骤返工）。 |
| 影响范围 | `application/dtos/plugin_context.py`（新建）、`application/dtos/plugin_action_result.py`（改造）、`application/ports/plugin_context.py`（改造）、`application/ports/plugin.py`（改造）、`application/services/plugin_context_service.py`（新建）、`app/bootstrap.py`（改造）、`plugins/loader.py`（改造）、`presentation/views/main_window.py`（改造）、`examples/plugins/{stats_report_plugin,hello_plugin}.py`（新建/改造）、7 个测试文件、`docs/development/{plugin-guide,plugin-context-design,phase1-adr-draft}.md`、`.ai/PROJECT_STATUS.md`。ISSUE-016 ExportController DEP-002 修复同阶段独立提交（`fix: decouple export controller from infrastructure`），不在本 ADR 管辖。定稿草案 `docs/development/phase1-adr-draft.md`（含拍板记录 + Protocol-first 顺序 + 完成标准）。 |
| 反驳驳回 | 阶段 1 开工前审查报告识别 4 项 Major 设计问题——MAJOR-1 Protocol 关系缺失致静默失败风险（处置：继承 + 二道兜底）、MAJOR-2 `match_status` Literal 与 Domain 不一致（处置：实测 MatchStatus 字面值 + Query/Summary 分态）、MAJOR-3 强制全 str 与 stats 数值用例冲突（处置：混合类型 + 宿主格式化）、MAJOR-4 顺序违反依赖方向（处置：Protocol-first）。4 项 Major 经前置门拍板选 A 全部处置，7 项 Minor 同批登记。 |

### ADR-027 — 阶段 2 Alembic migration 接管 Schema DDL（架构基础设施深化）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（前置门拍板 2026-08-12，定稿草案 `docs/development/phase2-adr-draft.md`） |
| 决策 | 阶段 2 深化 ADR-024 妥协形态——migration 从空 stamp 接管真实 Schema DDL。三拍板：(1) migration 全接管 6 表 + 6 索引 DDL（people/folders/photos/recognition_results/person_embeddings/archive_records），`initialize_schema()` 仅留 mkdir + PRAGMA 仅新库 stamp + 调 Alembic；(2) 新建 `002_split_create_ddl` 持 DDL，`001_initial_v4` 保留空 stamp 形态（避免改造 upgrade/downgrade 的首次 migration 无前版本可回难题）；(3) 保留仅新库（current_version==0）`PRAGMA user_version = 4` 兼容旧库迁移路径（ADR-024 已述兼容旧代码）。不推翻 ADR-024 raw SQL 路线，不动 ORM models / Repository 基类。 |
| 理由 | ADR-024 落地了 Alembic 迁移体系雏形但 `001_initial_v4` 是空 stamp migration（upgrade/downgrade 全 pass），`sqlite_connection.py:109-206` 的 `initialize_schema()` 仍用 raw SQL `CREATE TABLE IF NOT EXISTS` 创建 6 表 + 6 索引，Alembic 仅 stamp 版本未接管 Schema DDL——非 roadmap §190 期望的"Alembic 接管 Schema 版本管理"完整态。本 ADR 深化此形态：DDL 迁入 migration upgrade，downgrade 持 DROP TABLE IF EXISTS（FK 依赖逆序），幂等守护（CREATE/DROP TABLE IF NOT EXISTS/EXISTS）容重复执行。 |
| 影响范围 | `alembic/versions/002_split_create_ddl.py`（新建，6 表 + 6 索引 DDL）、`infrastructure/database/sqlite_connection.py`（`initialize_schema()` 改造移除 CREATE TABLE 重复路径）、`tests/integration/database/test_alembic_migrations.py`（新建，migration up/down + Schema 版本一致 + Repository 对照回归）、`.ai/PROJECT_STATUS.md`、`.ai/DOCUMENT_INDEX.md`（phase2-adr-draft.md 登记）。不变：Domain Schema、ORM models、Repository 基类/Session 生命周期、`alembic/env.py`/`alembic.ini`/`alembic_runner.py`、`001_initial_v4.py`（保留空 stamp）、依赖（`alembic==1.16.4` 已在）。定稿草案 `docs/development/phase2-adr-draft.md`（含拍板记录 + 完成标准）。 |
| 反驳驳回 | 阶段 2 开工前实测推翻原假"Alembic 待初始化"——Alembic 已落地（ADR-024 Accepted 2026-07-25），`alembic/`+`alembic.ini`+`alembic/versions/001_initial_v4.py`+`alembic_runner.py`+`run_alembic_migrations()` 集成 bootstrap+`alembic==1.16.4` 在 requirements。真实缺口是 `001` 空动作+`initialize_schema()` 持 raw SQL DDL+无 Alembic 测试。本 ADR 处置此三缺口不推翻 ADR-024。 |

### ADR-028 — 阶段 3 插件写能力 import_people（公开 API 扩展）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（前置门拍板 2026-08-13，定稿草案 `docs/development/phase3-adr-draft.md`） |
| 决策 | 阶段 3 重新开放 B5-a 暂缓项的写能力——但仅限 import_people（最小写路径），export 续暂缓留后续轮单独裁决。四拍板：(0) 真实用例驱动——插件从外部 CSV/JSON 导入人员实体（推翻 B5-a "YAGNI 当前无清晰用例"原裁决依据）；(1=A) 仅 import_people，export 不开放（ExportController 已有宿主路径不需插件触发）；(2=A) 无审批门先行（插件直调 PluginContextService.import_people，宿主仅渲染 ActionResult，审批门留后续轮加）；(3=C) 双向 DTO 脱 Domain——PluginImportPersonRow/PluginImportPeopleCommand 入参 + PluginImportResult 结果（imported_count/skipped_count/imported_person_ids: tuple[str, ...] 非 UUID/errors），不持 Person 实体/UUID 字面/PersonRepository 实例，与 ADR-026 Plugin DTO 边界一致。 |
| 理由 | B5-a 原裁决"暂缓 import/export"依据是"YAGNI 当前无清晰用例"——本 ADR 推翻依据：真实用例已现（插件从外部 CSV/JSON 导入人员实体），故重新开放写能力。范围限 import_people 先行：export 写文件用例暂缓（ExportController 已有宿主路径，不需插件触发，YAGNI）。宿主审批门暂缓：复杂度低先行，审批门（B/C 选项）留后续轮加（若真实用例需高危操作确认）。双向 DTO 脱 Domain：最小权限，与 ADR-026 Plugin DTO 边界一致，插件不触 ImportPeopleService/PersonRepository（DEP-060 守护）。 |
| 影响范围 | `application/dtos/plugin_context.py`（扩 PluginImportPersonRow/PluginImportPeopleCommand/PluginImportResult）、`application/ports/plugin_context.py`（新增 import_people 签名）、`application/services/plugin_context_service.py`（扩展 import_people 映射编排 + ImportPeopleService 联动）、`app/bootstrap.py`（注入 ImportPeopleService 依赖到 PluginContextService）、`examples/plugins/`（可选新增 import demo 或扩 stats_report）、`tests/unit/application/test_plugin_context_service.py`+`test_plugin_dtos.py`（扩展）、`docs/development/plugin-guide.md`（写能力章节）、`.ai/PROJECT_STATUS.md`、`.ai/DOCUMENT_INDEX.md`（phase3-adr-draft.md 登记）。不变：Domain Schema、依赖、ExportController（宿主路径不动）、`enable(context)` 兼容路径（另项裁决）、export 写能力（续暂缓）。定稿草案 `docs/development/phase3-adr-draft.md`（含拍板记录 + 完成标准）。 |
| 反驳驳回 | B5-a 原裁决"暂缓 import/export"依据"YAGNI 当前无清晰用例"被推翻——真实用例已现（插件从外部 CSV/JSON 导入人员实体），故重新开放写能力。但范围限 import_people 先行不双开放，export 续暂缓留后续轮单独裁决（YAGNI：ExportController 已有宿主路径不需插件触发）。宿主审批门暂缓（复杂度低先行）。 |

---

## 已裁决的规则/文档冲突（已在代码/规则中执行）

> 权威审计方法论：`.ai/rules/audit-methodology.md`（迁移自废弃文档 `.ai/Consistency-Audit-2026-07-13.md` §8，2026-07-24 裁决2已物理删除该废弃文档）。本节仅列已裁决并执行的冲突处置。

| ID | 冲突 | 裁决 | 状态 |
|---|---|---|---|
| R-1 | Workers 层导入 `PySide6.QtCore` vs DEP-040 依赖矩阵未授权 | 更新 DEP-040 + WRK-002，允许 `PySide6.QtCore`（线程原语 only） | ✅ 已执行 |
| R-2 | SQLite 代码在 `infrastructure/repositories/` vs `architecture-rules.md` §14 要求 `infrastructure/database/` | 迁移至 `infrastructure/database/` | ✅ 已执行 |
| R-3 | COD-005 行宽 88 vs `pyproject.toml` 行宽 100 | 统一为 100 | ✅ 已执行 |
| R-4 (C-1) | ARC-008 §8 vs §14 SQLite 位置表述不一 | §8 加 SQLite 例外条款 | ✅ 已执行 |
| R-5 (C-2) | `pydantic` 标 "if introduced" 但已投入使用 | 升为正式批准，补入 ai-rules §3 | ✅ 已执行 |
| R-6 (C-4) | 6 项库（Pillow/SQLAlchemy/alembic/watchdog/pytest-qt/ONNX）未进 §13/§3 | 补入并标注层归属 | ✅ 已执行 |
| R-7 (C-5) | `architecture-rules.md` §18 Logging Rules 允诺 `common/logging/` vs DEP-071 禁 common 导第三方 | 删除 `common/logging/` 选项 | ✅ 已执行 |
| R-8 (2026-07-24) | `architecture-rules.md` §5 Allowed Dependencies 与 `dependency-rules.md` §4 依赖矩阵表述冲突（§5 缺 `ai`/`workers`/`plugins`/`common` 全方向，且未含 SQLite 仓储例外等） | 以 DEP §4 矩阵为唯一权威；ARC §5 改指针，正文不重复矩阵 | ✅ 已执行（SSOT 收敛主题2） |

---

## 状态约定

- **Accepted**：已确认并落地，AI 必须遵守，不得重新设计。
- **Proposed**：提议中，未落地，AI 不得假设其生效。
- **Superseded**：被后续 ADR 取代，保留历史但不再生效（标注被谁取代）。
- **Deprecated**：废弃，不再生效。

---

> 📝 本文件由 AtomCode (GLM-5.2) 于 2026-07-18 基于真实项目决策记录生成。只有真正产生新的架构裁决时更新；不记录 Bug/TODO/未确定方案。

End of ARCHITECTURE_DECISIONS.md

