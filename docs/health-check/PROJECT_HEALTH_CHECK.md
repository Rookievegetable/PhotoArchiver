# PhotoArchiver — 项目综合体检报告（Project Health Check）

> **文档性质**：独立、端到端、以当前 HEAD 为唯一基准的全项目体检
> **体检时间**：2026-09-02
> **基线**：HEAD `3a2ef0a`（== origin/main，working tree clean）
> **方法**：READ ONLY / Evidence Driven / Current HEAD Driven——所有结论基于当前源码 + 当前测试 + 当前正式文档交叉验证，不以历史审计结论为事实来源
> **配套文件**：`docs/roadmap/DEVELOPMENT_ROADMAP.md`（后续开发计划）

---

## 1. Executive Summary

**PROJECT HEALTH: Attention Required（健康但有需注意项）**

PhotoArchiver 的工程质量基座是扎实的：分层架构实测合规（Domain 零框架依赖、Workers 仅 QtCore、Presentation 不触 Infrastructure）、四项质量门全绿（ruff / mypy 171 files / pip check / pytest 570 passed）、核心业务管线（扫描 → 元数据 → 识别 → 审核 → 归档 → 导出）形成真实闭环且安全防护（路径逃逸、解压炸弹、公式注入、SQL 注入）成体系。

但本次体检发现 **3 项此前未登记的用户可见功能失效**（S1 级）：

1. **插件系统在 UI 中从未加载**——`main_window.py:191` 以 4×parent 解析出 `src/examples/plugins`（不存在），`is_dir()` 静默跳过，插件动作与 PluginReportDialog 运行时不可达（后端能力完整）。
2. **缩略图从不渲染**——模型仅提供自定义 `THUMBNAIL_ROLE`，全 src 无任何 delegate/DecorationRole 消费者，默认 QListView delegate 只渲染文件名。整条缩略图生成/缓存/异步加载管线产出对用户不可见。
3. **Excel 人员导入断线**——文件选择器接受 `.xlsx/.xls`（`main_window.py:393`），但装配只注入 `TxtPersonImportReader`（`app/services.py:140`），Excel 读取器为孤儿模块；选 xlsx 即把二进制喂给 csv reader。

另有两项**流程性漂移**：`PROJECT_STATUS.md` 未随 Phase 9 更新（仍称 HEAD=`5aad031`、本地领先 22 笔——均为历史重写前状态）；其引用的 `docs/health-check/PHASE_*.md` 审计报告在当前 main 历史中不存在（历史重写时剥离）。

以及一项**已知 flake 的状态恶化**：F-002（match 控制器线程池时序）本次**单跑 ×2 均失败**（历史记录为"单跑 ×2 稳定"），失败点移至单飞守卫断言（`controller.is_running`），持久化断言本身通过——是测试时序问题而非生产缺陷，但"单跑稳定"的复判口径已不成立。

**总体判断**：项目处于"开发完成度高、发布准备度低"的状态。以受支持的源码/clone 形态（ADR-031）面向技术用户，核心产品流程可用；面向目标受众（学校/政府/档案馆等非技术用户）的 v1.0 交付，还差发布工程（分发、数据安全、首启体验）与上述 3 项功能失效修复。

---

## 2. Current Baseline

| 项 | 值 |
|---|---|
| HEAD | `3a2ef0a197769b3ccd885bf44738930643c7ce5e` |
| origin/main | `3a2ef0a`（**== HEAD ✓**） |
| Working tree | clean ✓ |
| 分支 | main（tracking origin/main，无领先/落后） |
| 版本 | pyproject 2.2.0 = CHANGELOG 2.2.0 = .env.example APP_VERSION 2.2.0 ✓ |
| tag 全景 | v1.0.0 / v2.0.0 / v2.1.0 / v2.2.0（均已发布 GitHub Release） |
| 源码规模 | 171 个 .py 文件 / 13,303 行（src）；测试 87 个文件（81 个 test 模块） |
| Python | 3.11.9（venv 实测） |
| 最近 5 commit | Phase 9 P0 Filter Completeness（日期筛选 / 人员筛选 / 三轴联合 + FILTERED 导出联测）+ 文档 |

**质量门实测（本次体检执行）**：

| 门 | 结果 | 备注 |
|---|---|---|
| pytest | **1 failed / 570 passed / 3 skipped**（111.98s，62 warnings） | 唯一 failed = F-002 已知 flake（见 §10） |
| ruff check . | All checks passed ✓ | |
| mypy src | Success: no issues in 171 source files ✓ | |
| pip check | No broken requirements found ✓ | |

**环境注意**：根目录残留 6 个未跟踪的 `p9_*.log` 日志文件（gitignore 覆盖，不进库）；`config/env|logging|settings|themes` 与根 `models/` 为空目录（死脚手架）；`resources/models/` 内有嵌套解压残留 `models/buffalo_l(.zip)`。

---

## 3. Architecture Health

**结论：合规且干净，无实质性分层违规；存在少量"实践中合理但矩阵未授权"的偏差。**

### 3.1 合规项（实测）

| 检查 | 结果 | 证据 |
|---|---|---|
| Domain 零框架依赖 | ✅ 全部 26 文件仅 stdlib + domain 内部 | `face_embedding.py` 等逐文件核验；`numpy` 字样仅存在于 docstring；ADR-015 零 numpy 不变量经 `insightface_types.py:53`（`.tolist()` 边界）保持 |
| Application 无 GUI/SQL/Infrastructure | ✅ 零违规 | 无 PySide6/sqlite3/cv2/insightface/openpyxl import；loguru 为 §13 明示允许 |
| Workers 仅 QtCore | ✅ | `qt_executor.py:3` 唯一 Qt import 为 `PySide6.QtCore`（DEP-040 允许集）；任务层零业务规则 |
| Presentation 不触 Infrastructure | ✅ | 零 infrastructure/sqlite3/cv2/insightface/openpyxl import |
| SQLite 仅在 infrastructure/database | ✅ | |
| ai/ 层合规 | ✅ | ai → domain only；`infrastructure/ai/` 负责 loader（DEP-050 双包分工有 `ai/__init__.py:3` 明示） |
| CLI 不绕过 Application | ✅ | `main.py` scan/archive/backfill 均经 `bootstrap_application()` → Application service |
| 组合根 | ✅ | `bootstrap.py` 纯装配；services 延迟 import AI（CLI/CI 免付 ~3s InsightFace 成本）；模型缺失降级 `_UnavailableMatchService` 而非启动失败 |

### 3.2 偏差与风险（Finding）

| # | 发现 | 级别 | 证据 |
|---|---|---|---|
| A-1 | **app ↔ presentation 包级循环 import**：`app/application.py:10` 导入 MainWindow，`main_window.py:31` 导入 `app.context`。仅因 `main.py:10` 先导入 app 而成立；`presentation/views/__init__.py:3-8` 以文档化规避而非消除。直接运行 `python -c "from photo_archiver.presentation.views.main_window import MainWindow"` 会 ImportError | Important | 已文档化（DEP-018 张力），加载顺序纪律维系 |
| A-2 | **Infrastructure → Application ports（16 处）**：`sqlite_unit_of_work.py:5`、3 个 exporter、scanner/metadata/thumbnail/importers/settings store 等导入 `application.ports/DTO`。方向内向（DIP 有效），但 DEP §4 矩阵未授权 infra → application | Observation | 建议矩阵补记"infra → application（仅 ports）"或端口下沉 Domain |
| A-3 | **PySide6 出现在 Infrastructure**：`qsettings_user_settings_store.py:22` `from PySide6.QtCore import QSettings`——矩阵未授权，虽是孤立的有意适配器 | Observation | 规则文本与实现不一致（二选一：修矩阵或改适配器） |
| A-4 | **矩阵缺口**：presentation → workers（6 文件）、presentation → app.context、presentation → plugins、app → infrastructure（组合根必然）——实践合理、成文缺失 | Observation | 依赖矩阵文档滞后于架构现实 |
| A-5 | `ModelPackMissing` 双定义：`app/services.py:202` 与 `infrastructure/ai/insightface_loader.py:20` 是两个同名不同类 | Observation | 潜在 except 捕获失配隐患 |
| A-6 | `common/` 为空包（DEP-070 授权的"通用工具层"零代码） | Observation | 死结构 |
| A-7 | 迁移每启动重复执行两次（`sqlite_connection.py:144` + `bootstrap.py:56`）；幂等但冗余 | Observation | |
| A-8 | InMemory 仓储：生产零消费，为规则 §16 明示的测试替身——非死代码 | Observation | |

