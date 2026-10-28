# 批次级删除功能 · 实现细节讨论稿（2026-10-28）

> 状态：**已实施（2026-10-29）**——Owner 裁定 D1~D5 按推荐方案执行、同意 D10 标签改造；D6~D9 按推荐默认值落地。实现记录见文末 §13。
> 数据来源：代码只读审查 + 生产库只读探查（`%LOCALAPPDATA%\PhotoArchiver\photo_archiver.db`，2026-10-28 17:xx 快照）。
> 相关既有材料：`docs/development/` 下界面优化系列提交（`376340a` 删除级联披露 / `c104cde` / `181c7d5`）。

---

## 1. 结论摘要

1. **需求里的"导入批次"在数据模型里对应两套互不相连的实体**，这是本次设计的第一分歧点：
   - **名单导入批次** = `import_batches`（`名单_test.txt` 等名单文件），人员归属靠 `people.source_batch_id` 关联；
   - **识别运行** = `recognition_runs`（截图底部下拉框"识别执行 2026-10-26 23:06 · 已完成 · 1441 张脸"），照片归属靠 `recognition_run_photos` 关联。
   - 两者**没有任何外键或字段级关联**，"同一次导入的名单 + 照片"在库里不存在。
2. **名单侧的能力已经存在**：`people_admin_page` 顶部的「按批次删除…」按钮 + `DeletePersonService.execute_batch()` 已经能删除某名单批次的当前归属人员，并可勾选连带删除批次记录与导入草稿。所以"删除选定导入批次的名单及记录"若指名单批次，**是已有能力，不是新增功能**。
3. **照片侧的能力完全缺失**：目前没有任何"按运行批次删除照片"的入口（只有主窗口照片列表的选中删除）。
4. 因此建议的落地口径是：**以识别运行为锚点**，新增两个动作：
   - **A：删除该运行批次的名单及记录** = 删除该运行产生的身份指向（人员）及其全部级联记录；
   - **B：删除该运行批次的照片及记录** = 删除该运行快照内的照片登记及其全部级联记录。
   同时保留名单批次的既有「按批次删除…」，两者并存但语义分离。
5. 三个必须先裁定的语义问题（详见 §10）：**A 的"名单"是删人还是只删匹配关系**；**B 是否连带删除该运行的聚类代际**；**存在归档记录 / GT 裁定 / 样本库时是否硬阻断**。默认推荐见决策表。

---

## 2. 术语与锚点（第一分歧点）

| 术语 | 库中实体 | 选择器位置 | 关联字段 | 现有删除入口 |
|---|---|---|---|---|
| 名单导入批次 | `import_batches` | 人员名册页顶部「来源批次」下拉（`people_admin_page.py:291`） | `people.source_batch_id`（**无 FK**，软指针） | ✅「按批次删除…」（`people_admin_page.py:750`） |
| 识别运行 | `recognition_runs` | 人员名册页底部「识别执行」下拉（`people_admin_page.py:863`） | `recognition_run_photos.run_id` | ❌ 无 |
| 聚类代际 | `face_cluster_runs` | 聚类结果对话框内「聚类代际」下拉 | `face_clusters.cluster_run_id` | ❌ 无 |

截图 2 红框圈住的是**识别运行**下拉框（条目形如 `2026-10-26 23:06 · 已完成 · 1441 张脸`，标签模板见 `presentation/ui_text.py:496`），不是名单导入批次；截图 1 红框圈住的是名册表里 `名单_test.txt` 来源批次列的前几行。**建议以识别运行为"批次"锚点**，理由：

- 照片只挂在识别运行下（`recognition_run_photos`），需求 B 在名单批次下无解；
- 名单批次侧的等价能力已有，A 若也挂在名单批次上就是重复建设；
- 用户截图明确指向识别运行下拉作为"选定批次"的操作点。

