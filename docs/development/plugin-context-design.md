# PluginContext Interface 详细方案（B5-a 前置门）

> **文档性质**：B5-a 裁决前置门产出——按 §6 B5-a 要求"开工前必须先出 PluginContext interface 草案评审"，本文件即该草案的完整方案版。评审拍板后才进 loader 装配与示例插件实施。
>
> **文档状态（2026-08-11）**：已纳入正式文档体系（`.ai/DOCUMENT_INDEX.md` §2.4 登记），作为 B5 PluginContext 接口设计决策依据文档；非 SSOT——实现现状以代码与 `PROJECT_STATUS.md` 为准，B5-a 裁决见 `ARCHITECTURE_DECISIONS.md`。阶段 1 加固（ADR-026）后本草案 v3 收敛：``ContextAwarePlugin(Plugin)`` 继承 + ``set_context(context) → enable()`` 新标准 + Plugin DTO 边界（``PluginPhotoQuery`` 3 态 / ``PluginPhotoSummary`` 4 态含 none）+ ``PluginReport`` 单元格 ``str | int | float`` 混合 + ``ActionResult.report`` 收紧替旧 ``payload:Any``——详见 `docs/development/phase1-adr-draft.md`。
>
> **文档状态补充（2026-08-25）**：阶段 3 已按 ADR-028 重新开放部分写能力——`PluginContext.import_people` 已落地（仅 import_people；export 续暂缓）。本文下述 v2 收敛块中"只读 / 暂缓 import/export"的表述自该裁决起**部分过时**；实现现状以代码与 `.ai/PROJECT_STATUS.md` 为准，见 `.ai/ARCHITECTURE_DECISIONS.md` ADR-028 与 `docs/development/phase3-adr-draft.md`。
>
> **裁决编号**：B5-a（已拍板"批准设计"+ 前置门"开工前出草案评审"）
>
> **产出时间**：2026-08-02
>
> **产出者**：AtomCode (GLM-5.2)
>
> **v2 收敛修订（2026-08-10 拍板）**：原 v1 暴露 4 方法（search_photos / detect_duplicates / import_people / export）含写路径。拍板裁决："批准但将草案收敛为**只读 PluginContext** + 可选上下文注入 + 宿主渲染动作结果；**暂缓 import/export 写能力**。" 故 v2 收敛为：
> - **只暴露读方法**：search_photos + detect_duplicates（删 import_people / export）
> - **可选上下文注入**：Plugin.enable(context=None)——context 为 None 时插件走无 Context 路径（兼容纯声明插件如 HelloPlugin）
> - **宿主渲染动作结果**：Plugin.execute_action 改为 `execute_action(action_id) -> ActionResult`——插件返结构化结果对象，宿主负责渲染/展示（插件不直触 UI/文件系统）
> - **暂缓 import/export**：写能力留后续轮单独裁决（YAGNI 当前，无清晰用例）

---

## 0. 文档目的

回答 §6 B5-a 裁决原文提出的 6 个问题：

1. Context 暴露 ImportPeopleService / ExportService / DetectDuplicatesService（B1 落地后）/ SearchPhotosService（B2 落地后）的**哪些方法**？
2. **是否暴露只读 Repository 查询**？
3. Context 是否需带 **ProgressReporter**？
4. Context 是否需带 **当前 ApplicationContext 引用**？
5. **禁止暴露什么**及理由？
6. **Plugin 公开 API 怎么变**？loader 装配怎么变？

本文件分 10 节，按裁决前置门的证据门槛逐一回答，并附实施路径与验收标准。

---

## 1. 归属与定位

### 1.1 归属层

**Application 层** `src/photo_archiver/application/ports/plugin_context.py`。

理由：

- 与 Plugin Protocol（`application/ports/plugin.py`）同目录——插件依赖的公开 API 集中在 Application port 边界
- DEP-060 约束：Plugins → Application only，不得 import Infrastructure
- 门面是"Application 向 Plugins 提供的受限能力集"，归 Application port 边界最合分层契约

### 1.2 性质

**门面（Facade）**，非 Service 全集。

核心设计原则（同 §6 B5-a 裁决原文）：

> Context 是门面不是 Service 全集，防止插件绕过编排直触仓储。

具体含义：

- 只暴露插件**允许调用**的 Application Service 子集
- 不暴露 Service 的**全部方法**——只暴露编排用例边界方法
- 不暴露 Service 持有的 **Repository 引用**——插件无法经 Service 拿到仓储再绕编排

### 1.3 装配时机

**bootstrap 构造一次**，与 ApplicationContext 同生命。

