# Stage 2 — PhotoArchiver 业务规则与状态模型重建

> **依据**：当前仓库 HEAD `2823d1c7ceaab09c38d39b9a80e1e724839cfa17`（2026-09-28 01:44:20 +0800，`fix: resolve business baseline freeze blockers`）。Stage 1 报告仅作分析输入，本文件全部关键结论已回查一手证据（源码/迁移/测试/计划文档）。
> **基线收口（2026-09-28）**：原基于 `b3b8685`；`2823d1c` 落地 Stage 4 BLK-1/BLK-5 修复与 D-1/D-2 裁决，`pairing_workbench_service.py`（+11/+16 行）、`pairing.py`、`sqlite_recognition_repository.py`、`review_recognition_service.py`、`archive_planner.py`、`recognition.py`、`ui_text.py` 及被引测试文件行号漂移。本修订版已把**全部受影响引用按当前 HEAD 重新核对改写**，D-1/D-2 结论已统一。行号为 HEAD `2823d1c` 版本行号。
> **方法**：只读审计；未运行 pytest（"测试通过"一律按 UNKNOWN 处理，标记中的 TESTED 仅指存在对应测试断言）；未修改代码/数据库/测试/文档；未提交 Git。
> **标记**：IMPLEMENTED（代码可执行且被生产调用）/ PARTIAL（存在但有缺口或未接线）/ PLANNED（仅存在于计划文档）/ TESTED（存在对应测试断言）/ INFERRED（由代码推导的非声明结论）/ UNKNOWN（无仓库证据可确认）。
> **引用格式**：`路径:行号`（行号为 HEAD 版本）。规则带稳定编号：RO 名单 / RE 识别 / CL 分组 / PR 配对 / RR 重跑 / HI 历史 / AR 归档 / CM 兼容链。

---

## 1. 核心业务规则

> 本节是全局级"主干规则"；细则见后文分组（§6）、配对（§7）、rerun（§8）、历史（§9）各章。

| 编号 | 规则 | 标记 | 证据 |
|---|---|---|---|
| CORE-01 | 名单落库只有一条正式路径：草稿批次确认（`ConfirmImportService`）；取消不写人员 | IMPLEMENTED+TESTED | `confirm_import_service.py:50-109`；`tests/integration/test_import_draft_flow.py:147,165` |
| CORE-02 | 识别运行对手照片产出"全部人脸"观测（不再 Top-1 截断），统计数据与观测分离 | IMPLEMENTED+TESTED | `run_recognition_service.py:104-133`；`tests/unit/application/test_run_recognition_service.py:43` |
| CORE-03 | Stage C–E 全流程追加式：run/观测/聚类/建议恒写新行，历史永不改写；**唯一被改写的是 `recognition_results`**（审核状态迁移、配对回收 DELETE） | IMPLEMENTED+TESTED | `run_recognition_service.py:47`；`cluster_faces_service.py:70`；迁移 004/006/007 docstring；`pairing_workbench_service.py:347-374` |
| CORE-04 | 系统自动只到 `suggested`；`confirmed` 必须要人工动作（确认/指派） | IMPLEMENTED+TESTED | `domain/services/pairing.py:15`；`tests/unit/domain/test_stage_e_pairing_domain.py:42` |
| CORE-05 | **`recognition_results` APPROVED 是进入归档的唯一门票**；观测/簇/指派对归档不可见 | IMPLEMENTED+TESTED | `archive_planner.py:116,167`；`tests/unit/application/test_stage_e_remediation.py:364,398` |
| CORE-06 | 归档成功态去重作用域 = `(person_id, photo_id)`。**Stage 4 BLK-1 修复后由稳定 `person_id` 判定**（migration 008 增 `archive_records.person_id`）；`person_id IS NULL` 的存量行回退按 `target_person_name` 匹配。同一照片可归于多人目录，且同名不同人互不抑制、人员改名后不重复归档。**已知限制（Stage 4.1 KL-1/KL-2）**：存量重名归档行与**人员删除后 `person_id` 被置 NULL 的孤儿行**仍按姓名回退去重——"删人 + 同名重建"场景可能被静默抑制，属升级前行为原样保留 | IMPLEMENTED+TESTED（Stage 4 重验） | `sqlite_archive_record_repository.py:107-138`；`sqlite_recognition_repository.py:219-241`（workspace counter 同口径）；`alembic/versions/008_archive_identity_and_confidence.py`；`tests/unit/application/test_freeze_blockers.py` |
| CORE-07 | 配对确认是第二生产 `recognition_results` 的来源（APPROVED 投影），且会沉淀多样本；两操作随解除/改派被对称回收 | IMPLEMENTED+TESTED | `pairing_workbench_service.py:105-137,185-229,276-374`；`test_stage_e_remediation.py:251-330` |
| CORE-08 | 人脸"对象"的最小单位是 `FaceObservation`（一次 run × 一张照片 × 一张脸）；同人跨照片 ⇒ 聚类成 `FaceCluster`；同人⇒Person 的绑定只能是 `ClusterPersonAssignment` | IMPLEMENTED | 迁移 004/006/007；`cluster_faces_service.py` |

**CORE 级状态机提要**：详见 §2/§3——runs 五态（created→running→completed|failed|cancelled，终态不可回退）；assignments 四态（suggested 起，confirmed/rejected 降落，unassigned 终）；簇实写三态（pending/unknown/ignored）；`recognition_results` 三态；`import_batches` 实写两态。

---

## 2. 状态模型

| 实体（表） | 状态词汇 | 初值 | 定义处 |
|---|---|---|---|
| `ImportBatch`（import_batches） | `draft` `confirmed` `cancelled` | draft | `domain/entities/import_batch.py:13-19`；迁移 003 |
| `ImportDraftRow`（import_draft_rows） | 无状态机；`action`: `create` `merge_existing` `skip` | create | `import_batch.py:13-19`；迁移 003 |
| `Person`（people） | 无状态机（roster_order 可空整数、source_batch_id 可空、identity 唯一） | roster_order=None | `domain/entities/person.py:15-26`；迁移 003:66-68 |
| `Photo`（photos） | 无状态机（元数据字段、captured_at 可空） | — | 迁移 002 |
| `RecognitionRun`（recognition_runs） | `created` `running` `completed` `failed` `cancelled` | created | `domain/entities/recognition_run.py:24-45`；迁移 004/005 |
| `FaceObservation`（face_observations） | 无状态机，只 `scope_verdict`: `in_selected_scope`/`out_of_selected_scope` | 由 classify_scope 计算 | `domain/entities/face_observation.py:22-26`；迁移 004 |
| `RecognitionResult`（recognition_results） | `pending` `approved` `rejected` | pending | `domain/entities/recognition.py:11-21`；迁移 002；ADR-009 |
| `FaceClusterRun`（face_cluster_runs） | `created` `running` `completed` `failed` `cancelled` | created | `domain/entities/face_cluster.py:31-52`；迁移 006 |
| `FaceCluster`（face_clusters） | `pending` `confirmed` `unknown` `ignored` `split` `merged` | pending | `face_cluster.py:54-69`；迁移 006 |
| `FaceClusterMember`（face_cluster_members） | 无状态机；`source`: `auto`/`manual` | auto | `face_cluster.py:71-73`；迁移 006 |
| `ClusterPersonAssignment`（cluster_person_assignments） | `suggested` `confirmed` `rejected` `unassigned` | suggested | `domain/entities/cluster_assignment.py:31-47`；迁移 007 |
| `PersonFaceSample`（person_face_embeddings） | 无状态机；`enabled`: 1/0 | 1 | `cluster_assignment.py:134-151`；迁移 007 |
| `ArchiveRecord`（archive_records） | `planned` `dry_run` `archived` `skipped` `renamed` `overwritten` `failed` | planned | `domain/entities/archive.py`；迁移 002 |
| person_embeddings（单样本旧表） | 无状态机 | — | 迁移 002:99-105 |

**"当前有效"的定义**：
- assignment 当前有效行 = status ∈ {suggested, confirmed}（`cluster_assignment.py:45-47`），服务层保证同簇至多一行（`pairing_workbench_service.py:268-274`）。
- 归档"已成功"拦截集 = {archived, skipped, renamed, overwritten}（`archive_planner.py:28-33`）——PLANNED/DRY_RUN/FAILED 允许重试。

---

## 3. 状态转换

