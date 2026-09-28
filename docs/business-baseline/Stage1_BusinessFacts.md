# Stage 1 — PhotoArchiver 业务事实重建报告

> **依据**：当前仓库 HEAD `2823d1c7ceaab09c38d39b9a80e1e724839cfa17`（2026-09-28 01:44:20 +0800，`fix: resolve business baseline freeze blockers`），工作区除 `docs/development/evidence/` 下 2 个未跟踪证据文档外干净。
> **基线收口（2026-09-28）**：本文件原基于 `b3b8685` 编写；`2823d1c` 落地了 Stage 4 BLK-1/BLK-5 修复与 D-1/D-2 裁决，并使 `pairing_workbench_service.py`（+11/+16 行）、`pairing.py`、`sqlite_recognition_repository.py`、`review_recognition_service.py`、`archive_planner.py`、`recognition.py`、`ui_text.py` 等文件行号整体漂移。本修订版已把**全部受影响引用按当前 HEAD 重新核对改写**，并把 D-1/D-2 结论统一到当前实现。行号均为 HEAD `2823d1c` 版本行号。
> **方法**：只读代码/测试/迁移/ADR/业务文档审计。全量 pytest 已由 Stage 4.1 复审实跑复现（**1310 passed / 6 skipped**，2026-09-28）；本文件标记中的 TESTED 指存在对应测试断言。未修改任何源码。
> **证据分级**：IMPLEMENTED（代码可执行路径存在且被生产调用）/ PARTIAL（存在但有缺口或未接线）/ PLANNED（仅存在于计划文档）/ TESTED（有对应测试断言）/ INFERRED（由代码推导，非直接声明）/ UNKNOWN（无法从仓库证据确认）。
> **引用格式**：`路径:行号`。行号为 HEAD 版本行号。

---

## 0. 一句话结论

仓库当前的真实链路是：**名单两段式导入（草稿→确认）→ 扫描登记照片 → 可追溯识别运行（RecognitionRun + FaceObservation）→ 人脸聚类（FaceClusterRun/FaceCluster/Member）→ 建议式人员配对（ClusterPersonAssignment）→ 人工确认 → 兼容投影写 `recognition_results`（APPROVED）→ 归档只消费 `recognition_results`**。

核心事实：**Stage C/D/E 的新数据（观测、聚类、指派）本身不直接驱动归档**；归档的唯一输入仍是 legacy `recognition_results` 表的 APPROVED 行，而 Stage E 的"确认/改派"动作通过显式维护这张表把新链路接进归档（`pairing_workbench_service.py:276-345`、`archive_planner.py:116`）。这是理解全链路的关键枢纽。

---

## 1. 实际业务链路

### 1.1 主链路（GUI 可达，共 7 段）

| # | 段 | 入口 | 自动化程度 | 主要落库 |
|---|---|---|---|---|
| 1 | 人员名单导入 | 工具栏"导入人员" `main_window.py:307,362-366` | 解析**自动**；**确认必须人工** | `import_batches`(draft) + `import_draft_rows` → `people`(roster_order, source_batch_id) |
| 2 | 照片进入系统 | 工具栏"扫描"（`scan_controller.py`） | 自动 | `folders` + `photos` |
| 3 | 人脸识别运行 | 工具栏"识别" `main_window.py:311` → 范围对话框 | 自动（人工只选照片范围/人脸数范围） | `recognition_runs` + `recognition_run_scopes` + `recognition_run_photos` + `face_observations` + **兼容行** `recognition_results`(PENDING) |
| 4 | 人脸聚类 | 人员页"运行人脸聚类"（选 recognition run） | 自动（阈值不可调） | `face_cluster_runs` + `face_clusters` + `face_cluster_members` |
| 5 | 配对建议 | 配对工作台"生成建议" | 自动，但只写 `suggested` | `cluster_person_assignments`(suggested) |
| 6 | 人工身份决策 | 配对工作台 确认/拒绝/改派/解除/标陌生/忽略 | **纯人工** | `cluster_person_assignments` 状态迁移 + `person_face_embeddings` + **兼容行** `recognition_results`(APPROVED/DELETE) |
| 7 | 归档 | 工具栏"归档" / 照片库批量归档 | 计划自动；执行需人工确认（dry-run 默认勾选） | `archive_records` + 磁盘文件 |

### 1.2 旁路链路（非 GUI）

| 链 | 入口 | 说明 |
|---|---|---|
| 直通名单导入（无草稿/无预览） | CLI `import-people` `main.py:165-178,439` + 插件 `PluginContextService.import_people` `plugin_context_service.py:223-255` | 只写 `people`，**不建 import_batch**（`import_people_service.py:46-53`） |
| 旧识别管线 | CLI `recognize` `main.py:227,674-739` | 用 `MatchPersonsService`，同样只写 `recognition_results`；GUI 已不再接线（`main_window.py:276` 注释 + 架构守卫测试） |
| 历史人员回填 | `tools/backfill_historical_people.py` / `BackfillHistoricalPeopleService` | 只动 `people.source_batch_id/roster_order` + 造一个 `source_type="backfill"` 批次（`backfill_historical_people_service.py:17-23`） |

### 1.3 逐段事实（务必注意的语义细节）

**段 1 — 导入**
- 选文件后**立即**创建草稿批次（`parse_import_draft_service.py:71-83`）：`import_batches.status='draft'` + N 行 `import_draft_rows`。此时 `people` 零写入。
- 预览期的每一次编辑（改单元格/切 action/reparse/拆分多人行）都是**整批 DELETE + 重插** `import_draft_rows`（`sqlite_import_batch_repository.py:99-130`，调用点 `parse_import_draft_service.py:107,146,153`）。
- 确认（`confirm_import_service.py:50-109`）在一个 UoW 内按 `order_index` 逐行写 `people`；`roster_order` 从**全局 MAX+1** 续号（`:64-67`），因此跨批次单调递增；`source_batch_id` 指回批次。
- **批次状态置 `confirmed` 在 UoW 之外**（`:96-98`）——people 与批次状态不是同一事务。
- 取消：草稿批次与草稿行**保留**，`people` 零写入（`main_window.py:1122-1124` 注释；测试 `tests/integration/test_import_draft_flow.py:165`）。**没有任何路径把批次置为 `cancelled`**（`BATCH_STATUS_CANCELLED` 仅在 `import_batch.py:15` 定义、`entities/__init__.py:47` 导出，无写入者）。

**段 3 — 识别（最需要精确理解的一段）**
- 照片范围：`RecognitionScopeDialog` 三选一 —— 全部 / 当前选中 / **重试**（重试 = 最新终态 run 中"输入但无观测"的照片，`recognition_failure_service.py:74-108`）。
- **已匹配照片不再被过滤**：`RecognitionRunController.start_run` 每次提交整份快照（`recognition_run_controller.py:82-105`），控制器 docstring 明确写"no already-matched filtering"。
- 每张照片产出（`run_recognition_service.py:104-133`）：
  - 不可读 → `unreadable_count+1`，**0 条 Observation**；
  - 检测抛异常 → `error_count+1`，**0 条 Observation**（异常隔离到单张，批次继续）；
  - 检出 0 脸 → `no_face_count+1`，**0 条 Observation**；
  - 检出 N≥1 脸 → **N 条 Observation**，`face_index` 按 `(‑det_score, x1, y1, x2, y2)` 确定性排序（`:114-115`），照片级 `scope_verdict` 由 `classify_scope()` 决定并被该照片全部观测共享（`face_observation.py:67-83`）。
  - 范围外照片**仍然完整保存全部观测**（只有 `scope_verdict` 不同）；不写兼容行。
- 观测按 50 条一批 flush（`run_recognition_service.py:21,85-87`）；表上有 `UNIQUE(run_id, photo_id, face_index)` 且 INSERT **无 ON CONFLICT**（`sqlite_face_observation_repository.py:26-66`）—— 从存储层杜绝同 run 覆盖。
- 兼容行写入条件（`:124-129`）：`in_scope` **且** 该照片在 `recognition_results` **一行都没有**。用 `ordered[0]`（置信度最高的脸）走 1:N Top-1 匹配（对齐 ADR-017）。因此：范围外照片永不产生兼容行；**任何历史行（含 PENDING/REJECTED/person_id=NULL）都会永久阻止该照片再次写入兼容行**（重跑不会"修正"旧结论）。