---

## 4. Product Completeness

**结论：核心管线 COMPLETE；但存在 3 项用户可见功能失效（后端已建成）+ 1 组库管理能力 MISSING（有意 deferred）。**

### 4.1 用户核心问题回答

> **PhotoArchiver 现在到底能不能作为一个完整产品使用？**

- **对技术用户（源码/clone 形态，Windows）**：**能完成主流程**——导入人员（txt）→ 扫描照片 → 人脸识别匹配 → 审核通过 → 归档 → 导出报告，全链路真实可用，错误有 UI 呈现，进度有反馈，归档有预览确认。
- **对目标受众（非技术用户）**：**尚不能独立使用**——安装需 MSVC 编译 insightface（sdist-only）、需手动下载 300MB 模型包（脚本无摘要校验）、`.env` 手工配置、ARCHIVE_ROOT 无设置界面、数据库位置随启动目录漂移。
- **被"已完成"文档掩盖的失效**：插件菜单（Step 15 交付物）与缩略图预览（Step 7 交付物）在当前 HEAD **运行时不可见**——文档说 COMPLETE，实际用户看不到效果。这是本次体检最重要的产品级发现。

### 4.2 功能失效明细（新发现，未登记于 KNOWN_ISSUES）

| # | 失效 | 证据 | 影响 |
|---|---|---|---|
| P-1 | **插件 UI 死路径**：`Path(__file__).resolve().parent.parent.parent.parent / "examples/plugins"` 解析为 `<repo>/src/examples/plugins`（实测 `exists: False`；真实目录在仓库根，差一层 parent）。`is_dir()` 静默跳过 → 3 个示例插件的 QAction 永不出现，`PluginReportDialog` 不可达 | `main_window.py:191`；本体检 Python 实测复现 | Step 15 / ADR-026/028 全部插件能力对用户不可见；FAQ 仍在宣传该功能（文档-现实漂移） |
| P-2 | **缩略图不渲染**：`PhotoListModel` 仅提供 `THUMBNAIL_ROLE`（`photo_list_model.py:18,72`），全 src 无 `setItemDelegate`/`QStyledItemDelegate`/`DecorationRole` 消费者（grep 实测 0 处）；默认 delegate 只认 DisplayRole/DecorationRole → 异步加载、缓存命中、`set_thumbnail` 全部生效但**画面上只有文件名**。模型 docstring 还宣称提供 "person match, status" per-row data（不存在） | `photo_list_model.py:4-5`（docstring 失实）+ grep 证据 | 照片库浏览体验缺失核心一环；缩略图管线（Step 7 全部工作）用户不可见 |
| P-3 | **Excel 导入断线**：UI 文件过滤器 `*.txt *.xlsx *.xls`，装配仅注入 `TxtPersonImportReader`，`ExcelPersonImportReader` 生产零消费；选 xlsx → 二进制按 csv 解析 | `main_window.py:393`、`app/services.py:140` | "Excel Import"（Step 5 名称）实际仅支持 txt/csv；错误信息难定位 |

### 4.3 有意缺口（Deferred/Blocked，非缺陷）

| 能力 | 状态 | 依据 |
|---|---|---|
| CURRENT_BATCH 导出 | DEFERRED | UI 永久禁用 + 服务/Task 层诚实 `ValueError`（Phase 7 契约 §2/D1-D5）；需批次持久化（schema owner 门） |
| 照片删除 / 库管理 | MISSING | 全仓零 DELETE API（仓储协议层即无 remove）；重复检测只读报告 |
| 重扫/增量对账 | MISSING | 重扫仅按绝对路径幂等追加；文件变更不重读、删除不清理 |
| CLI 对等 | PARTIAL | 仅 scan/archive/backfill-content-hash；import-people/match/export 无 CLI |
| 安装态分发 | BLOCKED | ADR-031 by-design；方案 B 需求信号触发 |
| i18n / 语言切换 | PLACEHOLDER | 设置对话框有语言选项，全 src 零 `.tr()`/translate 调用，UI 硬编码英文 |

---

## 5. Core Workflow Health

**结论：10 环节中 7 个为真实闭环；Import 与 Match 持久化两环有实质性韧性缺口。**

| 环节 | 判定 | 关键证据与缺口 |
|---|---|---|
| 1. Import People | **PARTIAL** | 无事务——每行独立 autocommit（`sqlite_person_repository.py:17`），中断=部分提交；无 identity 行重复导入会重复入库（`import_people_service.py:52` 的查重以 identity 非空为前提，UNIQUE 不拦 NULL）；IntegrityError 类意外异常中止剩余行；UI 成功路径不显示逐行错误（`main_window.py:344`）；xlsx 断线（P-3） |
| 2. Scan Photos | **CLOSED LOOP（最强）** | 全程单 UoW（`scan_and_register_photos_service.py:59`）+ 逐照片元数据异常隔离（:98）；损坏文件不入库；按路径幂等重扫。缺口：无内容哈希/mtime 对账（文件变更不重读、删除不清除）、大小写不敏感文件系统可用不同大小写注册重复行 |
| 3. Metadata | **CLOSED LOOP** | EXIF DateTimeOriginal → mtime → None 三级回退（`pillow_photo_metadata_reader.py:104`）；DecompressionBomb/UnidentifiedImage 映射为 ValueError 进隔离；content hash 同程计算 |
| 4. Thumbnail | **CLOSED LOOP（生成侧）** | 懒加载 + 线程池 + `_in_flight` 去重（`photo_list_controller.py:114-131`）；key=sha256(path+size+mtime+file_size) 天然失效更新。缺口：**渲染断点（P-2）**；孤儿缓存永不清理 |
| 5. Recognition + Matching | **CLOSED LOOP（附条件）** | 模型缺失 → TaskFailed → UI 弹窗（`app/services.py:206-244`）；单照片异常隔离；**生产配置（max_workers=4）走并行路径，持久化收束为批次末单次 `add_many`（`match_persons_service.py:242`）——进程崩溃丢整批**（串行路径逐张提交反而更韧）；无 UoW；"未检出人脸"不落行 → 下次 Match 重提交（恢复语义按"有无结果行"判定）；取消仅批边界（LIMIT-002） |
| 6. Review | **CLOSED LOOP** | approve/reject/bulk 齐备；逐条 UoW（`review_recognition_service.py:127`）；已终态幂等跳过。UX 弱项：行显示原始 UUID（`review_dialog.py:107`）；批量=N 次独立事务非原子；空队列自动关闭无反馈；识别运行中不自动刷新 |
| 7. Filter/Search | **CLOSED LOOP** | Phase 9 后三轴全通（status/person/date AND 语义、门控复选框、QVariant 陷阱已修）；参数化 SQL。缺口：JOIN 无 DISTINCT（多识别行照片重复出现）；无"未匹配"哨兵（VO docstring 承诺未兑现，`photo_search_criteria.py:34`）；date 轴用 captured_at（mtime 回退时语义静默变松） |
| 8. Archive | **CLOSED LOOP** | Planner→Plan→Executor；dry-run；conflict skip/overwrite/rename（.dup-N）；词典+symlink 双重包容校验（`archive_executor.py:244-276`）；APPROVED 驱动 + 成功态去重跳过 + 失败可重试；单 UoW 批量。缺口：FS 复制在事务窗口内，崩溃时 DB 回滚而文件已落盘（靠 skip 策略兜底收敛）；源文件永不移动/删除（by-design copy 语义，需用户知晓） |
| 9. Export | **PARTIAL** | ALL/FILTERED 全链闭环 + 泄漏矩阵测试；公式注入防护（CSV/Excel `'` 前缀、HTML escape）；导出对话框 CURRENT_BATCH 禁用诚实。缺口：**全内存收集 + openpyxl 整簿构建，无流式**（大库内存受限）；无 temp-file+rename 原子写（中断留半文件）；导出读库无快照 |
| 10. Duplicate Detection | **CLOSED LOOP（只读）** | 单 SQL push-down 无 N+1（`sqlite_photo_repository.py:137`）；报告对话框严格只读 |

