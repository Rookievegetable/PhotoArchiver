# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**“项目现在开发到哪里了？”**
>
> 每次开发结束后刷新；不保留历史状态。
>
> Version: 1.9.0 · Last Updated: 2026-09-02 · Status: Live

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

项目主路线图已完成；经 2026-09-02 全项目体检后，当前处于 **Phase A（Runtime Correctness）P0 修复轮**——修复体检确认的用户可见功能断点。

- 阶段 0（质量基线与文档收口）：✅ 完成。
- 阶段 1（PluginContext 公共边界加固，ADR-026）：✅ 完成。
- 阶段 2（Alembic 接管 Schema DDL，ADR-027）：✅ 完成。
- 阶段 3（插件写能力 import_people，ADR-028）：✅ 完成（仅 import_people；export 经 ADR-030 裁决 YAGNI 正式关闭）。
- 阶段 4（技术债轮：search_photos N+1 加固 ADR-029 + 轮次裁决 ADR-030）：✅ 完成（兼容路径移除原挂账 v2.0.0，已于 v2.0.0 轮兑现——见下表「v2.0.0 破坏性窗口」行；审批门续暂缓）。
- 阶段 5（识别管线吞吐加固，ADR-032）：✅ 完成——线程并行 + `add_many` 单事务批下推 + 基准工具入库（全网格基线落档；线程扩展 1.28× 弱于建议阈值）。二轮证据链闭合：batch 批推理经 W1 尖刺证据性出局；W2-segment 尖刺段内分解定址两个死重模型（landmark 35.4ms + genderage 9.8ms，生产零消费）——phase7 执行轮完成（ADR-033，owner 三项全 A 拍板 2026-08-29）：landmark 双模型 + genderage 死重剔除（loader `allowed_modules=("detection","recognition")` 一行配置），全网格复测 2600 串行 656.94→332.02s（**1.98×**）、4-worker 5.06→**11.22** photos/s（**2.22×**），等价不变量全程保持（pytest 417），v2.2.0。
- **Phase 4.2（FEATURE-001：Face Recognition / Matching 生产触发入口）**：✅ 完成并 Final Audit **CLOSED**（2026-08-30，HEAD `638ef30`）——原 P1「Face Recognition 无 UI/CLI 触发入口」闭环：四个 Commit（`2788d64` Worker Task → `ba9a413` Controller → `afc29e9` UI Action → `638ef30` Integration tests）。真实持久化链路（Task → Service → SQLite → PENDING → Review approve）由真实 SQLite integration 验证（AC-015/AC-016 PASS）；AC-001~016 逐条对账；`pytest 485 passed / 3 skipped`、`ruff`、`mypy 170 files`、`pip check` 全绿。两项设计/测试覆盖限制登记 `KNOWN_ISSUES.md`（LIMIT-001 真实缺模型 E2E 未入 CI；LIMIT-002 取消粒度为 batch-level）。
- **Phase 5（FEATURE-002：Export 生产触发入口 / Export UI）**：✅ 完成并 Final Audit **PASS / CLOSED**（2026-08-31，HEAD `3db7074`）——原 P1「Export 无 UI/CLI 触发入口」闭环：两个 Feature Commit（`4f054b4` feat(ui) 增加 Export Data QAction + handler + 信号 wiring；`396b706` test(integration) UI→Controller→Task→Service→Exporter→SQLite→file 全真实链路集成测试）+ Final Audit Commit `3db7074`（docs(audit) AC 证据缺口闭合 + Final Audit 报告，已随 Git 历史清理自 main 移除）。AC-001~015 全部 PASS（15/15，结论保留于本节）；`pytest 500 passed / 3 skipped`、`ruff`、`mypy 170 files`、`pip check` 全绿；生产代码变更仅 Commit 1 的 `main_window.py`（+69 行），Commit 2/3 生产代码 0。Finding 对账：F-001（ExportService scope stub，CURRENT_BATCH/FILTERED 未实现）保持既有 P3 登记（FEATURE-004 独立跟进，不重复入 KNOWN_ISSUES）；F-002（match 控制器真实线程池集成测试偶发时序 flake）保持 Phase 4.2 审计既有记录；F-003 已于 Final Audit 闭合（补测完成）。Phase 5 无新增开放问题，`KNOWN_ISSUES.md` 维持既有 2 项设计/测试覆盖限制（LIMIT-001/002）。
- **Phase 6（FEATURE-COMPLETENESS-001：已 CLOSED Feature 完整性审计与稳定性加固）**：✅ 完成并 Final Audit **PASS**（2026-09-01，Baseline commit `b9b6c90`）——对已 CLOSED 的 FEATURE-001（Face Recognition）与 FEATURE-002（Export Data）做完整性核验：Feature Matrix 全在位（FEATURE-001 Controller/WorkerTask/Service/Repository/UI Action/Review Pipeline；FEATURE-002 Controller/WorkerTask/Service/Exporter/SQLite 读取/文件输出/UI Action），实现零漂移（`git diff HEAD -- src/ tests/ alembic/` 为空）；**AC 31/31 PASS**（16/16 + 15/15，逐条以当前代码 + 当前测试双证据核验）；**Quality Gates**：`pytest 499 passed / 3 skipped / 1 known failure`（唯一 failed = F-002 历史线程池时序 flake，单跑 ×2 稳定）、`ruff`、`mypy 170 files`、`pip check` 全绿；**Production Code Changes: NONE**。Finding 对账：F-001（Export scope stub，Deferred FEATURE-004）、F-002（Known limitation）、LIMIT-001/002 均维持既有登记，新增 None。审计结论：Baseline Audit Rev 2 PASS + Final Audit PASS（报告已随 Git 历史清理自 main 移除）。
- **Phase 7（FEATURE-004：Export Scope Implementation）**：✅ 完成并 Final Audit **PASS / CLOSED**（2026-09-02，HEAD `747ccab`）——Phase 5 遗留 P3 F-001（ExportService scope stub）闭环，四 Commit（`d339904` audit(export) Scope Contract 定义 + criteria 签名贯通 → `0e1e9e3` feat(export) `_gather_data` 三分支 dispatch + `RecognitionRepository`/`ArchiveRecordRepository` `list_by_photo_ids`（Protocol 默认实现 + SQLite IN-clause 分块覆写）→ `c4ca958` feat(ui) scope selection + `_current_criteria` 持有一点 → `747ccab` test(export) 真实 SQLite 集成收口）。ALL 行为零漂移（逐字节不变性测试 + 真实 SQLite 8 行 approved-only 回归）；FILTERED 契约 §3/F1–F8 全量落地——criteria 快照在导出执行时刻经 `PhotoRepository.search` 重查询、matches/people/archive_records 严格自主集派生（matches 全状态含 Pending）、真实 UI→Controller→Task→Service→Repository→Exporter→file 链 CSV/XLSX 双格式逐项断言、Photo A/B 泄漏矩阵零泄漏；CURRENT_BATCH 按 §2 D1–D5 裁决 **DEFERRED**（UI 永久禁用 + 枚举成员保留 + Service/Task 层诚实 `ValueError`，无静默 fallback）；FILTERED+criteria=None 经真实链路双层拒绝。**AC 8/8 PASS**（0 NOT VERIFIED）；`pytest 535 passed / 3 skipped`、`ruff`、`mypy 170 files`、`pip check` 全绿（F-002 本轮全量复现 1 次，单跑 ×2 稳定复判为同一已知 flake）。Finding 对账：F-001 **CLOSED**；F-002 维持 Known limitation；LIMIT-001/002 维持；新增 None。审计链：Baseline Audit（BLOCKED）→ Scope Contract Revision（解锁契约）→ Final Audit（PASS）→ Closure（报告已随 Git 历史清理自 main 移除）。

