# ADR-028 草案 — 阶段 3 插件写能力 import/export（前置门产出）

> **文档性质**：ADR 草案（Proposed 状态），阶段 3 开工前置门产出。
>
> 按 `AI_ONBOARDING.md §6` 与 B5-a / ADR-026 / ADR-027 前置门先例：公开 API 破坏性变更须先出草案评审拍板，拍板后才进实施。拍板后本草案定稿内容写入 `.ai/ARCHITECTURE_DECISIONS.md` ADR-028 Accepted 条目，本文件保留作设计依据。
>
> **产出时间**：2026-08-12 ｜ **产出者**：AtomCode (GLM-5.2) ｜ **状态**：Proposed（待评审拍板）

---

## 0. 裁决点（待拍板）

本草案涉及 3 项设计裁决，属你的决策（非我可自行拍板或查阅替代）：

| 裁决点 | 选项 | 推荐 |
|---|---|---|
| 1 — 写能力开放范围 | A. 仅 import_people（最小写路径，导入人员实体）/ B. 仅 export（写文件但库只读）/ C. import_people + export 双开放（完整写能力） | A |
| 2 — 宿主审批门 | A. 无审批门（插件直调 Service，宿主仅渲染结果）/ B. 宿主审批门（插件请求 → 宿主弹确认 → 执行）/ C. 宿主预授权（enable 时声明写能力，宿主一次授权后免审批） | A |
| 3 — Plugin DTO 边界 | A. 完整镜像 Application DTO（PluginImportPeopleCommand 持 PersonImportRow rows + PluginExportCommand 持 scope + exporter_format）/ B. 最小暴露（仅插件能给的入参，宿主补默认值）/ C. 双向 DTO（入参 + 结果都特化，脱 Domain Person/UUID 字面） | C |

**推荐理由**：裁决点 1=A 最小写路径先行（YAGNI：import_people 用例清晰——插件从外部 CSV/JSON 导入人员实体；export 写文件用例暂缓，因 ExportController 已有宿主路径不需插件触发）；裁决点 2=A 无审批门先行（复杂度低，宿主渲染 ActionResult 已是结果反馈，审批门留后续轮加）；裁决点 3=C 双向 DTO（与 ADR-026 Plugin DTO 边界一致，脱 Domain Person/UUID 字面，最小权限）。

**但本草案触及 B5-a 原裁决"暂缓"依据**："YAGNI 当前无清晰用例"——重新开放写能力需先确认有真实用例驱动（非我自行假造）。拍板前请你确认：**是否有真实插件写能力需求驱动本阶段**？

---

## 1. 背景

### 1.1 B5-a 暂缓项原文（实测 2026-08-12）

`docs/development/plugin-context-design.md` §v2 收敛修订（2026-08-10 拍板）：
> 原 v1 暴露 4 方法（search_photos / detect_duplicates / import_people / export）含写路径。拍板裁决："批准但将草案收敛为**只读 PluginContext** + 可选上下文注入 + 宿主渲染动作结果；**暂缓 import/export 写能力**。" 故 v2 收敛为：
> - **暂缓 import/export**：写能力留后续轮单独裁决（YAGNI 当前，无清晰用例）

`ARCHITECTURE_DECISIONS.md` ADR-025 / B5-a 裁决：暂缓项留后续轮单独裁决。本草案即该"后续轮单独裁决"。

### 1.2 现有 Application Service API（实测 2026-08-12）

> ⚠ **勘误（2026-08-25 实施时发现）**：本节所载 "ImportPeopleCommand 持 `rows`" 与代码不符——实际 `ImportPeopleCommand` 为 `source_path/has_header/sheet_name` 形状（行数据经 `PersonImportReader` 端口从文件读取）。实施裁决：新增 `ImportPeopleService.import_rows()` 预解析行入口承接本 ADR 的插件写路径（`execute()` 文件路径委托同一落库核心，语义不变）；`PluginContextService.import_people` 映射 Plugin DTO 后调用 `import_rows()`。

