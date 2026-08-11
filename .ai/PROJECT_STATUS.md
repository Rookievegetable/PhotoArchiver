# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**"项目现在开发到哪里了？"**
>
> 这是唯一允许频繁修改的 AI 文档。每次开发结束必须更新。历史状态不保留——永远只有当前状态。
>
> Version: 1.4.0 ｜ Last Updated: 2026-08-11 ｜ Status: Live

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
| 3 | Database | ✅ Completed（sqlite3 + PRAGMA v4 → Alembic 迁移体系已激活，ADR-024） |
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

里程碑：M1-M6 全部就绪（Step 0.5-15 全完成）；M7 可扩展未启动。

---

## 2. Current Step（当前开发阶段）

**项目开发已全面收官。所有 Step 0.5-15 全部完成。陔带清零（ruff 0 + mypy 0）。Alembic 迁移体系已激活。CI 流水线已激活（GitHub Actions 三平台矩陂 + 模型缓存，ISSUE-008/009 双关闭，KNOWN_ISSUES 清零）。**

前置就绪状态：
- All 15 steps completed and verified.
- 数据库 Schema v4（Alembic `001_initial_v4` 管理）。
- 陔带清理轮执行完毕：ruff 4→0, mypy 25→0。
- CI 流水线已激活（`.github/workflows/ci.yml`，三 OS 矩陂 + buffalo_l 模型缓存 + R-4 AI 断言 + UI 断言双守卫，ISSUE-008/009 关闭，KNOWN_ISSUES 清零）。

---

## 3. Project Status（项目当前状态）

**全部 15 个 Roadmap Step 均已实现并验证通过**；阶段 B 业务增强 B1-B5 已全部落地（阶段 0 收口实测质量门：pytest 320 passed + 8 skipped，ruff 0，mypy 0）。

| 阶段 | 状态 |
|---|---|
| Phase 1（Step 0.5-11） | ✅ 完成 |
| Phase 2 产品化（Step 12-15） | ✅ 完成 |
| 陔带清理轮 | ✅ ruff 0 + mypy 0 |
| Alembic 迁移体系 | ✅ 已激活（ADR-024） |
| CI 流水线（GitHub Actions） | ✅ 已激活（三 OS 矩陂 + buffalo_l 模型缓存 + R-4 AI 断言 + UI 断言双守卫，ISSUE-008/009 关闭，KNOWN_ISSUES 清零） |
| 阶段 B 业务增强 B1 重复图片检测 | ✅ 已落地（2026-08-01，HEAD 6301612） |
| 阶段 B 业务增强 B2 搜索/筛选 | ✅ 已落地（2026-08-01，HEAD 39bd576） |
| 阶段 B 业务增强 B3 批量操作 | ✅ 已落地（2026-08-02，HEAD cafff2b） |
| 阶段 B 业务增强 B4 HTML 导出 | ✅ 已落地（2026-08-02，HEAD cafff2b） |
| 阶段 B 业务增强 B5 插件上下文 | ✅ 已落地（2026-08-10，HEAD cafff2b，v2 只读 PluginContext） |

详见 `.ai/business/roadmap.md` §18-§20（规划原文保持计划格式，实际进度以本节 §1 为准）。

---

## 4. Current Modules（当前模块状态）

