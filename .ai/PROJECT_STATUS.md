# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**“项目现在开发到哪里了？”**
>
> 每次开发结束后刷新；不保留历史状态。
>
> Version: 1.8.0 · Last Updated: 2026-09-02 · Status: Live

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
- 阶段 5（识别管线吞吐加固，ADR-032）：✅ 完成——线程并行 + `add_many` 单事务批下推 + 基准工具入库（全网格基线落档；线程扩展 1.28× 弱于建议阈值）。二轮证据链闭合：batch 批推理经 W1 尖刺证据性出局；W2-segment 尖刺段内分解定址两个死重模型（landmark 35.4ms + genderage 9.8ms，生产零消费）——phase7 执行轮完成（ADR-033，owner 三项全 A 拍板 2026-08-29）：landmark 双模型 + genderage 死重剔除（loader `allowed_modules=("detection","recognition")` 一行配置），全网格复测 2600 串行 656.94→332.02s（**1.98×**）、4-worker 5.06→**11.22** photos/s（**2.22×**），等价不变量全程保持（pytest 417），v2.2.0。
- **Phase 4.2（FEATURE-001：Face Recognition / Matching 生产触发入口）**：✅ 完成并 Final Audit **CLOSED**（2026-08-30，HEAD `638ef30`）——原 P1「Face Recognition 无 UI/CLI 触发入口」闭环：四个 Commit（`2788d64` Worker Task → `ba9a413` Controller → `afc29e9` UI Action → `638ef30` Integration tests）。真实持久化链路（Task → Service → SQLite → PENDING → Review approve）由真实 SQLite integration 验证（AC-015/AC-016 PASS）；AC-001~016 逐条对账；`pytest 485 passed / 3 skipped`、`ruff`、`mypy 170 files`、`pip check` 全绿。两项设计/测试覆盖限制登记 `KNOWN_ISSUES.md`（LIMIT-001 真实缺模型 E2E 未入 CI；LIMIT-002 取消粒度为 batch-level）。
- **Phase 5（FEATURE-002：Export 生产触发入口 / Export UI）**：✅ 完成并 Final Audit **PASS / CLOSED**（2026-08-31，HEAD `3db7074`）——原 P1「Export 无 UI/CLI 触发入口」闭环：两个 Feature Commit（`4f054b4` feat(ui) 增加 Export Data QAction + handler + 信号 wiring；`396b706` test(integration) UI→Controller→Task→Service→Exporter→SQLite→file 全真实链路集成测试）+ Final Audit Commit `3db7074`（docs(audit) AC 证据缺口闭合 + 审计报告 `docs/health-check/PHASE_5_FINAL_AUDIT.md`）。AC-001~015 全部 PASS（15/15，逐条证据见审计报告 §3）；`pytest 500 passed / 3 skipped`、`ruff`、`mypy 170 files`、`pip check` 全绿；生产代码变更仅 Commit 1 的 `main_window.py`（+69 行），Commit 2/3 生产代码 0。Finding 对账：F-001（ExportService scope stub，CURRENT_BATCH/FILTERED 未实现）保持既有 P3 登记（FEATURE-004 独立跟进，不重复入 KNOWN_ISSUES）；F-002（match 控制器真实线程池集成测试偶发时序 flake）保持 Phase 4.2 审计既有记录；F-003 已于 Final Audit 闭合（补测完成）。Phase 5 无新增开放问题，`KNOWN_ISSUES.md` 维持既有 2 项设计/测试覆盖限制（LIMIT-001/002）。
- **Phase 6（FEATURE-COMPLETENESS-001：已 CLOSED Feature 完整性审计与稳定性加固）**：✅ 完成并 Final Audit **PASS**（2026-09-01，Baseline commit `b9b6c90`）——对已 CLOSED 的 FEATURE-001（Face Recognition）与 FEATURE-002（Export Data）做完整性核验：Feature Matrix 全在位（FEATURE-001 Controller/WorkerTask/Service/Repository/UI Action/Review Pipeline；FEATURE-002 Controller/WorkerTask/Service/Exporter/SQLite 读取/文件输出/UI Action），实现零漂移（`git diff HEAD -- src/ tests/ alembic/` 为空）；**AC 31/31 PASS**（16/16 + 15/15，逐条以当前代码 + 当前测试双证据核验）；**Quality Gates**：`pytest 499 passed / 3 skipped / 1 known failure`（唯一 failed = F-002 历史线程池时序 flake，单跑 ×2 稳定）、`ruff`、`mypy 170 files`、`pip check` 全绿；**Production Code Changes: NONE**。Finding 对账：F-001（Export scope stub，Deferred FEATURE-004）、F-002（Known limitation）、LIMIT-001/002 均维持既有登记，新增 None。审计报告：`docs/health-check/PHASE_6_BASELINE_AUDIT.md`（Rev 2 PASS）+ `docs/health-check/PHASE_6_FINAL_AUDIT.md`（PASS）。
- **Phase 7（FEATURE-004：Export Scope Implementation）**：✅ 完成并 Final Audit **PASS / CLOSED**（2026-09-02，HEAD `747ccab`）——Phase 5 遗留 P3 F-001（ExportService scope stub）闭环，四 Commit（`d339904` audit(export) Scope Contract 定义 + criteria 签名贯通 → `0e1e9e3` feat(export) `_gather_data` 三分支 dispatch + `RecognitionRepository`/`ArchiveRecordRepository` `list_by_photo_ids`（Protocol 默认实现 + SQLite IN-clause 分块覆写）→ `c4ca958` feat(ui) scope selection + `_current_criteria` 持有一点 → `747ccab` test(export) 真实 SQLite 集成收口）。ALL 行为零漂移（逐字节不变性测试 + 真实 SQLite 8 行 approved-only 回归）；FILTERED 契约 §3/F1–F8 全量落地——criteria 快照在导出执行时刻经 `PhotoRepository.search` 重查询、matches/people/archive_records 严格自主集派生（matches 全状态含 Pending）、真实 UI→Controller→Task→Service→Repository→Exporter→file 链 CSV/XLSX 双格式逐项断言、Photo A/B 泄漏矩阵零泄漏；CURRENT_BATCH 按 §2 D1–D5 裁决 **DEFERRED**（UI 永久禁用 + 枚举成员保留 + Service/Task 层诚实 `ValueError`，无静默 fallback）；FILTERED+criteria=None 经真实链路双层拒绝。**AC 8/8 PASS**（0 NOT VERIFIED）；`pytest 535 passed / 3 skipped`、`ruff`、`mypy 170 files`、`pip check` 全绿（F-002 本轮全量复现 1 次，单跑 ×2 稳定复判为同一已知 flake）。Finding 对账：F-001 **CLOSED**；F-002 维持 Known limitation；LIMIT-001/002 维持；新增 None。审计链：`docs/health-check/PHASE_7_BASELINE_AUDIT.md`（BLOCKED）→ `PHASE_7_SCOPE_CONTRACT_REVISION.md`（解锁契约）→ `PHASE_7_FINAL_AUDIT.md`（PASS）→ `PHASE_7_CLOSURE.md`。