- **Phase 9 P0（FEAT-P9-1/2/3：Filter Completeness）**：✅ 完成（2026-09-02，HEAD `3a2ef0a`）——日期范围筛选（From/To checkbox 门控）、人员筛选（新增薄读取用例 `ListPersonsService`）、三轴联合 AND 语义矩阵 + FILTERED 导出真实链路联测（泄漏矩阵零泄漏）。DoD 23/23；`pytest 570 passed / 3 skipped`；联测暴露并修复 QVariant userData 缺陷（userData 改存字符串 id）。实施报告：`docs/development/PHASE_9_FILTER_COMPLETENESS_REPORT.md`；规划：`docs/roadmap/NEXT_PHASE_FEATURE_DEVELOPMENT_PLAN.md`。
- **Phase A（Runtime Correctness——全项目体检 P0 修复轮）**：🚧 Owner 已授权执行（2026-09-02）——范围 P0-10（文档收口）/ P0-1（插件 UI 加载）/ P0-2（缩略图 UI 渲染）/ P0-3（Excel 导入接线）/ P0-4（取消信号 + 扫描单飞），按序独立提交；每项完成后 STOP 待指令。体检基线报告：`docs/health-check/PROJECT_HEALTH_CHECK.md`（3 项用户可见功能失效 + 数据安全底线缺位 + F-002 恶化等 18 项 Finding）；开发路线图：`docs/roadmap/DEVELOPMENT_ROADMAP.md`。**P0-10、P0-1、P0-2、P0-3 已完成**（见 §5/§6）。

