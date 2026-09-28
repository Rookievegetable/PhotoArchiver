# Stage 4.1 — Freeze Remediation 独立复审报告

- **复审对象**：`D:\work\PhotoArchiver`，HEAD `2823d1c7ceaab09c38d39b9a80e1e724839cfa17`（`main`，2026-09-28 01:44:20 +0800，`fix: resolve business baseline freeze blockers`）
- **复审输入（全部视为待验证材料）**：`Stage4_FinalAudit.md`、`Stage1_BusinessFacts.md`、`Stage1_Handoff.md`、`Stage2_BusinessRules.md`、`Stage2_Handoff.md`、`Stage3_BusinessDiagrams.md`
- **复审日期**：2026-09-28
- **权威事实源**：当前工作区 HEAD 的源码 / migration / 测试 / 实时 SQLite schema；Git 历史仅用于对照 `b3b8685`（Stage 1–3 声明的基线）
- **项目改动**：**零改动**。复审前后 `git status --porcelain` 完全一致（仅存量未跟踪文件 `docs/development/evidence/stage-f-acceptance-review.md`）。临时校验脚本与一次性探针写在 `C:\Users\Public\PhotoArchiverAudit\`（仓库外），探针库写在 `%TEMP%`，未触碰仓库文件、产品数据库、测试或业务文档

---

## 1. 审计范围与方法

| # | 复审核查面 | 方法 |
|---|---|---|
| 1 | 原 5 个 FREEZE 阻断项（BLK-1/2/3/4/5） | 逐项对照当前源码 / migration / 测试；能执行的用真库执行 |
| 2 | `2823d1c` 的 27 个改动文件 | `git show --stat` / 逐文件读取当前实现（非只看 diff 文本） |
| 3 | migration 008 schema / 回填 / 索引 / FK | 真库升级（alembic head）+ `PRAGMA table_info` / `foreign_key_list` / `sqlite_master` 实测 |
| 4 | BLK-1 四项验收口径 | 自建一次性真库探针（`probe_blk1.py`）：同名不同人 / 改名 / 存量回退 / counter 同口径 / `ON DELETE SET NULL` |
| 5 | D-1 / D-2 端到端 | 真库探针：`review → approval(带身份) → planner`；`suggest_pairings` 三点边界（0.39/0.40/0.41）实跑 |
| 6 | Stage 1–3 全部 `文件.py:行号` 引用 | 机械化校验（仓库外脚本 `cite_check.ps1`：文件名存在性 + 行号越界）+ 关键引用逐条人工复核 |
| 7 | 测试与证据 | 实际运行测试（真 SQLite / 真 alembic 集成用例）+ 逐条检查断言是否覆盖**行为**而非字段类型 |
| 8 | 回归面 | 改动模块的全部调用方（`.confidence` 读取点、`has_successful_for_person` 调用点、review DTO/导出链）逐点核查 |

**未覆盖（明确声明）**：未运行 GUI 手工走查（无 runtime UI walkthrough）；未做 10k 级 `archive_records` 的 migration 性能实测。（完整测试套件已实跑复现，见 §10.1/§10.4。）

---

## 2. 使用证据清单

| 类型 | 具体证据 |
|---|---|
| 当前实现（HEAD） | `alembic/versions/008_archive_identity_and_confidence.py`（164 行全读）；`domain/entities/archive.py:39-60`；`domain/entities/recognition.py:34-58`；`domain/services/pairing.py:1-155`；`domain/repositories/archive_record_repository.py:29-45`；`domain/repositories/recognition_repository.py:125-140`；`infrastructure/database/sqlite_archive_record_repository.py:28-138`；`sqlite_recognition_repository.py:181-255,282-330`；`sqlite_mappers.py:142-173`；`application/services/archive_planner.py:199-225`；`archive_executor.py:325-343`；`pairing_workbench_service.py:59-68,105-137,276-375`；`review_recognition_service.py:51-220`；`use_cases/review_recognition.py`；`dtos/export.py:49-62`；`ports/exporter.py:36`；三道 exporter；`presentation/controllers/review_controller.py:93-138`；`views/review_dialog.py:96-383`；`ui_text.py:234-256`；`controllers/workspace_controller.py:42-64`；`controllers/cluster_faces_controller.py:41-58`；`services/confirm_import_service.py:50-151`；`models: sqlite_cluster_assignment_repository.py:92-117` |
| 测试（当前实现） | `tests/unit/application/test_freeze_blockers.py`（13 项，全读）；`tests/unit/domain/test_stage_e_pairing_domain.py:138-186`；`tests/integration/database/test_alembic_migrations.py:268-332`；`tests/integration/test_upgrade_integrity.py:124-184`；`tests/unit/presentation/test_review_dialog_*.py`；`tests/unit/application/test_run_recognition_service.py:43-140`；`tests/unit/application/test_archive_executor.py:33-120` |
| 实跑结果 | `pytest tests/unit/application/test_freeze_blockers.py tests/integration/database/test_alembic_migrations.py` → **24 passed**；`pytest`（review 两对话框 + review controller + review service + archive planner + archive executor + upgrade integrity）→ **61 passed**；**全量 `pytest` → 1310 passed, 6 skipped（233.25s）**；`probe_blk1.py`（真库 schema 实测 + BLK-1 / BLK-5 / D-1 / D-2 全场景输出）；`probe2_d1_export.py`（无身份批准不进计划 + 三 exporter 导出 NULL confidence 行不报错） |
| Migration 实测 schema | `alembic_version=008_archive_identity_and_confidence`；`archive_records` 列 = `id,photo_id,target_*,status,archived_at,error,person_id`；FK = `photos(photo_id) CASCADE` + `people(person_id) SET NULL`；`recognition_results.confidence.notnull=0`；`idx_archive_records_person_id` 存在；`idx_recognition_results_photo_id` / `_person_id` 均在 |
| 文档机械校验 | `cite_check.ps1` 输出：Stage 1–3 三份主文档**无越界行号、无不存在文件**（唯余 3 处为省略写法 `004_...py:24` / `006_...py:19` / `003_...py:67`，其指向的 migration 文件真实存在且行号在界内，已逐条人工核对，见 §5.2） |
| Git | `git show 2823d1c --stat`、`git show b3b8685:<file>`（对照基线行号）、`git grep`、`git status --porcelain`（前后一致） |

---

## 3. BLK-1 复核 — archive dedup identity（结论：**关闭**，含一处需登记的残余语义）

### 3.1 `archive_records.person_id` 是否真实存在 + FK / index / migration

| 声明 | 证据（当前 HEAD） | 结论 |
|---|---|---|
| 新增列 | `alembic/versions/008_archive_identity_and_confidence.py:48-55`：`ALTER TABLE archive_records ADD COLUMN person_id TEXT REFERENCES people(id) ON DELETE SET NULL` | ✅ 真实 |
| 新增索引 | 同文件 `:56-59` `CREATE INDEX IF NOT EXISTS idx_archive_records_person_id` | ✅ |
| 实测 schema | 真库 `PRAGMA table_info(archive_records)` 末列 = `person_id`；`PRAGMA foreign_key_list` = `(photos, photo_id) ON DELETE CASCADE` + `(people, person_id) ON DELETE SET NULL`；`sqlite_master` 含 `idx_archive_records_person_id` | ✅ FK/索引**真实生效**（非纯文本声明） |
| 实体 / mapper | `domain/entities/archive.py:59-60`（`person_id: UUID \| None = None`）；`infrastructure/database/sqlite_mappers.py:171-172`（NULL 安全）；`sqlite_archive_record_repository.add` `:42-72` 的 INSERT/ON CONFLICT 均写 `person_id` | ✅ 读写双向落地 |

### 3.2 backfill 是否安全

`008:63-76`：

```sql
UPDATE archive_records SET person_id = (
  SELECT p.id FROM people p WHERE p.name = archive_records.target_person_name
     AND (SELECT COUNT(*) FROM people p2 WHERE p2.name = archive_records.target_person_name) = 1)
