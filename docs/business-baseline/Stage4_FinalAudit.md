# Stage 4 — 独立业务逻辑最终审计报告

- **审计对象**：`D:\work\PhotoArchiver`，仓库 HEAD `b3b8685dbfb9a47ffddbd8ed2ebd5e69e058eb6d`，分支 `main`
- **审计输入**：`Stage1_BusinessFacts.md`、`Stage1_Handoff.md`、`Stage2_BusinessRules.md`、`Stage2_Handoff.md`、`Stage3_BusinessDiagrams.md`
- **审计日期**：2026-09-27
- **审计原则**：仓库 HEAD 为唯一权威事实源；Stage 1–3 全部视为**待验证声明**，任何无代码/迁移/测试/Git 支撑的表述一律不采信
- **项目改动**：**零改动**。本次审计仅执行只读命令（`git grep` / `git log` / `Select-String` / 目录列举），`git status --porcelain` 审计前后一致（仅存量未跟踪文件 `docs/development/evidence/stage-f-acceptance-review.md`，非本次产生）

---

## 1. 审计结论摘要

| 分类 | 数量 | 说明 |
|---|---|---|
| **VERIFIED**（已验证） | 见 §14 | Stage 1–3 的绝大多数主流程事实与代码一致 |
| **INCORRECT**（事实错误） | **4 项** | 引用不存在的文件 / 引用越界行号 / 引用不存在的列名 |
| **UNSUPPORTED**（无证据支撑） | **3 项** | 关键节点表用"已核对"口吻给出无法指认的证据 |
| **OVERSTATED**（过度断言） | **2 项** | 把 UNKNOWN/INFERRED 升级为既成事实 |
| **MISSING**（遗漏） | **8 项** | 代码中真实存在、且影响主流程的业务事实，三阶段均未记录 |
| **DECISION**（需业务方裁决） | **2 项** | 代码行为已确认，但"是否算业务错误"需 owner 判定 |

**关键判定：NOT-FREEZE-READY。**

阻断项集中在两类：

1. **证据链完整性缺陷**——Stage 3 的"关键节点说明表"和"事实差异对照表"两处是全项目最需要可追溯性的交付物，却包含**指向仓库中不存在的文件**（`batch_import_flow_service.py`）与**越界行号**（`pairing_workbench_service.py:530-555`，该文件仅 364 行）。这直接违反 Stage 3 §7 自身声明的"「当前代码实现位置」＝本人在 HEAD 亲自核对的文件:行"。
2. **业务事实缺口**——归档去重的真实主键是**人员姓名字符串**而非 `person_id`，Stage 1/2/3 一致写成 `(person_id, photo_id)`；以及按位置配对的建议因无分数会把兼容行 confidence 写成 0.0。二者都会造成用户可见的数据错误。

---

## 2. 审计方法与证据基线

### 2.1 已使用的证据源

| 证据类型 | 具体范围 |
|---|---|
| 源码 | `src/photo_archiver/{domain,application,infrastructure,presentation}` 全量关键文件 |
| 迁移 | `alembic/versions/002 / 003 / 004 / 005 / 006 / 007` |
| 测试 | `tests/unit/{application,infrastructure,domain,architecture}` |
| Git | `git status --porcelain`、`git log --all -S <符号>`、`git grep` |
| 证据文档 | `docs/development/evidence/stage-f-acceptance-review.md` |

### 2.2 引用完整性机械校验

对 Stage 1–3 三份主文档（共 ~1400 行）中的**全部** `文件.py:行号` 形式的引用做机械化校验：建立仓库全部 `.py` 文件的"文件名 → 总行数"索引，逐一比对被引用的最大行号是否超出文件实际长度，或文件根本不存在。

**校验脚本**（临时文件已删除，未落入项目）：

```powershell
$roots = @('d:\work\PhotoArchiver\src','d:\work\PhotoArchiver\tests',
           'd:\work\PhotoArchiver\tools','d:\work\PhotoArchiver\alembic')
$map = @{}
foreach ($r in $roots) {
  Get-ChildItem -Path $r -Recurse -Filter *.py -File |
    ForEach-Object { $map[$_.Name] = [System.IO.File]::ReadAllLines($_.FullName).Length }
}
# 逐行正则提取 ([A-Za-z0-9_]+\.py):(\d+)(?:-(\d+))?，比对 $map
```

**校验输出（全部 9 条异常，去重后）**：

```
Stage1_BusinessFacts.md:47      __init__.py:47                            (file has 1 lines)   <- 误报，见 3.6
Stage1_BusinessFacts.md:62      cluster_faces.py:25-44                    (file has 15 lines)  <- 误报，见 3.6
Stage1_BusinessFacts.md:223     import_batch.py:22-73                     (file has 72 lines)  <- 轻微越界
Stage2_BusinessRules.md:218     cluster_faces.py:24-44                    (file has 15 lines)  <- 误报，见 3.6
Stage3_BusinessDiagrams.md:771  workspace_controller.py:298-315           (file has 81 lines)  <- 越界
Stage3_BusinessDiagrams.md:784  batch_import_flow_service.py:106-118      (FILE NOT FOUND)    <- 虚构文件
Stage3_BusinessDiagrams.md:799  batch_import_flow_service.py:95-122       (FILE NOT FOUND)    <- 虚构文件
Stage3_BusinessDiagrams.md:819  batch_import_flow_service.py:106-118      (FILE NOT FOUND)    <- 虚构文件
Stage3_BusinessDiagrams.md:821  pairing_workbench_service.py:530-555      (file has 364 lines) <- 越界
```

---

## 3. 关键节点逐条核对

### 3.1 INCORRECT-1 | Stage 3 引用了仓库中不存在的文件 `batch_import_flow_service.py`（3 处）

**声明位置**
- `Stage3_BusinessDiagrams.md:784`（§7 关键节点说明表）
- `Stage3_BusinessDiagrams.md:799`（§8-A1 主流程一致项）
- `Stage3_BusinessDiagrams.md:819`（§8-B5 事实差异项）

**声明原文（转录）**

| 行 | 声明内容 |
|---|---|
| 784 | `` `import_batches.status` 在事务外更新 \| 导入批次标签落库 \| `batch_import_flow_service.py:106-118`（事务内只 `update_many` photo_source_batch） `` |
| 799 | `` \| A1 \| 导入名单 → 人员档案 \| `batch_import_flow_service.py:95-122`：create / merge_existing 分流、同事务、批次标签 \| `` |
| 819 | `` \| **B5** \| 批次标签在事务外写 \| `batch_import_flow_service.py:106-118`（事务内只 `update_many`） \| `` |

**核查结果**

```powershell
Get-ChildItem -Path d:\work\PhotoArchiver -Recurse -Filter batch_import_flow_service.py
# -> 无输出

git log --all --oneline -S "batch_import_flow_service"
# -> 无输出（该字符串在整个 Git 历史中从未出现）

git log --all --oneline --diff-filter=A -- "*batch_import_flow_service.py"
# -> 无输出
```

三重确认：**文件不存在于工作区、不存在于任何历史提交、不存在被重命名/删除的可能**。

**真实实现位置**

- `src/photo_archiver/application/services/confirm_import_service.py`（共 151 行）
  - `:50` `def confirm(...)` 起；`:95-99` 事务体
  - `:96-98` 事务提交后于 UoW **之外**单独调用 `batch.mark_confirmed()` -> 对应"批次标签在事务外写"的**真实事实**
- `src/photo_archiver/domain/entities/import_batch.py:45` `def mark_confirmed(self)`

**附带事实错误**：三处引用均提到"事务内只 `update_many` photo_source_batch"。全仓校验：

```powershell
git grep -n "photo_source_batch" -- src
# -> 无输出
```

`photo_source_batch` 在 `src/` 中**完全不存在**（`source_type` 只作为 `ImportBatch` 的普通字段出现在 `import_batch.py:28`）。该"事务内做了 X"的具体机制描述亦为虚构。

