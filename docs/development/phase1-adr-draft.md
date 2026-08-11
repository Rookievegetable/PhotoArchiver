# ADR-026 草案 — 阶段 1 PluginContext 公共边界加固（前置门产出）

> **文档性质**：ADR 草案（Proposed 状态），阶段 1 开工前置门产出。
>
> 按 `AI_ONBOARDING.md §6` 与 B5-a 前置门先例：公开 API 破坏性变更须先出草案评审拍板，拍板后才进实施。拍板后本草案定稿内容写入 `.ai/ARCHITECTURE_DECISIONS.md` ADR-026 Accepted 条目，本文件保留作设计依据（与 `plugin-context-design.md` 同命运）。
>
> **产出时间**：2026-08-11 ｜ **产出者**：AtomCode (GLM-5.2) ｜ **状态**：Proposed（待评审拍板）

---

## 0. 裁决点拍板汇总（已拍板 2026-08-11）

| 裁决点 | 选项 | 拍板结果 |
|---|---|---|
| 1 — ADR 编号与形式 | A | ADR-026 草案落 `docs/development/phase1-adr-draft.md`（Proposed），拍板后写入正式 ADR Register |
| 2 — Protocol 继承关系（MAJOR-1） | A | `ContextAwarePlugin(Plugin)` 继承——新插件必须同时实现 `set_context + enable + disable + actions + execute_action`，mypy 静态守护完整 |
| 3 — `match_status` "none" 语义（MAJOR-2） | A | `PluginPhotoSummary` 含 none 4 态（未注册审核）；`PluginPhotoQuery` 只 3 态（pending/approved/rejected），不含 none；stats 插件取 none 数量需取全集后客户端过滤 |
| 4 — PluginReport 单元格类型（MAJOR-3） | A | `str | int | float` 混合——宿主渲染层做格式化（数值列右对齐/排序/国际化数量格式），插件给结构化数据 |

**实测证据**（MAJOR-2 裁决依据）：`src/photo_archiver/domain/entities/recognition.py:11` `class MatchStatus(str, Enum)` 字面值 `"pending"/"approved"/"rejected"`，**无 `"none"`**——`RecognitionResult` 不存在即"未参与匹配"，插件层 `"none"` 是新概念表达"无 RecognitionResult"。

---

## 1. 背景

B5 v2 收敛拍板（ADR-025 后、B5-a 前置门）落地了只读 `PluginContext`（`search_photos + detect_duplicates`）+ 可选上下文注入（`enable(context=None)`）+ 宿主渲染 `ActionResult`。但当前 B5 落地存在三项公开 API 债务：

1. **插件间接依赖 Domain**：`PluginContext.search_photos(criteria: PhotoSearchCriteria) -> list[Photo]` 与 `detect_duplicates() -> DuplicateReport`——插件导入 `PhotoSearchCriteria`/`Photo`/`DuplicateReport` 即触 Domain，违反 DEP-060（Plugins → Application only）精神。
2. **`ActionResult.payload: Any`**：宿主 `_render_plugin_action_result` 用 `str(result.payload)` 兜底渲染（`main_window.py:206`），无类型守护。
3. **`enable(context)` 签名混淆**：当前 `Plugin.enable(self, context=None)` 把生命周期与上下文注入耦合在一参，旧无参插件与新上下文插件混入同一签名。

阶段 1 收敛这三项为稳定的插件公共边界。本阶段**不改 Schema、不加依赖、不实现插件写操作**。

---

## 2. 裁决正文

### 2.1 Protocol 继承关系（MAJOR-1 裁决点 2=A）

```python
class Plugin(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def version(self) -> str: ...
    def enable(self) -> None: ...
    def disable(self) -> None: ...
    def actions(self) -> list[PluginAction]: ...
    def execute_action(self, action_id: str) -> ActionResult: ...

class ContextAwarePlugin(Plugin, Protocol):
    def set_context(self, context: PluginContext) -> None: ...
```

`ContextAwarePlugin` 继承 `Plugin`——新标准插件必须同时实现 `set_context + enable + disable + actions + execute_action`，mypy 静态守护完整，误漏任一方法即编译报错。

**Registry 启用顺序**（§5 细化）：

```text
发现插件
  ↓
检查是否 ContextAwarePlugin（hasattr set_context 签名）
  ↓ 是 → 先调 set_context(context) → 再调 enable()
  ↓ 否 → 检查是否旧 enable(context) 兼容签名
         ↓ 是 → 走兼容适配层调 enable(context)
         ↓ 否 → 调 enable()（无参）
  ↓
失败则记录错误、跳过该插件
```