- app 启动时 bootstrap 构造 PluginContext 实例
- app 退出时销
- plugin disable/enable **不重建** Context——Context 是 host 级单例，与单个插件生命周期解耦

### 1.4 生命周期

| 阶段 | Context 状态 |
|---|---|
| app 启动 bootstrap | 构造 PluginContext，注入所持 Service 引用 |
| MainWindow `_load_plugins` | 从 ApplicationContext 取 PluginContext，传 PluginRegistry |
| PluginRegistry `enable_all` | 调每个 plugin.enable(context) 注入 |
| plugin `execute_action` | 用存的 context 引用调 Service |
| app 退出 | Context 随 ApplicationContext 销，无需显式释放（所持 Service 引用是弱关系，host 自管） |

---

## 2. 暴露的 Service 子集清单

按裁决前置门要求，本节列**每方法签名** + 暴露理由 + 不暴露该 Service 的哪些方法及理由。

### 2.1 SearchPhotosService（B2 落地后）

**暴露方法**：

```python
def search_photos(self, criteria: PhotoSearchCriteria) -> list[Photo]:
    """Return photos matching the supplied search criteria.

    暴露 SearchPhotosService.execute —— B2 落地后的查询编排，插件
    可据 person/status/date 区间取照片做统计报表等读路径用例。
    """
```

**暴露理由**：

- 读路径无副作用——查询不写任何仓储
- 统计报表插件的核心用例：按 person/status 区间取照片计数
- SearchPhotosService 是 Application 编排，经它走 SQLite SQL 下推 / InMemory 内存过滤的完整链路，非直触仓储

**不暴露该 Service 的什么**：

- SearchPhotosService 无其他公开方法——`__init__(photo_repository)` 是构造器不暴露
- 所持 `self._photo_repository` 不暴露——门面封装，插件无法经 Service 拿到仓储

### 2.2 DetectDuplicatesService（B1 落地后）

**暴露方法**：

```python
def detect_duplicates(self) -> DuplicateReport:
    """Return the duplicate-photo report across all loaded photos.

    暴露 DetectDuplicatesService.execute —— B1 落地后的查重编排，插件
    可取重复组做报表展示等读路径用例。
    """
```

**暴露理由**：

- 读路径无副作用——查重不写任何仓储
- DuplicateReport DTO 是 Application 层数据载体，插件可读其结构做报表
- 经 Application 编排走 PhotoRepository.list_duplicate_groups 完整链路

**不暴露该 Service 的什么**：

- 同 2.1——无其他公开方法，所持 Repository 不暴露

### 2.3 ImportPeopleService（写路径，非高危）

**暴露方法**：

```python
def import_people(self, source_path: str) -> ImportPeopleResult:
    """Import people from the given text-file source path.

    暴露 ImportPeopleService.execute —— 名单导入属写路径但非高危
    （仅写 Person 仓储，不触归档/删除），外部名单导入插件消费。
    """
```

**暴露理由**：

- 名单导入是插件用例的典型写路径（外部名单导入插件候选见 §6）
- 仅写 Person 仓储——非高危（不触归档/删除/移动用户文件）
- ImportPeopleResult DTO 是 Application 层数据载体，插件可读成功/失败计数

**不暴露该 Service 的什么**：

- 所持 PersonRepository 不暴露
- 无其他公开方法

### 2.4 ExportService（导出编排，有副作用但用户选定路径）

**暴露方法**：

```python
def export(
    self,
    exporter: Exporter,
    output_path: str,
    scope: ExportScope = ExportScope.ALL,
) -> str:
    """Export data to output_path via the given exporter, return summary.

    暴露 ExportService.export —— 统计报表插件可调 HtmlExporter 生成
    报表文件。exporter 由插件选定（Context 不持 exporter 注册表，
    避免门面膨胀；插件自构 CsvExporter/HtmlExporter 等 stdlib 零依赖
    exporter，或持自带的）。
    """
```

**暴露理由**：

- 统计报表插件的核心用例：生成"归档总览报表"HTML 文件
- 副作用是写文件到用户选定路径——非高危（不移动用户原文件，只生成新报表）
- ExportService 经 Exporter Protocol 多态注入，插件自选 exporter

**关键设计决策：exporter 由插件选定，Context 不持 exporter 注册表**

理由：

- 避免门面膨胀——Context 不应持"格式 → Exporter 映射"注册表
- 插件自构 `HtmlExporter()` / `CsvExporter()` 是 stdlib 零依赖（B4 落地后 HtmlExporter 仅 stdlib html/string）
- 若插件要自带非 stdlib exporter（如 PDF），由插件自带依赖，host 不背