当前无未解决的 O 级产品问题；`KNOWN_ISSUES.md` 登记 2 项设计/覆盖限制（Limit 表格）。

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

当前 HEAD：`5aad031`（docs(audit): close Phase 7 FEATURE-004——Phase 7 Closure 提交）；origin/main = `d762751`（Phase 6/7 发版链收口登记），本地 main 领先远端 22 笔（Phase 4.2 → Phase 7 全部实现/审计/收口提交，`git ls-remote` + `git merge-base` 实测远端无本地缺失提交），分支引用推送按 GIT-020 留待 owner `git push origin main` 对齐（非阻塞）。tag 全景（本地 `git tag` 实测）：`v1.0.0`→`49b2ac6`、`v2.0.0`→`ba3ad02`、`v2.1.0`→`bd52fbb`、`v2.2.0`→`f9fb8c5`；v2.1.0 / v2.2.0 两 Release 已发布（owner 推送 + CI 全绿确认，2026-08-29）。历史链：`d762751`（Phase 6/7 发版链收口）、`f9fb8c5`（phase7 CI 回填）、`4fe8aa4`（phase7 登记）、`9f0bede`（phase7 实现）。

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
| 会话范围 | Phase 7（FEATURE-004 Export Scope）Commit 4 集成收口 + Closure；Phase 8 Baseline Audit；Phase 8 Contract Revision（owner 提供执行规则后启动）。 |
| 已完成 | ① **Phase 7 Commit 4**（`747ccab` test(export): scope integration closure）——新增 `tests/integration/export/test_export_scope_integration.py`（7 tests）：真实 SQLite 全链 FILTERED CSV（UI 链）+ XLSX（Task 链）逐项断言 + Photo A/B 泄漏矩阵零泄漏；CURRENT_BATCH / FILTERED+criteria=None 经真实 Task 链与真实 UI 链双重拒绝（契约文案逐字断言、无导出文件、无 fallback）；ALL 回归（同库 8 行 approved-only 语义不变）。`PHASE_7_FINAL_AUDIT.md`（§1–§11）落档：**AC 8/8 PASS**，F-001 CLOSED，F-002 单跑 ×2 稳定复判为同一已知 flake。② **Phase 7 Closure**（`5aad031` docs(audit): close Phase 7 FEATURE-004）——PROJECT_STATUS §2 追加 Phase 7 记录；KNOWN_ISSUES 对账不变（F-001/F-002 审计级登记先例）；`PHASE_7_CLOSURE.md` 落档，**Phase 7 CLOSED**。③ **Phase 8 Baseline Audit**（`docs/health-check/PHASE_8_BASELINE_AUDIT.md`，独立实测）——Git 基线/架构/schema/依赖/测试/质量门全绿，但 Phase 8 无正式 Feature 契约 → **BLOCKED**（登记 P3 文档漂移 Finding 2 项 + 新发现 1 项）。④ **Phase 8 Contract Revision**（owner 提供执行规则 `docs/health-check/PHASE 8 — CONTRACT REVISION EXECUTION RULES.md` 解锁；本会话执行）——Finding Ledger 建立 + 逐条复验：F8-001 PROJECT_STATUS 当前状态漂移 / F8-002 KNOWN_ISSUES 版本头漂移 / F8-003 AI_ONBOARDING 自测答案漂移（三项均 F1 Documentation Drift，文档修订）；Worker/Qt 依赖契约（DEP-040/WRK-002/ADR-007/`qt_executor.py`）与 Schema/Configuration 契约复验一致（F0 无 Finding）；修订、验证、提交与 Post-Revision Audit 见 `docs/health-check/PHASE_8_CONTRACT_REVISION.md`。 |
| 当前质量门 | `ruff check .` 通过；`mypy src` 170 个源文件无问题；pytest 全量 **534 passed / 3 skipped**（F-002 已知 flake 偶发时单跑 ×2 稳定——Phase 4.2/5/6/7 历史记录一致）；`pip check` 无损坏依赖。 |
| 工作区 | Phase 7 全链（`d339904`→`747ccab`→`5aad031`）已提交，工作区 tracked 零改动；origin/main = `d762751`，本地领先 22 笔按 GIT-020 留待 owner push（非阻塞）。Phase 8 交付物（Baseline Audit / Contract Revision / Post-Revision Audit 报告）随后续提交入库。 |
| Remaining | 无代码/文档阻塞项。Phase 8 Contract Revision Finding 全部闭环（VERIFIED / F0）；F-002 维持 Known limitation（禁止修复）；LIMIT-001/002 维持。发版动作（GIT-020 归 owner）：`git push origin main` 将分支引用从 `d762751` 对齐至最新 HEAD（非阻塞）。 |
| Next Step | Phase 8（Contract Revision）完成后项目回归**条件触发等待区**：无排期事项、无已授权 Feature。后续任何新 Feature（含 CURRENT_BATCH 批次持久化等 Candidate 池条目）均须 owner 另立前置门 + Feature 契约授权，AI 不得自行选定。 |