**横向语义**：
- **Idempotency**：扫描（按路径）✓、识别（按"有无结果行"恢复，不含"未检出"态）△、导入（仅 identity 行）✗、审核（终态跳过）✓、归档（成功态跳过）✓。
- **Cancellation**：全部批边界级（LIMIT-002）；scan/import 的 cancelled 信号未接线（见 §9 W-2）。
- **Partial failure**：扫描/识别/归档逐项隔离良好；导入/匹配持久化两环如上。
- **Retry**：归档失败态可重试 ✓；识别无重试（靠再次手动触发 + 恢复语义）△。

---

## 6. UI / UX Health

**结论：核心操作流可用、确认门齐全；存在 3 项功能失效（§4.2）、若干占位/断线控件与空态缺失。**

| 项 | 现状 | 评价 |
|---|---|---|
| 主窗口结构 | 单 QToolBar + 9 QAction，无菜单栏 | 简洁够用 |
| 破坏性操作确认 | 归档有 ArchivePreviewDialog（计划/跳过计数 + 冲突策略 + dry-run）；删除类操作不存在（duplicate 报告只读） | ✓ 良好 |
| 进度 | 单一共享进度条 + 状态栏；TaskProgress 首/每10/末张上报 | 够用 |
| 空态 | 照片列表无空态占位（白板）；ReviewDialog 空队列自动关闭无"已完成"反馈；重复检测有友好空态 | 需补 |
| 失效/占位控件 | CURRENT_BATCH radio（by-design 禁用+诚实）；**语言下拉（i18n 占位，零实现）**；主题需重启生效；ARCHIVE_ROOT 无 UI 编辑（仅 .env+重启） | 语言项应视为断线控件 |
| 术语一致性 | 中文注释 + 英文 UI 文案统一；review 行裸 UUID 可读性差（`review_dialog.py:107`） | |
| 后端有 UI 无 / UI 有后端无 | backfill-content-hash 仅 CLI；插件动作 UI 缺失（P-1）；xlsx 过滤器有、读取器无（P-3） | |
| 识别状态可见性 | PhotoList 无识别/归档状态列（模型 docstring 宣称有，实无）；仅能经 Status 组合筛选间接感知 | |

---

## 7. Database / Persistence

**结论：Schema 健康、FK 全连接强制、SQL 全参数化；韧性短板在并发配置与备份缺位。**

### 7.1 Schema（Alembic 001 stamp + 002 DDL 唯一权威，ADR-027）

6 表：people（identity UNIQUE）/ folders（raw_path+path_base UNIQUE）/ photos（raw_path+path_base UNIQUE, folder_id → folders **ON DELETE SET NULL**）/ recognition_results（photo_id **CASCADE**, person_id **SET NULL**）/ person_embeddings（person_id **CASCADE**）/ archive_records（photo_id **CASCADE**）+ 5 命名索引。`PRAGMA foreign_keys=ON` 每连接执行（`sqlite_connection.py:72,96`）——级联语义真实生效。应用零 DELETE → 级联路径休眠、孤儿仅可能来自库损坏而非应用逻辑。

### 7.2 Finding

| # | 发现 | 级别 | 证据 |
|---|---|---|---|
| D-1 | **无 WAL、无显式 busy_timeout**：默认 rollback journal + Python 隐式 5s busy handler。扫描 UoW 持写锁覆盖整批（含逐张 SHA-256），期间 UI 线程同步写（审核）→ 可触发 `database is locked` | **Important（可达）** | grep 零 journal_mode/busy_timeout；`sqlite_connection.py:60-107` |
| D-2 | **零备份机制**：无 backup/VACUUM INTO/启动副本；FAQ 的备份指引=复制单文件。DB 损坏 → bootstrap 直接 re-raise，启动崩溃无修复提示 | **Important** | `bootstrap.py:54-63` |
| D-3 | **数据库路径 CWD 相对**：默认 `sqlite:///data/photo_archiver.db`（`settings.py:19,168`）+ `.env` 也按 CWD 加载——换目录启动即静默创建/使用另一个空库（macOS Finder 双启 CWD=`/` 必触发） | **Important（尤其 macOS）** | 与 ADR-031 E4 断点同源；源码形态下亦影响"从任意目录启动" |
| D-4 | `PRAGMA user_version=4` 为死状态：docstring 声称 Alembic 检测 user_version——实际 Alembic 只认 alembic_version 表；全代码无 reader | Observation | `sqlite_connection.py:131-138`、`001_initial_v4.py:22` |
| D-5 | 大小写不敏感盘上同文件不同大小写 → 重复注册（路径精确比较 + UNIQUE 大小写敏感） | Minor | `scan_and_register_photos_service.py:78-89` |
| D-6 | IN-clause 500 参数分块 + 全局排序恢复（`sqlite_recognition_repository.py:107-134`）；`add_many` 单事务 executemany ✓ | — | 良好实践 |
| D-7 | 归档：FS 复制在 UoW 窗口内 → 崩溃时 DB/磁盘分歧（skip 策略兜底可收敛；overwrite 会重写） | Minor | `archive_executor.py:79-82,279` |

---

## 8. Dependency Health

**结论：版本自洽无冲突；两个"批准未使用"依赖与 insightface 安装摩擦是主要风险。**

| 项 | 事实 |
|---|---|
| 清单体系 | base/dev/lock + ai.txt 扩展挂载点 + README 策略文档（P2-010）——治理良好 |
| pyproject | **无 dependencies 声明、无 console script**——wheel 安装态不可运行（ADR-031 by-design）；但 release.yml 仍构建发布 wheel/sdist 且无元数据警示 |
| 锁定 | lock.txt 为全 dev 环境 pip freeze（含 black/pytest/mypy/pre-commit），与 base/dev 内部一致；含非常见包 `python-discovery==1.4.4` 建议下次 freeze 复核 |
| 批准未使用 | pandas 2.3.1、watchdog 6.0.0——base.txt 注释明示"approved but unused, zero import"，有据可查非泄漏 |
| **insightface 1.0.1** | **sdist-only：每个用户安装都本地编译 C++（Windows 需 MSVC Build Tools + Cython）**——目标受众（非技术用户）安装的第一大障碍（P2-010 已登记） |
| onnxruntime 1.27.0 | CPU-only 官方 wheel（三平台）；CUDA provider 警告为良性回退（本次 pytest warnings 实测）；无 GPU 加速路径（有意简化，建议在文档确认） |
| numpy 2.2.6 | opencv/insightface 导入期硬依赖，显式 pin（P2-009）——与 insightface 1.0.1 实测共存无冲突 |
| 覆盖率工具缺失 | dev.txt 无 pytest-cov，全仓无覆盖率度量 |