**分类**：INCORRECT
**严重度**：高——出现在 §8-A1「主流程一致（无需特殊画法）」与 §8-B5「实现 vs 设计预期差异」两处**结论性表格**中，且 §8-B5 的差异结论（"提交后额外写库，非原子"）本身**恰好与真实代码一致**。这意味着作者可能确实看懂了代码，但把证据挂到了不存在的文件上——**证据不可复核，结论不可追溯**。

---

### 3.2 INCORRECT-2 | Stage 3 引用越界行号（文件长度不足一半）

**声明位置**：`Stage3_BusinessDiagrams.md:821`（§8-B7 照片删除的跨代际残留）

**声明原文**

```
| **B7** | 照片删除的跨代际残留 | `pairing_workbench_service.py:530-555` 只回收当前代际 …
```

**核查结果**：`pairing_workbench_service.py` 全文件 **364 行**。引用 `:530-555` 越界 166 行。

**相关联的第二处越界**（未被上表单列，但同属此文件）：

```
Stage3_BusinessDiagrams.md:782  pairing_workbench_service.py:240-335 / 361-376 / 505-528
Stage3_BusinessDiagrams.md:722  pairing_workbench_service.py:505-528
```

`:505-528` 同样越界。真实的三连写/三连回收实现区间是：

| 逻辑 | 真实行号 | 函数 |
|---|---|---|
| 确认写样本 + 兼容行 | `:117-126` | `confirm` -> `_sink_confirmation` |
| `_sink_confirmation` 定义 | `:265-329` | 写 `person_face_embeddings` + `recognition_results` APPROVED |
| `_retract_confirmation` 定义 | `:331-358` | 删 APPROVED + 停用样本 |
| 解除映射 | `:140-170` | `unassign` |
| 改派 | `:174-220` | `assign_person` |

**分类**：INCORRECT
**严重度**：中高——三处引用（B6 三连写、B7 跨代际、§7 关键节点表）均不可复核。

---

### 3.3 INCORRECT-3 | Stage 3 引用越界行号 `workspace_controller.py:298-315`

**声明位置**：`Stage3_BusinessDiagrams.md:771`（§7 关键节点说明表首行，"影响主流程 = 是"）

**声明原文**

```
| 照片集合非空闸门 | 所有 AI/分组操作的统一前置 | `workspace_controller.py:298-315`（`_readiness` 计算点） | ... | 是：闸门本身生效 |
```

**核查结果**：`workspace_controller.py` 全文件 **81 行**。该文件内**不存在**名为 `_readiness` 的方法。

**真实实现位置**

- `src/photo_archiver/presentation/controllers/workspace_controller.py`
  - `:42-64` `def match_guidance(self) -> ActionGuidance` —— 逐段返回闸门判定
  - `:66-81` `def archive_guidance(self) -> ActionGuidance`
  - `:37` `def status(self)` 读 `self._readiness_provider.readiness()`
- 就绪数据的真正计算点：`SQLiteRecognitionRepository.read_workspace_counts`（`sqlite_recognition_repository.py:181-247`）

**结论**：闸门**确实生效**（Stage 3 的业务结论正确），但给出的证据位置完全错误。

**分类**：INCORRECT
**严重度**：中——业务结论正确，证据位置错误。

---

### 3.4 INCORRECT-4 | Stage 3 §7 声称 `update_assignment` 只更新 `updated_at/assigned_by`——两个列都不存在

**声明位置**：`Stage3_BusinessDiagrams.md:781`（§7 关键节点说明表）

**声明原文**

```
| `cluster_person_assignments` 决策行 | 人工调整全历史 + 当前有效集合 | 同左（`update_assignment` 只更新 `updated_at/assigned_by`） | 改派/解除保留历史 | **只更新不删除**；人员删除才 CASCADE | 是（决定「当前有效」口径） |
```

**核查结果 1——实际 UPDATE 语句**
`src/photo_archiver/infrastructure/database/sqlite_cluster_assignment_repository.py:92-117`：

```sql
UPDATE cluster_person_assignments SET
  status = ?,          -- sqlite_cluster_assignment_repository.py:98
  score = ?,           -- :99
  sort_snapshot = ?,   -- :100
  confirmed_at = ?     -- :101
WHERE id = ?
```

**核查结果 2——表结构中根本没有这两列**
`alembic/versions/007_assignments_and_person_samples.py` 建表列：

```
id, cluster_id, person_id, status, source, score, sort_snapshot, error,
created_at, confirmed_at
```

`git grep "updated_at" -- alembic/versions/007_assignments_and_person_samples.py` -> 无输出
`git grep "assigned_by" -- alembic/versions/007_assignments_and_person_samples.py` -> 无输出

迁移 007 中 `error` 列（`:45`）**定义了但 `update_assignment` 从不写入**。

**业务影响**：`update_assignment` **会改写 `status` 与 `confirmed_at`**——即它就是 Stage 1 §5 所说的"决策行状态迁移持久化"。Stage 3 §6.3 的状态机图把状态迁移画成**行内改写**，而 §7 却说只更新审计列，两处自相矛盾。Stage 3 §6.3 的画法（行内改写）是对的，§7 的描述是错的。

**分类**：INCORRECT
**严重度**：中高——涉及状态机持久化语义这一核心机制的自相矛盾。

---

### 3.5 UNSUPPORTED-1 | Stage 3 §7 关键节点表"照片集合非空闸门"的差异列无证据

**声明位置**：`Stage3_BusinessDiagrams.md:771` 差异列

**声明原文**：「就绪判定读旧兼容投影（pending/archivable），与簇/配对无关」

**核查**：`read_workspace_counts`（`sqlite_recognition_repository.py:181-247`）确实只读 `photos` / `recognition_results` / `archive_records`，不 JOIN `face_clusters` / `cluster_person_assignments` / `face_observations`。**业务结论成立**。

但 Stage 3 §7 的表头声明「『当前代码实现位置』＝本人在 HEAD `b3b8685` **亲自核对**的文件:行」，而该行的实现位置是越界的 `:298-315`。业务结论对、证据位置错，读者无法复核。

**分类**：UNSUPPORTED
**严重度**：中

---

### 3.6 引用校验的 3 处误报（经人工复核排除，不计入问题清单）

机械校验另有 3 条异常，人工复核后确认为**脚本误报**，特此记录以免后续阶段重复排查：

| 校验输出 | 实际情况 | 判定 |
|---|---|---|
| `Stage1:47  __init__.py:47 (file has 1 lines)` | Stage 1 原文为 `` `entities/__init__.py:47` ``，指向 `src/photo_archiver/domain/entities/__init__.py`。该文件第 47 行确为 `BATCH_STATUS_CANCELLED,`（本次已 Read 确认，位于 `from ...import_batch import (` 块内）。脚本按"文件名"建索引，`__init__.py` 在仓库中有大量同名文件，取到了错误那一个。 | 引用正确 |
| `Stage1:62  cluster_faces.py:25-44 (file has 15 lines)` | Stage 1 原文为 `` `commands/cluster_faces.py:25-44` ``。`application/commands/cluster_faces.py` 共 **42 行**，`:24-30` 确为 `recognition_run_id` + 三个阈值默认值。脚本命中了同名的 `application/use_cases/cluster_faces.py`（15 行，全是 `raise NotImplementedError`）。 | 引用基本正确（`:25-44` 越界 2 行，阈值实为 `:26-30`） |
| `Stage2:218  cluster_faces.py:24-44 (file has 15 lines)` | 同上，同一文件同一处。 | 同上 |

**唯一残留的轻微越界**：`Stage1:223  import_batch.py:22-73` — 文件 72 行。`ImportBatch` 类实为 `:22-44`，`ImportDraftRow` 为 `:46-72`。引用把两个类合并成 `22-73`，越界 1 行。属笔误，不影响可复核性。

