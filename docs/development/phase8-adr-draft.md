# Phase E ADR 前置门草案 — 删除语义与库管理（P2-1/P2-2/P2-3）

| 项 | 内容 |
|---|---|
| 状态 | **Accepted（owner 拍板 2026-09-06：D1–D6 全部按建议执行——「按建议执行」）** |
| 日期 | 2026-09-06 |
| 前序 | roadmap Phase E（owner 立项门开启，选定路径二）；开发计划 `docs/development/phase-e-deletion-plan.md`；schema 级联矩阵实证（`alembic/versions/002_split_create_ddl.py`） |
| 目标版本 | v2.4.0（minor——新增删除/对账能力，契约只增不改） |

---

## §0 背景与动机

库自 Step 5 起"只进不出"：照片与人员一旦登记便无法移除，重复导入、误扫目录、人员离职等真实运营场景无出口。roadmap 将其列为 Phase E（P2，owner 立项门），前置条件"删除必须建立在有备份的基础上"已由 Phase B 启动备份（`VACUUM INTO` + 3 份滚动，J6 恢复演练实证）满足。owner 于 2026-09-06 开启立项门并批准开发计划，本 ADR 固化六项裁决（D1–D6）。

## §1 证据链（schema 实证，锚点 `alembic/versions/002_split_create_ddl.py`）

| # | 事实 | 锚点 |
|---|---|---|
| F1 | `recognition_results.photo_id → photos` 为 **ON DELETE CASCADE** | 002_split_create_ddl.py:92 |
| F2 | `recognition_results.person_id → people` 为 **ON DELETE SET NULL** | :93 |
| F3 | `person_embeddings.person_id → people` 为 **ON DELETE CASCADE** | :103 |
| F4 | `archive_records.photo_id → photos` 为 **ON DELETE CASCADE** | :119 |
| F5 | `photos.folder_id → folders` 为 **ON DELETE SET NULL** | :79 |
| F6 | 应用连接每条均施加 `PRAGMA foreign_keys=ON`（级联真实生效，有专项测试） | `sqlite_connection.py` `_configure_connection`；`test_sqlite_connection_pragmas.py::test_connect_keeps_foreign_keys_and_row_factory` |
| F7 | Domain 仓储协议**零删除方法**（`add/find/list/search` only——grep 实证），删除能力为本 ADR 新增 | `domain/repositories/{photo,person}_repository.py` |
| F8 | 既有 IN 子句分块先例（500 参数/块） | ADR-029 `list_first_by_photo_ids` |
| F9 | 排序确定性教训：同刻 `created_at` 必须有显式决胜（UUID 决胜曾致 macOS CI flake） | LIMIT-005（已修复留档） |

**推论**：删除级联语义已在 DB 层由 FK 完整表达——本 ADR 确认既有语义而非新设计；**零 schema migration**（软删除才需要，D4 否决）。

## §2 裁决点（拍板表，owner 2026-09-06 全按建议）

| # | 裁决点 | 拍板 | 语义 |
|---|---|---|---|
| D1 | 照片删除的库级联 | **A：确认既有 CASCADE** | 删照片 → 识别结果 + 归档记录级联删除（FK F1/F4 自动） |
| D2 | 人员删除的库级联 | **A：确认既有 SET NULL + CASCADE** | 删人员 → 嵌入删除（F3）、识别结果归属置空变"未知人员"（F2）、**照片全部保留** |
| D3 | 磁盘文件处置 | **A：DB 删登记，任何磁盘文件一律不动** | 含照片原文件与已归档产物；UI/CLI 文案必须明示 |
| D4 | 硬删除 vs 软删除 | **A：硬删除（不扩 schema）** | 回收站/撤销为 roadmap Out-of-Scope；安全网 = Phase B 启动备份（J6 已实证恢复路径） |
| D5 | 重扫对账语义 | **A：扫描只增不删 + 显式失联清理** | 文件消失不自动删库（防移动盘未挂载误判）；提供独立清理入口（CLI `prune-missing`，先列后删）；文件内容变化（mtime/hash）→ 更新登记元数据 |
| D6 | 重复照片处置 | **A：组内保留最早注册一张，其余删登记（文件不动）** | "最早注册"= `created_at` 最小，同刻按 id 决胜（F9 教训）；手动勾选保留为后续增强，不入 v2.4.0 |

