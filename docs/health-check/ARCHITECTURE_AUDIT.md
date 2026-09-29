# ARCHITECTURE_AUDIT.md — 全面工程健康审计 · 架构审计（Stage 1）

- **审计日期**: 2026-09-28 ｜ 对象: HEAD `2823d1c` ｜ 性质: READ-ONLY
- **方法**: 声明架构（`.ai/rules/dependency-rules.md` §4 矩阵、`architecture-rules.md`、`docs/architecture/overview.md`）→ 实际依赖图（AST 全量扫描，脚本与结果见 `docs/health-check/evidence/arch_dependency_scan.py` / `arch_scan_result.json`）→ 逐行比对 + 定点读码验证
- **证据基线**: 258 个源文件全部解析；层间边缘 19 组；SCC 环检测；116 处函数级导入去重后 10 组

---

## 1. 实际架构 [VERIFIED]

```text
                     ┌─────────────────────────── app/（组合根，import 全开）───────────────────────────┐
                     │  → infrastructure ×15   → application ×9   → presentation ×5                    │
                     │  → ai ×3   → workers ×3   → domain ×1                                           │
                     └─────────────────────────────────────────────────────────────────────────────────┘
 presentation ──45──▶ application ◀──6── workers          ai ──4──▶ domain ◀──38── infrastructure
      │ │ │                │ ▲                                ▲              ▲            │ 19
      │ │ └─ plugins ×1    │ └─ 82 边（services→domain 仓储/实体/值对象）     │            │ （实现 application/ports）
      │ └─── workers ×11   └──── 82 边中含仓储 Protocol 调用        domain │      application
      └───── domain ×18                                            （零内部依赖）
```

- **依赖方向总体正确**：domain 零内部依赖（stdlib-only）；application 只依赖 domain；无 presentation→infrastructure、无 infrastructure→presentation/workers/app、无 application→presentation。
- **无模块级循环依赖**：Tarjan SCC 全图扫描 size≥2 的强连通分量 = **0**（DEP-018 达标）。
- **分层守卫常驻**：`tests/unit/architecture/test_layer_boundaries.py` 对六层逐文件 AST 断言本地+第三方禁令，随 CI 三平台运行；本轮全量套件中该项通过。

## 2. 声明 vs 实际：DEP §4 依赖矩阵比对 [VERIFIED] → **AUD-009**

`dependency-rules.md` §4 自称"矩阵权威"，但 **5 行与实际代码和守卫测试均不符**：

| 矩阵行（声明） | 实际（AST 实测） | 守卫测试口径 |
|---|---|---|
| `app \| presentation, application, common` | 另有 infrastructure ×15、workers ×3、ai ×3、domain ×1 | 测试明确豁免 app（"组合根 import 全开"） |
| `infrastructure \| domain, common` | **另有 application ×19**（全部为实现 `application/ports/*`：exporter、unit_of_work、user_settings_store、photo_file_scanner、thumbnail_generator、person_import_reader 等） | 测试不禁止（正确反映端口模式） |
| `presentation \| application, common` | 另有 domain ×18、workers ×11、plugins ×1（ADR-038 在案）、app ×1（TYPE_CHECKING，测试注释在案） | 测试允许 domain/workers |
| `ai \| infrastructure, domain, common` | 仅 domain ×4（实际比声明更严格） | 一致 |
| `workers \| application, common` | 另有 domain ×2（application_tasks/export_task 引实体） | 测试允许 |

判定：矩阵是**端口迁移到 application 层 + TaskCoordinator 接线之前的历史快照**，从未随代码演进更新；守卫测试实际上已成为真正的架构契约 SSOT（其 docstring 记载了例外条款），但两份"权威"互相矛盾——按项目自身方法论（`.ai/rules/audit-methodology.md` §4）属 **Critical/Major 级真实矛盾**（同一规则两个说法）。实际风险：误导维护者按矩阵"纠正"代码反而破坏端口模式，或新依赖无从判合法。

## 3. 规则违例核查 [VERIFIED] → **AUD-010**

| 规则 | 结果 |
|---|---|
| DEP-004 presentation 不实例化仓储实现 | ✅ 干净（grep 零命中） |
| DEP-012 application 无 SQL | ✅ 干净（SQL 全部隔离于 `infrastructure/database/` 10 个仓储文件） |
| DEP-021 domain 框架无关 | ✅ domain 第三方=纯 stdlib（dataclasses/enum/pathlib/typing/uuid/collections/datetime/copy/types） |
| DEP-002 presentation 禁 sqlite3/cv2/insightface/pandas/openpyxl/numpy | ✅ 第三方仅 PySide6+loguru+stdlib |
| DEP §13 直连传递依赖禁令（scipy/skimage/networkx/protobuf/onnx） | ✅ 全仓零直连 |
| **DEP §17 仅 Infrastructure 可访问文件系统** | ❌ **application 层 3 个服务直接文件 I/O**（见下） |

**AUD-010 证据**（application 层直接 I/O）：
- `application/services/archive_executor.py:191`（`target.parent.mkdir(parents=True, exist_ok=True)`）、`:288-290`（函数内 `import shutil` + `shutil.copy2(source, target)`）——**核心归档落盘**在 Application 内完成，含符号链接防护逻辑（review M-4，配套 `test_archive_executor_symlink.py`）
- `application/services/recognition_failure_service.py:116`（`open(path, "w", encoding="utf-8-sig")` 直接写失败清单 CSV，且 `import csv`）——Stage F 新增，绕过既有 `application/ports/exporter` + `infrastructure/exporters/` 导出栈
- `application/services/parse_import_draft_service.py:292`（`source_path.open("rb")` 直读名单文件字节）