当前无未解决的 O 级产品缺陷登记于 KNOWN_ISSUES（P0-1~3 修复中的缺陷见体检报告 §4.2/§15，落地即销，不重复登记）；`KNOWN_ISSUES.md` Limit 表格登记 4 项设计/测试覆盖限制（LIMIT-001/002 + LIMIT-003 F-002 恶化 + LIMIT-004 Qt 子集顺序崩溃）。

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
| Phase 6 吞吐加固 | ✅ | ADR-032 五项裁决落地——ThreadPoolExecutor per-photo 并行（并行段限纯推理、持久化回主线程、`max_workers=1` 逐字节串行原路径）；Domain `RecognitionRepository` 扩 `add_many`、SQLite 端单事务批量提交（往返 O(N)→O(1)）；基准工具 `tools/bench_recognition.py` 入库（全网格基线落 docstring：2600 张串行 656.9s → 4 workers 514.0s = **1.28×**；InsightFace session 跨线程共享实测安全）；等价不变量测试锁定（pytest 410→**417** passed）。线程扩展弱于 ≥2× 建议阈值——batch 批推理（A-2=B）二轮证据已触发；W1 尖刺实测完成（`tools/spike_batch_inference.py`，2026-08-29）：纯推理天花板 ≈13.7 photos/s、线程超订阅假设证伪、瓶颈定址非推理段（~143ms/张）；W2-segment 尖刺（`tools/spike_segment_profile.py` v2，账目闭合 251.3≈249.4≈254.4 ms/张）定址两个零消费死重模型——landmark 双模型 35.4ms（剔除 1.522×）、genderage 9.8ms（合计 1.985×），剔除落点为 loader `allowed_modules` 一行配置；phase7 前置门草案待 owner 拍板（W2-1/W2-2/W2-3）。 |
| Phase 7 死重剔除（v2.2.0） | ✅ | ADR-033 三项裁决全 A（W2-1 landmark 剔除 / W2-2 genderage 一并剔除，owner 确认近期无性别年龄功能规划 / W2-3 剩余非推理段本轮不改造）——loader `allowed_modules=("detection","recognition")` 落地，bbox/kps/embedding 逐字节不变；`tools/bench_recognition.py` 全网格复测落 docstring：2600×1 656.94→332.02s（**1.98×**）、2600×4 514.00→231.68s（**2.22×**）、600×4 2.45×，全部格子 100% 产出 / 全 PENDING 等价保持；门禁本地全绿（ruff 0 / mypy 168 ✓ / pytest **417** passed）；证据链 `tools/spike_segment_profile.py` v2（账目闭合）+ phase7 定稿（`docs/development/phase7-adr-draft.md`）。CI 实证已回填（owner push 后 API 实测 head `4fe8aa4` CI run completed/success 三平台全绿，2026-08-29）；发版链实证——tag `v2.1.0`@`bd52fbb` / tag `v2.2.0`@`f9fb8c5` 已由 owner 推送（ls-remote 实测远端指向正确），两 tag 触发 release workflow，owner 确认 CI 全绿，v2.1.0 / v2.2.0 已发布（2026-08-29）。 |
| CI | ✅ | GitHub Actions 三 OS 矩阵、模型缓存与 AI/UI 断言已启用。 |

