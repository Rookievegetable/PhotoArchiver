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
- 阶段 4（技术债轮：search_photos N+1 加固 ADR-029 + 轮次裁决 ADR-030）：✅ 完成（兼容路径移除原挂账 v2.0.0，已于 v2.0.0 轮兑现——见下表「v2.0.0 破坏性窗口」行；审批门续暂缓）。
- 阶段 5（识别管线吞吐加固，ADR-032）：✅ 完成——线程并行 + `add_many` 单事务批下推 + 基准工具入库（全网格基线落档；线程扩展 1.28× 弱于建议阈值，batch 批推理二轮证据已触发、待 owner 立项拍板）。

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
| 阶段 4 技术债轮 | ✅ | ADR-029：插件查询识别状态批量联查——2600 张库单次查询 1137.9ms → 62.5ms（18.2×），往返 O(N)→O(1)；ADR-030：兼容路径移除挂账 v2.0.0（已兑现，见「v2.0.0 破坏性窗口」行）、export 暂缓终结、审批门续暂缓。基线工具 `tools/bench_plugin_search.py` 入库可复跑。 |
| M8 可发布里程碑 | ✅ | MIT License 落定（占位已删除）；pyproject 元数据落位（version 1.0.0 / license / classifiers / readme / description）；`.github/workflows/release.yml` 增补（tag 触发 sdist+wheel 构建并发布 GitHub Release）；`CHANGELOG.md` 建立；tag `v1.0.0` 已推送，GitHub Release v1.0.0 资产挂载确认（sdist+wheel）。 |
| M9 分发定位裁决 | ✅ | ADR-031 登记并执行完毕——运行形态定位为「源码/clone 唯一受支持」；Release v1.0.0 body 置顶安装态标注已由 owner 粘贴（2026-08-26 API 实测生效，B5-3 销账）；ISSUE-018 以 by-design 正式终结（KNOWN_ISSUES 回归空态）。 |
| v2.0.0 破坏性窗口 | ✅ | ADR-030/B4-1 兑现——旧 `enable(context)` 分发分支移除（loader 三分叉收敛为二分叉：ContextAware / 无参 enable），生产与示例代码零消费者 grep 实证；测试矩阵净减 3 个 legacy 用例（413→410 全绿）；CHANGELOG `[2.0.0]` BREAKING 标注落定；版本链 bump 2.0.0（pyproject + .env.example 示例值；settings 回退值按 configuration.md 口径保持不动）。发版链实证——tag `v2.0.0` 已推送并触发 release workflow（run 33071797649 双 job success）：GitHub Release v2.0.0 自动创建且双资产挂载 API 实测确认（wheel 220KB / sdist 152KB）；发布前实现提交 `ba3ad02` CI 三平台全绿（run 33070707134）。Breaking Notes 已由 owner 粘贴（2026-08-27 API 复验：body 859 字符、文案逐字到位，紧随自动生成的 Full Changelog 行呈现，Review MINOR-4 销账）。 |
| Phase 6 吞吐加固 | ✅ | ADR-032 五项裁决落地——ThreadPoolExecutor per-photo 并行（并行段限纯推理、持久化回主线程、`max_workers=1` 逐字节串行原路径）；Domain `RecognitionRepository` 扩 `add_many`、SQLite 端单事务批量提交（往返 O(N)→O(1)）；基准工具 `tools/bench_recognition.py` 入库（全网格基线落 docstring：2600 张串行 656.9s → 4 workers 514.0s = **1.28×**；InsightFace session 跨线程共享实测安全）；等价不变量测试锁定（pytest 410→**417** passed）。线程扩展弱于 ≥2× 建议阈值——batch 批推理（A-2=B）二轮证据已触发，是否立项由 owner 拍板。 |
| CI | ✅ | GitHub Actions 三 OS 矩阵、模型缓存与 AI/UI 断言已启用。 |