> 遗留歧义（若 Owner 坚持 A 挂在名单批次上）：则 A 完全由既有「按批次删除…」覆盖，仅需补"删除批次记录与草稿"默认勾选与文案，本轮实际新增只剩 B。

---

## 3. 现状能力矩阵

| 已有能力 | 入口 | 服务 | 磁盘文件 | 事务 |
|---|---|---|---|---|
| 删除单人 | 主窗口 / 名册页 | `DeletePersonService.execute` | 不动 | ✅ 单 UoW |
| 名册多选删除 | 名册页多选 | 同上 | 不动 | ✅ |
| **按名单批次删除人员** | 「按批次删除…」 | `DeletePersonService.execute_batch` | 不动 | ✅ 单 UoW（人员+批次+草稿同一事务） |
| 清空所有人员 | 「清空所有人员…」 | `execute_clear_all` | 不动 | ✅ |
| 删除选中照片登记 | 主窗口照片列表 | `DeletePhotosService.execute` | 不动 | ✅ |
| 按建议处置重复项 | 重复报告 | `DisposeDuplicatesService` | 不动 | ✅ |
| 清理缩略图缓存 | 维护通道 | `CleanupThumbnailCacheService` | 删缓存文件（对账式） | — |

**全局不变量（D3）**：应用内任何删除路径都**不删除磁盘上的照片原件**（`delete_photos_service.py:1-7` 明确"服务层不接收文件系统依赖"）。归档流程只复制不移动。**新功能必须继承这条不变量**。

**级联语义唯一裁判是真实 SQLite**（`PRAGMA foreign_keys = ON`，`sqlite_connection.py:31`）；InMemory 替身不模拟级联。

---

## 4. 生产库实测量化（2026-10-28 快照）

```
photos=473  people=36  recognition_results=401(全部 pending, person_id 全 NULL)
archive_records=0  person_face_embeddings=0  calibration_ground_truth=0
face_observations=1441  face_clusters=216  face_cluster_members=405
cluster_person_assignments=36  recognition_runs=4  recognition_run_photos=473
```

| 识别运行 | 创建时间 | 照片快照 | 观测 | 簇 | 成员 | 指派行 | 涉及人员 |
|---|---|---|---|---|---|---|---|
| `bb94edc4` | 10-28 17:07 | **473** | 1441 | 36 | 405 | 0 | 0 |
| `586365ec` | 10-26 23:06 | 0 | 0 | 108 | 0 | 36 | 1 |
| `63977600` | 10-25 09:31 | 0 | 0 | 72 | 0 | 0 | 0 |
| `81115a5b` | 10-24 01:40 | 0 | 0 | 0 | 0 | 0 | 0 |

由此得出三条**硬约束**：

- **C-1 历史运行不可按批次删照片**：10-26 / 10-25 / 10-24 三个运行 `recognition_run_photos` 与 `face_observations` 均为 0 行，照片归属信息**已经不存在**（只剩空壳簇行与 36 条指派行）。对这些运行，B 必须给出"该运行没有可删除的照片快照"的明确空态，**不得静默 no-op**（项目既有禁令）。
- **C-2 36 条指派行全部指向同一个人**：`cluster_person_assignments` 36 行分布在 10-26 运行的 36 个簇上，`person_id` 只有 1 个不同值——这正是历史"36 簇批量误指派给 roster#1"的事故残留。A 功能若删人，会连带清掉这 36 条决策行。
- **C-3 簇成员计数已经大面积失真**：216 个簇里 **180 个** `face_clusters.member_count` 与实际成员数不符（均为历史代际：存储 405 / 实际 0）。任何"删照片后成员关系级联消失"的路径都会**再次制造这种失真**——这是必须在新功能里显式处理的既有问题，不是新功能引入的。

---

## 5. 功能 A：删除选定批次的名单及记录

### 5.1 范围解析（以识别运行为锚点）