**静默失败防护**（MAJOR-1 风险兜底）：Registry 启用后对每个已启用插件调 `plugin.actions()`，若返回空列表且插件非声明式（无 `actions()` 覆盖即走 Protocol 默认 `return []`），日志 warning 提示"插件启用但无动作，可能误漏 enable 实现"。`ContextAwarePlugin(Plugin)` 继承关系使此风险大幅降低——误漏 `enable` 时 mypy 即报错，防护属二道兜底。

### 2.2 `match_status` "none" 语义（MAJOR-2 裁决点 3=A）

**Domain 实测**：`MatchStatus(str, Enum)` 三态 `PENDING="pending" / APPROVED="approved" / REJECTED="rejected"`，无 `"none"`。`RecognitionResult` 不存在即"未参与匹配"。

**Plugin DTO**（§3 细化）：

```python
@dataclass(frozen=True, slots=True)
class PluginPhotoQuery:
    person_id: UUID | None = None
    match_status: Literal["pending", "approved", "rejected"] | None = None  # 3 态，不含 none
    captured_from: date | None = None
    captured_to: date | None = None

@dataclass(frozen=True, slots=True)
class PluginPhotoSummary:
    photo_id: UUID
    captured_at: datetime | None  # None = 未捕获拍摄日期（MINOR-7 语义）
    registered_at: datetime
    match_status: Literal["pending", "approved", "rejected", "none"]  # 4 态含 none
```

**映射规则**：

- `PluginPhotoQuery.match_status` (3 态) → `PhotoSearchCriteria.match_status` (Domain `MatchStatus`)：直映射，`None` 保留不过滤。
- `Photo` (Domain) → `PluginPhotoSummary` (4 态)：`RecognitionResult` 不存在 → `"none"`；存在则取 `MatchStatus.value` 字面值。
- stats 插件取 `"none"` 数量：`search_photos(query)` 不支持 none 查询，需取全集后客户端过滤 `match_status == "none"`——与 Domain 三态一致，none 是插件层聚合概念。

### 2.3 PluginReport 单元格类型（MAJOR-3 裁决点 4=A）

```python
@dataclass(frozen=True, slots=True)
class PluginReport:
    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str | int | float, ...], ...]

@dataclass(frozen=True, slots=True)
class ActionResult:
    status: Literal["success", "failure", "noop"]
    message: str = ""
    report: PluginReport | None = None
```

**职责分工**：插件给结构化数据（`str | int | float` 混合单元格），宿主渲染层做格式化（数值列右对齐/排序/国际化数量格式）。`str()` 兜底渲染废止。

**三态规则**（§4 细化）：

- `success(message, report=None)`——可带 `PluginReport`，无 report 时宿主信息提示。
- `failure(message)`——只带面向用户信息，不带任意对象。
- `noop()`——不带内容。
- 禁止 `Any`、dict 约定、`str(payload)` 兜底。

### 2.4 兼容路径（§1 计划"保留一个版本"）

`enable(context)` 旧签名作为兼容路径保留一个版本，`plugin-guide.md` 标为 Deprecated。兼容路径移除轮次留 v2.0.0 单独裁决（MINOR-1 处置）。

---

## 3. 影响范围

| 模块 | 变更类型 | 文件 |
|---|---|---|
| Application DTO | 新增 | `application/dtos/plugin_context.py`（Plugin DTO）、`application/dtos/plugin_action_result.py`（改造 ActionResult + 新增 PluginReport） |
| Application Port | 改造 | `application/ports/plugin_context.py`（协议签名改 Plugin DTO）、`application/ports/plugin.py`（Plugin.enable 无参 + 新增 ContextAwarePlugin） |
| Application Service | 新增 | `application/services/plugin_context_service.py`（DTO ↔ Domain 映射） |
| App 装配 | 改造 | `app/bootstrap.py`（移除 `_ReadOnlyPluginContext`，注入 `PluginContextService`） |
| Plugins Loader | 改造 | `plugins/loader.py`（Registry 三类生命周期兼容 + 静默失败防护） |
| Presentation | 改造 | `presentation/views/main_window.py`（`_render_plugin_action_result` 改 PluginReport 渲染 + 新增通用报告对话框） |
| Examples | 新增/改造 | `examples/plugins/stats_report_plugin.py`（新增）、`examples/plugins/hello_plugin.py`（改造演示新标准） |
| Tests | 新增/扩展 | 7 个测试文件（§7） |
| Docs | 改造 | `docs/development/plugin-guide.md`、`docs/development/plugin-context-design.md`、`.ai/PROJECT_STATUS.md` |