WHERE person_id IS NULL
```

- 只碰 `person_id IS NULL` 行 → 不覆盖任何已有身份 ✅
- 只用「姓名**唯一**命中」→ 重名（多命中）子查询返回 NULL，保持 `person_id IS NULL` ✅（宁可留空也不猜身份）
- 真库验证：`tests/integration/database/test_alembic_migrations.py:291-332`（建 007 库 → 插「唯一人员 1 人 / 同名 2 人」→ upgrade head → 断言唯一命中回填、重名留 `None`）。**实跑通过**。
- 附加证据：`tests/integration/test_upgrade_integrity.py:133-145`（003 → head 全表逐行快照对比）覆盖 008 的表重建，**实跑通过**。

### 3.3 dedup 是否真正优先使用 stable `person_id`

`sqlite_archive_record_repository.py:107-138`：

```sql
SELECT 1 FROM archive_records
 WHERE photo_id = ?
   AND status IN ('archived','skipped','renamed','overwritten')
   AND ( (? IS NOT NULL AND person_id = ?)
         OR (person_id IS NULL AND target_person_name = ?) )
 LIMIT 1
```

调用链：`application/services/archive_planner.py:203-210`（`has_successful_for_person(photo_id, person_id, person_name)`）；协议签名 `domain/repositories/archive_record_repository.py:29-34`。

真库探针（`probe_blk1.py`，非 fake）：

```
[BLK-1.1] 同名「张伟」A/B 各持同一照片 APPROVED，未归档时：planner_items=2 counter=2
[BLK-1.1] A 归档成功后：planned person_ids=[B]        ← A 被抑制、B 不被误抑制
[BLK-1.1] counter=1
[BLK-1.2] A 改名后重跑：planned=0 skipped=1           ← 改名不重复归档
[BLK-1.2] 新建同名（改名后姓名）C：planned=1 (C)      ← 同名不同人不被误抑制
```

→ **「同名人员互相吞掉归档」与「改名后重复归档」两个 Stage 4 认定的用户可见错误在真库上均已消除**，且去重**优先按 `person_id`**（仅在存量 `person_id IS NULL` 行上回退姓名）。

### 3.4 workspace counter 与 planner 是否完全同口径

`sqlite_recognition_repository.py:220-241`（`read_workspace_counts` 的 `archivable_count`）使用与 planner 相同的谓词：

```sql
AND NOT EXISTS (SELECT 1 FROM archive_records a
                 WHERE a.photo_id = r.photo_id
                   AND a.status IN ('archived','skipped','renamed','overwritten')
                   AND ( a.person_id = r.person_id
                         OR (a.person_id IS NULL AND a.target_person_name = person.name) ))
