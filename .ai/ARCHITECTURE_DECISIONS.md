# ARCHITECTURE_DECISIONS.md — PhotoArchiver 架构决策记录（ADR Register）

> **本文档是已确认架构决策的唯一寄存器（Architecture Decision Register）。**
>
> 回答：**"哪些架构决策已经确定，AI 不得重新设计？"**
>
> 这是整个 AI Runtime Context 中最重要的稳定文档之一。长期保留，不会因版本变化删除。
>
> Version: 1.9.0 ｜ Status: Stable ｜ Last Updated: 2026-09-29

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

### ADR-029 — search_photos 识别状态批量联查修复 N+1（公开端口扩展）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（前置门拍板 2026-08-25，定稿草案 `docs/development/phase4-adr-draft.md` B4-2） |
| 决策 | `RecognitionRepository` Protocol 新增 `list_first_by_photo_ids(photo_ids) -> dict[UUID, RecognitionResult]`——SQLite 以 IN 子句分块（每块 500 参数）单次往返取回每张照片最早识别结果（ORDER BY created_at, id，镜像 `list_by_photo(id)[0]` 语义）；`PluginContextService.search_photos` 从逐照片 `list_by_photo` 改为一次批量取回后内存配对。 |
| 理由 | `tools/bench_plugin_search.py` 实测 N+1：调用次数恒等于照片数（2600 张 → 1137.9ms），且该路径运行于主窗口筛选刷新与插件报表的 UI 线程同步路径。设计细化论证：前置门原荐「PhotoRepository 承载联查」在详细设计中确认使 InMemory 测试替身无法独立实现 status 轴（photo 仓储反向耦合 recognition 聚合），等效细化为 RecognitionRepository 批量接口——同达 O(1) 往返目标、端口面更小、替身可实现（判定标准与 ADR-025 一致：以字段语义 + 跨用例复用性定归属，不以首次出现用例倒推）。 |
| 影响范围 | `domain/repositories/recognition_repository.py`（协议扩展）、`infrastructure/database/sqlite_recognition_repository.py`（分块 IN 实现）、`application/services/plugin_context_service.py`（search 循环改批量）、`tests/unit/application/test_plugin_context_service.py`（N+1 回归守护用例：calls==1）、`tests/unit/infrastructure/repositories/test_sqlite_repositories.py`(批量语义 + 空输入 2 用例)、3 个显式继承 RecognitionRepository 的测试替身补齐 stub、`tools/bench_plugin_search.py` 基线工具入库。不变：Schema、依赖、SearchPhotosService 签名、list_by_photo 及其余端口成员。 |
| 实施结果 | 2600 张库 1137.9ms → **62.5ms（18.2×）**；识别仓储往返 2600 次 → 1 次。前后对比见 phase4 定稿草案 §6。 |

### ADR-030 — 阶段 4 技术债三项轮次裁决（兼容路径挂账 / export 终结 / 审批门续暂缓）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（前置门拍板 2026-08-25，定稿草案 `docs/development/phase4-adr-draft.md` B4-1/B4-4/B4-5） |
| 决策 | 三项裁决：(1) 旧 `enable(context)` 兼容分发分支的移除绑定 v1.0.0 发布后的首个破坏性窗口（即 v2.0.0）执行——兑现 ADR-026 "Deprecated 保留一个版本"承诺，本轮不动 loader；(2) export 插件写能力经负责人确认**无真实用例**，B5-a/ADR-028 的 export 暂缓项就此 **YAGNI 正式关闭**（获得确定性终态而非无限期悬挂），未来出现真实用例须另起前置门草案重新裁决；(3) 宿主审批门继续暂缓——无已知高危写用例前不引入确认复杂度（ADR-028 裁决点 2=A 逻辑延续）。 |
| 理由 | grep 实证旧签名在生产与示例代码零消费者（仅测试 fake 自身使用），影响面完全可控但仍属破坏性变更，须绑定主版本窗口以守 GIT 语义化承诺；YAGNI 结论使长期开放的暂缓项获得确定性终态，消除文档中"续暂缓"开放态的歧义与漂移温床。 |
| 影响范围 | v2.0.0 轮实施清单（loader `_enable_plugin` 二分叉收敛 + `test_plugin_lifecycle_compatibility.py` 兼容矩阵删改 + plugin-guide legacy 表述刷新 + Release Notes 破坏性标注）；`plugin-context-design.md` 头部取代注记已就位；本轮无代码变更。 |

### ADR-031 — 应用运行形态定位：源码/clone 唯一受支持，打包安装态按设计不支持

| 字段 | 值 |
|---|---|
| 状态 | Accepted（前置门拍板 2026-08-26，定稿草案 `docs/development/phase5-adr-draft.md` B5-1~B5-3 全按推荐通过） |
| 决策 | 四点：(1) 应用受支持运行形态 = 仓库 clone + venv + `pip install -r requirements/base.txt` + `python main.py`（user-guide 链路，入口自带 src 路径注入）；(2) Release 页挂载的 wheel/sdist 定位为**源码元数据产物**，不承诺安装态可运行，Release body 置顶安装态标注文案（owner 粘贴）；(3) ISSUE-018 以 **by-design 正式终结**——安装态断点 E1-E6（wheel/sdist 无 main.py 与 console 入口、alembic 五层 parent 解析、插件目录 4×parent 缺失、DATABASE_URL/MODEL_PATH/LOG_DIRECTORY 默认值 CWD 相对、无 MANIFEST/package-data）不再作为缺陷追踪；(4) 未来出现非技术用户分发需求时，另起前置门草案按方案 B 重开（console 入口 + package_data + 用户目录默认值重构，v1.1.0 候选）。 |
| 理由 | 实测证明安装态支持是运行形态级重构而非补丁：E1-E6 断点中默认路径语义（CWD 相对迁往用户目录）直接触及 ADR-010/022 的 base 设计与设置体系；在无非技术用户分发需求的现状下投入违背 YAGNI。受支持流（user-guide 链路）全程不安装包本体，方案 A 以一条页内标注获得确定性终态并消除 ISSUE-018 的开放态歧义。 |
| 影响范围 | GitHub Release v1.0.0 body 标注（owner 粘贴，文案见 phase5 草案 §4）；KNOWN_ISSUES ISSUE-018 条目移除（by-design 关闭不入清单）；`docs/user-guide/installation.md` 已与该定位一致无需改；代码 / Schema / 依赖 / Schema 迁移体系零变更。反例守护：禁止未来无声引入「半支持安装态」（如仅修 E3 不修 E4/E5）。 |
| 追记（2026-09-13，ADR-031 方案 B 触发落地） | owner 立项 Windows 桌面交付（Phase P）：PyInstaller onedir + Inno Setup per-user 安装器（在线/离线双产物）+ `download-models` 内置命令（sha256 fail-closed）。源码形态继续受支持；打包适配点：alembic 脚本随 bundle（frozen 感知 runner）、模型目录 frozen 锚定 `<exe>\models`、枚举前置主线程（ADR-041）使扫描在打包形态天然规避 LIMIT-006 线程形态。详见 `packaging/windows/`。 |