### 3.1 RecognitionRun（IMPLEMENTED+TESTED）
```
created → running → completed | failed | cancelled
```
- 仅 `start()/complete()/fail()/cancel()` 可转换；终态再转换抛 `ValidationError`（`domain/entities/recognition_run.py:110-158`）。
- `complete/cancel/fail` 把 `RecognitionRunStats`（faces/unreadable/no_face/error/in_scope/out_of_scope 六计数）写入 run 的统计列；`finished_at` 落地。
- `parameters`（创建时不可变快照）永不被 `update_run` 更新（`sqlite_recognition_run_repository.py:81-119`）。
- 测试：`tests/unit/domain/test_stage_c_commit1.py:68`（状态机与终态守卫）。

### 3.2 FaceClusterRun（IMPLEMENTED+TESTED）
与 3.1 同形五态机（`face_cluster.py:104-150`）。`complete` 携带 (cluster_count, member_count, excluded_count)；`cancel` 可携带部分统计（已落库的簇保留）；测试 `test_cluster_faces_service.py:177,192,216`。

### 3.3 FaceCluster.status（PARTIAL — 六态定义、三态实写）
- 定义 6 态（`face_cluster.py:54-69`）；实际写路径只有：
  - 创建 → `pending`（`cluster_faces_service.py:176-183`）
  - 工作台"标记陌生人/忽略组" → `unknown`/`ignored`（`pairing_workbench_service.py:233-244`）
- `confirmed`/`split`/`merged` **无任何写入者**（全仓 grep 无 MergeClusters/SplitClusters 服务）。
- 注意：**确认配对不会改变簇状态**（confirm 只动 assignment；`face_clusters` 行保持 pending）。

### 3.4 ClusterPersonAssignment（IMPLEMENTED+TESTED）
```
suggested → confirmed（人工确认，存 sort_snapshot + confirmed_at）
suggested → rejected（人工拒绝）
suggested → unassigned（撤回建议）
confirmed → unassigned（解除/改派前置）
rejected  → unassigned（撤销拒绝）
unassigned → （终态，无出边）
```
- 非法转换抛 `ValidationError`（`cluster_assignment.py:60-71,125-131`）；同簇决策历史以多行表达（`list_by_cluster` 按 created_at DESC）。
- 测试：`test_stage_e_pairing_domain.py:42-92`（状态机矩阵）、`test_stage_e_pairing_services.py:256,272`。

### 3.5 RecognitionResult（IMPLEMENTED，有一条特殊旁路）
```
pending → approved（审核通过）
pending → rejected（审核拒绝）
```
- `approve()/reject()` 只允许 pending 起点（`recognition.py:60-75`）。
- **旁路**：配对确认以 `status=APPROVED` 直接构造新行（`pairing_workbench_service.py:338-343`），绕过实体状态机（`__post_init__` 不校验初始状态）。这是有意设计（E-SG-6 兼容投影），但意味着表内存在"未经 pending 的 APPROVED"行。

### 3.6 ImportBatch（PARTIAL）
- `draft`（创建，`parse_import_draft_service.py:79`）→ `confirmed`（`confirm_import_service.py:96-98`）。
- `cancelled` **永不写入**（无调用者；取消仅保留 draft 现状）。

### 3.7 ArchiveRecord（IMPLEMENTED+TESTED）
`planned → dry_run | archived | skipped | renamed | overwritten | failed`（executor 的双段写：INSERT planned → 执行 → 更新终态，`archive_executor.py:93-101,118-242`）。测试 `test_step11_archive_e2e.py`。

---

## 4. 条件分支

### 4.1 人员名单（RO 系列）
| 编号 | 规则 | 标记 | 证据 |
|---|---|---|---|
| RO-01 | `roster_order` 可空整数、**不唯一**（迁移只加列+索引，无 UNIQUE）——"用户确认的名单顺序" | IMPLEMENTED | `003_import_batches_and_roster.py:66-68`；计划 A-1 明说"唯一性不强制" |
| RO-02 | 展示顺序：有序者按 roster_order 升序，无顺序者（NULL）排后按 (created_at, name, id) 兜底 | IMPLEMENTED+TESTED | `sqlite_person_repository.py:109-117` |
| RO-03 | 确认导入按草稿 `order_index` 升序逐行，`order_seq` 从全局 `MAX(roster_order)+1` 续号（跨批次单调，owner F-A1/LIMIT-007 裁决） | IMPLEMENTED+TESTED | `confirm_import_service.py:55-76`；`test_import_draft_flow.py:198` |
| RO-04 | **合并会改顺序**：`merge_existing` 或确认时发现 DB identity 重复，都会执行 `_attach_roster`：覆盖 `roster_order=order_seq`、`source_batch_id=新批次` → 重新导入同一名单 = 该批人员整体按新批次行序重排到名单尾部 | IMPLEMENTED（重排后果 INFERRED） | `confirm_import_service.py:82-85,111-151`；bulk 测试只断言合并数不断言最终位置 |
| RO-05 | `skip` 行零写 people | IMPLEMENTED+TESTED | `confirm_import_service.py:74-76` |
| RO-06 | 行级校验错误隔离：错误入 `errors`（带行号），其余行继续 | IMPLEMENTED+TESTED | `:87-88`；`test_import_draft_flow.py:177` |
| RO-07 | 事务边界：people 批写在 UoW 内，批次状态翻转 `confirmed` 在 UoW **之外**（两事务） | IMPLEMENTED | `confirm_import_service.py:90-98` |
| RO-08 | 人员页手工新增：`roster_order = MAX+1` 追加 | IMPLEMENTED+TESTED | `manage_people_service.py:81`；`test_manage_people_service.py` |
| RO-09 | 人员页重排：传入整表 id 序列 → 写位置 1..N（`enumerate(...,1)`），单事务；拒绝重复 id 与不存在 id | IMPLEMENTED+TESTED | `manage_people_service.py:113-139`；`sqlite_person_repository.py:125-135` |
| RO-10 | 删除人员：**不重排**其余人员，序号空洞保留（代码中无任何压实/重编号路径） | IMPLEMENTED（代码缺失）+INFERRED（效果） | `sqlite_person_repository.py:71-80`；`delete_person_service.py` |
| RO-11 | 工号 identity 全库唯一：DB UNIQUE + 服务二次校验（重复 → "工号已被其他人员占用"）；确认期 DB 撞单降级为 merge 而非硬失败 | IMPLEMENTED+TESTED | 迁移 002 `identity TEXT UNIQUE`；`manage_people_service.py:172-180`；`confirm_import_service.py:82-85,113-118` |
| RO-12 | 姓名+部门精确匹配（NULL 安全 `department IS ?`）仅是 merge 目标解析链的一环 | IMPLEMENTED | `confirm_import_service.py:136-140`；`sqlite_person_repository.py:88-99` |
| RO-13 | `roster_order` 的业务含义：①名单页展示序 ②照片库筛选人员轴顺序 ③**配对规则③的人员顺序轴**（见 §7）④批次来源回看列 | IMPLEMENTED | `suggest_pairings_service.py:117`；`list_persons_service.py` |
| RO-14 | 拆分多名单元格：每段成一行，仅当只有 1 段时保留 `parsed_identity`（多段置空防重复冲突） | IMPLEMENTED+TESTED | `parse_import_draft_service.py:129-142`；`test_import_draft_flow.py:110` |
| RO-15 | 批次状态：draft → confirmed；cancelled 定义未用；草稿批次/行**永不自动清理** | IMPLEMENTED（清理缺失） | `import_batch.py:13-15`；grep 无写入者；PROJECT_STATUS 边界登记 |
| RO-16 | 确认执行方式：行数 ≤500 在窗口线程同步执行，>500 走 Worker（任务名 `import_confirm`） | IMPLEMENTED+TESTED | `import_preview_dialog.py:44`；`main_window.py:1127-1148`；`test_bulk_people_import_closed_loop.py:102` |
| RO-17 | 历史人员回填：只补 `source_batch_id IS NULL` 的存量人员；创建 `source_type='backfill'` 批次；已有顺序不覆盖（COALESCE），无序者按 (created_at, id) 接全局最大之后；幂等 no-op | IMPLEMENTED+TESTED | `backfill_historical_people_service.py:72-148`；`test_stage_f_services.py:83-148` |

