# CODE_LOGIC_AUDIT.md — 全面工程健康审计 · 代码与业务逻辑审计（Stage 2）

- **审计日期**: 2026-09-28 ｜ 对象: HEAD `2823d1c` ｜ 性质: READ-ONLY
- **方法**: 沿业务链读码追踪（入口→服务→域→仓储→持久化→结果）+ 定向回归测试佐证；每条结论附文件:行号证据
- **深度声明**: 归档/审核/配对/识别运行/扫描/导入六链为**行为级深查**；导出/删除/清理/重复处置/插件为**结构+关键路径抽查**；搜索/缩略图/设置/回填为**标记级+文档级**（见 §6 未深查清单）。诚实优先于表面覆盖。

---

## 1. 冻结阻断修复核验（AUD-004 收口）

2823d1c 提交声称"5 阻断项 + 2 裁决"落地。逐项核验结果：

| 项 | 判定 | 证据链 |
|---|---|---|
| BLK-1 归档去重身份 | ✅ **VERIFIED 全链** | migration 008（`alembic/versions/008_archive_identity_and_confidence.py`：person_id FK+回填幂等守护+重名保守回退）→ `sqlite_archive_record_repository.py:107-138`（has_successful_for_person：person_id 优先、NULL 行回退姓名）→ `archive_planner.py:219-225`（PlanItem 携带 person_id）→ `archive_executor.py` `_make_planned_record`（落盘 person_id）→ `sqlite_recognition_repository.py:219-241`（archivable_count 同口径，含 NULL 回退）。5 项回归：`test_freeze_blockers.py:87,109,128,147,174` |
| BLK-5 置信度三态 | ✅ **VERIFIED** | `domain/entities/recognition.py:44-48`（None=无证据，数值校验 [0,1]）；`pairing_workbench_service.py:314-321`（ordered_suggestion/manual 写 NULL、sample_match 写真实余弦，注释明示"不是 0.0"）；migration 008 重建表放宽 NOT NULL+按 002 重建命名索引；回归 `test_freeze_blockers.py:200,207,223,235` |
| D-1 人工结果为最终结果 | ✅ **VERIFIED 全链** | `review_recognition_service.py:51-71`（approve(result_id, person_id) 同写身份与状态，docstring 明示旧缺陷"批准后 person_id 恒 NULL 归档永不选中"）→ `review_controller.py:109-119`（person_id 透传）→ `review_dialog.py:162-168`（身份选择器，D-1 注释）；批量默认身份不覆盖行上已有决定（`test_freeze_blockers.py:320,343`）；`test_freeze_blockers.py:261`（approve→planner 选中）、`:298`（无身份批准→不可归档，语义显式化） |
| D-2 阈值 ≥0.40 | ✅ **VERIFIED（代码侧）** | `application/dtos/settings.py:12`（DEFAULT_MATCH_THRESHOLD=0.40）、`:83-85`（边界校验）、`app/services.py:375`（注入 matcher）。**证据侧缺口仍在**：`match_threshold` 在 stage-f-calibration-report.md 中 0 命中（F1-2 的"校准交付"未补）→ 归 Stage 5 文档核对 |
| F1-4 废弃 Top-1 规则残留 | ❌ **未修复** → **AUD-014（新）** | 见 §2 |
| F1-1 端到端贯通回归 | ⚠️ **部分** | `test_freeze_blockers.py` 以真实 SQLite 仓储覆盖 approve→plan 与 confirm→plan→execute 的**应用层**链；但两段式导入（Parse→Confirm）与配对确认（PairingWorkbench.confirm）→ArchiveExecutor.execute 仍无单条测试贯通（`tools/validate_stage_f.py:272-355` 直造名单且止于 plan()）。F1-1 主张的"全链单条回归"仍未成立 → 保留于 AUD-004，Stage 4 复核 |

## 2. 业务链行为审计

### 2A 归档链（深查）→ 发现 AUD-014 / AUD-015 / AUD-016

