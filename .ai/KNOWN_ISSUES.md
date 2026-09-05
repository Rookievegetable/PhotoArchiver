# KNOWN_ISSUES.md — PhotoArchiver 当前未解决问题列表

> **本文档记录项目当前尚未解决的问题。**
>
> 回答：**"目前有哪些问题需要 AI 注意？"**
>
> 动态维护，实时更新。问题解决后**立即删除**，不保留历史记录。
>
> Version: 1.10.0 ｜ Last Updated: 2026-09-05 ｜ Status: Live

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
| ISSUE-019 | **疑似缺陷（高置信，待真实相机照片终验）**：`PillowPhotoMetadataReader._extract_captured_at` 仅读 `image.getexif().get(36868)`（IFD0 顶层），而 EXIF 标准将 DateTimeOriginal(36867)/DateTimeDigitized(36868) 置于 Exif 子 IFD（0x8769）——标准结构相机照片无法命中，`captured_at` 走 mtime 兜底，归档"按拍摄日期"分桶对真实相机照片实际按文件修改时间执行。证据（2026-09-04 受控实验）：合成 JPEG 将 36867/36868 写入 0x8769（PIL `get_ifd` 回读确认存在）→ reader captured_at = mtime；同图将 36868 置于 IFD0 顶层 → reader 精确命中 EXIF（2026-01-15）。Phase 2 Step 11 既有实现，**非 v2.3.0 回归**；既有测试全绿（fixture 未覆盖标准子 IFD 结构）。 | Open | Medium | 功能不中断（mtime 兜底）；桌面复验素材 `testdata/generate_materials.py` 以 IFD0 放置适配 reader | Owner 决策是否立项：reader 增加子 IFD 读取（36867 优先、36868 兜底）+ 真实相机照片终验 + 等价性回归评估（EXIF 命中后 captured_at 语义变化触归档命名）。不阻塞 v2.3.0 发布。 |

> 注意：以下为**设计性/测试覆盖限制**，非缺陷，登记于表格供审计与 CI 规划参考。

## 设计限制与测试覆盖限制

| ID | Description | Status | Impact | 说明 |
|---|---|---|---|---|
| LIMIT-001 | 真实模型包缺失集成测试未纳入 CI | Open | Low | `InsightFaceLoader.load` 缺包 raise `ModelPackMissing` 路径与 UI 失败反馈已有单元/组件测试覆盖（`test_recognition_ports.py`、`test_match_ui_wiring.py`）；但"真实缺模型 → `_UnavailableMatchService` → TaskFailed → UI"完整 E2E 依赖本地缺模型环境，未纳入 CI 自动套件（Principle 3：不把模型设为 CI 前提）。 |
| LIMIT-002 | 识别取消粒度为 batch-level cooperative cancellation | Open | Low | `WorkerTaskCancelled` 由 `WorkerTask.run()` 前后边界触发，`MatchPersonsService` 单张 `except Exception` 不吞取消（有专项测试）。当前批处理中途不可逐张即时取消，属设计特征（Phase 4.2 Final Audit 明确记录），非缺陷。scan 取消同为任务边界粒度（Phase A P0-4 确认，设计同型）。 |
| LIMIT-004 | Qt 原生级崩溃（exit 127，无 Python traceback）：特定子集顺序（`test_archive_controller` + `test_export_controller*` 后紧接首个构造 MainWindow 的测试）触发；全量收集顺序不受影响 | Open | Low | 先于 Phase 9 存在（Phase 9 报告 §9.2 登记，干净基线 `git stash` 可复现）；仅影响子集顺序本地调试，CI 全量绿；后续轮候审，不阻塞 Phase A。 |

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