### 4.2 识别入场分支（RE，门禁与范围）
| 编号 | 规则 | 标记 | 证据 |
|---|---|---|---|
| RE-G1 | UI 识别前经就绪门：无人→去导入；无照片→去扫描；模型包缺→不可用（拒绝） | IMPLEMENTED+TESTED | `workspace_controller.py:42-64`；`test_workspace_readiness.py` |
| RE-G2 | 照片范围三选一：全部（默认）/ 当前选中 / 重试上一终态 run 的失败照片 | IMPLEMENTED+TESTED | `recognition_scope_dialog.py:75-91,142-149`；`main_window.py:1440-1450` |
| RE-G3 | 人脸数范围：可多选（预设 [1] [2-3] [4-5] [6-10] [11+] 默认全勾），空选禁止提交 | IMPLEMENTED+TESTED | `recognition_scope_dialog.py:34-40,130-135`；`face_count_range.py` |
| RE-G4 | **不再过滤"已有结果"的照片**：每次提交整份快照、全量重检（与旧 CLI 链路的续跑语义相反） | IMPLEMENTED+TESTED | `recognition_run_controller.py:60-105`；`test_recognition_entry_migration.py` |
| RE-G5 | 重试运行取数：retryable = run_photos − 有观测照片；**重试不在参数里留 "retry" 标签**（`scope_label` 无调用者 → 快照为 "selected"） | IMPLEMENTED（标签缺失为 INFERRED 缺口） | `recognition_failure_service.py:80-94`；`recognition_run_controller.py:99-104`；`main_window.py:1451-1454` |
| RE-G6 | 服务/控制器级拒绝：单航班中、模型包缺、空快照 → 拒绝并落 `last_refusal_reason` | IMPLEMENTED+TESTED | `recognition_run_controller.py:76-91` |
| RE-G7 | CLI `recognize`（旧链路）相反语义：默认只跑无结果照片（`--all` 全量） | IMPLEMENTED | `main.py:674-739` |

---

## 5. 异常规则（含"识别检查清单"逐格答案）

### 5.1 人脸识别场景的逐格事实

| 场景 | 行为 | 会不会建 Observation | 会不会写 compat 行 | 标记 | 证据 |
|---|---|---|---|---|---|
| 0 张脸 | `no_face_count`+1 | 否 | 否 | IMPLEMENTED+TESTED | `run_recognition_service.py:111-113`；`test_run_recognition_service.py:43` |
| 1 张脸 | 1 条观测；若 in-scope 且无历史行 → 1 条 PENDING compat（用该脸匹配） | 是 | 视守卫 | IMPLEMENTED+TESTED | `:114-129` |
| 多张脸（N≥2） | N 条观测，`face_index` 按 (-det_score, x1,y1,x2,y2) 确定性排序；photo_level verdict 共享；compat 只用 `ordered[0]`（最高 det 的脸）走 1:N Top-1 | 是（N 条） | 视守卫 | IMPLEMENTED+TESTED | `:114-123`；ADR-017 |
| 无法读取（ImageUnreadableError） | `unreadable_count`+1；单张隔离不中断批次 | 否 | 否 | IMPLEMENTED+TESTED | `:106-107`；`face_analysis_task.py:40-41`；`test_run_recognition_service.py:43` |
| 检测失败（其他异常） | `error_count`+1；日志隔离；批次继续 | 否 | 否 | IMPLEMENTED+TESTED | `:108-110`；`face_analysis_task.py:42-43`；`test_run_recognition_service.py:85` |
| 部分成功 | 三种失败只计数；run 仍 completed；photo 级不可分辨（失败清单统一归类"未产出人脸观测"） | — | — | IMPLEMENTED（不可分辨为已声明 Spec Gap） | `recognition_failure_service.py:8-18,31` |
| 取消 | 协作式；已 flush 观测保留；run→cancelled（携带已累加统计）；终态后拒绝再转换 | 保留已落库 | — | IMPLEMENTED+TESTED | `run_recognition_service.py:72-94`；`recognition_run.py:134-139`；`test_stage_f_lifecycle.py:122` |
| 重复执行（rerun） | 恒新建 run + 新观测；旧 run/观测不动；详见 §8 | 新行 | 受 ROB-兼容守卫 | IMPLEMENTED+TESTED | `test_run_recognition_service.py:67` |
| run 级未捕获异常 | 已 flush 观测保留；run→failed（记 error）后异常上抛 | 保留已落库 | — | IMPLEMENTED | `run_recognition_service.py:96-102` |

### 5.2 观测唯一性与一致性
- `UNIQUE(run_id, photo_id, face_index)`；INSERT 不含 ON CONFLICT，冲突即 `IntegrityError`（防同 run 重复/覆盖；`sqlite_face_observation_repository.py:26-30`）。IMPLEMENTED+TESTED（`test_stage_c_recognition_repositories.py:80`）。
- 实体不变式：`photo_face_count>=1`、`0 <= face_index < photo_face_count`、`det_score∈[0,1]`、`quality_score∈[0,1] or None`（`face_observation.py:49-64`）。IMPLEMENTED+TESTED（`test_stage_c_commit1.py:41`）。
- 检测线程池只做纯计算，所有 DB 写在消费线程（`face_analysis_task.py:1-6` 注释 + `run_recognition_service.py:68-95`）。IMPLEMENTED。

### 5.3 聚类异常
| 场景 | 行为 | 证据 |
|---|---|---|
| 目标 recognition run 不存在 | `ValidationError` | `cluster_faces_service.py:72-76` |
| 无参与观测 | run completed；(0,0,excluded_count) | `:112-114` |
| 算法取消（进入前/候选阶段/合并阶段） | `ClusteringCancelled` → run cancelled，0 落库 | `:95-99`；`face_clustering.py:41-42,88-89,141-142,175-176` |
| 持久化异常 | run failed + error 后抛出 | `cluster_faces_service.py:100-103` |
| 同簇重复成员 | UNIQUE(cluster_id, observation_id) 即 `IntegrityError` | `sqlite_face_cluster_repository.py:153-176` |

### 5.4 配对/指派异常（IMPLEMENTED+TESTED）
- 确认非 suggested（如重复确认）→ `ValidationError`（`pairing_workbench_service.py:108-111`；`test_stage_e_pairing_services.py:256`）。
- 改派/确认时 cluster/person 不存在 → `ValidationError`（`:248-266`）。
- 行级并发删除（UPDATE 返回 0）→ `ValidationError`（`:123-126,145-148,168-171,192-195,215-218`）。
- 重复沉淀同一 (person, observation) 样本：先查重跳过；存储级 UNIQUE 兜底（`:297-312`；迁移 007）。
- 解除不存在的映射（簇无非 unassigned 行）→ `ValidationError`（`:163-166`）。
- 非法 cluster state → `ValidationError`（`:235-239`）。

### 5.5 归档异常（IMPLEMENTED+TESTED）
- 目标路径已存在：按 `skip（默认）/overwrite/rename`（`archive_executor.py:192-226`；ADR-011）。
- 源文件缺失、目标越界（非 archive_root 之内）→ 该 item FAILED，批次继续（`:139-149,185,233-242,244-276`）。
- 相对路径照片、缺失照片、(person,photo) 已成功归档、person 已删 → 计划期 skip 并计数（`archive_planner.py:111-114,188-210`）。
- 空计划短路（`archive_photos_service.py:97-102`）。

---

## 6. 人脸分组规则（CL 系列）

### 6.1 对象形成
| 编号 | 规则 | 标记 | 证据 |
|---|---|---|---|
| CL-01 | `FaceObservation` 是"人脸对象"的最小持久化单位：一次 run × 一张照片 × 一张脸；同照片在不同 run 里产生各自独立的观测行（不存在跨 run 共用的"人脸"） | IMPLEMENTED | 迁移 004；`face_observation.py` |
| CL-02 | "多张照片中的同一人"通过聚类算法聚合：跨照片、跨观测的 embedding 余弦相似度决定归属；**没有任何其他身份依据**（不知 photo、不知时间） | IMPLEMENTED+TESTED | `face_clustering.py:74-102`；`similarity_kernel` 端口注入 numpy |
| CL-03 | 聚类输入 = 选定 recognition run 的全部观测中，`scope_verdict=='in_selected_scope'` 且 `embedding.vector` 非空者；其余计入 `excluded_count`，不参与成簇 | IMPLEMENTED+TESTED | `cluster_faces_service.py:109-114,230-236`；`test_cluster_faces_service.py:128` |
| CL-04 | 参与观测按 (-det_score, bbox 字典序, observation id) 全序排序后进入算法——同输入恒定同输出（确定性） | IMPLEMENTED+TESTED | `cluster_faces_service.py:239-246`；`face_clustering.py:18-21`；`test_face_clustering_algorithm.py:186` |