| 模块 | 状态 | 关键文件 |
|---|---|---|
| Logging | ✅ Step 1 就绪 | `infrastructure/logging/configuration.py` |
| Configuration | ✅ Step 2 就绪（系统配置 `AppSettings`）+ Step 13 用户偏好闭环（`UserPreferences` + `UserSettingsStore` 抽象端口 + QSettings/InMemory 双适配器） | `infrastructure/config/settings.py`（`AppSettings`）、`application/dtos/settings.py`、`infrastructure/persistence/{in_memory,qsettings}_user_settings_store.py` |
| Database | ✅ Step 3 就绪 + Alembic 迁移体系已激活（ADR-024，`001_initial_v4`） | `infrastructure/database/sqlite_connection.py`、`infrastructure/database/alembic_runner.py`、`alembic/` |
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
| 阶段 B / B1 重复图片检测 | ✅ 已落地（2026-08-01，HEAD 6301612）：PillowPhotoMetadataReader 可选注入 ContentHashCalculator + PhotoRepository.list_duplicate_groups（SQLite 单查询 IN + InMemory 内存过滤）+ DetectDuplicatesService + DuplicateReport DTO + BackfillContentHashService + `backfill-content-hash` CLI 子命令 + DuplicateReportDialog 首版只读 + DetectDuplicatesController + MainWindow toolbar 入口 | `infrastructure/filesystem/pillow_photo_metadata_reader.py`、`domain/repositories/photo_repository.py`、`infrastructure/database/sqlite_photo_repository.py`、`infrastructure/repositories/in_memory_photo_repository.py`、`application/services/{detect_duplicates,backfill_content_hash}_service.py`、`application/dtos/duplicates.py`、`presentation/views/duplicate_report_dialog.py`、`presentation/controllers/detect_duplicates_controller.py`、`main.py` |
| 阶段 B / B2 搜索/筛选 | ✅ 已落地（2026-08-01，HEAD 39bd576）：PhotoSearchCriteria Domain 值对象（person_id/match_status/captured_from/captured_to 可选 AND）+ PhotoRepository.search 扩展（SQLite SQL 下推 + InMemory 内存过滤，对照测试守护一致）+ SearchPhotosService + PhotoListController.search_photos + FilterBar（criteria_changed → 刷新列表，criteria None 回退 list_all） | `domain/value_objects/photo_search_criteria.py`、`domain/repositories/photo_repository.py`、`infrastructure/database/sqlite_photo_repository.py`、`infrastructure/repositories/in_memory_photo_repository.py`、`application/services/search_photos_service.py`、`presentation/views/filter_bar.py`、`presentation/controllers/photo_list_controller.py`、`presentation/views/main_window.py` |
| 阶段 B / B3 批量操作 | ✅ 已落地（2026-08-02，HEAD cafff2b）：ArchivePhotosCommand 加 photo_ids 可选参数（向后兼容）+ ArchivePlanner.plan 加 photo_ids 过滤（O(1) set 过滤 APPROVED 集合）+ ArchivePhotosService execute/preview 双处透传 photo_ids + ArchiveController preview/execute 加 photo_ids 参数 + PhotoList QListView 改 ExtendedSelection 多选 + MainWindow `_on_archive_clicked` 读选中项透传 + `_collect_selected_photo_ids` 辅助 | `application/commands/archive.py`、`application/services/archive_planner.py`、`application/services/archive_photos_service.py`、`application/use_cases/archive.py`、`presentation/controllers/archive_controller.py`、`presentation/views/main_window.py` |
| 阶段 B / B4 HTML 导出 | ✅ 已落地（2026-08-02，HEAD cafff2b）：HtmlExporter Infrastructure 新建（零依赖 stdlib html.escape + string.Template，XSS 转义）+ ExportService 无改动（多态注入 Exporter Protocol）+ ExportController export 加 format_name 参数 + _resolve_exporter format→Exporter 映射（xlsx/csv/html）+ ExportDialog _FORMAT_CHOICES 加 HTML 选项 + format_name/_on_browse 扩 html 分支 | `infrastructure/exporters/html_exporter.py`、`application/ports/exporter.py`、`presentation/controllers/export_controller.py`、`presentation/views/export_dialog.py` |
| 阶段 B / B5 插件上下文 | ✅ 已落地（2026-08-10，HEAD cafff2b）：PluginContext Port 新建（v2 收敛只读版：search_photos + detect_duplicates 读方法；import/export 写能力暂缓留后续轮单独裁决）+ ActionResult DTO（success/failure/noop 三态，宿主渲染动作结果）+ Plugin Protocol enable 扩可选 context 参 + execute_action 改返 ActionResult + PluginRegistry 扩可选 context 参 + enable_all 透传 + bootstrap 装配 _ReadOnlyPluginContext 实例 + ApplicationContext 扩 plugin_context 字段 + MainWindow `_load_plugins` 改从 context 取 + `_on_plugin_action` 接住 ActionResult 渲染 + `_render_plugin_action_result` + HelloPlugin example enable 扩参 + execute_action 改返 ActionResult | `application/ports/plugin_context.py`、`application/dtos/plugin_action_result.py`、`application/ports/plugin.py`、`plugins/loader.py`、`app/bootstrap.py`、`app/context.py`、`presentation/views/main_window.py`、`examples/plugins/hello_plugin.py`、`docs/development/plugin-context-design.md` |

