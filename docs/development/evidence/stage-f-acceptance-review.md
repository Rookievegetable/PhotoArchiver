# Stage F 冻结评审验收报告（Final Acceptance / Freeze Review）

> 评审对象：HEAD `b3b8685`（工作树干净）。评审性质：Stage F 收口 / Stage C–F 冻结门。
> 评审依据：`.ai/rules/review-rules.md`、`.ai/rules/audit-methodology.md`、
> `docs/development/people-import-face-clustering-development-plan.md` §阶段 F、
> `docs/development/people-import-face-clustering-execution-plan.md` §阶段 F。
> 本报告只判定验收状态并登记发现，不含任何实现性修改。

## 0. 结论

**有条件通过（CONDITIONAL PASS）** —— 代码层未发现功能缺陷，质量门全绿，
Stage D/E 冻结契约保持 additive-only；但 **3 项冻结收口条件未闭合**
（SSOT 登记、Owner 裁决登记、端到端贯通回归）+ **1 项需 Owner 裁决的新现象**
（取消延迟 60.0s 的根因与既有说明不符）。修完 P0-F1/F2/F3 后方可宣告 Stage F 冻结。

| 质量门 | 结果 | 命令/证据 |
|---|---|---|
| Ruff | ✅ | `ruff check src tests tools` |
| MyPy | ✅ | `mypy src`（258 source files，0 error） |
| 全量测试 | ✅ | 1292 passed / 6 skipped / 229.62s |
| 工作树 | ✅ 干净 | `git status --porcelain` 空 |
| 契约稳定 | ✅ additive | `git diff f6e70b0 b3b8685`：domain+infrastructure 仅 +39 行（person repo 三个新方法），无删改 |

## 1. Owner 任务书逐项判定

| # | 检查点 | 判定 | 证据锚点 |
|---|---|---|---|
| 1 | 阈值/质量公式校准 | ⚠️ 部分 | `stage-f-calibration-report.md` §2 有 4 项分布证据；**`match_threshold` 零证据**（见 F-05）；本轮未改阈值，符合"改动须先经 Owner 裁决"约束 |
| 2 | 真实数据全流程 | ✅ | `evidence/stage-f-real-run.json`：473 照片 / 1441 脸 / 44 簇 / 6 确认 / 199 样本 / 199 计划项；与生产库实测一致 |
| 3 | 千级取消/重试/续跑压测 | ⚠️ 部分 | `evidence/stage-f-lifecycle-stress.json` 1000 张三段全绿 + 确定性回归 `test_stage_f_lifecycle.py`（1200 张）；**取消延迟根因误述**（见 F-04） |
| 4 | 老旧库升级完整性 | ✅ | `evidence/stage-f-upgrade-real.json` + `tests/integration/test_upgrade_integrity.py`（逐行对比零丢失 / 新表空初始化 / 升级→回填幂等）；生产库仍处 alembic `003`，场景真实 |
| 5 | 历史人员回填 | ✅ | `tools/backfill_historical_people.py`（`--dry-run`）+ `BackfillHistoricalPeopleService`；幂等、不覆盖既有 `source_batch_id`/`roster_order` |
| 6 | 历史照片重分析入口 + 失败清单导出 | ✅ | `RecognitionFailureService` + `recognition_scope_dialog.py` 重试/导出入口；`retryable = run 输入照片 − 已产出观测照片` |
| 7 | 端到端回归（导入→确认→识别→聚类→配对→审核→归档） | ❌ 未贯通 | 见 F-03：无任何单条回归覆盖全链；真实运行亦未覆盖两段式导入、审核、归档执行 |
| 8 | Stage D/E 冻结契约保持 | ✅ | `pairing_workbench_service.py` / `cluster_faces_service.py` / `suggest_pairings_service.py` 在 `f6e70b0..b3b8685` **零改动** |
| 9 | `(person, photo)` 规则一致性 | ⚠️ 代码一致、文档缺失 | 见 F-02 |