**段 4 — 聚类**
- 用户可**选择 recognition run**（人员页下拉，`people_admin_page.py:528-530,551-579,594-597`），但**不能调任何阈值**——`StartClusteringRunCommand` 默认 `cluster_sim_threshold=0.5 / consistency_threshold=0.4 / low_quality_threshold=0.0 / scope_filter="in_selected_scope"`（`commands/cluster_faces.py:24-30`），UI 无对应控件。
- 参与聚类的观测 = `scope_verdict=='in_selected_scope'` 且 `embedding.vector` 非空（`cluster_faces_service.py:230-236`）；其余计入 `excluded_count`。
- 算法 = 两段式：①贪心簇心余弦 ≥0.5 成候选；②完全链接，跨簇两两最小相似度 ≥0.4（含等号）才合并（`face_clustering.py:74-102,130-185`，`ALGORITHM_VERSION="cosine-centroid-completelink-v1"` `:31`）。
- 落库：每簇 `ordinal` 由 `(captured_at_iso, path_key, tiebreak)` 排序键决定（`cluster_faces_service.py:156-183`），`first_captured_at` 取成员照片 `run_photos` 快照中最早非空拍摄时间，全簇无时间则为 `None`（`:197-223`）——**明确不得用注册时间替代**。
- 重跑 = 新 `FaceClusterRun` + 新簇集合，旧代际原样保留（`:69-103`）。

**段 5 — 建议（三条规则，全部只写 suggested）**
- 规则①：组成员的观测嵌入 vs `person_face_embeddings`(enabled=1) 的**最大余弦 >= 0.40** → `source='sample_match'`，`score=余弦`（**Stage 4 D-2 裁决统一为 `>=`：恰等于 0.40 命中**；实现把阈值与「当前最优」分离，`score < threshold` 跳过；`domain/services/pairing.py:92-120`，阈值判定 `:109-112`；阈值常量 `:28`）。
- 规则②：全程跳过 rejected 的 (cluster, person) 对（`:104-105,132-136`）。
- 规则③：剩余簇按 `sort_key` 升序 × 剩余人员按 **`roster_order` 升序**（无 order 者排后）一对一，`source='ordered_suggestion'`，`score=NULL`（`:76-86,122-146`）。
- 已有有效指派（suggested/confirmed）的簇跳过；已被确认的人员不参与（`suggest_pairings_service.py:130-142`）。
- **本函数从不产生 confirmed**（`domain/services/pairing.py:15`；实体注释 `cluster_assignment.py:9-11` 同述）。

**段 6 — 人工决策（配对工作台）**

| UI 动作 | 服务方法 | DB 效果 |
|---|---|---|
| 确认建议 | `confirm` `pairing_workbench_service.py:105-137` | assignment → confirmed + `sort_snapshot`；写 `person_face_embeddings`；写 `recognition_results` APPROVED |
| 拒绝 | `reject` `:141-149` | assignment → rejected |
| 解除映射 | `unassign` `:151-181` | 最新非 unassigned 行 → unassigned；若曾有 person → 回收兼容投影 + 停用样本 |
| 人工改派/新增 | `assign_person` `:185-229` | 旧有效行 → unassigned + 回收；新行 `source='manual'` → 立即 confirmed + 沉淀 |
| 标陌生人/忽略组 | `set_cluster_state` `:233-244` | `face_clusters.status` → unknown / ignored |

- 兼容投影细节（`_sink_confirmation` `:276-345`）：按 `(person, photo)` **至多一条当前有效 APPROVED**；不同 person 对同一照片的归属互不覆盖（E-P1-1）。**confidence 语义（Stage 4 BLK-5 修复后）**：有相似度证据（`sample_match`）写真实余弦（`clamp_unit(score)`，`:321-323`）；无证据（位置配对 `ordered_suggestion` / 人工指派 `manual`，`score IS NULL`）写 **NULL**，**不是 0.0**——「无证据」与「相似度为零」语义不同。
- 回收细节（`_retract_confirmation` `:347-374`）：`DELETE FROM recognition_results WHERE person_id=? AND status='approved' AND photo_id IN (...)`；样本 `enabled=0`（历史保留）。
- **原始数据不动**：成员关系、排序、观测在任何操作下都不被修改（`:16-18` 注释）。

**段 7 — 归档**
- 计划输入**只有**：`recognition_results` 的 APPROVED 行（`archive_planner.py:116,167`）+ `people.name`（`:111-115,137`）+ `photos`（路径/`captured_at`/`original_name`，`:188-218`）+ `archive_records` 成功态去重（`:199-210`）。
- 去重作用域 = `(person_id, photo_id)`。**Stage 4 BLK-1 修复后**：`archive_records` 增 `person_id`（migration 008），持久去重按**稳定 person 身份**判定（`sqlite_archive_record_repository.py:107-138` `has_successful_for_person`）；`person_id IS NULL` 的存量行回退按 `target_person_name` 匹配。→ **同一照片可归档到多个人员目录**（且同名不同人互不抑制、改名后不重复归档）。**已知限制（Stage 4.1 KL-1/KL-2）**：存量重名归档行（008 无法唯一回填时故意留 NULL）与**人员删除后 `person_id` 被置 NULL 的孤儿行**仍按姓名回退去重——"删人 + 同名重建"场景下新归属可能被旧孤儿行静默抑制（仅 `logger.debug`），属升级前行为的原样保留。
- 目标路径 = `{archive_root}/{person_name}/{YYYY-MM-DD}/{original_name}`（`archive_path_builder_service.py:33-81`），降级段 `unknown-person` / `unknown-date`，三段均经 `sanitize_windows_filename` 净化。
- 执行器（`archive_executor.py`）：UoW 内先写 `archive_records` PLANNED，再动文件系统，再写终态；dry_run 默认勾选（`archive_preview_dialog.py:147-152`）。
- **归档链路完全不读** `face_observations` / `face_clusters` / `cluster_person_assignments` / `person_face_embeddings`（`archive_planner.py:17-23` 的 import 清单可证）。

---

## 2. 实际调用链

### 2.1 导入（GUI 两段式）

```
QAction "导入人员"                      main_window.py:307
 → MainWindow._on_import_clicked        main_window.py:1100-1125
 → ParseImportDraftService.execute      parse_import_draft_service.py:63-84
    → FileRosterTableReader.read_raw     infrastructure/importers/roster_table_reader.py
    → SQLiteImportBatchRepository.add_batch / replace_draft_rows
                                         sqlite_import_batch_repository.py:56-79,99-130
 → ImportPreviewDialog(draft, services, path, self)   main_window.py:1120
    → reparse / save_draft_rows / split_draft_row      import_preview_dialog.py:177-279
 → MainWindow._confirm_import           main_window.py:1127-1148
    ├─ row_count > 500 → ConfirmImportTask → QtWorkerExecutor（异步）
    └─ 否则同步 ConfirmImportService.execute
                         confirm_import_service.py:50-109
       → UnitOfWork { SQLitePersonRepository.add(upsert) }   :69-94
       → ImportBatchRepository.set_batch_status('confirmed')  :96-98  ← 事务外
 → _refresh_filter_persons() + _refresh_workspace_state()     main_window.py:1147-1148
```

### 2.2 识别