**版本链**：pyproject 2.2.0 = CHANGELOG = .env.example = bootstrap 元数据回退 ✓ 无漂移。

---

## 9. Worker / Concurrency

**结论：QRunnable + 全局 QThreadPool + queued signals 模式正确，异常不丢失；取消接线与并发防护有缺口。**

| # | 发现 | 级别 | 证据 |
|---|---|---|---|
| W-1 | 异常纪律良好：WorkerTask.run 捕获→TaskFailed 信号→re-raise→runnable 吞并 debug log→UI 弹窗（`task.py:72-75`、`main_window.py:364`） | ✓ | |
| W-2 | **scan/import 的 cancelled 信号未连接**：`_connect_task_signals`（`main_window.py:321-331`）只接 started/progress/completed/failed；取消扫描后状态栏停留 "Cancelling ..."，无终态处理器复位 UI。match 有 cancelled slot（:551）；export 无取消 | **Important（用户可达）** | `scan_controller.py:46-52` |
| W-3 | **Scan 无单飞防护**：识别/导出有 is_running 守卫，扫描没有（`main_window.py:381`）——并发两次扫描交错共享 reporter（`bind_progress_reporter` save/restore）+ 双写锁竞争 | **Important** | `scan_and_register_photos_service.py:143-156` |
| W-4 | 取消仅批边界（LIMIT-002 登记一致）：`raise_if_cancelled` 只在 use case 前后（`application_tasks.py:35-38` 等） | Known Limitation | |
| W-5 | QRunnable autoDelete 缺省 True：池在工作线程删除 C++ 对象，而 signals QObject 建于 GUI 线程；`_active_runnable` 悬引用可在完成与终态信号间隙触发 `RuntimeError: Internal C++ object already deleted`（点 Cancel 时）。理论但真实 | Minor（低概率） | `qt_executor.py:31-36` |
| W-6 | UI 线程同步操作（记录在案的 by-design）：review 转换、筛选搜索、重复检测、列表刷新、设置保存、**插件 execute_action（任意插件代码在 UI 线程跑）**；归档 preview 的 Planner N+1 仓储读也在 UI 线程（大审核目录可感卡顿） | Minor | `main_window.py:430` |
| W-7 | 线程预算：QtWorkerExecutor 未传 max_workers（Qt 默认池 + 缩略图任务共享）；match 内层再开 ThreadPoolExecutor——两级并发。InsightFace session 跨线程共享有实测背书（ADR-032 基准）但无文档引用 onnxruntime 保证 | Observation | `app/bootstrap.py:64` |

---

## 10. Testing / Quality

**结论：规模与真实度俱佳（570+ 测试、真实 SQLite、真链路 E2E、三 OS CI）；短板在 flake 状态、边界强制自动化与覆盖率缺位。**

### 10.1 套件盘点（81 test 模块）

unit：application 20 / infrastructure 16 / presentation 14 / domain 5 / plugins 4 / ai 3 / workers 2 / 杂 3；integration：根 6 / database 1 / export 4 / face_detection 4。**无 conftest.py（全仓零共享 fixture，各文件自建 ~12 处）**；测试全部文件级真实 SQLite（零 `:memory:`）；pytest-qt 4.5.0 用于 10 个 UI 文件。

### 10.2 本次执行结果与 F-002 复判

- 全量：**1 failed / 570 passed / 3 skipped**（111.98s）。唯一 failed = `test_match_persons_controller_real_executor_e2e.py::test_controller_real_thread_pool_persists_pending`（F-002）。
- **F-002 单跑 ×2 均失败（2.18s / 1.77s）——与历史"单跑 ×2 稳定"记录不符，为本轮状态恶化**。
- 失败签名定性（--tb=long 实测）：持久化断言全部通过（pending 行落库、person_id/status/confidence 正确）；失败在末位 `assert controller.is_running is False`——completed 信号已发射、数据已可见，但单飞守卫释放的 queued slot 尚未执行。**是 documented 时序竞态的变体（守卫释放 vs 断言窗口），非生产缺陷**；但"全量偶发、单跑稳定"的复判口径自本轮起不成立。
- skips 全部正当（Pillow 缺失守卫 ×3、模型包守卫 ×2、Windows junction 平台守卫、symlink 权限运行时守卫、openpyxl 守卫）——无 mark.skip 滥用。

### 10.3 结构性缺口

| # | 缺口 | 影响 |
|---|---|---|
| T-1 | 无 import-linter / 自动化分层断言：仅 2 个手写静态 grep 测试（plugins/export controller 专用）+ 仓储协议契约测试 | 分层回归靠人工 + mypy |
| T-2 | 无覆盖率工具（无 pytest-cov） | 无法量化盲区 |
| T-3 | 对话框直测缺失：review_dialog / archive_preview_dialog / duplicate_report_dialog 零直测 | |
| T-4 | `_load_plugins` 无测试——正是 P-1 死路径长期未被发现的原因 | |
| T-5 | CI "no SKIPPED" 守卫用 `pytest --co -q`（收集期不含 importorskip 运行时 skip）→ 守卫基本恒 0，效力存疑 | `ci.yml:86-107` |
| T-6 | Qt 原生级崩溃（exit 127）在特定子集顺序下可复现（Phase 9 报告登记，先于 Phase 9 存在）；全量顺序安全 | 环境依赖型已知问题 |
| T-7 | LIMIT-001（真实缺模型 E2E 未入 CI）维持登记 | Known Limitation |

### 10.4 亮点

真实链路 E2E 文化（UI→Controller→QtWorkerExecutor→Task→Service→Repository→SQLite→文件，边界 double 仅限模态对话框并明示 What-remains-real）；三 OS CI 矩阵（offscreen Qt + 强制 AI/UI 测试不 skip + 模型缓存）；Phase 9 的 QVariant/真实链路联测再次验证该策略有效性。

---

## 11. Security

**结论：防护成体系且多数经测试锁定；缺口集中在模型完整性与 Windows 文件名语义。**