当前 HEAD：`39c6298`（fix(import): complete Excel import wiring——Phase A P0-3）；origin/main = `3a2ef0a`（Phase 9 P0 Filter Completeness），本地 main 领先 8 笔（体检报告 + 路线图 + P0-10 + onboarding 同步/清理 + P0-1 + P0-2 + P0-3），分支引用推送按 GIT-020 留待 owner `git push origin main` 对齐（非阻塞）。tag 全景（本地 `git for-each-ref` 实测）：`v1.0.0`→`49b2ac6`、`v2.0.0`→`ba3ad02`、`v2.1.0`→`bd52fbb`、`v2.2.0`→`f9fb8c5`；四个 Release 均已发布（GitHub Release 实证，2026-08-29）。历史重写注记：Git History Cleanup 后 main 现行历史不含 Phase 4.2–8 期间的 `docs/health-check/PHASE_*.md` 审计报告文件，其 AC 结论保留于本节文字；全项目当前状态以 `docs/health-check/PROJECT_HEALTH_CHECK.md` 为准。

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
| 时间 | 2026-09-02（本地） |
| 生成者 | ZCode (GLM-5.3-Flash) |
| 会话范围 | 全项目体检（READ ONLY，HEAD `3a2ef0a` 基线）→ Owner 授权 Phase A（Runtime Correctness）→ Phase A **P0-10 文档收口**、**P0-1 Plugin UI Loading**、**P0-2 Thumbnail Rendering**、**P0-3 Excel Import Wiring** 执行（截至本提交）。 |
| 已完成 | ① **全项目体检**（12 维度证据化核查，READ ONLY）：确认 3 项用户可见功能失效（插件 UI 死路径 `main_window.py:191` / 缩略图不渲染 / Excel 导入断线 `app/services.py:140`）+ 数据安全底线缺位（无 WAL/busy_timeout、零备份、CWD 相对库位置）+ F-002 恶化等 18 项 Finding，Gap Matrix + 成熟度评分 + Minimum Path to v1.0 产出；交付 `5cac1a4`（health check）+ `483cb18`（roadmap）。② **Phase A 授权与 P0-10 执行**（本提交）：PROJECT_STATUS 对齐当前 HEAD / Phase 9 / Phase A；§2/§3/§5/§6 过期状态（HEAD `5aad031`、origin `d762751`、领先 22 笔等历史重写前信息）全部清理；`docs/health-check/PHASE_*.md` 悬空引用改为"已随 Git 历史清理移除"注记；KNOWN_ISSUES 登记 LIMIT-003（F-002 恶化）/ LIMIT-004（Qt 子集顺序崩溃）；FAQ 插件条目与当前实际对齐（P0-1 落地后恢复）；roadmap 状态行更新。③ **P0-1 Plugin UI Loading**（`d30a4de`）——修复两处链路断点：`main_window.py` 插件目录 anchor（4×parent → `parents[4]`，原指向不存在的 `src/examples/plugins` 整链静默跳过）+ toolbar `setObjectName("Main")`（`QToolBar("Main", …)` 构造串是 windowTitle 非 objectName，`_add_plugin_actions` 的 `findChild` 契约失效——路径修复后由新增测试暴露的第二个断点）；新增 `test_plugin_ui_loading.py`（3 tests）证明真实链路：加载→启用→QAction 注册→isEnabled/isVisible→触发→真实 execute_action→渲染；offscreen 真实入口 Runtime Smoke PASS（3 插件动作出现在工具栏且全部可见）；FAQ 插件条目恢复可用表述。④ **P0-2 Thumbnail Rendering**（`cbc2718`）——新增 `PhotoThumbnailDelegate(QStyledItemDelegate)`（`photo_list_delegate.py`）消费 `THUMBNAIL_ROLE`：Path→QPixmap 经 QPixmapCache 托管，顶部缩略图 + 底部文件名，选中样式走 style 原语；`_build_central` 一行 `setItemDelegate` 接线；模型 docstring 真实化。新增 `test_photo_thumbnail_rendering.py`（2 tests）：真实生成/缓存（含二次命中 mtime 不变）+ 真实 MainWindow 管线（真实 photos.add → 真实异步加载 → waitUntil → THUMBNAIL_ROLE 路径 → **delegate paint 像素 == 源色** → view.grab() 全 widget 渲染含缩略图）。Runtime Smoke 双层：Layer A offscreen（真实 CLI `main.py scan` 隔离库 → 真实入口 → 像素断言 PASS）；Layer B 真桌面（`main.py` 真实窗口截图，缩略图 + 文件名肉眼可见）。⑤ **P0-3 Excel Import Wiring**（`39c6298`）——三断点修复：①装配行只接 TXT reader → 新增 `DispatchingPersonImportReader`（.xlsx/.xlsm→openpyxl 读取器，其余→TXT）；②导入文件过滤器广告 `*.xls` 但 openpyxl 不支持 → 收敛为 `*.txt *.csv *.xlsx`；③真桌面手动烟测（owner 执行，125% DPI）发现导入刷新后 FilterBar 出现"残影组件" → 根因为 FilterBar/central 普通QWidget 不绘自身背景（真桌面几何转储证实布局全对、autoFillBackground=False）→ 两处 `setAutoFillBackground(True)`。测试 +10（调度路由 6 / 真实 UI 闭环 1 / person 轴几何与背景钉扎 3）。Runtime Smoke：Layer A offscreen PASS（真实 xlsx→真实 QAction→SQLite→combo 刷新）；Layer B owner 手动测试确认步骤 1-4（导入完成、`import_people complete`、Alice/Bob 落库由只读 SQL 核验）。 |
| 当前质量门 | `ruff check .` 通过；`mypy src` 173 个源文件无问题；pytest 全量 **585 passed / 3 skipped / 1 failed**——唯一 failed = F-002，**状态恶化：单跑 ×2 亦失败**（失败点 `controller.is_running` 单飞守卫断言，持久化断言通过；已登记 KNOWN_ISSUES LIMIT-003，处置属 Phase C）；`pip check` 无损坏依赖。 |
| 工作区 | P0-10 文档收口提交后 tracked 零改动；HEAD/origin 状态见 §3。 |
| Remaining | Phase A：P0-10 ✅、P0-1 ✅、P0-2 ✅、P0-3 ✅（残影修复待 owner 最终视觉复验）；P0-4（取消信号 + 扫描单飞）待执行。P0-5~P0-9（数据安全底线）、P1/P2、Phase B–E 均未授权，禁止提前实施。发版动作（GIT-020 归 owner）：`git push origin main` 对齐分支引用（非阻塞）。 |
| Next Step | **P0-4 Cancellation + Scan Single-flight**——按停止规则待 Owner 指令启动（Phase A 每项 P0 完成后 STOP，不自动开始下一项）。 |