```
QAction "识别"                          main_window.py:311
 → MainWindow._on_match_clicked         main_window.py:1406-1460
    → WorkspaceController.match_guidance()   presentation/controllers/workspace_controller.py:42-64
    → RecognitionFailureService.latest_resumable_run_id()/report()
                                         recognition_failure_service.py:64-108
    → RecognitionScopeDialog（全部/选中/重试 + 人脸数范围）  views/recognition_scope_dialog.py
 → RecognitionRunController.start_run(selected_ranges, photo_ids)
                                         recognition_run_controller.py:60-109
    → PhotoRepository.list_all() 快照 → StartRecognitionRunCommand
    → RunRecognitionTask → QtWorkerExecutor.submit   workers/application_tasks.py:158-183
 → RunRecognitionService.execute         run_recognition_service.py:46-102
    → RecognitionRunRepository.add_run / add_run_scopes / add_run_photos / update_run
                                         sqlite_recognition_run_repository.py:32-62,121-159,81-119
    → ThreadPoolExecutor × FaceAnalysisTask        face_analysis_task.py:31-44
    → FaceObservationRepository.add_many（每 50 条） sqlite_face_observation_repository.py:26-66
    → RecognitionRepository.add（兼容行，条件式）     sqlite_recognition_repository.py:31-55
 → 终态 → TaskCoordinator.receive → MainWindow._on_terminal → _on_completed
                                         main_window.py:943-952,980-1035
 → _refresh_task_results('run_recognition') → 刷新照片列表 + 待审核 + 工作区就绪
                                         main_window.py:954-973
```

### 2.3 聚类

```
人员页"运行人脸聚类"                     people_admin_page.py:531-533 → cluster_run_requested
 → MainWindow._on_cluster_run_clicked    main_window.py:1465-1486
    → people_admin_page.selected_recognition_run_id()   people_admin_page.py:594-597
 → ClusterFacesController.start_cluster  presentation/controllers/cluster_faces_controller.py:41-58
 → ClusterFacesTask → ClusterFacesService.execute      cluster_faces_service.py:69-103
    → FaceClusterRepository.add_cluster_run / update_cluster_run
                                         sqlite_face_cluster_repository.py:40-69,80-108
    → FaceObservationRepository.list_by_run
    → NumpyCosineSimilarityFactory().build
    → domain cluster_items()              domain/services/face_clustering.py:74-102
    → add_clusters / add_members          sqlite_face_cluster_repository.py:120-176
 → _refresh_task_results('face_clustering') → people_admin_page.refresh_clustering()
                                         main_window.py:966-967
```

### 2.4 配对

```
人员页"人物配对工作台"                   people_admin_page.py:539 → pairing_workbench_requested
 → MainWindow._on_pairing_workbench_clicked  main_window.py:1502-1516
 → PairingWorkbenchDialog(suggest_pairings, pairing_workbench, cluster_results, list_persons, run_id)

[生成建议]  pairing_workbench_dialog.py:287-301
 → SuggestPairingsService.execute        suggest_pairings_service.py:70-163
    → FaceClusterRepository.list_clusters/list_members
    → PersonFaceSampleRepository.list_enabled
    → PersonRepository.list_all（roster_order 参与排序）
    → domain suggest_pairings()           domain/services/pairing.py:60-146
    → ClusterPersonAssignmentRepository.add_assignments   sqlite_cluster_assignment_repository.py:50-82

[确认]  pairing_workbench_dialog.py:303-319
 → PairingWorkbenchService.confirm       pairing_workbench_service.py:105-137
    → ClusterPersonAssignment.confirm()（实体状态机）  cluster_assignment.py:108-115
    → ClusterPersonAssignmentRepository.update_assignment  sqlite_cluster_assignment_repository.py:92-117
    → _sink_confirmation:
        PersonFaceSampleRepository.add_samples  sqlite_cluster_assignment_repository.py:197-225
        RecognitionRepository.add(APPROVED)     sqlite_recognition_repository.py:31-55
```

### 2.5 归档

```
QAction "归档" / 批量归档按钮            main_window.py:315,511-514
 → MainWindow._on_archive_clicked        main_window.py:1174-1228
    → ArchiveController.preview          presentation/controllers/archive_controller.py:47-64
    → ArchivePhotosService.preview/plan  archive_photos_service.py:61-77
       → ArchivePlanner.plan             archive_planner.py:68-151
          → RecognitionRepository.list_approved_by_person  sqlite_recognition_repository.py:266-280
          → PersonRepository.find_by_id / PhotoRepository.find_by_id
          → ArchiveRecordRepository.has_successful_for_person
          → ArchivePathBuilderService.build  archive_path_builder_service.py:33-81
    → ArchivePreviewDialog（dry-run 默认勾选）
 → ArchiveController.execute → ArchivePhotosTask
    → ArchivePhotosService.execute       archive_photos_service.py:79-108
    → ArchiveExecutor.execute            archive_executor.py:63-82（内含 UnitOfWork）
       → ArchiveRecordRepository.add（PLANNED → 终态）  sqlite_archive_record_repository.py:28-72
       → shutil.copy2
```

### 2.6 未被任何生产代码调用的接口（死接口，勿当作已实现能力）

| 接口 | 证据 |
|---|---|
| `FaceEmbeddingRepository.save`（`person_embeddings` 的唯一写入口） | 全仓 `src/` 无调用者（仅 `list_all` 被读）；`sqlite_face_embedding_repository.py:27` |
| `RecognitionRunRepository.list_run_scopes` | 调用者仅在测试（`tests/unit/infrastructure/repositories/test_stage_c_recognition_repositories.py:68,135`） |
| `MatchPersonsController` | 未接任何 UI（`main_window.py:276` 注释 + `tests/unit/architecture/test_recognition_entry_migration.py:43-69` 守卫） |
| `ImportPeopleController.import_from` | GUI 无调用者，仅测试；生产可达路径是 CLI + 插件 |
| `PersonRepository.reorder` | 由 `ManagePeopleService.reorder_people` 调用（人员页上移/下移/拖拽），**属活路径** |

---

## 3. 核心业务对象

| 对象（实体） | 表 | 关键字段 | 产生者 | 状态 |
|---|---|---|---|---|
| `ImportBatch` `domain/entities/import_batch.py:22-44` | `import_batches` | file_name/file_hash/source_type/encoding/delimiter/has_header/sheet_name/status/created_at/confirmed_at | `ParseImportDraftService` | 活 |
| `ImportDraftRow` | `import_draft_rows` | source_row/raw_values/parsed_*/warnings/action/merge_target_id/order_index | 同上 | 活 |
| `Person` `domain/entities/person.py` | `people` | name/identity/department/note/**roster_order**/**source_batch_id** | 确认导入 / 人员页新增 / 回填 | 活 |
| `Photo` | `photos` | raw_path/path_base/folder_id/original_name/**captured_at**/metadata_* | 扫描登记 | 活 |
| `RecognitionRun` `domain/entities/recognition_run.py:79-158` | `recognition_runs` | parameters(JSON 快照)/status/六个统计列/error/created_at/finished_at | `RunRecognitionService` | 活 |
| `RunPhotoSnapshot` `:161-172` | `recognition_run_photos` | raw_path_snapshot/captured_at_snapshot | 同上 | 活（输入快照，照片删除级联） |
| `FaceCountRange` | `recognition_run_scopes` | ordinal/min_count/max_count | 同上 | **写活读死** |
| `FaceObservation` `domain/entities/face_observation.py:29-64` | `face_observations` | run_id/photo_id/face_index/photo_face_count/det_score/box(JSON)/quality_score/embedding(JSON)/scope_verdict | 同上 | 活，Stage D/E 的唯一输入 |
| `RecognitionResult`（legacy）`domain/entities/recognition.py:24-75` | `recognition_results` | photo_id/person_id/status/confidence/created_at | 识别兼容投影 / 配对确认 / 审核状态迁移 / CLI recognize | **活（归档唯一输入）** |
| `FaceClusterRun` `domain/entities/face_cluster.py:76-150` | `face_cluster_runs` | recognition_run_id/algorithm_version/parameters/status/cluster_count/member_count/excluded_count | `ClusterFacesService` | 活 |
| `FaceCluster` `:153-180` | `face_clusters` | cluster_run_id/run_id/ordinal/member_count/first_captured_at/sort_key/status | 同上 | 活 |
| `FaceClusterMember` `:183-201` | `face_cluster_members` | cluster_id/observation_id/source(auto)/confidence | 同上 | 活 |
| `ClusterPersonAssignment` `domain/entities/cluster_assignment.py:74-131` | `cluster_person_assignments` | cluster_id/person_id/status/source/score/sort_snapshot/confirmed_at/error | 建议生成 + 工作台 | 活 |
| `PersonFaceSample` `:134-151` | `person_face_embeddings` | person_id/observation_id/embedding/quality_score/**enabled** | 配对确认/改派 | 活（只被建议生成消费） |
| （仅仓储，无实体） | `person_embeddings` | person_id PK/embedding(BLOB 声明，实存 JSON TEXT)/created_at | **无生产者** | **读活写死** |
| `ArchiveRecord` `domain/entities/archive.py` | `archive_records` | photo_id/target_*/status/archived_at/error | `ArchiveExecutor` | 活 |