### ADR-032 — Phase 6 识别管线吞吐加固五项裁决（基准入库 / 线程并行 / 持久化批下推 / 进度保持 / UI 触发点不补）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（前置门拍板 2026-08-28，定稿草案 `docs/development/phase6-adr-draft.md` A-1~A-5 全按默认推荐） |
| 决策 | 五项裁决：(1) A-1 基准工具 `tools/bench_recognition.py` **入库长期保留**（库容 × workers 双梯度，数字续记 docstring；管线零生产消费者 F5 使其兼作当前唯一可复跑驱动入口）；(2) A-2 并行形态 = **ThreadPoolExecutor per-photo 复用 MAX_WORKERS 先行**，并行段限纯推理（detect_with_embeddings + cosine match），持久化收敛回主线程；B（onnxruntime batch 批推理）视 A-1 证据决定是否二轮，进程池排除；(3) A-3 Domain `RecognitionRepository` 扩 `add_many`，SQLite 端单事务批量提交（往返 O(N)→O(1)）；(4) A-4 进度语义保持「完成张数」口径与上报规则（首末张 + 每 10 张）不变；(5) A-5 UI 识别触发点本轮不补（功能开发另立轮次，避免范围蔓延）。四条不变量（结果等价 / SQLite 线程安全 / 进度语义 / 失败隔离）全部必选。 |
| 理由 | F1 串行 for 循环 + F4 逐条持久化是识别管线仅有的两个可量化瓶颈；F7 实证 onnxruntime 推理释放 GIL 使线程并行前提成立；ADR-029/B4-2 端口扩展先例直接覆盖 A-3。基准先行（A-1）把「模型对象跨线程共享是否安全」的设计风险转化为可实测证据，避免盲改。 |
| 影响范围 | `tools/bench_recognition.py`（新建）、`application/services/match_persons_service.py`（并行化 + 批量收集）、`domain/repositories/recognition_repository.py`（协议扩 add_many）、`infrastructure/database/sqlite_recognition_repository.py`（单事务批量 INSERT）、`tests/unit/application/test_match_persons_service.py` + `tests/unit/infrastructure/repositories/test_sqlite_repositories.py`（等价/失败隔离/单事务/进度用例，410→417）、`CHANGELOG.md`（v2.1.0 段）、`.ai/PROJECT_STATUS.md`、本文件。不变：Schema、依赖、`MatchPersonsCommand` 形状（F5 零生产消费者）、`max_workers=1` 串行路径逐字节等价。 |
| 实施结果 | 全网格基线（2026-08-29，37.4 min，exit 0）：2600 张串行 656.94s（3.96 photos/s）；4 workers 514.00s（5.06 photos/s，**1.28×**）——线程扩展弱于建议阈值 ≥2×，与 §5 预判吻合（onnxruntime intra-op 池单次推理已吃满核心，worker 线程仅重叠 Python 侧开销）；**A-2=B 二轮裁决条件已触发，是否立项由 owner 拍板**（REV-AI-003）。InsightFace session 跨线程共享实测安全（2/4 workers 全档 100% 产出、等价不变量全程成立，§5 首项风险解除）。 |

### ADR-033 — Phase 7 识别管线死重模型剔除（allowed_modules 加载收敛 / landmark+genderage 出局 / 剩余非推理段缓议）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（前置门拍板 2026-08-29，定稿草案 `docs/development/phase7-adr-draft.md` W2-1/W2-2/W2-3 全 A，W2-2 前提经 owner 确认：近期无性别/年龄功能规划） |
| 决策 | 三项裁决：(1) W2-1 landmark 死重剔除 = **A**——loader `FaceAnalysis` 构造传 `allowed_modules=("detection", "recognition")`，加载层直接跳过 buffalo_l 包内 1k3d68 + 2d106det 两个 landmark 模型（35.4 ms/张，生产仅消费 bbox+kps+embedding，零消费 grep 实证）；(2) W2-2 genderage 一并剔除 = **A（附条件已确认）**——`Person` 域实体无性别/年龄字段，src 全库零消费，未来需要时加回一个模块名即恢复，无数据/接口迁移成本；(3) W2-3 剔除后剩余 ~38 ms/张非推理段（rec 对齐 ~30 + det 前后处理）本轮不改造——先拿零风险增益复测，按剩余占比与真实需求再议；进程池方案已被 W1 证据排除（模型多份加载不划算）。 |
| 理由 | W2-segment 尖刺（`tools/spike_segment_profile.py` v2，账目闭合 251.3≈249.4≈254.4 ms/张）A/B 移除实验实证：剔除后 254.4→128.2 ms/张（**1.985×**）且 bbox/kps/embedding 输出逐字节不变——最大增益不是复杂的并发改造而是两行加载配置；insightface `allowed_modules` 为公开 API（签名实测第 4 参），锁版本前提下稳定。phase6 并行化 1.28× 的根因（非推理 GIL 串行段 ~143ms/张）经本轮剔除削减近半，零结构风险。 |
| 影响范围 | `infrastructure/ai/insightface_loader.py`（`allowed_modules` 一行 + 证据注记）、`tools/bench_recognition.py`（复测数字续记 docstring）、`CHANGELOG.md`（v2.2.0 段）、版本链 bump（pyproject + .env.example）、`docs/development/phase7-adr-draft.md`（转定稿）、`.ai/PROJECT_STATUS.md`、本文件。不变：Schema、依赖、AI 端口契约（`FaceDetector`/`FaceRecognizer` 签名）、phase6 并行结构（线程池 + `add_many` 批持久化 + 进度语义）、识别结果集与入库顺序逐字节等价。 |

### ADR-034 — Phase E 删除语义与库管理（照片/人员删除 + 重扫对账 + 重复处置）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（owner 拍板 2026-09-06：D1–D6 全部按建议执行——「按建议执行」） |
| 决策 | 六项裁决落定（定稿草案 `docs/development/phase8-adr-draft.md`，证据链为 `002_split_create_ddl` 的 FK 级联矩阵实证）：(D1) 照片删除确认既有 CASCADE——识别结果与归档记录随删（FK 层自动）；(D2) 人员删除确认既有 SET NULL + CASCADE——嵌入随删、识别结果归属置空为"未知人员"、照片全部保留；(D3) 磁盘文件一律不动（含归档产物），删除仅作用于库内登记，UI/CLI 必须明示；(D4) 硬删除、不扩 schema（回收站/撤销为 roadmap Out-of-Scope，安全网 = Phase B 启动备份）；(D5) 重扫对账"只增不删"——文件消失不自动删库（防移动盘误判），提供显式 `prune-missing` 清理入口（dry-run 默认），文件内容变化（mtime/hash）更新登记元数据；(D6) 重复处置组内保留最早注册一张（`created_at` 最小、同刻 id 决胜），其余删登记。通用：remove 幂等（0 行成功）、删除必经确认流（级联计数预览）、loguru 审计行、IN 子句 500 分块（ADR-029 先例）。 |
| 理由 | 删除级联语义已由 schema FK 完整表达（recognition/archive 对 photo CASCADE、recognition 对 person SET NULL、embeddings 对 person CASCADE、photos 对 folder SET NULL）且连接强制 `PRAGMA foreign_keys=ON`——本 ADR 确认既有语义而非新设计，零 schema migration；Phase B 备份（J6 恢复演练实证）满足 roadmap 前置"删除必须建立在有备份的基础上"；软删除被否决因其引入 migration + 全查询过滤 + 撤销语义，而撤销明确 Out-of-Scope。 |
| 影响范围 | `domain/repositories/{photo,person}_repository.py`（协议扩 remove）、`infrastructure/database/sqlite_{photo,person}_repository.py`（分块 DELETE）、`infrastructure/repositories/in_memory_*`（替身同步，不模拟级联——级联裁判专属真实 SQLite 集成测试）、`application/dtos/deletion.py` 与四个删除/对账服务（新建）、`presentation`（删除入口 + 确认流 + 重复处置按钮）、`main.py`（prune-missing 子命令）、scan service（内容变更元数据更新，PhotoRepository 扩 update_metadata）、`tests/`（级联矩阵/幂等/预览/对账/CLI）、CHANGELOG v2.4.0 + 用户指南。不变：既有方法签名、Schema、导入/扫描/归档/导出行为、磁盘文件（零触碰不变量）。 |