| 域 | 状态 | 证据 |
|---|---|---|
| 路径穿越 | ✅ 强 | ArchivePath VO 拒空段/`/`/`\`/`.`/`..`（`archive_path.py:56-69`）；executor 词典+resolve(symlink) 双重包容校验且拒绝 symlink 叶目标；event_or_date 恒为 builder 生成的 `%Y-%m-%d` |
| 文件名净化 | ⚠️ 缺 Windows 语义 | **未处理保留设备名（CON/PRN/AUX/NUL/COM1-9/LPT1-9）、尾点尾空格、非法字符 `: * ? " < > |`**——人名 `con` 或源文件 `nul.jpg` 会使归档项系统性 FAILED（被逐项 OSError 隔离兜底，但持续失败）；`...` 通过校验 |
| Symlink/Junction | ⚠️ 半覆盖 | 归档侧强（P2-005）；**扫描侧 Python 3.11 pathlib `**` 不识别 Windows junction**（仅 symlink tag）→ junction 环路可致递归失控（3.12+ 已修，本项目 pinned 3.11） |
| 图像解压 | ✅ | MAX_IMAGE_PIXELS 由 settings 强制且校验器禁用禁用（`settings.py:133-142`）；DecompressionBomb 双路径映射隔离；缩略图不带 EXIF（隐私剥离） |
| 公式注入 | ✅（小缺口） | CSV+Excel 每格 `'` 前缀（`= + @ \t \r` 及非数字 `-`）；HTML 全转义。OWASP 亦列的前导 `\|` 未中和 |
| SQL 注入 | ✅ | 全参数化；f-string 仅生成 `?` 占位与常量子句 |
| **模型完整性** | ❌ fail-open | `is_available` 仅查目录非空；`download_models.py` 有 SHA-256 机制但 **EXPECTED_SHA256 为空串**，CI 明传 `--allow-unverified` 且带移除 TODO（`ci.yml:46-48`）——被篡改/截断模型包目前可通过 |
| 配置校验 | ✅ | pydantic-settings 全字段校验（URL sqlite-only、worker 边界、阈值边界、像素下限、冲突策略枚举） |
| 导入输入 | ✅/⚠️ | 逐行错误隔离 + 行号回显；但 Excel 读取全量入内存无行上限（本地信任边界内的 DoS 面） |
| 导出原子性 | ⚠️ | 无 temp+rename；导出中断留半文件（用户可见但可重导） |

---

## 12. Performance

**结论：识别管线已经两轮证据驱动优化（累计 ~2.2×），当前性能满足目标；无需为优化而优化。**

| 项 | 事实 | 评价 |
|---|---|---|
| 人脸识别 | ADR-032/033：2600 张串行 656.9s → 332.0s（1.98×）；4-worker 11.22 photos/s（2.22×）；死重模型剔除（landmark/genderage）有 spike 证据链 | ✅ 已达标，W2-3=A 有意收尾 |
| 插件查询 | ADR-029：18.2×（N+1 → 批量联查） | ✅ |
| 大批量扫描 | 单 UoW 含逐张 SHA-256 —— 写锁长持有（见 D-1 锁风险） | ⚠️ 与并发相关非性能本身 |
| 导出 | 全内存收集 + openpyxl 整簿；无流式 | ⚠️ 大库（数万行+）内存受限；当前库规模下可接受 |
| 归档 preview | Planner N+1 仓储读在 UI 线程 | ⚠️ 大目录可感 |
| 缩略图 | 异步 + 去重 + 内容寻址缓存 | ✅（渲染断点除外） |
| 基准工具 | `tools/bench_recognition.py` / `bench_plugin_search.py` / 2 个 spike 入库可复跑 | ✅ 性能治理有证据链 |

---

## 13. Cross-platform Readiness

**结论：三 OS CI 真实跑通（含 AI + UI 强制测试）是强背书；但"安装形态级"路径假设使 macOS 就绪度显著低于 Windows。**

