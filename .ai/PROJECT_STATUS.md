# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**"项目现在开发到哪里了？"**
>
> 每次开发结束后刷新；不保留历史状态。
>
> Version: 1.38.0 · Last Updated: 2026-09-29 · Status: Live

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

**P3 命令契约与数据模型清偿（Stage 13C-B，2026-09-29）**——**AUD-016 FIXED（体检前提经复核证伪）**：应用边界早已存在权威校验（`ArchivePhotosService._resolve_conflict_strategy`：自有常量 + strip/lower 归一 + 非法值 ValueError，`test_archive_photos_service.py:135` 专项测试在案），体检"命令层无校验"结论不完整；本轮补两项防御纵深：executor 未知策略 `else` fail-closed（此前目标已存在时静默落入复制 = 等同未授权覆盖）、application/settings 两侧合法集合同值测试防漂移。**AUD-018 三子项全部 FIXED（ADR-052，登记既有设计）**：**018-A 级联**——recognition_results/archive_records person_id = SET NULL（记录描述照片，删人后照片与归档事实保留、身份匿名化）vs cluster_person_assignments/person_face_embeddings = CASCADE（映射与样本从属于人，无独立生命期），与业务基线记载一致，**不改 migration**；**018-B status**——裁定**域枚举为唯一状态机**，不为 002/008 冻结表补 DB CHECK，仅补齐唯一缺口：`RecognitionResult.__post_init__` 增加 status 类型校验（dataclass 不强制类型，此前可构造非法状态直达 DB，与 ArchiveRecord 同口径）；**018-C file_hash**——定性为溯源 metadata（Type D），**不做去重键**（同文件编辑后重导是合法业务行为，按内容去重会静默跳过合法重导），保留字段、明确用途。新增契约测试 12 项。验证：全量 **1367 passed / 8 skipped**、ruff/mypy（261 文件）绿。

**P3 架构与结构债务清偿（Stage 13C-A，2026-09-29）**——AUD-011（UseCase Protocol 双轨制）**FIXED**：盘点 11 文件/14 Protocol（每个恰一实现；11 个有 presentation/worker 边界标注消费者，3 个无但服务为活的组合根能力，测试引用 2/14）→ 核心问题以代码事实定案：**本项目单进程 + 单一组合根（`ApplicationServices` 具体类字段），Protocol 是跨边界标注机制而非 service 强制壳**；确立 **ARC-010** 使用准则 + **ADR-050**（含 3 个契约冗余候选的删除变体——触及 `application/__init__.py` 公开导出，属 Owner API 决策，记录为待决项，代码零变更）。AUD-013（`common/` 空置 + main_window 规模）**FIXED**：①`common/` 为 1 行空骨架、全仓零导入 → **删除**并同步 DEP §3/§4 矩阵、ARC-008（改写为 Removed）、project-structure（ADR-051）；②main_window 职责盘点（63 方法 = 事件路由 29 / UI 构建 8 / 状态同步 5 / 编排辅助 11，业务规则与文件/SQL 触点为零）→ 判定"大但职责已外移"，**不做代码拆分**（行数非拆分理由），确立 **ARC-011** 职责边界规则防业务逻辑回潮。验证：全量 **1355 passed / 8 skipped**、ruff/mypy（261 文件）绿。

