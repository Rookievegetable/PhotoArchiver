# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**“项目现在开发到哪里了？”**
>
> 每次开发结束后刷新；不保留历史状态。
>
> Version: 1.7.0 · Last Updated: 2026-08-25 · Status: Live

---

## 1. Roadmap（开发路线图概览）

权威 15 步路线图：`.ai/business/roadmap.md`。

| Step | 名称 | 状态 |
|---|---|---|
| 0.5–11 | Walking Skeleton、基础设施、Domain、导入、扫描、缩略图、人脸识别、归档 | ✅ Completed |
| 12–14 | Main UI、Settings、Export | ✅ Completed |
| 15 | Plugin System | ✅ Completed |

M1–M7 及 Step 0.5–15 已全部完成；阶段 B 业务增强 B1–B5 与收官加固阶段 0–3 均已落地。

---

## 2. Current Step（当前开发阶段）

项目主路线图已完成，当前处于完成后的架构加固与可选能力扩展阶段。

- 阶段 0（质量基线与文档收口）：✅ 完成。
- 阶段 1（PluginContext 公共边界加固，ADR-026）：✅ 完成。
- 阶段 2（Alembic 接管 Schema DDL，ADR-027）：✅ 完成。
- 阶段 3（插件写能力 import_people，ADR-028）：✅ 完成（仅 import_people；export 续暂缓）。

当前无已登记的未解决问题；`KNOWN_ISSUES.md` 为空。

---

## 3. Project Status（项目当前状态）

| 范围 | 状态 | 当前事实 |
|---|---|---|
| 15 步产品路线图 | ✅ | Step 0.5–15 全部已实现并验证。 |
| 阶段 B 业务增强 B1–B5 | ✅ | 重复图片、搜索/筛选、批量归档、HTML 导出、只读插件上下文均已落地。 |
| 阶段 0 质量基线 | ✅ | 质量门和文档收口已完成。 |
| 阶段 1 PluginContext | ✅ | ADR-026：`ContextAwarePlugin` 生命周期、Plugin DTO 边界、结构化 `PluginReport`。 |
| 阶段 2 Schema DDL 所有权 | ✅ | ADR-027：`002_split_create_ddl` 为 Schema DDL 唯一权威。 |
| 阶段 3 插件写能力 | ✅ | ADR-028：`PluginContext.import_people` 已实现——插件经 `PluginImportPeopleCommand`/`PluginImportPersonRow` 写入人员实体（宿主补 row_number），结果 `PluginImportResult` 以 str ids 脱 Domain；无宿主审批门；export 续暂缓留后续轮单独裁决。示例插件 `examples/plugins/import_people_demo_plugin.py` 端到端演示。 |
| CI | ✅ | GitHub Actions 三 OS 矩阵、模型缓存与 AI/UI 断言已启用。 |

当前 HEAD：阶段 3 实现提交 + 状态文档同步提交（均本轮）。前置基线：`cdb0fd7`（ADR-028 登记）、`a76c8ed`（阶段 2 状态同步）、`64ec47a`（阶段 2 实现）。

---

## 4. Current Modules（当前模块状态）

| 模块 | 状态 | 关键位置 |
|---|---|---|
| Logging / Configuration | ✅ | `infrastructure/logging/`、`infrastructure/config/` |
| Database | ✅ | Alembic 已启用；`002_split_create_ddl` 为 Schema DDL 唯一权威（ADR-024、ADR-027）。 |
| Domain / Import / Scan / Thumbnail | ✅ | `domain/`、`application/services/`、`infrastructure/`；`ImportPeopleService.import_rows` 提供预解析行导入入口（文件路径 `execute()` 委托同一落库核心）。 |
| Recognition / Review | ✅ | InsightFace detect/recognize/match 与审核闭环已完成。 |
| Archive | ✅ | Planner → Plan → Executor，支持 dry-run、captured_at 和批量筛选归档。 |
| UI / Settings / Export | ✅ | 主窗口、设置闭环、Excel/CSV/HTML 导出和 Worker 路径已完成。 |
| Plugins | ✅ | 发现/加载/生命周期 + PluginContext 读方法（search_photos/detect_duplicates）+ 写方法 `import_people`（ADR-028）；宿主经通用 PluginReportDialog 渲染插件报告。 |

### 数据库 Schema

`PRAGMA user_version = 4`。Schema 演进由 `alembic/` 与 `alembic_runner.py` 管理；表与索引 DDL 属于 Alembic 迁移（ADR-027）。阶段 3 未改 Schema、未新增依赖。

---

## 5. Last Session（最近一次开发记录）