---

## 6. Next Step（下一步开发计划）

**Phase A（Runtime Correctness）执行状态**：Owner 以 Phase A 启动指令授权本阶段——修复体检确认的用户可见功能断点；每项 P0 以 静态契约 + 单测 + 集成测试 + Runtime Smoke + 用户视角验证 五层达标方为 COMPLETE，独立提交，完成后 STOP。

1. ~~P0-10 文档收口~~ ✅ 已完成（2026-09-02，本提交）：PROJECT_STATUS 对齐当前 HEAD / Phase 9 / Phase A；`docs/health-check/PHASE_*.md` 悬空引用清理（注记"已随 Git 历史清理移除"）；KNOWN_ISSUES 登记 LIMIT-003（F-002 恶化）/ LIMIT-004（Qt 子集顺序崩溃）——两项均属不修项，如实登记；FAQ 插件条目与当前实际对齐（P0-1 落地后恢复表述）。
2. ~~P0-1 插件 UI 加载修复~~ ✅ 已完成（`d30a4de`）：两处断点修复（目录 anchor 4×parent → `parents[4]`；toolbar objectName 补齐使 `_add_plugin_actions` 的 `findChild` 契约成立——路径修复后由新增测试暴露的第二个断点）+ `test_plugin_ui_loading.py`（3 tests）真实链路测试 + offscreen 真实入口 Runtime Smoke PASS（3 插件动作真实出现且可见）。存量观察：子集顺序 Qt 原生崩溃维持 LIMIT-004 登记（stash 基线复证实为先于 P0-1 存在，全量顺序不受影响）。
3. ~~P0-2 缩略图 UI 渲染~~ ✅ 已完成（`cbc2718`）：新增 `PhotoThumbnailDelegate` 消费 `THUMBNAIL_ROLE`（Path→QPixmap QPixmapCache 托管；style 原语保选中高亮）+ `_build_central` 接线 + `test_photo_thumbnail_rendering.py`（2 tests，管线含缓存命中 + delegate paint 像素 == 源色 + view.grab() 渲染证据）+ Runtime Smoke 双层 PASS（offscreen 真实 CLI scan→真实入口像素断言；真桌面窗口截图肉眼可见）。断点单一：模型对 DecorationRole 返 None 且 THUMBNAIL_ROLE 无消费者（体检 P-2 判定证实）。
4. ~~P0-3 Excel Import Wiring~~ ✅ 已完成（`39c6298`）：三断点修复（装配单 reader → DispatchingPersonImportReader；过滤器撤下不受支持的 .xls；FilterBar/central 补 autoFillBackground 消除导入刷新残影——owner 手动烟测暴露，真桌面几何转储证实为纯像素残留而非布局错误）+ 测试 +10。数据面证据：owner 手动导入后只读 SQL 核验 Alice/Bob 落库字段正确。
5. P0-4 Cancellation + Scan Single-flight —— 待 Owner 指令。