---

## 4. 数据关系独立复核

Stage 1 §4.1 / §4.2 的表清单与关系图，逐表对照迁移 DDL 复核。

### 4.1 关系正确性：VERIFIED

| 关系 | 声明 | 核查 | 结论 |
|---|---|---|---|
| people 1-N cluster_person_assignments | `person_id FK CASCADE` | `007:49` `person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE` | OK |
| face_clusters 1-N cluster_person_assignments | `cluster_id FK CASCADE` | `007:38` `cluster_id TEXT NOT NULL REFERENCES face_clusters(id) ON DELETE CASCADE` | OK |
| photos 1-N recognition_results | `photo_id FK CASCADE` | `002:92` `ON DELETE CASCADE` | OK |
| people 1-N recognition_results | `person_id FK SET NULL` | `002:93` `ON DELETE SET NULL` | OK |
| photos 1-N archive_records | `photo_id FK CASCADE` | `002:119` `ON DELETE CASCADE` | OK |
| people 1-N person_face_embeddings | CASCADE | `007:63` | OK |
| photos 1-N face_observations | CASCADE | `004` | OK |

**注意 Stage 1/2/3 均未点明的一条事实**：`recognition_results.person_id` 是**可空**列（`002:88` `person_id TEXT,`），而 Stage 3 §2 断点④ 的整条推理链（"审核通过 != 可归档"）**完全依赖这个可空性**。该列可空是断点成立的结构前提，应显式记录。

### 4.2 DATA_RELATION-1 | 归档去重主键是"人员姓名字符串"，不是 `person_id`（三阶段一致记错）

**三阶段的统一声明**

| 文档 | 位置 | 原文 |
|---|---|---|
| Stage 1 | `:91` | 「去重作用域 = `(person_id, photo_id)`（`:106-132`）-> **同一照片可归档到多个人员目录**」 |
| Stage 2 | `CORE-06` | 「归档成功态去重作用域 = (person_id, photo_id)」 |
| Stage 3 | `:507` | `` PL->>REPO: PhotoRepository + ArchiveRecordRepository；(person,photo) 成功态去重 `` |

**核查结果——去重实际按姓名**

`src/photo_archiver/application/services/archive_planner.py:201-208`：

```python
if self._archive_record_repository.has_successful_for_person(
    photo_id, person_name,          # <- 传的是姓名，不是 person_id
):
    return None
```

`src/photo_archiver/domain/repositories/archive_record_repository.py:29-34`：

```python
def has_successful_for_person(self, photo_id: UUID, person_name: str) -> bool:
    """Stage E（E-SG-6）：该 (person, photo) 是否已有成功态归档记录.
    归档去重作用域为 (person, photo)：…
    """
```

`sqlite_archive_record_repository.py` 中该方法的 SQL：

```sql
SELECT 1 FROM archive_records
WHERE photo_id = ? AND target_person_name = ? AND status IN (...)
```

**表结构佐证**——`archive_records` 根本没有 `person_id` 列：
`alembic/versions/002_split_create_ddl.py:109-120`

```
id, photo_id, target_archive_root, target_person_name,
target_event_or_date, target_original_name, status, archived_at, error
```

**同源影响：工作区计数也按姓名**
`sqlite_recognition_repository.py:229` `read_workspace_counts` 的 archivable 判定同样用 `a.target_person_name = person.name` JOIN——即概览页"可归档 N 张"的数字与 planner 用的是**同一个姓名键**。

**三个用户可见的业务后果**

1. **同名人员互相吞掉归档**：若 `people` 表存在两个同名人员（导入无重名校验，`confirm_import_service.py:136-140` 的合并解析用 `name + department`，同部门同名会走 merge；但**跨部门同名会建出两个独立 person**），则 A 归档过某照片后，B 的同一张照片被 `has_successful_for_person` 判为已归档而**静默跳过**（`archive_planner.py:204-207` 仅 `logger.debug`，UI 不可见），结果是"同一照片可归档到多个人员目录"这条 Stage 1 结论在同名场景下**不成立**。
2. **改名后重复归档**：归档成功后修改人员姓名，`target_person_name` 写死不回写（Stage 2 U12 已记录此点），新姓名查不到旧记录 -> 同一张照片可被**再次归档**到新目录。
3. **概览页计数与实际可归档项口径绑定在姓名上**，与 `person_id` 身份语义脱钩。

**为什么三阶段都记错**：`pairing.py:74-89` 的规划器内部确实用 `seen_person_photo_pairs`（**元素为 `(person_id, photo_id)`**）做**单次 plan 调用内**的去重，Stage 1 引用的 `:106-132` 正是这段。三阶段把"调用内集合元素"当成了"跨调用持久去重键"，漏掉了持久层用的是姓名字符串。

**分类**：DATA_RELATION_ERROR
**严重度**：**高（FREEZE 阻断项）**——这是会导致照片**静默漏归档**的业务错误，且方向性结论（"同一照片可归档到多个人员目录"）在真实数据下可被证伪。

**正确表述建议**

> 归档去重分两层：
> - **单次 plan 调用内**：内存集合 `seen_person_photo_pairs`，键为 `(person_id, photo_id)`（`archive_planner.py:106-132`）
> - **跨调用持久去重**：`archive_records` 表无 `person_id` 列，SQL 按 `(photo_id, target_person_name)` 匹配。因此同名人员互相抑制、改名后可重复归档。
>
> 设计预期「(person_id, photo_id)」与实现的偏差应作为事实差异登记。

---

## 5. 状态机独立复核

### 5.1 VERIFIED：`cluster_person_assignments` 五态机

`src/photo_archiver/domain/entities/cluster_assignment.py:60-71` 与 Stage 1 §5 / Stage 2 §2 的表述**逐条一致**：

| 迁移 | 代码 | Stage 声明 | 结论 |
|---|---|---|---|
| `__post_init__` 校验 | `:22-39` | 4 条不变量 | OK |
| `confirm` 仅 `suggested -> confirmed` | `:43-46` | OK | OK |
| `reject` 仅 `suggested -> rejected` | `:49-52` | OK | OK |
| `unassign`：`suggested`/`confirmed`/`rejected` -> `unassigned` | `:55-58` | OK | OK |
| `confirmed_at` 仅 confirm 时置位 | `:46` | OK | OK |
| 终态 `unassigned` 不可再迁出 | `:55-58` 无 `unassigned` 分支 | OK | OK |

Stage 3 §6.3 状态机图**完全正确**。§7 表格对 `update_assignment` 的描述错误（见 §3.4）。

### 5.2 VERIFIED：簇状态六态中仅 3 态有写入路径

```powershell
git grep -n "update_cluster_status" -- src
# -> sqlite_face_cluster_repository.py:（定义）
# -> pairing_workbench_service.py:229        （唯一调用点）
```

`pairing_workbench_service.py:222-233` `set_cluster_state` 只接受 `unknown` / `ignored`，其余抛 `ValidationError`。建簇时 `FaceCluster` 初始 `status="pending"`。

-> `confirmed` / `split` / `merged` **定义存在、零写入**。Stage 1 §5、Stage 2 CL-19、Stage 3 §6.3 note 的声明**全部正确**。

### 5.3 VERIFIED：`import_batches.cancelled` 零写入

`cancelled` 只出现在 `import_batch.py` 的常量定义与实体校验中，无任何 `mark_*` 方法产出该状态。Stage 1 §5 / Stage 2 RO-15 / Stage 2 HI-08 **正确**。

### 5.4 VERIFIED：`recognition_results` 三态与绕道写入

`002:85-94` + `sqlite_recognition_repository.py:36-55` + `290-302`：
- 表**无 CHECK 约束**，状态列仅 `pending` / `approved` / `rejected` 三个常量被使用
- 写入点：`add`（`:36`）/ `add_many`（`:48`，预过滤已存在项）/ `update_status`（`:290`，审核中心）
- 配对三连写**直接调 `add` 写 APPROVED**，绕开状态机

