# ARCHITECTURE_DECISIONS.md — PhotoArchiver 架构决策记录（ADR Register）

> **本文档是已确认架构决策的唯一寄存器（Architecture Decision Register）。**
>
> 回答：**"哪些架构决策已经确定，AI 不得重新设计？"**
>
> 这是整个 AI Runtime Context 中最重要的稳定文档之一。长期保留，不会因版本变化删除。
>
> Version: 1.0.0 ｜ Status: Stable ｜ Last Updated: 2026-07-18

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

### ADR-005 — SQLAlchemy/Alembic 延后，当前用 sqlite3 + PRAGMA user_version

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
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
| 决策 | 归档流程拆为三段：`ArchivePlanner`（生成 `ArchivePlan`）→ `ArchiveExecutor`（执行 Plan）。CLI/UI/测试共用同一套归档计划。`--dry-run` 旗标在 Executor 内落 DRY_RUN 状态 + `ArchiveRecord` �库，可预审整批归档计划。 |
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

### ADR-024 — 数据库 Schema 版本管理走 PRAGMA user_version

| 字段 | 值 |
|---|---|
| 状态 | Accepted |
| 决策 | Schema 版本由 `PRAGMA user_version` 单调递增管理。当前 v4。每次 Schema 变更 bump 版本号并在 `sqlite_connection.py` 初始化逻辑中处理升级。 |
| 理由 | 在 SQLAlchemy/Alembic 延后（ADR-005）期间需要轻量版本管理。 |
| 影响范围 | `infrastructure/database/sqlite_connection.py` |

---

## 已裁决的规则/文档冲突（已在代码/规则中执行）

> 权威审计报告：`.ai/Consistency-Audit-2026-07-13.md`。本节仅列已裁决并执行的冲突处置。

| ID | 冲突 | 裁决 | 状态 |
|---|---|---|---|
| R-1 | Workers 层导入 `PySide6.QtCore` vs DEP-040 依赖矩阵未授权 | 更新 DEP-040 + WRK-002，允许 `PySide6.QtCore`（线程原语 only） | ✅ 已执行 |
| R-2 | SQLite 代码在 `infrastructure/repositories/` vs `architecture-rules.md` §14 要求 `infrastructure/database/` | 迁移至 `infrastructure/database/` | ✅ 已执行 |
| R-3 | COD-005 行宽 88 vs `pyproject.toml` 行宽 100 | 统一为 100 | ✅ 已执行 |
| R-4 (C-1) | ARC-008 §8 vs §14 SQLite 位置表述不一 | §8 加 SQLite 例外条款 | ✅ 已执行 |
| R-5 (C-2) | `pydantic` 标 "if introduced" 但已投入使用 | 升为正式批准，补入 ai-rules §3 | ✅ 已执行 |
| R-6 (C-4) | 6 项库（Pillow/SQLAlchemy/alembic/watchdog/pytest-qt/ONNX）未进 §13/§3 | 补入并标注层归属 | ✅ 已执行 |
| R-7 (C-5) | `architecture-rules.md` §18 Logging Rules 允诺 `common/logging/` vs DEP-071 禁 common 导第三方 | 删除 `common/logging/` 选项 | ✅ 已执行 |

---

## 状态约定

- **Accepted**：已确认并落地，AI 必须遵守，不得重新设计。
- **Proposed**：提议中，未落地，AI 不得假设其生效。
- **Superseded**：被后续 ADR 取代，保留历史但不再生效（标注被谁取代）。
- **Deprecated**：废弃，不再生效。

---

> 📝 本文件由 AtomCode (GLM-5.2) 于 2026-07-18 基于真实项目决策记录生成。只有真正产生新的架构裁决时更新；不记录 Bug/TODO/未确定方案。

End of ARCHITECTURE_DECISIONS.md