**P3 文档与治理卫生清偿 · 第一轮（Stage 13A，2026-09-29）**——体检 P3 共 14 项，按类别分批处置；本轮仅处理文档/治理/仓库卫生类 5 项：**AUD-006**（仓库杂物：`jobs34.json`/`jobs_tmp.json`/`runs_all.json`（93KB CI 查询 dump）/`release_check_tmp.yml`（工作流草稿副本）——经核验无任何代码/测试/文档引用（仅体检台账提及），`git rm` 出库 + `.gitignore` 增加 `jobs*.json`/`runs_all.json`/`*_tmp.yml`/`*.part` 规则并探针验证生效）；**AUD-007**（pre-commit 声明与配置脱节——处置 Option B：删除 dev.txt 钉定与 README 开发栈提及。理由：项目自始无 `.pre-commit-config.yaml`、`.ai/rules/git-rules.md` 无 hook 规范，真实质量门禁是 CI（`ruff check .` + `mypy src` + pytest）+ 手动工具调用；引入 hooks 属开发工作流变更，须 owner 立项而非卫生整改）；**AUD-022**（历史规划文档无标记——`DEVELOPMENT_ROADMAP.md` 与 `NEXT_PHASE_FEATURE_DEVELOPMENT_PLAN.md` 加 `Status: Historical` 横幅：Superseded by / Effective baseline `928981a`+ / 逐条列明已知失真点；历史正文原样保留）；**AUD-005 / AUD-008** 标记 RESOLVED BY PRIOR STAGE（Stage 10 合并 LIMIT 双表、LIMIT-006 去重、Stage 12C 更新 LIMIT-002 说明；LIMIT-001/004 经复核仍准确）。本轮零生产代码行为变更。剩余 9 项 P3（设计/测试/数据/UI 类：AUD-011/012/013/016/018/020/021/024/025）留 Stage 13B/13C。

**AUD-010 Application 文件 I/O 架构边界定性与处置（Stage 12E，2026-09-29）**——**DEP §17 定性 = Type B（规则过度严格）**：全量盘点确认 application 层真实文件 I/O 恰 3 处且全部业务性（归档复制+containment、名单批次哈希、失败清单导出），非业务性 I/O 为零；原禁令"应用层永不触碰文件"与本项目的工作流编排定位冲突。**处置 = 端口化（不取消禁令、不建通用 framework）**：新增 `ArchiveFileStore` / `FailureListWriter` 业务语义端口 + `RosterTableReader.read_bytes` 协议扩展 + 两个基建实现（FS 逻辑逐字迁移，行为零变化）+ **DEP-072** 取代 §17 绝对表述 + 守卫测试 `test_application_has_no_direct_file_io`（AST 逐文件断言，负向验证已捕获注入违规）。行为不变：三冲突策略、dry-run、containment/symlink 防护、M-4 mtime 语义、AUD-015 原子复制与 FS/DB 一致性模型全部由既有套件证明。ADR-049。验证：全量 **1355 passed / 8 skipped**（2 项为 Windows symlink 平台门控）、ruff/mypy 绿。

**AUD-015 归档 FS/DB 一致性定性与处置（Stage 12D，2026-09-29）**——故障注入定性（真实 SQLite + commit 边界崩溃注入，6 项测试）：**一致性模型定案（ADR-048）：Accepted Partial State + retry 幂等收敛**——批级 DB 原子 × 非事务 FS 复制为声明的设计取舍（伪事务否决：SQLite 无法回滚 FS 副作用）；窗口 1（批级回滚→孤儿）经重试幂等收敛（skip→SKIPPED/overwrite→ARCHIVED/rename→RENAMED+dup 兄弟）；**窗口 2（mid-copy 半写 + skip = 永久锁定损坏归档）为 Type B 恢复缺口 → 最小修复**：`_copy_file` 经同目录 .part + os.replace 原子落位（目标"存在即完整"，失败清理 .part，符号链接拒绝语义不变）；窗口 3（DB 成功后文件外部消失）executor 无法产生、无主动检测——已知边界。成功定义 = FS+DB 均成功。验证：全量 **1348 passed / 6 skipped**、ruff/mypy 绿。

**AUD-023 取消延迟整改（Stage 12C，2026-09-29）**——根因（体检 Stage 6/F-04）：`RunRecognitionService.execute` 一次性 submit 全部 futures，取消仅 break 消费循环，with 块退出 `shutdown(wait=True)` 排空全部已入队任务（千张 ≈60s）。**组合策略最小修复**：①取消分支内阻塞等待前批量取消 `futures[index:]`（executor 为任务内私有实例）；②`FaceAnalysisTask` 入口取消检查（闭合条目完成→下一轮检查间 worker 拾取竞争；`FaceAnalysisResult` 增 `cancelled` 标记，不产统计计数）；③with 块内兜底取消全部 future。语义不变：PENDING 不再启动 / RUNNING 单张安全点完成 / COMPLETED 保留，LIMIT-002 粒度不变，AR-02 维持。证据：修复前确定性复现（Event 门控，join 30s 超时、61s 排空）→ 修复后 4 场景 14/14 轮稳定（0.72–0.87s）；全量 **1342 passed / 6 skipped**。MatchPersons 遗留并行路径（无服务级取消，UI 已解绑 ADR-042）不在本阶段范围。

