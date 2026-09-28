# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**"项目现在开发到哪里了？"**
>
> 每次开发结束后刷新；不保留历史状态。
>
> Version: 1.35.0 · Last Updated: 2026-09-28 · Status: Live

---

## 1. Roadmap（开发路线图概览）

权威 15 步路线图：`.ai/business/roadmap.md`。

| Step | 名称 | 状态 |
|---|---|---|
| 0.5–11 | Walking Skeleton、基础设施、Domain、导入、扫描、缩略图、人脸识别、归档 | ✅ Completed |
| 12–14 | Main UI、Settings、Export | ✅ Completed |
| 15 | Plugin System | ✅ Completed |

M1–M7 及 Step 0.5–15 全部完成；阶段 B 业务增强 B1–B5 与收官加固阶段 0–3 已落地；发布工程至 v2.8.0（2026-09-13）。**2026-09-20 立项「人员名单导入与人脸分组匹配」重设计**：阶段 A（两段式导入，09-21 owner 验收 ✅）→ 阶段 B（人员与分组页，09-23 owner 验收 ✅）→ **阶段 C/D/E/F（2026-09-24 ~ 09-28 全部实施完成并冻结审查）**。**2026-09-28 完成全面工程健康体检（Stage 0–9，判 ATTENTION）与治理基线恢复（Stage 10）**；业务基线冻结正式生效待 owner 签核（Stage4.2 复审 8 项条件已满足，见 `docs/business-baseline/`）。

## 2. Current Step（当前开发阶段）

**治理基线恢复与 AUD-017 决策准备（Stage 10，2026-09-28）**——全面工程健康体检（同日，Stage 0–9，只读，判 **ATTENTION**：P0×0 / P1×1 / P2×10 / P3×15）后的第一轮整改，严格限定五项：