**不暴露该 Service 的什么**：

- 所持各 Repository 不暴露（ExportService 持 person/photo/recognition/archive_repo 四个引用）
- `_gather_data` / `_flatten` 私有方法不暴露

---

## 3. 不暴露什么及理由

按裁决前置门要求，本节显式列**禁止暴露**清单 + 每项理由。

### 3.1 禁止：直接 Repository 实例

**禁止项**：PhotoRepository / PersonRepository / RecognitionRepository / ArchiveRecordRepository 等任何仓储实例。

**理由**：

- **门面原则**——插件绕过编排直触仓储会破 UnitOfWork 边界
- **业务不变量**——Application 编排守的业务规则（如 ArchivePlanner 的 1:N Top-1 策略、SearchPhotosService 的 SQL 下推契约）插件直触仓储会绕过
- **审计盲点**——host 无法经 Service log 观测插件对仓储的操作

### 3.2 禁止：UnitOfWork

**禁止项**：UnitOfWork 边界对象 / 事务管理器。

**理由**：

- 事务边界归 Application 编排——插件不应自管事务
- 插件自管事务会破 host 的事务一致性（如归档需原子写 ArchiveRecord + 移文件，插件不应自拆）

### 3.3 禁止：ArchivePhotosService（含写能力的归档）

**禁止项**：ArchivePhotosService / ArchivePlanner / ArchiveExecutor。

**理由**：

- **§6 B5-a 裁决原文明文禁止**："禁止暴露直接 Repository 实例 / UnitOfWork / 含写能力的 ArchivePhotosService（归档属高危操作不应让插件触发）"
- 归档是**高危操作**——移动用户原文件到归档目录，不可逆
- 触发归档应由 host UI 经 ArchiveController 走完整 preview dialog 确认流，插件不应绕过此确认直接触发

### 3.4 禁止：ArchiveExecutor / WorkerExecutor

**禁止项**：Worker 调度器 / 长耗时任务提交能力。

**理由**：

- 长耗时任务调度归 host——插件经 Context 同步编排即足
- 插件自提交 Worker 会破 host 的"单活动任务"约束（host 用 `_active_runnable` 跟踪当前任务，插件自提交会绕过此单活跃约束）
- 所暴露 Service 均同步编排（search_photos/detect_duplicates/import_people/export），完成即返——无长耗时需 Worker

### 3.5 禁止：ApplicationContext 引用

**禁止项**：整个 ApplicationContext 对象引用。

**理由**：

- Context 持整个应用上下文会**绕开门面边界**——ApplicationContext 含所有 Service / Repository / Controller 引用，插件经 Context 拿到 context 即拿到全集
- Context 只**显式持所暴露 Service 的引用**——非整个上下文
- 装配时 bootstrap 显式传 4 个 Service 引用给 PluginContext 构造器，非传 ApplicationContext

### 3.6 禁止：SettingsService 写能力

**禁止项**：SettingsService 的写方法 / UserSettingsStore 引用。

**理由**：

- 设置写入归 host UI——插件不应改用户设置（如 archive_root、conflict_strategy）
- 读能力**暂不暴露**——无清晰用例（YAGNI 当前），若未来插件需读 settings 做行为决策，再单独裁决加只读门面

---

## 4. ProgressReporter / ApplicationContext 引用决策

按裁决前置门问题 3/4，本节显式回答。

### 4.1 ProgressReporter：不暴露

**决策**：不暴露 ProgressReporterPort。

**理由**：

- 所暴露 4 个 Service 均同步编排，完成即返——无长耗时需报进度
  - search_photos：SQLite SQL 下推 <50ms 典型
  - detect_duplicates：单查询 IN，O(单) 不是 O(N²)
  - import_people：名单导入通常 <100 人，<1s
  - export：Excel/CSV/HTML 导出，<1s 典型
- 若未来插件需长耗时用例（如批量图像处理），**再单独裁决**加 ProgressReporterPort（YAGNI 当前）

### 4.2 ApplicationContext 引用：不暴露

**决策**：PluginContext 不持 ApplicationContext 引用。

**理由**：

- 见 §3.5——持整个上下文会绕开门面边界
- Context 只显式持所暴露 Service 的引用（4 个）
- 装配时 bootstrap 显式传 Service 引用，非传 context

---

## 5. Plugin Protocol API 变更

按裁决前置门问题 6，本节显式回答 Plugin 公开 API 怎么变。

### 5.1 `enable()` 签名扩参注入 Context

**变更前**（现状）：

```python
class Plugin(Protocol):
    def enable(self) -> None:
        """Activate the plugin (called after loading or on user enable)."""
```

**变更后**：