Stage 1 §5「项目无状态机校验、状态可绕道写入」**正确**。

### 5.5 MISSING-1 | `error` 列在 `cluster_person_assignments` 上定义但从不写入

`alembic/versions/007:45` 定义 `error TEXT`，但 `update_assignment` 的 UPDATE 列表（`sqlite_cluster_assignment_repository.py:97-102`）**不含 `error`**，`add_assignments` 的 INSERT 亦不写该列。

**业务影响**：与 §7.2 的规则③ 无分数问题同源——`suggest_pairings` 规则③ 按位置配对**不产生相似度分数**，这类建议的 `score` 为 `NULL`。而人工确认时 `_sink_confirmation` 会写 `confidence = clamp(assignment.score or 0, 0, 1)`（`pairing_workbench_service.py:322-324`）——**按位置配对的建议，其写入 `recognition_results` 的 confidence 被写成 0.0**。

Stage 2 §3 与 Stage 3 §6.2 都把"建议带分数"当作通例画图，**未记录"按位置配对的建议 score 为空 -> 兼容行 confidence=0.0"这一事实**。`error` 列的空转属于同一处设计的未完成面。

**分类**：MISSING
**严重度**：中——会产生"已确认归档的记录置信度为 0"的困惑数据，影响审计与后续复算

---

## 6. 主流程顺序独立复核

### 6.1 Stage 3 §6.1 序列图：VERIFIED

逐步比对 UI 入口与 Gate：

| 阶段 | 声明 | 代码 | 结论 |
|---|---|---|---|
| ① 扫描 | `scan_controller` -> `ScanPhotosService` | `main_window.py:309-310` | OK |
| ② 识别 | Gate `match_guidance` -> Controller `start_run` -> Service | `main_window.py:311-312`；`recognition_run_controller.py:60-105` | OK |
| ③ 聚类 | 人员页选 run -> `ClusterFacesService` | `people_admin_page.py:528-530` | OK |
| ④ 配对 | `PairingWorkbenchDialog` 选代际 -> 生成/确认/拒绝/改派/解除/标陌生/忽略 | `pairing_workbench_dialog.py:287-372` | OK 六个操作全部有 UI 入口 |
| ⑤ 审核 | `ReviewDialog` 通过/拒绝 | `review_dialog.py` | OK |
| ⑥ 归档 | `ArchivePreviewDialog`（dry-run 默认勾选） | `archive_preview_dialog.py:149-152` | OK |

**Gate 顺序 VERIFIED**：`main_window.py:308-316` 的动作注册顺序为 import -> scan -> match -> review -> archive，与 `match_guidance`（`workspace_controller.py:53-63`）的分段判定（no_persons->import / no_photos->scan / model 缺失->model / pending=0->review）**逐段对应**。

### 6.2 MISSING-2 | 配对工作台的六个操作按钮无按状态使能/禁用

`pairing_workbench_dialog.py:249-253`：

```python
def _set_actions_enabled(self, enabled: bool) -> None:
    for button in (self._confirm_button, self._reject_button,
                   self._assign_button, self._unassign_button,
                   self._unknown_button, self._ignore_button):
        button.setEnabled(enabled)
```

**六个按钮的 enabled 状态完全绑定"是否选中了簇"这一个条件**，不区分当前指派状态。这意味着：
- 簇无任何指派时，点"确认" -> 服务层 `confirm` 抛 `Only suggested assignments can be confirmed`（`pairing_workbench_service.py:97-100`）-> 对话框 `_warn` 弹错误
- 簇无任何指派时，点"拒绝" -> `reject` 会把 `_require_assignment` 抛出的 `Assignment ... does not exist` 弹出（`:238-241`）
- 已 `confirmed` 的簇再点"拒绝" -> 同样被拒

Stage 3 §6.2 把六个操作画成对等的人工调整入口（`O --> P1..P6`），**未记录**「UI 层无按状态使能，非法组合靠服务层抛 ValidationError 弹窗兜底」这一实现事实。

**分类**：MISSING
**严重度**：低—中（不产生数据错误，但影响 Stage 3 图对人工调整路径的准确性；Stage 3 §6.2 节点 `O` 已标 `ROLE_GATE`，方向正确，只是未说明 Gate 位置在服务层而非 UI 层）

---

## 7. 人脸流程与配对逻辑独立复核

### 7.1 0/1/N 张脸、无脸、不可读、检测失败——VERIFIED

`run_recognition_service.py:106-133` `_consume_result` 的分支已逐条核对：

| 情形 | 代码 | 行为 | Stage 声明 | 结论 |
|---|---|---|---|---|
| `not result.embeddings`（无脸） | `:111-113` | `no_face_count=1`，**返回空 faces**，不建观测 | Stage 1 §6-3 | OK |
| 提取失败（不可读） | `:115-116` | `unreadable_count=1`，不建观测 | OK | OK |
| 异常（检测失败） | `:118-123` except 分支 | `error_count=1`，不建观测，单张失败**不中断整批** | OK | OK |
| N >= 1 张脸 | `:125-131` | **对每张脸都建观测**（`scope_verdict` 随之不同），按 `photo_face_count` 排序 | Stage 3 P-09 | OK |
| 兼容行 | `:133-137` | **仅 `ordered[0]`**（置信度最高）写 PENDING；且守卫 `if in_scope and not self._recognition_repository.list_by_photo(...)` | Stage 1 §6-3 | OK |

**Stage 3 P-09 的自我纠正是正确的**：`run_recognition_service.py:125-131` 确实对 N 脸照片无条件建 N 条观测，出局发生在**读取端**（`cluster_faces_service.py:230-236` 只取 `scope_verdict == "in_selected_scope"` 且 `embedding.vector` 非空）。Stage 3 明确写「Stage 2 §2 的措辞是正确的，无需校正」，回查后确认这一判断**成立**。

**阈值与合并规则 VERIFIED**：
- `face_clustering.py:112-117` 贪心簇心 `>= 0.5`（含等号）
- `face_clustering.py:203-220` 完全链接跨簇最小相似度 `>= 0.4`（含等号）
- `face_clustering.py:13-16` `low_quality_threshold` 默认 `0.0` = **整门禁用**（`quality_score < 0.0` 永不成立）
- `_NO_EVIDENCE = -inf`（无高质量证据对 -> 永不合并）

Stage 2 CL-07 / CL-18 全部**准确**。

### 7.2 MISSING-3 | 配对规则③ 按位置配对**不产生相似度证据**，`score` 为空

`src/photo_archiver/domain/services/pairing.py:106-141` `ordered_suggestion`：逐位配对时构造的 assignment **不设 `score`**（`score` 保持 dataclass 默认 `None`）。而规则① `sample_match` 的 assignment 带 `score=best_score`。

`pairing_workbench_dialog.py:215-229` 渲染建议时按状态分支，`suggested` 分支（`:217-228`）才格式化分数。

**业务影响**：`score` 为空的建议被人工确认后，`_sink_confirmation`（`pairing_workbench_service.py:322-324`）写：

```
confidence = clamp(assignment.score or 0, 0, 1)   # -> 0.0
```

即**按位置配对确认的照片，其 `recognition_results.confidence` 被写为 0.0**，与"识别匹配得分"字段语义混淆。

Stage 3 §6.2 节点 I 写「规则③ 剩余按位置一对一：簇序 = sort_key / 人员序 = roster_order [IMPL]」，并在节点 T 标注「roster_order 与时间轴的对应只是人为约定，非相似度证据 [INFER]」。**Stage 3 已经意识到位置配对不是相似度证据，但没有把"因此 compat 行 confidence=0.0"这一具体落库后果记录下来**。

