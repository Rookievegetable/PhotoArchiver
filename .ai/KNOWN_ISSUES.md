# KNOWN_ISSUES.md — PhotoArchiver 当前未解决问题列表

> **本文档记录项目当前尚未解决的问题。**
>
> 回答：**"目前有哪些问题需要 AI 注意？"**
>
> 动态维护，实时更新。问题解决后**立即删除**，不保留历史记录。
>
> Version: 1.14.0 ｜ Last Updated: 2026-09-12 ｜ Status: Live

---

## ⚠️ 本文档不是什么

| 不是 | 这些应在别处找 |
|---|---|
| 已解决的问题 | 不保留（解决后立即删除） |
| 已裁决的架构决策 / ADR | `ARCHITECTURE_DECISIONS.md` |
| 当前任务 / Step / Roadmap | `PROJECT_STATUS.md` |
| AI 阅读顺序 / 工作流程 | `AI_ONBOARDING.md` |

---

## Issue 格式约定

每个 Issue 至少包含：

| 字段 | 说明 |
|---|---|
| ID | `ISSUE-XXX`，单调递增；问题解决后整条删除（ID 不复用） |
| Description | 问题简述 |
| Status | Open / Mitigated（已有 workaround）/ Resolving（已在某 Step 推进） |
| Impact | 影响范围与严重度（High/Medium/Low） |
| Temporary Workaround | 当前临时规避方式（若有） |
| Planned Resolution | 计划何时/何 Step 解决 |

---

## 未决问题

| ID | Description | Status | Impact | Temporary Workaround | Planned Resolution |
|---|---|---|---|---|---|

_当前无未决问题条目（2026-09-12）：ISSUE-019（EXIF 子 IFD 拍摄时刻）2026-09-06 修复终验关闭。以下条目曾来自 2026-09-10 全项目体检（`docs/health-check/PROJECT_HEALTH_CHECK_2026-09-10.md` §15.2）经 owner 决策登记（2026-09-12）；ISSUE-020/021 已于 2026-09-12 分别经 ADR-038（插件目录生产接线）与 ADR-037（并行匹配分片 flush）修复关闭；ISSUE-022 实证不复现（name+department 去重仅对无 identity 行生效，D-B2 保守语义，已加测试锁定）删除；ISSUE-023 经 `cleanup-thumbnails` CLI + 缓存端口 cleanup 修复关闭；ISSUE-024 经真实模型包（v0.7 release，360662982 字节，zip 校验后）计算摘要补钉关闭；体检其余发现（F-10/F-11/F-13/N-2/N-3/N-4/N-6/N-9）已立项 Phase F 正确性收口（`docs/development/phase-f-correctness-plan.md`，ADR-036），随修复同提交删除、不再预登记。_

| ID | Description | Status | Impact | Temporary Workaround | Planned Resolution |
|---|---|---|---|---|---|

> 注意：以下为**设计性/测试覆盖限制**，非缺陷，登记于表格供审计与 CI 规划参考。

## 设计限制与测试覆盖限制