```python
class Plugin(Protocol):
    def enable(self, context: PluginContext) -> None:
        """Activate the plugin with the host-provided context.

        Args:
            context: PluginContext 门面——插件经此访问受限 Application
                Service 子集。host 在 enable_all() 时注入；插件应存此引用
                供 execute_action() 使用。

        Implementations should perform any resource allocation here AND
        store the context reference for later use in execute_action().
        """
```

**兼容性影响**：

- 这是**Plugin 公开 API 破坏性变更**——既有 HelloPlugin.enable() 签名需改
- HelloPlugin 是 example 非 production，改其签名即可
- 第三方插件（若有）需同步改——但项目尚无第三方插件生态，无迁移成本

### 5.2 `execute_action` 不变

**不变**：

```python
def execute_action(self, action_id: str) -> None:
    """Execute the command identified by ``action_id``."""
```

**理由**：

- action 触发时插件用存的 context 引用调 Service
- context 在 enable() 时已注入并存于 plugin 实例，execute_action 不需再传

### 5.3 其他 Plugin 方法不变

`name` / `version` / `disable` / `actions` 均不变。

- `disable()` 不需 context——插件释放资源时不再调 Service
- `actions()` 是声明性描述，不需 Service

---

## 6. loader 装配变更

按裁决前置门问题 6，本节显式回答 loader 装配怎么变。

### 6.1 PluginRegistry 构造器扩参

**变更前**（现状）：

```python
class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._enabled: set[str] = set()
        self._errors: list[tuple[str, str]] = []
```

**变更后**：

```python
class PluginRegistry:
    def __init__(self, context: PluginContext) -> None:
        self._context = context
        self._plugins: dict[str, Plugin] = {}
        self._enabled: set[str] = set()
        self._errors: list[tuple[str, str]] = []
```

### 6.2 enable_all 透传 context

**变更前**：

```python
def enable_all(self) -> None:
    for name, plugin in self._plugins.items():
        try:
            plugin.enable()
            self._enabled.add(name)
```

**变更后**：

```python
def enable_all(self) -> None:
    for name, plugin in self._plugins.items():
        try:
            plugin.enable(self._context)  # 透传 context
            self._enabled.add(name)
```

### 6.3 MainWindow `_load_plugins` 改从 ApplicationContext 取

**变更前**（现状）：

```python
def _load_plugins(self) -> None:
    self._plugin_registry = PluginRegistry()  # 自构
    examples_plugins = Path(...) / "examples" / "plugins"
    if examples_plugins.is_dir():
        self._plugin_registry.load_from_path(examples_plugins)
        self._plugin_registry.enable_all()
        self._add_plugin_actions()
```

**变更后**：

```python
def _load_plugins(self) -> None:
    # 从 ApplicationContext 取已装配的 PluginRegistry（含 PluginContext）
    self._plugin_registry = self._context.plugin_registry
    examples_plugins = Path(...) / "examples" / "plugins"
    if examples_plugins.is_dir():
        self._plugin_registry.load_from_path(examples_plugins)
        self._plugin_registry.enable_all()
        self._add_plugin_actions()
```

### 6.4 bootstrap 装配新增

**新增**：bootstrap 构造 PluginContext 实例 + PluginRegistry 实例。

```python
# app/bootstrap.py 新增段
plugin_context = PluginContext(
    search_photos=services.search_photos,
    detect_duplicates=services.detect_duplicates,
    import_people=services.import_people,
    export=services.export,
)
plugin_registry = PluginRegistry(context=plugin_context)
```

**ApplicationContext 扩字段**：

```python
# app/context.py 新增字段
plugin_registry: PluginRegistry
```

---

## 7. 涉及文件清单

按 dev-plan §B5 涉及文件原文 + 本方案细化：

| 文件 | 改动性质 | 改动内容 |
|---|---|---|
| `src/photo_archiver/application/ports/plugin_context.py` | **新建** | PluginContext Protocol + 4 方法签名 |
| `src/photo_archiver/application/ports/plugin.py` | 改 | `enable(self)` → `enable(self, context: PluginContext)` |
| `src/photo_archiver/plugins/loader.py` | 改 | PluginRegistry `__init__` 扩参 context + `enable_all` 透传 |
| `src/photo_archiver/app/bootstrap.py` | 改 | 构造 PluginContext + PluginRegistry 实例 |
| `src/photo_archiver/app/context.py` | 改 | ApplicationContext 扩 `plugin_registry` 字段 |
| `src/photo_archiver/presentation/views/main_window.py` | 改 | `_load_plugins` 改从 context 取 PluginRegistry |
| `examples/plugins/hello_plugin.py` | 改 | `enable()` 签名扩参 + 存 context 引用 |
| `examples/plugins/stats_report_plugin.py` | **新建** | 统计报表插件示例（读路径：search_photos + export HtmlExporter） |
| `tests/unit/application/test_plugin_context.py` | **新建** | PluginContext Protocol 契约测试 |
| `tests/unit/plugins/test_plugin_registry_context_injection.py` | **新建** | loader 透传 context 测试 |
| `tests/integration/test_plugin_context_e2e.py` | **新建** | 示例插件端到端测试（action → context → Service） |