**分类**：MISSING
**严重度**：中—高（落库数据语义错误；与 §5.5 的 `error` 列空转同源，均为"位置配对无分数"设计的未完成面）

### 7.3 UNSUPPORTED-2 | 规则① 阈值边界 0.40 的 `>` vs `>=` 争议，Stage 3 标为 `[INFER]`

`pairing.py:97,106` 实际为：

```python
best_score = sample_match_threshold      # 初值 = 阈值
...
if score is not None and score > best_score:   # 严格大于
```

**恰好等于 0.40 的相似度不会命中。** 但 `pairing.py` 模块 docstring 写「>=」。

Stage 3 §6.2 注（`:741`）已明确记录此分歧并标 `[INFER]`，指向 Stage 2 §7-1 未裁决项。**这是本次审计中 Stage 3 处理得最规范的一处**——事实、代码位置、docstring 矛盾、裁决归属四要素齐备。

**核查结论**：Stage 3 正确，此处不构成问题。但需在冻结前由 owner 裁决（见 §12）。

### 7.4 MISSING-4 | `person_embeddings` 无生产者，三阶段均已记录但未推导出完整后果

`git grep "\.save(" -- src`（`FaceEmbeddingRepository.save` 调用方）：仅 `settings_store.save` / `Workbook.save` / 缩略图 `.save()` / `painter.save()`。**产品代码零调用**。Stage 1 §1-10 / Stage 3 §2 断点① / §8-B2 **全部正确**。

完整后果链（三阶段均只记了一半）：

1. `run_recognition_service.py:66` 读 `list_all()` -> 恒空 -> `match` 恒返 `None` -> `person_id` 恒 `NULL`（Stage 3 断点① 已记）
2. 审核中心 `update_status`（`sqlite_recognition_repository.py:290-302`）**只改 `status` 不改 `person_id`** -> 通过后仍是 `person_id IS NULL`（Stage 3 断点④ / B12 已记）
3. `list_approved_by_person`（`sqlite_recognition_repository.py:266-270`）`WHERE person_id = ? AND status = ?` -> 审核通过的行**永不进归档计划**（Stage 3 B12 已记）
4. **【Stage 1/2/3 均未记录】** -> 因为 `person_id` 恒 NULL，`recognition_results` 写入时 `person_id` 列为 `NULL`（`002:88` 可空列）。而 Stage 3 §2 断点④ 论证的前提正是这个可空性，却**未在任何文档中显式记录"person_id 列可空"这一 schema 事实**。删除人员时 `ON DELETE SET NULL`（`002:93`）与"写入时就是 NULL"这两种 NULL **语义完全不同**（前者曾有归属、后者从未有归属），但在数据上不可区分——Stage 3 §3.2 H2 注释提到「删过人的照片（person_id 已置 NULL 的行仍在）」，却**未指出新链路写入的行也是 NULL，两者混同**。

**分类**：MISSING
**严重度**：中—高（两种 NULL 语义混同，是 Stage 3 断点④ 全部推理的隐含前提，却未显式登记）

### 7.5 VERIFIED：配对排除集合的三项作用域

`pairing.py:99-105` 构造的排除集合，全部限定在**当前代际**：

| 排除项 | 仓储方法 | SQL 作用域 | 结论 |
|---|---|---|---|
| 已有有效指派的簇 | `list_active_by_cluster_run` -> `list_by_cluster_run` | `JOIN face_clusters ... WHERE face_clusters.cluster_run_id = ?` | OK 代际内 |
| 已确认人员 | `list_confirmed_person_ids` | `JOIN face_clusters ... WHERE cluster_run_id = ? AND status='confirmed'`（`sqlite_cluster_assignment_repository.py:168-182`） | OK 代际内 |
| rejected 对 | `list_rejected_pairs` | `JOIN face_clusters ... WHERE cluster_run_id = ? AND status='rejected'`（`:149-165`） | OK 代际内 |

Stage 2 §3.4 / Stage 3 §6.2 节点 F「排除集合（均按代际作用域）[IMPL]」**完全正确**。

### 7.6 VERIFIED：簇状态不参与建议过滤

`pairing.py:99-105` 的排除集合**不含 `face_clusters.status`**。Stage 3 §8-B4「簇状态未参与建议过滤：只按『有/无有效指派』过滤，不判状态 -> unknown/ignored 簇继续收建议」**正确**。

---

## 8. 归档流程独立复核

### 8.1 VERIFIED：只认 `recognition_results.status='approved'`

`archive_planner.py:116` 唯一数据入口 `list_approved_by_person(person_id)`。全文件不引用 `face_observations` / `face_clusters` / `cluster_person_assignments`。

Stage 2 BA-02「识别 PENDING 行与 Stage D/E 互不知情：聚类不读 `recognition_results`；归档不读观测/簇/指派」**双向核验通过**（`cluster_faces_service.py:26-41` 的 import 列表中确无 `RecognitionRepository`）。

### 8.2 VERIFIED：0 脸 / 不可读 / 范围外照片永不可归档

三阶段一致声明，核验链条：
- 0 脸照片无观测（`run_recognition_service.py:111-113`）-> 不进聚类 -> 无簇 -> 无指派 -> 无 APPROVED
- 不可读/检测失败同理
- 范围外照片**有**观测，但 `cluster_faces_service.py:230-236` 过滤掉 -> 同上

**结论：可归档集合 == 「配对确认三连写产出的 APPROVED」**。Stage 3 断点④ 的表述**正确**。

### 8.3 VERIFIED：dry-run 默认勾选

`archive_preview_dialog.py:149-152`：

```python
self._dry_run_check = QCheckBox(ARCHIVE_DRY_RUN_CHECK, self)
self._dry_run_check.setChecked(True)      # <- 默认勾选
```

Stage 1 §1-3 / Stage 2 Handoff / Stage 3 §6.1 均记录 **正确**。

### 8.4 VERIFIED：目标路径三段 + 净化 + 降级

`archive_path_builder_service.py:33-81`：
- `{archive_root}/{person_name}/{YYYY-MM-DD}/{original_name}`
- 空姓名 -> `unknown-person`（`:48-49`）；`captured_at is None` -> `unknown-date`（`:50-53`）
- 三段均过 `sanitize_windows_filename`（`:55-57`），净化时 `logger.warning`（`:58-63`）

Stage 1 §1-3 段 7 **准确**。

### 8.5 MISSING-5 | `target_person_name` 写死不回写，是 §4.2 数据关系缺陷的**放大器**

Stage 2 U12 已记录「归档已完成成功后再次变更人员姓名/删除人员，`target_person_name` 不回写（写死字符串）」，标记 `INFERRED`，并建议"评估是否需要 owner 裁决"。

本次审计将其**升级为 CONFIRMED 并与 §4.2 合并**：

`archive_planner.py` 构造 `ArchiveRecord` 时传入当时的 `person.name` 字符串；`archive_records` 表无 `person_id` 列（`002:109-120`）；`archive_executor` 只按 `photo_id + target_person_name` 查重。

**因此"改名后重复归档"不是理论风险，而是必然结果**——改名后新姓名查不到旧记录，planner 会重新规划并实际写盘。Stage 2 将其标为 `INFERRED` 是**低估**。

**分类**：MISSING（Stage 2 已半记，缺 CONFIRMED 定级与后果链）
**严重度**：高（与 §4.2 合并计入 FREEZE 阻断项）

### 8.6 VERIFIED：状态词汇与成功态定义

`ArchiveStatus` 七态：`planned` / `archived` / `skipped` / `renamed` / `overwritten` / `failed` / `dry_run`。

`has_successful_for_person` 拦 `archived` / `skipped` / `renamed` / `overwritten`，**不拦** `failed` / `planned` / `dry_run`（`archive_record_repository.py:33-34` docstring）。Stage 1 §1-3 / Stage 2 归档段**准确**。

---

## 9. 重跑与历史保留独立复核