## 2. `(person, photo)` 规则代码符合性（专项）

| 位置 | 实际语义 | 判定 |
|---|---|---|
| `pairing_workbench_service.py:303-319` | 同一 person 的同照片多观测 → `seen_photos` 去重，仅 1 条 APPROVED；不同 person 的同照片归属互不覆盖（`result.person_id == person_id` 判等） | ✅ 符合 |
| `test_stage_e_remediation.py:364-395` | 同照片 2 人 → `planned_count == 2`，计划项集合 `{(人物A,photo),(人物B,photo)}` | ✅ 符合 |
| `test_stage_e_remediation.py:398-431` | 改派后 planner 只出当前身份（A 投影回收） | ✅ 符合 |
| `recognition_failure_service.py` / `recognition_scope_dialog.py` | 失败/重试以 **照片** 为单位（一照片要么产出观测要么没有，与 person 无关） | ✅ 与规则不冲突 |

**结论：实现与测试内部一致，符合 `(person, photo)` 去重作用域。** 但该裁决在仓库内
**没有权威文档载体**（ADR 无条目、`PROJECT_STATUS.md` 冻结于 2026-09-23 未覆盖 C–F、
`manual.md` 未涉及）——详见 F-02。


## 3. 发现清单

### F-01 【P0·MAJOR】`KNOWN_ISSUES.md` 未登记 Stage C–F 未决项（SSOT 违约）

`KNOWN_ISSUES.md` 头部为 `v1.16.0 / Last Updated 2026-09-21`——早于 Stage C 起始，
Stage C/D/E/F 全程未写入任何新条目。而 `.ai/DOCUMENT_INDEX.md` §3 明确
「当前未决问题 / 技术债」的**唯一权威文档**就是它。当前处于「口头记录在案、
SSOT 无载」状态的具体项：

| 应登记未登记项 | 目前唯一的记录位置 | 风险 |
|---|---|---|
| 失败分类为 run 级、非 per-photo 语义缺口 | 提交信息 / calibration 报告 §4 | 换会话即丢失 |
| E-SG-4「合格样本」未定义（样本沉淀=全部有嵌入成员） | 仅代码注释 + 报告 §2 行 38 | 冻结后无人认领 |
| 44 簇聚类质量人工复核 | 仅报告 §6 | Owner 动作无追踪 |
| 取消传播 60s（新现象，见 F-04） | 无 | 完全未登记 |

`git grep -n 'E-SG' -- .ai/` 命中数为 0，可复现。**这是本次评审唯一的流程性 P0**：
冻结意味着后续会话只读 SSOT，未登记 = 事实上不存在。

### F-02 【P0·MAJOR】Owner 裁决未进 ADR 登记册

`ARCHITECTURE_DECISIONS.md` 最后一条为 **ADR-041（2026-09-13）**，早于 Stage A
（2026-09-20 起）。以下已落地并已被测试锁定的裁决**均无 ADR 条目**：

- Stage C–E 的 D1–D6 设计裁决（含 D3「确认即写 APPROVED，确认即可归档」——
  该条实际**改变了「审核」环节的定义**，影响用户可见语义）；
- Stage D 合并门 inclusive（提交 `8d4c342`，提交信息自述 "per owner ruling"）；
- **E-SG-6 `(person, photo)` 去重作用域**（提交 `f6e70b0`）——即本次评审第 9 项
  要核对的「Owner 最新规则」，仓库内**不存在可比对的权威文本**，只能以代码+测试
  反推。这使「文档是否与规则一致」严格意义上**不可判定**；
- E-SG-4 的「暂不定义」是**未裁决**而非已裁决，需以 KNOWN_ISSUES/Open 形式挂账。

### F-03 【P0·MAJOR】端到端回归未贯通（执行计划明列验收项）

