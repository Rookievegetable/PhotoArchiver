# KNOWN_ISSUES.md — PhotoArchiver 当前未解决问题列表

> **本文档记录项目当前尚未解决的问题。**
>
> 回答：**"目前有哪些问题需要 AI 注意？"**
>
> 动态维护，实时更新。问题解决后**立即删除**，不保留历史记录。
>
> Version: 1.17.0 ｜ Last Updated: 2026-09-28 ｜ Status: Live

---

## ⚠️ 本文档不是什么

| 不是 | 这些应在别处找 |
|---|---|
| 已解决的问题 | 不保留（解决后立即删除） |
| 已裁决的架构决策 / ADR | `ARCHITECTURE_DECISIONS.md` |
| 当前任务 / Step / Roadmap | `PROJECT_STATUS.md` |
| AI 阅读顺序 / 工作流程 | `AI_ONBOARDING.md` |
| 体检发现的完整台账 | `docs/health-check/FINDINGS_LEDGER.md`（工作树产物，AUD-XXX 编号体系） |

---

## Issue 格式约定

每个 Issue 至少包含：

| 字段 | 说明 |
|---|---|
| ID | `ISSUE-XXX`，单调递增；问题解决后整条删除（ID 不复用）。全面工程体检（2026-09-28）产出的发现沿用其台账编号 `AUD-XXX` |
| Description | 问题简述 |
| Status | Open / Mitigated（已有 workaround）/ Resolving（已在某 Step 推进） |
| Impact | 影响范围与严重度（High/Medium/Low） |
| Temporary Workaround | 当前临时规避方式（若有） |
| Planned Resolution | 计划何时/何 Step 解决 |

---

## 未决问题

_无 ISSUE-XXX 系未决条目。设计 / 平台 / 测试覆盖限制见下方限制表；全面体检产出的 OPEN 发现见下节登记。_

## 全面体检登记（2026-09-28，Stage 10 治理恢复时同步）

> 来源：全面工程健康体检（Stage 0–9，READ-ONLY，判 ATTENTION；完整台账与证据见 `docs/health-check/FINDINGS_LEDGER.md`）。以下为**保持 OPEN** 的 P2 级发现（P1 AUD-001 与 P2 AUD-003/009/014 已于 Stage 10 整改闭合；P3 级 15 项见台账，不在此重复登记）。

| ID | Severity | Description | Status | Impact | Planned Resolution |
|---|---|---|---|---|---|
| AUD-002 | P2 | main 领先 origin/main 44 提交未推送——HEAD 区间（阶段 C–F）未经远端三平台 CI 验证；CHANGELOG 无对应发行记录（本轮已补 `[Unreleased]` 段，版本切分待 owner） | Open | Medium | owner 推送 + 发版评估（PROJECT_STATUS §6 #3） |
| AUD-004 | P2 | Stage-F 审查 F1-1 残余：两段式导入→配对确认→归档执行**无单条全链贯通回归**（各段分别有测试；`tools/validate_stage_f.py` 直造名单且止于 plan()）。BLK-1/5、D-1/D-2、F1-4 已核验闭合 | Open | Medium | 补一条全链集成测试（owner 立项） |
| AUD-015 | P2 | 归档批 FS/DB 部分失败不一致：整批单 UoW 事务包裹 DB 写而文件复制不可事务化；批中途异常逃逸/断电 → 已复制文件无 DB 记录，重跑产生 `.archived-N` 副本或误标 SKIPPED；无崩溃对账路径（逐项 OSError 有隔离） | Open | Medium | owner 定性：补对账工具 or 文档声明为已知取舍 |
| AUD-017 | P2 | `person_embeddings` 全 git 历史零生产写入者，两条识别链匹配候选读它 → 候选恒空、识别期自动匹配空转；开发计划 :155 承诺的样本化匹配未落地；测试以 stub 掩蔽 | Open（Decision Required） | Medium | **owner 三选一裁决**（A 激活旧表 / B 登记受限 / C 样本直读）：`docs/decisions/AUD-017-person-embeddings-decision.md` |
| AUD-019 | P2 | workers 任务包装器错误/回滚分支覆盖 74.1%（>500 行导入确认走 Worker，其失败分支 UI 终态行为未经行为验证）；配对服务并发删除守卫与分数钳制 14 行未测 | Open | Medium | 补定向测试（owner 立项） |
| AUD-023 | P2 | 识别取消延迟 = 剩余队列全排空：`run_recognition_service` 一次性 submit 全部 futures，取消只 break 消费循环，`with ThreadPoolExecutor` 退出 `shutdown(wait=True)` 无 cancel_futures → 已入队任务照常执行（千张 ≈60s，即 Stage F 审查 F-04"取消延迟 60.0s"真根因）；状态一致性无损 | Open | Medium | 修复方向：批量 future.cancel + `shutdown(cancel_futures=True)` 或任务体感知取消（owner 立项） |