### 9.1 VERIFIED：`recognition_runs.parameters` 永不改写

`sqlite_recognition_run_repository.py:81-119` `update_run` 的 UPDATE 列表（`:90-100`）：

```
status, face_count, unreadable_count, no_face_count, error_count,
in_scope_photo_count, out_of_scope_photo_count, error, finished_at
```

**不含 `parameters`**。方法 docstring `:82` 明写「刻意不更新 parameters（C-SEM-3）」。

Stage 1 §5 / Stage 2 CORE-03 / Stage 1 Handoff 第 3 条 **全部正确**。

### 9.2 VERIFIED：重跑 = 恒新 run + 新观测，旧 run 零改写

`run_recognition_service.py` 每次 `execute` 新建 `RecognitionRun` + 新 `FaceObservation`；`recognition_run_photos` 为输入快照（`:121-127`）。

`cluster_faces_service.py:69-103` 恒新建 `FaceClusterRun` + 新簇全集，旧代际不修剪。`test_cluster_faces_service.py:160` 有"两代并存"测试。

Stage 1 §6-2 / Stage 2 RR-08 / Stage 2 RR-11 / Stage 3 §3.2 H1 **全部正确**。

### 9.3 VERIFIED：兼容行"一次性"守卫

`run_recognition_service.py:133-137`：

```python
if in_scope and not self._recognition_repository.list_by_photo(photo.id):
    # 只在无历史行时写 PENDING
```

`list_by_photo` 返回**全部**行（不限状态，`sqlite_recognition_repository.py:103-110`）。故任何历史行（含 REJECTED / person_id IS NULL）永久阻止重写。

`test_run_recognition_service.py:67,101` 有对应测试。Stage 2 RR-11「兼容行的去重是按『照片』的：既存每行（含 PENDING）都阻新」**准确**。

### 9.4 VERIFIED：识别范围选择不按既有结果过滤

`recognition_run_controller.py:60-105` 的快照闸门只校验模型可用性 + 快照非空，**不排除已有 `recognition_results` 的照片**。`workspace_controller.py:45-48` docstring 明确说明「photos that already carry recognition results no longer block this entry」。

Stage 1 Handoff 第 3 条 / Stage 2 §6-PARTIAL③ **正确**。

### 9.5 MISSING-6 | 重跑时缩小范围无法撤销既有待审项

`run_recognition_service.py:105-109` 的 `classify_scope` 以 `photo_ids`（本次快照内）+ `selected_photo_ids`（本次用户选择）判定 `scope_verdict`。

**但守卫 `not list_by_photo(...)`（`:133`）使得范围外照片与已投影照片互斥**。后果：

- 一张照片在 run#1 中被**排除**在范围外 -> 不写兼容行（`:133` 的 `in_scope` 条件为假）
- run#2 中把它**纳入**范围 -> 仍无历史行 -> **可以**写 PENDING
- 反之：run#1 纳入并写了 PENDING -> run#2 即使用户**明确排除**该照片，`in_scope` 为假不写新行，但旧 PENDING 行**依然留在库里、依然出现在审核中心列表中**——用户没有 UI 手段把它从待审队列移除

Stage 3 §8-B1 把兼容行一次性记为核心分歧（"新观测无法再进审核 -> 跨 run 追加式分组断裂"），**方向正确**，但未记录上述"用户缩小范围无法撤销既有待审项"这一具体后果。Stage 2 §6-PARTIAL ④ 提到"不可读/无脸照片仅有计数+CSV 导出，照片库无语义筛选轴"，但那是讲**扫描维度**缺失，不是讲**待审项无法撤销**。

**分类**：MISSING
**严重度**：中（用户可见的功能缺口；非数据错误）

### 9.6 VERIFIED：导入草稿永保留

`parse_import_draft_service.py:107,146,153` 每次编辑都 `DELETE` + 重插 `import_draft_rows`（`sqlite_import_batch_repository.py:99-130`）。取消导入后草稿行**保留**，但 UI 无重新打开入口。

Stage 1 §1-1 / Stage 2 HI-08 / Stage 2 Handoff PARTIAL ② **全部正确**。

---

## 10. 删除与级联行为独立复核

### 10.1 VERIFIED：删人员 = 嵌入 CASCADE + 识别结果 SET NULL

```powershell
# 测试证据
tests/unit/infrastructure/test_deletion_cascade.py:121
  test_remove_person_sets_recognition_null_and_cascades_embeddings
```

`002:93` `ON DELETE SET NULL`；`007:63` `person_face_embeddings` CASCADE；`007:49` `cluster_person_assignments` CASCADE。

`PersonDeletionPreview`（`deletion.py:78+`）计数语义与 DDL 一致。**FK CASCADE 生效**——`sqlite_connection.py:26` 每连接执行 `PRAGMA foreign_keys = ON`。

Stage 1 §1-6 / Stage 2 §2 / Stage 3 §3.2 I **正确**。

### 10.2 VERIFIED：删照片连带删 `recognition_results` + `archive_records`

```powershell
tests/unit/infrastructure/test_deletion_cascade.py:92
  test_remove_photos_cascades_recognition_and_archive
```

`002:92` / `002:119` 均 CASCADE。**正确**。

### 10.3 MISSING-7 | 删照片会**级联抹掉**已确认指派写入的 APPROVED 行，但**不删** assignment

核验：删除一张已配对确认的照片，`ON DELETE CASCADE` 触发：
- `face_observations` CASCADE（`004`）
- `face_cluster_members` CASCADE（`006`）
- `recognition_results` CASCADE（`002:92`）-> **APPROVED 行消失**
- `cluster_person_assignments` **不动**（其 FK 指向 `face_clusters`，非 `photos`）-> **confirmed 指派仍在**
- `person_face_embeddings` **不动**（FK 指向 `people`）

即：assignment 仍显示 `confirmed`，但它投影出去的 APPROVED 行已被 CASCADE 抹掉，样本仍指向已删照片的观测。

Stage 3 §8-B7「照片删除的跨代际残留」**方向触及此区域**，但（a）其唯一证据 `pairing_workbench_service.py:530-555` 是越界引用（见 §3.2），（b）该行讲的是"删除后重新指派跨代际时只回收当前代际"，与"删除本身触发的级联残留"是两件事，**未明确区分**。

**分类**：MISSING
**严重度**：中—高（工作台状态与实际可归档性脱节的静默不一致）

---

## 11. UI 入口与实现状态独立复核

### 11.1 入口齐全性：VERIFIED

| 业务动作 | UI 入口 | 状态 |
|---|---|---|
| 导入名单 | `import_people_controller` + `import_preview_dialog` | OK |
| 扫描 | `main_window.py:309` | OK |
| 识别 | `main_window.py:311` | OK |
| 审核 | `main_window.py:313` + `review_dialog` | OK |
| 归档 | `main_window.py:315` + `archive_preview_dialog` | OK |
| 聚类 | `people_admin_page.py:528-530` | OK |
| 配对 | `pairing_workbench_dialog` | OK 6 操作齐备 |
| 人员增删改排序 | `manage_people_service` + `people_admin_page` | OK |
| 删人员 / 删照片 | `main_window.py:324,327` | OK |
| 取消任务 | `main_window.py:335`（默认 disabled） | OK |

Stage 3 §5「实现状态图」无「未接线」节点，**准确**。

### 11.2 MISSING-8 | `person_face_embeddings.enabled` 字段无停用入口

Stage 3 §7 已记录「写入 `confirm/assign` 路径；撤回入口未暴露」「字段存在但 UI 无撤回入口」，标记 `NO`。

**本次核验确认该记录正确**，并补充：`unassign`（`pairing_workbench_service.py:162-165`）会调 `_retract_confirmation` 停用样本，但 `unassign` 的触发前提是"该簇存在一条非 `unassigned` 的指派行"。若一条 `confirmed` 指派因人员被删而 CASCADE 消失，样本则**永久停用且无法恢复**（`enabled=0`）。