**ImportPeopleService**（`application/services/import_people_service.py`）：
- `execute(command: ImportPeopleCommand) -> ImportPeopleResult`
- ImportPeopleCommand 持 `rows: tuple[PersonImportRow, ...]`（name/identity/department/note/row_number）
- ImportPeopleResult 持 `imported_count/skipped_count/person_ids: tuple[UUID, ...]/errors: tuple[str, ...]`
- 依赖 `PersonImportReader`（读外部源）+ `PersonRepository`（写库）

**ExportService**（`application/services/export_service.py`）：
- `export(exporter: Exporter, output_path: Path, scope: ExportScope) -> str`（返摘要消息）
- 依赖 `PhotoRepository / PersonRepository / RecognitionResultRepository / ArchiveRecordRepository`（读库）
- ExportScope 枚举：ALL / PEOPLE_ONLY / PHOTOS_ONLY / RECOGNITION_ONLY / ARCHIVE_ONLY

### 1.3 PluginContext 现状边界（实测 2026-08-12）

`application/ports/plugin_context.py` 当前只读 2 方法：
- `search_photos(query: PluginPhotoQuery) -> tuple[PluginPhotoSummary, ...]`
- `detect_duplicates() -> PluginDuplicateReport`

注释明文："import/export 写能力暂缓留后续轮单独裁决（YAGNI 当前无清晰用例）"。

---

## 2. 裁决正文

### 2.1 写能力开放范围（裁决点 1=A：仅 import_people）

**仅开放 import_people**——最小写路径先行：

```python
class PluginContext(Protocol):
    def search_photos(self, query: PluginPhotoQuery) -> tuple[PluginPhotoSummary, ...]: ...
    def detect_duplicates(self) -> PluginDuplicateReport: ...
    # 阶段 3 新增（ADR-028）：
    def import_people(self, command: PluginImportPeopleCommand) -> PluginImportResult: ...
```

**暂缓 export**：ExportController 已有宿主路径（ExportDialog → ExportController → ExportService），不需插件触发；export 写文件用例暂缓，留后续轮单独裁决（YAGNI）。

### 2.2 宿主审批门（裁决点 2=A：无审批门）

**无审批门**——插件直调 PluginContextService.import_people，宿主仅渲染 ActionResult：
- 插件 `execute_action` 调 `context.import_people(command)` → 返 `PluginImportResult`
- 插件返 `ActionResult.success(message, PluginReport(...))` 摘要 imported/skipped/errors
- 宿主 PluginReportDialog 渲染摘要

**暂缓审批门**：复杂度低先行，审批门（B/C 选项）留后续轮加（若真实用例需高危操作确认）。

### 2.3 Plugin DTO 边界（裁决点 3=C：双向 DTO）

**入参** `PluginImportPeopleCommand`：
```python
@dataclass(frozen=True, slots=True)
class PluginImportPersonRow:
    name: str
    identity: str | None = None
    department: str | None = None
    note: str | None = None

@dataclass(frozen=True, slots=True)
class PluginImportPeopleCommand:
    rows: tuple[PluginImportPersonRow, ...]
```

**结果** `PluginImportResult`：
```python
@dataclass(frozen=True, slots=True)
class PluginImportResult:
    imported_count: int
    skipped_count: int
    imported_person_ids: tuple[str, ...]  # str 非 UUID——脱 Domain 字面
    errors: tuple[str, ...]
```

**脱 Domain**：不持 `Person` 实体 / `UUID` 字面 / `PersonRepository` 实例——最小权限，与 ADR-026 Plugin DTO 边界一致。

---

## 3. 影响范围