---

### ADR-035 — captured_at 回填通道 + 默认路径锚定 + platformdirs 依赖批准

| 字段 | 值 |
|---|---|
| 状态 | Accepted（owner 2026-09-08「按建议方案执行」拍板，计划 `docs/development/phase-f-plan.md`） |
| 决策 | 三项：(1) **`PhotoRepository.update_capture_time(photo_id, captured_at) -> int` 协议扩**（SQLite/InMemory 双实现，只 UPDATE captured_at 列，与 ADR-034 的 `update_metadata` 对称——供 Issue-019 后历史照片拍摄时刻一次性回填 CLI 使用，幂等返回受影响行数）；(2) **默认路径锚定**：`database_url` 与 `log_directory` 的**默认值**由 CWD 相对改为 `platformdirs.user_data_dir/user_log_dir("PhotoArchiver")` 锚定（显式 `.env` 配置完全优先，`model_fields_set` 判定；显式相对值保留既有 CWD 警告；旧 CWD 库首启检测仅打印迁移引导、不自动搬库）；(3) **platformdirs 依赖批准**（4.10.0，仅 `infrastructure/config` 层） |
| 理由 | (1) Issue-019 修复后新扫描已正确，历史错误值需一次性纠错；`update_metadata` 有意保留快照列，回填需要对称的专用通道（最小写面）。(2) N4 实证 CWD 相对默认值导致换目录启动静默换库（真实用户库分裂风险，P1），锚定用户数据目录是三平台惯例且为 Phase D 形态二铺路；显式配置优先保证零破坏。(3) platformdirs 为 tox/black 生态标准库（venv 已有 4.10.0 传递安装），手写三平台路径惯例易错。 |
| 影响范围 | `domain/repositories/photo_repository.py`（协议扩）、`infrastructure/database/sqlite_photo_repository.py` + `infrastructure/repositories/in_memory_photo_repository.py`（实现）、`infrastructure/config/settings.py`（默认值锚定 + 锚定常量）、`app/bootstrap.py`（旧库首启提示）、`requirements/base.txt`、`.ai/rules/dependency-rules.md` §13、`application/services/backfill_capture_time_service.py`（新建）、`main.py`（backfill-capture-time 子命令）、测试、用户指南。不变：显式 DATABASE_URL 语义、photos 表其余列、既有迁移链路。 |
| 后续 | Phase D 形态二（P2-11）落地时复用锚定目录常量；旧 CWD 库自动迁移（migrate 子命令）如需要另行立项。 |

---

### ADR-036 — Phase F 正确性收口：Windows 文件名净化 + 扫描链接防护 + 查询/取消/CLI 裁决

| 字段 | 值 |
|---|---|
| 状态 | Accepted（owner 2026-09-12 按建议批准计划裁决点 D4–D9，计划 `docs/development/phase-f-correctness-plan.md`；依据 2026-09-10 体检 P0-2/P1 项） |
| 决策 | 五项：(1) **Windows 文件名净化（D4）**：Domain `ArchivePath` 段净化为纯字符串逻辑——非法字符 `: * ? " < > \|` 与控制字符替换为 `_`、尾点/尾空格去除、保留设备名（去扩展名后匹配 CON/PRN/AUX/NUL/COM1-9/LPT1-9，大小写不敏感）前缀 `_`；静默替换 + loguru 审计，不拒绝（不把平台限制转嫁给用户）；仅影响新归档，存量 `archive_records` 不动。(2) **扫描链接环防护（D5）**：扫描器改迭代式 `os.scandir` + visited realpath 环检测 + 可配深度上限（默认 32），不跟随链接目录——同时覆盖 symlink 与 Windows junction（junction 的 `is_symlink()` 为 False，仅跳 symlink 防不住）。(3) **"未匹配"哨兵实现（D6）**：`PhotoSearchCriteria.match_status` 接受 `UNMATCHED` 哨兵（Domain 值对象导出），SQLite 走 `LEFT JOIN ... IS NULL`，识别轴 JOIN 加 `DISTINCT` 消除一照片多识别行的重复行；InMemory 按"recognition 依赖轴返回空"既有惯例。(4) **导出取消通道（D7）**：任务边界粒度（LIMIT-002 同型），import 任务补 cancelled 接线对齐 scan。(5) **CLI 启动备份对齐 GUI（D8）**：修订 `docs/development/configuration.md` 既定"CLI 不生成启动备份"行为，CLI 写库子命令与 GUI 同样生成 `VACUUM INTO` 快照。D8' 语言占位控件标注 Out-of-Scope 不实装；D9 本阶段发版 **v2.5.0**。 |
| 理由 | 体检 Release Candidate 差距四项中三项（F-10/F-13/N-2）+ P1-3/P1-4 属本阶段；净化为静默替换而非 ValidationError，避免"人名叫 con"这类合法输入持续 FAILED；环检测用 realpath 集合而非 reparse tag 平台特判，跨平台可维护；哨兵实现成本低于改写文档承诺的沟通成本；CLI 与 GUI 同样写库（scan / prune-missing / backfill），风险面同量级，备份应一致。 |
| 影响范围 | `domain/value_objects/archive_path.py`（段净化，纯字符串，零文件系统调用）、`infrastructure/filesystem/local_photo_file_scanner.py`（遍历重写）、`domain/value_objects/photo_search_criteria.py` + `domain/repositories/photo_repository.py`（协议 docstring）、`infrastructure/database/sqlite_photo_repository.py` + `infrastructure/repositories/in_memory_photo_repository.py`（DISTINCT + LEFT JOIN）、`presentation`（import cancelled 接线、导出取消、空态、审核行可读性、.xlsm 过滤器）、`application`/`main.py`（导出取消通道、CLI 备份、import-people/export 子命令）、`requirements/dev.txt`（pytest-cov，dev-only）、`docs/development/configuration.md`（D8 行为修订）、README（N-2 修订）。不变：Schema、既有归档记录、磁盘文件零触碰不变量、识别管线（ADR-032/033）、显式配置语义。 |
| 后续 | N-1 插件可见性、F-8 并行匹配分片 flush、N-5 去重键、N-8 孤儿缓存不在本 ADR 范围（见 KNOWN_ISSUES ISSUE-020..023）。 |

---

