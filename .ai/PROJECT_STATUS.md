# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**“项目现在开发到哪里了？”**
>
> 每次开发结束后刷新；不保留历史状态。
>
> Version: 1.7.1 · Last Updated: 2026-08-26 · Status: Live

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
- 阶段 3（插件写能力 import_people，ADR-028）：✅ 完成（仅 import_people；export 经 ADR-030 裁决 YAGNI 正式关闭）。
- 阶段 4（技术债轮：search_photos N+1 加固 ADR-029 + 轮次裁决 ADR-030）：✅ 完成（兼容路径移除挂账 v2.0.0；审批门续暂缓）。

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
| 阶段 3 插件写能力 | ✅ | ADR-028：`PluginContext.import_people` 已实现——插件经 `PluginImportPeopleCommand`/`PluginImportPersonRow` 写入人员实体（宿主补 row_number），结果 `PluginImportResult` 以 str ids 脱 Domain；无宿主审批门；export 写能力经 ADR-030 裁决 YAGNI 正式关闭。示例插件 `examples/plugins/import_people_demo_plugin.py` 端到端演示。 |
| 阶段 4 技术债轮 | ✅ | ADR-029：插件查询识别状态批量联查——2600 张库单次查询 1137.9ms → 62.5ms（18.2×），往返 O(N)→O(1)；ADR-030：兼容路径移除挂账 v2.0.0、export 暂缓终结、审批门续暂缓。基线工具 `tools/bench_plugin_search.py` 入库可复跑。 |
| M8 可发布里程碑 | ✅ | MIT License 落定（占位已删除）；pyproject 元数据落位（version 1.0.0 / license / classifiers / readme / description）；`.github/workflows/release.yml` 增补（tag 触发 sdist+wheel 构建并发布 GitHub Release）；`CHANGELOG.md` 建立；tag `v1.0.0` 已推送，GitHub Release v1.0.0 资产挂载确认（sdist+wheel）。 |
| M9 分发定位裁决 | ✅ | ADR-031 登记并执行完毕——运行形态定位为「源码/clone 唯一受支持」；Release v1.0.0 body 置顶安装态标注已由 owner 粘贴（2026-08-26 API 实测生效，B5-3 销账）；ISSUE-018 以 by-design 正式终结（KNOWN_ISSUES 回归空态）。 |
| v2.0.0 破坏性窗口 | ✅ | ADR-030/B4-1 兑现——旧 `enable(context)` 分发分支移除（loader 三分叉收敛为二分叉：ContextAware / 无参 enable），生产与示例代码零消费者 grep 实证；测试矩阵净减 3 个 legacy 用例（413→410 全绿）；CHANGELOG `[2.0.0]` BREAKING 标注落定；版本链 bump 2.0.0（pyproject + .env.example 示例值；settings 回退值按 configuration.md 口径保持不动）。发版链实证——tag `v2.0.0` 已推送并触发 release workflow（run 33071797649 双 job success）：GitHub Release v2.0.0 自动创建且双资产挂载 API 实测确认（wheel 220KB / sdist 152KB）；发布前实现提交 `ba3ad02` CI 三平台全绿（run 33070707134）。仅余 owner 向 body 置顶粘贴 Breaking Notes。 |
| CI | ✅ | GitHub Actions 三 OS 矩阵、模型缓存与 AI/UI 断言已启用。 |