### 通用裁决（随 D1–D6 一并生效）

- **幂等**：`remove` 目标不存在 = 0 行视为成功，不抛错；
- **确认流**：所有删除必须经确认（预览级联计数：照片/识别/归档各 N）；
- **审计**：每次删除经 loguru 记录审计行（操作、id 列表、实际删除数）；
- **批量分块**：IN 子句按 500 参数分块（F8 先例）。

## §3 拟议变更清单

| 文件 | 改动 |
|---|---|
| `domain/repositories/photo_repository.py` / `person_repository.py` | 协议扩 `remove(photo_ids: Sequence[UUID]) -> int` / `remove(person_id: UUID) -> int` |
| `infrastructure/database/sqlite_{photo,person}_repository.py` | 分块 DELETE 实现（级联由 FK 保证，F6） |
| `infrastructure/repositories/in_memory_{photo,person}_repository.py` | 测试替身同步（仅删本聚合，**不模拟级联**——级联验证专属真实 SQLite，见 §4.4） |
| `application/dtos/deletion.py`（新建） | DeletePhotosCommand / DeletionPreview / DeletionResult / PrunePlan 等 DTO |
| `application/services/delete_photos_service.py` 等四个服务（新建） | 照片删除、人员删除、失联清理、重复处置（编排 + 预览 + 审计） |
| `application/use_cases/`（协议文件） | 对应 UseCase Protocol |
| `presentation/views/main_window.py` + `ui_text.py` | 工具栏「删除所选」+ 确认对话框（级联预览 + 磁盘文件不动明示） |
| `presentation/views/person_management_dialog.py`（新建）+ duplicate_report_dialog.py | 人员删除入口；重复报告「处置重复」按钮（keep-earliest 预览确认） |
| `main.py` + scan service | `prune-missing` 子命令（默认 dry-run，`--execute` 执行）；重扫内容变更更新元数据（PhotoRepository 协议扩 `update_metadata`） |
| `tests/` | 级联矩阵 / 幂等 / 批量 / 预览计数 / 对账 / 重复处置 / CLI 全套 |
| 文档链 | CHANGELOG `[2.4.0]` + 用户指南删除章节 + PROJECT_STATUS + 版本链 bump |

## §4 不变量（必选约束）

1. **磁盘零触碰**——任何删除路径不得触碰照片原文件、归档产物、缩略图缓存之外的任何用户文件（缩略图缓存属可再生副产物，同样不动）；
2. **级联由 SQLite FK 保证**——服务层不手写级联 DELETE（防与 FK 双轨漂移）；
3. **契约只增不改**——既有方法签名、Schema、导入/扫描/归档/导出行为零变化；
4. **InMemory 替身不模拟级联**——级联语义的唯一裁判是真实 SQLite 集成测试（与 ADR-029 的替身可实现性判定同源）；
5. **确定性**——keep-earliest 决胜、列表排序、批量结果全部确定（F9）；
6. **全量测试不减**——既有 672 用例绿是每阶段提交前置门。

## §5 风险与缓解

| 风险 | 缓解 |
|---|---|
| 数据破坏面大 | 硬删除 + 确认流（级联计数预览）+ 审计日志 + Phase B 备份兜底（J6 实证恢复） |
| 级联语义误用（InMemory 下"看似没级联"） | §4.4——级联测试专属真实 SQLite；用例级 InMemory 测试只断言本聚合行为 |
| 失联清理误删（移动盘未挂载） | D5 显式入口 + dry-run 默认 + 路径列表全量展示 |
| macOS CI 段错误复发（LIMIT-006） | 新增测试不含大目录压力扫描形态 |

## §6 完成标准（= roadmap Phase E 验收原文）

1. 删除照片后库与磁盘状态符合本 ADR 语义且可审计；
2. 对账重扫不误删不漏判；
3. 全量测试不减（≥ 672 + 新增全绿）。

发版收口：v2.4.0（CI 三平台绿 → tag → release → body）。
