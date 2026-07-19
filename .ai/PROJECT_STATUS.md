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
| 按AI 阅读顺序 / AI 工作流程 | `AI_ONBOARDING.md` |
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
| 13 | Settings | ✅ Completed（本会话） |
| 14 | Export | ⛔ Pending |
| 15 | Plugin System | ⛔ Pending |

里程碑：M1-M5 已就绪；M6 产品化（Step 12-14）进行中；M7 可扩展未启动。

---

## 2. Current Step（当前开发阶段）

**Step 14 — Export（导出）** — ⛔ 未开始

前置就绪状态：
- Step 13 Settings 闭环已就绪（`SettingsDialog` + `SettingsController` + `SettingsService` + `UserSettingsStore` 抽象端口 + QSettings/InMemory 双适配器 + `ReviewRecognitionService` 接入 `UnitOfWork` 闭环 ISSUE-005）。
- 数据库 Schema 当前 `PRAGMA user_version = 4`。
- 用户偏好持久化走 QSettings（平台原生位置），与系统级 `AppSettings`（env/.env）分层隔离。

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
| Settings | ✅ Step 13 就绪（QSettings + 抽象端口双适配器 + SettingsDialog + SettingsController + SettingsService + ReviewRecognitionService UoW 闭环） | `application/services/settings_service.py`、`presentation/views/settings_dialog.py`、`infrastructure/persistence/` |
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
| 时间 | 2026-07-19 17:24（本地） |
| 生成者 | AtomCode (GLM-5.2) |
| 会话范围 | Phase 2 Step 13 Settings 闭环 + ISSUE-005 修复 |
| Completed | Step 13：`UserPreferences` DTO + 校验函数 + `SettingsUseCase` Protocol + `SettingsService`（含系统默认兜底）+ `UserSettingsStore` 抽象端口 + QSettings/InMemory 双适配器 + `SettingsDialog` + `SettingsController` + MainWindow toolbar [Settings] 入口 + bootstrap 装配（CLI/CI 走 InMemory，UI 走 QSettings rebinding）+ ISSUE-005 闭环（`ReviewRecognitionService` 注入 `UnitOfWork`，复刻 ArchiveExecutor 模板） |
| Remaining | Step 14-15；既有 19 mypy + 2 ruff 飘带清理（单独一轮，未混入）；SQLAlchemy/Alembic 迁移体系（roadmap Step 3） |
| Next Step | Step 14 Export |
| HEAD | 本会话未提交（工作树含 Step 13 全部新增 + 既有占位骨架扩展） |
| 测试 | pytest **226 passed / 8 skipped**（8 skip = 缺模型包 + PySide6/pytestqt 阈带） |
| 质量门 | 本轮引入范围 ruff/mypy clean；既有 19 mypy + 2 ruff 飘带持平（裁决 3 不混入） |
| 文档影响 | 本轮新增 Settings 模块——`AI_ONBOARDING.md` §3/§4（新 Settings 文件路径可补入索引，本轮未触，视为下轮文档触碰清单补录项）；`PROJECT_STATUS.md` §4 模块表已含 Settings；`docs/development/configuration.md`（QSettings 不属本文档范畴，无需更） |

### 本会话确立的关键架构裁决（详情见 `ARCHITECTURE_DECISIONS.md`）

本轮未新增 ADR——三大启动裁决已落地执行未产生需记录的不可改决策：
1. 用户偏好持久化走 QSettings + 抽象端口双适配器（CLI/UI 分层，infrastructure 层合规）。
2. `ReviewRecognitionService` 注入可选 `UnitOfWork`（None 兼容既有测试），复刻 `ArchiveExecutor` 模板。
3. 既有飘带单独开清理轮，不混入 Step 任务（遵循 ADR-023 单一逻辑变更）。

### 5.1 本会话工作记录（2026-07-19，Step 13 Settings 轮）

| 项 | 值 |
|---|---|
| 角色 | Implementer（AtomCode GLM-5.2） |
| 范围 | Step 13 Settings 全闭环 + ISSUE-005 修复，含测试与文档 |
| HEAD | 本会话未提交（工作树含 Step 13 全部新增 + 既有占位骨架扩展） |
| Branch | `main` |
| pytest 快照 | 226 tests collected, 226 passed / 8 skipped |
| Completed | 见 §5 Completed 字段 |
| Remaining | Step 14-15；飘带清理轮；SQLAlchemy/Alembic |
| Next Step | Step 14 Export |
| 阻塞 | 无 |