| 项目 | 值 |
|---|---|
| 时间 | 2026-08-25（本地） |
| 生成者 | Cline |
| 会话范围 | 阶段 3（ADR-028 插件写能力 import_people）实现收尾。 |
| 已完成 | ① 修正草案前提偏差——`docs/development/phase3-adr-draft.md` §1.2 误载 ImportPeopleCommand 持 rows（实际为 source_path 形状），半成品代码照抄导致运行时 TypeError；新增 `ImportPeopleService.import_rows()` 承接预解析行路径并在草案加勘误注。② `PluginContextService.import_people` 改调 `import_rows`，移除对不存在命令形状的构造。③ bootstrap 注入第 4 参 `services.import_people`。④ `PluginImportResult.succeeded` 对齐项目惯例改为属性；三个 import DTO 补入 `application/dtos/__init__.py` 导出。⑤ 测试扩展：test_plugin_context_service 新增 4 个映射/真实链路用例并更新 Protocol 白名单断言（含 import_people）；test_plugin_dtos 新增 6 个 DTO 边界用例。⑥ 新增端到端示例插件 import_people_demo_plugin（静态依赖审计自动覆盖）。⑦ 文档同步：plugin-guide.md 写能力章节 + 本状态文件刷新。⑧ Review 处置（依据 review-rules.md §18.1）：两项 Minor 修毕——import demo 样例行全量补 identity 使幂等声明成立并修正 demo/指南措辞（限定幂等仅覆盖带 identity 行）；plugin-context-design.md 头部加 ADR-028 部分取代注记。⑨ P0 收口执行——四个未跟踪过程文档经内容逐份核验后物理删除（dev-plan-phase-b B1–B5 方案已全量实施；REV-AI-001~007 草案已 100% 并入 review-rules.md §18.1；B1 双 Review 报告全部修复项闭环，外部 M-1 backfill 单字段替换经源码锚点复核已落地）+ shell 故障垃圾文件清理；按 audit-methodology 五维比对完成阶段 2+3 轻量复审（规则内部一致性 / 规则 vs 代码 / 规则 vs docs / 重复承载 / 占位空文档均无新增矛盾）。⑩ P1-B 技术债轮启动——产出 `docs/development/phase4-adr-draft.md` 前置门草案（三项技术债证据与五个裁决点 B4-1~B4-5）；新增零依赖基准脚本 `tools/bench_plugin_search.py` 并实测 N+1 基线：插件查询调用次数恒等于照片数（100/600/2600 张 → 47.1/266.8/1137.9 ms，线性），2600 张库单次查询超 1.1 秒且运行于 UI 线程同步路径。 |
| 当前质量门 | `ruff check .` 通过；`mypy src`：168 个源文件无问题；`pytest -q`：402 passed、8 skipped。 |
| 工作区 | 过程审阅文档仍未跟踪：`dev-plan-phase-b.md`、`review-b1-merged.md`、`review-report-external.txt`、`review-rules-addition-draft.md`；它们不是已批准的项目状态。 |
| Remaining | 无已登记阻塞项。已知历史文档瑕疵：phase3-adr-draft.md §1.2 命令形状描述错误已加勘误注（草案按历史保留原文，正确契约以代码 docstring 与本文件为准）。遗留待裁决：docs/{api,design,user-guide} 三个空目录的填实或删除（归入 P1-A 用户文档任务）。 |
| Next Step | **等待 phase4 草案拍板**——五个裁决点 B4-1~B4-5 见 `docs/development/phase4-adr-draft.md`（兼容路径移除轮次 / N+1 批量查询方案选型 / 基准脚本归属 / export 用例确认 / 审批门）；M8「可发布」里程碑候选并行待排期。 |

---

## 6. Next Step（下一步开发计划）

阶段 3 已收尾。后续均为独立候选项，开工前先由项目负责人裁决排期：

1. 在下一个主版本评审 `enable(context)` 兼容路径的移除。
2. 性能加固（识别管线批量吞吐等）。
3. export 插件写能力是否开放的单独裁决（YAGNI：ExportController 宿主路径已可用）。
4. 如真实用例出现高危写操作，再评审宿主审批门（ADR-028 裁决点 2=B/C）。

---

## 7. Key Files（关键文件索引）

| 职责 | 文件 |
|---|---|
| 插件协议与上下文 | `src/photo_archiver/application/ports/plugin.py`、`src/photo_archiver/application/ports/plugin_context.py` |
| 插件上下文服务（读映射 + import_people 写编排） | `src/photo_archiver/application/services/plugin_context_service.py` |
| 人员导入服务（文件/预解析行双入口） | `src/photo_archiver/application/services/import_people_service.py` |
| Plugin import DTO | `src/photo_archiver/application/dtos/plugin_context.py` |
| 插件加载与应用装配 | `src/photo_archiver/plugins/loader.py`、`src/photo_archiver/app/bootstrap.py`、`src/photo_archiver/app/context.py` |
| 示例插件 | `examples/plugins/stats_report_plugin.py`（读）、`examples/plugins/import_people_demo_plugin.py`（写） |
| 插件设计与决策 | `docs/development/plugin-context-design.md`、`docs/development/phase3-adr-draft.md`、`.ai/ARCHITECTURE_DECISIONS.md`（ADR-026/028） |
| Schema 初始化与迁移 | `src/photo_archiver/infrastructure/database/sqlite_connection.py`、`src/photo_archiver/infrastructure/database/alembic_runner.py`、`alembic/versions/002_split_create_ddl.py` |
| 质量验证 | `tests/`、`.github/workflows/ci.yml` |

---

> 本文件只描述当前状态；历史决策见 `.ai/ARCHITECTURE_DECISIONS.md`，当前问题见 `.ai/KNOWN_ISSUES.md`，路线图见 `.ai/business/roadmap.md`。