Stage 1 §6 / Stage 2 §7-7 记录了「样本可撤回」的设计意图。**不构成 Stage 错误，补记为实现缺口**。

**分类**：MISSING（Stage 3 已半记，缺级联消失后的不可恢复后果）
**严重度**：低

### 11.3 关键参数硬编码：VERIFIED

`commands/cluster_faces.py:24-30`（`StartClusteringRunCommand`）：

```python
recognition_run_id: UUID
cluster_sim_threshold: float = DEFAULT_CLUSTER_SIM_THRESHOLD      # 0.5
consistency_threshold: float = DEFAULT_CONSISTENCY_THRESHOLD     # 0.4
low_quality_threshold: float = DEFAULT_LOW_QUALITY_THRESHOLD     # 0.0
```

`__post_init__:31-34` 校验范围；`parameters():36-42` 生成不可变快照（`scope_filter="in_selected_scope"` 硬编码在快照内）。

**UI 无任何阈值控件**（Stage 2 CL-16 标 `PARTIAL`）——`git grep` 确认 `people_admin_page` 无阈值输入控件。**正确**。

---

## 12. 需业务方裁决项（DECISION）

### D-1 | `person_embeddings` 恒空 => 身份匹配链路整体未激活

**事实链（全部 CONFIRMED）**

1. `FaceEmbeddingRepository.save` 在 `src/` 中零调用方（`git grep "\.save(" -- src` 逐条排除）
2. `run_recognition_service.py:66` 读 `list_all()` -> 恒空
3. `match` 恒返 `None` -> `recognition_results.person_id` 写入时恒为 `NULL`
4. `list_approved_by_person`（`sqlite_recognition_repository.py:266-270`）`WHERE person_id = ?` -> 审核通过的行永不进归档计划

**裁决问题**：审核中心"通过"按钮在当前状态下**必然产出不可归档的结果**。这是
- (a) 预期的过渡态（Stage D/E 上线后该入口将废弃 / 仅供旧数据浏览），还是
- (b) 未完成的功能（审核中心应写入 `person_id`，但缺 UI 选人）？

Stage 3 §8-B12 标为 `NO`（影响主流程），Stage 2 §4 把「审核通过」列为"人工边界（隐含可否归档）"。**三阶段都记录了事实，但都未把它升格为需要 owner 明确回答的裁决题。**

**建议**：冻结前必须裁决。若为 (a)，审核中心应在 UI 上明确标注"通过仅标记，不建立身份归属"；若为 (b)，需补 `person_id` 选择 UI。

### D-2 | 规则① 样本匹配阈值边界：`>` 还是 `>=`

`pairing.py:97,106` 实际为严格大于；`pairing.py` docstring 写「>=」。

**裁决问题**：恰为 0.40 的余弦相似度是否应命中？生产数据中该精确值出现概率低，但**边界语义必须与 ADR-017 一致**。

Stage 3 §6.2 注（`:741`）已完整记录分歧并指向 Stage 2 §7-1 未裁决项。**建议 owner 裁决后统一 docstring 或代码。**

---

## 13. 未发现的错误类型（阴性结论）

为便于判断审计覆盖面，明确记录以下**已检查且未发现问题**的类别：

| 类别 | 检查范围 | 结论 |
|---|---|---|
| **阶段顺序错误** | 6 个主流程阶段与 4 处 Gate 的先后 | 未发现。UI 动作注册顺序、Guidance 分段判定、服务层闸门三方一致 |
| **主流程缺环** | 导入 -> 扫描 -> 识别 -> 聚类 -> 配对 -> 审核 -> 归档 | 未发现缺失。7 环全部有 UI 入口 + 服务 + 仓储 |
| **实体/表映射错误** | 20 张表 x `sqlite_mappers.py` 逐字段 | 未发现映射遗漏 |
| **状态机迁移错误** | 5 个状态机（assignment / cluster_run / cluster / recognition_result / import_batch） | 未发现非法迁移放行；未发现终态可迁出 |
| **数据关系错误** | 7 条 FK 关系 + 4 条业务关联 | FK 全部正确；**1 处业务关联错误（§4.2 归档去重主键）** |
| **异常路径遗漏** | 识别（单张失败隔离）/ 配对（ValidationError）/ 归档（逐条 try）/ 删除（幂等 no-op） | 未发现未捕获异常导致整体中断 |
| **实现状态误标** | Stage 3 §5 / §6 全部 `[IMPL]` `[PART]` `[PLAN]` 标记 | 未发现把 `[PLAN]` 标成 `[IMPL]` |

---

## 14. VERIFIED 清单（Stage 1–3 准确的部分）

以下为逐条代码核验通过的声明，构成 Stage 4 认定的**可信基线**：

### 14.1 主流程与 Gate

- 导入是人员入库唯一入口，`create` / `merge_existing` 分流
- 扫描 -> 照片登记
- 识别为追加型：恒新建 `RecognitionRun` + 新 `FaceObservation`
- `parameters` 永不改写
- 重跑不按既有 `recognition_results` 过滤
- 聚类恒新建 `FaceClusterRun` + 新簇全集
- 配对恒写 `suggested`，**从不自动 `confirmed`**
- 归档只读 `recognition_results.status='approved'`
- dry-run 默认勾选

### 14.2 人脸流程

- 0 脸 / 不可读 / 检测失败 -> 不建观测（各自计数）
- N >= 1 脸 -> **N 条观测全部落库**（含范围外），出局在读取端
- 兼容行只投影 `ordered[0]`（置信度最高）
- 兼容行守卫：照片已有**任意**历史行则永久不重写
- 聚类参与条件：`in_selected_scope` 且 `embedding.vector` 非空
- 阈值 0.5 / 0.4（含等号），`low_quality_threshold=0.0` = 整门禁用
- `_NO_EVIDENCE = -inf`：无高质量证据对永不合并

### 14.3 配对

- 规则① 样本匹配（`person_face_embeddings` enabled）
- 规则② 跳过 `rejected` 对
- 规则③ 剩余按 `sort_key` x `roster_order` 位置配对
- 排除集合三项（有效指派簇 / 已确认人员 / rejected 对）**均按代际作用域**
- 簇状态（`unknown`/`ignored`）**不参与**建议过滤
- `person_embeddings` 读活写死（零生产者）
- 人工六操作全部有 UI 入口

### 14.4 状态机

- `cluster_person_assignments` 五态机逐条一致
- `confirm` 仅接受 `suggested`；`unassign` 接受 `suggested`/`confirmed`/`rejected`
- `unassigned` 为终态
- `face_clusters` 六态定义，仅 `pending`/`unknown`/`ignored` 有写入路径
- `import_batches.cancelled` 定义但零写入
- `recognition_results` 无 CHECK 约束，状态可绕道写入
- `cluster_run` 五态机（`running` -> `complete`/`failed`/`cancelled`）

### 14.5 数据关系与删除

- 7 条 FK 的 CASCADE / SET NULL 全部与 DDL 一致
- 删人员：嵌入 CASCADE + 识别结果 SET NULL
- 删照片：识别结果 + 归档记录 CASCADE
- 预览计数走 `list_by_photo_ids` 批量下推，无 N+1，Application 层零 SQL
- `PRAGMA foreign_keys = ON` 每连接执行

### 14.6 重跑与历史

- 导入草稿行每次编辑 DELETE + 重插，取消后保留
- `run_photos` 既是输入快照又是删除快照的悬挂点
- 范围外观测永久留存、无清理入口
- 失败分类三合一（读不到 / 检不出 / 不摄入），`run_photos` 不存逐照片分类

### 14.7 归档