### 6.2 算法（cosine-centroid-completelink-v1，owner 裁决 2026-09-25）
| 编号 | 规则 | 标记 | 证据 |
|---|---|---|---|
| CL-05 | 阶段①贪心候选：逐个观测与各候选簇**簇心**余弦相似度 **≥ 0.5**（`cluster_sim_threshold`）者加入最高分的候选簇（同分取最早候选簇）；否则新建候选簇 | IMPLEMENTED+TESTED | `face_clustering.py:74-89,130-155`；`DEFAULT_CLUSTER_SIM_THRESHOLD=0.5`（`:31-35`）；边界测试 `:88` |
| CL-06 | 阶段②完全链接合并：每轮取"跨簇两两最小相似度"最高的候选簇对；**当且仅当该值 ≥ 0.4**（`consistency_threshold`，**含等号**，owner 裁决 D-2）才合并；否则停止 | IMPLEMENTED+TESTED | `face_clustering.py:158-185,171 注释`；边界测试 `test_face_clustering_algorithm.py:238-259`；commit `8d4c342`（含等号修复） |
| CL-07 | 低质量观测（`quality_score < low_quality_threshold`，默认 0.0 = **整门禁用**）可入候选，但不参与跨簇最小相似度证据；无高质量证据对的簇对永不合并（`_NO_EVIDENCE=-inf`） | IMPLEMENTED+TESTED | `face_clustering.py:13-16,120-127,203-220`；`test_face_clustering_algorithm.py:156` |
| CL-08 | 质量分 = `det_score`（检测置信度）的占位公式；"真正 quality 公式待 F 校准"是已知待决，当前 `quality_score` 与 `det_score` 同值 | IMPLEMENTED（占位）+PLANNED（公式） | `run_recognition_service.py:122`；`stage-f-calibration-report.md:35` |
| CL-09 | 链式反例防护：A~B~C 相似但 A~C 不到阈值 → 不并（完全链接 + min 证据） | IMPLEMENTED+TESTED | `face_clustering.py:12,107,118 测试` |
| CL-10 | 每个参与观测恰好归属一个簇（算法保证；存储层防的仅是同簇内重复，跨簇重复在存储层不禁止） | IMPLEMENTED+TESTED | `face_clustering.py` 全程；`test_stage_d_cluster_repositories.py:224` 边界说明 |

### 6.3 排序（方案 §D-3）
| 编号 | 规则 | 标记 | 证据 |
|---|---|---|---|
| CL-11 | 簇排序键 = (最早非空 `captured_at` ISO 文本, 同刻照片的 raw_path 最小者, 创建序 tiebreak)；`captured_at` 全缺的簇统一排末位；**禁用注册时间兜底** | IMPLEMENTED+TESTED | `cluster_faces_service.py:156-183,197-223`；`face_clustering.py:273-301`；`test_cluster_faces_service.py:253,275` |
| CL-12 | `sort_key` 物化为文本 `"{time}\|{path}\|{tiebreak:06d}"`（无时间用 `~`）；`ordinal` 为排序后位次；UI 展示 `第 {ordinal+1} 组` | IMPLEMENTED+TESTED | `face_clustering.py:294-301`；`ui_text.py:409,423` |
| CL-13 | `first_captured_at` 取**成员照片在 run_photos 快照里**的最早非空 captured_at；排序值不会随后续新增照片回写（快照不更新） | IMPLEMENTED+TESTED | `cluster_faces_service.py:197-223`；`sqlite_recognition_run_repository.py:121-143` |
| CL-14 | UI 对无拍摄时间的簇显示 "时间缺失"；计划要求的完整提示 "时间缺失，顺序建议不可靠" 的"顺序建议不可靠"后缀未实现 | IMPLEMENTED（显示）+PARTIAL（提示减半） | `ui_text.py:410`；`cluster_results_dialog.py:171` |

### 6.4 代际与人工操作
| 编号 | 规则 | 标记 | 证据 |
|---|---|---|---|
| CL-15 | 聚类 rerun = 新 FaceClusterRun（新代际）+ 新簇全集；旧代际的簇/成员/指派一行不动；不因已有簇跳过任何项 | IMPLEMENTED+TESTED | `cluster_faces_service.py:69-103`；`test_cluster_faces_service.py:160` |
| CL-16 | 每个代际可调任意参数；**当前 UI 不允许用户改阈值**（命令默认 0.5/0.4/0.0；`scope_filter="in_selected_scope"` 物化进 parameters） | IMPLEMENTED（参数快照）+PARTIAL（无调参入口） | `commands/cluster_faces.py:24-30`；presentation 无阈值控件（grep 无） |
| CL-17 | 人工"合并组/拆分组"**未实现**（服务、命令、UI 均不存在） | PLANNED | 计划 §D-2/§5.2；全仓 grep 零命中 MergeClusters/SplitClusters |
| CL-18 | `member_count >= 1`、簇种子成员 confidence=1.0、入簇=簇心相似度、并簇吸收=并簇证据值 | IMPLEMENTED+TESTED | `face_cluster.py:177-178`；`face_clustering.py:112-117,230-235` |
| CL-19 | `face_clusters.status` 六态已定义；**只写 pending / unknown / ignored**；"confirmed" 有词表无写入路径（确认配对不改簇状态） | PARTIAL | `face_cluster.py:54-69`；`pairing_workbench_service.py:233-244,105-137` |
| CL-20 | 聚类结果查看对话框为**只读**：只列代际、簇、成员 + 缩略图，无任何编辑操作 | IMPLEMENTED | `cluster_results_dialog.py` 全文件无写调用 |

---

## 7. 人员配对规则（PR 系列）

### 7.1 建议生成（自动；命令 `StartSuggestPairingsCommand(cluster_run_id)`）
| 编号 | 规则 | 标记 | 证据 |
|---|---|---|---|
| PR-01 | 建议一次只针对**一个聚类代际**生成；样本库与名单是全库，簇与排除域参数按该代际求值 | IMPLEMENTED | `suggest_pairings_service.py:70-143` |
| PR-02 | **`roster_order` 真正参与配对**：规则③的人员轴按 `roster_order` 升序（无顺序者排有序之后，按 person_id 兜底）；直接保证"名单顺序决定建议顺序" | IMPLEMENTED+TESTED | `domain/services/pairing.py:76-86`；`test_stage_e_pairing_domain.py:224` |
| PR-03 | 规则①样本匹配：对每个尚无有效指派的簇，取该簇全部成员观测嵌入 × 该人全部 **enabled 样本**的最大余弦；`score` **>= 0.40** 产出 `sample_match` 建议（**Stage 4 D-2 裁决统一为 `>=`**：恰等于 0.40 **命中**；实现把阈值与「当前最优」分离，`score < threshold` 跳过） | IMPLEMENTED+TESTED（含 <0.40 / ==0.40 / >0.40 三点边界） | `pairing.py:92-120`（阈值判定 `:109-112`）；`test_stage_e_pairing_domain.py`（`test_score_exactly_at_threshold_matches` / `..._below_...` / `..._above_...`） |
| PR-04 | 规则②：rejected (cluster, person) 对在两阶段都被排除；被拒后人选顺延到下一位候选人 | IMPLEMENTED+TESTED | `pairing.py:104-105,132-136`；`test_stage_e_pairing_domain.py:205` |
| PR-05 | 规则③：剩余簇按 `sort_key` 升序 × 剩余人员按 `roster_order` 升序做一对一顺序配对，产出 `ordered_suggestion`（score=NULL） | IMPLEMENTED+TESTED | `pairing.py:122-146`；`test_stage_e_pairing_domain.py:224` |
| PR-06 | 数量=（簇=人）：全部簇得建议，每人至多被建议一次（`consumed_persons`）；如有 sample_match 会先消耗人员 | IMPLEMENTED+TESTED | `pairing.py:89-146`；测试 `:224` |
| PR-07 | 数量不一致-簇<人：只前 min 个簇获得建议；**其余人员无持久化标记**（仅 summary 的 `persons_without_cluster` 计数，瞬时展示） | IMPLEMENTED（无标记者 PARTIAL） | `suggest_pairings_service.py:150-157`；`pairing_workbench_dialog.py:294-300` summary 只展示 3 个计数 |
| PR-08 | 数量不一致-簇>人：仅前 min 个簇获得建议；剩余簇**无任何指派行**，保持 pending（"自动标记未知/待处理"未实现，见 §11-P3） | IMPLEMENTED（建议）+PLANNED（自动标记） | `pairing.py:127-145` |
| PR-09 | 无名单：suggestions=0；允许先聚类、导入名单后再进入配对——聚类不依赖名单 | IMPLEMENTED+TESTED | `pairing.py` 服务路径；`test_stage_e_pairing_domain.py:267`；`cluster_faces_service.py` 不触碰 people |
| PR-10 | 无簇（该代际聚类为空）→ 无建议；UI 显示"该识别运行尚无聚类结果/该代聚类没有簇" | IMPLEMENTED+TESTED | `ui_text.py:407-408,442` |
| PR-11 | 已确认的人员（`list_confirmed_person_ids(cluster_run_id)`）与已有有效指派的簇不参与新一轮建议；**所有排除按 cluster_run 作用域**——换代际后被排除对可重新出现（同一旧对可在新代际重新被建议） | IMPLEMENTED（作用域）+INFERRED（换代际效果） | `pairing.py:92-98,122-131`；`suggest_pairings_service.py:130-142`；仓储查询均带 cluster_run_id |
| PR-12 | **建议恒为 `suggested`**——本函数从不产生 confirmed（"建议不改变正式归属"明文） | IMPLEMENTED+TESTED | `pairing.py:15`；`test_stage_e_pairing_domain.py:42` |
| PR-13 | 建议幂等：再跑一次被 `clusters_with_active` 跳过，不重复生成 | IMPLEMENTED+TESTED | `test_stage_e_pairing_services.py:333` |
| PR-14 | **unknown / ignored 簇仍会继续进入建议管道**——建议逻辑不读 `face_clusters.status`（读域只见 clusters+members）；该状态仅作展示与人工语义 | IMPLEMENTED（不排除）+PARTIAL（语义未规格化） | `suggest_pairings_service.py:78-142`（无 status 过滤）；`face_clustering.py`/`pairing.py` 无状态入参 |

