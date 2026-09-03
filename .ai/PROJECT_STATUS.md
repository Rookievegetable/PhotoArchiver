# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**“项目现在开发到哪里了？”**
>
> 每次开发结束后刷新；不保留历史状态。
>
> Version: 1.12.0 · Last Updated: 2026-09-02 · Status: Live

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

项目主路线图已完成；经 2026-09-02 全项目体检后，**Phase A/B/C 均已完成，当前处于 Phase D（发布工程·形态一）执行轮**（D-0 裁决：源码形态 v1.0，维持 ADR-031；决策批复 D-B1~D-B8 记录于 §2）。

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
- **Phase A（Runtime Correctness——全项目体检 P0 修复轮）**：🚧 Owner 已授权执行（2026-09-02）——范围 P0-10（文档收口）/ P0-1（插件 UI 加载）/ P0-2（缩略图 UI 渲染）/ P0-3（Excel 导入接线）/ P0-4（取消信号 + 扫描单飞），按序独立提交；每项完成后 STOP 待指令。体检基线报告：`docs/health-check/PROJECT_HEALTH_CHECK.md`（3 项用户可见功能失效 + 数据安全底线缺位 + F-002 恶化等 18 项 Finding）；开发路线图：`docs/roadmap/DEVELOPMENT_ROADMAP.md`。**Phase A 全部 5 项 P0 已完成（P0-10/1/2/3/4）**（见 §5/§6）。
- **Phase C（时序 flake 专项）**：⚠️ Owner 授权并解除禁修定性（2026-09-02）——首版方案（is_finished 权威终态）推送后 CI win/mac 新故障签名（AttributeError + access violation），**整体回退**（根因待查）；测试侧加固替代方案落地（两 match e2e 守卫断言改轮询），LIMIT-005 排序修复保留并经 mac CI 实证；回退收尾后连续两轮全量全绿 641/3/0。F-002/LIMIT-003 竞态的根治方案待重研（禁用包装器属性读取方向）。
- **Phase D（发布工程·形态一）**：🚧 D-0 裁决源码形态 v1.0（维持 ADR-031，方案 B 不触发）——P2-5 导出原子写已完成（`c33bbdd`）；剩余：发布验收清单执行（owner 手动）+ 发布说明素材（已交付会话）+ tag 命名裁决 + push/release。
- **Phase B（数据安全底线）**：🚧 Owner 已授权（2026-09-02）按 AI 计划草案的建议方案执行——决策批复：D-B1 导入按批原子（500 行/批）/ D-B2 无 identity 行按 name+department 查重 / D-B3 备份 VACUUM INTO + 每启动 + 3 份滚动 / D-B4 损坏库报错退出（不重建/不换库）/ D-B5 Windows 源码形态下 P0-9 完整锚定降 P1、本轮仅做启动警告 / D-B7 常量默认值（busy_timeout=5000、批 500 行、backups 同目录）/ D-B8 逐项授权。范围 P0-5→P0-6→P0-7→P0-8→P0-9(警告) 按序独立提交，每项完成后 STOP 待指令。**P0-5/6/7/8/9 全部完成**（`22305dd` / `ab92d5c`+`0295f62`+`9752af3` / `169abb3b`+`9359dfb` / `548d7fc`+`c46062f`+`4e91ee4` / `37fb675`——P0-8 并入质量审查 F-1/F-2）（见 §5/§6）。

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

