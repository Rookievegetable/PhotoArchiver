# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**"项目现在开发到哪里了？"**
>
> 这是唯一允许频繁修改的 AI 文档。每次开发结束必须更新。历史状态不保留——永远只有当前状态。
>
> Version: 1.2.0 ｜ Last Updated: 2026-07-24 ｜ Status: Live

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
| 14 | Export | ✅ Completed（本会话） |
| 15 | Plugin System | ✅ Completed（本会话） |

里程碑：M1-M5 已就绪；M6 产品化（Step 12-14）进行中；M7 可扩展未启动。

---

## 2. Current Step（当前开发阶段）

**Phase 2 产品化里程碑 M6 已全部完成。**

所有 Step 0.5-15 均已实现。下一阶段：飘带清理轮（23 mypy + 4 ruff）+ SQLAlchemy/Alembic 迁移体系。

前置就绪状态：
- Step 15 Plugin System 已完成（Plugin interface + loader + example plugin + MainWindow 注册 + 插件开发指南 + 单元测试 6 条）。
- 数据库 Schema 当前 `PRAGMA user_version = 4`。

---

## 3. Current Goal（当前阶段最终目标）

完成 Step 13-15，达成 M6 产品化与 M7 可扩展里程碑：

- Step 13：`SettingsDialog` + `SettingsController` + `SettingsService` + 用户偏好持久化（QSettings 或 DB/配置文件），可配项含主题、语言（预留）、默认导入/导出路径、识别阈值、MAX_WORKERS。✅ 已完成
- Step 14：`ExportService` + Excel/CSV 导出器 + `ExportWorker` + `ExportDialog`，导出范围全量/当前批次/筛选结果。✅ 已完成
- Step 15：插件接口定义 + 发现/加载机制 + 生命周期管理 + 示例插件。⛔ 待完成

详见 `.ai/business/roadmap.md` §18-§20。

---

## 4. Current Modules（当前模块状态）

| 模块 | 状态 | 关键文件 |
|---|---|---|
| Logging | ✅ Step 1 就绪 | `infrastructure/logging/configuration.py` |
| Configuration | ✅ Step 2 就绪（系统配置 `AppSettings`）+ Step 13 用户偏好闭环（`UserPreferences` + `UserSettingsStore` 抽象端口 + QSettings/InMemory 双适配器） | `infrastructure/config/settings.py`（`AppSettings`）、`application/dtos/settings.py`、`infrastructure/persistence/{in_memory,qsettings}_user_settings_store.py` |
| Database | ✅ Step 3 就绪（sqlite3 + PRAGMA v4）；SQLAlchemy/Alembic 延后 | `infrastructure/database/sqlite_connection.py` |
| Domain | ✅ Step 4 + 后续迭代就绪 | `domain/{entities,value_objects,repositories}/` |
| Import | ✅ Step 5 就绪（TXT + Excel） | `infrastructure/importers/`、`application/services/import_person_service.py` |
| Scan | ✅ Step 6 就绪 | `application/services/scan_folder_service.py`、`infrastructure/filesystem/` |
| Thumbnail | ✅ Step 7 就绪 | `application/services/thumbnail_service.py`、`infrastructure/image/` |
| Recognition | ✅ Step 8-10 就绪（InsightFace detect/recognize/match + Review） | `ai/`、`infrastructure/ai/insightface_loader.py`、`application/services/{match_persons,review_recognition}_service.py` |
| Archive | ✅ Step 11 就绪（Planner→Plan→Executor + dry-run + captured_at） | `application/services/{archive_planner,archive_executor,archive_photos_service,archive_path_builder_service}.py` |
| UI | ✅ Step 12 就绪（MainWindow + 4 controller + ArchivePhotosTask + ArchivePreviewDialog + ReviewDialog） | `presentation/views/{main_window,review_dialog}.py`、`presentation/controllers/` |
| Settings | ✅ Step 13 就绪（QSettings + 抽象端口双适配器 + SettingsDialog + SettingsController + SettingsService + ReviewRecognitionService UoW 闭环） | `application/services/settings_service.py`、`presentation/views/settings_dialog.py`、`infrastructure/persistence/` |
| Export | ✅ Step 14 就绪（ExportService + Excel/CSV exporter + ExportWorker + ExportDialog + Controller） | `application/services/export_service.py`、`infrastructure/exporters/{excel_exporter,csv_exporter}.py`、`workers/export_task.py`、`presentation/{controllers/export_controller,views/export_dialog}.py` |
| Plugins | ✅ Step 15 就绪（Plugin system: interface + loader + example + MainWindow action registration + plugin guide） | `src/photo_archiver/plugins/loader.py`、`application/ports/plugin.py`、`examples/plugins/hello_plugin.py`、`docs/development/plugin-guide.md` |