`ArchiveController/UI → ArchivePhotosService（编排：root 校验+strategy 默认）→ ArchivePlanner.plan()（预览侧无副作用）→ ArchiveExecutor.execute()（单 UoW 全批事务）→ per-item：PLANNED 落库 → 执行 → 终态 upsert`。

- **冲突策略**：skip/overwrite/rename 三态；Settings 层 fail-closed 校验（`infrastructure/config/settings.py:192-200`）；rename 采用确定性 `.archived-N` 计数（`_compute_renamed_target`），并发同 plan 重跑安全。
- **越界防护**：三层（词法 relative_to + resolve(strict=False) 跟随符号链接 + 拒绝写穿叶级 symlink），dry-run 同样校验（P2-005/M-3/M-4 注释链完整，mtime 保留有明确业务理由——重扫回退 mtime 提取拍摄时间）。
- **失败隔离**：逐项 OSError→mark_failed→继续；DB 异常不在此列（见 AUD-015）。
- **幂等**：add 为 by-id upsert；同 record PLANNED→终态两次 add 幂等；成功态去重 (person, photo)；FAILED/PLANNED/DRY_RUN 不拦重试（与计数器口径一致，注释 M-2）。
- **崩溃恢复**：无对账工具；依赖重跑+策略兜底（AUD-015）。
- **❗ AUD-014（F1-4 未修）**：`archive_planner.py:96-98` docstring 仍写"Each photo is planned at most once … first APPROVED match … 1:N Top-1 strategy fixed in 裁决 #5"，而同函数 :104-110 代码按 `(person, photo)` 对去重、跨 person 多归属各自成项（E-SG-6）。**文档字符串与自身代码直接矛盾**；另两载体未清：`plugin-context-design.md:211`（把废弃规则列为插件不可篡改业务不变量）、`face-recognition-pipeline-and-archive.md:250`。代码行为正确（测试佐证），错在文档。
- **❗ AUD-015**：`archive_executor.py:68-72` —— 整批单 UoW 事务包裹全部 item 的 DB 写，但 `shutil.copy2` 文件复制不可事务化。若批中途发生未捕获异常（非 OSError 的 DB 错误/进程崩溃），已复制文件无任何 DB 记录（全批回滚）→ 重跑时 skip 策略把这些文件误标 SKIPPED（记录显示"曾归档"但行是本次新建）、rename 策略产生 `.archived-1` 副本。**无崩溃对账路径**。触发条件：批中 DB 异常/断电/进程被杀。影响：归档目录与库状态分歧、计数失真。属设计权衡（DB 原子性优先）但未见文档声明该取舍。

### 2B 审核链（深查）

`ReviewDialog（身份选择器+二次确认）→ ReviewController（同步调用，<10ms 理由在案）→ ReviewRecognitionUseCase → ReviewRecognitionService`。

- 状态机：PENDING→APPROVED/REJECTED 终态，实体 `_assert_pending` 禁止重开（`recognition.py:64-75`）；服务层对缺失/已终态行**静默跳过**（`:134-140`），bulk 返回实际迁移数 → 重复审批幂等。
- UoW 包裹持久化（ISSUE-005 注释），find→update 间隙并发删除处理（affected==0 回滚）。
- 只读旁路：Controller 直接持 RecognitionRepository.list_pending（`review_controller.py:7-9` 注释声明读写分离理由）——记录在案，无发现。

### 2C 配对链（深查）

`PairingWorkbenchDialog → PairingWorkbenchService.confirm/manual_assign/reject/unassign/set_cluster_state → ClusterAssignment 状态机 + _sink_confirmation`。

- 状态机：suggested→confirmed/rejected；unassign 可自 suggested/confirmed/rejected 三入口（撤销语义完整，`:151-181`）；受影响行数校验防并发删除（`:123-126`）。
- `_sink_confirmation`（`:276-321`）：D4 样本沉淀按 observation_id 去重（幂等，跳过已沉淀对）；D3 兼容写 recognition_results APPROVED，(person, photo) 单活跃约束、跨 person 不互覆（E-P1-1）；BLK-5 三态置信度在此落地。
- 观测读取 `observations[member.observation_id]` 直接下标（`:290-295`）——member 引用不存在观测时将 KeyError；前置过滤 `if member.observation_id in observations` 已防护（同一表达式内）。✓