当前 HEAD：`1436a62`（fix(workers): replay terminal events lost to late wiring——macOS CI 竞态修复）；origin/main = owner 已推送 blocker 修复链（含 `ae5a244`，其 CI 触发本竞态暴露），本地领先 **1 笔**（本修复），推送后 CI 重跑验证。版本链 2.3.0 三处一致，待 tag `v2.3.0`。tag 全景：`v1.0.0`→`49b2ac6`、`v2.0.0`→`ba3ad02`、`v2.1.0`→`bd52fbb`、`v2.2.0`→`f9fb8c5`；四个 Release 均已发布。历史重写注记与全项目状态锚点同前（`docs/health-check/PROJECT_HEALTH_CHECK.md`）。

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
| 生成者 | Cline |
| 会话范围 | 交接基线校验 → Phase B 计划草案与 D-B1~D-B8 批复 → **P0-5/6/7 顺序执行**（Cline 会话）→ **P0-8 + 审查 F-1/F-2 并入 → P0-9 启动警告**（ZCode 会话）→ **Phase C 时序 flake 专项** → **Phase D 形态一 P2-5 导出原子写 + v2.3.0 发布准备**（ZCode 会话，D-0 裁决：源码形态 v1.0）。 |
| 已完成 | ① **交接基线校验**（HEAD `f868b2d` / origin `3a2ef0a` / 领先 17 笔 / clean，全匹配）→ Phase B 计划草案 + Owner 批复 D-B1~D-B8。② **Phase B P0-5~P0-9 全部完成**：P0-5 WAL+busy_timeout（`22305dd`）；P0-6 损坏库门+中文指引+VACUUM INTO 备份（`ab92d5c`/`0295f62`/`9752af3`）；P0-7 导入批原子+无 identity 查重（`169abb3b`）；P0-8 模型 SHA-256 pin + CI fail-closed + 审查 F-1/F-2 并入（`548d7fc`/`c46062f`/`4e91ee4`）；P0-9 启动路径警告（`37fb675`，完整锚定降 P1）。③ **Phase C 时序 flake 专项**：LIMIT-005 根因=人员轴排序未定义（同刻 created_at + UUID 决胜随机）→ `list_all` 决胜改 name（`a6b70db`，mac CI 实证保留）；F-002 首版 is_finished 方案推送后 CI win/mac 原生崩溃 → **回退**（`7834c8b`）+ 测试侧轮询加固（`fa0c8fc`）。④ **Phase D 形态一**：P2-5 导出原子写（`c33bbdd`）+ v2.3.0 版本链（`24c7a86`）+ **P0-8 Release Blocker 修复**（`ae5a244`：Clean VM 模型下载 CERTIFICATE_VERIFY_FAILED → downloader TLS 显式锚定 certifi CA bundle + certifi 提升为正式 runtime dependency；证书/主机名校验保持开启，SHA-256 fail-closed 不变）。 |
| 当前质量门 | `ruff check .` 通过；`mypy src` 177 个源文件无问题；pytest 全量 **646 passed / 3 skipped / 0 failed 连续两轮**（含竞态修复 +3）；`pip check` 无损坏依赖。 |
| 工作区 | macOS 竞态修复提交（`1436a62`）+ 状态文档提交后 tracked 零改动；HEAD/origin 状态见 §3。 |
| Remaining | **Phase D（形态一）进行中：P2-5 原子写 ✅ + P0-8 Release Blocker 修复 ✅（已推送）+ macOS CI 竞态修复 ✅（本提交，待推送）**。剩余收口：owner 推送 1 笔 → CI 三平台重跑 → **Clean Machine Acceptance 重验**（重点步骤 2.3 模型下载）→ tag `v2.3.0` → Release v2.3.0（说明素材见 Phase D 报告 §4）。真桌面复验清单保留待 owner 补验（P0-4/6/7/9）。Phase E（删除语义 ADR 门）未授权。 |
| Next Step | **macOS 竞态修复已提交，STOP 等待 Owner**：推送 1 笔 → CI 重跑（三平台全绿确认）→ Clean Machine Acceptance 重验 → tag `v2.3.0` → Release v2.3.0。Phase E 须另行授权。 |

---

## 6. Next Step（下一步开发计划）

**Phase B（数据安全底线）执行状态**：Owner 已授权（2026-09-02）按 AI 计划草案建议方案执行（决策批复 D-B1~D-B8 见 §2）；每项以 静态契约 + 单测 + 集成测试 + Runtime Smoke + 用户视角验证 五层达标方为 COMPLETE，独立提交，完成后 STOP 待 Owner 逐项指令。