**不变**：Domain Schema、依赖（`requirements/`）、`pyproject.toml`、`.github/workflows/`、`.ai/rules/`、ExportController（ISSUE-016 独立修复，见 §5）。

---

## 4. 与既有裁决的关系

| 裁决/规则 | 关系 |
|---|---|
| B5-a 前置门（`plugin-context-design.md`） | 本草案是 B5-a 之后第二次公开 API 变更的前置门，流程同先例 |
| DEP-060~062/070~071（Plugins → Application only） | §3 PluginContext 协议不再导入 Domain，Plugins 不再触 Domain 类型——加固 DEP-060 |
| ARC-001/006/007（Presentation/Application/Plugins 职责） | §4 宿主渲染 PluginReport 属 Presentation 职责，插件不触 UI——符合 ARC-007 |
| ISSUE-016（`KNOWN_ISSUES.md`） | ExportController DEP-002 越界修复与本草案同阶段但**独立提交**（§5） |
| git-rules §18（大重构拆分） | §6 提交边界遵循"先结构后实现"主题拆分 |

---

## 5. ISSUE-016 独立修复与提交边界

**ExportController DEP-002 越界**（`presentation/controllers/export_controller.py:14-17` 直接导入 `infrastructure.exporters`）与本草案同阶段但**独立工作**——不同 type、不同文件、不同裁决动机。

**提交边界**（git-rules §8 GIT-010 避免混合 refactor 与 fix）：

```text
阶段 1a PluginContext 公共边界加固（本草案管辖）——拆多提交：
  refactor: introduce typed plugin context dto boundary
  feat: add structured plugin action reports
  fix: preserve plugin lifecycle compatibility
  feat: add plugin statistics example
  docs: document plugin context compatibility
  （顺序遵循 MAJOR-4 Protocol-first：先 Protocol 签名 → DTO → Service → Registry → MainWindow → 示例 → 测试 → 文档）

阶段 1b ExportController DEP-002 修复（ISSUE-016 管辖）——独立提交：
  fix: decouple export controller from infrastructure
  （format→Exporter 注册表迁 app 装配层或 Application 侧 ExporterRegistry，
   Presentation 仅依赖 Exporter Protocol + format_name 字符串；
   属公开 API 变更需本草案拍板后单独确认实施）
```

**ISSUE-016 删条**：修复提交（`fix: decouple export controller from infrastructure`）**同提交删除 `KNOWN_ISSUES.md` ISSUE-016 整条**（维护规则"解决后必须同提交整条删除"）。

---

## 6. PluginRegistry 兼容层细节（§5 计划细化）

**三类生命周期兼容**（MAJOR-1 静默失败防护 + MINOR-3 签名识别方案）：

```python
# 签名识别——用 inspect.signature 而非捕获 TypeError 重试
import inspect

def _enable_plugin(self, plugin: Plugin, context: PluginContext | None) -> None:
    if isinstance(plugin, ContextAwarePlugin) or hasattr(plugin, "set_context"):
        # 新标准：set_context(context) → enable()
        plugin.set_context(context)  # type: ignore[attr-defined]
        plugin.enable()
        return

    sig = inspect.signature(plugin.enable)
    params = sig.parameters
    # 兜底：旧 enable(context) 兼容签名（context 是位置参）
    if "context" in params:
        try:
            plugin.enable(context)  # type: ignore[call-arg]
        except TypeError as exc:
            # 区分：签名识别已通过，此处 TypeError 是插件内部真实异常
            logger.exception("Plugin enable() raised internally: {}", exc)
            raise
        return

    # 旧无参：enable()
    plugin.enable()
```

**关键**：`inspect.signature` 在调用前判断签名，不靠"捕获 TypeError 后重试"——插件内部真实 `TypeError` 不会被误判为兼容问题。

**测试必须覆盖**（§7 列表 + 静默失败防护）：

- 旧无参插件 `enable()` 成功启用。
- 当前 B5 的 `enable(context)` 插件成功启用（兼容路径）。
- 新 `ContextAwarePlugin` 成功接收 Context（`set_context → enable`）。
- `set_context()` 抛异常时该插件不启用且宿主续运行。
- `enable()` 抛异常时错误隔离保持有效（`_errors` 记录 + skip）。
- `context=None` 测试环境保持可用。
- **静默失败防护**：误漏 `enable` 实现（走 Protocol 默认 noop）后 `actions()` 返回空且非声明式 → 日志 warning。

---