---

## 6. Next Step（下一步开发计划）

**Phase 8（Contract Revision）执行状态**：owner 以 `docs/health-check/PHASE 8 — CONTRACT REVISION EXECUTION RULES.md` 授权本阶段——将 Baseline Audit 已确认的 Contract 偏差转为经验证、最小范围、可追溯的 Contract Revision。

1. ~~Phase 8 Baseline Audit~~ ✅ 已完成（2026-09-02，`PHASE_8_BASELINE_AUDIT.md`：基线健康 + BLOCKED 登记 3 项 F1 文档漂移 Finding）。
2. ~~Phase 8 Contract Revision~~ ✅ 已完成（Finding Ledger 全闭环：F8-001/002/003 F1 文档修订 VERIFIED；Worker/Qt 依赖契约与 Schema/Configuration 契约 F0 无 Finding；报告 `PHASE_8_CONTRACT_REVISION.md` + `PHASE_8_POST_REVISION_AUDIT.md`）。

吞吐线与历史阶段状态不变：Phase 4.2 / 5 / 6 / 7 全部 CLOSED（详见 §2）；v2.1.0 / v2.2.0 已发布；剩余非推理段改造（W2-3=A）、插件审批门、分发方案 B、CURRENT_BATCH 批次持久化等均为**条件触发型 Deferred/Candidate**——触发前不排期、不自动选定。发版收尾（非阻塞，GIT-020 归 owner）：`git push origin main` 对齐分支引用（本地领先 origin/main `d762751` 22 笔）。

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

---

> 本文件只描述当前状态；历史决策见 `.ai/ARCHITECTURE_DECISIONS.md`，当前问题见 `.ai/KNOWN_ISSUES.md`，路线图见 `.ai/business/roadmap.md`。