### ADR-037 — 并行匹配持久化分片 flush（修订 phase6 裁决 A-3 的"末尾单次 add_many"）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（2026-09-12，ISSUE-021 / 2026-09-10 体检 F-8 修复，owner 既有"下一轮处理"指示） |
| 决策 | `MatchPersonsService._execute_parallel` 的持久化由"全程收集、末尾单次 `add_many`"改为**每消费 `_PARALLEL_FLUSH_SIZE=50` 个识别聚合 flush 一次**（余片收尾 flush）。批量下推（ADR-029 单事务 insert）保留；flush 全部发生在消费循环所在线程，线程画像不变。 |
| 理由 | 体检 F-8：`max_workers>1` 时崩溃丢整批（2600 张 × 332s 计算结果全部丢失，仅默认 `max_workers=1` 规避）。分片后崩溃丢失窗口 ≤ 49 条；50 条/批的额外事务开销相对 11.22 photos/s 推理耗时可忽略。 |
| 影响范围 | `application/services/match_persons_service.py`（分片 flush + 日志）、`tests/unit/application/test_match_persons_service.py`（分片边界 [2,2,1] 矩阵 + 小批单次 flush 契约）、`KNOWN_ISSUES.md`（ISSUE-021 同提交删除）。不变：A-4 顺序/进度契约、识别管线推理路径（ADR-032/033）、Repository 协议（`add_many` 语义不变，仅调用时机分片）。 |

---

### ADR-038 — 插件目录生产接线（ISSUE-020 裁决①：恢复对外承诺）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（owner 2026-09-12 二选一裁决：① 接入可配置插件目录并调用 `_add_plugin_actions()`） |
| 决策 | 新增设置 `PLUGINS_DIRECTORY`（`plugins_directory: Path \| None = None`，显式 opt-in）——配置后启动链 `load_from_path(directory) → enable_all() → _add_plugin_actions()` 自动执行，插件动作挂载主工具栏；未配置（默认）零加载，示例插件仍不自动加载（与既有决策零破坏）。加载/启用失败由 PluginRegistry 既有错误隔离兜底（坏插件记 error 跳过、宿主续运行，ADR-026）。 |
| 理由 | 体检 N-1：插件机制完整但 `_add_plugin_actions()` 生产零调用，对外宣称与用户可见性名实不符。owner 裁决恢复承诺而非收回宣称。**opt-in 而非默认目录**：插件是启动即执行的 Python 代码，默认 CWD/锚定目录自动执行会引入供应链风险；显式配置 = 用户明确信任该目录（安全模型与浏览器扩展一致）。 |
| 影响范围 | `infrastructure/config/settings.py`（新字段 + optional-path validator 组）、`app/bootstrap.py`（cwd 相对警告清单加插件目录）、`presentation/views/main_window.py`（`_load_plugins` 挂载全链 + 加载摘要日志）、`docs/`（configuration.md 环境变量表 / plugin-guide / FAQ / README）、`tests/`（settings 3 项 + 集成 4 项：标准加载/未配置/目录缺失/坏插件隔离）、`KNOWN_ISSUES.md`（ISSUE-020 同提交删除）。不变：Plugin 协议、PluginContext、错误隔离语义、示例插件不自动加载。 |

---

### ADR-039 — 旧 CWD 库迁移子命令 `migrate`（落地 ADR-035"后续"项）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（owner 2026-09-12 指示继续候选清单；承接 ADR-035 后续注记与 Phase F 计划 D3"不自动搬移"原则） |
| 决策 | 新增 CLI 子命令 `migrate`：将旧版启动目录下的数据库（CWD `data/photo_archiver.db`）经 `VACUUM INTO` 一致性快照**复制**到锚定默认库路径。dry-run 默认（只打印计划），`--execute` 才复制；**复制不搬移**——旧库原地保留。仅适用于"DATABASE_URL 未显式配置（锚定默认接管）"场景；bootstrap 已创建的空锚定库（六业务表零行，启动备份已留快照）可被安全接管，非空目标拒绝并指引手动处置。 |
| 理由 | ADR-035 路径锚定落地后，旧版用户的库仍在 CWD，bootstrap 只打印迁移指引无可执行动作——`migrate` 补齐该闭环。VACUUM INTO 复制对 WAL 库事务一致；空库接管安全（bootstrap 每次启动已对锚定库做 VACUUM INTO 备份）。 |
| 影响范围 | `infrastructure/database/backup.py`（`copy_database` 原语，拒绝覆盖既有目标）、`infrastructure/config/settings.py`（`default_database_path()` 助手）、`main.py`（migrate 子命令 + 空库判定）、`app/bootstrap.py`（迁移提示文本补 migrate 指引）、user-guide 两表、tests（CLI 壳 6 项）。不变：bootstrap 启动链、显式 DATABASE_URL 语义、旧库文件零触碰。 |

---

### ADR-040 — 扫描任务移出 QThreadPool（LIMIT-006 规避，owner 立项）

| 字段 | 值 |
|---|---|
| 状态 | Rejected（规避证伪：run #91 在 Python 线程上段错误复现——线程类型不是必要条件，崩溃点漂移至服务的 realpath 解析层，`<no Python frame>` 佐证原生层故障；代码已回滚至 QThreadPool 模型，darwin skip 恢复） |
| 决策 | `QtWorkerExecutor.submit` 增加 `run_on_python_thread` 开关；**仅扫描任务**（`ScanController.scan_folder`）以该开关在普通 Python `threading.Thread`（daemon、按 task_id 命名）上执行；其余任务（import/match/export/…）保持 QThreadPool 不变。`QtWorkerRunnable` 的信号契约（started/progress/completed/failed/cancelled + pending-terminal replay）完全不变——Qt 信号从 Python 线程发出，经队列连接投递到主线程，消费方（单飞守卫/取消/终端复位）零改动。 |
| 理由 | D-3 排除矩阵（run #80/#82/#88 + owner 供日志）锁定崩溃形态：**QThreadPool 线程做文件系统枚举 + 主线程 Qt 事件循环并发**，在 macOS arm64 上与枚举 API（glob/scandir/listdir）及 PySide6 版本（6.8.3/6.11.1）均无关，故障点在 Python 帧之下的原生层——超出本仓库可修复范围，规避是唯一可控选项。扫描为单飞长任务，线程池复用无收益；Python 线程 + 队列信号是 Qt 生态标准模式。 |
| 影响范围 | `workers/qt_executor.py`（submit 开关 + threading 导入）、`presentation/controllers/scan_controller.py`（scan 传开关）、CI no-skip 守卫恢复严格计数（LIMIT-006 白名单随 skip 解除移除）、4 处 darwin skip 解除（LIMIT-006 规避生效后 macOS 全量真跑）、KNOWN_ISSUES（LIMIT-006 更新规避状态）、CHANGELOG。不变：其他任务的 QThreadPool 执行、任务层（WorkerTask/事件/取消）契约、UI 控制器。 |

---