规格原文：dev-plan:242 与 exec-plan:224 均要求
「端到端回归（导入→确认→识别→聚类→配对→审核→归档）」。实测覆盖形态：

| 链段 | 覆盖位置 | 缺口 |
|---|---|---|
| 导入→确认（两段式名单） | `test_import_draft_flow.py` | 与识别链**断开** |
| 识别→聚类 | `test_cluster_faces_service.py` 等 | 用 InMemory，不接导入 |
| 聚类→配对→确认 | `test_stage_e_pairing_services.py` | 用 fixture 造簇，不从识别来 |
| 确认→归档 | `test_stage_e_remediation.py:364` | **止于 `ArchivePlanner.plan()`，且全为 `_Fake*Repository`** |
| 归档执行（写盘） | `test_step11_archive_e2e.py:114` | 走 **legacy 路径**（旧 PENDING→APPROVED 审核），**不由 Stage E 确认喂入** |
| 真实数据 | calibration §1 | 未含两段式导入、未含归档执行 |

即：Stage E 产出的 APPROVED 归属 → 真实 SQLite → `ArchiveExecutor` 落盘，
**从未被任何一次自动化或真实运行验证过**。机械推演应可工作（planner 读
`recognition_results`），但属未验证推断，不得作为冻结依据。

> 注：D3 之下「审核」已由配对确认承担，审核中心继续消费历史 PENDING——
> 因此本项缺口的实质是「**缺一条 SQLite + 文件系统的贯通回归**」，而非缺功能。

### F-04 【P1·需 Owner 裁决】取消延迟 60.0s：报告归因与代码不符，且非 LIMIT-002 所覆盖

事实（`evidence/stage-f-lifecycle-stress.json`；工具为实测非粗采样——
`stress_lifecycle_stage_f.py:199-203` 在 `service.cancel()` 后 `thread.join()` 计时）：

- t+30s 请求取消 → 实际 60.0s 后返回；`elapsed 90.0s`；保留 337 观测；
- Phase 2 重试 663 张耗时 63.33s ⇒ **10.4 张/s**；
- 60.0s × 10.4 ≈ **624 张在取消之后被重新检测，且结果全部丢弃**（≈62% 算力浪费）。

根因（`run_recognition_service.py:68-93`，可复核）：一次性 `pool.submit` 全部照片 →
取消时消费循环仅对**当前一个** future 调 `future.cancel()` 随即 `break`（72-79 行）→
`with ThreadPoolExecutor(...)` 退出时执行 `shutdown(wait=True)`，
**把剩余全部已提交任务跑完**；因消费循环已 break，这些结果不落库（数据无害）。

报告 §3.4 表述为「协作式：**当前检测批完成后**返回」——代码中**不存在批次边界**，
该归因不成立；`LIMIT-002` 描述的是「任务/批边界粒度」，也**不覆盖**
「整条已提交队列排空」这一行为类别。用户可见后果：点「取消」后界面任务互斥入口
继续占用约 1 分钟，且规模越大越久（万级 → 十分钟量级）。

处置建议（二选一，须 Owner 签字）：
(a) 认定为可接受限制 → 登记 KNOWN_ISSUES（含「队列排空 + 结果丢弃」准确描述）；
(b) 小改动根治 → 取消时 `pool.shutdown(cancel_futures=True)` 或改为受背压的惰性提交。

### F-05 【P2·MINOR】`match_threshold` 无校准证据

`0.40` 为 `DEFAULT_MATCH_THRESHOLD`（`application/dtos/settings.py:12`），
在两个 Stage F 工具中**硬编码**（`validate_stage_f.py:156`、
`stress_lifecycle_stage_f.py:128`）而非读取配置；真实运行 `sample_matched = 0`
⇒ 1:N 样本匹配路径在真实数据上**从未产生过一次正命中**，其阈值实质未被测量。

### F-06 【P2·MINOR】用户文档未跟进 C–F（违反执行计划 §0.6）

