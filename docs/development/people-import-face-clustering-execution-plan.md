# 人员名单导入与人脸分组匹配 — 分阶段开发执行计划

> 依据：`docs/development/people-import-face-clustering-development-plan.md`（owner 业务方案）。
> 本文件是该方案的**工程执行计划**：把每个阶段拆到 schema、分层改动、兼容联动、测试与验收，
> 供 owner 审核后逐阶段开发。**审核通过前不写任何代码。**
> 工程基线：`f7cfe72`（2026-09-20），迁移下一号 `003`，全量 pytest 1049 passed。

---

## 0. 跨阶段工程约定（每阶段都适用）

1. **迁移纪律**：每阶段独立 Alembic migration（`003` 起，阶段内可拆多支但一次评审）；
   `upgrade()` 与 `downgrade()` 都必须实现并在测试中验证升级/回滚；外键开启（现状 `PRAGMA foreign_keys=ON`）。
2. **分层不变**：Presentation → Application → Domain ← Infrastructure；UI 零仓储访问；长任务（批量导入确认、全脸检测、聚类、重分析）一律 Worker + Qt signal，经 TaskCoordinator 互斥。
3. **兼容红线**：`recognition_results`/`people`/`photos`/`archive_records` 既有消费方（审核对话框、归档 Planner、导出、工作区就绪、删除级联）每阶段保持全绿；迁移升级既有库不丢数据。
4. **质量门**：每阶段提交前 Ruff + MyPy + 全量 pytest（当前 1049 passed 基线只增不减）；定向新测试按 §测试计划。
5. **文案与样式**：新增 UI 文案全入 `ui_text.py`；视觉走 `visual_style` 既有体系（primary/danger 角色）。
6. **文档触碰**：每阶段收尾更新 `PROJECT_STATUS.md`；影响用户可见行为的阶段同步 `docs/user-guide/manual.md`。

### 需 owner 拍板的决策点（阻塞对应阶段）

| # | 决策 | 建议 | 阻塞 |
|---|---|---|---|
| D1 | `.xls`（老二进制格式）支持 | 方案 §4.1 要求支持；需新增 `xlrd` 依赖（requirements 审批）。**建议：批准新增 `xlrd==2.0.1`，放入阶段 A**；若不接受新依赖则明确不支持 .xls 并从选择器移除 | A |
| D2 | 编码探测实现 | `charset-normalizer` 已在 lock.txt（传递依赖），提升为直接依赖最省事；或自实现 BOM + UTF-8/UTF-16/GB18030 试解码阶梯（零依赖、可控）。**建议：自实现阶梯（约 60 行），不新增直接依赖** | A |
| D3 | 兼容层写入语义 | 确认组—人员映射后，适配服务向 `recognition_results` 写入什么？**建议：写 `APPROVED`（含 person_id、来源标记），确认即可归档**；审核对话框继续消费历史 PENDING 数据 | E |
| D4 | 后续 1:N 匹配策略 v1 | **建议：多样本取最大余弦，≥阈值（沿用 0.40，F 阶段校准）即候选**；中心特征留作 F 阶段选项 | E |
| D5 | 新页面导航位置 | "人员名单管理"与"分组配对工作台"进入主窗口导航（现 5 项）。**建议：导航改为 6 项（概览/照片库/**人员与分组**/审核中心/数据工具/设置），人员管理与配对工作台合并为一个页面容器**，避免 Batch 3 IA 膨胀 | B（首次涉及 UI） |
| D6 | 新任务类型注册 | `import_confirm`（大批量确认写入）、`face_analysis`（全脸检测/重分析）、`face_clustering` 进入 TASK_LABELS 与互斥集合；**建议：导入确认 ≤500 行保持同步，超出走 Worker** | C |

---

## 阶段 A — 导入草稿与稳定名单顺序

**规模：XL（预计 3–4 个提交）｜前置：D1、D2**

### A-1 Schema（迁移 `003_import_batches_and_roster`）

```text
import_batches:   id PK, file_name, file_hash, source_type(xlsx/csv/txt/xls),
                  encoding, delimiter, has_header, sheet_name,
                  status(draft|confirmed|cancelled), created_at, confirmed_at
import_draft_rows: id PK, batch_id FK->import_batches, source_row,
                   raw_values(JSON), parsed_name/parsed_identity/parsed_department/
                   parsed_note/parsed_group, warnings(JSON 数组),
                   action(create|merge_existing|skip), merge_target_id FK->people 可空,
                   order_index（批次内草稿顺序）
people:            ADD roster_order INTEGER（确认时按草稿顺序写入，唯一性不强制，
                   允许并列）; ADD source_batch_id FK->import_batches 可空
索引：import_draft_rows(batch_id)、people(roster_order)
```