**AUD-019 workers/配对守卫测试补强（Stage 12B，2026-09-29）**——补齐体检覆盖缺口（真实 SQLite 集成测试 15 项，生产代码零改动）：**Workers**（`test_aud019_worker_lifecycle_sqlite.py` 6 项）：ConfirmImportTask 主路径（此前完全未覆盖：事件序列+真实落库+完成进度标记）、真实失败（批次不存在）→ failed terminal（错误信息保留、恰好一次、无假成功）→ 重试成功零重复副作用、ClusterFacesTask/Scan/Run 无 binder 兜底分支走真实链（Cluster 天然无 binder；Scan/Run 经真实 execute 绑定方法的 binder 剥离代理）、取消→cancelled terminal 且零 run 产生、多订阅者失败终态 exactly-once；**Pairing 守卫**（`test_aud019_pairing_guards_sqlite.py` 9 项）：不存在对象/双重确认/reject 后确认/非法簇状态/人员删除真实级联后陈旧建议被拒/簇删除 FK CASCADE 后作用域隔离（其他簇建议不受影响）/TOCTOU delete-then-update 注入触发受影响行数守卫/双实例竞争单胜者/clamp 边界。覆盖率：application_tasks 74.1%→81%（定向）、pairing_workbench 89.8%→92%。验证：全量 **1338 passed / 6 skipped**、ruff/mypy 绿。

**AUD-004 全链贯通回归（Stage 12A，2026-09-29）**——补齐体检遗留的"两段式导入→扫描→识别→聚类→配对建议→人工确认→归档规划→归档执行"单条真实链回归：`tests/integration/test_aud004_full_chain_regression.py` 4 场景（真实 SQLite/仓储/服务，仅 AI 检测器按任务书允许用可控假件）：A 标准冷启动（重复 execute 去重 + 全批重跑不覆盖人工决定/兼容 (person,photo) 幂等/归档零重复，且第二代建议自动切换 sample_match 路径——双路径语义得证）、B 簇<人不强配、C 簇>人未确认簇不归属、§9 单项失败隔离+FAILED 重试（现状语义钉定，不涉 AUD-015）。**期间暴露并修复真实接缝缺陷（AUD-004 范围内最小修复）**：`RunRecognitionService` 构造 run_photos 快照时丢弃照片 captured_at → 聚类 sort_key 经真实链路恒为 `~|~|创建序`，Stage D 时间排序从未真实生效；最小修复=服务注入 `PhotoRepository`（可选参数，兼容既有构造）+ 快照填充 captured_at + 装配接线 + 测试快照接缝断言；生产链时间排序自此真实生效。验证：全量 **1323 passed / 6 skipped**、ruff/mypy 绿。