### ADR-041 — 扫描枚举前置到主线程（LIMIT-006 仓内根治，owner 批准"功能不依赖外部"）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（owner 2026-09-13 指示"项目功能正常不能依赖外部"——LIMIT-006 处置从等待上游改为仓内根治） |
| 决策 | 目录枚举与 realpath 从扫描 worker 线程**前置到主线程**：`ScanController.scan_folder` 在提交前 `resolve` 根目录并经新用例方法 `enumerate_files` 完成枚举，条目经 `ScanAndRegisterPhotosCommand.pre_enumerated_items` 传入 worker；worker（预枚举模式）**零枚举/零 realpath syscall**（含取消 per-item resolve，run #91 的崩溃点）。CLI 与旧路径（pre_enumerated_items=None）行为不变。 |
| 理由 | D-3 排除矩阵终态：崩溃与枚举 API（3 种实现）、PySide6 版本（6.8.3/6.11.1）、线程类型（QThreadPool/Python）均无关，唯一共同必要条件 = **后台线程做 macOS 文件系统调用 + 主线程事件循环并发**（故障在 Python 帧之下原生层，见 run #80/#88/#91 三份 faulthandler 栈）。把枚举搬回主线程使该并发组合在扫描路径上不复存在。枚举成本实测 0.140s/2000 文件（主线程一次性，配状态提示可接受）。 |
| 影响范围 | `application/services/scan_and_register_photos_service.py`（`enumerate_files` 新用例方法 + execute 预枚举分支 + `_scan_and_register` resolve 开关）、`application/use_cases/scan_and_register_photos.py`（协议扩 enumerate_files）、`application/commands/scan_and_register_photos.py`（pre_enumerated_items 字段）、`presentation/controllers/scan_controller.py`（主线程前置）、`tests/`（服务/控制器/AST 守卫）、user-guide 已知问题节。不变：任务层契约（事件/取消/单飞）、CLI 行为、其他任务的线程模型。 |
| 残余风险 | worker 仍执行文件内容读取（PIL/哈希）——macOS CI 数百次运行从未在该面崩溃（崩溃仅现于枚举/realpath 系统调用）。大库枚举的主线程冻结 ≈ 70µs/文件（10 万文件 ≈ 7s），阈值已文档化，超出时分块枚举另行立项。 |

### ADR-042 — Stage C 识别入口切换为可追溯运行（多脸观测 + 重跑 + 兼容双写）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（owner 立项阶段 C；2026-09-25 实施，提交 `73657ec`/`7ec3173`/`a9f15b3`） |
| 决策 | 新增可追溯识别数据链：`recognition_runs`/`recognition_run_photos`/`recognition_run_scopes`/`face_observations`（migration `004`）+ `error_count`（`005`）；`RunRecognitionService` 逐脸写观测并按旧逻辑产出一条 PENDING `RecognitionResult` 兼容行（单脸 Top-1 语义不变，审核/归档/导出/就绪全绿）；UI 识别入口切换为 `RecognitionScopeDialog`（范围 all/selected + 脸数档位 + 仅重试失败照片），经 `RecognitionRunController`→`RunRecognitionTask` 提交；**重跑 = 新建 run**（历史保留，不覆盖人工决定）；AST 守卫测试禁止旧 `MatchPersonsController` UI 路径回接。 |
| 理由 | 阶段 C 目标"多脸检测与可重跑"要求逐脸证据可追溯；兼容双写使冻结期内既有消费方零改动（后续 E-SG 系列裁决的前提）。 |
| 影响范围 | `application/services/run_recognition_service.py`、`face_analysis_task.py`、`presentation/controllers/recognition_run_controller.py`、`views/recognition_scope_dialog.py`、`alembic/versions/004/005`、AST 守卫 `test_recognition_entry_migration.py`、生命周期回归 `test_stage_f_lifecycle.py`。 |

### ADR-043 — Stage D 聚类两段式算法与 inclusive 合并门限（≥0.4 含等号）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（owner 裁决：两段式算法 + 合并门限 ≥0.4；2026-09-25 实施 `5c3c6d2`，偏差修复 `8d4c342`） |
| 决策 | 两段式聚类：①贪心候选——观测向量按量化簇心余弦 **≥0.5** 归入候选；②complete-linkage 合并——簇间 min-pairwise 余弦 **≥0.4（含等号）** 即合并（实现初版 `>0.4` 为偏差，owner 裁决与规格 §D-2 均为 ≥，经 runtime 证明 cos=0.4 量化后误分 2 簇；修复为"扫描取严格 `>` 最大值自 -inf 起、扫描后以 `>=` 判门限"，三点边界测试钉死：0.4 合并 / 0.5 分离 / 0.400001 合并）。低质量门限默认 0.0（禁用，待 Stage F 校准质量公式）。表 `face_cluster_runs`/`face_clusters`/`face_cluster_members`（migration `006`）；重跑 = 新一代 cluster run，历史保留；输入默认 `in_selected_scope` 观测。 |
| 理由 | 两段式在贪心效率与 complete-linkage 簇质量间取平衡；inclusive 边界是 owner 明示裁决；量化（6 位小数）吸收 BLAS 末位抖动保证跨平台确定性。 |
| 影响范围 | `domain/services/face_clustering.py`、`application/services/cluster_faces_service.py`、`infrastructure/cosine_kernel.py`、`alembic/versions/006`、`tests/unit/domain/test_face_clustering_algorithm.py`、D-4 UI（人员页聚类区 + `cluster_results_dialog.py`）。 |

### ADR-044 — Stage E 配对确认与 (person, photo) 兼容语义（E-SG-5 / E-SG-6）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（owner 裁决 E-SG-6/E-SG-5；2026-09-25 实施 `ee5d7d4`，整改 `f6e70b0`） |
| 决策 | ①**E-SG-6**：兼容层与归档去重作用域 = **(person, photo)**——同一照片可同时归属多个 Person（各自持有一条 APPROVED 兼容行；`recognition_results` 无 UNIQUE(photo_id)，多行合法）；改派/解除（unassign/reassign）回撤旧人兼容投影（`remove_results_for_person_photos`）并 disable 其样本（`enabled=0`，历史保留）。②**E-SG-5**：改派后旧人样本停用，不参与后续建议。③建议顺序：sample-match（该人 enabled 样本 max cosine **≥0.40**，排除 rejected 对）优先，其次 sort_key × roster_order 一对一顺序建议；**建议永不自动写归属**，确认才生效。④样本沉淀：确认时整簇成员观测写入 `person_face_embeddings`（`UNIQUE(person_id, observation_id)` 幂等）。 |
| 理由 | 审计实证 E-P1-1（第二确认的归属在兼容层丢失 → 该照片永不按第二人归档）与 E-P1-2（改派后兼容层残留旧身份 → 归档错人）；旧"每照片一条 APPROVED"语义无法表达多归属，owner 按归档业务现实裁决为 (person, photo)。 |
| 影响范围 | `application/services/pairing_workbench_service.py`、`domain/services/pairing.py`、`sqlite_recognition_repository.py`（`remove_results_for_person_photos`）、`ArchivePlanner`（`seen_person_photo_pairs` + `has_successful_for_person`）、`alembic/versions/007`、`test_stage_e_remediation.py`。 |

### ADR-045 — 归档按稳定身份去重 + 置信度三态 + 人工身份最终化（BLK-1 / BLK-5 / D-1）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（Stage 4 冻结阻断修复 + owner 裁决落地；2026-09-28 `2823d1c`） |
| 决策 | ①**BLK-1**：`archive_records` 增 `person_id`（migration `008`，FK→people ON DELETE SET NULL + 索引；存量行按"姓名唯一命中"回填，重名保持 NULL 不猜身份）；成功态归档去重优先按稳定 person_id（同名不同人互不抑制、改名后不重复归档），无主存量行回退姓名匹配；`read_workspace_counts` archivable_count 与 planner 同口径。②**BLK-5**：`recognition_results.confidence` 放宽为可空（008 重建表并按 002 重建命名索引）——`None` = 该归属无相似度证据（位置配对/人工指派），数值 = 真实余弦（[0,1] 校验）；禁止把"无证据"写为 0.0；配对确认 sample_match 写真实余弦、ordered_suggestion/manual 写 NULL。③**D-1**：审核批准可同时写入 `person_id`（人工选择/修改/确认的身份即最终结果，使该行真正进入归档计划）；`ReviewDialog` 增身份选择器，未指定身份时显式告警不静默；批量批准的默认身份不覆盖行上已有身份；重跑识别不覆盖人工批准。 |
| 理由 | 冻结审查三项业务级阻断：同名互抑/改名重复归档（DATA_RELATION_ERROR）、"无证据"被误表达为"相似度为零"、批准后 person_id 恒 NULL 致归档永不选中；migration 008 幂等守护（列存在探测）+ downgrade 先回填 NULL 再恢复 NOT NULL，升级/回滚数据安全。 |
| 影响范围 | `alembic/versions/008`、`sqlite_archive_record_repository.py`、`sqlite_recognition_repository.py`、`archive_planner.py`/`archive_executor.py`、`domain/entities/recognition.py`、`review_recognition_service.py`、`review_dialog.py`、`test_freeze_blockers.py`（13 项回归）。 |