1. ~~P0-5 SQLite WAL + busy_timeout~~ ✅ 已完成（`22305dd`）：`sqlite_connection.py` 两条连接路径（`connect()` / `transaction()`）统一经 `_configure_connection` 施加 PRAGMA——`busy_timeout=5000`（先于 journal 设置，写锁争用时等待而非报错）+ `journal_mode=WAL`（`:memory:` 跳过；WAL 为库文件持久属性，既有库幂等升级）。+6 真实链路测试（`tests/unit/infrastructure/test_sqlite_connection_pragmas.py`：双路径 PRAGMA 断言 / `:memory:` 边界 / 既有契约回归 / 双连接真实锁场景——写者 B 在 busy_timeout 内等待写者 A 提交后成功）；`docs/development/configuration.md` v1.2 增补 PRAGMA 说明 + WAL 网络盘限制注记。Runtime Smoke PASS（offscreen 真实 `bootstrap_application` + 隔离库 `%TEMP%\p0p5_smoke`：journal_mode=wal / busy_timeout=5000 实测，Alembic 迁移链真实跑通）。质量门：pytest **601 passed / 3 skipped / 0 failed**（F-002 本轮未复现——LIMIT-003 定性不变，不因单次全绿宣布处置）、ruff / mypy 173 files / pip check 全绿。
2. ~~P0-6 损坏库友好失败 + 最小备份~~ ✅ 已完成（`ab92d5c` + `0295f62` + `9752af3`）：①完整性门 `infrastructure/database/integrity.py`——`verify_database_integrity` 以 URI mode=ro 只读跑 `PRAGMA quick_check`（缺文件/`:memory:` 跳过，绝不写坏文件/绝不创建文件），`CorruptedDatabaseError(path, issues)` 承载具体 issues；bootstrap 在 repos/migrations 前置该门，`sqlite3.DatabaseError` 兜底归一同类（防御纵深）。②友好失败 `presentation/startup_failure.py`——中文恢复指引（数据库位置/备份目录/复制恢复步骤/技术细节），GUI 自备 QApplication 弹 QMessageBox（QApplication 默认 quitOnLastWindowClosed=True，进程随返回码 2 退出），CLI stderr 同文案；main.py 四入口分流（CLI stderr+exit 2 / GUI dialog+exit 2），presentation 仅收 Path/str 原语零 infrastructure 依赖。③启动备份 `infrastructure/database/backup.py`（D-B3）——GUI 启动成功后 `VACUUM INTO` 快照至库同目录 `backups/`，3 份滚动保留，同秒冲突 _N 后缀，备份失败仅 WARNING 不阻塞启动、半成品清理，CLI 不备份；配置说明 v1.3 注记。Runtime Smoke A/B/C 全 PASS（A 注坏库 GUI 弹框 offscreen 截图核对中文文案；B 正常启动备份生成 + roundtrip 可读；C CLI 注坏库 exit 2 + stderr 指引 + 零备份泄漏 + 零 WAL 残留）。质量门：pytest **620 passed / 3 skipped / 0 failed**（+19：integrity 5 / startup_failure 4 / CLI 失败路径 4 / backup 5 / UoW 错误归类 1；F-002 连续三轮未复现——LIMIT-003 定性不变，处置仍归 Phase C）、ruff / mypy 176 files / pip check 全绿。
3. ~~P0-7 导入事务化 + 无 identity 查重~~ ✅ 已完成（`169abb3b` 功能 + `9359dfb` LIMIT-005 登记）：①按批原子（D-B1）——`ImportPeopleService` 增可选 `UnitOfWork` 注入（`ReviewRecognitionService` 同型惯例，`None`=内存测试路径裸写），行按 `BATCH_SIZE=500`（D-B7）分块，每批一个 UoW 作用域：批内意外失败仅回滚当前批、先前批保持已提交，永不留半批；②逐行错误隔离保留——`ValueError`/`ValidationError` 记入 `result.errors` 不中断批次（roadmap「避免把弹性导入变成全有全无」注记）；③无 identity 查重（D-B2）——`PersonRepository` 协议扩 `find_by_name_department`（SQLite 实现 `name=? AND department IS ?` NULL 安全 / InMemory 同步 / 领域契约测试替身更新），归一镜像 `Person.__post_init__`（strip / `or None`）；插件 `import_rows` 路径（ADR-028）同受批+查重覆盖。+7 真实链路测试（`tests/unit/application/test_import_people_transactional.py`：真实 SQLite tmp 库 + 真实 UoW——批中途崩溃→仅当前批回滚主断言 / identity 重复 / name+department 查重矩阵（含 NULL 部门）/ 跨批提交）。Runtime Smoke PASS（offscreen 真实 `bootstrap_application` + 隔离库 `%TEMP%\p0p7_smoke`：20 行→15 导入 / 5 查重跳过 / 0 错误，二轮幂等全跳 20，库内计数 15 一致）。过程发现：Excel 导入 UI 闭环集成测试负载敏感时序 flake（3 次全量 2 挂 1 过 + 单跑稳定，失败点 FilterBar 刷新段、持久化断言均先过）按 Scope Lock 登记 `KNOWN_ISSUES` LIMIT-005 不修，候选并入 Phase C 时序 flake 专项。质量门：pytest **627 passed / 3 skipped / 0 failed**（F-002 连续三轮未复现——LIMIT-003 定性不变）、ruff / mypy 176 files / pip check 全绿。
4. ~~P0-8 模型 SHA-256 固定~~ ✅ 已完成（`548d7fc` + `c46062f` + `4e91ee4`，质量审查 F-1/F-2 经 owner 批复并入本轮）：①`EXPECTED_SHA256["buffalo_l"]` pin 官方 v0.7 zip digest `80ffe37d…ca2f`（三重验证：官方 URL 下载件实测 / zip 内 5 ONNX 与 CI 绿色工作包逐一一致 / Hugging Face LFS 记录同前缀交叉印证）；②CI 移除 `--allow-unverified` 与 TODO（每次下载 fail-closed）；③审查 F-1：GUI 启动备份失败由裸调用崩溃改为 warning 不阻断（`main.py`，D-B3 best-effort 语义落地）；④审查 F-2：热 `-wal` 残留时完整性门延迟至读写打开（真损坏仍由 bootstrap DatabaseError 兜底，防御纵深不损失）。测试 +5（生产 pin 失开回归守卫 / 不匹配拒绝 / F-1 备份失败仍启动 / 热 WAL 延迟 + 无 sidecar 仍报损）。E2E 双路径实测：干净 zip verified→extract ✓ / 篡改 1 字节 → mismatch → Archive rejected → exit 1 ✓。CI 三平台强校验首跑依赖 owner push（D-B6 知会项）。
5. ~~P0-9 路径锚定~~ ✅ 已完成——本轮仅启动警告（`37fb675`，D-B5 批复：完整锚定降 P1）：`bootstrap.py` 增 `cwd_dependent_path_warnings` 枚举全部 CWD 相对配置路径，启动时逐条中文 warning（含解析绝对路径与 .env 建议）；`:memory:`/绝对路径静默、未配置可选根跳过。测试 +5（纯函数矩阵 + 真实 bootstrap 经真实日志文件断言）。真实入口冒烟：相对库 3 条警告 / 绝对库仅模型目录 1 条（设计预期）。完整锚定（用户目录/注册表定位）降 P1，凭需求信号另启。
6. ~~P0-9 路径锚定~~ 补充：P0-9 用户可见复验=换目录启动核对日志警告（清单保留）。
7. ~~Phase C 时序 flake 专项~~ ✅ 已完成——**含一次回退（如实记录）**：①F-002/LIMIT-003 首版方案（`9616c3e`：`QtWorkerRunnable.is_finished` 权威终态 + 控制器 `is_running` 语义升级）推送后 **CI win/mac 双平台出现新故障签名**（pytest-qt 内部 AttributeError + Windows access violation 崩溃，历史未见）→ 疑点指向 main 线程读取已被 autoDelete 的 QRunnable 包装器属性 → **整体 revert（`7834c8b`）**，根因待查（is_finished 思路需改用非包装器机制重试）。②测试侧加固替代方案已落地：两 match e2e 的守卫断言改 `qtbot.waitUntil` 轮询（对投递时序鲁棒，不触生产）。③LIMIT-005 修复（`a6b70db` 人员轴排序确定性）经 mac CI 实证有效、保留。验证：回退收尾后连续两轮全量全绿 641/3/0。
8. **Phase B/C 收口**：Phase B（P0-5~P0-9）+ Phase C（时序 flake 专项）全部完工；Phase D/E 须另行授权。

CI 事故结案注记：is_finished 方案（`9616c3e`，已回退）在 owner push 后的 CI 首跑中于 win/mac 触发 pytest-qt 内部错误与 Windows 原生崩溃；回退（`7834c8b`）后 owner 实证 CI 三平台全绿——方案与崩溃的因果确证，重试需改用非包装器机制。发版收尾（非阻塞，GIT-020 归 owner）

macOS 竞态结案注记（`1436a62`）：owner 推送 blocker 链后的 CI mac 失败（export UI 链 15s 超时）根因为**真实生产竞态**——快失败任务的终态信号在视图接线前发射即永久丢失；`QtWorkerRunnable` 保留终态 + `replay_pending_terminal()`（4 接线点）根治。迟订阅回归测试 + 连续两轮全量 646/3/0。

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