| 维度 | Windows | macOS |
|---|---|---|
| 源码/clone 运行 | ✅ 实测（本次体检环境） | CI 绿灯背书（同套件）；无本机长期使用证据 |
| 路径处理 | pathlib 全面、无硬编码盘符/反斜杠拼接 | 同左 ✓ |
| 数据库位置 | ⚠️ CWD 相对——快捷方式"起始位置"不同即换库 | ❌ Finder 双启 CWD=`/` 必换库 |
| 安装摩擦 | ❌ insightface 需 MSVC C++ 编译 | ❌ insightface 本地编译（需 Xcode CLT） |
| 模型分发 | 手动脚本下载，CWD 相对 `resources/models` | 同左 |
| 保留文件名/junction | ❌ 未净化保留名；junction 环路递归风险 | n/a |
| 长路径 | ⚠️ 无 `\\?\`/longPathAware 处理（深树归档逐项 FAILED 兜底） | n/a |
| App 打包 | 无（ADR-031 source-only） | 无 .app bundle；无 retina/菜单栏特判（Qt6 默认可覆盖） |
| 已验证假设 | pytest 三平台 × py3.11 全绿（CI 实证） | offscreen Qt + 真实模型推理 + UI 测试（CI 实证） |

**判定**：不得声称"跨平台完成"。准确表述：**三平台测试矩阵绿 + Windows 源码形态实测可用；macOS 无使用态证据且受 CWD 路径与编译安装双重制约。**

---

## 14. Release Readiness

**结论：按 ADR-031 源码形态，技术用户今日即可用（GitHub 已有 v2.2.0 Release）；面向目标受众的可交付 v1.0 尚有明确距离。**

| 发布要素 | 状态 | 说明 |
|---|---|---|
| 受支持运行形态 | ✅ | clone + venv + `pip install -r requirements/base.txt` + `python main.py`（ADR-031；user-guide 链路准确） |
| wheel/sdist | ⚠️ | 按裁决仅为"源码元数据产物"，但 Release 持续挂载且包内无依赖声明/入口/警示元数据——误装风险由用户承担 |
| Installer / 打包 | ❌ | 无 PyInstaller/MSI/NSIS/.app；ADR-031 方案 B 未触发 |
| 首启体验 | ⚠️ | .env 非必需（有默认+告警）✓；但模型包手动下载（300MB）+ insightface 编译 + ARCHIVE_ROOT 手配 .env |
| 数据库初始化/迁移 | ✅ | 首启自动建库 + Alembic upgrade head；损坏库 → 启动崩溃（无提示无修复） |
| 日志 | ✅ | loguru + 轮转（10MB）+ LOG_DIRECTORY 可配 |
| 错误恢复 | ⚠️ | 任务级错误弹窗/逐项隔离良好；**库级**（备份/恢复/损坏修复）缺位 |
| 升级路径 | ⚠️ | Alembic 迁移体系在位（未来可升级）；但 CWD 相对库位置使"升级后还找得到旧库"依赖启动目录习惯 |
| 用户文档 | ✅/⚠️ | user-guide 链路准确；FAQ 插件菜单宣传与 P-1 失效相悖；`installation.md` "3.11（不向后兼容）"表述过强 |
| 版本链 | ✅ | 2.2.0 三处一致；CHANGELOG 2.0.0 BREAKING 有登记 |

**发布准备度分级**（按任务书四档）：
- **Development Ready：✅ 已达到**（主路线图 15 步 + Phase B + Phase 4.2–9 全部落地，四门全绿）
- **Beta Ready：✅（限技术用户 + Windows 优先）**——前提是先修 §4.2 三项功能失效与 W-2/W-3
- **Release Candidate：❌**——差：数据安全底线（备份/损坏处理/库位置）、3 项失效修复、模型摘要固定
- **Production Ready：❌**——再加：分发形态（方案 B/installer）、首启体验、i18n 决策、对非技术用户的支撑链

---

## 15. Known Issues（重验证与重新分类）

对 `.ai/KNOWN_ISSUES.md`（v1.7.0）逐条以当前 HEAD 重验证：

| ID | 原登记 | 本次重验证 | 重新分类 |
|---|---|---|---|
| LIMIT-001 | 真实缺模型 E2E 未入 CI（Open/Low） | 仍成立：CI 以模型下载为前提，缺模型→UI 链 E2E 仅单测/组件级覆盖 | **KNOWN LIMITATION**（维持） |
| LIMIT-002 | 识别取消粒度 batch-level（Open/Low） | 仍成立：`raise_if_cancelled` 仅批边界；另发现 scan/import cancelled 信号未接线（新 F-2，独立于本条） | **KNOWN LIMITATION**（维持） |
| F-002（审计级 flake） | match 控制器线程池时序，全量偶发、单跑 ×2 稳定 | **状态恶化**：本轮全量 1 失败 + **单跑 ×2 均失败**；失败点移至 `controller.is_running` 守卫断言（持久化断言通过）。"单跑稳定"复判口径失效；仍属测试时序问题而非生产缺陷 | **IMPORTANT**（升级；修复或重设计该测试应进入下一轮议程，解除"禁止修复"前需 owner 重新定性） |
| ISSUE-018 | 已于 ADR-031 by-design 终结 | 终结有效；但 D-3（CWD 相对库位置）在**源码形态内**仍有真实用户影响（ADR 只终结了"安装态"语境） | **STALE / RESOLVED**（原条目）；CWD 问题另立新 Finding |

**本次体检新发现（不入 KNOWN_ISSUES——本次为只读体检；建议 owner 决策后由开发轮登记）**：

| 编号 | 发现 | 拟分类 |
|---|---|---|
| F-1a | 插件 UI 死路径（P-1） | RELEASE-BLOCKING（对外宣称的功能不可用） |
| F-1b | 缩略图不渲染（P-2） | RELEASE-BLOCKING（核心浏览体验缺失） |
| F-1c | Excel 导入断线（P-3） | IMPORTANT |
| F-2 | scan/import cancelled 信号未接线（W-2） | IMPORTANT |
| F-3 | Scan 无单飞防护（W-3） | IMPORTANT |
| F-4 | 导入无事务 + 无 identity 行重复导入（§5 环节1） | IMPORTANT（数据完整性） |
| F-5 | 无 WAL/busy_timeout（D-1） | IMPORTANT（并发可达故障） |
| F-6 | 零备份 + 损坏库启动崩溃（D-2） | IMPORTANT（发布前置） |
| F-7 | 数据库/模型/`.env` 路径 CWD 相对（D-3） | IMPORTANT（macOS 发布阻塞） |
| F-8 | 生产并行路径整批末次持久化（§5 环节5） | IMPORTANT（崩溃丢批） |
| F-9 | 模型摘要未固定 + CI `--allow-unverified` | IMPORTANT（供应链完整性） |
| F-10 | Windows 保留名/非法字符未净化 | NON-BLOCKING |
| F-11 | junction 环路递归（3.11） | NON-BLOCKING |
| F-12 | PROJECT_STATUS 未随 Phase 9 更新 + 悬空 `docs/health-check` 指针 | IMPORTANT（文档漂移，流程违规） |
| F-13 | search JOIN 无 DISTINCT / 无"未匹配"哨兵 | NON-BLOCKING |
| F-14 | QRunnable autoDelete 悬引用竞态 | OBSERVATION |
| F-15 | 语言设置为无实现占位控件 | NON-BLOCKING |
| F-16 | 导出无原子写 / 全内存 | NON-BLOCKING（当前规模） |
| F-17 | app↔presentation 循环 import（文档化规避） | OBSERVATION |
| F-18 | InMemory 孤儿缩略图缓存 / 大小写重复注册 / user_version 死状态 / migrations 双跑 / ModelPackMissing 双定义 / 空 common/ / 死脚手架目录 | OBSERVATION（打包一组） |

---

## 16. Feature Inventory

| ID | Feature | Status | Evidence | User Value | Risk | Release Impact |
|---|---|---|---|---|---|---|
| FEAT-01 | 人员导入（txt/csv） | COMPLETE | `import_people_service.py` + UI→Worker 链 + 查重 | 高（数据入口） | 无事务/无 identity 重复（F-4） | 非阻塞 |
| FEAT-02 | 人员导入（Excel） | **PARTIAL（断线）** | 读取器在、装配未接（`app/services.py:140`）+ UI 放行 .xlsx | 高（Step 5 名称即 Excel Import） | 选 xlsx 即错 | **RELEASE-BLOCKING（名实不符）** |
| FEAT-03 | 目录扫描/注册 | COMPLETE | `scan_and_register_photos_service.py` 全 UoW + 幂等 | 高 | 无变更对账（有意缺） | 非阻塞 |
| FEAT-04 | EXIF 元数据 | COMPLETE | `pillow_photo_metadata_reader.py` 三级回退 | 高 | mtime 回退语义 | 非阻塞 |
| FEAT-05 | 缩略图生成/缓存 | COMPLETE（后端） | generator+cache+异步加载 | 高 | **渲染断点 P-2 → 用户不可见** | **RELEASE-BLOCKING** |
| FEAT-06 | 人脸检测/识别/匹配 | COMPLETE | InsightFace 链 + 并行 + add_many + 恢复语义 | 高（核心 AI 价值） | 崩溃丢批（F-8） | 非阻塞 |
| FEAT-07 | 识别审核（approve/reject） | COMPLETE | ReviewDialog + 逐条 UoW + 幂等 | 高（人机闭环） | UUID 行可读性 | 非阻塞 |
| FEAT-08 | 筛选（status/person/date） | COMPLETE | Phase 9 P0：FilterBar 三轴 + AND 矩阵测试 | 高 | DISTINCT/哨兵小缺口 | 非阻塞 |
| FEAT-09 | 归档（预览/冲突策略/dry-run） | COMPLETE | Planner→Executor + 包容校验 + 成功态幂等 | 高（核心产出） | FS/DB 窗口分歧（兜底） | 非阻塞 |
| FEAT-10 | 导出 ALL/FILTERED（CSV/XLSX/HTML） | COMPLETE | Phase 5/7 闭环 + 泄漏矩阵测试 + 注入防护 | 高 | CURRENT_BATCH 诚实拒绝 | 非阻塞 |
| FEAT-11 | CURRENT_BATCH 导出 | DEFERRED | 契约 D1-D5 + UI 禁用 + ValueError | 低（批次概念未建） | — | 非 v1.0 必需 |
| FEAT-12 | 重复图片检测 | COMPLETE（只读） | 单 SQL 组查询 + 只读报告 | 中 | 处置缺位（有意） | 非阻塞 |
| FEAT-13 | 插件系统（读+import_people） | **PARTIAL（UI 断线）** | 后端全链 + loader；`main_window.py:191` 死路径 → 动作不出现 | 中（扩展性承诺） | **P-1 → 用户不可见** | **RELEASE-BLOCKING（对外承诺）** |
| FEAT-14 | 设置（主题/路径/阈值/并发） | PARTIAL | settings_dialog 闭环；ARCHIVE_ROOT 无 UI；语言占位 | 中 | 占位控件（F-15） | 非阻塞 |
| FEAT-15 | CLI（scan/archive/backfill） | PARTIAL | `main.py` 三子命令经 Application | 中 | import/match/export 无 CLI | P1 增强 |
| FEAT-16 | 持久化（Alembic 体系） | COMPLETE | 001+002 + FK 强制 + UoW | 高 | 备份/锁配置（F-5/6） | 发布前置 |
| FEAT-17 | 照片/人员删除、库对账 | MISSING | 零 DELETE API | 中（长期库运营必需） | 需 ADR+schema 门 | P2，非 v1.0 阻塞 |
| FEAT-18 | 安装态分发 | BLOCKED | ADR-031 by-design；方案 B 未触发 | 高（对非技术受众） | — | v1.0 交付决策点 |
| FEAT-19 | 日志/配置体系 | COMPLETE | loguru 轮转 + pydantic-settings 校验 | 中 | — | 非阻塞 |
| FEAT-20 | i18n | PLACEHOLDER | 语言下拉零实现 | 低（当前受众） | 占位控件 | 建议明示 Out-of-Scope |

---

## 17. Maturity Score

| 维度 | 得分 | 依据摘要 |
|---|---|---|
| Architecture | **88** | 分层实测合规、组合根干净、协议驱动；扣分：循环 import 规避式存在、矩阵文档缺口、PySide6-in-infra 文本冲突 |
| Code Quality | **85** | ruff/mypy 全绿、类型注解与 docstring 纪律、错误隔离模式一致；扣分：死脚手架、双定义异常、docstring 失实（photo_list_model） |
| Feature Completeness | **72** | 20 项中 13 COMPLETE；扣分：3 项断线（Excel 导入/缩略图渲染/插件 UI）、删除与对账 MISSING、CLI 不对等、i18n 占位 |
| Testing | **78** | 570 测试、真实 SQLite/真链路 E2E、三 OS CI、skip 纪律；扣分：F-002 恶化、无 conftest/覆盖率/import-linter、对话框直测缺、CI skip 守卫失效 |
| Security | **82** | 穿越/炸弹/注入/SQL 全防且测试锁定；扣分：模型完整性 fail-open、Windows 文件名语义、junction 递归 |
| Reliability | **68** | 逐项隔离+UoW+诚实 DTO 良好；扣分：导入部分提交、并行匹配丢批、无备份/损坏恢复、锁配置缺、取消接线断 |
| Performance | **80** | 两轮证据驱动优化 2.2×、基准入库、查询 18.2×；扣分：导出全内存、planner UI 线程 N+1（当前规模可接受） |
| UX | **65** | 核心流可用、确认门齐；扣分：缩略图不可见、UUID 审核行、空态缺、占位语言项、取消状态卡死、状态列缺失 |
| Data Integrity | **70** | FK 强制、扫描/审核/归档事务正确；扣分：导入部分提交、匹配丢批、无备份、CWD 漂移库、大小写重复 |
| Cross-platform | **62** | 三 OS CI 真实绿；扣分：CWD 路径假设、保留名/junction/长路径、macOS 使用态零证据、无打包 |
| Packaging / Release | **45** | 源码形态文档准确、版本链一致；扣分：无 installer、wheel 无警示挂载、模型手动下载无校验、insightface 编译门槛、首启链路长 |
| Documentation | **70** | .ai 体系设计优秀（指针化+触碰清单）；扣分：**PROJECT_STATUS 漂移 + 悬空指针（流程违规现行犯）**、FAQ 失实宣传、docstring 失实 |
| **Overall** | **73 / 100** | 工程底座优于典型同规模项目；失分集中在"最后可见一公里"（UI 断线）与发布工程 |

---

## 18. Completion Estimate

> 估算口径：以"当前 HEAD 实测证据"对照各阶段的完成定义（Definition of Done），非日历承诺。

### Audit：**95%**

- 已完成：Step 0.5–15 全链、Phase 4.2/5/6/7 的 Feature 级 Final Audit（AC 逐条对账）、Phase 6 完整性审计、Phase 8 Contract Revision、Phase 9 P0 DoD 23/23——合计 31+15+8+23 项 AC 有双重证据（代码+测试）。
- 本次全项目体检补上了缺的一块：**跨 Feature 的产品级视角**（3 项断线功能即此类——它们各自通过了所属 Phase 的 AC，但"用户看得到"从未被验证）。
- 剩余 5%：F-002 需要一次重新定性（flake→修复或重设计测试）、文档漂移修复后的一致性复核。**不建议再开新的系统性 Audit Phase**（项目已出现审计边际收益递减的明确信号——Phase 6–9 的 Finding 均为 F1/P3 级）。

### Product：**82%**

- 计入：主管线 10 环节 7 闭环 + 筛选/导出/归档全部可用 + 模型管线经性能与安全加固。
- 未计入（-18%）：3 项用户可见断线（≈-8%）、库管理删除/对账缺失（≈-4%）、CLI 对等缺口（≈-2%）、空态/可读性 UX 欠账（≈-2%）、语言占位等（≈-2%）。
- 依据：Feature Inventory 20 项中 13 COMPLETE / 3 PARTIAL(断线) / 1 PARTIAL / 1 DEFERRED / 1 MISSING / 1 BLOCKED。

### Release：**55%**（以"面向目标受众的可交付 v1.0"为 100% 基准）

- 已有：源码形态运行链完整 + 自动化迁移 + 日志 + 版本链一致 + CHANGELOG + GitHub Release 流程（4 个 tag 已发布）。
- 缺失（-45%）：分发形态裁决与实现（ADR-031 方案 B / installer / 便携包 ≈-20%）、数据安全底线（备份/损坏恢复/库位置 ≈-10%）、3 项断线修复 + 取消接线（≈-8%）、模型摘要固定与首启引导（≈-4%）、i18n 决策与用户文档收口（≈-3%）。
- 备注：若 v1.0 定义维持 ADR-031 现状（仅源码形态、技术用户），则 Release ≈ 75%（差数据安全底线 + 断线修复即可 RC）；两个口径的差值正是 owner 需要裁决的**分发定位**问题。

### 「如果今天停止开发，PhotoArchiver 处于什么状态？」

- 一个**工程质量良好、可被技术用户立即投入使用的桌面照片归档工具**（源码形态，Windows 最顺）：核心 AI 归档流程真实闭环，数据库安全，导出可用。
- 但它**不是一个面向目标受众（学校/档案馆等）的完整产品**：插件与缩略图两处"看起来有、实际没有"，Excel 导入名不符实，库只进不出，无备份，换目录启动会静默换库。
- 项目管理面：文档体系进入轻度漂移（PROJECT_STATUS 落后 Phase 9 一轮；审计报告指针悬空）——若长期停摆，漂移会放大。

### 距离可交付 v1.0 的最少工作（Minimum Path to v1.0）

1. **修复 3 项断线功能**（插件路径 / 缩略图 delegate / Excel 读取接线）——~1.5 天
2. **数据安全底线**：WAL+busy_timeout、库位置策略（项目锚定或用户目录）、损坏库友好失败、最小备份指引——~2 天
3. **取消接线 + 扫描单飞 + 导入事务化**——~1.5 天
4. **模型摘要固定**（补 EXPECTED_SHA256 + CI 移除 --allow-unverified）——~0.5 天
5. **文档收口**（PROJECT_STATUS 刷新、悬空指针清理、FAQ 修正）——~0.5 天
6. **发布工程裁决**：owner 拍板 ADR-031 方案 B（console 入口 + package_data + 用户目录默认值 + 打包脚本）或维持源码形态并出"便携 zip"指引——0.5~3 天（视裁决）
7. **发布门**：全量四门 + 手工验收清单 + tag——~0.5 天

**合计 ≈ 6.5–9.5 个 AI 工作日**（详见 DEVELOPMENT_ROADMAP.md）。

---

## 19. Gap Matrix

| Gap | Severity | User Impact | Technical Impact | Effort | Priority | Blocking? |
|---|---|---|---|---|---|---|
| G-01 插件 UI 死路径（P-1） | S1 | 插件功能完全不可见，文档仍宣传 | 一行路径修复 + 补 1 测试；暴露"_load_plugins 无测试" | XS | P0 | Release-blocking（对 v1.0 对外承诺） |
| G-02 缩略图不渲染（P-2） | S1 | 照片浏览无预览图 | 需 QStyledItemDelegate/DecorationRole（新 UI 组件，约 40-80 行）+ docstring 修正 | S | P0 | Release-blocking（核心体验） |
| G-03 Excel 导入断线（P-3） | S1 | Step 5 名实不符；选 xlsx 即错 | 扩展名 dispatch 注入两个 reader；xlsx 路径需测试（当前 Excel reader 零测试） | S | P0 | Release-blocking（名实不符） |
| G-04 取消信号未接线 + 扫描无单飞（W-2/W-3） | S1 | 取消后状态卡死；并发扫描互相干扰 | main_window 接线 + 守卫 + reporter 绑定复核 | S | P0 | RC-blocking |
| G-05 无 WAL/busy_timeout（D-1） | S1 | 扫描中审核可遇 "database is locked" | PRAGMA 两行 + 锁行为测试 | XS | P0 | RC-blocking |
| G-06 导入无事务 + 无 identity 重复（F-4） | S1 | 中断=半库人员；重复导入涨重 | UoW 包裹或分批提交策略（需裁决原子性口径）；identity 空值查重 | M | P0 | RC-blocking（数据完整性） |
| G-07 并行匹配整批末次持久化（F-8） | S1 | 崩溃丢整批分析（默认 4 workers 即此路径） | 分片 flush（每 N 张 add_many）需等价性测试 | M | P1 | 非阻塞（有恢复语义兜底） |
| G-08 数据库位置 CWD 相对（F-7） | S1 | 换目录启动=静默新库（macOS 必现） | 路径锚定策略需 owner 裁决（触碰 ADR-010/022 语境） | M | P0（若 v1.0 含 macOS）/P1 | v1.0-macOS blocking |
| G-09 零备份/损坏库硬崩（D-2） | S1 | 数据安全事故无缓冲 | 启动校验 + 友好失败 + 备份指引/自动副本 | S–M | P0 | RC-blocking |
| G-10 模型摘要未固定（F-9） | S2 | 供应链完整性缺失 | 补 digest + CI 去 --allow-unverified（含 CI 验证轮） | S | P0 | RC-blocking（安全门） |
| G-11 F-002 恶化（单跑不稳定） | S2 | 无（测试侧） | 测试时序重设计或修守卫释放路径；需先解除"禁止修复"定性 | S–M | P1 | 非阻塞（CI 红信号噪声） |
| G-12 Windows 保留名/非法字符净化（F-10） | S3 | 特定人名/文件名归档持续失败 | ArchivePath VO 补净化规则（有测试基建） | S | P1 | 非阻塞 |
| G-13 junction 递归（3.11）（F-11） | S3 | 极端目录结构扫描失控 | 扫描前 junction 检测或文档警示（3.12 缓解） | S | P2 | 非阻塞 |
| G-14 PROJECT_STATUS 漂移 + 悬空指针（F-12） | S2 | AI 上下文失真（下一轮 AI 拿到错误基线） | 单文件文档修订 + 指针清理 | XS | P0 | 流程阻塞（非产品） |
| G-15 CLI 对等（import-people/export） | S3 | 批处理/自动化用户缺失入口 | 两个子命令复用既有服务 | S | P1 | 非阻塞 |
| G-16 照片删除/库对账 | S2 | 库只进不出（长期运营硬伤） | 需删除语义 ADR + FK 级联验证 + UI 确认 | L | P2 | 非 v1.0 |
| G-17 CURRENT_BATCH 批次持久化 | S3 | 批次导出概念缺失 | schema/migration + owner 门 | M | P2 | 非 v1.0 |
| G-18 导出原子写/流式 | S3 | 中断半文件；超大库内存 | temp+rename 简单；流式重构大 | S（原子写）/XL（流式） | P2 | 非阻塞 |
| G-19 i18n 占位控件（F-15） | S3 | 假选项误导 | 移除控件或立项 i18n（XL） | XS（移除）/XL（实现） | P2 | 建议移除 |
| G-20 循环 import / 矩阵文档化（A-1~A-4） | S3 | 无直接用户影响 | 文档修订为主；解环需 MainWindow 解耦重构 | XS（文档）/M（解环） | P2 | 非阻塞 |

---

## 20. Risks

| # | 风险 | 类别 | 触发条件 | 缓解 |
|---|---|---|---|---|
| R-1 | **文档体系再度漂移**：PROJECT_STATUS 已落后一个 Phase；触碰清单机制（AI_ONBOARDING §12）在 Phase 9 未被执行 | 流程 | 任何不刷新状态文档的开发轮 | Phase 9 补登 + 把"状态文档刷新"纳入 DoD 硬门 |
| R-2 | **"单跑稳定"口径失效后，CI/本地全量长期带红**：团队对 pytest 失败敏感度钝化 → 真回归被淹没 | 质量 | F-002 持续失败期间 | 尽快定性修复或隔离标记（需 owner 解除禁修） |
| R-3 | **数据丢失**：无备份 + 并行匹配丢批 + 导入部分提交 + CWD 换库 | 数据 | 崩溃/误操作/换目录启动 | G-05/06/08/09 组合修复（发布前） |
| R-4 | **分发定位悬置**：ADR-031 方案 B 无触发主，而目标受众天然需要安装态 → 项目长期停在"技术用户工具"形态 | 产品 | v1.0 定义不含分发 | owner 明确 v1.0 受众与形态，触发或不触发方案 B |
| R-5 | **模型供应链**：digest 空 + CI --allow-unverified 已成惯性（TODO 无主） | 安全 | 模型源变更/镜像篡改 | G-10 |
| R-6 | **insightface 1.0.1 生态老化**：sdist-only、deprecation warning（本次 pytest 实测 `estimate` 弃用，2.2 版将移除）、numpy 大版本耦合 | 依赖 | 上游升级/新平台 | 锁定现状 + 监控；不主动替换（无需求） |
| R-7 | **Python 3.11 junction 盲区与 3.12+ 行为差异** | 平台 | Windows 目录含 junction | 升级 Python 下限（需依赖门）或扫描防护 |
| R-8 | **审计边际递减**：连续 6 轮 Audit/Contract Revision 的 Finding 已降至 F1/P3——继续审计不再产出等值信息 | 流程 | 再开 Audit Phase | 本报告为唯一全项目体检；转入开发轮 |

---

## 21. Final Assessment

**PROJECT HEALTH: Attention Required**

PhotoArchiver 是一个**架构纪律与工程文化显著优于同类项目**的代码库：分层契约实测成立、测试真实度（真 SQLite、真链路、真模型）罕见地高、性能与安全工作有完整证据链、文档体系设计（指针化 + 触碰清单）理念先进。

它当前的真实短板不在"写得好不好"，而在两处：

1. **可见性断层**——三次 Feature 级审计都PASS了的插件、缩略图、Excel 导入，在用户眼前是坏的。根因是验收始终以"AC 对账"进行，从未包含"启动真实应用看一眼"的冒烟验证。建议未来 DoD 增加一条真实启动冒烟（含插件加载与列表渲染断言）。
2. **发布工程未启动**——数据安全底线（备份/锁/库位置）与分发形态是 v1.0 的两块主梁，当前均为缺位或悬置状态。

** maturity 73/100，Audit 95% / Product 82% / Release 55%。** 项目不需要更多审计，需要一次以"用户可见的正确性 + 数据安全 + 发布裁决"为主线的**修复与发布轮**。开发计划见 `docs/roadmap/DEVELOPMENT_ROADMAP.md`。

---

> 本报告为只读体检产物，未修改任何生产代码、测试、规则、契约或 schema。
> 所有 Finding 均附文件:行号证据；新发现问题未登记入 KNOWN_ISSUES.md（保持本次只读边界），登记动作留给 owner 决策后的开发轮执行。

PROJECT HEALTH CHECK — COMPLETE
OWNER DECISION REQUIRED