---

## 8. 实施路径（B5-3 ~ B5-5）

### B5-3 PluginContext Port 落地 + 注入路径 + loader 装配

1. 新建 `application/ports/plugin_context.py` —— Protocol + 4 方法签名
2. 改 `application/ports/plugin.py` —— enable 签名扩参
3. 改 `plugins/loader.py` —— PluginRegistry 扩参 + enable_all 透传
4. 改 `app/bootstrap.py` —— 构造 PluginContext + PluginRegistry
5. 改 `app/context.py` —— 扩 plugin_registry 字段
6. 改 `presentation/views/main_window.py` —— `_load_plugins` 改从 context 取
7. 改 `examples/plugins/hello_plugin.py` —— enable 签名扩参 + 存 context

### B5-4 测试

1. `test_plugin_context.py` —— Protocol 契约测试（4 方法签名 + 不暴露项审计）
2. `test_plugin_registry_context_injection.py` —— loader 透传 context 测试
3. `test_plugin_context_e2e.py` —— HelloPlugin / stats_report_plugin 端到端
4. 新建 `examples/plugins/stats_report_plugin.py` —— 统计报表插件示例

### B5-5 质量门

1. ruff 0 + mypy 0 + pytest 全绿
2. PROJECT_STATUS §3/§4/§5 刷新
3. plugin-guide.md 补 PluginContext 章节（dev-plan §B5 验收条目）

---

## 9. 验收标准

按 dev-plan §B5 验收标准原文 + 本方案细化：

- [ ] 插件仅经 PluginContext 访问业务能力，无法 import Infrastructure（依赖审计测试或 review 确认）
- [ ] 妥插件加载失败仍不崩主程序（回归既有测试）
- [ ] 至少 1 个实用插件端到端可用（action 出现 → 点击 → 业务执行 → 用户反馈）—— stats_report_plugin 候选
- [ ] 核心应用不依赖任何具体插件（Protocol First 不回退）
- [ ] PluginContext 不暴露 Repository 实例 / UnitOfWork / ArchivePhotosService / WorkerExecutor / ApplicationContext 引用（审计测试守护）
- [ ] Plugin.enable 签名变更后既有 HelloPlugin example 同步改且通过测试

---

## 10. 裁决前置门回答汇总

按 §6 B5-a 裁决原文的 6 问，本方案回答汇总：

| # | 问题 | 回答 |
|---|---|---|
| 1 | Context 暴露哪些 Service 的哪些方法？ | search_photos / detect_duplicates / import_people / export 共 4 方法（见 §2） |
| 2 | 是否暴露只读 Repository 查询？ | **否**——经 Application Service 编排访问，不直触仓储（见 §3.1） |
| 3 | Context 是否需带 ProgressReporter？ | **否**——所暴露 Service 均同步编排，YAGNI（见 §4.1） |
| 4 | Context 是否需带 ApplicationContext 引用？ | **否**——只显式持 4 个 Service 引用（见 §4.2 + §3.5） |
| 5 | 禁止暴露什么及理由？ | Repository / UnitOfWork / ArchivePhotosService / WorkerExecutor / ApplicationContext / SettingsService 写能力（见 §3） |
| 6 | Plugin 公开 API 怎么变？loader 装配怎么变？ | enable 扩参注入 context；PluginRegistry 扩参 + enable_all 透传；bootstrap 构造；MainWindow 改从 context 取（见 §5 + §6） |

---

## 11. 评审门槛

本方案已回答 §6 B5-a 裁决全部 6 问。按裁决前置门要求，**评审拍板后才进 B5-3 实施**。

待你三选一：

| 选项 | 含义 |
|---|---|
| **批准草案** | 照此落地——PluginContext Protocol 4 方法 + Plugin.enable 扩参 + loader 透传 + bootstrap 装配 |
| **批准但调整** | 方向对但需改暴露面（如加/减某 Service、改 ProgressReporter 决策等）——请说明调整点 |
| **否决重出** | 草案不妥——请说明否决理由 + 期望方向 |

---

End of Document