**AUD-017 实现闭环（Stage 11A 决策 + 11B 实现，2026-09-28）**——owner 正式裁决 **Option C**（`person_face_embeddings` 作为后续批次样本相似度候选来源）+ **K-3=suggested 建议层**（样本相似度仅生成 `similarity_suggestion`，不得直接形成身份确认），并附加约束：冷启动 FaceCluster → sort_key → roster_order → ordered_suggestion → 人工确认 → 样本沉淀 链不变、`person_embeddings` 不恢复生产写入路径。**实现核验结论：Option C 的生产链在阶段 E 已存在**（`SuggestPairingsService` 经 `list_enabled()`（enabled=1，person_id 确定序）读候选样本 + `NumpyCosineSimilarityFactory` 多样本 max 余弦 + 规则① `sample_match` 建议 ≥0.40 + 规则③冷启动补位，全部落 suggested 层），本阶段完成证明与登记：**真实 SQLite 闭环集成测试 4 项**（`tests/integration/test_aud017_sample_suggestion_sqlite.py`——主闭环含 disabled 样本排除与解除→重建议→重复确认样本幂等 / 零样本冷启动仅 ordered / 平分 tie-break 确定性 / 维度不一致 fail-closed）、domain 规则钉定 3 项（cluster<persons 不强配 / 平分首位 / 高分胜出）、kernel 钉定 2 项（量化 0.4/0.6 边界 + 混维 fail-closed）；**生产代码零改动**。登记：ADR-047、决策文档 §7 已填裁决、KNOWN_ISSUES 移除 AUD-017（闭环）。遗留边界（ADR-047 登记）：识别兼容链对 `person_embeddings` 的遗留读不动（候选可证恒空）；多样本大库性能路径为实现期关注点；识别侧阈值边界证据随实现轮补校准报告（F1-2）。

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
| 人员筛选 | ✅ | 三轴组合筛选 + 人员轴智能搜索（`presentation/person_name_ranker.py`） |
| 人员名单导入（阶段 A） | ✅ 已验收（09-21） | 两段式：`parse_import_draft_service.py`/`confirm_import_service.py`/`import_preview_dialog.py`（003） |
| 人员与分组页（阶段 B） | ✅ 已验收（09-23） | `manage_people_service.py`/`people_admin_page.py`；导航 5→6 |
| Plugins | ✅ | 发现/装载/生命周期 + PluginContext 读方法 + import_people（ADR-026/028/038） |
| 业务基线（文档） | ✅ 已入库 | `docs/business-baseline/`（Stage1–3 有效 / Stage4 系演进链）；决策材料 `docs/decisions/AUD-017-person-embeddings-decision.md` |

---

## 5. Last Session（最近一次开发记录）

| 项目 | 值 |
|---|---|
| 时间 | 2026-09-28 ~ 09-29（Windows 11 build 26200 / Python 3.11.9 / PySide6 6.11.1）；五段工作：**①全面工程健康体检（Stage 0–9，只读）**；**②治理基线恢复（Stage 10，commit `a01f11b`）**；**③AUD-017 决策准备（Stage 11A）**——决策材料 v2（真实库探针闭合基线 UNKNOWN-2：生产库 person_embeddings 0 行 / alembic 003 / 472 条识别结果 person_id 全 NULL）→ **owner 正式裁决 Option C + K-3=suggested 层**；**④AUD-017 实现闭环（Stage 11B）**；**⑤AUD-004 全链贯通回归（Stage 12A，09-29）**——4 场景真实链回归 + 聚类时间排序接缝缺陷最小修复（快照 captured_at）；**⑥AUD-019 workers/配对守卫测试补强（Stage 12B，09-29）**——15 项真实 SQLite 守卫/生命周期测试；**⑦AUD-023 取消延迟整改（Stage 12C，09-29）**——3 处最小生产修复 + 4 场景确定性取消证据测试；**⑧AUD-015 归档 FS/DB 定性（Stage 12D，09-29）**——6 项故障注入 + ADR-048 一致性模型 + 原子复制修复；**⑨AUD-010 文件 I/O 端口化（Stage 12E，09-29）**——2 端口+2 实现+DEP-072+守卫+8 项契约测试；**⑩P3 治理卫生第一轮（Stage 13A，09-29）**——仓库杂物出库+gitignore、pre-commit 声明收敛、历史文档标记 |
| 会话范围 | Stage 11A：决策文档 v2（现状/数据链/三方案七维对比/冲突 K-1~K-3）；Stage 11B：按裁决核验生产链（Option C 能力阶段 E 已存在）→ 新增真实 SQLite 闭环集成测试 4 项 + domain 钉定 3 项 + kernel 钉定 2 项（生产代码零改动）→ 登记 ADR-047 / 决策文档 §7 / KNOWN_ISSUES 移除 AUD-017 / CHANGELOG / 本文件 |
| 关键产出 | 体检报告 10 份 + 台账（`docs/health-check/`，工作树未入库）；Stage 10：`docs/business-baseline/`（8 文件 + README）、`docs/decisions/AUD-017-person-embeddings-decision.md`、dependency-rules 对齐、Top-1 三载体清理、SSOT 刷新；Stage 11A/11B：裁决登记 + ADR-047 + `tests/integration/test_aud017_sample_suggestion_sqlite.py`（§14 硬要求：真实数据库→真实候选仓储→真实 kernel→真实建议→人工确认→样本沉淀，零 stub） |
| 当前质量门 | 全量 pytest **1367 passed / 8 skipped**（体检基线 1310 → 11B +9 → 12A +4 → 12B +15 → 12C +4 → 12D +6 → 12E +7 → 13C-B +12）；ruff / mypy 全绿 |
| 覆盖率（可复现） | **93.8%（10480 / 11172 行语句，coverage 7.16.0，branch coverage 关闭）**——测量范围 `src/photo_archiver/`（262 个 .py，经 `pyproject` 的 `pythonpath = ["src"]` 解析）；**分母不含**：根入口 `main.py`（CLI）、`tools/`、`scripts/`、`tests/`、`alembic/`（非 `photo_archiver` 包）；无 `[tool.coverage]` 配置、无 `.coveragerc`、无 omit 规则（仅 coverage 默认的 `# pragma: no cover`）。复现命令：`.venv/Scripts/python.exe -m pytest tests/ -q --cov=src/photo_archiver --cov-report=json`（本地）；CI 门禁命令 `pytest --cov=photo_archiver --cov-fail-under=90`（仅 Linux job，见 `.github/workflows/ci.yml`） |
| 工作区 | main；Stage 11A/11B 产物随本轮提交入库；**未推送**（push 属 owner，GIT-020） |
| Remaining | 见 §6 Next Step。 |