### 2D 识别运行链（深查）

`RecognitionScopeDialog（重试/范围）→ RecognitionRunController → RunRecognitionService → Detector/Matcher 端口 → RecognitionRun + Observations 持久化`。

- **显式状态机**（`domain/entities/recognition_run.py:43-44`）：`created→running→{completed|failed|cancelled}`，终态封闭，非法转换由实体校验拦截。
- 逐照片异常隔离：`_consume_result` 异常计 error_count=1 不中断批（`:104-110`）。
- 取消：batch-level 协作式（LIMIT-002 在案）；**取消→部分观测持久化+run 标 cancelled**；重试 = 新建 run 只覆盖 `输入照片−已产出观测`（`recognition_failure_service` retryable 语义，`test_stage_f_services.py:207,268`）。
- 重跑不覆盖人工决定：`test_freeze_blockers.py:343`（rerun_does_not_overwrite_manual_approval）。
- 千级确定性回归：`test_stage_f_lifecycle.py`（1200 张全量/中途取消/取消后重试/反复取消重试/坏图不崩溃，5 项）。

### 2E 扫描链（深查）

`ScanController（主线程预枚举 ADR-041）→ ScanAndRegisterPhotosService.execute → per-folder 预取 existing（N+1 防护，`:115-119`）→ 已存在走 `_update_if_changed`（content_hash 可比则比 hash，否则 mtime；重读失败保留旧元数据 = fail-safe，`:182-215`）→ 新照片注册`。

- 重扫幂等：路径键 + 内容对账（reconcile 更新元数据，`test_reconcile_scan_updates_metadata.py`）；未变更项跳过。
- 取消一致性：任务边界粒度（LIMIT-002 同型），专项 `test_scan_cancel_consistency.py`、`test_scan_single_flight.py`（防重入）。

### 2F 导入链（深查）

`选文件 → ParseImportDraftService（编码阶梯/表头映射/拆分建议/冲突分类）→ ImportPreviewDialog → ConfirmImportService`。

- **单事务**确认；行级错误隔离带行号；**TOCTOU 二次查重降级为合并**（绝不硬失败，`confirm_import_service.py:10-11,84`）；草稿保留可回溯，取消不写正式人员。
- 历史回填幂等：首跑建批次、重跑 noop、不动既有决定（`test_stage_f_services.py:83-138`）。

### 2G 导出链（抽查）

`ExportDialog → ExportController → ExportService._gather_data（scope 分派）→ Exporter 端口 → infrastructure/exporters（_atomic_write/_spreadsheet_safety）`。

- `CURRENT_BATCH` 为**诚实 fail-closed 延迟项**：请求即 raise ValueError 并说明契约出处（`export_service.py:122-127`），UI 已移除该选项（Batch 6）——非假完成。
- 取消检查点：`workers/export_task.py:51,56`（阶段间 raise_if_cancelled）。

### 2H 删除/清理/重复处置链（抽查）

三个服务同构：**preview（无副作用）→ execute（重新校验后仍满足条件才动手，TOCTOU 守卫）→ AUDIT 结构化日志**。Delete person：幂等（缺失 id 计入 missing 不抛错，`:6`）、级联（FK SET NULL + embedding cascade 计数）；Prune missing：execute 时重验 still_missing（`:93-95`）；Dispose duplicates：对仓储报告做契约校验（违反即 raise，`:77`）。✓ 均无发现。

### 2I 插件/设置链（结构级）

插件宿主：importlib spec 装载 + 签名探测向后兼容 + 静默失败告警 + 错误累积（`plugins/loader.py`）；插件上下文为应用服务薄映射（search/duplicates/import_people 经 ADR-028 写路径），**无仓储直触**。信任边界（任意外部 .py 装载 = 任意代码执行，同权限运行）→ Stage 6 安全项。