## 7. 测试计划（§7 计划 + 新旧标注）

| 测试文件 | 类型 | 验收点 |
|---|---|---|
| `tests/unit/application/test_plugin_context_service.py` | **新建** | Domain → Plugin DTO 映射正确、3 态查询 → MatchStatus、4 态摘要含 none、RecognitionResult 不存在 → "none" |
| `tests/unit/application/test_plugin_dtos.py` | **新建** | DTO 不可变（frozen + slots）、日期范围校验、match_status Literal 值域、PluginReport 单元格类型边界（str\|int\|float） |
| `tests/unit/application/test_plugin_action_result.py` | **新建** | 三态（success/failure/noop）+ Report 类型正确、failure 不带任意对象、success 可带 Report |
| `tests/unit/plugins/test_loader.py` | **扩展**（现存） | 三类签名兼容、静默失败防护、set_context 异常隔离 |
| `tests/unit/plugins/test_plugin_context.py` | **扩展**（现存） | Context 最小权限不暴露路径/Repository/UoW/Worker/ApplicationContext |
| `tests/unit/plugins/test_plugin_lifecycle_compatibility.py` | **新建** | 三种插件签名兼容矩阵、ContextAwarePlugin 继承关系、误漏 enable 静默告警 |
| `tests/unit/presentation/test_plugin_report_dialog.py` | **新建** | Report 正确显示标题/列/行、数值列右对齐、str 列左对齐 |
| `tests/integration/test_plugin_stats_report_e2e.py` | **新建** | 工具栏动作 → 插件 → Context → Result → 宿主报告对话框全链 |
| 静态依赖检查 | **新建**（pytest 测试或独立脚本） | `examples/plugins/` 不导入 domain/infrastructure/presentation/workers/ai |

**回归守护**：HelloPlugin、坏插件加载隔离不退化（现有 `test_loader.py` 测试不得删）。

---

## 8. 文档同步

| 文件 | 改动 |
|---|---|
| `docs/development/plugin-guide.md` | v3 API 同步：`set_context(context)` + `enable()` 无参 + `ContextAwarePlugin` 协议 + `PluginReport` 渲染契约 + 旧 `enable(context)` Deprecated 标注（兼容路径保留版本，移除轮次留 v2.0.0 单独裁决） |
| `docs/development/plugin-context-design.md` | 头部状态标注刷新：v3 收敛（阶段 1 加固后现状）+ 指针指向本草案 ADR-026 |
| `.ai/PROJECT_STATUS.md` | §1 版本 bump、§3 阶段 1 落地行、§5 本会话快照、§6 Next Step |
| `.ai/DOCUMENT_INDEX.md` | §2.4 登记 `phase1-adr-draft.md`（与 `plugin-context-design.md` 同命运） |
| `.ai/KNOWN_ISSUES.md` | ISSUE-016 修复同提交删条（§5 已述） |
| `.ai/ARCHITECTURE_DECISIONS.md` | 拍板后写入 ADR-026 Accepted 条目（本草案定稿） |

**文档必须明确**：

- PluginContext 是只读、最小能力门面。
- 插件不依赖 Domain 或 Infrastructure。
- 当前不支持插件直接导入、导出、归档、文件选择和后台任务。
- 插件是受信任本地 Python 代码，不是隔离沙箱。
- `enable(context)` 是兼容路径，新插件应使用 `set_context(context)`。

---

## 9. 执行顺序（MAJOR-4 Protocol-first 调整）

**原计划 §9 问题**：先建 DTO（步骤 2）→ Service（步骤 3）→ Protocol（步骤 4），Protocol 未定时 DTO 字段无法与 Protocol 签名对齐验证，Protocol 变更后步骤 2-3 返工。

**调整为 Protocol-first**：

```text
1. 再次核对现有 B5 API 与测试（现状已核对完毕，见本草案证据）
2. 改 PluginContext Protocol 签名（仅占位 ...，引用 Plugin DTO 类型名但 DTO 未建——先向前引用）
3. 改 Plugin Protocol.enable 无参 + 新增 ContextAwarePlugin Protocol（继承 Plugin）
4. 新建 Plugin DTO（PluginPhotoQuery/Summary/DuplicateGroup/DuplicateReport）
5. 改造 ActionResult DTO + 新增 PluginReport（单元格 str | int | float）
6. 落地 PluginContextService（Domain ↔ Plugin DTO 映射）
7. 改造 bootstrap（移除 _ReadOnlyPluginContext，注入 PluginContextService）
8. 实现 Registry 三类生命周期兼容 + 静默失败防护
9. 改造 MainWindow 通用报告渲染 + 新增通用报告对话框
10. 添加 stats_report_plugin + 改造 HelloPlugin
11. 补齐单元、UI、E2E 测试（§7 矩阵）
12. 更新文档与 PROJECT_STATUS（§8）
13. 运行质量门与架构审查
14. 独立提交（阶段 1a 多提交拆分 + 阶段 1b ISSUE-016 独立修复）
```