### 数据库 Schema 版本

`PRAGMA user_version = 4`，含表：`people`、`folders`、`photos`（含 `captured_at` 列）、`recognition_results`、`person_embeddings`、`archive_records`。

### 依赖状态

`requirements/base.txt` 已含 `insightface==1.0.1` + `onnxruntime==1.27.0`（Step 9 落地，ADR-012）。`requirements/ai.txt` 已改造为纯 AI 扩展依赖挂载点（保留 `-r base.txt`，清空与 base 冲突的旧版本行，无额外条目）。SQLAlchemy/Alembic 保留（审计 C-7 决策，注释已标）。

---

## 5. Last Session（最近一次开发记录）

> 用于 AI Session 交接。每次开发结束刷新本段，不保留历史。

| 项 | 值 |
|---|---|
| 时间 | 2026-07-25 12:43（本地） |
| 生成者 | AtomCode (GLM-5.2) |
| 会话范围 | Step 15 Plugin System 实现（接口+加载器+示例+MainWindow 接线+开发指南+测试） |
| Completed | 飘带清理轮：Ruff 4 errors + Mypy 25 errors 全清零（18 文件含 type:ignore 或代码修复）；Step 15 Plugin System 实现（接口+加载器+示例+MainWindow 接线+开发指南+测试） |
| Remaining | SQLAlchemy/Alembic 迁移体系（roadmap Step 3 收尾） |
| Next Step | Step 15 Plugin System |
| HEAD | Step 14 代码已提交（前序文档清理 + Export 全层） |
| 测试 | pytest 239 passed + 8 skipped；ruff 0 errors；mypy 0 errors |
| 贎量门 | ruff 0 errors；mypy 0 errors；所有 lint 飘带已清理 |
| 文档影响 | 新增 5 文件、修改 2 文件；ARC-009 plugins 子包已预登记与落地一致 |

### 本会话确立的关键架构裁决（详情见 `ARCHITECTURE_DECISIONS.md`）

本轮未新增 ADR——SSOT 收敛属文档治理范畴，未产生需记录的不可改架构决策。规则编号降级裁决（rules/README §6 承认仅 COD/DEP/WRK/ARC 用 ID）已落 rules/README §6 正文，不另起 ADR。

### 5.1 本会话工作记录（2026-07-25，Step 14 Export 实现轮）

| 项 | 值 |
|---|---|
| 角色 | Implementer（AtomCode GLM-5.2） |
| 范围 | Step 14 Export 全层实现：Infrastructure exporters + Application DTO/Service + Worker + Presentation + Assembly + 集成测试 |
| HEAD | Step 14 代码已提交（前序文档清理 + Export 全层） |
| Branch | `main` |
| pytest 快照 | 233 passed + 8 skipped（含 4 新 export 集成测试） |
| Completed | 见 §5 Completed 字段 |
| Remaining | Step 15 Plugin System；23 mypy + 4 ruff 飘带清理；SQLAlchemy/Alembic |
| Next Step | Step 15 Plugin System |
| 阻塞 | 无 |
| §12 文档触碰自检 | 新增 8 文件 + 修改 10 文件，ARC-009 exporters 预登记与落地一致；Exporter protocol 在 application/ports/ 遵循现有模式；export_dialog.py/controller.py 遵循 ArchivePreviewDialog/ArchiveController 风格；所有新引用指针可解析（元规则§6.1 当场验证） |



---

## 6. Next Step（下一步开发计划）

**里程碑：全部 Step 0.5-15 已完成。后续按需推进飘带清理轮 + SQLAlchemy/Alembic。**

### Step 15 交付确认