### ADR-046 — 匹配阈值 D-2：`>= 0.40`（含等号命中）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（owner 裁决 D-2，2026-09-28 随 `2823d1c` 统一；边界经 Stage4.2 真库实测） |
| 决策 | 人员匹配阈值判定为 `similarity >= 0.40`（**含等号**）：`DEFAULT_MATCH_THRESHOLD = 0.40`（`application/dtos/settings.py`）+ 设置边界校验 + `CosinePersonMatcher` 注入；配对建议 sample-match 规则同口径；全部文档统一 `>=` 表述（历史 `>`/`>=` 口径分裂收口）。 |
| 理由 | Stage4.2 实测三点边界：0.39 不命中 / 0.40 命中 / 0.41 命中。 |
| 影响范围 | settings DTO、`ai/similarity_matcher.py`、`domain/services/pairing.py`、文档口径；**附注**：识别侧（自动匹配）阈值边界证据仍须补入 Stage F 校准报告——与 AUD-017 方案选择一并处理（体检 F1-2 证据缺口）。 |

### ADR-047 — AUD-017 裁决：样本相似度建议走 suggested 层（Option C），`person_embeddings` 不恢复写入（Stage 11B）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（owner 裁决 2026-09-28：Option C + K-3=suggested 层；决策材料 `docs/decisions/AUD-017-person-embeddings-decision.md`） |
| 决策 | 身份建议的候选来源 = **`person_face_embeddings`（enabled=1 样本）**：建议生成经 `SuggestPairingsService.list_enabled()`（`ORDER BY person_id, created_at, id` 确定序）+ `NumpyCosineSimilarityFactory`（量化 6 位）计算成员观测 × 样本的**多样本 max 余弦**（D4），规则① `>= 0.40`（恰等命中，D-2）产出 `sample_match` 建议；样本相似度结果**仅落 suggested 层**（K-3：绝不写 confirmed、不写兼容行 person_id、不自动学习）；冷启动 ordered_suggestion 链（FaceCluster → sort_key → roster_order → 位次一对一）原样保留，两路径并存互不替代；**`person_embeddings` 不恢复任何生产写入路径**，其读路径保留为兼容链遗留（全 git 历史无写入者、候选可证恒空——真实库探针 0 行，见决策材料 §2）。维度不一致 fail-closed（kernel 拒绝混维向量——单模型 buffalo_l 下维度校验即模型身份守卫；模型版本列如未来需要另行 migration 裁决）。 |
| 理由 | Option C 正是执行计划 E-3/E-4 与开发计划 :155 的既定形态（多样本匹配、非覆盖式），消除基线 Stage3 B2 的"候选源二义"；K-3 保证人工确认是身份确认的唯一入口（与 D-1/E-SG"永不自动确认"一致）；生产链在阶段 E 已存在（规则①+`list_enabled`），本裁决将其确立为 AUD-017 的正式答案并以真实 SQLite 集成测试闭环证明（任务书 §14：禁止 stub 掩蔽空表）。 |
| 影响范围 | 零生产代码改动（能力已存在，Stage 11B 完成证明与登记）；新增 `tests/integration/test_aud017_sample_suggestion_sqlite.py`（4 项：主闭环含 disabled 排除与重复确认幂等 / 零样本冷启动 / 平分 tie-break / 维度 fail-closed）、`tests/unit/domain/test_stage_e_pairing_domain.py` 钉定 3 项、`tests/unit/infrastructure/test_cosine_kernel.py` 钉定 2 项；KNOWN_ISSUES 移除 AUD-017 条目。**边界**：识别兼容链（`run_recognition_service` 对 `person_embeddings` 的遗留读）不动——候选可证恒空故行为等价于零匹配，清除属后续清理裁决；多样本匹配的性能路径（样本量大时复用 numpy kernel）为实现期关注点。 |


### ADR-048 — 归档 FS/DB 一致性模型：Accepted Partial State + retry 幂等收敛；executor 原子复制（Stage 12D / AUD-015）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（2026-09-29，全面体检 AUD-015 整改：故障注入定性 + 最小机制修复） |
| 决策 | 归档链（Planner → Executor）的一致性模型定为 **Accepted Partial State + retry 幂等收敛**——非强一致、无自动后台对账：(1) **批量 DB 原子**（单 UoW：全部归档记录同一事务提交/回滚，review M-1 语义维持）× **非事务性 FS 复制**，二者间无分布式事务（SQLite 无法回滚已完成的 FS 副作用，禁止伪事务）；(2) **崩溃窗口 1（批级回滚）**：已复制文件成孤儿（记录全失）——重试收敛：skip 策略把"目标已存在"收敛为 SKIPPED 成功态（零重复复制）、overwrite 收敛为 ARCHIVED（重新复制）、rename 收敛为 RENAMED + dup 兄弟并存；成功态（ARCHIVED/SKIPPED/RENAMED/OVERWRITTEN）拦截再规划，FAILED/PLANNED/DRY_RUN 可重试（M-2）；(3) **崩溃窗口 2（mid-copy 半写）**：`_copy_file` 改经同目录 `.part` 临时副本 + `os.replace` 原子落位——mid-copy 崩溃只遗留 `.part` 兄弟（无害残留，同名重试复用临时路径），目标位置"存在即完整"；replace 前失败 → 单项 FAILED + `.part` 清理 → 重试收敛。修复前直接 `copy2` 到目标，半写文件 + skip 策略 = **永久锁定损坏归档**（SKIPPED 成功态拦截重新规划，无法经 overwrite 恢复——故障注入实证的非收敛窗口，本修复消除其源头）。(4) **窗口 3（DB 成功后文件外部消失）**：executor 无法产生、无主动检测——登记为已知边界，人工处置。 |
| 理由 | 故障注入实证（`test_aud015_archive_consistency.py`，真实 SQLite + 真实 FS + commit 边界崩溃注入）：窗口 1 经重试自然收敛（孤儿→SKIPPED/ARCHIVED，幂等）；窗口 2 修复前为**唯一非收敛状态**（损坏归档被标记为成功且无法重试恢复）——原子复制以 ~10 行消除该窗口源头，是覆盖实际故障窗口的最小机制；伪事务（BEGIN-copy-COMMIT）被明确否决（SQLite 不能回滚 FS 副作用）。 |
| 影响范围 | `archive_executor.py::_copy_file`（原子化，containment 检查与 rename/skip/overwrite 语义不变；符号链接目标仍被先行拒绝，`os.replace` 不穿越链接）；新增 `tests/integration/test_aud015_archive_consistency.py`（6 项：FS 失败隔离与重试收敛 / 崩溃孤儿 skip 自愈 / overwrite 重新归档 / 遗留半写锁定证据 + 原子复制新语义 / rename dup 兄弟 / 幂等）；**钉定既有行为**：RENAMED 记录保留规划名（兄弟名仅在 outcome）。 |
| 残余风险 | `.part` 兄弟残留（无害，重试复用同名路径）；窗口 3 无主动检测（外部删除需人工）；**遗留半写目标**（修复前版本产生）+ skip 锁定需人工恢复（删除记录与目标后重归档）——修复后 executor 不再产生该形态。 |

