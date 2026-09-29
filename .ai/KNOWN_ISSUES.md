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

> 来源：全面工程健康体检（Stage 0–9，READ-ONLY，判 ATTENTION；完整台账与证据见 `docs/health-check/FINDINGS_LEDGER.md`）。以下为**保持 OPEN** 的 P2 级发现（P1 AUD-001 与 P2 AUD-003/009/014 已于 Stage 10 整改闭合；P2 AUD-017 已于 Stage 11B 按 owner 裁决 Option C 实现闭环（ADR-047）、P2 AUD-004 已于 Stage 12A 全链贯通回归闭合（含聚类时间排序接缝修复）、P2 AUD-019 已于 Stage 12B worker/配对守卫测试补强闭合、P2 AUD-023 已于 Stage 12C 取消延迟整改闭合、P2 AUD-015 已于 Stage 12D 定性为恢复缺口并以原子复制修复（ADR-048 一致性模型）、P2 AUD-010 已于 Stage 12E 端口化并由 DEP-072 + 守卫测试强制（ADR-049）；P3 级 15 项见台账，不在此重复登记）。

| ID | Severity | Description | Status | Impact | Planned Resolution |
|---|---|---|---|---|---|
| AUD-002 | P2 | main 领先 origin/main 44 提交未推送——HEAD 区间（阶段 C–F）未经远端三平台 CI 验证；CHANGELOG 无对应发行记录（本轮已补 `[Unreleased]` 段，版本切分待 owner） | Open | Medium | owner 推送 + 发版评估（PROJECT_STATUS §6 #3） |

---

## 设计限制与平台限制

> 合并说明（2026-09-28）：原「设计限制与测试覆盖限制」「平台与第三方限制」两表中 LIMIT-006 重复承载，合并为本表（AUD-005 整改，内容未丢失）。

| ID | Description | Status | Impact | 说明 |
|---|---|---|---|---|
| LIMIT-001 | 真实模型包缺失集成测试未纳入 CI | Open | Low | `InsightFaceLoader.load` 缺包 raise `ModelPackMissing` 路径与 UI 失败反馈已有单元/组件测试覆盖（`test_recognition_ports.py`、`test_match_ui_wiring.py`）；但"真实缺模型 → `_UnavailableMatchService` → TaskFailed → UI"完整 E2E 依赖本地缺模型环境，未纳入 CI 自动套件（Principle 3：不把模型设为 CI 前提）。 |
| LIMIT-002 | 识别取消粒度为 batch-level cooperative cancellation | Open | Low | `WorkerTaskCancelled` 由 `WorkerTask.run()` 前后边界触发，`MatchPersonsService` 单张 `except Exception` 不吞取消（有专项测试）。当前批处理中途不可逐张即时取消，属设计特征（Phase 4.2 Final Audit 明确记录），非缺陷。scan 取消同为任务边界粒度（Phase A P0-4 确认，设计同型）。**修正（2026-09-28 体检）**：识别链实际取消语义弱于本条原表述——取消生效需等待已入队 futures 全部执行完毕（`run_recognition_service.py:69-75` submit-all + shutdown 排空，千张 ≈60s，见 AUD-023）；该现象已于 Stage 12C 修复（取消后 pending 批量取消 + 任务入口取消检查，terminal 及时到达）；"任务边界协作式取消"的粒度语义不变，本条维持"设计特征"登记。 |
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