---

## 4. 数据关系

### 4.1 外键与级联（以 007 为终态）

```
import_batches 1─N import_draft_rows            [CASCADE]
import_draft_rows.merge_target_id → people(id)  [SET NULL]
people.source_batch_id → import_batches(id)     （003 仅加列，未建 FK 约束）
folders 1─N photos                              [SET NULL]

photos 1─N recognition_results                  [CASCADE]
people 1─N recognition_results                  [SET NULL]   ← 删人员保留照片归属为"未知"

people 1─N person_embeddings                    [CASCADE]
people 1─N person_face_embeddings               [CASCADE]    ← 删人员直接删除样本（非停用）

recognition_runs 1─N recognition_run_photos     [CASCADE]
recognition_runs 1─N recognition_run_scopes     [CASCADE]
recognition_runs 1─N face_observations          [CASCADE]
photos 1─N recognition_run_photos               [CASCADE]    ← 删照片连带删快照
photos 1─N face_observations                    [CASCADE]

recognition_runs 1─N face_cluster_runs          [CASCADE]
face_cluster_runs 1─N face_clusters             [CASCADE]
recognition_runs 1─N face_clusters              [CASCADE]（冗余直连 run_id）
face_clusters 1─N face_cluster_members          [CASCADE]
face_observations 1─N face_cluster_members      [CASCADE]    ← 观测消亡 → 聚类归属消亡

face_clusters 1─N cluster_person_assignments    [CASCADE]
people 1─N cluster_person_assignments           [CASCADE]    ← 删人员直接删除决策历史
face_observations 1─N person_face_embeddings    [CASCADE]
```

唯一约束：`photos(raw_path,path_base)`、`folders(raw_path,path_base)`、`people.identity`、
`face_observations(run_id,photo_id,face_index)`、`recognition_run_photos(run_id,photo_id)`、
`recognition_run_scopes(run_id,ordinal)`、`face_cluster_members(cluster_id,observation_id)`、
`person_face_embeddings(person_id,observation_id)`。

### 4.2 派生关系（无 FK，靠代码维持）

| 关系 | 维持者 | 证据 |
|---|---|---|
| 聚类输入 = 某 run 的 observations | `ClusterFacesService._cluster_all` | `cluster_faces_service.py:109-134` |
| 建议输入 = 某 cluster_run 的 clusters+members + 该 run 的 observations + enabled 样本 + 全部 people | `SuggestPairingsService.execute` | `suggest_pairings_service.py:78-124` |
| **兼容行（APPROVED）= 当前有效指派（confirmed）的投影** | `_sink_confirmation` / `_retract_confirmation` | `pairing_workbench_service.py:276-374` |
| 归档项 = `(person_id, photo_id)` 的 APPROVED 行 | `ArchivePlanner.plan` | `archive_planner.py:106-143` |
| 失败/重试集 = run_photos 减去有观测的 photo_id | `RecognitionFailureService.report` | `recognition_failure_service.py:80-94` |

### 4.3 一处需要特别注意的不对称

`recognition_results` 有两种**语义上不同**的 APPROVED 行来源，归档无法区分：
1. 用户在审核中心对 PENDING 行点"通过"（`review_recognition_service.py` + `update_status`；**Stage 4 D-1 后批准可同时写入人工指定的 `person_id`**，`sqlite_recognition_repository.py:298-330`——未指定身份时该行仍不可归档）；
2. 配对工作台确认/改派写入的投影（`add`，带 `status=APPROVED`）。
两者在表中字段完全相同（无来源标记列）。执行计划 D3 建议"含来源标记"，实际**未实现来源标记**。

---

## 5. 数据生命周期

| 数据 | 创建 | 更新 | 删除/失效 |
|---|---|---|---|
| `import_batches` / `import_draft_rows` | 解析时 | 草稿行整体替换；批次状态一次置 confirmed | **无删除路径**（草稿批次无清理策略，PROJECT_STATUS 已登记为边界） |
| `people` | 确认导入 / 人员页新增 / 回填 | upsert（改名/部门/备注/roster_order）；`reorder` 批量改序 | 人员页删除（物理删除） |
| `photos` | 扫描登记 | 元数据/拍摄时间补齐 | 照片删除 / 重复处置 / 重扫对账 |
| `recognition_runs`（+scopes/+run_photos） | 每次识别新建 | 仅 status/统计列/finished_at 更新；`parameters` **永不更新** | 无显式删除；照片删除级联删 run_photos |
| `face_observations` | 同上 | **从不更新**（追加型，无 ON CONFLICT） | 随 run/照片 CASCADE |
| `recognition_results` | 识别兼容投影（一次）；配对确认；CLI recognize | 仅 `status`（审核迁移）；配对写入新行 | 配对解除/改派 DELETE；照片删除 CASCADE；人员删除 SET NULL |
| `face_cluster_runs` / `face_clusters` / `members` | 每次聚类新建 | run 状态/统计；cluster 仅 status | 随 recognition run / observation CASCADE；**无 UI 删除簇** |
| `cluster_person_assignments` | 建议 / 人工操作 | status/sort_snapshot/confirmed_at | 随 cluster / person CASCADE；同簇历史行保留（多行表达历史） |
| `person_face_embeddings` | 配对确认/改派 | `enabled` 置 0 | 随 person / observation CASCADE |
| `person_embeddings` | **无人创建** | — | 随 person CASCADE |
| `archive_records` | 归档执行 | PLANNED → 终态 | 随 photo CASCADE |

**"历史是否保留"的直接回答**：识别与聚类都是**追加型**——重跑新增 run/代际，旧 run、旧观测、旧簇集合一律不动（`run_recognition_service.py:47`、`cluster_faces_service.py:70`、迁移注释 `004_...py:24`、`006_...py:19`）。**唯一会被覆盖/删除的是 `recognition_results`**（审核改状态、配对改派时 DELETE 旧 person 的行），以及 `import_draft_rows`（编辑期整体替换）。

---

## 6. 状态及状态转换

### 6.1 `recognition_runs.status`（`recognition_run.py:24-45`）
`created → running → completed | failed | cancelled`；终态不可回退（`:150-158` 抛 ValidationError）。仅 `RecognitionRun` 实体的 `start/complete/fail/cancel` 能改。

### 6.2 `face_cluster_runs.status`（`face_cluster.py:31-52`）
与 6.1 同型的五态机（`FaceClusterRun.start/complete/fail/cancel` `:104-150`）。

### 6.3 `face_clusters.status`（六态定义 `face_cluster.py:54-69`）
| 值 | 是否被写入 | 写入点 |
|---|---|---|
| `pending` | 是（创建默认） | `cluster_faces_service.py:176-183` |
| `unknown` / `ignored` | 是 | `pairing_workbench_service.py:233-244` |
| `confirmed` / `split` / `merged` | **否** — 无任何写入者 | 计划 §D-2/§3.2 定义，未实现 |

### 6.4 `cluster_person_assignments.status`（`cluster_assignment.py:60-71`）
```
suggested → confirmed | rejected | unassigned
confirmed → unassigned
rejected  → unassigned
unassigned → （终态，无出边）
```
当前有效行 = `{suggested, confirmed}`（`:45-47`）。PENDING-like 重复确认/重复拒绝会被实体拒绝（`:125-131`）。

### 6.5 `recognition_results.status`（`recognition.py:11-21`）
`pending → approved | rejected`（`approve()/reject()` 只能从 pending，`:60-75`）。注意：配对工作台写入的 APPROVED 行**绕过**实体状态机（直接以 `status=APPROVED` 构造，`RecognitionResult.__post_init__` 不校验初始状态）。