### 7.2 人工六操作（工作台）
| 编号 | 规则 | 标记 | 证据 |
|---|---|---|---|
| PR-15 | 确认建议：仅允许从 `suggested` → `confirmed`；保存 `sort_snapshot`（当时的 sort_key/first_captured_at/confirmed_at）；确认后即可归档（D3 裁决） | IMPLEMENTED+TESTED | `pairing_workbench_service.py:105-137`；`test_stage_e_pairing_services.py:210` |
| PR-16 | 拒绝建议：`suggested → rejected`；该 (cluster, person) 进入本代际的 rejected 集，后续建议跳过；rejected 只能再 `unassigned` | IMPLEMENTED+TESTED | `pairing_workbench_service.py:141-149`；`cluster_assignment.py:117-120` |
| PR-17 | 解除映射：把该簇**最新一条非 unassigned** 行转 unassigned（覆盖撤回建议/解除确认/撤销拒绝三个入口）；若该行带 person → 同步回收（见 PR-20） | IMPLEMENTED+TESTED | `pairing_workbench_service.py:151-181`；`test_stage_e_pairing_services.py:272` |
| PR-18 | 人工改派/新增指派：旧有效行先转 unassigned+回收，再新行 `source=manual` 并立即 confirmed + 沉淀（**人工显式选择=确认**） | IMPLEMENTED+TESTED | `pairing_workbench_service.py:185-229`；`test_stage_e_pairing_services.py:292` |
| PR-19 | 标记陌生人/忽略组：把 `face_clusters.status` 改为 `unknown`/`ignored`；不改 assignment、样本、成员、排序 | IMPLEMENTED+TESTED | `pairing_workbench_service.py:233-244`；`face_cluster_repository.py:53` |
| PR-20 | 确认/指派的副作用三联（`_sink_confirmation`）：①样本沉淀——该簇全部"有有效嵌入"的成员观测 → `person_face_embeddings`（同一 (person, observation) 对跳过已存在）；②兼容投影——按 (person, photo) 幂等写 `recognition_results` APPROVED（confidence **三态**（Stage 4 BLK-5）：`sample_match` 写真实余弦 `clamp_unit(score)`，`ordered_suggestion`/`manual`（`score IS NULL`）写 **NULL**——「无相似度证据」，不是 0.0；**同一照片的多张脸只写一条**（提到了 `seen_photos`），多个 person 归属同一照片互不覆盖） | IMPLEMENTED+TESTED | `pairing_workbench_service.py:276-345`（confidence 表达式 `:321-323`）；`test_stage_e_remediation.py:226,364` |
| PR-21 | 解除/改派的回收三联（`_retract_confirmation`）：①`DELETE recognition_results WHERE person_id=? AND status='approved' AND photo_id IN (...)`；②同一投影只移除旧 person 的行；②样本 `enabled=0`（历史保留可复核） | IMPLEMENTED+TESTED | `pairing_workbench_service.py:347-374`；`sqlite_recognition_repository.py:282-296`；`test_stage_e_remediation.py:273` |
| PR-22 | **同一 cluster 至多一条"当前有效"指派**（suggested 或 confirmed），服务层保证（`_active_assignment`），改派自动失效旧行 | IMPLEMENTED+TESTED | `cluster_assignment.py:45-47`；`pairing_workbench_service.py:268-274,189-199` |
| PR-23 | 同一 person 可被指派到多个簇（手动 `assign_person` **不检查**该人是否已在别簇 confirmed）；人员下拉列全部名单不加过滤器 | IMPLEMENTED（无守卫）+INFERRED（语义=计划"多组关联同一人"） | `pairing_workbench_service.py:185-229`；`pairing_workbench_dialog.py:239-247`；`test_stage_e_remediation.py:297`（A→B→C 链） |
| PR-24 | 未配对对象的状态：①无任何指派行的簇 = UI 显示"尚未生成建议；可点击生成建议或直接指派"（无持久状态行）；②suggested = 待人工确认；③rejected = 系统不再建议该对（本代际）；④confirmed = 正式归属且立刻产生归档可见性 | IMPLEMENTED | `ui_text.py:424-443`；`cluster_assignment.py` |
| PR-25 | 配对工作台全部操作为**同步快 SQLite**（不经 Worker），每次操作后重读重渲染；无取消/进度概念 | IMPLEMENTED | `pairing_workbench_dialog.py:5-8,303-378` |
| PR-26 | 阈值固定不可调：sample_match 0.40（`SAMPLE_MATCH_THRESHOLD_DEFAULT`）、无 UI/命令行入口；变更需改代码+走 owner 裁决 | IMPLEMENTED（固定） | `pairing.py:28`；calibration report §6 |
| PR-27 | 聚类结果展示里"当前指派"列只读（assignments_active 读 suggested+confirmed），不允许在结果对话框内操作 | IMPLEMENTED | `cluster_results_service.py:48-52`；`pairing_workbench_dialog.py:169-176` |

---

## 8. rerun 规则（RR 系列）

| 编号 | 规则（对三处"重跑"全部逐一作答） | 标记 | 证据 |
|---|---|---|---|
| RR-01 | **识别 rerun 是否新建 RecognitionRun**：恒新建——`add_run` 是 INSERT 新 UUID 行，`update_run` 只写 status/统计/finished_at，不存在把本次执行写进任一旧行的路径 | IMPLEMENTED+TESTED | `run_recognition_service.py:47-60`；`sqlite_recognition_run_repository.py:32-62,81-119`；`test_run_recognition_service.py:67`（`first.id != second.id`） |
| RR-02 | **新旧 Run 是否同时保留**：是——`list_runs()` 返回所有代际；任何代码路径不删除旧 run | IMPLEMENTED | `sqlite_recognition_run_repository.py:73-79`；delete 谓词不存在 |
| RR-03 | **FaceObservation 是否被覆盖**：否——UNIQUE 键含 `run_id`，跨 run 无冲突；同 run 绝无第二次写入（取消/失败后也不会） | IMPLEMENTED+TESTED | `sqlite_face_observation_repository.py:26-30`；`test_stage_c_recognition_repositories.py:80` |
| RR-04 | **旧结果（旧 run 观测、旧簇、旧指派）是否失效**：不失效；观测与簇按 run_id/cluster_run_id 悬挂在原 run 下；"当前指派"仅在本代际内有效，换代际后需在新代际**重新**确认/指派 | IMPLEMENTED+INFERRED（换代际语义） | FK CASCADE 全集无状态失效机制；§7.1 PR-11 |
| RR-05 | **历史是否可追溯**：可——runs/clusters/assignments 全部按 created_at 排序或按 run_id 可列；UI 提供代际选择器（聚类页运行选择 + 结果对话框代际下拉 + 工作台代际下拉） | IMPLEMENTED+TESTED | `sqlite_recognition_run_repository.py:73-79`；`sqlite_face_cluster_repository.py:110-118`；`people_admin_page.py:551-579`；`cluster_results_dialog.py:68-75` |
| RR-06 | **重试的输入**：仅上次终态最新 run 中"有输入但没有观测"的照片（unreadable+error+no_face 三类一并）；以新 run 执行 | IMPLEMENTED+TESTED | `recognition_failure_service.py:64-108`；`test_stage_f_services.py:207,268`；`test_stage_f_lifecycle.py:142` |
| RR-07 | **重试运行参数快照标签**：写 `photo_scope="selected"`（不见 "retry" 字样——`scope_label` 参数无任何调用者）；原始限制只在"照片数/范围"参数里可见 | IMPLEMENTED（INFERRED 缺口） | `recognition_run_controller.py:99-104`；`main_window.py:1451-1454` |
| RR-08 | **聚类 rerun**：恒新建 FaceClusterRun + 新簇全集；不参与"续写"或"修剪" | IMPLEMENTED+TESTED | `cluster_faces_service.py:70`；`test_cluster_faces_service.py:160`（两代并存） |
| RR-09 | **归档 rerun**：成功 4 态 (archived/skipped/renamed/overwritten) 按 (person, photo) 拦截重规划；PLANNED/DRY_RUN/FAILED 允许重试——DRY_RUN 是预览非提交，FAILED 是清理态 | IMPLEMENTED+TESTED | `archive_planner.py:28-33,199-210`；`test_step11_archive_e2e.py:197`（第二轮 planned_count=0） |
| RR-10 | **识别 rerun 不写任何"更新很久前的结论"**：既有 compat 行的存在性守卫阻止重写（不动态修正旧 PENDING/REJECTED/归属）；要修正身份只能经配对工作台（PR-15/18) 或人工审核（approve/reject) | IMPLEMENTED+INFERRED | `run_recognition_service.py:125-129`；`review_recognition_service.py` |
| RR-11 | **识别兼容行的去重是按"照片"的**：既存每行（含 PENDING）都阻新；"重复执行"产生的是新观测行而非新 PENDING 行 | IMPLEMENTED+TESTED | `run_recognition_service.py:125`；`test_run_recognition_service.py:67,101` |