当前 HEAD：实现提交 `0871048`（Phase 6 吞吐加固：并行化 + add_many 批持久化 + 基准工具 + 版本链 2.1.0 + CHANGELOG/ADR-032/phase6 核销）→ 本状态登记提交随本笔并入；本地领先 origin/main 三笔（GIT-020 规则 `75a4fe6` + 实现 `0871048` + 本登记提交；push 由 owner 手动执行，CI 三平台实证随 push 触发）。tag `v2.0.0` 指向 `ba3ad02`（v2.0.0 周期）；历史基线链：`eea3c1b`（Review 四 Minor 清偿）、`eddc8ee`（发版链实证登记）、`2bbbfb8`（B5-3 收官登记）。

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
| 时间 | 2026-08-29（本地） |
| 生成者 | Cline |
| 会话范围 | Phase 6 吞吐加固执行轮——前置门拍板转定稿后全程实施（并行化 + 批持久化 + 基准实测 + 文档收官）。 |
| 已完成 | ① 草案转定稿（2026-08-28 owner 五项全按默认推荐拍板）并登记 **ADR-032**；② 实施落地——`match_persons_service.py` 串行段改 ThreadPoolExecutor 并行（并行段限纯推理、持久化收敛主线程、`max_workers=1` 逐字节原路径）、Domain 协议扩 `add_many` + SQLite 单事务批量 INSERT、等价/失败隔离/进度/单事务测试新增（pytest **410→417**）；③ 基准工具 `tools/bench_recognition.py` 完成五处 SIG-PATCH 真实签名对齐（`load()`/构造参/实体形状/`list_all()` dict 返回）+ 6 处修正后冒烟通过；④ 全网格基线实测（37.4 min，exit 0）：2600 张串行 656.94s → 4 workers 514.00s（**1.28×**），session 跨线程共享实测安全，数字落 docstring 防回退；⑤ 主 diff 合规审查 **0 Critical / 0 Major / 0 Minor**；⑥ 门禁全绿：ruff ✓ / mypy 168 文件 ✓ / pytest **417 passed**；⑦ 文档收官——CHANGELOG `[2.1.0]` 段、phase6 §6 核销（4/6 勾销 + 性能目标与 CI 两项诚实注记）、版本链 bump 2.1.0（pyproject + .env.example）、ADR-032 登记、GIT-020 工作流规则入库（commit-only）。 |
| 当前质量门 | `ruff check .` 通过；`mypy src` 168 个源文件无问题；pytest 全量 **417 passed**（本地实测）。CI 三平台待 push 后触发（GIT-020：本轮不自动 push）。 |
| 工作区 | 实施改动 9 文件 + 收官文档 6 文件分两笔提交（实现 / 状态登记）；无过程脚本遗留；基准数字持久锚点在 `tools/bench_recognition.py` docstring。 |
| Remaining | 两项 owner 动作：(1) 手动 `git push origin main`——触发 CI 三平台实证后回填 phase6 §6 末行 checkbox；(2) **A-2=B（onnxruntime batch 批推理）立项拍板**——1.28× 线程扩展证据已触发二轮裁决条件（REV-AI-003：不以修改代替裁决）。 |
| Next Step | owner 拍板 A-2=B 后即起草二轮前置门附页（batch 维度改造设计：session 内 batch 推理 + padding 策略 + 等价不变量沿用）；若暂不立项，v2.1.0 按当前态发版（push + tag 由 owner 执行，Release body 建议粘贴 CHANGELOG `[2.1.0]` 段摘要）。 |

---

## 6. Next Step（下一步开发计划）

Phase 6 吞吐加固执行轮已全部收尾（代码/测试/基准/文档，质量门本地全绿）。剩余两项 owner 动作：

1. **手动 push**（GIT-020 规则：AI 只 commit 不 push）——`git push origin main` 触发 CI 三平台矩阵，全绿后回填 phase6 定稿 §6 末行 checkbox；发版时 push tag `v2.1.0.0`（或按本仓 tag 惯例 `v2.1.0`）触发 release workflow，Release body 建议粘贴 CHANGELOG `[2.1.0]` 段摘要。
2. **A-2=B 立项拍板**——实测线程扩展 1.28×（4 workers @2600 张）弱于 ≥2× 建议阈值，与 §5 预判吻合；onnxruntime batch 批推理是记录在案的二轮候选（ADR-032 实施结果栏）。拍板「立项」即起草二轮前置门附页；拍板「暂缓」则该证据留档为基线结论，v2.1.0 按当前态发版。

其余条件触发行不变：真实高危插件写用例→审批门复审（ADR-028 裁决点 2=B/C）；非技术用户分发需求→phase5 定稿方案 B 另起前置门；UI 识别触发点→功能轮另立（A-5=B）。

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
| 性能基线 | `tools/bench_plugin_search.py`（插件查询路径，零依赖可离线复跑，数据见 phase4 定稿 §6）、`tools/bench_recognition.py`（识别管线全网格基线，数字续记 docstring，phase6/ADR-032） |
| Schema 初始化与迁移 | `src/photo_archiver/infrastructure/database/sqlite_connection.py`、`src/photo_archiver/infrastructure/database/alembic_runner.py`、`alembic/versions/002_split_create_ddl.py` |
| 质量验证 | `tests/`、`.github/workflows/ci.yml` |

---

> 本文件只描述当前状态；历史决策见 `.ai/ARCHITECTURE_DECISIONS.md`，当前问题见 `.ai/KNOWN_ISSUES.md`，路线图见 `.ai/business/roadmap.md`。