### 6.6 `import_batches.status`
`draft`（创建）→ `confirmed`（确认）。`cancelled` 定义但**永不写入**。

### 6.7 `archive_records.status`
`planned → dry_run | archived | skipped | renamed | overwritten | failed`（`archive_executor.py:139-339`；成功态集合 `archive_planner.py:28-33`）。

---

## 7. 自动/人工边界

### 7.1 全自动（无人工确认即生效）

| 动作 | 副作用范围 |
|---|---|
| 解析名单文件 | 只写草稿（不影响正式人员） |
| 识别检测 + 观测落库 | 写 `recognition_runs/run_scopes/run_photos/face_observations` |
| 识别兼容投影 | **写 `recognition_results`(PENDING)** ← 这是唯一一处"自动写审核队列" |
| 聚类 | 写 cluster run / clusters / members |
| 建议生成 | 写 assignments(`suggested`) |
| 归档计划（preview） | 零副作用（`archive_planner.py:38-41` 明述） |

### 7.2 必须人工

| 动作 | 唯一性 |
|---|---|
| **确认导入** | 草稿路径写 `people` 的唯一入口（`confirm_import_service.py`；GUI 无第二条） |
| 人员新增/编辑/排序/删除 | 人员页 |
| 识别范围选择 | 全部/选中/重试 + 人脸数范围（`recognition_scope_dialog.py`） |
| **确认配对（→confirmed）** | 无自动确认路径（`domain/services/pairing.py:15`） |
| 拒绝/解除/改派/标陌生/忽略 | 配对工作台 |
| 审核通过/拒绝（legacy PENDING） | 审核中心 |
| 归档执行 | 对话框确认；dry-run 默认勾选 |

### 7.3 边界上的"半自动"事实（易误解，需重点记录）

1. **识别会自动产生 PENDING 审核项**——只要照片在范围内且此前从无 `recognition_results` 行。因此"自动检测"会间接进入归档候选（经用户审核通过后；**Stage 4 D-1 后审核批准须同时指定人员身份才可归档**）。
2. **配对确认会自动写归档候选**——确认一次即向 `recognition_results` 写多行 APPROVED，**立即可被归档计划消费**（D3 裁决"确认即可归档"）。
3. **聚类阈值与配对阈值不可由用户调整**，全部固化在命令默认值（0.5/0.4/0.0 与 0.40）。
4. **聚类结果不可在 UI 中确认/合并/拆分**——`ClusterResultsDialog` 严格只读（无任何写调用），簇身份的唯一修改入口是配对工作台的确认/改派。

---

## 8. 异常与分支

| 场景 | 行为 | 证据 |
|---|---|---|
| 图片不可读 | `unreadable_count+1`；**不建 Observation**；批次继续 | `run_recognition_service.py:106-107`；`face_analysis_task.py:40-41` |
| 检测抛异常 | `error_count+1`；**不建 Observation**；异常隔离到单张 | `:108-110`；`face_analysis_task.py:42-43` |
| 检出 0 脸 | `no_face_count+1`；**不建 Observation** | `:111-112` |
| 人脸数不在选中范围 | 仍保存**全部** Observation，`scope_verdict='out_of_selected_scope'`；不写兼容行 | `:116-123`、`face_observation.py:67-83` |
| 该照片已有任意 `recognition_results` 行 | **跳过兼容写入**（不更新、不覆盖） | `:125` |
| 用户取消识别 | 已 flush 观测保留；run → cancelled（携带已处理统计） | `:93-94`；`recognition_run.py:134-139` |
| 识别中途未捕获异常 | 已 flush 观测保留；run → failed 并记 error 后**上抛** | `:96-102` |
| 同 run 重复观测 | `IntegrityError`（无 ON CONFLICT） | `sqlite_face_observation_repository.py:28-31` |
| 聚类无参与观测 | run completed，cluster/member 计数 0，`excluded_count`=全部 | `cluster_faces_service.py:112-114` |
| 聚类算法阶段取消 | run cancelled，0 簇落库 | `:95-99` |
| 聚类持久化失败 | run failed + error 后抛出 | `:100-103` |
| 聚类指定 run 不存在 | `ValidationError` | `:72-76` |
| 确认非 suggested 的指派 | `ValidationError` | `pairing_workbench_service.py:108-111` |
| 赋权给不存在的 cluster/person | `ValidationError` | `:254-266` |
| 指派行被并发删除（update 返回 0） | `ValidationError` | `:123-126` 等 |
| 归档路径已存在 | 按策略 `skip`(默认)/`overwrite`/`rename` | `archive_executor.py:192-226`；ADR-011 |
| 归档源文件缺失 / 目标越界 | item 级 FAILED，批次继续 | `:139,149,185,245-276` |
| 归档照片相对路径 | 计划阶段直接 skip | `archive_planner.py:192-197` |
| 已成功归档的 `(person, photo)` | 计划阶段 skip | `:201-208` |
| 删除照片 | CASCADE 删 `recognition_results`/`face_observations`/`run_photos`/`archive_records` | 迁移 002/004 FK；`tests/unit/infrastructure/test_deletion_cascade.py` |
| 删除人员 | `recognition_results.person_id` → NULL；`person_embeddings`/`person_face_embeddings`/`cluster_person_assignments` **整体 CASCADE 删除** | 迁移 002/007 FK；`sqlite_person_repository.py:71-80`；`delete_person_service.py:86-100` |

> ⚠️ 上表最后一行值得单列：删除人员会**物理删除**其全部 `cluster_person_assignments` 决策历史与 `person_face_embeddings` 样本，**不会**转成 `unassigned` 或 `enabled=0`。执行计划 B-2 曾要求"置 unassigned / 停用"，**未实现**（详见 §10 冲突 5）。

---

## 9. 当前实现状态

### 9.1 18 个关键检查点逐条结论

