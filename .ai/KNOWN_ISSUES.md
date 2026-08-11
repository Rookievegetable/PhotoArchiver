# KNOWN_ISSUES.md — PhotoArchiver 当前未解决问题列表

> **本文档记录项目当前尚未解决的问题。**
>
> 回答：**"目前有哪些问题需要 AI 注意？"**
>
> 动态维护，实时更新。问题解决后**立即删除**，不保留历史记录。
>
> Version: 1.4.0 ｜ Last Updated: 2026-08-11 ｜ Status: Live

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

### ISSUE-016 — ExportController（Presentation）直接导入 Infrastructure 导出器（DEP-002 越界）

| 字段 | 值 |
|---|---|
| ID | ISSUE-016 |
| Description | `presentation/controllers/export_controller.py` 模块级导入 `photo_archiver.infrastructure.exporters` 并在类属性 `_EXPORTERS` 中实例化 `CsvExporter / ExcelExporter / HtmlExporter`，违反 DEP-002（Presentation MUST NOT import infrastructure）与 ARC-001。由 B4 提交 `cafff2b` 引入（Step 14 基线 `086acaa` 为构造器注入单一 exporter，无 infrastructure 导入；B4 为支持 format_name 查找新增了该映射）。 |
| Status | Open |
| Impact | Medium——架构边界越界，B4 HTML 导出功能路径可达；不破坏功能或数据，但打破分层契约、Presentation 直接依赖具体实现、模块加载期实例化 exporter 增加耦合与测试难度 |
| Temporary Workaround | 无（功能可用，仅架构违规；ExportDialog HTML 选项依赖该映射） |
| Planned Resolution | 阶段 1 PluginContext 边界加固：format→Exporter 注册表迁至 app 装配层（`ui_assembly` / bootstrap 注入）或 Application 侧 `ExporterRegistry`，Presentation 仅依赖 `Exporter` Protocol + `format_name` 字符串；属公开 API 变更，按 `AI_ONBOARDING.md` §6 确认后实施 |

---

## 平台与第三方限制

_当前无未决平台与第三方限制条目。_

## 维护规则

- **问题解决后必须同提交整条删除**，不保留历史（历史在 Git 与审计报告中）。
- 新发现问题实时追加，ID 单调递增，不复用已删除 ID。
- 状态从 `Open` → `Mitigated`（有 workaround）→ `Resolving`（已在某 Step 推进）→ 删除。

---

> 📝 本文件由 AtomCode (GLM-5.2) 于 2026-07-18 基于真实项目状态生成。实时维护，始终保持"当前未解决问题"。

End of KNOWN_ISSUES.md
