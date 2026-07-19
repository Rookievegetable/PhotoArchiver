# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**"项目现在开发到哪里了？"**
>
> 这是唯一允许频繁修改的 AI 文档。每次开发结束必须更新。历史状态不保留——永远只有当前状态。
>
> Version: 1.0.0 ｜ Last Updated: 2026-07-18 ｜ Status: Live

---

## ⚠️ 本文档不是什么

| 不是 | 这些应在别处找 |
|---|---|
| 架构决策 / ADR / 依赖规则 / 编码规则 | `ARCHITECTURE_DECISIONS.md` |
| 当前 Bug / 技术债 / 风险 / workaround | `KNOWN_ISSUES.md` |
| �AI 阅读顺序 / AI 工作流程 | `AI_ONBOARDING.md` |
| Bug 原因分析 / 长篇历史记录 / 聊天记录 | 不保留 |

---

## 1. Roadmap（开发路线图概览）

权威 15 步路线图：`.ai/business/roadmap.md`。本节仅维护进度状态。

| Step | 名称 | 状态 |
|------|------|----------|
| 0.5 | Walking Skeleton | ✅ Completed |
| 1 | Logging | ✅ Completed |
| 2 | Configuration | ✅ Completed |
| 3 | Database | ✅ Completed（SQLAlchemy/Alembic 延后，当前 sqlite3 + PRAGMA user_version） |
| 4 | Domain Model | ✅ Completed |
| 5 | Excel Import | ✅ Completed |
| 6 | Folder Scanner | ✅ Completed |
| 7 | Thumbnail Generator | ✅ Completed（上一会话 `4d48a5c`） |
| 8 | Face Detection | ✅ Completed（`8d245ab`） |
| 9 | Face Recognition | ✅ Completed（`75a865d`） |
| 10 | Matching Engine | ✅ Completed（`947b428`） |
| 11 | Archive Generator | ✅ Completed（本会话） |
| 12 | Main UI | ✅ Completed（本会话，三轮 Review 修复落 `03f4395`） |
| 13 | Settings | ⛔ Pending |
| 14 | Export | ⛔ Pending |
| 15 | Plugin System | ⛔ Pending |

里程碑：M1-M5 已就绪；M6 产品化（Step 12-14）进行中；M7 可扩展未启动。

---

## 2. Current Step（当前开发阶段）

**Step 13 — Settings（设置与偏好）** — ⛔ 未开始

前置就绪状态：
- Step 12 完整 UI 工作台已就绪（MainWindow 重构 + 4 controller + ArchivePhotosTask + ArchivePreviewDialog）。
- `AppSettings`（pydantic-settings）系统配置就绪，但**用户偏好持久化未建**。
- 数据库 Schema 当前 `PRAGMA user_version = 4`。

---

## 3. Current Goal（当前阶段最终目标）

完成 Step 13-15，达成 M6 产品化与 M7 可扩展里程碑：

- Step 13：`SettingsDialog` + `SettingsController` + `SettingsService` + 用户偏好持久化（QSettings 或 DB/配置文件），可配项含主题、语言（预留）、默认导入/导出路径、识别阈值、MAX_WORKERS。
- Step 14：`ExportService` + Excel/CSV 导出器 + `ExportWorker` + `ExportDialog`，导出范围全量/当前批次/筛选结果。
- Step 15：插件接口定义 + 发现/加载机制 + 生命周期管理 + 示例插件。

详见 `.ai/business/roadmap.md` §18-§20。

---

## 4. Current Modules（当前模块状态）

| 模块 | 状态 | 关键文件 |
|---|---|---|
| Logging | ✅ Step 1 就绪 | `infrastructure/logging/configuration.py` |
| Configuration | ✅ Step 2 就绪（系统配置）；用户偏好 ⛔ 未建 | `infrastructure/config/settings.py`（`AppSettings`） |
| Database | ✅ Step 3 就绪（sqlite3 + PRAGMA v4）；SQLAlchemy/Alembic 延后 | `infrastructure/database/sqlite_connection.py` |
| Domain | ✅ Step 4 + 后续迭代就绪 | `domain/{entities,value_objects,repositories}/` |
| Import | ✅ Step 5 就绪（TXT + Excel） | `infrastructure/importers/`、`application/services/import_person_service.py` |
| Scan | ✅ Step 6 就绪 | `application/services/scan_folder_service.py`、`infrastructure/filesystem/` |
| Thumbnail | ✅ Step 7 就绪 | `application/services/thumbnail_service.py`、`infrastructure/image/` |
| Recognition | ✅ Step 8-10 就绪（InsightFace detect/recognize/match + Review） | `ai/`、`infrastructure/ai/insightface_loader.py`、`application/services/{match_persons,review_recognition}_service.py` |
| Archive | ✅ Step 11 就绪（Planner→Plan→Executor + dry-run + captured_at） | `application/services/{archive_planner,archive_executor,archive_photos_service,archive_path_builder_service}.py` |
| UI | ✅ Step 12 就绪（MainWindow + 4 controller + ArchivePhotosTask + ArchivePreviewDialog） | `presentation/views/main_window.py`、`presentation/controllers/` |
| Settings | ⛔ Step 13 未开始 | — |
| Export | ⛔ Step 14 未开始 | — |
| Plugins | ⛔ Step 15 未开始 | — |