| # | 检查点 | 状态 | 核心证据 |
|---|---|---|---|
| 1 | 人员名单导入流程 | **IMPLEMENTED + TESTED** | `parse_import_draft_service.py` / `confirm_import_service.py` / `import_preview_dialog.py`；`tests/integration/test_import_draft_flow.py`（12 项）、`test_bulk_people_import_closed_loop.py:102`（1200 行真实闭环）、`test_excel_import_ui_closed_loop.py` |
| 2 | `people.roster_order` 真实用途 | **IMPLEMENTED** | ① `list_all()` 排序主键（`sqlite_person_repository.py:109-117`）；② 确认导入全局续号（`confirm_import_service.py:67`）；③ 人员页重排（`reorder` `:125-135`）；④ 人员页新增取 MAX+1（`manage_people_service.py:81`）；⑤ **配对规则③ 的人员顺序轴**（`domain/services/pairing.py:82-86`）；⑥ F 阶段回填 COALESCE 保序（`sqlite_person_repository.py:53-69`）。**非唯一约束**（迁移 003 仅加列+索引） |
| 3 | 照片进入识别的入口 | **IMPLEMENTED + TESTED** | 三条入口：全部 / 照片库选中 / 重试失败照片；**不再有"仅未匹配"过滤**。`recognition_run_controller.py:82-94`、`main_window.py:1440-1450` |
| 4 | RecognitionRun 创建/状态/生命周期/照片范围 | **IMPLEMENTED + TESTED** | 创建 `run_recognition_service.py:49-60`；状态机 `recognition_run.py:110-158`；照片范围 = `recognition_run_photos` 快照 + `recognition_run_scopes` 范围；测试 `test_run_recognition_service.py`(6)、`test_stage_c_commit1.py:68`、`test_stage_c_recognition_repositories.py:48`、`test_stage_f_lifecycle.py`(5, 1200 张) |
| 5 | FaceObservation 产生/字段/保存/关联 | **IMPLEMENTED + TESTED** | 产生 `run_recognition_service.py:114-123`；字段 `face_observation.py:38-64`；保存 `sqlite_face_observation_repository.py:26-66`（50/批、无 ON CONFLICT）；关联 = run_id + photo_id；测试 `test_run_recognition_service.py:43-64,122` |
| 6 | 不可读 / 无脸 / 检测失败 | **IMPLEMENTED + TESTED** | 三者均不建 Observation，分别计 `unreadable_count` / `no_face_count` / `error_count`；**分类无法从数据上事后区分**（失败清单统一文案 `recognition_failure_service.py:31`，Spec Gap 已自陈）。测试 `test_run_recognition_service.py:43,85`、`test_stage_f_lifecycle.py:208` |
| 7 | FaceCluster/Member 是否真实参与业务 | **IMPLEMENTED** | 参与：建议生成的输入（`suggest_pairings_service.py:78-108`）、结果展示（`cluster_results_service.py`）、确认时的样本与兼容投影来源（`pairing_workbench_service.py:276-345`）。**不参与**：归档（`archive_planner.py` import 无聚类相关） |
| 8 | 人脸对象/分组如何形成 | **IMPLEMENTED + TESTED** | 两段式纯算法 `face_clustering.py:74-185`；21 项算法单测 `tests/unit/domain/test_face_clustering_algorithm.py` |
| 9 | 人员配对如何执行 | **IMPLEMENTED + TESTED** | 三规则 `domain/services/pairing.py:60-146`；领域单测 `test_stage_e_pairing_domain.py`（含 Stage 4 D-2 三点边界用例） |
| 10 | ClusterPersonAssignment 是否已实现 | **IMPLEMENTED + TESTED** | 实体+状态机 `cluster_assignment.py`；仓储 `sqlite_cluster_assignment_repository.py`；5 项仓储测试 + 6 项服务测试 + 8 项对话框测试 |
| 11 | 自动配对与人工修正边界 | **IMPLEMENTED** | 自动只到 `suggested`；`confirmed` 仅人工（`pairing_workbench_service.py:105-137,185-229`）；人工改派会回收旧身份投影与样本（`:347-374`）；测试 `test_stage_e_remediation.py:297-330` |
| 12 | `recognition_results` 旧兼容链 | **IMPLEMENTED（活）** | 仍是审核/筛选/徽标/就绪/导出/删除预览/**归档**的唯一识别数据源。写入方 4 个：识别兼容投影、配对确认、配对回收（DELETE）、审核状态迁移（+CLI recognize 旧管线） |
| 13 | `person_embeddings` 现状与实际用途 | **PARTIAL（读活写死）** | `list_all` 被 `run_recognition_service.py:66`、`match_persons_service.py:159`、`delete_person_service.py:65` 读取；**`save` 无任何生产调用者** → 生产环境该表恒空，识别兼容投影的匹配候选集恒为空（故 `person_id` 恒为 NULL）。Stage E 的替代物是 `person_face_embeddings`，但**只被建议生成消费，未接回识别** |
| 14 | 归档消费哪些识别/配对结果 | **IMPLEMENTED + TESTED** | **仅** `recognition_results` APPROVED（+people+photos+archive_records）。测试 `test_stage_e_remediation.py:364,398`（多 attribution / 改派后身份）、`test_step11_archive_e2e.py`(5)、`test_archive_planner.py`(10) |
| 15 | rerun 如何创建与保存数据 | **IMPLEMENTED + TESTED** | 识别：新 `RecognitionRun` + 新观测，旧 run 不动（`run_recognition_service.py:47-58`）；聚类：新 `FaceClusterRun` + 新簇（`cluster_faces_service.py:70-86`）。测试 `test_run_recognition_service.py:67-82`、`test_cluster_faces_service.py:160`、`test_stage_f_lifecycle.py:142` |
| 16 | 历史数据是否保留 | **IMPLEMENTED（除 recognition_results）** | 迁移 004/006/007 均"不迁移既有数据"；观测/簇追加型；**`recognition_results` 会被状态迁移与配对回收改写/删除**；草稿行编辑期整体替换 |
| 17 | 状态如何转换 | **IMPLEMENTED** | 见 §6（5 套状态机），其中聚类簇的 `confirmed/split/merged` 与批次的 `cancelled` 为**定义未使用** |
| 18 | UI→Controller→Service→Domain→Repo→DB 调用链 | **IMPLEMENTED** | 见 §2；分层守卫 `tests/unit/architecture/test_layer_boundaries.py` |

### 9.2 汇总矩阵

| 能力 | 状态 |
|---|---|
| 名单两段式导入（草稿/预览/确认/合并/拆分/顺序） | IMPLEMENTED + TESTED |
| 直通导入（CLI/插件） | IMPLEMENTED（无草稿） |
| 历史人员回填 | IMPLEMENTED + TESTED（`test_stage_f_services.py:83-148`、`test_upgrade_integrity.py:161`） |
| 多脸检测 + 全脸观测 | IMPLEMENTED + TESTED |
| 识别范围选择（全部/选中/重试）+ 人脸数范围 | IMPLEMENTED + TESTED |
| 可追溯 run + 统计 + 失败清单导出 | IMPLEMENTED + TESTED |
| 聚类（两段式） | IMPLEMENTED + TESTED |
| 聚类结果查看 | IMPLEMENTED（**只读**） |
| 簇的人工合并/拆分 | **PLANNED（未实现）**——无 `MergeClustersService`/`SplitClusterService`（全仓 grep 零命中） |
| 配对建议（三规则） | IMPLEMENTED + TESTED |
| 配对工作台确认/拒绝/解除/改派/标陌生/忽略 | IMPLEMENTED + TESTED |
| 多样本匹配（1:N max 余弦）接入识别 | **PLANNED（未实现）**——执行计划 E-3 未落地 |
| 阈值/质量公式校准 | **PARTIAL**——已出报告与证据，数值未变更，Owner 裁决点未决（`docs/development/stage-f-calibration-report.md:118-124`） |
| 归档 | IMPLEMENTED + TESTED |
| 真实数据端到端 | IMPLEMENTED（工具级证据）——`tools/validate_stage_f.py`、`tools/stress_lifecycle_stage_f.py`；报告 `stage-f-calibration-report.md` |
| 全量测试通过 | **已实跑复现**：Stage 4.1 复审（2026-09-28）全量 `pytest` = **1310 passed / 6 skipped**（233.25s），与 `2823d1c` 提交信息一致 |

---

## 10. 代码 / 测试 / 文档冲突

### 冲突 1（重要）：执行计划 E-3「后续照片匹配切换」未实现，但兼容投影仍依赖空表
- 计划：`docs/development/people-import-face-clustering-execution-plan.md:206-208`（E-3）要求"候选 = `person_face_embeddings` 启用态多样本 max 余弦"。
- 代码：`RunRecognitionService` 仍然读 **`person_embeddings`**（`run_recognition_service.py:66`），而该表**无生产者**。
- 后果（INFERRED）：新识别运行的兼容行 `person_id` 恒为 `NULL`；**自动识别本身尚未建立最终人员身份**。新数据的最终身份只能来自人工动作——配对工作台确认/改派，**或审核中心批准时指定人员（Stage 4 D-1 落地后）**。**Stage E 的样本沉淀目前不回流到识别**。（Stage 4 BLK-5 后该行的 `confidence` 为 `NULL`——「无相似度证据」，而非 `0.0`。）
- 注：`stage-f-calibration-report.md:31` 记录实测确为"无样本库故无 sample_match"，与代码一致——即报告承认现象，但计划 E-3 的切换承诺未兑现。

### 冲突 2：重试运行的参数快照标签写不进 `retry`
- 控制器注释声称 `scope_label（retry/selected/all）进参数快照`（`recognition_run_controller.py:100-101`）。
- 但 `scope_label` **无任何调用者**（全仓 grep 仅控制器自身），`main_window.py:1451-1454` 未传该参数 → 重试路径实际写入 `photo_scope="selected"`。
- 影响：重试运行在 `parameters` 里与"手动选中"不可区分（可追溯性缺口，非功能缺陷）。

### 冲突 3：执行计划 C-1 的 schema 草案与迁移 004 不一致
- 计划（`:110-121`）写 `recognition_runs(algorithm_version, scope, photo_count, ...)`、`face_observations(captured_at_snapshot, created_at)`。
- 实际（`alembic/versions/004_recognition_runs_and_observations.py`）：无 `algorithm_version/scope/photo_count` 列；改以 `parameters` JSON 快照 + 六个独立统计列 + 独立 `recognition_run_photos`/`recognition_run_scopes` 表；观测无 `captured_at_snapshot`。
- 判定：**代码为准，计划文档已过期**（004 的 docstring `:8-23` 给出 C-SEM-1/2/3/4 的更细裁决）。

### 冲突 4：执行计划 D-1/D-2 与迁移 006 不一致
- 计划（`:149-165`）中 `face_clusters` 直连 `run_id`，无 `cluster_run_id`；无 `ordinal/sort_key/member_count/algorithm_version`。
- 实际 006 新增独立代际容器 `face_cluster_runs` 并保留 `run_id` 冗余列（`006_face_clusters.py:20-31`）。
- 判定：代码为准。

### 冲突 5：人员删除的指派/样本级联语义与计划 B-2 不一致
- 计划 B-2（`:94-96`）要求"新增对 `cluster_person_assignments`/`person_face_embeddings` 的级联处置（**置 unassigned / 停用**）"。
- 实际：`DeletePersonService` 不涉及这两张表（`delete_person_service.py:56-100` 只用 people/photos/recognition/face_embeddings 四个仓储）；唯一处置是迁移 007 的 **`ON DELETE CASCADE`（物理删除）**。
- 判定：**实现与计划的分歧**——删除人员会丢失身份决策历史与样本，且 `unassigned` 从不被写入（该状态仅由工作台"解除映射/改派"路径产生）。

### 冲突 6：PROJECT_STATUS §7 迁移链滞后
- `.ai/PROJECT_STATUS.md` §7 写"迁移链 `001`→`002`→`003`"。
- 实际存在 `004`–`007`（`alembic/versions/`）。属文档滞后（同类滞后亦见 §5「阶段 A 验收证据」中 `head 记录 003...` 的表述）。

### 冲突 7：Stage F 校准报告 §5 的范围声明已过期
- `stage-f-calibration-report.md:112-116` 称"历史人员回填、重分析入口 + 失败清单导出属 Stage F 后续提交，**本轮未实施**"。
- 实际已实现（提交 `d47d984`）：`backfill_historical_people_service.py`、`recognition_failure_service.py`、`tools/backfill_historical_people.py`。
- 判定：报告写作时点早于实现，**结论语句需以代码为准**。

### 冲突 8：`recognition_results` 的"来源标记"缺失
- 计划 D3（`:27`）要求兼容行"含来源标记"。
- 实际表结构无来源列（迁移 002 `:85-95`），配对写入的行与审核通过的行在库内无法区分。
- 判定：**未实现**（对归档语义无影响，对审计/调试有影响）。

### 冲突 9：KNOWN_ISSUES 声称"无未决问题"，但存在未登记的实现缺口
- `.ai/KNOWN_ISSUES.md:41` 明确"当前无未决问题条目"。
- 但 §10 冲突 1/5 所述缺口（E-3 未切换致匹配候选集恒空；删人员丢指派历史）**未登记**为该文件的 Issue，也未在 PROJECT_STATUS 中登记为 Remaining。
- 判定：**文档治理冲突**（信息存在但未进入 SSOT 问题清单）。

### 冲突 10：`face_clusters.status` 六态与只写三态
- 计划/实体定义六态（`face_cluster.py:54-69`，含 `confirmed/split/merged`）；实际只写 `pending/unknown/ignored`（§6.3）。
- 判定：**定义超前于实现**（属预留，非缺陷，但读者易误判"簇可确认"）。

### 无冲突但需记录的"测试与实现并存"现象
`MatchPersonsService`/`MatchPersonsController` 已被 UI 退役（架构守卫测试 `test_recognition_entry_migration.py:43-69` 断言 presentation 不再 import），但**服务实现与 13+10 项旧单测仍保留**，且 CLI `recognize` 仍走该路径。即"退役"仅限 Presentation 层。

---

## 11. 未确认事项

| # | 未确认项 | 为什么无法确认 | 建议 Stage 2 动作 |
|---|---|---|---|
| 1 | 全量 pytest 是否通过 | **已由 Stage 4.1 复审实跑复现：1310 passed / 6 skipped**（2026-09-28，与 `2823d1c` 提交信息一致） | 已关闭；后续代码变更后需重跑 |
| 2 | 生产库中 `person_embeddings` 是否真的为空 | 需读用户数据目录 `%LOCALAPPDATA%` 的实际库；代码层只能证明"无写入者" | 检查真实库行数与 `recognition_results.person_id` 非空比例 |
| 3 | 生产库中 `face_clusters.status` 是否有非 `pending` 值、`cluster_person_assignments` 实际使用程度 | 同上，需真实数据 | 统计各表行数分布 |
| 4 | 真实库中 `parameters["photo_scope"]` 是否出现过 `retry` | 冲突 2 推论为"不可能"（INFERRED），需数据验证 | 抽样 `recognition_runs.parameters` |
| 5 | 聚类质量（0.5/0.4 阈值是否合理） | 需 Owner 人工缩略图复核（`stage-f-calibration-report.md:124`） | 属 Owner 决策，非代码可证 |
| 6 | E-SG-4「合格样本」定义 | 报告自陈 Spec Gap（`:122`） | 等待规格裁决 |
| 7 | E-SG-5「改派后旧样本停用之外的样本恢复语义」 | 同上（`:123`） | 等待规格裁决 |
| 8 | 10k+ 观测的聚类性能 | 仅外推到 4000（`stage-f-calibration-report.md:56-68`），未实测 | 如需扩容再测 |
| 9 | 草稿批次的清理策略 | PROJECT_STATUS 自陈"暂无自动清理策略" | 属产品决策 |
| 10 | `people.source_batch_id` 是否真的有 FK 约束 | 迁移 003 只 `ALTER TABLE people ADD COLUMN source_batch_id TEXT`，**未加 REFERENCES**（`003_...py:67`）；`PRAGMA foreign_keys=ON` 对该列无约束效果 | 可写入任意 UUID 而不报错——属设计（软引用），建议 Stage 2 确认是否有意为之 |

---

## 12. 证据索引

### 12.1 迁移（Schema 权威）
| 文件 | 内容 |
|---|---|
| `alembic/versions/001_initial_v4.py` | 空 stamp（user_version=4 兼容） |
| `alembic/versions/002_split_create_ddl.py` | 6 表 + 6 索引：people/folders/photos/**recognition_results**/**person_embeddings**/archive_records |
| `alembic/versions/003_import_batches_and_roster.py` | `import_batches`、`import_draft_rows`、`people.roster_order` + `source_batch_id` |
| `alembic/versions/004_recognition_runs_and_observations.py` | `recognition_runs`、`recognition_run_photos`、`recognition_run_scopes`、`face_observations` |
| `alembic/versions/005_recognition_run_error_count.py` | `recognition_runs.error_count` |
| `alembic/versions/006_face_clusters.py` | `face_cluster_runs`、`face_clusters`、`face_cluster_members` |
| `alembic/versions/007_assignments_and_person_samples.py` | `cluster_person_assignments`、`person_face_embeddings` |
| `src/photo_archiver/infrastructure/database/sqlite_connection.py:128-166` | `initialize_schema` 已不持 DDL，转调 Alembic（ADR-027） |