```
运行 R 的"名单" = DISTINCT person_id FROM cluster_person_assignments
                  JOIN face_clusters ON cluster_id
                  WHERE face_clusters.run_id = R AND person_id IS NOT NULL
```
（`cluster_assignment_repository.list_by_cluster_run(cluster_run_id)` 已能按**聚类代际**取指派行，但按**识别运行**需跨代际汇总——`list_confirmed_person_ids(cluster_run_id)` 只给 confirmed/auto_confirmed，而 A 的范围应含全部状态，需要新增一个按运行聚合的读取口。）

当前库中：运行 `bb94edc4` 的名单 = **空**（尚无指派行）；运行 `586365ec` 的名单 = **1 人**（带 36 条指派行）。

### 5.2 级联清单（删 people 行时）

| 表 | 行为 | 后果 |
|---|---|---|
| `cluster_person_assignments` | **CASCADE**（`person_id`） | 跨**所有代际**的该人决策行全灭，包括其它运行的确认结论 |
| `person_face_embeddings`（多样本库） | **CASCADE** | 该人的样本库清空（当前 0 行，GT 采样后会成为实质损失） |
| `person_embeddings`（遗留） | CASCADE | 清空 |
| `recognition_results.person_id` | **SET NULL** | 识别记录**保留**，归属变为"未分配"——不删照片时仍在 |
| `archive_records.person_id` | SET NULL | 已归档记录保留，丢失人员指向 |
| `calibration_ground_truth.person_id` | **SET NULL** | **GT 裁定行保留但失去人名指向**——身份证据被削弱，不可恢复 |
| `calibration_annotations.person_id` | SET NULL | 同上 |
| `import_draft_rows.merge_target_id` | SET NULL | 导入草稿的合并目标失联（草稿本身在） |
| `people` | DELETE | 名册行消失 |

### 5.3 三种可选语义

| 选项 | 行为 | 适用 | 代价 |
|---|---|---|---|
| **A1（轻）** | 只删该运行产生的**指派行**（`cluster_person_assignments`），保留人员与其余记录 | 只想"撤销这批次的匹配结论"，人员档案保留 | 决策行按项目惯例"只增改不删"（`cluster_assignment_repository.py` 文档明确"决策行只增改状态不删（历史可追溯）"）——删除会破坏该不变量的精神 |
| **A2（中）** | 删**该运行相关的指派行**，人员保留、记录保留 | 同上但范围更精确 | 同 A1 的历史可追溯问题 |
| **A3（重）** | 删**人员实体**及其全部级联记录 | 彻底清场（与既有「按批次删除…」语义一致） | 跨代际决策、样本、GT 人名指向全灭；不可恢复 |

**推荐 A3 + 强制披露 + 可选降级到 A1**：默认按 A3 执行（与既有删除人员的级联披露范式一致），在对话框里把"连带删除 N 条跨代际指派、M 条样本、K 条 GT 指向"逐项列出并要求显式勾选知悉；同时提供一个"仅解除该批次匹配（保留人员）"的次级选项覆盖 A1 需求。

### 5.4 与既有「按批次删除…」的关系

既有实现按 `people.source_batch_id` 解析当前归属，**执行时点重算**（合并/迁移会改写归属），语义严谨。新功能按运行解析，是**另一维度**，两者不冲突。建议：

- 保留既有按钮，不动其语义；
- 新按钮与识别运行下拉同区，明确命名区分，例如「删除该运行名单…」/「删除该运行照片…」，避免两个"批次删除"混淆；
- 来源批次下拉当前存在**同名歧义**（库里 5 个 `import_batches` 都叫 `名单_test.txt`，标签只有 `文件名（人数）`，见 `ui_text.py:117`），4 个 draft 批次都显示"（0 人）"，Owner 无法区分——建议顺手把标签改为 `文件名（人数）· 创建时间 · 状态`，否则新的删除入口也会踩同一个坑。

---

## 6. 功能 B：删除选定批次的照片及记录

### 6.1 范围解析