---

## 9. 历史规则（HI 系列）

| 编号 | 规则 | 标记 | 证据 |
|---|---|---|---|
| HI-01 | 迁移 001→007 全部为 additive-only：新表/新列以 IF NOT EXISTS 添加；`003 → 004 → 005 → 006 → 007` 不迁移任何既有数据 | IMPLEMENTED+TESTED | 各 migration docstring；`test_upgrade_integrity.py:133`（逐行对比零丢失） |
| HI-02 | `recognition_results` 旧行永远保留并被持续消费（审核、筛选、徽标、就绪、导出、删除预览、归档） | IMPLEMENTED | §12 证据索引 |
| HI-03 | 历史人员回填：见 RO-17 | IMPLEMENTED+TESTED | `backfill_historical_people_service.py:72-148` |
| HI-04 | 删除照片（业务删除，非 FS 删）→ FK CASCADE 同步删除其全部派生数据：`recognition_results`、`face_observations`、`recognition_run_photos` 快照、`face_cluster_members`、`person_face_embeddings`、`archive_records` | IMPLEMENTED+TESTED | 迁移 002/004/006/007 的 ON DELETE CASCADE；`test_deletion_cascade.py`；`test_stage_c_recognition_repositories.py:99` |
| HI-05 | 删除人员 → `recognition_results.person_id` 置 NULL（"未知"归属，照片保留）；`person_embeddings` CASCADE 删；**`cluster_person_assignments` 与 `person_face_embeddings` 直接 CASCADE 删除（不转 unassigned、不停用）** | IMPLEMENTED+TESTED（级联语义由迁移与删除测试覆盖） | 迁移 002/007 FK；`sqlite_person_repository.py:71-80`；`delete_person_service.py:86-100`；`test_stage_e_assignment_repositories.py:147` |
| HI-06 | 计划 B-2 曾要求人员删除时把指派"置 unassigned / 样本停用"——**未实现**，与 HI-05 的 CASCADE 删除冲突（Stage 1 冲突 5；注意 PROJECT_STATUS 未登记） | PARTIAL（计划未兑现） | `docs/development/people-import-face-clustering-execution-plan.md:94-96`；`delete_person_service.py:56-100`（无 assignment/sample 仓储依赖） |
| HI-07 | 归档记录与照片同生死：照片被删时 archive_records 一并 CASCADE；删除照片前由 `DeletePhotosService` 预览并拦截 | IMPLEMENTED+TESTED | `sqlite_photo_repository.py:87-107`；`delete_photos_service.py:58` |
| HI-08 | 草稿批次/草稿行永不自动清理；取消的导入也留作历史；`cancelled` 状态定义未使用 | IMPLEMENTED（残留语义） | 无清理代码路径；RO-15 |
| HI-09 | `run_photos` 是输入快照同时是删除快照的悬挂点：照片删除时快照也删（FK CASCADE）——不为"查照片已删"而永久保留快照 | IMPLEMENTED | `domain/entities/recognition_run.py:161-172` 注释；迁移 004 FK |

---

## 10. 自动/人工边界

### 10.1 画图时的"边界表"（人工必须介入之处）

| 步骤 | 性质 | 用户动作 | 自动连动 |
|---|---|---|---|
| 名单解析 | 自动 | 选文件 | 生成 import_batches(draft)+draft_rows |
| 名单预览编辑 | 人工 | 改单元格/换 action/拆分行 | 每次编辑整体替换草稿行 |
| 名单**落库** | **人工** | 点"确认"（dialog.exec()） | 一个 UoW 内写 people + roster_order |
| 名单取消 | 人工 | 点"取消" | 零写 people，草稿保留 |
| 识别范围选择 | 人工 | 选范围、勾人脸数 | 弹结果后由控制器落 StartRecognitionRunCommand |
| 识别执行 | 自动 | （仅点启动） | run/快照/观测/统计/PENDING compat |
| **兼容行 APPROVED 的产生** | **必须人工** | — | **不自动产生** |
| 聚类执行 | 自动 | （仅点启动 + 选 run） | 新代际 + 簇 + 成员 |
| 聚类结果查看 | 人工读 | 打开对话框 | 只读 |
| 建议生成 | 自动 | 点"生成建议" | 只写 suggested |
| 配对确认/拒绝/解除/改派/标记 | **人工** | 对话框按钮 | 三连写/回收（PR-20/21） |
| 审核中心 通过/拒绝（legacy PENDING） | 人工 | 审核对话框 | `update_status`（写 status；**批准时可同时写入人工指定 `person_id`——Stage 4 D-1**；未指定身份的批准行仍不可归档） |
| 归档根/执行/冲突策略 | 人工 | 对话框；dry_run 默认勾选 | 计划 preview 零副作用；执行走 Worker |
| 人员增/删/改/重排 | 人工 | 人员页 | 按 RO-08/09/10 规则 |
| 历史人员回填 | **偏工具（owner 触发）** | 运行 `tools/backfill_historical_people.py` | 单事务批量更新 |
| 失败清单导出 | 人工 | 对话框导出按钮 | 只读 CSV（UTF-8-BOM） |

### 10.2 边界规则（最容易在图里画错的六处）

| 编号 | 规则 | 标记 | 证据 |
|---|---|---|---|
| BA-01 | **配对确认 = 归档门槛**：没有 confirmed 指派（且无审核通过**并指定身份**的 PENDING 行——Stage 4 D-1）→ 没有 APPROVED 行 → 归档计划为空 | IMPLEMENTED | 见 CORE-04/05 |
| BA-02 | **识别 PENDING 行与 Stage D/E 互不知情**：聚类不读 `recognition_results`；归档不读观测/簇/指派；两边仅由"配对确认"这一人工作点把新链路写进旧表 | IMPLEMENTED | import 排序对比：`archive_planner.py:17-23` vs `cluster_faces_service.py:26-41` |
| BA-03 | 建议不会自动生成人工决策：每轮"生成建议"只新增 suggested 行 | IMPLEMENTED | PR-12 |
| BA-04 | "重试上一 run 失败照片"在 UI 是自动取数 + 人工确认的组合：系统自动探失败集，但**仍需人工选"重试"并确认** | IMPLEMENTED | `main_window.py:1428-1448` |
| BA-05 | 人员手工新增/编辑/删除在名单页；**配对工作台不能新增人员**（无按钮/无调用） | PLANNED（计划要求工作台可新增人员） | `pairing_workbench_dialog.py:75-132`（按钮全集）；计划 §6 表格"工作台必须支持……新增人员" |
| BA-06 | 自动配对里"自动"的时间点：聚类恒自动、建议按需手动点、确认恒人工；**无后台周期性自动建议任务** | IMPLEMENTED | 无定时器/计划任务代码 |

---

## 11. 当前实现 vs 目标规则

> 目标规则来源：`docs/development/people-import-face-clustering-development-plan.md`（owner 业务方案）与其工程计划 `...-execution-plan.md`。本节逐段对照并给状态。