### 数据库 Schema 版本

`PRAGMA user_version = 4`，含表：`people`、`folders`、`photos`（含 `captured_at` 列）、`recognition_results`、`person_embeddings`、`archive_records`。Schema 迁移由 Alembic 管理（`alembic/` 目录 + `alembic_runner.py`）。

### 依赖状态

`requirements/base.txt` 已含 `insightface==1.0.1` + `onnxruntime==1.27.0`（Step 9 落地，ADR-012）。`requirements/ai.txt` 已改造为纯 AI 扩展依赖挂载点（保留 `-r base.txt`，清空与 base 冲突的旧版本行，无额外条目）。SQLAlchemy/Alembic 保留（审计 C-7 决策，注释已标）。

---

## 5. Last Session（最近一次开发记录）

> 用于 AI Session 交接。每次开发结束刷新本段，不保留历史。

| 项 | 值 |
|---|---|
| 时间 | 2026-08-11（本地） |
| 生成者 | AtomCode |
| 会话范围 | 阶段 0 质量基线与文档收口（承接阶段 B1-B5 落地会话，B 方案与落地细节见 §3/§4） |
| Completed | 阶段 0 收口：① 实测质量门（ruff 0 / mypy 0 / pytest 320 passed + 8 skipped，Python 3.11.9 @ .venv）；② B3/B4/B5 架构边界审查（B3 photo_ids 向后兼容 + 过滤留 ArchivePlanner；B4 HtmlExporter 仅 Infrastructure + XSS 转义 + 走 ExportTask；B5 只读 PluginContext 不暴露 Repository/UoW/Archive/WorkerExecutor/ApplicationContext，宿主渲染 ActionResult；发现 1 项代码问题只记录不修：ExportController 直连 infrastructure.exporters 违反 DEP-002，见阶段 0 报告）；③ 静态规则检查全项 0 命中（print/TODO/except:/插件 infra 导入）；④ 文档收口：plugin-guide.md 同步 v2 API（enable(context=None) + execute_action→ActionResult + 只读限制 + 非沙箱声明）；PROJECT_STATUS §1/§3/§4/§5/§6 刷新；plugin-context-design.md 纳入正式文档体系（DOCUMENT_INDEX §2.4 登记 + 头部状态标注） |
| Remaining | 无阻塞（代码问题 1 项仅记录：ExportController 直连 Infrastructure，待阶段 1 修复） |
| Next Step | 阶段 0 收口完成后进入 PluginContext 边界加固（阶段 1）：消除 Presentation→Infrastructure 越界（exporter 注册表迁 app 装配层或 Application 侧注册）；之后再考虑插件写能力（import/export 暂缓项）、Alembic 深化与性能加固 |
| HEAD | 3ae3cd3（阶段 0 文档收口提交：docs: synchronize phase b and plugin documentation）；B3+B4+B5 落地于 cafff2b |
| 测试 | 实测 pytest 320 passed + 8 skipped（8 skip：InsightFace 模型包或示例人脸图片缺失——`tests/integration/face_detection/` 的 skip 条件，装齐 `download_models.py` 模型 + 样例 JPG 后实跑）；ruff 0 errors；mypy 0 errors |
| 质量门 | 全部实测通过（2026-08-11，.venv Python 3.11.9）：ruff 0 + mypy 0 + pytest 320 passed + 8 skipped；git diff --check 干净 |
| 文档影响 | 本会话触及 PROJECT_STATUS §1/§3/§4/§5/§6 + plugin-guide.md（v3 API 同步：ContextAwarePlugin + set_context → enable + PluginReport 渲染契约）+ DOCUMENT_INDEX §2.4（phase1-adr-draft.md 登记）+ KNOWN_ISSUES（新增 ISSUE-016：ExportController DEP-002 越界，阶段 1b 独立修复）+ plugin-context-design.md 头部状态标注（v3 收敛）+ ARCHITECTURE_DECISIONS（新增 ADR-026：阶段 1 PluginContext 公共边界加固）+ phase1-adr-draft.md（前置门定稿草案落盘）；新增 ADR-026 |