```
运行 R 的照片 = recognition_run_photos WHERE run_id = R 的 photo_id 集合
```
当前唯一可用：`bb94edc4` → 473 张（其中 472 张有观测，1 张无脸）。

**C-1 适用**：历史运行快照为空 → 对话框显示"该运行没有照片快照记录（快照自 004 版本起才写入），无法按批次删除照片"，并可提供降级路径"改为删除该运行派生出的照片集合"（由 `face_observations.run_id` 反推）——但对当前库这三条运行派生集合也是空。

### 6.2 级联清单（删 photos 行时）

| 表 | 行为 | 后果 / 风险 |
|---|---|---|
| `recognition_results` | **CASCADE** | **401 条识别记录全部消失**（当前均为 pending）。归档管线只消费 APPROVED 记录（`PROJECTION_SUPPORT_STATUSES={confirmed}` 的对应链路），一旦转 approved 再删照片，**归档能力随之丧失且不可恢复** |
| `archive_records` | **CASCADE** | 归档索引行消失，但**归档目录里的实体文件仍在** → 产生无索引孤儿文件（当前 0 行，风险为未来态） |
| `face_observations` | **CASCADE** | 该批 1441 条观测消失 |
| `face_cluster_members` | CASCADE（经观测） | 簇成员关系消失 → **`face_clusters.member_count` 再次失真**（C-3 已有 180 个失真簇） |
| `cluster_person_assignments` | 不受影响（按 cluster_id 级联） | **已确认/自动确认的指派行会留下，但簇已空** → 名册"匹配状态"仍显示已匹配，实际已无照片支撑，属**误导性残留** |
| `person_face_embeddings` | CASCADE（经观测） | 人员的多样本库对应样本消失（当前 0 行） |
| `recognition_run_photos`（**其它运行**） | CASCADE（按 photo_id） | 其它运行的输入快照行被抹掉。当前库**无跨运行重叠照片**（实测 0），但一旦有重叠，删除会静默破坏其它运行的历史快照 |
| `photo_ignore_states` | CASCADE | 忽略标记消失（当前 0 行） |
| `folders.total_photos` / `scanned_photos` | 不更新 | 目录统计字段可能失真（需确认扫描器是否每次重算） |
| 磁盘原件 | **不删**（D3） | 照片文件保留在原处；**缩略图缓存**会变孤儿，但已有对账式清理通道 `CleanupThumbnailCacheService`（按当前照片库比对缓存键）可收尾，无需新代码 |

### 6.3 建议的执行策略

1. **单事务**：照片行删除 + 簇成员计数修正 + 该运行的聚类代际处置 + 其它运行快照行处置，全部在一个 UoW 内（对齐 `execute_batch` 的既有范式）。
2. **簇计数修正**：删除后重算受影响簇的 `member_count`（同时修 `face_cluster_runs.member_count`），避免制造 C-3 式失真。**注意：这是既有缺陷的顺带修复面，建议单独一个提交并单独测试，不要混进本功能**。
3. **指派残留**：建议在同一事务内把"簇已空"的 confirmed/auto_confirmed 指派行迁移为 `unassigned`（**改状态而非删行**，符合"决策行只增改不删"惯例），否则名册匹配标记会撒谎。
4. **其它运行快照**：预览里显式披露"另有 N 条其它运行的快照行会随之消失"；当前为 0，但这是"不可恢复"级别的信息，必须显示。
5. **归档与 GT 保护**：若目标照片存在 `archive_records` 或 `calibration_ground_truth`，**硬阻断**（禁用执行按钮并说明原因），而不是只给一个勾选项——理由：归档目录已有实体文件、GT 是身份裁定证据，两者删了都不可能靠重新识别还原。当前库两者均为 0 行，因此不阻断现状。
6. **磁盘文件**：对话框固定文案"只移除库内登记，磁盘上的照片文件全部保留"（复用 `DELETE_PHOTOS_CONFIRM` 措辞）。

### 6.4 是否连带删除该运行的聚类代际？