### 12.2 领域实体与领域服务
`domain/entities/import_batch.py`、`person.py`、`photo.py`、`recognition.py`、`recognition_run.py`、`face_observation.py`、`face_cluster.py`、`cluster_assignment.py`、`archive.py`；
`domain/services/face_clustering.py`（ALGORITHM_VERSION + 两段式）、`domain/services/pairing.py`（三规则）。

### 12.3 应用服务
`application/services/`：`parse_import_draft_service.py`、`confirm_import_service.py`、`import_people_service.py`、`manage_people_service.py`、`backfill_historical_people_service.py`、`run_recognition_service.py`、`face_analysis_task.py`、`recognition_failure_service.py`、`list_recognition_runs_service.py`、`cluster_faces_service.py`、`cluster_results_service.py`、`suggest_pairings_service.py`、`pairing_workbench_service.py`、`review_recognition_service.py`、`archive_planner.py`、`archive_path_builder_service.py`、`archive_photos_service.py`、`archive_executor.py`、`delete_person_service.py`、`workspace_readiness.py`、`search_photos_service.py`、`export_service.py`、`match_persons_service.py`、`list_persons_service.py`。

### 12.4 仓储实现（SQL 权威）
`infrastructure/database/`：`sqlite_person_repository.py`、`sqlite_import_batch_repository.py`、`sqlite_recognition_run_repository.py`、`sqlite_face_observation_repository.py`、`sqlite_face_cluster_repository.py`、`sqlite_cluster_assignment_repository.py`、`sqlite_recognition_repository.py`、`sqlite_face_embedding_repository.py`、`sqlite_archive_record_repository.py`、`sqlite_photo_repository.py`、`sqlite_mappers.py`。