`docs/user-guide/manual.md` 仍停留在 Stage B 形态：五步流程无「聚类/分组工作台」，
「运行人脸识别」节无「重新分析入口 / 失败清单导出」，无「历史人员回填」，
归档节未说明「一张照片可归属多人 → 多条归档计划」的 `(person, photo)` 语义。

### F-07 【P2·MINOR】`DOCUMENT_INDEX.md` §2.4 未登记本轮产物

`people-import-*.md`、`stage-f-calibration-report.md`、`docs/development/evidence/*`
均不在索引内（该表登记止于 phase5），冻结后新会话无法从索引发现这些证据。

### F-08 【OBS】压测证据为一次性脚本产物，不受回归保护

`stage-f-lifecycle-stress.json` 依赖真模型 + 临时目录，无法进 CI；
确定性替身 `test_stage_f_lifecycle.py` 用 InMemory + fake detector 断言「能完成」，
性能数字不受守卫。属可接受取舍，但须在报告中如实标注（当前报告未标注）。

### F-09 【OBS】回填脚本在部分失败时会产生多个历史批次

`BackfillHistoricalPeopleService` 每次执行新建一个 `source_type=backfill` 批次；
若首轮存在 per-person 失败使部分人员仍无来源，重跑会再建一批。不影响正确性
（幂等仅指「已关联者跳过」），但「单一历史批次」不变式并非全局成立。

## 4. 冻结收口条件

**P0（修完才可宣布 Stage F 冻结）**

1. **F-01**：`KNOWN_ISSUES.md` 补登 4 项（失败分类语义、E-SG-4、44 簇复核、取消排空），并升版本号 / Last Updated。
2. **F-02**：`ARCHITECTURE_DECISIONS.md` 补录 D3、Stage D 合并门 inclusive、E-SG-6 `(person, photo)` 三条 Accepted ADR；`PROJECT_STATUS.md` 同步至 Stage F 终态。
3. **F-03**：新增 1 条 SQLite + 临时目录的贯通回归（导入草稿→确认→识别→聚类→配对确认→`ArchivePlanner`→`ArchiveExecutor` 落盘断言），或由 Owner 书面豁免并挂 KNOWN_ISSUES。

**P1（冻结前需 Owner 签字，可不改码）**

4. **F-04**：取消排空按 (a) 登记限制 或 (b) 根治；同时更正校准报告 §3.4 的归因文字。

**P2（冻结后首个文档轮内闭合）**

5. **F-05/F-06/F-07**：补 `match_threshold` 证据（或明确待真实名单验证）、`manual.md` 增补 C–F 用户可见行为、`DOCUMENT_INDEX` 登记本轮产物。

## 5. 评审方法与可复核锚点

- 契约稳定：`git diff --stat f6e70b0 b3b8685 -- src/photo_archiver/domain src/photo_archiver/infrastructure` → 3 files, +39/−0（person 仓储新增 3 方法）。
- SSOT 缺失：`git grep -n -I 'E-SG' -- .ai/` → 0 命中。
- ADR 止于 041：`ARCHITECTURE_DECISIONS.md:429`；冲突裁决表末条为 R-8（2026-07-24）。
- 取消机制：`run_recognition_service.py:68-79`（全量 submit / 单次 `future.cancel()` / `with` 退出等待）。
- 压测计时：`stress_lifecycle_stage_f.py:199-203`；数值自洽校验：663 ÷ 63.33s = 10.4 张/s，60s × 10.4 ≈ 624 张。
- 端到端断点：`test_stage_e_remediation.py:381-395`（Fake repo + 止于 plan）对照 `test_step11_archive_e2e.py:114`（legacy 审核路径）。
- `(person, photo)` 符合性：`pairing_workbench_service.py:303-319` + `test_stage_e_remediation.py:364-431`。
- 生产库现状：alembic `003`、473 照片——与 `stage-f-upgrade-real.json` 前置态一致（只读核验，未写入）。