---

### ADR-049 — Application 文件访问端口化：能力端口 + DEP-072 守卫（Stage 12E / AUD-010）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（2026-09-29，全面体检 AUD-010 定性 + 端口化处置） |
| 决策 | Application 层**不得**直接文件 I/O，全部经**业务语义能力端口**：(1) 新增 `ArchiveFileStore` 端口（`path_exists` / `ensure_parent_directory` / `verify_target_containment` / `copy_atomically` / `find_available_sibling`）——`ArchiveExecutor` 决定"做什么"（冲突策略、目标路径、状态机），`FilesystemArchiveFileStore`（infrastructure/filesystem）决定"怎么做"（P2-005/M-3/M-4 containment、AUD-015 原子复制、确定性 dup 协商逐字迁移，行为零变化）；(2) 新增 `FailureListWriter` 端口 + `CsvFailureListWriter`——失败清单 CSV 渲染（UTF-8-BOM、列序）归基础设施，服务层保留行结构语义；(3) `RosterTableReader` 协议扩展 `read_bytes`——批次 file_hash 溯源经既有 reader 端口，`ParseImportDraftService` 只做 SHA-256 纯计算。**DEP-072**（新增）取代原 §17 的绝对表述：禁令落在"能力端口"而非"应用层永不触碰文件"；守卫 `test_layer_boundaries.py::test_application_has_no_direct_file_io` 逐文件 AST 断言（builtin `open`、`shutil`/`tempfile` 导入、FS 专用方法调用），盲区在测试内如实声明。 |
| 理由 | 盘点确认 application 层真实文件 I/O 恰为 3 处且全部是**业务性**（归档复制与 containment、名单批次哈希、失败清单导出），非业务性（临时文件/日志/cache）在本层为零。原 §17 属"原则正确但不可机械执行"的过度严格规则（Type B）——本项目的应用层是工作流编排层，关闭其文件访问会迫使业务能力下沉或制造无意义抽象。判定原则：端口 MUST 表达业务语义（`ArchiveFileStore` 是归档能力，非 `IFileSystem` 封套），因此未建立通用 filesystem framework；每个端口恰有一个生产实现，无 stub。 |
| 影响范围 | 新增 `application/ports/{archive_file_store,failure_list_writer}.py`、`infrastructure/filesystem/archive_file_store.py`、`infrastructure/exporters/failure_list_writer.py`；改 `archive_executor.py`（构造注入 file_store，FS 逻辑迁出）、`recognition_failure_service.py`（writer 注入）、`parse_import_draft_service.py`（hash 经 reader）、`app/services.py`（装配）、`ports/roster_table_reader.py` + `FileRosterTableReader`（read_bytes）；测试：executor/step11/aud004/aud015/stage_f 构造点更新 + 新增 `test_archive_file_store.py`（8 项契约）+ 守卫测试（负向验证已捕获注入违规）。**行为不变**：三冲突策略、dry-run、containment/symlink 防护、M-4 mtime 语义、AUD-015 原子复制与 FS/DB 一致性模型全部由既有套件证明。 |
| 残余边界 | 守卫 AST 盲区（`read_bytes`/`replace` 等同名方法在无类型信息下无法区分端口调用与文件系统调用；可伪装形态依赖评审）；刻意不拆分 `ArchiveFileStore` 为多个细粒度端口（调用方与语义一一对应，过度细分无收益）。 |

---

### ADR-050 — UseCase Protocol 使用准则：按边界需要而非按 Service 一一映射（Stage 13C-A / AUD-011）

| 字段 | 值 |
|---|---|
| 状态 | **Accepted（2026-09-29 定性；2026-09-30 Owner 决策落地 = Option C，见下「Owner 决策」段）** |
| 决策 | Application 层的 UseCase Protocol **不是**每个 service 的强制壳，而是**跨边界能力的标注机制**。事实盘点（Stage 13C-A）：11 个 use_cases 文件声明 14 个 Protocol，每个恰有一个 service 实现；其中 **11 个** 被 presentation 控制器/worker 以类型标注消费（archive 2、run_recognition 3、cluster_faces 2、import_people 2、match_persons 2、scan_and_register 2、delete_person 1、delete_photos 1、dispose_duplicates 2、review_recognition 1、settings 1），**3 个**（RegisterPhoto / ScanPhotoFolder / PruneMissingPhotos）无外部标注方——其服务为**活的**组合根能力（`ApplicationServices` 以**具体类**字段标注暴露，CLI `prune` 经该字段驱动）。测试对 Protocol 的引用近乎为零（14 个中共 2 处），说明现存 Protocol 的价值是**边界标注**而非测试替身点。因此确立准则（ARC-010）：跨 application 边界的能力需要 Protocol；仅经组合根暴露的应用内能力不需要；不得为凑齐而批量新建；已声明但仅被自身 service 继承的 Protocol 视为契约冗余候选。 |
| 理由 | 回答体检核心问题"需要所有 service 都有 Protocol 吗"——以代码事实作答：本项目是**单进程桌面应用 + 单一组合根**（`ApplicationServices` 具体类字段），没有多实现替换需求；Protocol 的真实消费者是 presentation/worker 的构造函数标注（11/14 有），其余场景由组合根的具体类型承担。不建立 36 个 Protocol（无消费者的空壳），也不删除 11 个在用 Protocol（会破坏注入边界）。 |
| 影响范围 | `architecture-rules.md` 新增 ARC-010（使用准则）；本 ADR 记录盘点事实与 3 个冗余候选的**待决变体**（删除触及 `application/__init__.py` 公开导出 = 公开 API 变更，按 Stage 13C-A §9 属 Owner 决策，本阶段不执行）。代码零变更。 |
| **Owner 决策（2026-09-30，Stage 13D-A）** | **Option C：保留三个 Protocol，降级其架构定位。** `RegisterPhotoUseCase` / `ScanPhotoFolderUseCase` / `PruneMissingPhotosUseCase` **全部保留**，不删除、不改公开导出、不改生产行为。它们的定位明确为**兼容性 / 公开 API 层面的 Protocol**——**不要求**作为 Service 的强制抽象（ARC-010 准则同样适用于它们：无跨边界消费者 → 无需 Protocol 语义背书，但**已公开导出**，删除即构成不必要的公开 API breaking change）。**理由**：三者所描述的服务是**活的组合根能力**（`ApplicationServices` 以具体类字段暴露 `register_photo` / `scan_photo_folder` / `prune_missing_photos`；CLI `prune` 经该字段驱动真实调用），Protocol 作为其**已发布的类型契约**保留有对外价值；而"零边界消费者"是**结构性事实**（presentation / workers / plugins / tests 均无标注方），**不再作为待处理删除项**。决策门**关闭**。复核事实（HEAD `36a1d0f`）：三 Protocol 存在、公开导出 3/3 在位、消费者 0、组合根能力与 CLI 路径正常、服务实现类仍继承各自 Protocol。 |