### 12.5 表现层接线
`presentation/views/main_window.py`（262/279/287 控制器构造；307/311/315 QAction；615 人员页；1100 导入；1127 确认；1174 归档；1465/1488/1502 聚类与配对入口）、`people_admin_page.py`（160-162 信号；531-540 按钮；551-597 运行选择）、`import_preview_dialog.py`、`recognition_scope_dialog.py`、`cluster_results_dialog.py`、`pairing_workbench_dialog.py`、`archive_preview_dialog.py`、`review_dialog.py`；
`presentation/controllers/`：`recognition_run_controller.py`、`cluster_faces_controller.py`、`archive_controller.py`、`match_persons_controller.py`（已退役）、`import_people_controller.py`、`workspace_controller.py`；
`app/services.py:180-400`（装配，含 `_build_recognition_services` 模型包门控 `:353-393`）、`app/repositories.py`、`app/ui_assembly.py`。

### 12.6 测试（覆盖证据，均为 TESTED）
| 主题 | 文件 |
|---|---|
| 识别 run / 观测 / 取消 / 错误 / 兼容行 | `tests/unit/application/test_run_recognition_service.py`（6） |
| 千张生命周期与重试 | `tests/unit/application/test_stage_f_lifecycle.py`（5） |
| Stage F 服务（回填/失败/重试） | `tests/unit/application/test_stage_f_services.py`（10） |
| 聚类服务 | `tests/unit/application/test_cluster_faces_service.py`（13） |
| 聚类算法 | `tests/unit/domain/test_face_clustering_algorithm.py`（21） |
| 聚类结果读 | `tests/unit/application/test_cluster_results_service.py`（5） |
| Stage E 配对服务/领域/整改/仓储 | `test_stage_e_pairing_services.py`（6）、`test_stage_e_pairing_domain.py`（14）、`test_stage_e_remediation.py`（7）、`test_stage_e_assignment_repositories.py`（5） |
| Stage C 领域/仓储 | `test_stage_c_commit1.py`（6）、`test_stage_c_recognition_repositories.py`（4） |
| Stage D 仓储 | `test_stage_d_cluster_repositories.py`（7） |
| 导入闭环 | `test_import_draft_flow.py`（12）、`test_bulk_people_import_closed_loop.py`（1）、`test_excel_import_ui_closed_loop.py`（2）、`test_import_people_transactional.py`（9） |
| 归档 | `test_step11_archive_e2e.py`（5）、`test_archive_planner.py`（10） |
| 升级完整性 | `test_upgrade_integrity.py`（3） |
| 架构守卫 | `test_recognition_entry_migration.py`（3）、`test_layer_boundaries.py` |
| 迁移 | `tests/integration/database/test_alembic_migrations.py` |

### 12.7 计划与报告（PLANNED 的判定来源）
- `docs/development/people-import-face-clustering-development-plan.md`（Owner 业务方案）
- `docs/development/people-import-face-clustering-execution-plan.md`（阶段 A–F 工程计划 + 决策点 D1–D6）
- `docs/development/stage-f-calibration-report.md`（真实 473 张校准/性能/一致性证据 + 遗留裁决点）
- `docs/development/stage-a-import-acceptance-script.md`（阶段 A 验收）
- `docs/user-guide/manual.md`、`docs/user-guide/workflow.md`（用户可见行为）

### 12.8 状态与决策（SSOT）
- `.ai/PROJECT_STATUS.md`（当前状态；§7 迁移链表述滞后见冲突 6）
- `.ai/ARCHITECTURE_DECISIONS.md`（ADR-009 `recognition_results`、ADR-010 归档命名、ADR-011 冲突策略、ADR-017 1:N Top-1、ADR-036 Windows 名净化）
- `.ai/KNOWN_ISSUES.md`（LIMIT-001/002/004/006；无 Open 缺陷条目）

### 12.9 关键 Git 证据
```
2823d1c fix: resolve business baseline freeze blockers   ← 当前基线（Stage 4 阻断修复 + D-1/D-2 落地）
b3b8685 test(stage-f): add 1000-photo lifecycle stress and upgrade integrity
d47d984 feat(stage-f): add people backfill, retry entry and failure-list export
e7d2735 feat(stage-f): add real-data calibration and performance evidence
f6e70b0 fix(pairing): sync compat layer with current assignments per E-SG-6
ee5d7d4 feat(pairing): add cluster-to-person identity assignment (Stage E)
c543828 feat(clustering): add D-4 UI entry and results view
5c3c6d2 feat(clustering): add traceable face cluster runs
a9f15b3 feat(recognition): switch UI entry to traceable runs
7ec3173 feat(recognition): add traceable multi-face runs
73657ec feat: add recognition run data foundation
```
（`git log`；0004/007/008 迁移时间戳与提交顺序一致。）

---

## 13. 已知限制（Stage 4.1 复审登记；明确**不升级为本次 Freeze Blocker**）

> 来源：`Stage4_1_FinalReview.md` §12（KL-1..KL-8）。逐项均为**有界、可解释的现状事实**，此处仅登记，不做设计变更。

| # | 已知限制 | 现状事实 |
|---|---|---|
| KL-1 | `person_embeddings` 无 producer，仅作 legacy compatibility | `FaceEmbeddingRepository.save` 在 `src/` 零调用；`run_recognition_service.py:66` 读恒空表 → 识别期自动兼容行 `person_id` 恒 NULL，**自动识别本身尚未建立最终人员身份**（D-1 后由人工动作补身份） |
| KL-2 | 存量 ambiguous-name archive rows 的 name fallback | migration 008 只在**姓名唯一命中**时回填 `person_id`，重名行保持 NULL 并继续按姓名回退去重——同名场景沿用升级前语义（`008:16-18`、`sqlite_archive_record_repository.py:110-118`） |
| KL-3 | Person 删除导致 `person_id -> NULL` 的历史限制 | `recognition_results.person_id`/`archive_records.person_id` 均 `ON DELETE SET NULL`；孤儿归档行此后按姓名参与去重——"删人 + 同名重建"可能被旧孤儿行静默抑制（真库探针已复现） |
| KL-4 | 尚未完成 runtime UI walkthrough | Stage 4 与 Stage 4.1 均未做 GUI 手工走查；以静态复核 + 真库探针 + 全量测试替代覆盖 |
| KL-5 | Stage 4.1 提出的测试证据覆盖缺口（GAP-1..5） | GAP-1 executor 未断言 `person_id` 落库；GAP-2 BLK-5 的 UI/导出 NULL 路径无测试；GAP-3 "rerun 不覆盖人工确认"用例为同义反复；GAP-4 review 身份选择器接线无测试；GAP-5 `test_archive_planner.py` 的 fake 复刻去重谓词（漂移风险） |
| KL-6 | migration 008 其余低风险项 | `recognition_results` 整表复制（大库升级耗时未实测）；008 表重建分支不可重入；`person_id` 索引仅在加列分支创建；downgrade 把 NULL confidence 折叠为 0.0 |

---

**报告结束。本文件为 Stage 2 的事实基础，不含对未来的建议与设计。**