吞吐线与历史阶段状态不变：Phase 4.2 / 5 / 6 / 7 / 8 / 9 全部 CLOSED（详见 §2）；v1.0.0 / v2.0.0 / v2.1.0 / v2.2.0 已发布。P0-5~P0-9（数据安全底线）、P1/P2、Phase B–E、分发方案 B、CURRENT_BATCH 批次持久化等均为**未授权项**——触发前不排期、不自动选定、发现时只记录不修复（Phase A scope lock）。发版收尾（非阻塞，GIT-020 归 owner）：`git push origin main` 对齐分支引用（本地领先 2 笔 docs 提交）。

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
| 性能基线 | `tools/bench_plugin_search.py`（插件查询路径，零依赖可离线复跑，数据见 phase4 定稿 §6）、`tools/bench_recognition.py`（识别管线全网格基线，数字续记 docstring，phase6/ADR-032）、`tools/spike_batch_inference.py`（W1 批推理/线程尖刺，数据落 docstring）、`tools/spike_segment_profile.py`（W2 段内分解 + A/B 死重实验，数据落 docstring，phase7 证据） |
| Schema 初始化与迁移 | `src/photo_archiver/infrastructure/database/sqlite_connection.py`、`src/photo_archiver/infrastructure/database/alembic_runner.py`、`alembic/versions/002_split_create_ddl.py` |
| 质量验证 | `tests/`、`.github/workflows/ci.yml` |
| 体检与规划 | `docs/health-check/PROJECT_HEALTH_CHECK.md`（全项目体检基线）、`docs/roadmap/DEVELOPMENT_ROADMAP.md`（Phase A–E 路线图）、`docs/roadmap/NEXT_PHASE_FEATURE_DEVELOPMENT_PLAN.md`（Phase 9 规划，历史） |

---

> 本文件只描述当前状态；历史决策见 `.ai/ARCHITECTURE_DECISIONS.md`，当前问题见 `.ai/KNOWN_ISSUES.md`，路线图见 `.ai/business/roadmap.md`。