`recognition_runs` / `face_cluster_runs` / `face_clusters` 三层是否一并删除，**取决于"记录"的口径**：

| 选项 | 行为 | 后果 |
|---|---|---|
| B1（默认，推荐） | 只删照片及其级联；保留运行行、聚类代际、簇行（簇变空） | 运行历史与代际统计保留，但留下空簇壳；下拉框里仍能看到该运行 |
| B2 | 同时删除该运行的聚类代际（`face_cluster_runs` → `face_clusters` → 指派行级联） | 彻底清场，但**该运行在聚类结果对话框里的历史代际消失**，指派行（含 confirmed）被级联删除，人员可能被"空指派" |
| B3 | 连 `recognition_runs` 行一起删 | 运行本身从下拉框消失；该运行的 `recognition_run_photos`（本批次快照）级联消失。当前 `recognition_runs` 无外键指向其它表，删除安全，但会丢失运行配置快照 `parameters`（不可重建的审计信息） |

**推荐 B1 + 空簇清理选项**：默认 B1 保证"运行历史可审计"，另给一个显式勾选"同时清理该运行的空簇与聚类代际"（≈B2）覆盖彻底清场需求。

---

## 7. UI 与交互设计

### 7.1 入口位置

放在**识别运行下拉同一行**（`people_admin_page._build_clustering_ui`，`people_admin_page.py:853-884`），紧邻现有「重新运行聚类」「查看聚类结果」：

```
识别执行  [2026-10-28 17:07 · 已完成 · 1441 张脸 ▾]  [重新运行聚类] [查看聚类结果]  |  [删除该运行名单…] [删除该运行照片…]
```

- 无选中运行 / 运行无可删对象时按钮**禁用**并给出原因提示（空态不静默）。
- 危险按钮统一 `ROLE_DANGER`（`presentation/visual_style.py`），与既有删除按钮一致。

### 7.2 对话框范式（沿用项目已确立的"预览 → 披露 → 知悉勾选 → 执行 → 如实回执"）

```
┌ 删除该运行的照片 ─────────────────────────────┐
│ 运行：2026-10-28 17:07 · 已完成 · 1441 张脸      │
│ 照片 473 张 · 识别记录 401 条 · 观测 1441 条    │
│ 簇成员关系 405 条 · 其它运行快照 0 条             │
│ ⚠ 归档记录 0 条 · GT 裁定 0 条 · 样本 0 条       │
│ ☐ 我已知悉：以上记录将从库中永久移除，界面内无撤销 │
│ ☐ 同时清理该运行的空簇与聚类代际                  │
│                          [移除登记(危险)] [取消] │
└─────────────────────────────────────────────────┘
```

- 确认按钮默认焦点在**取消**（既有 `photo_deletion_confirm_dialog.py:77` 范式：误按 Enter 不执行删除）。
- 执行结果按实际完成状态回报（成功数/跳过数/失败原因），沿用 `BATCH_DELETE_DONE` 的如实反馈模式。

### 7.3 与既有删除入口的职责划分

| 入口 | 锚点 | 语义 |
|---|---|---|
| 「按批次删除…」 | 名单导入批次 | 该批次**当前归属人员** + 可选批次记录/草稿 |
| 「删除该运行名单…」（新） | 识别运行 | 该运行**身份指向的人员** + 其级联记录 |
| 「删除该运行照片…」（新） | 识别运行 | 该运行**照片登记** + 其级联记录 |

三者在界面上并列可能造成概念负担，建议：前两个"名单类"操作在文案上明确区分「名单来源批次」与「识别运行批次」。

---

## 8. 代码落点与事务边界

### 8.1 新增（建议）