说明：守卫测试（T-1）只编码 sqlite3/cv2/PIL 等第三方禁令，**未编码文件 I/O 禁令**——守卫弱于声明规则，违例可在 CI 全绿下持续累积。同类还有 `concurrent.futures`（match_persons_service:16、run_recognition_service:4 自建线程池，与 workers 层构成双并发机制——规则未禁，Stage 6 一并审查取消/生命周期）。

## 4. 抽象一致性 [VERIFIED] → **AUD-011**

- `application/use_cases/` 11 个 UseCase 协议存在，早期流程（archive/review/match/scan/import/settings）的控制器按协议依赖（`archive_controller.py:17`，注释明示 review M-3 意图："presentation 依赖 UseCase Protocol 而非具体服务类"）；**36 个服务中 25 个无协议**，Stage B/E/F 新流程的 presentation 直接 import 具体服务类：`export_controller.py:17`（ExportService）、`detect_duplicates_controller.py:25`、`cluster_results_dialog.py:29`、`person_deletion_dialog.py:20`（ListPersonsService）、`people_admin_page.py:41`、`pairing_workbench_dialog.py:35`；其中 4 处为 **views 直接调用服务**，绕过 ARC-010 的控制器模式。
- 判定：协议边界"半推半就"——同一层内两种风格并存，M-3 确立的意图未成为一致实践。行为无缺陷，属一致性/可维护性债。

## 5. 重复抽象核查 [VERIFIED]（嫌疑排除）

| 嫌疑 | 结论 |
|---|---|
| `ai/similarity_matcher.py`（CosinePersonMatcher）vs `infrastructure/cosine_kernel.py`（NumpyCosineSimilarityLookup） | **非重复**：分别实现两个不同端口（`PersonMatcher` 识别匹配 vs `SimilarityLookup` 聚类矩阵），消费方不同（识别 vs Stage D 聚类）；前者纯 Python 避免识别热路径拉 numpy，后者 numpy 矩阵化并量化 6 位小数保确定性。设计合理。 |
| `presentation/person_matcher.py` | **非业务泄漏**：纯函数 `rank_person_names`（人员下拉搜索排名，零 Qt 零 IO）。但与 `application/ports/person_matcher.py`（PersonMatcher 协议）**同名异义** → AUD-012（`filter_bar.py:107` 注释已显示混淆） |
| `infrastructure/repositories/in_memory_*`（7 个） | **非死代码**：项目声明为测试替身/非 SQLite 实现位（ARC-009）；被 `tests/unit/domain/test_repository_contracts.py` 等消费 |
| `main.py`（根目录 31KB） | 入口/CLI 编排，调用 application 命令，无业务规则复制；位于层规则管辖外（ARC §3 只管 `src/photo_archiver`），可接受 |

## 6. 规模热点与 God Object [VERIFIED] → **AUD-013**

- `presentation/views/main_window.py` **1577 行 / 1 类 / 63 函数**（最大 `_build_photo_library_page` 123 行）——窗口壳+六页构建集中一处，逻辑已外移控制器（"Widget 零仓储访问"模式），但体量随阶段 B–F 持续增长，呈 God-class 趋势。
- `app/services.py::build_application_services` **227 行**装配函数（文件 458 行）——纯 DI 接线，风险低但新增服务时修改集中。
- 其余视图 250–620 行（people_admin_page 618）、服务 250–380 行，分布均匀；>120 行函数全仓仅 2 个（上两处）。
- `common/` 模块：仅 1 行 docstring——ARC-008/DEP-070 声明的职责（常量/校验器/基类）**零实现**，空占位结构。

## 7. 贫血域检查 [VERIFIED]

域非贫血：`domain/entities/person.py` 含 `__post_init__` 校验（`raise ValidationError`）；`domain/services/face_clustering.py`（301 行，含 `_merge_pair` 合并门限算法）、`domain/services/pairing.py` 承载真实业务规则；值对象 9 个含 `ArchivePath`（净化/拼接）、`FaceEmbedding`（维度约束）等行为型对象。

## 8. 遗留观察（不立案，Stage 2/6 跟进）

1. `infrastructure/config/settings.py:27-41` 惰性导入 `photo_archiver._build_info`（构建期由 release.yml 注入）——已核验 try/except 回退完整，**非缺陷**。
2. `application/ports/plugin.py:144,196` 函数级导入同层 DTO——无环风险，风格问题。
3. `infrastructure/persistence/qsettings_user_settings_store.py` 使 infrastructure 依赖 PySide6（QSettings）——ARC-009 已声明该子包职责，DEP §13 PySide6 无条件批准，合规；记录在案。
4. `app/bootstrap.py:5,139` import sqlite3 捕获 `DatabaseError`（启动完整性检查）——组合根职权内，合规。

## 9. Stage 1 结论

架构**骨架健康**：分层方向正确、零循环依赖、SQL/图像/AI/第三方隔离全部达标、守卫测试常驻 CI、域模型非贫血。问题集中在**架构治理**而非架构本身：(1) 依赖矩阵 SSOT 与代码/守卫测试三方矛盾（AUD-009）；(2) 声明规则（文件 I/O）超出守卫覆盖且已被 3 处违反（AUD-010）；(3) 协议边界双轨制（AUD-011）。均为可控、可机械修复的债务，暂无阻断性违约。

## Findings 汇总（详见 FINDINGS_LEDGER.md）

```text
P0: 0
P1: 0
P2: 2   (AUD-009 依赖矩阵三方矛盾；AUD-010 application 层文件 I/O 违反 DEP §17 + 守卫盲区)
P3: 3   (AUD-011 UseCase 协议双轨制；AUD-012 person_matcher 同名异义；AUD-013 common 空置 + main_window 规模趋势)
```