| 模块 | 变更类型 | 文件 |
|---|---|---|
| Application DTO | 新增 | `application/dtos/plugin_context.py`（扩 PluginImportPersonRow/PluginImportPeopleCommand/PluginImportResult） |
| Application Port | 改造 | `application/ports/plugin_context.py`（新增 import_people 签名） |
| Application Service | 改造 | `application/services/plugin_context_service.py`（扩展 import_people 映射编排 + 联动 ImportPeopleService） |
| App 装配 | 改造 | `app/bootstrap.py`（注入 ImportPeopleService 依赖到 PluginContextService） |
| Examples | 可选 | `examples/plugins/`（新增 import demo 插件或扩 stats_report） |
| Tests | 新增 | `tests/unit/application/test_plugin_context_service.py`（扩展 import 映射）+ `tests/unit/application/test_plugin_dtos.py`（扩 import DTO） |
| Docs | 改造 | `docs/development/plugin-guide.md`（写能力章节）+ `.ai/PROJECT_STATUS.md` + `.ai/ARCHITECTURE_DECISIONS.md`（ADR-028 入 Register）+ `.ai/DOCUMENT_INDEX.md`（phase3-adr-draft.md 登记） |

**不变**：Domain Schema、依赖、ExportController（宿主路径不动）、`enable(context)` 兼容路径（另项裁决）。

---

## 4. 与既有裁决的关系

| 裁决/规则 | 关系 |
|---|---|
| B5-a 暂缓项（"暂缓 import/export"） | 本草案即"后续轮单独裁决"——重新开放 import_people（export 续暂缓） |
| ADR-026（PluginContext 公共边界） | 本草案扩 PluginContext 协议——遵循 ADR-026 Plugin DTO 边界（脱 Domain，最小权限） |
| ADR-024/027（Alembic Schema） | 无变化——import_people 写库走 PersonRepository，Schema 不动 |
| DEP-060/062（Plugins → Application only） | 无变化——插件触 PluginContext Protocol，不触 ImportPeopleService / PersonRepository |
| ARC-001/006/007（职责边界） | 无变化——import_people 映射属 Application Service 职责，宿主渲染属 Presentation |

---

## 5. 执行顺序

```text
1. 现状已核对完毕（见本草案证据）
2. 新建 Plugin DTO：PluginImportPersonRow/PluginImportPeopleCommand/PluginImportResult
3. 改造 PluginContext Protocol 暴露 import_people 签名
4. 落地 PluginContextService 扩展：import_people 映射编排 + ImportPeopleService 联动
5. 改造 bootstrap：注入 ImportPeopleService 依赖到 PluginContextService
6. 补测试：DTO + Service 映射 + 最小权限 + Repository CRUD 对照回归 + 静态依赖检查
7. 更新示例插件（可选：新增 import demo 或扩 stats_report）
8. 更新文档：plugin-guide 写能力章节 + PROJECT_STATUS §3/§5/§6
9. 运行质量门与架构审查
10. 提交（feat: enable plugin write capability import people）
```

---

## 6. 完成标准

- [ ] 插件经 PluginContext.import_people(command) 能导入人员实体到库
- [ ] PluginImportPeopleCommand/PluginImportResult 脱 Domain（不持 Person/UUID 字面/PersonRepository）
- [ ] 插件不触 ImportPeopleService / PersonRepository（DEP-060 守护）
- [ ] 宿主渲染 ActionResult.success + PluginReport 摘要（imported/skipped/errors）
- [ ] export 写能力仍暂缓（本草案不开放 export）
- [ ] 不新增依赖、不改 Schema
- [ ] Ruff、MyPy、pytest 全绿（实测）
- [ ] ADR-028 入 Register + DOCUMENT_INDEX 登记 + 文档指针可解析

---

## 7. 拍板后流转

```text
本草案（Proposed）评审拍板
  ↓
写入 .ai/ARCHITECTURE_DECISIONS.md ADR-028 Accepted 条目
  ↓
.ai/DOCUMENT_INDEX.md 登记 phase3-adr-draft.md
  ↓
按 §5 顺序进实施
  ↓
提交（feat: enable plugin write capability import people）
  ↓
质量门实测 + 架构审查 + 文档指针现场验证
  ↓
完成标准 §6 全勾
```

---

> 📝 本草案由 AtomCode (GLM-5.2) 于 2026-08-12 产出，属阶段 3 开工前置门评审材料。拍板后定稿内容写入 `.ai/ARCHITECTURE_DECISIONS.md` ADR-028 Accepted 条目。