| 层 | 文件 | 内容 |
|---|---|---|
| 命令 | `application/commands/deletion.py` | `DeleteRunPeopleCommand(run_id, delete_people: bool)` / `DeleteRunPhotosCommand(run_id, purge_cluster_generations: bool)` |
| DTO | `application/dtos/deletion.py` | `RunPeopleDeletionPreview/Result`、`RunPhotosDeletionPreview/Result`（含全部级联计数） |
| 用例 | `application/use_cases/deletion.py` | 对应 UseCase 协议 |
| 服务 | `application/services/delete_run_service.py`（或拆两个） | 预览（无副作用）+ 事务执行 + `AUDIT` 日志 |
| 端口 | `domain/repositories/*.py` | ①按**识别运行**聚合指派人员/指派行的读取口（现有只有按聚类代际）②按运行列出照片快照（`recognition_run_repository.list_run_photos` 已够）③簇计数修正写口（`face_cluster_repository` 需新增 `update_cluster_member_count` / `update_cluster_run_member_count`） |
| 视图 | `presentation/views/batch_run_deletion_dialog.py`（新） | 两个对话框（或一个带模式参数的对话框） |
| 文案 | `presentation/ui_text.py` | 新增预览/结果文案；**同时修正来源批次标签歧义**（§5.4） |
| 装配 | `app/services.py` | 新服务与 UoW 注入（与 `delete_person_service` 同款） |

### 8.2 事务边界

- 预览在事务外只读；**执行在单个 `SQLiteUnitOfWork` 内**完成：人员/照片删除 + 批次记录清理 + 簇计数修正 + 指派状态迁移 + 其它运行快照处置，全部成功才提交，任一失败整体回滚（对齐 `execute_batch` 的既有语义）。
- 幂等：不存在的运行、空快照、空名单一律计为 `missing`/`empty` 并在回执中如实说明，不静默成功。

### 8.3 审计日志

沿用既有格式：
```
AUDIT delete-run-photos actor=local-user run=<id> removed=473 recognition_cascade=401
     observation_cascade=1441 member_cascade=405 other_run_snapshot_cascade=0 missing=0
```

---

## 9. 测试计划

| 层级 | 用例要点 |
|---|---|
| 服务单测 | 预览无副作用、计数口径、空态（无快照/无名单）返回明确空态而非静默成功 |
| **SQLite 集成测试**（级联语义的唯一裁判） | 真实外键下验证：删照片 → 识别/观测/成员/样本/忽略态/其它运行快照全部按预期级联；删人员 → 指派 CASCADE、识别记录 SET NULL、GT SET NULL；事务失败整体回滚 |
| 簇计数回归 | 删除后 `face_clusters.member_count` 与实际成员一致；`face_cluster_runs.member_count` 一致 |
| 指派残留回归 | 空簇上的 confirmed 指派迁移为 `unassigned`；决策行**不被删除**（守住"决策行只增改不删"不变量） |
| UI 测试 | 按钮禁用态、对话框披露字段、知悉勾选前确认按钮禁用、取消默认焦点、回执文案与实际计数一致 |
| 回归 | 既有删除路径（单人/名单批次/清空/照片选中/按建议处置）不受影响；全量测试串行跑（勿与定向测试并行，历史上有 `aud023` 假失败） |

---

## 10. 待 Owner 裁定的决策表