### A-2 分层改动

| 层 | 内容 |
|---|---|
| Domain | `Person` 实体增 `roster_order/source_batch_id` 可空字段（向后兼容默认 None）；新增 `ImportBatch`/`ImportDraftRow` 实体与 `ImportBatchRepository` Protocol |
| Application | 新 `ParseImportDraftService`（解析→草稿，含编码阶梯 D2、分隔符探测、字段映射、多人分隔符拆分建议、组标题告警"N组/第N组/名单"、强/弱重复检测）；新 `ConfirmImportService`（单事务写 people + roster_order + 批次状态）；Command/DTO：`ParseImportDraftCommand/ImportDraftDTO/DraftRowAction` |
| Infrastructure | Reader 重构：现 `DispatchingPersonImportReader` 保留为旧直通路径；新增 `DraftPersonImportReader` 输出草稿行（.xlsx/.xlsm openpyxl、.csv/.tsv/.txt 文本、.xls 视 D1）；`SQLiteImportBatchRepository`；迁移 `003` |
| Workers | `ConfirmImportTask`（行数 > 500 时走 Worker，D6） |
| Presentation | 新 `ImportPreviewDialog`（模态）：原始内容/解析结果/告警/动作四区，字段映射下拉、拆分/合并/跳过编辑、将新增/合并/跳过计数、确认/取消（取消保留草稿）；MainWindow `_on_import_clicked` 改为两段式（选文件→预览→确认）；文案入 ui_text |

### A-3 兼容与联动

- 旧 `ImportPeopleService` 保留给插件 `import_people` 写路径（ADR-028），不删；UI 路径切换到预览流。
- 工作区就绪（persons 存在性）不受影响；`ListPersonsService` 增按 `roster_order` 排序输出。
- 现有人员无 roster_order：显示排在有顺序人员之后（不回填，F 阶段统一补齐）。

### A-4 测试（映射方案 §8）

- Reader：编码阶梯（UTF-8/BOM/UTF-16/GB18030 样本文件）、分隔符探测（`,`/`\t`/`;`）、无表头、多工作表、.xls（若 D1 批准）、空行、**顿号串联姓名拆分建议**、组标题告警、重复工号强冲突。
- 草稿：拆分/合并/跳过编辑、取消不写 people、确认原子性（中途失败回滚）、roster_order 与预览一致。
- 迁移：upgrade/downgrade 往返、既有库升级后人列为空 roster_order 仍可用。
- UI：预览对话框渲染四区、确认按钮经 TaskCoordinator、取消保留草稿。

### A-5 验收（方案 §7 阶段 A）

✅ 标准 Excel/CSV 导入结果不回归；✅ 顿号串联姓名在预览中拆为多人；✅ "2组"行默认告警可跳过；✅ 取消不写正式人员；✅ 确认后 roster_order 与预览一致。

---

## 阶段 B — 人员名单管理

**规模：M（1–2 个提交）｜前置：A、D5**

### B-1 改动

| 层 | 内容 |
|---|---|
| Application | 新 `ManagePeopleService`：新增/编辑（复用 Person 校验）/批量删除（复用 `DeletePersonService` 预览与级联语义）/调整顺序（拖拽 → 批量更新 roster_order，单事务）/按批次回看（ListImportBatches 查询） |
| Presentation | 新"人员与分组"页（D5）：人员表格（顺序、姓名、部门、来源批次、操作），拖拽排序，删除走既有确认对话框（danger + 默认取消）；导航 5→6 项；`_snap_nav_to_page` 等导航机制适配 |
| Infrastructure | `PersonRepository` 增 `update`/`reorder` 方法（SQLite 实现 + Protocol） |

### B-2 联动与风险

- 删除人员级联扩展：`delete_person_service` 现清理 `person_embeddings`——新增对 `cluster_person_assignments`/`person_face_embeddings` 的级联处置（置 unassigned/停用），该部分 schema 在 C/E 才出现，**B 阶段先留接口注释，C/E 落地时补全**（防遗忘：写入 PROJECT_STATUS Remaining）。
- 人员筛选下拉（FilterBar）与新页共享 `roster_order` 排序。

### B-3 测试与验收

- 新增/编辑/删除/排序的 Application 单测 + SQLite 集成测试；重启后顺序持久；删除后照片保留、历史归属转未分配（对既有 recognition_results 置空语义回归验证）。
- UI：导航切换、拖拽排序、批次回看。

---

## 阶段 C — 多脸检测与可重跑识别