### 11.1 方案 §3 领域模型与状态
| 方案条目 | 实现 | 状态 |
|---|---|---|
| `import_batches` / `import_draft_rows` 两表 | 003 已建；草稿-确认两段式存在 | IMPLEMENTED |
| `people.roster_order` / `source_batch_id` | 003 已加列；六处真实用途已接通（§4.1） | IMPLEMENTED |
| `recognition_runs` 允许明确重跑、"不再以是否已有结果阻止" | 代码已完成且 UI 退役旧门禁；CLI `recognize` 仍保留旧语义 | IMPLEMENTED |
| `face_observations` 一张脸一条记录 | 004；多脸、范围、确定性序全部落地 | IMPLEMENTED |
| `face_clusters`/`face_cluster_members`/`cluster_person_assignments`/`person_face_embeddings` 四表 | 006/007；写入路径全通 | IMPLEMENTED |
| `face_clusters.status` 六态 | 只实写三态（pending/unknown/ignored） | PARTIAL |
| "保留现有 `recognition_results` 作为历史审批与归档兼容层" | 已实作且是归档唯一门票（CORE-05） | IMPLEMENTED |

### 11.2 方案 §4 导入域
| 方案条目 | 实现 | 状态 |
|---|---|---|
| §4.1 解析原则（编码阶梯/分隔符/字段映射/多人拆分/组标题/强弱重复） | `parse_import_draft_service.py` 全部落地；GB18030/UTF-16/xls 有真实用例 | IMPLEMENTED+TESTED |
| §4.2 确认页展示草稿、批量映射、取消保留草稿 | 对话框就绪；取消不写 people | IMPLEMENTED+TESTED |
| §4.2 "**增加、删除**草稿人员" | **未实现**：dialog 无 add/delete row 按钮（只能改单元格/切 action/拆分） | PLANNED |
| §4.2 事务写入人员 | UoW 单事务写 people；批次状态翻转在事务外（RO-07） | IMPLEMENTED（事务边界 PARTIAL） |

### 11.3 方案 §5 人脸与聚类
| 方案条目 | 实现 | 状态 |
|---|---|---|
| §5.1 每张照片保存全部人脸 | 已实现（CORE-02） | IMPLEMENTED |
| §5.1 不可读取不伪装为无人脸 | permission 分开计数但**失败清单统一归类**（§5.1 已声明 Spec Gap） | PARTIAL |
| §5.2 两段式聚类 | cosine-centroid-completelink-v1 已实现 | IMPLEMENTED+TESTED |
| §5.2 低质量不驱动合并 | 实现；阈值当前 0.0=禁用（CL-07/08) | IMPLEMENTED(机制)+PLANNED(公式) |
| §5.2 "提供人工合并组和拆分组" | **不存在** | PLANNED |
| §5.3 排序键 + 缺失时间排末 | 已实现 | IMPLEMENTED+TESTED |
| §5.3 确认时存排序快照 | `_sink_confirmation`/confirm 各自保存 `sort_snapshot` | IMPLEMENTED |
| §5.3 UI 提示"时间缺失，顺序建议不可靠" | 只显示"时间缺失" | PARTIAL |

### 11.4 方案 §6 配对
| 方案条目 | 实现 | 状态 |
|---|---|---|
| 六场景表 行1（组=人全量建议） | 实测成立 | IMPLEMENTED+TESTED |
| 六场景表 行2（组<人，其余人员"尚无照片组"） | 建议侧成立；**"尚无照片组"标记未实例化**（只有瞬时计数） | PARTIAL |
| 六场景表 行3（组>人，剩余组"未知/待处理"） | 建议侧成立；**自动标记未实现**（无 set_cluster_state 自动路径） | PLANNED（标记部分） |
| 六场景表 行4（无组：展示统计） | 展示"该识别运行尚无聚类结果"等；无人脸/读取失败/低质量的聚合统计**不在配对工作台展示** | PARTIAL |
| 六场景表 行5（无名单允许先聚类） | 成立（聚类不依赖 people） | IMPLEMENTED+TESTED |
| 六场景表 行6（一人多组/多人合一组） | 一人多组的**手动指派**已可；**"提示相似组"未实现**；多人合一组的拆分未实现 | PARTIAL / PLANNED(拆分) |
| §6 工作台九动作 | 已实现 6 个（建议/确认/拒绝/解除/改派/标记）；"合并组/拆分组/新增人员"未接入工作台 | PARTIAL |
| §6 样本沉淀 + 后续 1:N 基于多样本 | 沉淀已实现；**新识别读取多样本（E-3）未接**——识别仍只读旧 `person_embeddings` | PLANNED（切换） |

### 11.5 旧的 `recognition_results` / `person_embeddings` 共生关系
| 关系 | 标记 | 证据 |
|---|---|---|
| `recognition_results` 仍是**当前活的事实表**（审核/筛选/徽标/就绪/导出/归档唯一读取源） | IMPLEMENTED | §13 证据索引 |
| `recognition_results` 三位写入者：识别 compat 投影（pending）/ 配对 confirm·assign（approved）/ 审核 status 迁移；两个删除者：配对 retract、照片/人员的 FK | IMPLEMENTED | Stage 1 §1.2；`sqlite_recognition_repository.py` |
| `person_embeddings` **读活写死**：无生产写者（`save` 无 src 调用者）；仅 `list_all` 被识别/旧 match/删除预览读 | PARTIAL（读）+ PLANNED（充实） | `sqlite_face_embedding_repository.py:27,74`；`run_recognition_service.py:66`；`match_persons_service.py:159`；`delete_person_service.py:65` |
| 直接后果：识别兼容行的 `person_id` 恒为 NULL（候选恒空），**最终身份只能来自人工动作**——配对工作台确认/改派，或审核中心批准时指定人员（Stage 4 D-1） | INFERRED（由写者缺失直接推导） | 同上两行 |
| `person_face_embeddings` 只被建议生成消费（list_enabled）与确认侧查重（list_by_person）；**不回写给识别链路当候选** | IMPLEMENTED（局部）+ PLANNED（回流） | `suggest_pairings_service.py:110`；`pairing_workbench_service.py:300` |
| APPROVED 行的**来源不可区分**：审核通过的行与配对投影行字段相同（无 source 列） | IMPLEMENTED（字段现状）+ PARTIAL（可追溯性） | 迁移 002 schema；E-SG-6 兼容裁决 |

---

## 12. 未确认业务规则

| 编号 | 未确认项 | 状态根据 | 建议 Stage 3 处理 |
|---|---|---|---|
| U1 | ~~sample_match 阈值边界：代码是 **严格 `> 0.40`**，计划/测试注释是 **≥ 0.40**~~ → **Stage 4 D-2 已裁决并落地**：统一为 `score >= 0.40`（恰等即命中），实现 / docstring / 测试三点一致 | 已裁决+TESTED | `pairing.py:92-120`（阈值判定 `:109-112`）；`test_stage_e_pairing_domain.py` 边界三点用例 |
| U2 | rejected 对是否应**跨代际**生效？代码按 `cluster_run_id` 求值（换代际重新建议同一对）；方案并未明确 | INFERRED | 待 owner 裁决是否按集群而非代际排除 |
| U3 | unknown/ignored 簇是否应从后续建议中排除？代码**不排除**（PR-14） | INFERRED | 待 owner 裁决"忽略 = 不再建议" |
| U4 | `import_batches.cancelled` 状态语义不完整：定义了但无写入路径；取消导入只保留 draft | PARTIAL | 待 owner 裁决是否补一条"取消确认即转 cancelled"的路径 |
| U5 | 人员删除时的指派/样本处置：FK CASCADE 物理删除 vs 计划 B-2 的"置 unassigned/停用"——**两文书不一致**（HI-06） | 实现 ↔ 计划冲突 | Stage 3 两张图都必须按 CASCADE 物理删除画，挂"待 owner 裁决" |
| U6 | `person_embeddings` 空缺在生产中是否就是预期（即"识别只能产出待人工结果"）——文档承认现象但未改变判定 | UNKNOWN（需读真实库）+INFERRED | 建议读真实 `%LOCALAPPDATA%` 库行数 |
| U7 | 配对确认产生的 APPROVED 行与审核通过的行**无法区分**（无 source 列） | PARTIAL | Stage 3 不要画两条不同含义的 APPROVED 边 |
| U8 | 同一照片在一张 run 内多张脸分别落观测，但确认投射时 `seen_photos` 只取该簇中的第一张观测行算 (person, photo) 幂等——**其他人脸观测通过同一照片被关联但不单独成行** | IMPLEMENTED（行为）+INFERRED（语义） | 见 `pairing_workbench_service.py:320-327` |
| U9 | 旧链路 `recognize --all` CLI 与 GUI-Stage C 的并发写入 `recognition_results` 无互斥（不同进程） | UNKNOWN | 不在本阶段判定范围 |
| U10 | `person_embeddings`、`face_clusters.confirmed/split/merged`、`recognition_run_scopes`（写活读死）这些"定义未用"字段/表是否进入 Stage 3 的状态图——只影响图面呈现，不影响业务事实 | INFERRED | 已列入本文件 §2/§3 作 PARTIAL 注记 |
| U11 | 样本"合格"定义（E-SG-4）与改派后样本恢复语义（E-SG-5） —— 报告自陈 Spec Gap 未裁决 | UNKNOWN | 待 owner 规格 |
| U12 | 归档"已完成"成功后再次变更人员姓名/删除人员，**归档记录 target_person_name 不回写**（写死字符串） | INFERRED | `archive_executor.py:325-343`；评估是否需要 owner 裁决 |