当前 HEAD：`ba3ad02`（origin/main 同步 = 实现 `8f317a6` + B1 基准留档；tag `v2.0.0` 已指向此线并推至远端）。前置基线：`2bbbfb8`（B5-3 收官登记）、`48c7493`（photopath 跨平台修复 + AI 用例路径修复）、`cdb0fd7`（ADR-028 登记）。

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
| 时间 | 2026-08-27（本地） |
| 生成者 | Cline |
| 会话范围 | v2.0.0 破坏性窗口执行轮——兑现 ADR-030/B4-1：移除旧 `enable(context)` 插件兼容分发分支。 |
| 已完成 | ① 开工复核：`def enable(self, context…` 在 src/examples/plugins/app 生产与示例代码零命中（仅 loader 兼容分支自身 + 测试 stub + docs 使用）。② `plugins/loader.py` `_enable_plugin` 删除 `inspect.signature` 探测分支收敛为二分叉并移除 `import inspect`；模块头 / `enable_all` / `_enable_plugin` docstring 同步 v2.0.0 收敛表述（旧签名调用即 TypeError 落错误隔离，宿主续运行）。③ 测试矩阵删改——test_plugin_context.py 移除 `_LegacyEnableContextStub` 类与 2 个 legacy 用例、契约注释改两类生命周期分发；test_plugin_lifecycle_compatibility.py 整段移除兼容 section/class 并将 context=None 三路径矩阵改写为两路径版（`test_context_none_two_paths_degrade_gracefully`）。④ API 表述刷新：application/ports/plugin.py 两处「Deprecated 保留一个版本」→「已于 v2.0.0 移除」；examples/plugins/hello_plugin.py 头注同步迁移指引。⑤ plugin-guide.md §6 legacy 表述改为 REMOVED-in-v2.0.0 + 影响面说明；limits 中 export「stays deferred」陈旧表述顺手对齐 ADR-030 YAGNI 终态。⑥ 版本链 bump：pyproject.toml version=2.0.0、`.env.example` APP_VERSION=2.0.0。⑦ CHANGELOG.md 新增 `[2.0.0] - 2026-08-27` 段——Removed **BREAKING** 显著标注 + 外部插件影响面 + 迁移指引指针 + 零消费者实证注记，原 Deferred 条目中 enable(context) 子项迁出并加已执行注记。⑧ 门禁全回归：ruff ✓ / mypy 168 文件 ✓ / pytest **410 passed**（恰为 413−3 净减预期）。 |
| 当前质量门 | `ruff check .` 通过；`mypy src`：168 个源文件无问题；`pytest -q`：410 passed、0 skipped（8 warnings 为第三方库弃用提示，无失败）。 |
| 工作区 | 本轮 9 文件改动全量提交；过程脚本即建即删，无未跟踪文档遗留。 |
| Remaining | 发版序列 a) 推送 ✅（origin/main = `ba3ad02`）、b) CI 三平台全绿 ✅（run 33070707134 completed/success——破坏性变更远端矩阵真实首验通过）、c) tag `v2.0.0` 推送 + Release 自动创建 ✅（release workflow run 33071797649 双 job success；资产 wheel 220KB / sdist 152KB 挂载实测确认）。**唯一站外待办**：owner 向 Release v2.0.0 body 置顶粘贴 Breaking Notes（CHANGELOG `[2.0.0]` Removed 段文案）。 |
| Next Step | owner 粘贴 Breaking Notes 后在本文件销账，v2.0.0 轮全闭环。此后条件触发行不变：识别管线批量吞吐性能加固；真实高危插件写用例出现时再评审宿主审批门（ADR-028 裁决点 2=B/C）；非技术用户分发需求出现时按 phase5 定稿方案 B 另起前置门。 |

---

## 6. Next Step（下一步开发计划）

v2.0.0 执行轮代码/测试/文档已全部收尾（质量门全绿）。剩余为纯发版序列：

1. ~~打 tag 前：`python tools/bench_plugin_search.py` 三档库容复跑~~ ✅ 已执行（2026-08-27）：100/600/2600 张 → 5.0/16.2/63.4ms，calls 全档 = 1；对照 ADR-029 基线（2600 张 62.5ms）零回退。
2. ~~推送 + 观察 CI + push tag~~ ✅ 全部完成（2026-08-27）：`ba3ad02` 三平台全绿（run 33070707134）→ tag `v2.0.0` 推送 → release workflow run 33071797649 成功 → GitHub Release v2.0.0 创建、双资产挂载。
3. **待办**：owner 向新 Release body 置顶粘贴 Breaking Notes（取 CHANGELOG `[2.0.0]` Removed 段文案），完成后在 §5 Remaining 销账。
4. 之后均为条件触发行：识别管线批量吞吐等性能加固；真实高危插件写用例出现时再评审宿主审批门（ADR-028 裁决点 2=B/C）；非技术用户分发需求出现时按 phase5 定稿方案 B 另起前置门。

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
| 性能基线 | `tools/bench_plugin_search.py`（零依赖可离线复跑，前后对比数据见 phase4 定稿草案 §6） |
| Schema 初始化与迁移 | `src/photo_archiver/infrastructure/database/sqlite_connection.py`、`src/photo_archiver/infrastructure/database/alembic_runner.py`、`alembic/versions/002_split_create_ddl.py` |
| 质量验证 | `tests/`、`.github/workflows/ci.yml` |

---

> 本文件只描述当前状态；历史决策见 `.ai/ARCHITECTURE_DECISIONS.md`，当前问题见 `.ai/KNOWN_ISSUES.md`，路线图见 `.ai/business/roadmap.md`。