### 数据库 Schema 版本

`PRAGMA user_version = 4`，含表：`people`、`folders`、`photos`（含 `captured_at` 列）、`recognition_results`、`person_embeddings`、`archive_records`。

### 依赖状态

`requirements/base.txt` 已含 `insightface==1.0.1` + `onnxruntime==1.27.0`（Step 9 落地，ADR-012）。`requirements/ai.txt` 已改造为纯 AI 扩展依赖挂载点（保留 `-r base.txt`，清空与 base 冲突的旧版本行，无额外条目）。SQLAlchemy/Alembic 保留（审计 C-7 决策，注释已标）。

---

## 5. Last Session（最近一次开发记录）

> 用于 AI Session 交接。每次开发结束刷新本段，不保留历史。

| 项 | 值 |
|---|---|
| 时间 | 2026-07-17 18:12（本地） |
| 生成者 | AtomCode (GLM-5.2) |
| 会话范围 | Phase 2 Step 8-10 + 三轮 Review + P0-P3 修复 + Step 11-12 实现 |
| Completed | Step 8-10（AI 检测/识别/匹配 + Review）；Step 11（归档闭环）；Step 12（完整 UI 工作台）；三轮 Review 修复；P0-P3 问题清单核验与修复 |
| Remaining | Step 13-15；既有 19 mypy + 2 ruff 飘带清理；SQLAlchemy/Alembic 迁移体系（roadmap Step 3） |
| Next Step | Step 13 Settings |
| HEAD | `03f4395`（Step 12 三轮 Review 修复完成），工作树干净 |
| 测试 | pytest **200 passed / 8 skipped**（8 skip = 缺模型包 + PySide6/pytestqt 阘带） |
| 质量门 | 本轮引入范围 ruff/mypy clean；既有 19 mypy + 2 ruff 阘带持平（交接 §6.3 决策不顺带修） |

### 本会话确立的关键架构裁决（详情见 `ARCHITECTURE_DECISIONS.md`）

1. `ai/` 层职责拆分：检测/识别/匹配；`infrastructure/ai/InsightFaceLoader` 持模型加载。
2. `FaceEmbedding` 持 tuple 不持 numpy（Domain 零框架依赖）。
3. Embedding 序列化用 JSON 非 pickle（SEC-030）。
4. 匹配策略固定 1:N Top-1（`max(boxes, key=confidence)`）。
5. `MatchResult.box` 字段 `FaceBox | None`（无人脸时 box=None）。
6. `update_status` 返回 int（受影响行数）。
7. `ensure_runtime_directories` 不建 `model_path`。
8. `ArchivePlanner` → `ArchivePlan` → `ArchiveExecutor` 三段拆分；CLI/UI/测试共用同一套归档计划。
9. 新增 `Photo.captured_at` + `PhotoMetadata.captured_at` 领域字段，由 `PillowPhotoMetadataReader` 在导入阶段统一填充（EXIF DateTimeOriginal → mtime 链式降级），Archive 只消费领域数据。
10. 新增独立 `AppSettings.archive_root` + `archive_conflict_strategy`（默认 skip）。

### 5.1 本会话工作记录（2026-07-18，Tech Lead 文档治理轮）