| # | 决策 | 选项 | 推荐 | 影响 |
|---|---|---|---|---|
| D1 | "批次"锚点 | ①识别运行 ②名单导入批次 | ①识别运行 | 决定 A 是否为重复建设 |
| D2 | A 的语义 | A1 只删指派行 / A3 删人员实体 / 两者可选 | A3 默认 + A1 可选 | A1 需面对"决策行不可删"的不变量 |
| D3 | A 的范围是否含跨代际 | 仅本运行 / 该人员全部代际 | 后者（外键强制） | 无法只删本运行指派而不动其它代际的同一人指派 |
| D4 | B 是否连带删除聚类代际 | B1 保留 / B2 删代际 / B3 连运行一起删 | B1 + 可选 B2 | 影响运行历史可审计性 |
| D5 | 归档/GT/样本存在时 | 仅警告 / 硬阻断 | **硬阻断** | 决定按钮是否可点 |
| D6 | 空簇上的 confirmed 指派 | 迁 `unassigned` / 删行 / 不处理 | 迁 `unassigned` | 不处理会让名册匹配标记撒谎 |
| D7 | 簇计数修正 | 本功能内顺带修 / 独立提交 | **独立提交** | 混入会让本功能回归面变大 |
| D8 | 磁盘原件 | 不删（D3）/ 提供"连磁盘一起删" | **不删** | 破坏既有不变量，且不可逆 |
| D9 | 其它运行共享照片 | 一并删除 / 排除共享者 | 一并删除 + 披露数量 | 当前 0 张，无实际差异，但需写死披露 |
| D10 | 来源批次同名歧义 | 本轮顺带修标签 / 单独排期 | 本轮顺带修（低成本） | 影响三个批次入口的可辨识性 |

---

## 11. 明确不做（Out of Scope）

- 不删除磁盘上的照片原件（守 D3）。
- 不提供界面内撤销（既有删除路径同样没有；如需可依赖既有 DB 备份机制）。
- 不做跨运行的"照片去重合并"（另案）。
- 不改写"决策行只增改不删"的项目不变量；A1 以"迁状态"方式实现而非物理删除。
- 不在未获裁定前动代码。

---

## 12. 风险登记

| 风险 | 等级 | 缓解 |
|---|---|---|
| 识别记录 CASCADE 后无法重新识别还原（除非重跑识别，但重跑会产生新运行、新 id） | 高 | 执行前强制披露；归档/GT/样本非空时硬阻断 |
| 人员删除使 GT 人名指向丢失（`calibration_ground_truth.person_id` SET NULL） | 高 | 同上；GT 非空时硬阻断 |
| 制造新的簇计数失真 | 中 | 删除后重算（独立提交） |
| 空簇残留 confirmed 指派导致名册状态撒谎 | 中 | 迁 `unassigned` |
| 同名导入批次不可辨识导致误删 | 中 | 修标签（文件名·时间·状态） |
| 历史运行无快照，B 对其不可用 | 低（已知） | 明确空态提示，不静默 |
| 既有缺陷干扰判读：216 簇中 180 个计数已失真、36 条指派集中指向 1 人 | — | 属既有状态，建议在实施前记录基线，实施后对比增量 |

---

## 13. 实现记录（2026-10-29）

Owner 裁定（2026-10-28 会话）：**D1~D5 按推荐方案执行，同意 D10 标签改造**；D6~D9 按讨论稿推荐默认值落地。

### 13.1 落地清单

| 裁定 | 落地 |
|---|---|
| D1 锚点=识别运行 | 两个入口按钮挂在人员名册页底部「人脸聚类」组的识别运行选择器同一行：「删除该运行名单…」「删除该运行照片…」 |
| D2 A3 默认 + A1 可选 | 对话框内单选：默认「删除该运行指向的人员及其记录」；可切换「仅解除该运行的匹配关系，保留人员」（状态迁移实现，复用 `PairingWorkbenchService.unassign` 的完整语义：投影回收 + 样本停用） |
| D3 跨代际范围 | 人员删除级联覆盖该人员跨所有代际的决策行（外键既定语义，预览披露"跨所有代际"） |
| D4 B1 默认 + B2 可选 | 默认保留运行历史与代际；「同时清理该运行的聚类代际」勾选项先披露"代际/簇/决策行级联删除"再允许勾选 |
| D5 硬阻断 | 归档记录 / GT 裁定 / 样本库任一非空 → 执行按钮禁用 + 阻断原因逐条展示 + execute 二道门（`ValidationError`）。A1 模式不删证据，不受阻断 |
| D6 空簇决策迁移 | 受影响代际的空簇上 confirmed/auto_confirmed/suggested 有效行迁为 `unassigned`（改状态不删行）；purge 模式跳过（决策行随代际级联删除，已在勾选警告中披露） |
| D7 计数修正独立面 | 簇/代际计数回写只修**本次操作弄坏的代际**（删除前判定受影响代际），不清扫 180/216 的存量失真 |
| D8 磁盘不动 | 服务不接收文件系统依赖（与既有删除服务同不变量）；对话框固定文案"不会删除磁盘上的任何照片文件" |
| D9 共享照片一并删+披露 | `count_other_run_snapshots` 端口统计其它运行引用同一批照片的快照行数，预览与回执均披露 |
| D10 标签改造 | `import_batch_entry_label()`：`文件名 · 创建时间 · 状态（N 人）`；名册页来源批次下拉与「按批次删除…」对话框共用；同名批次可区分 |