### 本会话确立的关键架构裁决（详情见 `ARCHITECTURE_DECISIONS.md`）

本轮新增 ADR-026（阶段 1 PluginContext 公共边界加固，前置门拍板 2026-08-11）：ContextAwarePlugin(Plugin) 继承关系 + set_context(context) → enable() 新标准 + Plugin DTO 边界（PluginPhotoQuery 3 态 / PluginPhotoSummary 4 态含 none）+ PluginReport 单元格 str | int | float 混合 + ActionResult.report 收紧替旧 payload:Any + Protocol-first 实施顺序 + ISSUE-016 独立修复提交边界。详见 `docs/development/phase1-adr-draft.md`。

### 5.1 本会话工作记录（2026-07-30~31，ISSUE-001+002+006+010 修复轮）

| 项 | 值 |
|---|---|
| 角色 | Implementer（AtomCode GLM-5.2） |
| 范围 | 严格一 Issue 一提交：Round 1 ISSUE-002 单提交 / Round 2 ISSUE-001 单提交 / Round 3 ISSUE-006+010 单提交（两低优先级顺手收口合并） |
| HEAD | 本会话收尾提交 |
| Branch | `main` |
| pytest 快照 | 249 passed + 8 skipped |
| Completed | 见 §5 Completed 字段 |
| Remaining | 无 |
| Next Step | Round 4 ISSUE-003（按已定计划最后一项） |
| 阻塞 | 无 |
| §12 文档触碰自检 | 仅触及 PROJECT_STATUS/KNOWN_ISSUES，无人类文档陈述失效（新能力 + 性能优化 + 类型收口 + 测试环境加固非现状描述） |

### 5.2 规则变更记录（2026-08-01，REV-AI 证据门槛落地）

| 项 | 值 |
|---|---|
| 时间 | 2026-08-01 20:52（本地） |
| 生成者 | Kimi（Moonshot AI） |
| 范围 | `review-rules.md` 新增 §18.1 Evidence-Gated Review（REV-AI-001~007：证据锚点/质量门先行/行为断言须复现/置信度三级/权威引用当场验证/严重度可达性校准/证伪自审），Version 1.0.1→1.1.0 |
| 依据 | `review-rules-addition-draft.md`（临时草案）§裁决点 1-4 按默认建议定案；动议背景：当日 B1 Review 轮外部报告臆造类问题（惯例臆造/行为臆断/错引 ADR 编号） |
| HEAD | `5dc2cd3`（单文件 docs 提交，未触碰当时未提交的 B1 工作区） |
| 文档影响 | review-rules.md §18.1 + 版本头；DOCUMENT_INDEX §2.2/§3 职责一句话与 SSOT 映射无变化未同步；PROJECT_STATUS 本记录 |



---

## 6. Next Step（下一步开发计划）

**里程碑：全部 Step 0.5-15 已完成 + 阶段 B（B1-B5）全链路已闭环 + 阶段 0 质量基线与文档收口已完成（2026-08-11）。阶段 1 PluginContext 公共边界加固（ADR-026）实施中——前置门草案已拍板，按 Protocol-first 顺序推进；ISSUE-016（ExportController DEP-002 越界）属阶段 1b 独立修复提交。后续考虑：插件写能力（import/export 暂缓项）、Alembic 深化与性能加固。**

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
| 裁决2 | 7 份废弃文档：独有信息已迁（上轮机制4），物理删除还是保留？ | 建议物理删除（banner 已合规满一周期） | ✅ 已执行（git rm 7 文档+修悬空指针，2026-07-24） |
| 裁决3 | `docs/roadmap/` 目录并入 `.ai/business/roadmap.md`？ | 建议并入（phase-1 已加横幅，路线图只需一份） | ✅ 已执行（并入横幅+删目录，2026-07-24） |
| 裁决4 | 规则编号：补齐还是降级？ | 建议降级（已落 rules/README §6 承认现状） | ✅ 已执行+复核干净（本轮补 §6.1 Pointer Integrity） |

---

## 8. 关键文件索引（Step 13 收尾状态）

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