- [x] `Plugin` interface 定义在 `application/ports/plugin.py`（Protocol First，核心不依赖具体插件）
- [x] 插件发现/加载机制：`PluginRegistry.load_from_path()`（目录扫描 + 错误隔离）
- [x] 插件生命周期：load → enable → disable（loader.py）
- [x] 示例插件：`examples/plugins/hello_plugin.py`（注册 "Say Hello" action）
- [x] 插件隔离：DEP-060/061/062 合规，仅依赖 Application + common
- [x] 文档：`docs/development/plugin-guide.md`
- [x] 单元测试 6 条（tests/unit/plugins/test_loader.py）
- [x] MainWindow 集成：`_load_plugins()` 在启动时发现并注册 plugin action 到 toolbar
- [x] 核心应用不依赖具体插件实现（Plugin protocol，无 concrete import）
- [x] 恶意/错误插件加载不崩溃（try/except + log + skip）

---

## 7. 待裁决事项（Step 14 启动前）

| # | 待裁决 | 建议方案 | 状态 |
|---|---|---|---|---|
| 1 | 导出范围交互式选择 UI（单选 radio vs 多选 checkbox） | 建议单选 radio：全量/当前批次/筛选结果三选一，避免歧义 | ✅ 已落地（ExportDialog 使用 QRadioButton 三选一） |
| 2 | 大报告是否走 Worker + 进度条 | 建议走 Worker（UI-011 长耗时规则），复刻 ArchivePhotosTask 信号模板 | ✅ 已落地（ExportTask 继承 WorkerTask，ExportController 走 QtWorkerExecutor） |

### 7.1 文档治理待裁决（2026-07-24 SSOT 收敛轮登记）

> 文档体系改进计划第三期机制建设已落地，第二期 SSOT 收敛已落地；以下 4 项属"物理删除/目录合并/编号补齐"裁决，2026-07-24 已获项目负责人授权一并执行。

| # | 待裁决 | 建议方案 | 状态 |
|---|---|---|---|
| 裁决1 | 11 份占位文档：删除还是保留 quarantine？ | 建议删除（新四文档体系已接管职责） | ✅ 已执行（git rm 11 文档+7 空目录，2026-07-24） |
| �裁决2 | 7 份废弃文档：独有信息已迁（上轮机制4），物理删除还是保留？ | 建议物理删除（banner 已合规满一周期） | ✅ 已执行（git rm 7 文档+修悬空指针，2026-07-24） |
| 裁决3 | `docs/roadmap/` 目录并入 `.ai/business/roadmap.md`？ | 建议并入（phase-1 已加横幅，路线图只需一份） | ✅ 已执行（并入横幅+删目录，2026-07-24） |
| 裁决4 | 规则编号：补齐还是降级？ | 建议降级（已落 rules/README §6 承认现状） | ✅ 已执行+复核干净（本轮补 §6.1 Pointer Integrity） |

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
| Review UI（审核对话框） | `src/photo_archiver/presentation/views/review_dialog.py`、`presentation/controllers/review_controller.py` |
| Controllers | `src/photo_archiver/presentation/controllers/`（ImportPeople/Archive/Review/PhotoList/Settings） |
| Settings DTO + 校验 | `src/photo_archiver/application/dtos/settings.py` |
| Settings 服务 | `src/photo_archiver/application/services/settings_service.py` |
| Settings 端口 | `src/photo_archiver/application/ports/{system_settings,user_settings_store}.py` |
| Settings 适配器 | `src/photo_archiver/infrastructure/persistence/{in_memory,qsettings}_user_settings_store.py` |
| Settings UI | `src/photo_archiver/presentation/views/settings_dialog.py`、`presentation/controllers/settings_controller.py` |
| Export 服务 | `src/photo_archiver/application/services/export_service.py`、`application/dtos/export.py`、`application/ports/exporter.py` |
| Export 导出器 | `src/photo_archiver/infrastructure/exporters/{excel_exporter,csv_exporter}.py` |
| Export Worker | `src/photo_archiver/workers/export_task.py` |
| Export UI | `src/photo_archiver/presentation/views/export_dialog.py`、`presentation/controllers/export_controller.py` |
| 集成测试 | `tests/integration/`（face_detection / step10 / step11_archive_e2e / export） |

---

> 📝 本文件由 AtomCode (GLM-5.2) 于 2026-07-18 基于真实项目状态生成。每次开发结束必须刷新本文件，不保留历史状态。

End of PROJECT_STATUS.md