```

真库探针：未归档 `counter=2`（planner 2 项）；A 归档后 `counter=1`（planner 1 项）；A 改名 + 新增 C 后 `counter=2`（planner 2 项）——**逐点一致**，不再出现 Stage 4 §4.2 的「概览计数与 planner 脱节」。✅

### 3.5 executor 是否真正持久化 `person_id`

- `application/dtos/archive.py:28` `ArchivePlanItem.person_id: UUID`
- `archive_planner.py:219-225` 构造 item 时带 `person_id=person_id`
- `archive_executor.py:325-343` `_make_planned_record`：`person_id=item.person_id`（`:342`）；PLANNED 与终态两次 `add(record)`（`:93-101`）写同一实体 → 终态行保留身份
- repository upsert 写列含 `person_id`（`:42-58`）、mapper 回读一致

⚠️ **证据缺口（非阻断）**：`tests/unit/application/test_archive_executor.py:33-45` 虽构造带 `person_id` 的 plan item，但**无任何断言检查落库记录的 `person_id`**；`test_freeze_blockers.py` 的 `_record()`（`:69-81`）直接写 repository，**未经过 executor**。该验收条目前为「代码已验证、测试未覆盖」（§10.3 GAP-1）。

### 3.6 四个关键语义问题（逐条回答）

| 问题 | 复核结果 |
|---|---|
| 两个同名 Person 是否可以分别归档 | ✅ 可以。A 的成功归档不再抑制 B（3.3 真库证据）；`read_workspace_counts` 同样把两人分别计入（3.4） |
| Person 改名是否不会重新触发同一照片的错误重复归档 | ✅ 不会。改名后 `person_id` 命中历史行 → planner `skipped`（3.3 真库证据 + `test_freeze_blockers.py:109-122,174-194`） |
| ambiguous-name historical rows 的 fallback 是否明确且不产生错误身份归属 | ✅ 回退**明确**（`008:16-18`、协议 docstring `:37-41`、repo docstring `:110-118`）；**不猜身份**（回填仅唯一命中时执行，重名留 NULL）。代价见 3.7 |
| migration 008 是否恢复原表必要的 indexes / constraints | ✅ `recognition_results` 重建后按 002 定义重建两个命名索引（`008:108-117`），两条 FK（`photos CASCADE` / `people SET NULL`）与列序、`id TEXT PRIMARY KEY`、`photo_id TEXT NOT NULL`、`status TEXT NOT NULL`、`created_at TEXT NOT NULL` 与 `002:85-96` 逐字段一致；`git grep "recognition_results" -- alembic` 确认该表**不存在其它约束/索引**（DDL 唯一来源为 002，仅 008 重建）；`archive_records` 原 `idx_archive_records_photo_id` / `idx_archive_records_status` 未受影响，并由 `tests/integration/database/test_alembic_migrations.py:129-137` 全索引断言守护（实跑通过） |

### 3.7 ⚠️ 残余：`person_id → NULL → name fallback` 的两条现实路径（本项复审重点）

复审明确要求回答「是否可能重新引入原来的身份歧义」。**结论：在两条有界路径上姓名回退确实仍然存在，且已在真库复现——但它不是新引入的错误，而是设计上明示的取舍。**

| 路径 | 真库证据（`probe_blk1.py`） | 业务后果 | 定级 |
|---|---|---|---|
| **P1 存量重名行**（008 无法唯一回填） | `[BLK-1.4] ambiguous legacy NULL row: planned=0 skipped=2`（两个同名「李娜」都被该 NULL 行抑制） | 升级前既有的行为被**原样保留**（「升级不退化」的明确取舍）。仅在库中已存在重名人员**且**存在无法归因的历史归档行时出现 | **已知限制**（与 ADV-6 duplicate-name policy 同源）。Stage 1/2 应明写「重名场景仍沿用旧语义」 |
| **P2 `ON DELETE SET NULL` 孤儿行** | 删「赵六」→ 该行 `person_id` 变 `NULL`（仍保留 `target_person_name`）→ 新建**另一个**同名「赵六」并批准同一照片 → `planned=0 skipped=1`（被孤儿行按姓名抑制） | 「同一照片可归档到多个人员目录」在**删人 + 同名重建**组合下仍可能落空（静默跳过，仅 `logger.debug`） | **已知限制 / 待裁决**：删除人员并不撤销历史归档事实（归档产物仍在盘上），故按姓名抑制**既可能是保护、也可能是错误抑制**，取决于业务定义。Stage 1/2/3 与 migration 008 文档均**未**记录此组合 |

**对 FREEZE 的影响**：BLK-1 的原始验收面（同名不同人互不抑制；改名不重复归档；去重键改为稳定 `person_id`；counter 同口径）全部成立且可复算。P1/P2 属「有界、可解释、需登记」的残余，**不构成本次 Freeze 阻断**（§12 KL-1），但文档必须明示，否则会给读者「身份去重已 100% 覆盖」的错误印象。

---

## 4. BLK-5 复核 — positional pairing confidence（结论：**关闭**；UI/导出 NULL 路径无测试）

### 4.1 三态语义：`ordered_suggestion` / `manual` → NULL；`sample_match` → 真实余弦

| 环节 | 证据 | 结论 |
|---|---|---|
| 实体 | `domain/entities/recognition.py:34-38` 三态 docstring；`:55-56` **仅在有值时**校验 `0.0 <= c <= 1.0` | ✅ `None` 合法、有值仍校验 |
| 持久化 | `infrastructure/database/sqlite_recognition_repository.py:31-56`（`add` 写 `result.confidence`，None → SQL NULL）；`sqlite_mappers.py:134` 原样回读 | ✅ `NULL` 与 `0.0` 在库内可区分（探针实测 `[(None,'approved'), (0.0,'pending')]`） |
| 配对确认写入 | `application/services/pairing_workbench_service.py:59-68` `clamp_unit`；`:321-323` `confidence = clamp_unit(assignment.score) if assignment.score is not None else None`；`:338-343` 写入 compat 行 | ✅ `ordered_suggestion` / `manual` 的 assignment `score` 为 `None`（`domain/services/pairing.py:140-145` 显式 `score=None`；`cluster_assignment.py:82` 默认 `None`；`assign_person` 构造 assignment 时未设 score）→ 落库 **NULL**，不再写 `0.0` |
| 有相似度证据 | `pairing.py:106-119` 命中的建议带真实余弦 `score` → `clamp_unit(score)` 落库 | ✅ |
| migration | `008:78-117` 把 `recognition_results.confidence` 由 `NOT NULL` 放宽为可空（重建表 + 重建命名索引） | ✅ 实测 `notnull=0` |
| 导出 DTO | `application/dtos/export.py:49-62`（`confidence: float \| None` 并注明「不得统一填 0」）；`ports/exporter.py:36` 原本已是 `float \| None` | ✅ 语义保留 |
| 导出实现 | `csv_exporter.py:52-75` / `excel_exporter.py:60-83` → `_spreadsheet_safety.sanitize_spreadsheet_cell`（`:40-46` 非 str 原样返回，None 安全）；`html_exporter.py:115-118` `None → ""` | ✅ 空单元格，不是 `0.0`、也不是字面量 `None`；探针 `probe2_d1_export.py` 对 NULL confidence 行**实跑三种导出全部成功** |
| UI | `views/review_dialog.py:96-111` `confidence_band(None) → REVIEW_CONFIDENCE_NO_EVIDENCE`；`:250-256` 行文本三分支；`ui_text.py:255` 文案「无相似度证据」 | ✅ 不再把「无证据」渲染成 `0.00` |

### 4.2 「没有相似度证据时不会伪装成 0.0」/「range validation 仍存在」

- `probe_blk1.py`：`[BLK-5] persisted confidences=[(None, 'approved'), (0.0, 'pending')]` → 两者库内可区分；`[BLK-5] NULL-confidence APPROVED archivable: planned=1` → 归档不因置信度为空而丢项。
- `tests/unit/application/test_freeze_blockers.py:200-204`（`None is not 0.0`）、`:223-232`（`1.5` / `-0.1` 仍抛 `ValidationError`）。
- 结论：**通过**。

### 4.3 compatibility chain 是否被破坏

- 全仓 `.confidence` 读取点枚举（`git grep "\.confidence" -- src`）：`export_service.py:232,284`、`sqlite_mappers.py:134`、`review_dialog.py:252-254` 是仅有的 `RecognitionResult.confidence` 消费点；其余命中均属 `FaceBox.confidence` / `FaceClusterMember.confidence`（不同对象）。**无任何调用方假定非空**（无 `:.2f` 直格式化、无算术、无比较）。✅
- `run_recognition_service.py:125-131` 写兼容行时 `confidence=` 取检测框得分（float），未受 DTO 变更影响。✅

### 4.4 测试是否覆盖行为而非只覆盖字段类型

覆盖到的：落库往返（`:207-220`）、实体校验（`:223-232`）、归档不受 NULL 影响（`:235-255`）、配对阈值三点（`test_stage_e_pairing_domain.py:141-185`）、schema 可空（`test_alembic_migrations.py:275-289`）。

**未覆盖（GAP-2）**：
- `review_dialog.confidence_band(None)` / 行文本「无相似度证据」渲染——`tests/unit/presentation/test_review_dialog_review_board.py:43-51` 的参数矩阵只有 `0.95/0.90/0.80/0.65/0.10`，`_result()`（`:29-30`）签名要求 `float`，**`None` 从未进入 UI 测试**。
- 导出侧 NULL confidence 落单元格的断言——`tests/unit/infrastructure/test_html_exporter.py:102-112` 覆盖 `match_confidence=None` 的 HTML 渲染（既有），但 CSV/Excel 与 `ExportService` 组装链**无 NULL 用例**（本次复审用探针补证，非仓库测试）。

---

## 5. BLK-2 / BLK-3 / BLK-4 复核 — evidence traceability

### 5.1 BLK-2（不存在的文件 / 虚构机制）——**关闭**

- 机械校验 + `Select-String`：Stage 1–3 与两份 Handoff 中**已无** `batch_import_flow_service.py`、`cluster_run_controller.py`（仅 Stage 3 头部修订说明第 5 行提到被删除的旧名，属记录性文字）。
- 替换后的引用**真实且准确**（逐条回查当前 HEAD）：
  - `confirm_import_service.py:50-109`（`execute` 起于 `:50`；内容与「create / merge_existing 分流、单 UoW 写 people」一致），`:96-98` 确为 UoW **之外**的 `set_batch_status(BATCH_STATUS_CONFIRMED, confirmed_at=...)` → Stage 3 `:791/:809/:829` 的「批次标签在事务外写（非原子）」结论**与真实代码一致**。
  - `cluster_faces_controller.py` 存在；`Stage1:151` 引 `:41-58` = `start_cluster`（`def` 在 `:41`，单飞/用例缺失拒绝在 `:49-54`）✅
  - `Stage2:96`（`parse_import_draft_service.py:79` / `confirm_import_service.py:96-98`）、`Stage2:103/:112/:113/:115/:119/:120` 引用的 `confirm_import_service.py` 行段全部落在界内且语义相符（该文件本次未被改动，行号天然有效）。✅

### 5.2 机械引用校验（全量 6 份审计输入文档）

- Stage 1–3 主文档：**无越界、无缺失文件**。唯余 3 处为省略写法并已人工核对：
  - `Stage1:315` 引 `004_...py:24`、`006_...py:19` → `alembic/versions/004_recognition_runs_and_observations.py`（其 docstring 述追加型）、`006_face_clusters.py` 均存在，行号在界内；
  - `Stage1:535` 引 `003_...py:67` → 实测 `alembic/versions/003_import_batches_and_roster.py:67` 正是 `ALTER TABLE people ADD COLUMN source_batch_id TEXT`（**无 REFERENCES**），与论断逐字相符 ✅
  - `Stage1:223` 的 `import_batch.py:22-44` 已由越界 1 行修正为准确范围（Stage 4 ADV-7 关闭）。
- Stage 4 报告中残留的越界/虚构引用（`:555`、`batch_import_flow_service.py`、`import_batch.py:73`）出现在**历史审计报告正文**中，属被复审对象的记录，不作为当前交付物缺陷。

### 5.3 BLK-4（`update_assignment` 字段描述）——**关闭**

| 声明 | 实测（当前 HEAD） | 结论 |
|---|---|---|
| 实际改写 `status` / `score` / `sort_snapshot` / `confirmed_at` | `infrastructure/database/sqlite_cluster_assignment_repository.py:92-117`（docstring `:93` + UPDATE 列 `:98-101`） | ✅ Stage 3 `:788` 现描述与代码**逐字段一致**，引用行段 `:92-117` 亦准确 |
| 原称只更新 `updated_at` / `assigned_by` | 迁移 007 建表列 = `id, cluster_id, person_id, status, source, score, sort_snapshot, error, created_at, confirmed_at`，**两列不存在** | ✅ 文档已删除该错误描述；§6.3 状态机图与 §7 表格不再自相矛盾 |

### 5.4 BLK-3（越界行号）——**未完全关闭**（本次复审核心发现，见 §11 BLK-3R）

- ✅ 越界问题本身已消除：`pairing_workbench_service.py:530-555`、`:505-528`、`workspace_controller.py:298-315` 均在文档中消失；`workspace_controller.py:42-64`（`match_guidance`）与文件实际 `:42-64` 完全吻合（该文件本次未改动）。
- ❌ 但**修正后的行号只在「修复前的那个提交」上成立**：见 §11 BLK-3R。

---

## 6. D-1 复核 — 人工结果为最终结果（结论：**代码实现成立**；Stage 文档尚未与实现重新一致）

业务决定：`自动结果 → 用户手动修改/指定人员 → 用户确认 → 最终身份 → 后续归档`。

### 6.1 逐条验收

| 验收点 | 证据（当前 HEAD） | 结论 |
|---|---|---|
| `update_status` 的 `person_id` 能正确记录人工决定 | `infrastructure/database/sqlite_recognition_repository.py:298-330`：`person_id is None` → 只写 `status`；否则 `UPDATE ... SET status = ?, person_id = ? WHERE id = ?`；协议与 docstring 同步 `domain/repositories/recognition_repository.py:125-140` | ✅ |
| 服务层把人工身份写入并保持内存/库一致 | `application/services/review_recognition_service.py:51-71`（`approve(result_id, person_id=None)`）、`:141-146`（`result.approve()` 后 `result.person_id = person_id`）、`:174-191`（`_persist_status` 传 `person_id`）；用例契约 `use_cases/review_recognition.py:16-41` | ✅ |
| Review UI 的 person picker 支持人工最终决定 | `views/review_dialog.py:162-171`（`_identity_combo`，首项为「（未指定）」`data=None`）、`:319-322` `_selected_identity()`；控制器 `controllers/review_controller.py:93-107`（`list_persons()`）；文案 `ui_text.py:246-256` | ✅ 存在真实接线（构造期填充；读侧缺失时降级为空 picker，见 `:304-317`） |
| 不选择人员时**不会静默**制造不可归档结果 | `review_dialog.py:324-338` `_confirm_without_identity()`（`QMessageBox.question`，默认 No）；`:344-346`（所选批准）、`:379-381`（全部批准）两条路径都先弹告警；文案 `ui_text.py:251-253` 明确「不会进入归档计划」 | ✅ 显式告知，且**不阻断**人工决定（符合 D-1「人工结果为最终结果」） |
| 真库端到端：批准携带身份后**真正进入归档计划** | `probe_blk1.py`：`[D-1] approve(person) -> stored.person_id=<P> planned=1`；反向：`probe2_d1_export.py`：`approved-without-identity appears in plan: False / plan size: 0` | ✅ |
| bulk approval 不覆盖单行人工决定 | `review_recognition_service.py:193-220` `_bulk_transition`：仅当行上 `person_id is None` 时才套用默认身份；`probe_blk1.py`：`[D-1] bulk_approve(default) on row with identity → person_id=<行上已有人员>`；`test_freeze_blockers.py:320-340` | ✅ |
| rerun 不静默覆盖已人工确定的结果 | `run_recognition_service.py:125` 守卫 `if in_scope and not self._recognition_repository.list_by_photo(result.photo_id)` → 照片已有**任意**行（含人工 APPROVED）即不再写兼容行 | ✅ 代码成立；**但测试主张不成立**（§10.3 GAP-3） |
| archive planner 实际消费人工最终结果 | `archive_planner.py:116`（`list_approved_by_person(person_id)`）+ `:203-210`（身份去重）；`sqlite_recognition_repository.py:266-280` 的 SQL `WHERE person_id = ? AND status = 'approved'` | ✅ |

### 6.2 「识别证据」与「人工最终业务决定」是否被区分

- **识别证据**：`confidence`（float）= 相似度证据；`None` = 无证据（BLK-5 三态）。识别期自动产生的兼容行 `person_id` 仍恒为 `NULL`（`person_embeddings` 无生产者，未变）。
- **人工最终业务决定**：批准时由人工指定的 `person_id`（`update_status` 第三参）+ 配对工作台指派。二者在库中仍是同一列，但**写入路径语义不同**：自动路径从不写身份（`run_recognition_service.py:128-131` 不传 `person_id`），身份只能来自人工（审核指定 / 配对确认）。
- 因此 D-1 之后，「可归档集合」= 「带人工身份的 APPROVED 行」，与「识别证据」完全解耦。✅

### 6.3 ⚠️ Stage 文档侧的 D-1 不一致（阻断项，见 §14 BLK-D1D）

修复引入了 D-1，但 Stage 1/2/3 中**多处仍在断言修复前的行为**，且与同一文档中新增的「Stage 4 D-1 修复」条目自相矛盾：

| 文档:行 | 现文本（要点） | 与当前实现的关系 |
|---|---|---|
| `Stage3:149`（§2 断点④） | 「`list_approved_by_person` 要求 `person_id = ?`，而①使新写兼容行 `person_id` 恒 NULL、**审核中心只改 `status` 不改 `person_id`** → 只有配对确认产生的 APPROVED 才真正进归档」 | ❌ 现已可携带身份（`update_status(..., person_id)`），结论不再普遍成立 |
| `Stage3:371` | 「**审核中心的「通过」不产生可归档照片**：`update_status` 只写 `status` 列……把照片变成可归档的人工动作**只有配对确认**一条」 | ❌ 同上；与 `Stage3:796`（新增的 D-1 行）直接冲突 |
| `Stage3:784`（§7 关键节点表首行） | 「① 审核通过 `review_recognition_service.py:51-58,118-131`（**只写 status 列**）」 | ❌ 与 `:796` 同表新增行冲突 |
| `Stage3:836`（§8-B12） | 「`update_status` 只写 `status` 列……审核中心通过的行（`person_id` 恒 NULL）**永远不进归档计划**」 | ❌ 与实现冲突（选择身份后即进计划） |
| `Stage3:890`（§10.2 建议主线） | 「审核中心形同**只改状态的空转闸门**……需要决定……还是让审核中心具备写 `person_id` 的能力」 | ❌ 该裁决已由 D-1 落地（`Stage3:796` 自陈），此处仍列为未决 |
| `Stage2:316`（§4 人工边界表） | 「审核中心 通过/拒绝 …… `update_status`（**仅 status**）」 | ❌ 与 `update_status` 新签名不符 |
| `Stage2:254`（PR-20） | 「兼容投影……`confidence=clamp(score,0,1)`」 | ❌ 与 BLK-5 三态不符（无证据时应为 NULL）；同文档 `Stage1:85` 已改、`Stage2` 未改 |
| `Stage1:471` / `Stage1_Handoff:19` | 「新识别兼容行 `person_id` 恒 NULL，**身份只能来自配对工作台**」 | ❌ 审核中心现亦可写入身份 |
| `Stage2_Handoff:76` | 「身份补写**只能靠配对**」 | ❌ 同上 |

> 注：`Stage2:388` 已补「（或人工审核）」，说明回填是真做了但**不成体系**；上表各项须逐条收口。

**D-1 结论**：实现层完全满足 D-1，并有真库证据；**文档层未与实现重新一致**，构成 Freeze 阻断（§14 BLK-D1D）。

---

## 7. D-2 复核 — threshold `>= 0.40`（结论：**实现/注释/测试一致**；**Stage 1 与两份 Handoff 不一致**）

### 7.1 实现行为（真库外纯域函数实跑）

`domain/services/pairing.py:92-119`：`best_score: float | None = None`；`if score is None or score < sample_match_threshold: continue`；`if best_score is None or score > best_score:` → 命中边界 = `>= threshold`。

`probe_blk1.py` 实跑结果（`suggest_pairings` 真实调用，阈值 0.40）：

```
[D-2] cos=0.39 -> sources=['ordered_suggestion'] scores=[None]      ← 不命中 sample_match（回落规则③）
[D-2] cos=0.40 -> sources=['sample_match']       scores=[0.4]       ← 恰等命中
[D-2] cos=0.41 -> sources=['sample_match']       scores=[0.41]      ← 命中
```

边界语义与 `pairing.py` 模块 docstring `:5-8`（「`>= sample_match_threshold`（0.40，F 校准；**恰等于阈值即命中**，Stage 4 D-2 裁决）」）完全一致。✅

### 7.2 五个面的一致性

| 面 | 位置 | 状态 |
|---|---|---|
| 实现 | `pairing.py:109-112` | ✅ `>=` |
| docstring | `pairing.py:5-8` | ✅ `>=`，并写明「恰等于阈值即命中」 |
| tests | `tests/unit/domain/test_stage_e_pairing_domain.py:141-155`（`== 0.40` 命中）、`:158-169`（0.39 不命中）、`:172-185`（0.41 命中） | ✅ 三点边界，断言 `source`/`score` **行为**而非字段类型 |
| Stage 2 | `Stage2:233`（PR-03 已注明 `>=`）、`Stage2:398`（U1 改为「已裁决+TESTED」） | ✅ 已收口 |
| Stage 3 | `Stage3:299/312/710/748` | ✅ 已收口（并解除原 `[INFER]`） |
| **Stage 1** | `Stage1:69`：「规则①：……最大余弦 **> 0.40** → `sample_match`」 | ❌ **未收口**（仍是严格大于） |
| **Stage 1 Handoff** | `Stage1_Handoff:16`：「①已确认样本 max 余弦 **>0.40** → `sample_match`」 | ❌ 未收口 |
| **Stage 2 Handoff** | `Stage2_Handoff:16`：「①样本匹配 max 余弦 **严格 >0.40**」；`Stage2_Handoff:68` 仍把「代码严格 `> 0.40` … 属未裁决矛盾」列为**未确认项 #1** | ❌ 未收口，且与已裁决结论直接冲突 |

### 7.3 结论

- 「实现 / docstring / tests」三点完全一致，边界是真行为（三点边界实跑 + 单测双证）。✅
- `>=` 与 `Stage 2`、`Stage 3` 主文档一致。✅
- 但复审要求「**Stage 1 / Stage 2 / Stage 3 全部使用相同边界语义**」——**Stage 1 主文档与两份 Handoff 仍写 `> 0.40`**，且 `Stage2_Handoff` 仍把它列成未裁决项。→ 不满足该验收口径，构成 Freeze 阻断（§14 BLK-D2D）。

---

## 8. Regression Review（`2823d1c` 是否引入新回归）

| # | 复审要求 | 核查方法与证据 | 结论 |
|---|---|---|---|
| 1 | migration 008 是否破坏原有 indexes / constraints | 真库 `PRAGMA` + `sqlite_master` 全量比对 002 定义；`git grep "recognition_results" -- alembic` 确认该表 DDL 唯一来源；`test_migration_upgrade_creates_all_indexes`（21 个命名索引）与 `test_schema_version_consistent_after_upgrade` 实跑通过；`test_upgrade_preserves_all_existing_data`（003→head 逐行）实跑通过 | ✅ 无破坏。`recognition_results` 两索引 + 两 FK + 列集/列序与 002 逐字段一致；`archive_records` 只增列增索引 |
| 2 | `confidence` 由 non-null 改 nullable 后旧调用方是否兼容 | 全仓 `.confidence` 消费点枚举（§4.3）：仅 `export_service` / `sqlite_mappers` / `review_dialog` 三处读 `RecognitionResult.confidence`，全部 NULL 安全；导出三实现在 NULL 行实跑成功；`add_many` 预过滤未改 | ✅ 兼容。无一处假定非空 |
| 3 | Review UI / DTO / export 是否出现类型或状态回归 | `review_dialog` 两测试文件 + `test_review_controller` 实跑通过（61 passed 的一部分）；两个对话框测试的 `bulk_approve` 断言已按新签名 `(ids, None)` 更新；`ExportMatchRow.confidence: float \| None`；HTML `None → ""` | ⚠️ 无功能回归，但发现**一处文案回归**：`review_dialog.py:333` 在「按所选批准但未指定身份」时复用了 `REVIEW_APPROVE_ALL_CONFIRM_TITLE`（=「确认全部通过」，`ui_text.py:234`）作为告警标题——只批准所选行却弹「全部通过」标题（§12 KL-2，低） |
| 4 | rerun / history 行为是否被意外改变 | 本次提交**未触碰** `run_recognition_service.py`、`cluster_faces_service.py`、`sqlite_recognition_run_repository.py`、`face_observation*`（`git show 2823d1c --stat` 27 文件清单核对）；`parameters` 永不改写逻辑未变 | ✅ 未改变 |
| 5 | archive planner / workspace counter 行为变化 | planner 变化仅在 `:203-210`（去重键）+ item 带身份；planner 的「单次 plan 调用内集合」`seen_person_photo_pairs`（`:108,126-132`）与成功态集合 `_ALREADY_ARCHIVED_STATES`（`:28-33`）**未变**；counter SQL 与 planner 同步改造并实测逐点一致；`DRY_RUN` 记录仍不拦重规划（探针 `[states] after DRY_RUN record: planned=1`，与 `find_by_photo` 语义一致） | ✅ 行为变化仅限 BLK-1 目标面，其余语义保持 |
| 6 | existing recognition compatibility chain 是否被破坏 | 兼容行仍只投影 `ordered[0]`（`run_recognition_service.py:125-131`）；守卫未变；配对三连写/三连回收未变（`pairing_workbench_service.py:276-375` 仅 confidence 表达式 + 注释变化）；APPROVED 行来源仍不可区分（无 source 列） | ✅ 未破坏（`Stage4 §14` 的可信基线逐条仍成立） |
| 7 | 旧调用方的签名兼容（`update_status` / `approve` / `bulk_approve` / `has_successful_for_person`） | 新参数均为**带默认值**的尾参（`person_id: UUID \| None = None`），旧位置调用不受影响；测试 fakes 已同步（`test_review_controller.py:26-50`、`test_archive_planner.py:88-96`）；`has_successful_for_person` 由 3 参变 3 参（第二参由 name 改 id，**唯一生产调用方已同步**，无其它调用点：`git grep` 仅 planner + 协议 + SQLite + 测试） | ✅ 兼容；注意该协议**不是**宽松兼容变更（第二参语义变更），但调用点仅一处且已同步 |

**回归总体结论**：未发现代码层新回归。唯一实际缺陷是 D-1 引发的文档/证据不一致（§6.3、§7.2、§11 BLK-3R）与一处 UI 文案误用。

---

## 9. Scope Review（Out-of-Scope 项的现状判断）

| 项 | 当前状态（HEAD） | 是否已构成新 Freeze Blocker |
|---|---|---|
| ADV-1 配对工作台六按钮不按状态使能 | `pairing_workbench_dialog` 未在本次提交中改动，行为不变 | 否（未阻断基线） |
| ADV-2 `recognition_results.person_id` 两种 NULL 语义混同 | **仍然存在**：识别期写入即 NULL vs 删人 SET NULL；D-1 未改变该事实（只是给审核提供了写入身份的路径）。`Stage3` 未显式登记 | 否（可追溯性弱化，非数据错误） |
| ADV-3 删照片 CASCADE 抹掉 APPROVED 行但 assignment 仍在 | 未在本次改动范围内 | 否（Stage 4 已定级中高但列建议项；未在本次复审观察到它对基线的新破坏） |
| ADV-4 重跑缩小范围无法撤销既有 PENDING | 未改动 | 否 |
| ADV-5 `cluster_person_assignments.error` 列空转 | `sqlite_cluster_assignment_repository.py:96-103` 仍不写 `error` | 否 |
| ADV-6 duplicate-name policy | BLK-1 修复**部分覆盖**（新建/正常路径按身份去重）；存量重名行与删人孤儿行仍回退姓名（§3.7 P1/P2） | 否（有界，需登记） |
| ADV-7 引用越界 1 行 | `Stage1:223` 已改为 `import_batch.py:22-44`（实测 `ImportBatch` 类范围 `:22-44`，文件 72 行） | **已关闭** |
| `person_embeddings` producer-less | 未变（`git grep "\.save(" -- src` 无生产者；`run_recognition_service.py:66` 仍读空表）→ 新兼容行 `person_id` 恒 NULL | 否（D-1 为其提供了人工出口；不改基线） |
| 未做 runtime UI walkthrough | 本次复审同样未做（静态 + 真库探针） | 否 |
| migration 008 大表 copy 性能风险 | `008:80-107` 对 `recognition_results` 走 RENAME + CREATE + `INSERT ... SELECT` + DROP，属整表复制；本次未实测大数据量 | 否（需在大库升级前评估；`archive_records` 侧为纯 `ADD COLUMN`，不复制） |

**Scope 结论**：ADV-* 均未升级为新的 Freeze Blocker；ADV-7 已关闭；ADV-6/ADV-2 被 §3.7 的残余语义部分重述。

---

## 10. 测试证据审查

### 10.1 本次复审实际执行的测试（真实 SQLite / 真实 alembic）

| 命令（等价） | 结果 |
|---|---|
| `pytest tests/unit/application/test_freeze_blockers.py tests/integration/database/test_alembic_migrations.py` | **24 passed** |
| `pytest`（review 两对话框 + review controller + review service + archive planner + archive executor + upgrade integrity） | **61 passed** |
| `pytest tests/unit/application tests/unit/domain tests/unit/architecture tests/unit/infrastructure tests/unit/workers tests/unit/scripts tests/integration` | **813 passed, 6 skipped**（178.91s） |
| `pytest`（全量套件，后台运行至完成） | **1310 passed, 6 skipped**（233.25s）——与 `2823d1c` 提交信息「全量 1310 passed / 6 skipped」**逐数字吻合** |

**真实 SQLite 使用情况（无 mock 替代）**：
- `test_freeze_blockers.py` 全部 13 项走 `build_sqlite_repositories(tmp_path / "db.sqlite3")`（`:92,134,153,178,209,239,271,304,326,349`）→ 真文件库、真 alembic schema、真 mapper。
- `test_alembic_migrations.py` 走真 `alembic.command.upgrade` + 原生 `sqlite3` PRAGMA 断言（`:275-332`），含 007→head 的**存量数据回填**场景。
- `test_upgrade_integrity.py` 走 003→head 的**全表逐行快照对比**。
- ❌ 未发现「只测 mock/fake 而无法证明真实数据库行为」的 BLK-1/BLK-5/D-1 关键用例：四项验收口径均有真库用例或真库断言。

### 10.2 BLK-1 四项验收口径的测试对应

| 验收口径 | 测试 | 是否行为级 |
|---|---|---|
| (1) 同名不同人不互相抑制 | `test_freeze_blockers.py:87-106`（真库 + repo 谓词）+ `:128-144`（真库 counter） | ✅ 行为级 |
| (2) 改名后不重复归档 | `:109-122`（真库 repo）+ `:174-194`（真库端到端 planner `planned_count==0 / skipped_count==1`） | ✅ 行为级 |
| (3) counter 与 planner 同口径 | `:128-144`；反向 `:147-171`（存量行回退时 `archivable_count==0`） | ✅ 行为级 |
| (4) 存量 NULL 行姓名回退 | `:147-171`（真库、`person_id=None` 行） | ✅ 行为级 |
| schema / 回填（BLK-1 migration） | `test_alembic_migrations.py:275-289`（列 + 可空 + 索引）、`:291-332`（唯一命中回填 / 重名留空，真 007 库） | ✅ 真库 schema 与数据级 |

### 10.3 测试证据缺口（明确列出）

| ID | 缺口 | 事实依据 | 影响 |
|---|---|---|---|
| **GAP-1** | **ArchiveExecutor 未验证 `person_id` 真正落库** | `test_archive_executor.py:33-45` 只构造带 `person_id` 的 item；全文件无 `person_id` 断言（`git grep person_id` 仅 1 命中=构造处）；`test_freeze_blockers._record()` 绕开 executor 直写 repository | BLK-1 第 5 项验收仅靠代码阅读 + 外部探针，仓库测试**未守护** |
| **GAP-2** | **BLK-5 的 UI/导出 NULL 路径无测试** | `test_review_dialog_review_board.py:43-51` 的 `confidence_band` 矩阵无 `None`；`_result()` 要求 `float`；无「无相似度证据」行文本断言；CSV/Excel/`ExportService` 无 NULL 用例 | 「UI / export 语义一致」只经代码阅读 + 外部探针证明 |
| **GAP-3** | **D-1「rerun 不覆盖人工确认」的主张不成立** | `test_freeze_blockers.py:343-359` 名为 `test_rerun_does_not_overwrite_manual_approval`，但**不调用 `RunRecognitionService`**：只写一条 APPROVED、断言 `list_by_photo` 非空、复述守卫条件 → 同义反复；`test_run_recognition_service.py` 中**无**用例断言「照片已有行 → 不写兼容行」 | 提交信息「rerun 守卫……经测试确认」与仓库证据不符；该守卫无行为级回归测试 |
| **GAP-4** | **Review 身份选择器接线未被测试** | `test_review_dialog_empty_queue.py:56,78`、`test_review_dialog_review_board.py:141-143` 只断言 `bulk_approve(ids, None)` 的调用形状；无 `_identity_combo` 选中后的传参测试、无「未指定 → 告警 → 取消」路径测试 | D-1 的 UI 主路径无 CI 守护 |
| **GAP-5** | `test_archive_planner.py` 的 fake 复刻了 SQLite 去重谓词 | `:88-96` 手工实现 identity 优先 + 姓名回退 | 双份语义（漂移风险）；所幸真库用例提供交叉验证 |

### 10.4 全量套件复现（对提交信息「1310 passed / 6 skipped」的独立验证）

首轮后台运行的进度在前几分钟集中在模型/集成类用例上（约 6 分钟推进 ~8%），但在后台持续运行下**完整跑完**：

```
1310 passed, 6 skipped, 106 warnings in 233.25s (0:03:53)
```

与 `2823d1c` 提交信息宣称的「全量 1310 passed / 6 skipped」**完全一致**（含 skip 数），因此该声明**已获独立复现，不构成问题**。同时说明：全量套件**通过并不代表本报告 §11 的文档一致性问题不存在**——§11 的三条阻断项全部位于**文档/证据引用层**，而仓库测试不覆盖 Stage 文档。

---

## 11. 新发现问题

### 11.1 BLK-3R（**阻断**）— 修正后的行号在修正提交上已失效：`pairing_workbench_service.py` 行偏移 +11 / +16

**事实**：`2823d1c` 在**同一个提交**里既改了 `pairing_workbench_service.py`（新增 `clamp_unit` 于 `:59-68`；`_sink_confirmation` 内加 3 行注释并把 confidence 表达式由 1 行展开为 3 行 → 全文 364 → **380 行**），又把 Stage 文档中被 Stage 4 判为越界的行号"修正"为 **`b3b8685` 上测得的行号**：

```
Stage3:6   「修正越界行号（原 pairing_workbench_service.py:530-555 → 现 :331-358；原 workspace_controller.py:298-315 → 现 :42-64）」
Stage3:789 「三连写/三连回收 … :94-126（confirm）、:265-329（_sink_confirmation）、:174-218（assign_person）、:331-358（_retract_confirmation）」
Stage3:831 「B7 … pairing_workbench_service.py:331-358（_retract_confirmation）」
```

**实测（当前 HEAD，逐行提取 `def`；对照 `git show b3b8685:<file>`）**：

| 函数 | `b3b8685`（文档采用值） | 当前 HEAD（真实值） | 偏移 |
|---|---|---|---|
| `confirm` | 94 | **105** | +11 |
| `reject` | 130 | **141** | +11 |
| `unassign` | 140 | **151** | +11 |
| `assign_person` | 174 | **185** | +11 |
| `set_cluster_state` | 222 | **233** | +11 |
| `_require_assignment` | 237 | **248** | +11 |
| `_active_assignment` | 257 | **268** | +11 |
| `_sink_confirmation` | 265 | **276** | +11 |
| `_retract_confirmation` | **331** | **347** | +16 |
| `_observations_by_run` | 360 | **376** | +16 |
| 文件总行数 | 364 | **380** | +16 |

**后果**：`pairing_workbench_service.py:331-358` 在当前仓库**不是** `_retract_confirmation`（该函数在 `:347-375`）；`:331-346` 是 `_sink_confirmation` 的尾部。三条新写入的"修正引用"（`Stage3:6/789/831`）**照抄 Stage 4 报告在 `b3b8685` 上测得的行号**，而修复本身又把这个文件推后 16 行 → 证据位置**仍不可复核**。

**失效引用面（以当前 HEAD 为判据，机械计数）**：5 份文档中共有 **35 处** `pairing_workbench_service.py:行` 引用（其中 34 处为证据引用，最小被引行号 = `:94`，**全部**落在 +11/+16 漂移区；另 1 处为 `Stage3:6` 修订说明里记录的旧越界号 `:530-555`），以及 **24 处** `pairing.py:` 引用（其中引 `:27`/`:91-115`/`:97`/`:75-86`/`:81-85`/`:101-102`/`:117-141`/`:122-134`/`:99-105` 等行段者漂移 **+1..+6**：阈值常量 `:27 → :28`、规则①块 `:91-115 → :92-121`、规则③块 `:117-141 → :127-141`；引 `:14` 等模块 docstring 行不受影响）。

失效引用的**文档行号**清单（便于逐条收口）：

- `Stage1_BusinessFacts.md`：`14`（引 `:303-329`）、`79`（`:94-126`）、`179`（`:94-126`）、`286`（`:265-358`）、`331`（`:222-233`）、`404`（`:97-100`）、`430`（`:265-329`）、`434`（`:94-126`）
- `Stage2_BusinessRules.md`：`18`（`:331-358`）、`22`（`:94-126`）、`49`（`:257-263`）、`71`（`:222-233`）、`93`（`:322-327`）、`171`（`:97-100`）、`221`（`:222-233`）、`249`（`:94-126`）、`250`（`:130-138`）、`251`（`:140-170`）、`252`（`:174-218`）、`253`（`:222-233`）、`254`（`:265-329`）、`255`（`:331-358`）、`256`（`:257-263`）、`257`（`:174-218`）、`389`（`:289`）、`405`（`:306-311`）
- `Stage3_BusinessDiagrams.md`：`784`（`:240-335`）、`787`（`:107-141`）、`789`（`:94-126` + `:265-329` + `:174-218` + `:331-358`）、`795`（`:305-311`）、`810`（`:237-245`）、`826`（`:160`）、`830`（`:94-126`）、`831`（`:331-358`）

**为什么仍判阻断**：这正是 BLK-3 被 Stage 4 定级「中高」的同一失效模式（证据不可复核 → §7/§8 两张取证基准表失效）；而 Stage 3 头部第 4–10 行明确宣示「证据引用已按 Stage 4 审计结论**逐条重核并修正**」——该宣示在当前 HEAD 上不成立，使读者对整份文档的证据可靠性失去判据。

**减轻情节（避免误判）**：Stage 1/2 头部写「行号为 HEAD 版本行号」（HEAD = `b3b8685`），Stage 3 头部基线同样写 `b3b8685`，故这些行号在**声明的历史基线内**自洽；且全部引用仍在界内（不再是越界）。但本轮 Freeze 的验收口径是「所有关键证据可以定位到**当前仓库**」，且 Stage 3 用了「现 :331-358」的当前性措辞，故列阻断——修复成本低（见 §14）。

### 11.2 BLK-D1D（**阻断**）— D-1 落地后 Stage 1/2/3 仍多处断言修复前行为

见 §6.3（**10 处引用，分布于 9 行**）：`Stage3:149/371/784/836/890`、`Stage2:316/254`、`Stage1:471`、`Stage1_Handoff:19`、`Stage2_Handoff:76`。其中 `Stage3:784`（§7 关键节点表）与同表新增的 `:796`（D-1 行）**直接互斥**，属「同一张最高可追溯性表内部自相矛盾」。

### 11.3 BLK-D2D（**阻断**）— D-2 的 `>=` 未在 Stage 1 与两份 Handoff 收口

见 §7.2：`Stage1:69`（「最大余弦 **> 0.40**」）、`Stage1_Handoff:16`、「`Stage2_Handoff:16`（「严格 >0.40」）、`Stage2_Handoff:68`（仍把已裁决项列为「未裁决矛盾」——与 `Stage2:398` 标为「已裁决+TESTED」冲突）。

### 11.4 其他新发现（非阻断）

| ID | 发现 | 证据 | 定级 |
|---|---|---|---|
| NEW-1 | 无身份批准告警标题误用「确认全部通过」 | `review_dialog.py:331-337` 用 `REVIEW_APPROVE_ALL_CONFIRM_TITLE`；该常量 `ui_text.py:234` = 「确认全部通过」 | 低（文案） |
| NEW-2 | migration 008 的表重建分支不可重入 | `008:78` 判定 `if "confidence" in _column_names("recognition_results")`；若表缺失（RENAME 后异常中断且未回滚）→ `_column_names` 返回 `set()` → 整段跳过 → 迁移"成功"但表缺失 | 低（alembic 事务通常回滚；建议改为显式反查 `recognition_results__008_old` / 表存在性） |
| NEW-3 | `person_id` 索引只在"加列"分支内创建 | `008:48-59`；若列已存在而索引缺失（部分应用态），索引不会被补建（去重退化为全表扫，结果仍正确） | 低 |
| NEW-4 | `downgrade` 把 NULL confidence 折叠为 `0.0` | `008:124` `UPDATE recognition_results SET confidence = 0 WHERE confidence IS NULL`（代码已注释声明） | 低（回滚丢失「无证据」语义） |
| NEW-5 | 会话未更新 Runtime Context | `2823d1c` 未触碰 `.ai/PROJECT_STATUS.md` / `.ai/KNOWN_ISSUES.md` / `.ai/DOCUMENT_INDEX.md`；`.ai/rules/git-rules.md` §9/§24 要求「include documentation updates (when needed) / Update documentation」 | 低（流程一致性） |

---

## 12. 已知但不阻断问题（Known Limitations / Out-of-Scope）

| ID | 问题 | 证据 | 归类 | 为什么**不**阻断 |
|---|---|---|---|---|
| KL-1 | **P1**：存量重名行的归档去重仍按姓名（008 无法唯一回填时故意留 NULL） | §3.7 P1；`008:16-18`、`sqlite_archive_record_repository.py:110-118`；探针 `planned=0 skipped=2` | Known limitation（duplicate-name policy，与 ADV-6 同源） | 仅在「库中已存在重名人员 **且** 存在无法归因的历史归档行」时发生；行为与升级前**完全一致**（不退化），且已有明确文档语义 |
| KL-2 | **P2**：删人 → `ON DELETE SET NULL` 孤儿行 → 再建同名人员会被姓名回退抑制 | §3.7 P2（真库复现） | Known limitation / 待业务裁决 | 删除人员不撤销历史归档事实，抑制与否取决于业务对「删人后同名重建」的定义；Stage 1/2 未记录该组合（建议补登记，见 §14 修复项 4） |
| KL-3 | `recognition_results.person_id` 的两种 NULL 语义仍混同（ADV-2） | 识别期写入即 NULL（`run_recognition_service.py:128` 不传身份）vs 删人 SET NULL；表内无区分列 | Known limitation | 非本次修复目标；不产生新的错误归属 |
| KL-4 | GAP-1/2/3/4/5（§10.3 五个测试证据缺口） | 见 §10.3 | Test-evidence gap | 代码经阅读 + 真库探针双证成立；缺口是「回归守护不足」而非「行为错误」。建议随 BLK 修复一并补测试（尤其 GAP-3 的主张必须修正或补实） |
| KL-5 | migration 008 对 `recognition_results` 整表复制（大库升级耗时/空间） | `008:80-107` | 性能风险（Out-of-Scope） | 未实测，且 `archive_records` 侧为纯 `ADD COLUMN`；升级前可在真实大库评估 |
| KL-6 | NEW-2/3/4（008 分支不可重入 / 索引补建 / downgrade 折叠 0.0） | §11.4 | 低风险健壮性 | 在 alembic 事务语义下不易触发；回滚路径的语义损失已在代码注释中声明 |
| KL-7 | NEW-5：`.ai/` Runtime Context 未同步 | §11.4 | 流程一致性 | 不影响业务基线正确性；建议随文档收口一并补 |
| KL-8 | 未做 runtime UI walkthrough | §1 | 审计覆盖限制 | 已用真库探针 + 全量 1310 项测试替代覆盖；不构成新的基线证据 |

---

## 13. 最终 Freeze 判定

# ❌ NOT-FREEZE-READY

**判定依据（Freeze-READY 必要条件逐条核对）**

| 必要条件 | 状态 | 依据 |
|---|---|---|
| BLK-1 关闭 | ✅ **满足** | §3：真库实测四项验收口径全部成立；FK/索引/回填/mapper/executor/counter 逐点复核 |
| BLK-5 关闭 | ✅ **满足** | §4：三态语义端到端落地，`0.0` 与 `NULL` 库内可区分，无调用方假定非空（UI/导出 NULL 路径缺测试，见 GAP-2） |
| BLK-2 关闭 | ✅ **满足** | §5.1：虚构文件与虚构机制已清除，替换引用真实且准确 |
| BLK-4 关闭 | ✅ **满足** | §5.3：`update_assignment` 描述与代码逐字段一致，文档内部矛盾消除 |
| BLK-3 关闭 | ❌ **不满足** | §5.4、§11.1 BLK-3R：越界本身已修复，但"修正后的"行号只在 `b3b8685` 成立；修复提交本身又把该文件推后 +11/+16 行，导致 35 处引用（含 `Stage3:6/789/831` 三处明确标注为"现"的修正）在**当前仓库**指向错误位置 |
| D-1 与当前代码一致 | ✅ 代码一致 / ❌ 文档不一致 | §6：实现与真库证据完整成立；但 Stage 1/2/3 与两份 Handoff 仍有 10 处引用（9 行）断言修复前行为（含 §7 关键节点表内部互斥） → §11.2 |
| D-2 与当前代码一致 | ✅ 代码一致 / ❌ 文档不一致 | §7：实现/docstring/tests/Stage2/Stage3 一致；`Stage1:69` 与两份 Handoff 仍写 `> 0.40`（其中 `Stage2_Handoff:68` 仍列为未裁决） → §11.3 |
| 未发现新的高严重度回归 | ✅ **满足** | §8：7 项回归面逐项核清；全量套件 **1310 passed / 6 skipped**（独立复现提交信息）+ 定向 85 项全绿；代码层零新回归（仅 NEW-1 文案级） |
| Stage 1~3 与当前实现重新一致 | ❌ **不满足** | §6.3、§7.2、§11.1（引用位置）三者叠加 |
| 剩余 ADV 项不会阻断当前业务基线冻结 | ✅ **满足** | §9：ADV-1..7 均未升级为 blocker；ADV-7 已关闭 |

**结论陈述**

> `2823d1c` 在**代码 / migration / schema / 真库行为**维度上已经关闭了 Stage 4 的全部业务级阻断项：BLK-1（归档去重身份）、BLK-5（置信度三态）经真库探针逐项复现为**修复成立**；BLK-2（虚构文件）、BLK-4（列名臆造）已彻底消除；D-1（人工最终结果）与 D-2（`>= 0.40`）在实现、协议、DTO、UI、导出、迁移上自洽且可复算。
>
> 但本轮 Freeze 的三条文档/证据一致性必要条件**未满足**：(1) BLK-3 的"修正引用"以修复前的行号写入，在修复提交上即失效（BLK-3R）；(2) D-1 已在代码落地，而 Stage 1/2/3 与 Handoff 仍多处断言"审核中心只改 status、通过永远不进归档"（BLK-D1D）；(3) D-2 的 `>=` 未在 Stage 1 与两份 Handoff 收口，且 `Stage2_Handoff` 仍将已裁决项列为未裁决（BLK-D2D）。
>
> 因此判定 **NOT-FREEZE-READY**。三条阻断项**全部是文档/证据口径**问题，不涉及任何新的业务逻辑错误、数据错误或运行时回归；修复后应在同一提交内重新跑机械引用校验（§14 附脚本要点），即可再次提交 Freeze 复评。

---

## 14. 阻断项清单（未通过原因）与最小修复建议

| # | 阻断 ID | 描述 | 证据 | 最小修复 |
|---|---|---|---|---|
| 1 | **BLK-3R** | Stage 1–3 中 `pairing_workbench_service.py`（35 处引用，34 处证据引用的行号全部落在 +11/+16 漂移区）与 `pairing.py`（24 处引用，涉阈值/规则①③行段者漂移 +1..+6）在当前 HEAD 上已失效；`Stage3:6` 的「现 :331-358」与事实不符 | §11.1 表与文档行号清单：`_retract_confirmation` 实际 `:347-375`；文件 364→380 行 | 以**当前 HEAD** 为准重算并改写三个 Stage 文档与两份 Handoff 中全部 `pairing_workbench_service.py:行` 与 `pairing.py:行`（`confirm 105 / reject 141 / unassign 151 / assign_person 185 / set_cluster_state 233 / _active_assignment 268 / _sink_confirmation 276 / _retract_confirmation 347-375`；`pairing.py` 阈值 `:28`、规则① `:92-121`、规则③ `:127-141`）；并把 Stage 3 头部第 4–10 行的「逐条重核并修正」改为**明确注明所用行号基线**（或改为「以当前 HEAD 为准」） |
| 2 | **BLK-D1D** | 9 处仍断言 D-1 之前的行为，与 `Stage3:796`/实现互斥 | §6.3 表 | 逐条改写：`Stage3:149/371/784/836/890`、`Stage2:316`（`update_status` 现可同时写 `person_id`）、`Stage2:254`（PR-20 的 `clamp(score,0,1)` → 「有证据写余弦、无证据写 NULL」）、`Stage1:471`、`Stage1_Handoff:19`、`Stage2_Handoff:76`（身份来源 = 审核指定 / 配对确认）。建议同时保留反向事实：**未指定身份时该行仍不可归档**（此点与新语义不冲突） |
| 3 | **BLK-D2D** | `>= 0.40` 未在 Stage 1 与两份 Handoff 收口；`Stage2_Handoff:68` 仍列为未裁决 | §7.2 表 | 改 `Stage1:69`、`Stage1_Handoff:16`、`Stage2_Handoff:16` 为 `>=`；把 `Stage2_Handoff:68` 的未确认项 #1 改为「已由 Stage 4 D-2 裁决并落地（`pairing.py:109-112`，测试三点边界）」，或直接移出未确认清单 |
| 4 | 建议同时处理（不阻断） | §3.7 P1/P2 的残余语义未在 Stage 1/2 归档段登记 | §3.7 | 在 Stage 1 §1-3 段 7 / Stage 2 CORE-06 补一句：「`person_id IS NULL` 的存量行与**人员删除后置 NULL** 的孤儿行仍按姓名回退去重——同名重建场景可能被抑制，属已知限制」 |
| 5 | 建议同时处理（不阻断） | GAP-1..4 测试缺口；GAP-3 的主张与测试不符 | §10.3 | ① executor 用例加 `assert repo.added[-1].person_id == item.person_id`；② `confidence_band(None)` + 行文本断言；③ 用真库调 `RunRecognitionService` 断言「已有行 → 不写兼容行」（替换现有同义反复用例）；④ 对话框用例断言 `_identity_combo` 选中后 `bulk_approve(ids, person_id)` 与取消路径 |
| 6 | 建议同时处理（不阻断） | NEW-1..5（文案 / migration 分支健壮性 / Runtime Context 同步） | §11.4 | 见各行"建议"；`.ai/PROJECT_STATUS.md` 建议补本次会话条目 |

**复评门禁建议（可直接复用）**：把 Stage 4 §2.2 的机械校验脚本作为固定门禁，并把「被引用文件在**当前 HEAD** 的行号是否覆盖被描述的函数名」纳入人工抽检——本次 BLK-3R 正是"行号在界内但指向错函数"这一机械校验盲区造成的。

---

## 15. 复审声明

- **取证方式**：全量静态复核（源码/migration/测试/ADR/规则）+ 全量 `文件.py:行号` 机械校验 + 真库升级与 PRAGMA 实测 + 一次性真库探针（BLK-1/D-1/D-2/导出链）+ 测试实跑（全量 1310 passed / 6 skipped；另定向 24 与 61 项）。
- **项目改动**：**零改动**，未提交 Git。`git status --porcelain` 复审前后一致（仅存量未跟踪 `docs/development/evidence/stage-f-acceptance-review.md`）。临时脚本与探针均在 `C:\Users\Public\PhotoArchiverAudit\`（仓库外），探针数据库在 `%TEMP%`。
- **未覆盖**：runtime UI 手工走查；大库 migration 性能实测（测试套件已全量实跑：1310 passed / 6 skipped）。
- **本报告定位**：对 `2823d1c` 的独立第三方复审，结论以当前 HEAD 的实际代码/测试/迁移/真库行为为准；与 Stage 1–3 及 Stage 4 的冲突处，一律以本报告列出的一手证据为准。