---

## 6. Next Step（下一步开发计划）

**待 owner**：

| # | 事项 | 依据 |
|---|---|---|
| 1 | **业务基线冻结签核**（Stage4.2 八项条件已满足，签核即冻结生效） | `docs/business-baseline/Stage4_2_FinalFreezeReview.md` §9 |
| 2 | **推送 44+ 提交过远端 CI**（AUD-002）+ 发版评估（`[Unreleased]` 段如何切版本、手册阶段 C–F 功能章节补齐） | 体检 §11 发布风险 |
| 3 | 阶段 B 复审五点复验（中文文案/拖拽无空行/删除预选/导入即刷/移动选区跟随） | 历史在案（09-23） |
| 4 | v2.8.0 Release body 签核 + A-1（CURRENT_BATCH）/ A-3（代码签名）决策 | 历史在案 |
| 5 | 体检 P2 已全部闭合（Stage 10–12E）；P3 剩余 2 项（AUD-024 连接显式关闭、AUD-025 审核空队列语义）→ Stage 13C-C；另有 ADR-050 记录的 3 个 Protocol 删除变体待 Owner API 决策；推送 + 远端 CI + 发版（#2，owner 操作）、阶段 B 复验（#3）、Release body 签核（#4）、第 5 轮体检候审、审计产物入库决策 | `docs/health-check/FINDINGS_LEDGER.md` |
| 6 | AUD-017 尾随项：识别侧阈值边界证据补入校准报告（F1-2 闭合）；`person_embeddings` 遗留读清理与否（清理属独立裁决） | ADR-047 |

**可立项**：全链贯通回归测试（导入→配对确认→归档执行单条）；AUD-023 取消延迟修复。**明确不做**（历史裁决维持）：i18n 实装、自动更新、macOS 安装包、批次撤销、重排性能 P1/P2。

---

## 7. Key Files（关键文件索引）

| 职责 | 文件 |
|---|---|
| 运行状态唯一快照 | `.ai/PROJECT_STATUS.md`（本文件） |
| 架构决策（ADR-001~052） | `.ai/ARCHITECTURE_DECISIONS.md`（042~046 = 阶段 C–F 裁决补登记；047 = AUD-017 Option C；048 = 归档 FS/DB 一致性模型；049 = Application 文件访问端口化；050 = UseCase Protocol 使用准则；051 = common 移除 + MainWindow 职责边界；052 = 数据生命周期与状态机职责定案） |
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