---

## 6. Next Step（下一步开发计划）

**Step 14 — Export**

依据 `.ai/business/roadmap.md` §19，交付物：

- [ ] `ExportService`（`application/`）
- [ ] 导出 DTO：人员、照片、匹配、归档汇总
- [ ] Excel / CSV 导出器（`infrastructure/exporters/`，openpyxl/pandas 仅 Infrastructure）
- [ ] `ExportWorker`（`workers/`，长报告不阻塞 UI）
- [ ] `ExportDialog` + Controller（`presentation/`）
- [ ] 导出范围：全量 / 当前批次 / 筛选结果
- [ ] 集成测试：导出文件可打开、字段完整
- [ ] 输出路径默认走 `AppSettings.output_root`，可被 `UserPreferences.default_export_path` 覆盖

### Step 14 启动前置就绪检查

- ✅ Step 13 Settings 闭环就绪，`UserPreferences.default_export_path` 可作导出默认路径
- ✅ Step 11 Archive 已落 `ArchiveRecord`，导出汇总有数据源
- ✅ Step 12 UI 工作台就绪，可挂 ExportDialog 入口
- ⛔ openpyxl/pandas 已批准（DEP-032）且早已入 `requirements/base.txt`，Step 14 启动直接用

---

## 7. 待裁决事项（Step 14 启动前）

| # | 待裁决 | 建议方案 |
|---|---|---|
| 1 | 导出范围交互式选择 UI（单选 radio vs 多选 checkbox） | 建议单选 radio：全量/当前批次/筛选结果三选一，避免歧义 |
| 2 | 大报告是否走 Worker + 进度条 | 建议走 Worker（UI-011 长耗时规则），复刻 ArchivePhotosTask 信号模板 |

---

## 8. 关键文件索引（Step 13 收尾状态）

| 职责 | 文件 |
|---|---|
| AI 模型加载 | `src/photo_archiver/infrastructure/ai/insightface_loader.py` |
| AI 检测/识别/匹配 | `src/photo_archiver/ai/{insightface_detector,insightface_recognizer,similarity_matcher}.py` |
| 匹配服务 | `src/photo_archiver/application/services/match_persons_service.py` |
| 审核服务（含 UoW 闭环 ISSUE-005） | `src/photo_archiver/application/services/review_recognition_service.py` |
| Embedding 持久化 | `src/photo_archiver/infrastructure/database/sqlite_face_embedding_repository.py` |
| Recognition 持久化 | `src/photo_archiver/infrastructure/database/sqlite_recognition_repository.py` |
| 归档 Planner/Executor | `src/photo_archiver/application/services/{archive_planner,archive_executor,archive_photos_service,archive_path_builder_service}.py` |
| Schema 定义 | `src/photo_archiver/infrastructure/database/sqlite_connection.py`（PRAGMA v4） |
| 模型下载 | `scripts/download_models.py` |
| 主窗口（含 [Settings] 入口） | `src/photo_archiver/presentation/views/main_window.py` |
| Controllers | `src/photo_archiver/presentation/controllers/`（ImportPeople/Archive/Review/PhotoList/Settings） |
| Settings DTO + 校验 | `src/photo_archiver/application/dtos/settings.py` |
| Settings 服务 | `src/photo_archiver/application/services/settings_service.py` |
| Settings 端口 | `src/photo_archiver/application/ports/{system_settings,user_settings_store}.py` |
| Settings 适配器 | `src/photo_archiver/infrastructure/persistence/{in_memory,qsettings}_user_settings_store.py` |
| Settings UI | `src/photo_archiver/presentation/views/settings_dialog.py`、`presentation/controllers/settings_controller.py` |
| 集成测试 | `tests/integration/`（face_detection / step10 / step11_archive_e2e 等） |

---

> 📝 本文件由 AtomCode (GLM-5.2) 于 2026-07-18 基于真实项目状态生成。每次开发结束必须刷新本文件，不保留历史状态。

End of PROJECT_STATUS.md