## 3. 状态机审计汇总

| 状态机 | 状态集 | 终态 | 非法转换防护 | UI/DB 一致性 |
|---|---|---|---|---|
| RecognitionResult | pending/approved/rejected | approved, rejected | 实体断言 + 服务跳过；重开路径不存在 | 审核对话框关闭后窗口刷新（Batch 5 在案） |
| RecognitionRun | created/running/completed/failed/cancelled | 后三者 | 显式转换表 + 实体校验（recognition_run.py:43-44,107） | 取消持久部分观测；终态刷新（test_task_terminal_refresh） |
| ClusterAssignment | suggested/confirmed/rejected/unassigned | unassign 可逆三入口 | update 受影响行数校验 | 配对工作台同步（E-SG-6 兼容层 f6e70b0） |
| ArchiveRecord | planned→archived/skipped/renamed/overwritten/failed/dry_run | 除 planned/failed 外拦重试 | upsert 幂等 | 计数器与 planner 同口径（BLK-1 后） |
| ImportBatch 行 | create/merge/skip 决策 | 确认后草稿保留 | TOCTOU 降级合并 | 导入预览四区 + 计数 |

**未发现**：非法转换通路、终态复开、重放重复副作用（各链幂等机制如上）。取消语义与状态一致（取消不产生"完成"态）。

## 4. 幂等性矩阵

| 操作 | 重复执行行为 | 机制 | 判定 |
|---|---|---|---|
| 重复导入确认 | 重复行合并/跳过 | TOCTOU 降级 + 单事务 | ✅ 设计保证 |
| 重复扫描 | 已存在对账/跳过 | 路径键 + content_hash/mtime | ✅ |
| 重复识别 run | 新 run，不覆盖人工决定 | run 追加 + 人工决定保护测试 | ✅ |
| 重复配对确认 | 样本去重、(person,photo) 单活跃 | observation_id 去重 | ✅ |
| 重复归档 | 成功态抑制 | (person, photo) 身份去重 | ✅（BLK-1 后） |
| 重复 migration | 幂等 | alembic 版本表 + 008 列探测 | ✅（Stage 3 再全链核） |
| 重复审批/删除/清理 | 跳过/计入 missing | 静默幂等 + 审计日志 | ✅ |
| 重复归档批执行（崩溃后） | **可产生重复副本/误标** | 无对账 | ⚠️ AUD-015 |

## 5. 本阶段 Findings

- **AUD-014（P2）**：F1-4 未修复——archive_planner docstring 与自身代码矛盾 + 2 文档载体（§2A 证据）。
- **AUD-015（P2）**：归档批 FS/DB 部分失败不一致，无崩溃对账（§2A；触发条件/影响已列）。
- **AUD-016（P3）**：`ArchivePhotosCommand.conflict_strategy` 自由字符串，命令层无校验；非法非 None 值在执行器静默落入"复制但标 archived"分支（Settings 层校验不覆盖此入口）。UI/CLI 当前值域安全，程序化调用方可触达。
- AUD-004 状态更新：BLK-1/BLK-5/D-1/D-2 → **代码侧 VERIFIED**；F1-1 部分缓解（应用层链测试在，全链贯通回归仍缺）；F1-2 代码侧落地、证据侧缺失（Stage 5）；F1-4 未修（→AUD-014）。

## 6. 未深查清单（诚实声明）

以下链为结构/标记级覆盖，未做逐行行为追踪（如需可立 Stage 2 续）：
`search_photos_service`（SQL 下推契约）、`detect_duplicates_service`（分组算法）、缩略图生成/缓存清理、`settings_service`、`backfill_capture_time/content_hash`、`export_service._gather_*` 全分支、`match_persons_service` 线程分片细节（并发归属 Stage 6）。全仓**无 N/A 业务功能**——任务书清单 16 项功能全部存在真实实现与入口。