---

## 13. 规则证据索引

### 13.1 迁移（权限最高，落点即实现）
`alembic/versions/001_initial_v4.py`、`002_split_create_ddl.py`（people/folders/photos/recognition_results/person_embeddings/archive_records + 6 索引）、`003_import_batches_and_roster.py`、`004_recognition_runs_and_observations.py`、`005_recognition_run_error_count.py`、`006_face_clusters.py`、`007_assignments_and_person_samples.py`。

### 13.2 领域实体与领域服务
- `src/photo_archiver/domain/entities/import_batch.py:13-19`（batch/row 行为词表）
- `src/photo_archiver/domain/entities/person.py:15-26`（Person 字段）
- `src/photo_archiver/domain/entities/recognition.py:11-75`（RecognitionResult 状态机）
- `src/photo_archiver/domain/entities/recognition_run.py:24-45,78-172`（RecognitionRun 状态机 + RunPhotoSnapshot）
- `src/photo_archiver/domain/entities/face_observation.py:22-83`（FaceObservation + classify_scope）
- `src/photo_archiver/domain/entities/face_cluster.py:31-201`（FaceClusterRun / FaceCluster / FaceClusterMember 词表与不变式）
- `src/photo_archiver/domain/entities/cluster_assignment.py:31-151`（ClusterPersonAssignment 状态机 + PersonFaceSample）
- `src/photo_archiver/domain/value_objects/face_count_range.py`（FaceCountRange 语义）
- `src/photo_archiver/domain/value_objects/archive_path.py`（路径净化）
- `src/photo_archiver/domain/services/face_clustering.py`（两段式算法全文）
- `src/photo_archiver/domain/services/pairing.py`（建议三规则全文）

### 13.3 应用服务（规则落点）
`parse_import_draft_service.py` / `confirm_import_service.py` / `import_people_service.py`（旧直通）/ `manage_people_service.py`（人员页）/ `backfill_historical_people_service.py` / `run_recognition_service.py` / `face_analysis_task.py` / `recognition_failure_service.py` / `list_recognition_runs_service.py`（只被人员页聚类选择器消费）/ `cluster_faces_service.py` / `cluster_results_service.py`（只读）/ `suggest_pairings_service.py` / `pairing_workbench_service.py` / `review_recognition_service.py` / `archive_planner.py` / `archive_path_builder_service.py` / `archive_photos_service.py` / `archive_executor.py` / `delete_person_service.py` / `delete_photos_service.py` / `workspace_readiness.py` / `plugin_context_service.py`（插件直通）。

### 13.4 仓储 SQL 落点（表列写入权威）
`sqlite_person_repository.py`（含 `list_all` 的 roster 排序：109-117；reorder：125-135）/ `sqlite_import_batch_repository.py` / `sqlite_recognition_run_repository.py`（add/update/list/list_run_stats）/ `sqlite_face_observation_repository.py`（无 ON CONFLICT）/ `sqlite_face_cluster_repository.py`（`update_cluster_status` 唯一写簇状态）/ `sqlite_cluster_assignment_repository.py` / `sqlite_recognition_repository.py`（含 `remove_results_for_person_photos`）/ `sqlite_face_embedding_repository.py`（生产无 save 调用）/ `sqlite_archive_record_repository.py` / `sqlite_photo_repository.py`（搜索 JOIN `recognition_results`）。

### 13.5 表现层接线
- `presentation/views/main_window.py`：`_on_import_clicked:1100`、`_confirm_import:1127`、`_on_archive_clicked:1174`、`_on_match_clicked:1405-1460`、`_on_cluster_run_clicked:1465`、`_on_pairing_workbench_clicked:1502`、`_refresh_task_results:954-973`。
- `presentation/views/people_admin_page.py`：`refresh_clustering:551`、`selected_recognition_run_id:594`。
- `presentation/views/recognition_scope_dialog.py`（`photo_scope`/`selected_ranges`/retry 逻辑）、`import_preview_dialog.py`（每步落库；`CONFIRM_SYNC_LIMIT=500:44`）、`cluster_results_dialog.py`（只读）、`pairing_workbench_dialog.py`（六操作全集 75-132 按钮 / 287-378 处理）、`archive_preview_dialog.py:147-152`（dry-run 默认勾选）。

### 13.6 计划与文档（PLANNED 判定的来源）
- `docs/development/people-import-face-clustering-development-plan.md`（§3 领域模型、§4 导入、§5 人脸、§6 配对、§7 分阶段）
- `docs/development/people-import-face-clustering-execution-plan.md`（A–F 分阶段；§C-1/§D-1 的 schema 草案已**被实现为准的 004/006/007 推翻**，见 Stage 1 §10 冲突 3/4）
- `docs/development/stage-f-calibration-report.md`（真实 473 张实测 + 遗留裁决点 §6）

### 13.7 命令与命令行
- 命令对象：`application/commands/import_draft.py`、`import_people.py`、`people_admin.py`、`start_recognition_run.py`、`cluster_faces.py`、`pairing.py`、`archive.py`、`deletion.py`。
- CLI 子命令：`scan`、`scan-register`、`archive`、`backfill-content-hash`、`prune-missing`、`backfill-capture-time`、`import-people`、`migrate`、`download-models`、`recognize`、`cleanup-thumbnails`、`export`（`main.py:107-253`）。
- `recognize` 与 GUI 的新链路是不同的"唯一尚存旧链路"；已通过 `tests/unit/architecture/test_recognition_entry_migration.py` 固定在"GUI 不再走 MatchPersons"状态。

### 13.8 关键测试（TESTED 的载体）
| 主题 | 文件（数量） |
|---|---|
| 识别 run/观测/取消/兼容 | `tests/unit/application/test_run_recognition_service.py`（6）；`tests/unit/application/test_stage_f_lifecycle.py`（5，1200 张） |
| Stage F 服务/失败/重试/回填 | `tests/unit/application/test_stage_f_services.py`（10） |
| 聚类服务 | `tests/unit/application/test_cluster_faces_service.py`（13） |
| 聚类算法 | `tests/unit/domain/test_face_clustering_algorithm.py`（21） |
| 聚类结果读 | `tests/unit/application/test_cluster_results_service.py`（5） |
| Stage E 领域/服务/整改/仓储 | `test_stage_e_pairing_domain.py`（14）/ `test_stage_e_pairing_services.py`（6）/ `test_stage_e_remediation.py`（7）/ `test_stage_e_assignment_repositories.py`（5） |
| Stage C/D 领域与仓储 | `test_stage_c_commit1.py`（6）/ `test_stage_c_recognition_repositories.py`（4）/ `test_stage_d_cluster_repositories.py`（7） |
| 导入闭环 | `tests/integration/test_import_draft_flow.py`（12）/ `test_bulk_people_import_closed_loop.py`（1）/ `test_excel_import_ui_closed_loop.py`（2）/ `test_import_people_transactional.py`（9） |
| 归档 | `tests/integration/test_step11_archive_e2e.py`（5）/ 单测 `test_archive_planner.py`（10） |
| 升级完整性 | `tests/integration/test_upgrade_integrity.py`（3） |
| 架构守卫（GUI 退役旧识别） | `tests/unit/architecture/test_recognition_entry_migration.py`（3）/ `test_layer_boundaries.py` |

> 全套仓库测试已由 Stage 4.1 复审（2026-09-28）实跑复现：**1310 passed / 6 skipped**（233.25s），与 `2823d1c` 提交信息一致；报告以测试文件存在与断言覆盖为 TESTED 依据。

---

**本文件供 Stage 3 使用。不画业务流程图属 Stage 3；本文件只回答"规则即代码"。**