---

## 设计限制与平台限制

> 合并说明（2026-09-28）：原「设计限制与测试覆盖限制」「平台与第三方限制」两表中 LIMIT-006 重复承载，合并为本表（AUD-005 整改，内容未丢失）。

| ID | Description | Status | Impact | 说明 |
|---|---|---|---|---|
| LIMIT-001 | 真实模型包缺失集成测试未纳入 CI | Open | Low | `InsightFaceLoader.load` 缺包 raise `ModelPackMissing` 路径与 UI 失败反馈已有单元/组件测试覆盖（`test_recognition_ports.py`、`test_match_ui_wiring.py`）；但"真实缺模型 → `_UnavailableMatchService` → TaskFailed → UI"完整 E2E 依赖本地缺模型环境，未纳入 CI 自动套件（Principle 3：不把模型设为 CI 前提）。 |
| LIMIT-002 | 识别取消粒度为 batch-level cooperative cancellation | Open | Low | `WorkerTaskCancelled` 由 `WorkerTask.run()` 前后边界触发，`MatchPersonsService` 单张 `except Exception` 不吞取消（有专项测试）。当前批处理中途不可逐张即时取消，属设计特征（Phase 4.2 Final Audit 明确记录），非缺陷。scan 取消同为任务边界粒度（Phase A P0-4 确认，设计同型）。**修正（2026-09-28 体检）**：识别链实际取消语义弱于本条原表述——取消生效需等待已入队 futures 全部执行完毕（`run_recognition_service.py:69-75` submit-all + shutdown 排空，千张 ≈60s，见 AUD-023）；该现象定性/修复随 AUD-023 处置，本条维持"设计特征"登记。 |
| LIMIT-004 | Qt 原生级崩溃（exit 127，无 Python traceback）：特定子集顺序（`test_archive_controller` + `test_export_controller*` 后紧接首个构造 MainWindow 的测试）触发；全量收集顺序不受影响 | Open | Low | 先于 Phase 9 存在（Phase 9 报告 §9.2 登记，干净基线 `git stash` 可复现）；仅影响子集顺序本地调试，CI 全量绿；后续轮候审，不阻塞 Phase A。 |
| LIMIT-006 | GitHub macOS/Linux runner 环境漂移致 pytest 工作线程概率性 SIGSEGV（exit 139；崩溃点每次漂移——已观测 scandir / realpath / sqlite3 / PIL / uuid4 五处） | Mitigated（CI 自愈 + darwin skip 长期维持） | Low | 五轮仓内实验已排除枚举 API（glob/scandir/listdir 三种实现）、PySide6 版本（6.8.3/6.11.1）、线程类型（QThreadPool/Python threading）、栈大小（512KB/64MB）——与仓库代码无关（docs-only 提交亦崩），故障在 Python 帧之下原生层，本仓库不可修复。CI pytest 步骤对 exit 139 自动重试 ≤3 次（真实断言失败 exit 1 不重试）；4 处 darwin skip 长期维持（reason 带 `PA_ALLOW_LIMIT_006` 豁免机制），实验入口 `tests/integration/test_scan_stress_no_qtbot.py`（PA_STRESS 门控）。**owner 处置（2026-09-13）：维持现状**——macOS 定性为实验性支持（user-guide/FAQ 已如实披露）；上游 issue 草稿备提交：`docs/development/limit006-upstream-issue-draft.md`。教训：曾两次过早宣布定论（6 连续通过判据、512KB 栈根因）均被下一轮证伪——除已排除变量外不再仓内猜测，不再因单轮绿宣布根治。 |

> 历史注记：ISSUE-018（打包安装态不可运行）已于 2026-08-26 经 ADR-031 裁决按 by-design 终结——安装态不在受支持运行形态内，详见 `docs/development/phase5-adr-draft.md`。

## 维护规则

- **问题解决后必须同提交整条删除**，不保留历史（历史在 Git 与审计报告中）。
- 新发现问题实时追加，ID 单调递增，不复用已删除 ID。
- 状态从 `Open` → `Mitigated`（有 workaround）→ `Resolving`（已在某 Step 推进）→ 删除。

---

> 📝 本文件由 AtomCode (GLM-5.2) 于 2026-07-18 基于真实项目状态生成。实时维护，始终保持"当前未解决问题"。

End of KNOWN_ISSUES.md