### 13.2 新增/修改面

- **迁移 016**（`alembic/versions/016_empty_cluster_member_count.py`）：`face_clusters.member_count` CHECK `>= 1` → `>= 0`（表重建，沿用 013 的 rename/copy/drop 模式 + `legacy_alter_table=ON`）。同步放宽实体校验 `FaceCluster.__post_init__`。理由：照片删除后**空簇是合法状态**，计数必须能表达真实值（存量 180/216 失真正是旧约束无法表达"空"的副产品）。
- **端口扩展**：`FaceClusterRepository.update_cluster_member_count / update_cluster_run_member_count / remove_cluster_run`；`RecognitionRunRepository.count_other_run_snapshots`；`PersonFaceSampleRepository.list_by_observation_ids`（各含 SQLite + InMemory 实现）。
- **应用层**：`DeleteRunPeopleCommand/DeleteRunPhotosCommand`（含 `RUN_PEOPLE_MODE_*` 常量）、`RunPeopleDeletionPreview/Result`、`RunPhotosDeletionPreview/Result`、`DeleteRunPeopleService`、`DeleteRunPhotosService`（各自持有**唯一** UnitOfWork——SQLite 不支持嵌套事务，两服务不复用 `DeletePersonService.execute`）。
- **表示层**：`run_deletion_dialog.py`（`RunPeopleDeletionDialog` / `RunPhotosDeletionDialog`，沿用"预览→披露→知悉勾选→事务执行→如实回执"范式，取消持默认焦点）；`people_admin_page` 两个入口按钮；`ui_text` 新文案组。
- **测试**：`tests/integration/test_run_scoped_deletion_sqlite.py`（11 例：级联/计数回写/空簇迁移/purge/硬阻断/幂等）、`tests/integration/test_migration_016_empty_cluster_member_count.py`（2 例：重建零丢失 + 降级应急路径）、`tests/unit/presentation/test_run_deletion_dialog.py`（9 例）。

### 13.3 实施中发现并修正的问题

- **计数回写时序 bug**（集成测试抓到）：照片删除发生在簇计数重算**之前**时，成员行已被级联清空，无法再反推受影响代际——受影响代际判定必须前置到删除前。
- **CHECK 违反**（集成测试抓到）：计数回写 0 时触发 `member_count >= 1` 的建表 CHECK——催生迁移 016。
- **purge 模式无效功**：B2 时计数回写与空簇迁移都被随后的代际删除吞掉——跳过并如实报 0。

### 13.4 已知限制（如实声明）

- **D5 硬阻断会让功能在 GT/样本/归档出现后不可用**：这是 Owner 批准的口径（不可恢复证据优先）。若后续要放宽，改点在两个服务的 `preview()` 的 `blocked` 判定（一处/服务）。
- **运行统计列保留历史值**：删除照片后 `recognition_runs.face_count` 等统计列不动（描述"该运行当时做了什么"），下拉框仍显示旧脸数——已在对话框文案中说明。
- **目录照片统计**：`folders.total_photos/scanned_photos` 在下次扫描前保持旧值——已在回执文案中说明。
- 存量失真（180/216 簇计数、36 条指派集中指向 1 人）不属于本功能清理范围。