**与 git-rules §18 对齐**：§18 推荐"结构 → 导入 → 测试 → 文档"阶段拆分，本顺序是"主题拆分"（更适合多文件耦合重构）——偏离理由：Protocol 契约是多文件共同依赖根，先稳定契约再扩散到实现/测试/文档，减少跨步骤返工。偏离已声明。

---

## 10. 完成标准（§10 + 可验收性细化）

- [ ] 插件 API 不再要求 Domain 类型（`application/ports/` 不导入 Domain，实测 grep 守护）。
- [ ] `ActionResult` 不含 `Any`（`payload: Any` 改为 `report: PluginReport | None`）。
- [ ] 宿主可稳定渲染结构化插件报告（通用报告对话框 + 数值列右对齐/排序）。
- [ ] 旧无参、当前 B5、新标准三类插件均可加载（`test_plugin_lifecycle_compatibility.py` 矩阵覆盖）。
- [ ] 插件不获得任何写能力（只读 PluginContext + 不暴露 import/export/archive/worker）。
- [ ] 插件不直接访问 UI、Infrastructure、Worker、Repository、UoW 或 ApplicationContext（`test_plugin_context.py` 守护）。
- [ ] 不新增依赖、不改 Schema（`pyproject.toml` 与 `infrastructure/database/alembic/` 未触）。
- [ ] Ruff、MyPy、pytest 全绿（实测，非文档转述）。
- [ ] 插件指南、设计文档和项目状态已同步（指针可解析性现场验证）。
- [ ] ISSUE-016 修复同提交删条（KNOWN_ISSUES 维护规则）。
- [ ] 静态依赖检查：`examples/plugins/` 不导入 domain/infrastructure/presentation/workers/ai。

---

## 11. 裁决点汇总与拍板记录

| 裁决点 | 选项 | 拍板 | 拍板依据 |
|---|---|---|---|
| 1 ADR 编号与形式 | A | A | 与 B5-a 前置门先例一致（`plugin-context-design.md` 同属 `docs/development/`），不污染正式 ADR Register 未拍板条目 |
| 2 MAJOR-1 Protocol 继承 | A | A | `ContextAwarePlugin(Plugin)` 继承——mypy 静态守护完整，误漏即编译报错；静默失败防护属二道兜底 |
| 3 MAJOR-2 "none" 语义 | A | A | 实测 Domain `MatchStatus` 三态无 none，"none" 是插件层新概念；Query 3 态与 Domain 一致，Summary 4 态聚合 RecognitionResult 不存在情况 |
| 4 MAJOR-3 Report 单元格 | A | A | 宿主管渲染职责正切，插件给结构化数据；数值列右对齐/排序/国际化格式化属渲染层 |

**待裁决（拍板后实施时再决）**：

- MINOR-1 `enable(context)` 兼容路径移除轮次（建议 v2.0.0，留单独裁决）。
- 阶段 1b ISSUE-016 修复方案二选一（迁 app 装配层 vs Application 侧 ExporterRegistry）——属 ISSUE-016 实施细节，本草案只声明独立提交边界。

---

## 12. 拍板后流转

```text
本草案（Proposed）评审拍板
  ↓
写入 .ai/ARCHITECTURE_DECISIONS.md ADR-026 Accepted 条目（本草案定稿内容）
  ↓
.ai/DOCUMENT_INDEX.md §2.4 登记 phase1-adr-draft.md
  ↓
按 §9 Protocol-first 顺序进实施
  ↓
阶段 1a 多提交拆分（refactor/feat/fix/feat/docs）
  ↓
阶段 1b ISSUE-016 独立修复（fix: decouple export controller from infrastructure）
  ↓
质量门实测 + 架构审查 + 文档指针现场验证
  ↓
完成标准 §10 全勾 + KNOWN_ISSUES ISSUE-016 删条
```

---

> 📝 本草案由 AtomCode (GLM-5.2) 于 2026-08-11 产出，属阶段 1 开工前置门评审材料。拍板后定稿内容写入 `.ai/ARCHITECTURE_DECISIONS.md` ADR-026 Accepted 条目。

End of phase1-adr-draft.md