- **AUD-001（P1）SSOT 恢复**：本文件与 KNOWN_ISSUES/ARCHITECTURE_DECISIONS/DOCUMENT_INDEX/CHANGELOG 全部刷新至 HEAD `2823d1c` 口径（阶段 C–F 完成态、迁移链 001–008、体检发现登记）；根因（阶段收尾义务无书面登记载体）已在体检 DOCUMENTATION_AUDIT 立案。
- **AUD-003（P2）业务基线入库**：Stage1_BusinessFacts / Stage1_Handoff / Stage2_BusinessRules / Stage2_Handoff / Stage3_BusinessDiagrams / Stage4_FinalAudit / Stage4_1_FinalReview / Stage4_2_FinalFreezeReview 八份自 `D:\workFile\PhotoArchiver-BusinessReview\` 原样收入 `docs/business-baseline/`（正文零改写；来源/基准/有效性表见该目录 README）。
- **AUD-009（P2）依赖矩阵三方对齐**：`dependency-rules.md` §4 矩阵 5 行过期口径修正（app 组合根全开；infrastructure 增 application ports/dtos；presentation 增 domain/workers/plugins/app-context；workers 增 domain）+ DEP-001/030/040 同步——与 AST 实测及守卫测试 `test_layer_boundaries.py` 一致。
- **AUD-014（P2）Top-1 归档残留清理（F1-4）**：`archive_planner.py` docstring、`face-recognition-pipeline-and-archive.md` §6.2、`plugin-context-design.md` §3.1 三处全部改为 (person, photo)（E-SG-6）口径；识别侧 Top-1（ADR-017 语义）不受影响。
- **AUD-017（P2）决策材料**：`docs/decisions/AUD-017-person-embeddings-decision.md`——现状/数据链/三方案（A 激活旧表 / B 登记受限 / C 样本直读）对比，**Decision Required，待 owner 裁决**。

**阶段 C–F 实施摘要（2026-09-24 ~ 09-28，全部已入库并冻结审查）**：

- **阶段 C 可追溯识别运行**（`73657ec`/`7ec3173`/`a9f15b3`）：`RecognitionRun`/`FaceObservation` 数据链（migration `004`/`005`）；`RunRecognitionService` 逐脸观测 + recognition_results PENDING 兼容双写（审核/归档/导出/就绪全绿）；UI 入口切 `RecognitionScopeDialog`（范围 + 脸数档位 + 仅重试失败照片），重跑=新建 run；AST 守卫禁止旧 MatchPersons UI 路径回接。
- **阶段 D 人脸聚类**（`5c3c6d2`/`8d4c342`/`c543828`）：两段式算法（贪心簇心候选 ≥0.5 → complete-linkage 合并 **≥0.4 含等号**，owner 裁决修正实现偏差并以三点边界测试钉死）；低质量门限默认 0.0 禁用待 F 校准；表 `006_face_clusters`；时间排序 sort_key；D-4 UI 入口（人员页聚类区 + 结果对话框）。
- **阶段 E 配对工作台**（`ee5d7d4`/`f6e70b0`）：簇→人建议（sample-match max-cosine ≥0.40 优先，排除 rejected 对；顺序建议次之；**永不自动写归属**）；确认→sort_snapshot + D3 兼容 APPROVED + 整簇样本沉淀（007 `person_face_embeddings`，UNIQUE 幂等）；**E-SG-6**：兼容/归档去重作用域 = (person, photo)，不同人各自持有同照片归属；改派/解除回撤旧投影并 disable 旧样本（E-SG-5）；unassign 覆盖三入口撤销。
- **阶段 F 历史/性能/上线**（`e7d2735`/`d47d984`/`b3b8685`/`2823d1c`）：真实数据校准（473 照片/1441 脸/44 簇全链实测）；人员历史回填（幂等）；失败重试入口 + 失败清单导出；1000 张生命周期压测（取消→部分持久→重试覆盖剩余）+ 升级完整性演练（生产库副本 003→007 零丢失）；**冻结阻断修复**：BLK-1 归档按稳定 person_id 去重（migration `008`：archive_records.person_id 回填 + confidence 可空三态）+ D-1 审核批准可携身份 + D-2 阈值 `>=0.40`。
- **冻结审查链**：Stage4 独立审计（NOT-FREEZE-READY）→ `2823d1c` 修复 5 阻断 + 2 裁决 → Stage4.1 复审（代码级闭合）→ 基线收口（Stage1–3 文档对齐 2823d1c）→ **Stage4.2 终审：8 项冻结条件全部满足**（真库探针 + D-1 七层一致 + D-2 边界 0.39 不命中/0.40 命中），**待 owner 签核**。

### 历史发版锚点

| 版本 | tag → 提交 | 主题 |
|---|---|---|
| v2.3.0 | `e14409e` | 数据安全底线 + 运行时正确性（Phase A/B/C，D-B1~D-B8 裁决） |
| v2.3.1 | `90c46db` | 桌面 UI 中文化 + 工具栏纯化 + 人员筛选智能搜索（owner 裁决多轮折入单一发布；tag 二次重打至 CI 绿树） |
| v2.3.2 | `2aadcee` | 桌面复验修复：EXIF 拍摄时刻 + 照片墙 + 占位 |
| v2.4.0 | `93b7a15` | 库管理：删除登记 / 删除人员 / 重复处置 / 重扫对账 / prune-missing CLI（Phase E） |
| v2.5.0 | 2026-09-12 | Phase F：captured_at 回填 + 路径锚定 + CI 崩溃诊断 + Windows 保留名净化/扫描环防护 + 查询去重/未匹配哨兵 + 取消接线/UX + 覆盖率基线 + CLI 对等（ADR-035/036） |
| v2.6.0 | 2026-09-12 | 审计清零轮：插件目录接线 + 并行匹配分片 flush + cleanup-thumbnails + migrate + 未匹配筛选 + antelopev2 钉定（ADR-037/038/039） |
| v2.7.0 | 2026-09-12 | Phase G 运营轮：recognize CLI + 归档根设置 + 状态角标 + LIMIT-006 计数器 + 覆盖率门槛 |
| v2.8.0 | `fe7f46f` | Windows 桌面交付：安装包（在线/离线）+ download-models + frozen 适配 + 离线模型路径修复（ADR-031 方案B / ADR-041） |

更早锚点：v1.0.0→`49b2ac6`、v2.0.0→`ba3ad02`、v2.1.0→`bd52fbb`、v2.2.0→`f9fb8c5`。

---

## 3. Project Status（项目当前状态）

| 范围 | 状态 | 当前事实 |
|---|---|---|
| 15 步产品路线图 | ✅ | Step 0.5–15 全部实现并验证。 |
| 人员导入重设计（阶段 A–F） | ✅ 实施完成 | 全部入库至 `2823d1c`；业务基线见 `docs/business-baseline/`；冻结待 owner 签核。 |
| 版本链 | ⚠️ | v2.8.0 三处一致（pyproject / .env.example / CHANGELOG `[2.8.0]`）；**此后 47 个提交未发版**——CHANGELOG 已补 `[Unreleased]` 段（阶段 A–F 主要变更），无伪造发行版本。 |
| 测试基线 | ✅ | 全量 **1310 passed / 6 skipped / 0 failed**（2026-09-28 两跑实测 250.55s/263.36s）；行覆盖 **93.2%**（实测）；已知盲区：workers 错误分支 74.1%、配对守卫分支（AUD-019）。 |
| CI | ⚠️ | 本地三质量门全绿（ruff / mypy 258 文件 / pytest）；**main 领先 origin 44 提交未推送——HEAD 区间未经远端三平台矩阵验证（AUD-002，OPEN）**；LIMIT-006 CI 自愈 + darwin skip 维持。 |
| 业务基线 | ✅ 已入库 | `docs/business-baseline/`（Stage1–3 现行有效 + Stage4/4.1 历史 + Stage4.2 冻结复审），基线 `2823d1c`，来源与有效性表见其 README。 |
| 未决问题 | 📋 已登记 | 体检台账：**P1×1（AUD-001 文档滞后——本 Stage 10 已整改闭合）**；P2×10 中 AUD-003/009/014 本轮闭合，**AUD-002/004/015/017/019/023 保持 OPEN**（详见 `.ai/KNOWN_ISSUES.md` 体检登记节与台账 `docs/health-check/FINDINGS_LEDGER.md`）；AUD-017 决策材料就绪待 owner。 |
| Limit 登记 | 4 项 | LIMIT-001（真实缺模型 E2E 未入 CI）/ LIMIT-002（取消粒度——说明已按体检修正：识别取消延迟=剩余队列排空，AUD-023）/ LIMIT-004（Windows 本地子集顺序原生崩溃）/ LIMIT-006（macOS/Linux runner 环境漂移 SIGSEGV，CI 自愈 + darwin skip 维持），均 Low、不阻塞。 |
| Release body | ⏳ 待 owner | GitHub Release v2.8.0 资产已发布；body 签核流程同前。 |

### 数据库 Schema

Alembic 管理，迁移链 **`001_initial_v4` → `002_split_create_ddl` → `003_import_batches_and_roster` → `004_recognition_runs_and_observations` → `005_recognition_run_error_count` → `006_face_clusters` → `007_assignments_and_person_samples` → `008_archive_identity_and_confidence`**（head = 008）。003 导入批次/草稿 + roster_order；004/005 识别运行/观测；006 聚类；007 配对/样本；008 archive_records.person_id 回填 + recognition_results.confidence 可空（BLK-1/BLK-5，幂等守护 + downgrade 先回填 NULL）。每次启动 `alembic_runner` 自动 upgrade head（frozen 适配）。

---

## 4. Current Modules（当前模块状态）

| 模块 | 状态 | 关键位置 |
|---|---|---|
| Logging / Configuration | ✅ | `infrastructure/logging/`、`infrastructure/config/`（ADR-035 用户数据目录锚定） |
| Database | ✅ | Alembic 001–008（ADR-024/027）；17 张表全有读写方（体检对账） |
| Domain / Import / Scan / Thumbnail | ✅ | `domain/`、`application/services/`、`infrastructure/`；扫描枚举前置主线程（ADR-041） |
| 模型部署（下载/解包/校验/frozen） | ✅ | `model_deployment.py`（sha256 fail-closed）+ `insightface_loader.py` + `download-models` CLI |
| Recognition / Review（兼容链） | ✅ | InsightFace 检测/识别 + 审核闭环（D-1 身份选择器，`2823d1c`） |
| 可追溯识别运行（阶段 C） | ✅ | `run_recognition_service.py` + `recognition_runs`/`face_observations`（004/005）+ `recognition_scope_dialog.py`（范围/重试/失败清单导出） |
| 人脸聚类（阶段 D） | ✅ | `domain/services/face_clustering.py`（两段式 ≥0.5/≥0.4 含等号）+ `cluster_faces_service.py` + `006` + 结果查看 |
| 配对工作台（阶段 E） | ✅ | `pairing_workbench_service.py` + `domain/services/pairing.py` + `007`；E-SG-6 (person, photo) 兼容语义；样本沉淀/回撤 |
| 归档（身份去重） | ✅ | `archive_planner.py`/`archive_executor.py`——(person, photo) 去重（E-SG-6 + BLK-1 稳定身份，migration 008）；**docstring 已同步 E-SG-6 口径（AUD-014 整改）** |
| 历史回填 / 失败重试（阶段 F） | ✅ | `backfill_historical_people_service.py`（幂等）+ `recognition_failure_service.py` |
| UI / Settings / Export | ✅ | 主窗口、设置闭环、Excel/CSV/HTML 导出；CURRENT_BATCH fail-closed 延迟项 |
| 人员筛选 | ✅ | 三轴组合筛选 + 人员轴智能搜索（`presentation/person_matcher.py`） |
| 人员名单导入（阶段 A） | ✅ 已验收（09-21） | 两段式：`parse_import_draft_service.py`/`confirm_import_service.py`/`import_preview_dialog.py`（003） |
| 人员与分组页（阶段 B） | ✅ 已验收（09-23） | `manage_people_service.py`/`people_admin_page.py`；导航 5→6 |
| Plugins | ✅ | 发现/装载/生命周期 + PluginContext 读方法 + import_people（ADR-026/028/038） |
| 业务基线（文档） | ✅ 已入库 | `docs/business-baseline/`（Stage1–3 有效 / Stage4 系演进链）；决策材料 `docs/decisions/AUD-017-person-embeddings-decision.md` |

---

## 5. Last Session（最近一次开发记录）

| 项目 | 值 |
|---|---|
| 时间 | 2026-09-28（Windows 11 build 26200 / Python 3.11.9 / PySide6 6.11.1）；当日两段工作：**①全面工程健康体检（Stage 0–9，只读）**——十阶段完成审计基线/架构/业务逻辑/数据/测试/文档/可靠性安全性能/UI/交叉/综合报告；**②治理基线恢复（Stage 10）**——按体检台账执行 AUD-001/003/009/014 整改与 AUD-017 决策准备 |
| 会话范围 | ①实测复跑全量测试（1310 passed / 6 skipped，两跑）+ 覆盖率 93.2% + ruff/mypy；②AST 依赖图全量实测（19 组层间边缘 + SCC 零环）；③业务链行为审计（归档/审核/配对/识别运行/扫描/导入深查 + 冻结阻断修复逐链核验）；④Schema×17 仓储读写对账；⑤文档体系逐份核验；⑥任务生命周期与安全扫描；⑦十维交叉矩阵；⑧Stage 10 文档整改（详见 §2） |
| 关键产出 | 体检报告 10 份 + 台账（`docs/health-check/`，工作树未入库）：AUDIT_BASELINE / ARCHITECTURE_AUDIT / CODE_LOGIC_AUDIT / DATA_PERSISTENCE_AUDIT / TEST_QUALITY_AUDIT / DOCUMENTATION_AUDIT / RELIABILITY_SECURITY_PERFORMANCE_AUDIT / UI_AUDIT / CROSS_DIMENSION_RECONCILIATION / FINAL_HEALTH_CHECK（判 ATTENTION）+ FINDINGS_LEDGER（P0×0/P1×1/P2×10/P3×15 + AR×5）；Stage 10：`docs/business-baseline/`（8 文件 + README 来源表）、`docs/decisions/AUD-017-person-embeddings-decision.md`（Decision Required）、dependency-rules §4/DEP-001/030/040 对齐、archive_planner docstring + 两文档 E-SG-6 口径、本文件与 KNOWN_ISSUES/ADR（ADR-042~046）/DOCUMENT_INDEX/CHANGELOG 刷新 |
| 当前质量门 | 体检实测：pytest **1310 passed / 6 skipped** ×2、ruff 全绿、mypy 258 文件零错、覆盖率 93.2%；Stage 10 验证：分层守卫测试 + archive planner 定向测试 + ruff/mypy（改动文件）全绿（详见提交信息） |
| 工作区 | main @ `2823d1c`；体检产物与业务基线等新文件随本轮治理提交入库；**未推送**（push 属 owner，GIT-020） |
| Remaining | 见 §6 Next Step。 |

---

## 6. Next Step（下一步开发计划）

**待 owner**：

| # | 事项 | 依据 |
|---|---|---|
| 1 | **业务基线冻结签核**（Stage4.2 八项条件已满足，签核即冻结生效） | `docs/business-baseline/Stage4_2_FinalFreezeReview.md` §9 |
| 2 | **AUD-017 裁决**：person_embeddings 候选源三选一（A 激活旧表 / B 登记受限 / C 样本直读多样本）——选择后补 ADR；选 A/C 须同补识别侧阈值边界证据进校准报告（顺带闭合 F1-2） | `docs/decisions/AUD-017-person-embeddings-decision.md` |
| 3 | **推送 44 提交过远端 CI**（AUD-002）+ 发版评估（`[Unreleased]` 段如何切版本、手册阶段 C–F 功能章节补齐） | 体检 §11 发布风险 |
| 4 | 阶段 B 复审五点复验（中文文案/拖拽无空行/删除预选/导入即刷/移动选区跟随） | 历史在案（09-23） |
| 5 | v2.8.0 Release body 签核 + A-1（CURRENT_BATCH）/ A-3（代码签名）决策 | 历史在案 |
| 6 | 体检 P2 整改排期：AUD-015（归档 FS/DB 失败语义：补对账 or 声明取舍）、AUD-023（取消延迟：`shutdown(cancel_futures=True)` 方向）、AUD-019（workers/配对守卫补测试）、AUD-004 残余（全链贯通回归一条）、AUD-010（DEP §17 文件 I/O：补端口 or 修订规则） | `docs/health-check/FINDINGS_LEDGER.md` |

**可立项**：全链贯通回归测试（导入→配对确认→归档执行单条）；AUD-023 取消延迟修复。**明确不做**（历史裁决维持）：i18n 实装、自动更新、macOS 安装包、批次撤销、重排性能 P1/P2。

---

## 7. Key Files（关键文件索引）

| 职责 | 文件 |
|---|---|
| 运行状态唯一快照 | `.ai/PROJECT_STATUS.md`（本文件） |
| 架构决策（ADR-001~046） | `.ai/ARCHITECTURE_DECISIONS.md`（042~046 = 阶段 C–F 裁决补登记） |
| 当前问题与限制 | `.ai/KNOWN_ISSUES.md`（含体检登记节） |
| 文档体系导航 | `.ai/DOCUMENT_INDEX.md` |
| 业务基线（现行/历史/冻结） | `docs/business-baseline/`（README 含来源与有效性表） |
| Owner 决策材料 | `docs/decisions/AUD-017-person-embeddings-decision.md` |
| 体检报告与台账 | `docs/health-check/`（工作树产物，含 FINDINGS_LEDGER） |
| 用户使用手册 | `docs/user-guide/manual.md`（阶段 C–F 功能章节待补，Next Step #3） |
| 依赖矩阵（SSOT） | `.ai/rules/dependency-rules.md` §4（v1.2.0 已对齐守卫测试） |
| 数据库初始化/迁移 | `sqlite_connection.py`、`alembic_runner.py`（链 `001`→`008`，`alembic/versions/`） |
| 可追溯识别运行 | `run_recognition_service.py` + `recognition_scope_dialog.py` + `recognition_failure_service.py` |
| 聚类 / 配对 | `domain/services/face_clustering.py` / `pairing.py`；`cluster_faces_service.py` / `pairing_workbench_service.py` |
| 归档（身份去重） | `archive_planner.py` / `archive_executor.py`（E-SG-6 + BLK-1） |
| 分层边界守卫 | `tests/unit/architecture/test_layer_boundaries.py` |
| 质量验证 / 发布工作流 | `tests/`、`.github/workflows/ci.yml` / `release.yml` |

---

> 本文件只描述当前状态；历史决策见 `.ai/ARCHITECTURE_DECISIONS.md`，当前问题见 `.ai/KNOWN_ISSUES.md`，业务基线见 `docs/business-baseline/`，路线图见 `.ai/business/roadmap.md`。