| 项 | 值 |
|---|---|
| 角色 | Tech Lead（AtomCode GLM-5.2） |
| �围 | 文档体系治理，不改源码 |
| HEAD | `ab523d2`（本会话开始时；上一会话末为 `03f4395`，已 commit 为 `ab523d2` docs(handoff)） |
| Branch | `main` |
| pytest 快照 | 208 tests collected（本轮未跑全量，未引入源码改动） |
| Completed | 建立 AI Runtime Context 四文档体系（上一轮）；新建 `.ai/DOCUMENT_INDEX.md` 文档导航 SSOT；改造 `requirements/ai.txt` 为纯扩展挂载点（清与 base 冲突的版本行）；7 个旧体系文档加 Deprecated banner（根 `AI_ONBOARDING.md` + `.ai/{START_HERE,PROJECT_CONTEXT,TASK_WORKFLOW,README,Session-Handoff-2026-07-17,Consistency-Audit-2026-07-13}.md`）；`AI_ONBOARDING.md` 新增 §13 Documentation Status；过期信息修正（`docs/architecture/overview.md` §6/§7、`docs/development/configuration.md` §2、`.ai/business/roadmap.md` Step 3、`README.md` 待实现列表 + AI 协作说明段） |
| Remaining | Step 13-15；既有 19 mypy + 2 ruff 阘带清理；SQLAlchemy/Alembic 迁移体系；5 处规则 SSOT 收敛（D-1~D-5，延后）；11 个 Placeholder 占位文档处置（延后） |
| Next Step | Step 13 Settings（待裁决 3 项见 §7） |
| 阻塞 | 无（文档治理轮完成，可进入 Step 13 裁决） |

**本会话关键裁决**：确立 `.ai/DOCUMENT_INDEX.md` 为文档体系结构 SSOT（已回答文档治理四问，见该文件 §0）。

---

## 6. Next Step（下一步开发计划）

**Step 13 — Settings**

依据 `.ai/business/roadmap.md` §18，交付物：

- [ ] `SettingsDialog` + `SettingsController`（`presentation/`）
- [ ] 用户偏好持久化（QSettings 或 DB / 配置文件）
- [ ] 可配置项：主题、语言（预留 i18n）、默认导入/导出路径、识别阈值、`MAX_WORKERS`
- [ ] `SettingsService`（`application/`）
- [ ] 修改后热生效或提示重启策略（文档化）
- [ ] 单元测试：读写 settings；UI 测试：保存/取消
- [ ] 与 Step 2 系统配置区分：系统 env vs 用户偏好
- [ ] `ReviewRecognitionService` 接入 `UnitOfWork` 事务边界（Step 12 遗留技术债）

### Step 13 启动前置就绪检查

- ✅ Step 12 UI 工作台就绪，可挂 SettingsDialog 入口
- ✅ `AppSettings`（pydantic-settings）系统配置已就绪
- ⛔ 用户偏好存储未建（需裁决：QSettings vs DB vs 配置文件）
- ⛔ `ReviewRecognitionService` 事务边界未补（建议本步一并接入）

---

## 7. 待裁决事项（Step 13 启动前）

| # | 待裁决 | 建议方案 |
|---|---|---|
| 1 | 用户偏好持久化机制：QSettings vs DB 表 vs JSON 配置文件 | QSettings（PySide6 原生，跨平台，无需额外 Schema），键名走命名常量 |
| 2 | `ReviewRecognitionService` 事务边界是否本轮补 | 建议 Step 13 接入 UI 审核流时一并补 `UnitOfWork`（与 Archive 看齐） |
| 3 | 既有 19 mypy + 2 ruff 飘带是否本轮顺带清理 | 建议单独开一轮清理，不混入 Step 13 |

---

## 8. 关键文件索引（Step 12 收尾状态）

| 职责 | 文件 |
|---|---|
| AI 模型加载 | `src/photo_archiver/infrastructure/ai/insightface_loader.py` |
| AI 检测/识别/匹配 | `src/photo_archiver/ai/{insightface_detector,insightface_recognizer,similarity_matcher}.py` |
| 匹配服务 | `src/photo_archiver/application/services/match_persons_service.py` |
| 审核服务 | `src/photo_archiver/application/services/review_recognition_service.py` |
| Embedding 持久化 | `src/photo_archiver/infrastructure/database/sqlite_face_embedding_repository.py` |
| Recognition 持久化 | `src/photo_archiver/infrastructure/database/sqlite_recognition_repository.py` |
| 归档 Planner/Executor | `src/photo_archiver/application/services/{archive_planner,archive_executor,archive_photos_service,archive_path_builder_service}.py` |
| Schema 定义 | `src/photo_archiver/infrastructure/database/sqlite_connection.py`（PRAGMA v4） |
| 模型下载 | `scripts/download_models.py` |
| 主窗口 | `src/photo_archiver/presentation/views/main_window.py` |
| Controllers | `src/photo_archiver/presentation/controllers/`（ImportPeople/Archive/Review/PhotoList） |
| 集成测试 | `tests/integration/`（face_detection / step10 / step11_archive_e2e 等） |

---

> 📝 本文件由 AtomCode (GLM-5.2) 于 2026-07-18 基于真实项目状态生成。每次开发结束必须刷新本文件，不保留历史状态。

End of PROJECT_STATUS.md