**规模：L（2–3 个提交）｜前置：无硬前置（与 A/B 可并行评审）｜D6**

### C-1 Schema（迁移 `004_recognition_runs_and_observations`）

```text
recognition_runs:  id PK, algorithm_version, scope(all|selected|photos…),
                   status(running|completed|cancelled|failed), photo_count,
                   created_at, completed_at, parameters(JSON)
face_observations: id PK, run_id FK, photo_id FK, bbox(JSON),
                   det_score, quality_score, embedding(JSON 512),
                   captured_at_snapshot, created_at
索引：face_observations(run_id)、(photo_id)、(run_id, photo_id)
```

### C-2 分层改动

| 层 | 内容 |
|---|---|
| Domain | `FaceObservation`/`RecognitionRun` 实体 + 仓储 Protocol（`FaceObservationRepository`/`RecognitionRunRepository`） |
| Application | `MatchPersonsService` 改造：`_analyze_one` 产出**全部**人脸的观测（不再 Top-1 截断），逐脸 quality_score（检测分派生，公式 F 阶段校准）；新增 `ReanalyzeService`（范围：选中/全部；重跑不删旧 run，互不覆盖）；读取失败/无人脸/低质量分类计数（沿用 read_failed 机制并扩展） |
| Infrastructure | `SQLiteFaceObservationRepository`/`SQLiteRecognitionRunRepository`；迁移 `004` |
| Workers | `MatchPersonsTask` 改为创建 run → 逐张写观测 → 完成 run（进度/取消沿用）；新增"重新分析"入口任务复用同任务类型 |
| Presentation | 照片库多选/工具栏入口"重新分析选中/全部"；任务文案；照片详情对话框可列出该照片全部人脸观测（后续 D 阶段接缩略图） |

### C-3 兼容与联动（本阶段最敏感）

- **旧链路保留**：`recognition_results` 的写入与审核/归档消费**不变**——阶段 C 只**新增**观测数据，`_analyze_one` 在写观测的同时仍按旧逻辑产出一条 `RecognitionResult`（保持审核/归档/导出/就绪全绿）；Top-1→全脸的业务切换在 E 阶段配对工作台接管后才完成。
- `MatchPersonsController` 续跑门（"已有结果即跳过"）改为"重分析"显式入口语义；工作区就绪 `pending_match_count` 定义保持不变（基于 recognition_results），避免 UI 引导回退。
- TaskCoordinator：`match_persons` 任务承载新 run；D6 注册。

### C-4 测试与验收

- 多人合照（测试图像合成两张脸或真实样本）→ ≥2 条观测；中文路径/不可读取/无人脸/低质量分别计数（沿用 read_failed 并新增分类）；重跑产生新 run 不覆盖历史；取消/续跑；迁移往返。
- 性能护栏：473 张照片量级下观测写入分批 flush（沿用 ADR-037 分片模式）。

---

## 阶段 D — 人物聚类与时间排序

**规模：L（2–3 个提交）**

### D-1 Schema（迁移 `005_face_clusters`）

```text
face_clusters:        id PK, run_id FK, status(pending|confirmed|unknown|ignored|
                      split|merged), first_captured_at 可空, sort_key, created_at
face_cluster_members: id PK, cluster_id FK, observation_id FK, source(auto|manual),
                      confidence, created_at; UNIQUE(cluster_id, observation_id)
索引：face_clusters(run_id)、face_cluster_members(cluster_id)
```

### D-2 聚类算法（Application，确定性、可测试）

- 输入：同一 run 的全部观测嵌入；输出：组 + 成员关系。
- 两段式：①按余弦相似度 ≥ `cluster_sim_threshold`（默认 0.5，F 校准）贪心成候选簇；②**组内一致性约束**：仅当候选簇内两两最小相似度 ≥ `consistency_threshold`（默认 0.4）才合并，防止链式误合并（方案 §5.2）；低质量/边界分数观测只进候选不驱动合并。
- `algorithm_version` + 参数写进 run；重跑 = 新 run 新组，旧组不动。
- 人工合并/拆分组：`MergeClustersService`/`SplitClusterService`（成员关系与来源可追溯：source=manual，操作记录进 cluster 状态迁移）。

### D-3 排序（纯函数，可穷举测试）

```text
sort_key = (最早非空 captured_at, 最早照片 raw_path 稳定键, cluster_id)
无 captured_at 的组排最后；不得用注册时间替代；界面标"时间缺失，顺序建议不可靠"
```

### D-4 Presentation

配对工作台骨架（D 阶段先出组列表 + 缩略图网格 + 时间轴视图；建议/确认操作 E 阶段接入）：组卡片（首图缩略、成员数、时间、状态徽标），合并/拆分按钮（danger 语义评估：拆分/合并可逆，用 primary/secondary + 确认对话框）。