| ID | Description | Status | Impact | 说明 |
|---|---|---|---|---|
| LIMIT-001 | 真实模型包缺失集成测试未纳入 CI | Open | Low | `InsightFaceLoader.load` 缺包 raise `ModelPackMissing` 路径与 UI 失败反馈已有单元/组件测试覆盖（`test_recognition_ports.py`、`test_match_ui_wiring.py`）；但"真实缺模型 → `_UnavailableMatchService` → TaskFailed → UI"完整 E2E 依赖本地缺模型环境，未纳入 CI 自动套件（Principle 3：不把模型设为 CI 前提）。 |
| LIMIT-002 | 识别取消粒度为 batch-level cooperative cancellation | Open | Low | `WorkerTaskCancelled` 由 `WorkerTask.run()` 前后边界触发，`MatchPersonsService` 单张 `except Exception` 不吞取消（有专项测试）。当前批处理中途不可逐张即时取消，属设计特征（Phase 4.2 Final Audit 明确记录），非缺陷。scan 取消同为任务边界粒度（Phase A P0-4 确认，设计同型）。 |
| LIMIT-004 | Qt 原生级崩溃（exit 127，无 Python traceback）：特定子集顺序（`test_archive_controller` + `test_export_controller*` 后紧接首个构造 MainWindow 的测试）触发；全量收集顺序不受影响 | Open | Low | 先于 Phase 9 存在（Phase 9 报告 §9.2 登记，干净基线 `git stash` 可复现）；仅影响子集顺序本地调试，CI 全量绿；后续轮候审，不阻塞 Phase A。 |
| LIMIT-006 | macOS CI runner 原生段错误（SIGSEGV）：真实执行器扫描用例在 macOS 上于 `local_photo_file_scanner.scan` 的 pathlib 原生调用处段错误，主线程同刻停于 `qtbot.waitUntil`。已观测两次形态：① `test_scan_single_flight.py::test_real_executor_refuses_second_scan_mid_flight_and_recovers`（2000 文件压力扫描，worker 于 `pathlib.glob/_select_from`）；② `tests/integration/test_scan_cancel_consistency.py::test_rescan_grows_superset_idempotently`（N3 重扫幂等，500 文件首扫，worker 于 `pathlib.is_file/stat`，faulthandler 无 Python 异常；PySide6 6.11.1 / py3.11.9 arm64，E-5 树首次观测——崩溃在 scanner.scan 的系统调用层，早于 E-5 变更检测路径且首扫行为 E-5 前后一致，产品代码无因果）。两形态同族：真实 QThreadPool 扫描 worker + 大目录 pathlib 遍历 + 主线程 qtbot 等待的交互，时序/环境敏感非确定性（LIMIT-006 历史同日绿红交替；②同 run 同文件另一 2000 文件用例 PASSED）。CI run #32–#36（head `f689c01`→`982a3ce`，UI 缺陷修复链起）macOS 四连，同日 run #30/#31 同用例仍绿；Windows/Linux 全量绿。处置：真实执行器压力用例 darwin 范围 skipif（win/linux 照跑）——`test_scan_single_flight` / `test_scan_cancellation` 各 1 用例 + N3 `test_scan_cancel_consistency` 2 用例（预防性同范围）。开放问题：是否为 macOS runner 镜像/Qt 6.11 环境漂移与真实线程池+大目录遍历的交互，待后续轮有 macOS 调试手段时追查。**D-2 实证（2026-09-12，CI run #62/#63）**：A-2/A-3 候选部分解除——ADR-036 D5 已将扫描器从 pathlib glob 换为迭代式 os.scandir + 环检测， darwin skip 临时移除后 macOS CI Pytest 步骤仍原生段错误（exit 139 SIGSEGV），ubuntu/windows 全绿——**崩溃面不是 pathlib glob**，嫌疑收敛到"真实 QThreadPool 扫描 worker + 大目录压力 + qtbot.waitUntil"交互本身；本轮 .ips 收集为空（artifact 0），需 macOS 调试手段立项（D-3）。实验提交 05186ba/ea45c9d 已回退（b3b0d39）。**D-3 实验一（2026-09-12，CI run #73 stress-macos job）**：非 qtbot 形态（真实 QThreadPool + 2000 文件真实扫描 + 主线程 sleep 轮询，`tests/integration/test_scan_stress_no_qtbot.py`，PA_STRESS 门控）在 macOS runner **稳定通过**——QThreadPool × 大目录扫描不是充分条件，**嫌疑收敛到 qtbot.waitUntil 主线程等待交互**；PYTHONFAULTHANDLER 已三平台常开（下次崩溃可从 stderr 取 C 层栈）。 | Open | Low | 四个真实执行器压力用例在 macOS CI 跳过（其余平台照跑）；产品扫描代码路径未观测到等价崩溃形态（崩溃语境为测试专属的背靠背大压力扫描+teardown 并发）；后续轮候审。 |

> 历史注记：ISSUE-018（打包安装态不可运行）已于 2026-08-26 经 ADR-031 裁决按 by-design 终结——安装态不在受支持运行形态内，详见 `docs/development/phase5-adr-draft.md`。


## 平台与第三方限制

_当前无未决平台与第三方限制条目。_

## 维护规则

- **问题解决后必须同提交整条删除**，不保留历史（历史在 Git 与审计报告中）。
- 新发现问题实时追加，ID 单调递增，不复用已删除 ID。
- 状态从 `Open` → `Mitigated`（有 workaround）→ `Resolving`（已在某 Step 推进）→ 删除。

---

> 📝 本文件由 AtomCode (GLM-5.2) 于 2026-07-18 基于真实项目状态生成。实时维护，始终保持"当前未解决问题"。

End of KNOWN_ISSUES.md