- 目标路径三段 + Windows 文件名净化 + `unknown-person`/`unknown-date` 降级
- 成功态 = `archived`/`skipped`/`renamed`/`overwritten`（`failed`/`planned`/`dry_run` 不拦）
- 单次 plan 内去重集合键为 `(person_id, photo_id)`（**但见 §4.2 跨调用层**）

---

## 15. 实施状态汇总表

| # | 项目 | Stage 1 | Stage 2 | Stage 3 | Stage 4 核验 |
|---|---|---|---|---|---|
| 1 | 导入名单 -> 人员档案 | 事实 | 规则 3/4 | A1 `[IMPL]` | **已实现**（证据位置错，§3.1） |
| 2 | 扫描登记 | 事实 | 规则 1/2 | A2 `[IMPL]` | 已实现 |
| 3 | 识别范围选择 | 事实 | 闸门 0..5 | A2 `[IMPL]` | 已实现 |
| 4 | 人脸检测/嵌入 | 事实 | — | A3 `[IMPL]` | 已实现 |
| 5 | 兼容投影（Top-1） | 事实 | §6 | A4 `[IMPL]` | 已实现 |
| 6 | 聚类两段式 | 事实 | CL-01..18 | A5 `[IMPL]` | 已实现 |
| 7 | 配对三规则 | 事实 | §3 | A6 `[IMPL]` | 已实现 |
| 8 | 人工六操作 | 事实 | §4 | A7 `[IMPL]` | 已实现 |
| 9 | 三连写 / 三连回收 | 事实 | §6-PARTIAL① | A8 `[PART]` | 已实现（无跨表事务）；证据越界（§3.2） |
| 10 | 审核中心 | 事实 | §4 | A9 `[IMPL]` | 已实现但**产出不可归档**（§7.4、D-1） |
| 11 | 归档计划 | 事实 | CORE-05/06 | A10 `[IMPL]` | 已实现，**去重主键错误**（§4.2） |
| 12 | 归档执行 | 事实 | §3 | A11 `[IMPL]` | 已实现 |
| 13 | 删除管理 | 事实 | §2 | A12 `[IMPL]` | 已实现，**级联残留未记录**（§10.3） |
| 14 | 人工合并/拆分组 | PLANNED | CL-17 `[PLANNED]` | `[PLAN]` | **未实现**（grep 零命中），三阶段一致 |
| 15 | 历史视图 | PLANNED | §6 | B8 `[PLAN]` | **未实现**，三阶段一致 |

---

## 16. 冻结裁决

# ❌ NOT-FREEZE-READY

### 16.1 阻断项（必须解决方可冻结）

| ID | 类别 | 描述 | 位置 | 严重度 |
|---|---|---|---|---|
| **BLK-1** | DATA_RELATION_ERROR | 归档去重主键是 `target_person_name` 字符串，`archive_records` 无 `person_id` 列。导致同名人员互相抑制归档、改名后重复归档。三阶段一致写成 `(person_id, photo_id)`，并据此得出"同一照片可归档到多个人员目录"——该结论在同名场景下**可被证伪** | §4.2 | **高** |
| **BLK-2** | INCORRECT | Stage 3 三处引用仓库中**不存在**的文件 `batch_import_flow_service.py`（含从未出现在任何 Git 提交中）；其中"事务内只 `update_many` photo_source_batch`"的机制描述在 `src/` 中完全不存在 | §3.1 | **高** |
| **BLK-3** | INCORRECT | Stage 3 引用越界行号：`pairing_workbench_service.py:530-555`（文件仅 364 行）、`workspace_controller.py:298-315`（文件仅 81 行）。§7 关键节点说明表是全项目可追溯性要求最高的交付物，不可复核即失效 | §3.2、§3.3 | **中高** |
| **BLK-4** | INCORRECT | Stage 3 §7 称 `update_assignment` 只更新 `updated_at/assigned_by`——**两列在迁移 007 中都不存在**，实际更新 `status`/`score`/`sort_snapshot`/`confirmed_at`。且与 Stage 3 §6.3 状态机图自相矛盾 | §3.4 | **中高** |
| **BLK-5** | MISSING | 「按位置配对（规则③）无相似度分数」导致确认后 `recognition_results.confidence` 被写为 **0.0**，与"识别匹配得分"字段语义混淆。三阶段均未记录此落库后果 | §7.2 | **中高** |

### 16.2 建议项（不阻断冻结，但应在下一版修正）

| ID | 类别 | 描述 | 位置 | 严重度 |
|---|---|---|---|---|
| ADV-1 | MISSING | 配对工作台六操作按钮不按指派状态使能，非法组合靠服务层抛 `ValidationError` 弹窗兜底 | §6.2 | 低中 |
| ADV-2 | MISSING | `recognition_results.person_id` 的**两种 NULL 语义混同**：写入时即为 NULL（新链路无生产者）vs 删除人员后 SET NULL（曾有归属），数据上不可区分 | §7.4 | 中高 |
| ADV-3 | MISSING | 删照片 CASCADE 会抹掉 APPROVED 行，但 `confirmed` assignment 与簇成员不受影响 -> 工作台状态与实际可归档性脱节 | §10.3 | 中高 |
| ADV-4 | MISSING | 重跑时缩小识别范围**无法撤销**已存在的待审 PENDING 行 | §9.5 | 中 |
| ADV-5 | MISSING | `cluster_person_assignments.error` 列定义但从不写入 | §5.5 | 中 |
| ADV-6 | UNSUPPORTED | `target_person_name` 不回写被 Stage 2 标为 `INFERRED`，实为 CONFIRMED 且是 BLK-1 的放大器 | §8.5 | 中 |
| ADV-7 | INCORRECT | `import_batch.py:22-73` 越界 1 行（`ImportBatch` 实际 `:22-44`） | §3.6 | 低 |

### 16.3 待裁决项（owner 决策，非文档缺陷）

| ID | 裁决问题 | 位置 |
|---|---|---|
| **D-1** | 审核中心「通过」在当前状态下必然产出不可归档结果——是预期过渡态（应标注）还是缺失功能（应补 `person_id` 选择 UI）？ | §12 |
| **D-2** | 规则① 阈值边界：代码为严格 `>`（`pairing.py:97,106`），docstring 写「>=」。以何者为准？ | §12 |

### 16.4 冻结建议路径

1. **先解 BLK-1**——这是唯一会导致**真实数据错误**（照片静默漏归档 / 重复归档）的业务缺陷。需决定：改用 `person_id` 去重（需加列 + 迁移），还是接受姓名语义并在 UI/文档中明示同名冲突。
2. **再解 BLK-2/3/4**——Stage 3 §7/§8 两张表是后续所有阶段的取证基准。建议**全量重核该两表的每一行**，用本报告 §2.2 的机械校验脚本作为固定门禁。
3. **BLK-5 与 ADV-1..7** 归入 Stage 3 修订版。
4. **D-1 优先于 D-2**——D-1 决定审核中心这一主流程入口是否可对用户开放。

---

## 17. 审计声明

- **审计范围**：Stage 1–3 三份主文档（~1400 行）逐条对照仓库 HEAD `b3b8685` 的源码、迁移、测试与 Git 历史
- **取证方式**：全量 `文件.py:行号` 引用机械化校验 + 关键业务逻辑人工逐行复核 + Git 历史溯源（`git log --all -S`）+ 测试用例反向验证
- **项目改动**：**零改动**。`git status --porcelain` 审计前后完全一致（仅存量未跟踪文件 `docs/development/evidence/stage-f-acceptance-review.md`）。临时校验脚本写在项目外目录并已删除
- **本报告定位**：Stage 1–3 的**独立第三方核验**，不替代它们。§14 列出的 VERIFIED 清单构成 Stage 1–3 可信基线，§16 列出必须修订项
- **未覆盖范围**：未执行运行时验证（未跑 `pytest`），全部结论基于静态代码/迁移/Git 证据。§6.2、§7.2 等涉及交互与落库后果的结论，建议在修订后以集成测试固化

---