### D-5 测试与验收

- 聚类：同人跨照片同组、异人分离、链式误合并反例（A~B~C 相似但 A~C 不达一致性阈值 → 不并）、低质量边界、参数与版本入 run。
- 排序：最早时间升序、无时间排末、同时间按路径键稳定、确认后快照不回写（E 阶段联测）。
- 合并/拆分后成员、排序、审计正确；Worker 任务可取消。

---

## 阶段 E — 名单配对工作台与样本沉淀

**规模：XL（3–4 个提交）｜前置：A–D 全部｜D3、D4**

### E-1 Schema（迁移 `006_assignments_and_person_samples`）

```text
cluster_person_assignments: id PK, cluster_id FK, person_id FK,
                            status(suggested|confirmed|rejected|unassigned),
                            source(ordered_suggestion|manual|sample_match), score,
                            confirmed_at, sort_snapshot(JSON 排序快照)
person_face_embeddings:     id PK, person_id FK, observation_id FK,
                            embedding(JSON), quality_score, enabled, created_at;
                            UNIQUE(person_id, observation_id)
```

### E-2 建议生成与工作台（方案 §6 全表实现）

- `SuggestPairingsService`：①已确认样本高置信匹配优先；②排除 rejected；③剩余按（组 sort_key × roster_order）一对一生成 `suggested`；组数≠人数/无组/无名单/一人多组/多人一组的六种场景全部落界面（方案 §6 表格逐行）。
- 工作台操作：确认建议、替换人员、解除映射、多组关联同一人、合并/拆分组（复用 D）、新增人员、标记陌生人（cluster→unknown）、忽略组；组人脸缩略图网格 + 拍摄时间轴。
- 确认动作：写 `confirmed` + sort_snapshot → **适配服务**按 D3 生成/更新兼容 `recognition_results`（语义 = D3 决策）→ 从该组合格成员写 `person_face_embeddings`（替代旧单条覆盖式 `person_embeddings` 写路径——旧表保留只读，删除人员级联同步清理）。

### E-3 后续照片匹配切换

`MatchPersonsService` 匹配段改为：候选 = `person_face_embeddings`（启用态）多样本 max 余弦（D4）；≥阈值 → 新照片观测直接生成 `suggested` 映射（仍需确认）或按旧链路 PENDING（以 D3 决策为准）；低于阈值 → 进入分组审核队列。

### E-4 测试与验收

- 方案 §6 六场景逐行端到端；顺序建议永不自动写归属；确认后才生效且兼容层/样本库正确；新照片优先匹配已确认样本；低置信度进人工队列；人员删除/新增后的映射状态迁移；撤销（rejected→unassigned）。

---

## 阶段 F — 历史数据、性能与上线

**规模：M–L（2 个提交）**

- 历史人员补建导入批次（`source_batch_id` 回填 + roster_order 按既有创建顺序）——迁移或一次性脚本 + 失败清单。
- 历史照片"重新分析"入口 + 进度/失败报告（读取失败清单导出，联动现有导出体系）。
- 真实样本集（含本次验收的 473 张中文路径照片）校准 `match_threshold`/`cluster_sim_threshold`/`consistency_threshold`/质量分公式；结论写入 ADR 候选（若形成长期裁决，先请求 owner 批准）。
- 千级照片任务取消/重试/续跑压测；端到端回归（导入→确认→识别→聚类→配对→审核→归档）。
- 数据迁移完整性验证：升级既有库（含本次验收产生的 9 人脏数据）不丢人员/照片/归档/历史审核。

---

## 依赖关系与排期视图

```text
A（导入草稿）──► B（人员管理）──► E（配对工作台 + 样本沉淀）──► F（历史/性能/上线）
C（多脸检测 + 可重跑）──► D（聚类 + 时间排序）──┘
     └─ C 可与 A/B 并行；E 需要 A–D 全部就绪
```

| 阶段 | 规模 | 新迁移 | 主要风险 |
|---|---|---|---|
| A | XL | 003 | 预览编辑 UI 复杂度；旧导入路径回归 |
| B | M | —（003 已含） | 导航 IA 变更；删除级联接口预留 |
| C | L | 004 | 兼容层双写正确性；就绪语义不变 |
| D | L | 005 | 聚类质量与链式误合并 |
| E | XL | 006 | 六场景 UI 状态机；兼容层语义（D3） |
| F | M–L | （数据回填脚本） | 脏数据迁移；阈值校准 |

每阶段独立提交、独立验收；任一阶段验收不通过不进入下一阶段。