### ADR-051 — 移除空置的 `common/` 包；MainWindow 职责边界成文（Stage 13C-A / AUD-013）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（2026-09-29） |
| 决策 | ①**移除 `src/photo_archiver/common/`**：该包为 1 行 docstring 空骨架，`src/`/`tests/`/`main.py` 零导入（仅分层守卫的命名空间黑名单提及）；其声明职责（constants/helpers/shared exceptions/base classes/validators）要么未用、要么已有更合适的归属（`domain/exceptions.py`、`infrastructure/logging/`、`application/dtos/`）。同步移除 DEP §3 模块树与 §4 矩阵条目、ARC-008 改写为"Removed"、project-structure 标注移除。②**`main_window.py` 不做代码拆分**（1578 行 / 63 方法：事件路由 29、UI 构建 8、状态同步 5、其余为编排辅助）：职责已外移——窗口只做装配/路由/状态同步，service 调用均为编排，业务规则、文件与 SQL 触点为零。确立 ARC-011 职责边界规则，防止后续以"文件大"为由机械重构或把业务逻辑塞回窗口。 |
| 理由 | 空批准包会招致死代码或错置工具（任务书 §11 原则：宁可删除空目录也不添加无意义 utility）；行数不是拆分理由（§14），Qt 惯例中事件路由本就是 MainWindow 职责。 |
| 影响范围 | 删除 1 个包目录；4 份规则/结构文档更新（architecture-rules、dependency-rules、project-structure、本 ADR）；守卫测试 `test_layer_boundaries.py` 的 domain 黑名单**保留** `photo_archiver.common`（命名空间级预防禁令，模块若重建则域层仍禁引）。代码行为零变更。 |

---

### ADR-052 — 数据生命周期与状态机职责定案：人员删除语义、status 枚举归属、`file_hash` 用途（Stage 13C-B / AUD-018）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（2026-09-29，体检 AUD-018 三子项逐项定性；登记**既有**设计而非新决策） |
| 决策 | **A 人员删除的数据生命周期**（FK 矩阵，登记既有设计）：`recognition_results.person_id` 与 `archive_records.person_id` = **SET NULL**——这两类记录描述的是**照片**（照片独立于人员存在），删人后照片与归档事实保留、身份匿名化；`cluster_person_assignments.person_id` 与 `person_face_embeddings.person_id`（及历史 `person_embeddings`）= **CASCADE**——映射与样本**从属于**该人员（无独立生命期；样本是"这个人的人脸模板"，人没了模板无意义；配对决策指向已删除的人会悬空）。二者不对称是**有意设计**（与 `docs/business-baseline/Stage1_BusinessFacts.md` §删除人员 记载一致），不改 migration。**B status 合法性归属**：新增表（003/004/006/007）在 DB 层有 CHECK，早期表（`recognition_results`/`archive_records`，002/008）没有——裁定 **域枚举是唯一状态机**（实体构造期/状态迁移处校验，仓储签名类型化，如 `update_status(status: MatchStatus)` 写 `status.value`），**不**为冻结表补 DB CHECK（迁移重建 + 生产数据集合核验成本，换不到真实缺陷防护）。补齐唯一缺口：`RecognitionResult.__post_init__` 增加 status 类型校验（此前 dataclass 不强制类型，可构造非法状态直达 DB），与 `ArchiveRecord.status` 同口径。**C `import_batches.file_hash`**：类型 D（审计/溯源 metadata）——记录"本批人员来自哪个文件内容"（`ParseImportDraftService` 计算 SHA-256；回填批次写 `backfill:<ts>` 合成值），读取方仅实体水合（`sqlite_import_batch_repository:18`），**不做去重键**（同一文件经编辑后重导是合法业务行为，按内容去重会静默跳过合法重导）——保留字段、明确用途，**不删除**。 |
| 理由 | 消除三处"看起来不一致其实有意"的模型歧义：A 的级联差异对应"记录 vs 从属物"的本质差异；B 的 CHECK 差异对应"新增表更严"的历史演进，防护责任在域枚举（唯一可写路径）；C 的不读取是**设计**而非缺失——去重键需要额外的查询/比较路径与"内容相同但用户想重导"的业务裁决，属功能而非卫生。 |
| 影响范围 | `domain/entities/recognition.py`（status 构造期类型校验）；新增 `tests/unit/application/test_aud016_018_contracts.py`（018-B 2 项）；迁移零变更、Schema 零变更。 |

---

### ADR-053 — SQLite 连接生命周期假设与审核队列错误语义（Stage 13C-C / AUD-024 + AUD-025）

| 字段 | 值 |
|---|---|
| 状态 | Accepted（2026-09-29；AUD-024 复核定性 + AUD-025 前提证伪与契约固化） |
| 决策 | **连接生命周期**：`UnitOfWork.transaction()` 与 backup/integrity 路径**显式 close**（``finally``，提交/回滚/异常三路径均覆盖）；per-call 路径（``SQLiteConnectionProvider.connect()``）的连接**关闭依赖 CPython 引用计数**（项目钉定 3.11）——每个仓储方法以 ``with … as connection`` 使用、不跨方法持有、不缓存、不跨线程共享（provider 为 thread-local），方法返回即释放。**判定：ACCEPTED-RISK**（有界、非泄漏）——不机械插入 ``close()``；契约以行为方式钉死：连接唯一性、UoW 三路径 close、嵌套事务拒绝、**异常后不滞留写锁**（真实 UNIQUE 冲突 → 后续写入成功）。异常路径下 traceback 可短暂持有帧引用使关闭延后至 GC——有界。跨解释器（无引用计数）保证不在本项目范围内（§21 决策门未触发：项目钉定 CPython 3.11）。**审核队列错误语义**：队列读取链（``ReviewDialog._refresh_list`` → ``ReviewController.list_pending`` → 仓储）**无 blanket catch**——读失败向上冒泡（构造期或刷新期），绝不退化为"暂无待审核"；空态仅表示**成功的空查询**。D-1 身份选择器读取（``_available_persons``）保留**文档化降级**（失败 → 选择器为空），其失败后果由既有"未指定身份"显式告警路径覆盖（批准仍可继续，告警不静默）——是否为其增加独立错误提示属**产品取舍**（不阻塞本项）。 |
| 理由 | AUD-024 复核：体检"依赖隐式关闭"描述准确但未评估真实风险——实测无共享、无缓存、无跨调用持有，且三种非仓储路径已显式 close；剩余风险仅是 CPython 实现依赖（有界）。AUD-025 复核：体检所指吞错点（``review_dialog.py:304-317``）实为**身份选择器**读取，不是审核队列；队列读取本身从不吞错——故以契约测试固化该事实（ERROR≠EMPTY + 故障恢复），并把选择器降级明确记为设计而非缺陷。 |
| 影响范围 | 生产代码零变更；新增 `tests/unit/infrastructure/test_aud024_connection_lifecycle.py`（7 项：spy 观测 UoW commit/rollback close、嵌套拒绝、per-call 唯一性、UNIQUE 冲突后无写锁、空事务 close）与 `tests/unit/presentation/test_aud025_review_error_semantics.py`（4 项：真实库空态 / 真实读失败冒泡 / 故障恢复 / 真实读路径对照）。 |

---
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

