# Stage 1 → Stage 2 交接摘要

> HEAD `2823d1c`（2026-09-28，`fix: resolve business baseline freeze blockers`）。完整证据见 `Stage1_BusinessFacts.md`。
> **基线收口（2026-09-28）**：原基于 `b3b8685`；`2823d1c` 落地 Stage 4 BLK-1/BLK-5 修复与 D-1/D-2 裁决后，本文件已把受影响结论（§1.7 阈值边界、§1.10 身份来源）与当前实现对齐。行号引用以 `Stage1_BusinessFacts.md` 修订版为准。
> 本文件只保留 Stage 2 作图/建模必需的事实与风险点。

---

## 1. 已确认核心事实（可直接作为事实基础）

1. **导入是两段式**：解析即建草稿批次（`import_batches` draft + `import_draft_rows`），预览期每次编辑整批替换草稿行，**确认是唯一写 `people` 的入口**，并按全局 `MAX(roster_order)+1` 续号。取消只留草稿，不写人员。
2. **识别入口三选一**：全部 / 照片库选中 / 重试（上一终态 run 中"有输入无观测"的照片）。**已取消"仅未匹配照片"过滤**——每次都全量重检，旧结果不阻止新 run。
3. **识别是追加型**：新 `RecognitionRun` + 新 `FaceObservation`，旧 run/观测永不改写（`parameters` 列永不更新）。
4. **观测规则**：1 张照片 N 脸 = N 条观测（`face_index` 按置信度降序确定性）；**0 脸 / 不可读 / 检测异常都不建观测**，只计 `no_face_count` / `unreadable_count` / `error_count`；范围外照片**仍保存全部观测**，只是 `scope_verdict='out_of_selected_scope'`。
5. **兼容投影是全局枢纽**：每张在范围内且此前**从无** `recognition_results` 行的照片，会写入一条 PENDING 兼容行（用置信度最高的脸走 1:N Top-1）。任何历史行都会永久阻止重写。
6. **聚类输入 = 某 recognition run 的 in-scope 且有嵌入的观测**；算法两段式（簇心贪心 0.5 → 完全链接一致性 0.4 含等号）；产出新代际 `FaceClusterRun` + 簇 + 成员，旧代际不动。**阈值 UI 不可调**。
7. **配对建议只写 `suggested`**：①已确认样本 max 余弦 **>= 0.40**（恰等于 0.40 命中，Stage 4 D-2 裁决）→ `sample_match`；②跳过 rejected 对；③剩余按（簇 sort_key × 人员 **roster_order**）一对一 → `ordered_suggestion`。**系统从不自动确认**。
8. **人工确认才生效**：确认/改派写 `person_face_embeddings` 样本 + 向 `recognition_results` 写 **APPROVED**；解除/改派会 DELETE 旧 person 的 APPROVED 行并把样本 `enabled=0`。
9. **归档只读 `recognition_results` APPROVED**（+ `people.name` + `photos` + `archive_records` 去重），去重作用域 `(person_id, photo_id)` → 一图可入多人目录。**完全不读观测/簇/指派表**。
10. **`person_embeddings` 读活写死**：无生产者 → 生产环境中匹配候选集恒空 → 新识别兼容行 `person_id` 恒 NULL，**自动识别本身尚未建立最终人员身份**；最终身份由人工动作写入——配对工作台确认/改派，**或审核中心批准时指定人员（Stage 4 D-1）**。

---

## 2. 核心对象及关系

```
import_batches ──1:N── import_draft_rows ──(merge_target_id)──► people
people ──(source_batch_id, 软引用)──► import_batches
people ──roster_order──────────────────────────────► 配对规则③ 的人员顺序轴

photos ──1:N── recognition_results ──APPROVED──► ArchivePlanner ──► archive_records
people ──SET NULL──► recognition_results          （删人员 → 归属变"未知"）

recognition_runs ──1:N── recognition_run_photos（输入快照）
             ──1:N── recognition_run_scopes（写入后无人读）
             ──1:N── face_observations ──1:N── face_cluster_members ──N:1── face_clusters
                          │                                              │
                          └──1:N── person_face_embeddings ◄──确认时沉淀──┤
                                                                         │
face_cluster_runs ──1:N── face_clusters ──1:N── cluster_person_assignments
                                                     │
                                      confirmed（人工）─┴─► 写 APPROVED 兼容行 + 样本
```

**必须记住的双写点**：配对确认同时写 3 处（assignment / samples / 兼容行）；改派同时改 3 处（旧行 unassigned / 删旧 APPROVED + 停用旧样本 / 新行 confirmed + 新投影）。

---

## 3. 关键状态

| 状态机 | 值 | 备注 |
|---|---|---|
| `recognition_runs` / `face_cluster_runs` | `created → running → completed \| failed \| cancelled` | 终态不可回退 |
| `recognition_results` | `pending → approved \| rejected` | 配对写入的 APPROVED **绕过**实体状态机 |
| `cluster_person_assignments` | `suggested → confirmed \| rejected \| unassigned`；`confirmed/rejected → unassigned`；`unassigned` 终态 | 当前有效 = suggested+confirmed |
| `face_clusters` | 实写：`pending`（创建）、`unknown`/`ignored`（工作台）；**`confirmed`/`split`/`merged` 从未写入** | 无簇合并/拆分能力 |
| `import_batches` | `draft → confirmed`；**`cancelled` 从未写入** | |
| `archive_records` | `planned → dry_run \| archived \| skipped \| renamed \| overwritten \| failed` | 前四个成功态阻止重复归档 |

---

## 4. 关键异常

- 不可读 / 检测异常 / 无脸 → 均**不建观测**，分别计数；单张失败不中断批次。
- 照片在范围内但已有任意兼容行 → 兼容写入静默跳过（重跑不会修正旧结论）。
- 取消/失败 → 已 flush 的观测**保留**（50 条一批）。
- 取消/中止 → 不删除任何旧 run/旧簇（重跑 = 新代际）。
- 确认非 `suggested` 指派、cluster/person 不存在 → `ValidationError`。
- 归档：路径冲突默认 `skip`；相对路径照片 skip；已成功 `(person, photo)` skip；单 item 失败隔离。
- **删除人员 = CASCADE 物理删除**其 `cluster_person_assignments` 决策历史 + `person_face_embeddings`（**不**转 unassigned、**不**停用），`recognition_results.person_id` 置 NULL。

---

## 5. 自动 / 人工边界

| 自动（无人工确认即落库） | 必须人工 |
|---|---|
| 解析 → 草稿批次与草稿行 | **确认导入**（唯一写 `people` 的草稿路径） |
| 识别检测 + 观测落库 | 识别范围选择（全部/选中/重试 + 人脸数范围） |
| **兼容行 PENDING 写入**（进入审核队列） | 审核通过 / 拒绝 |
| 聚类 + 簇/成员落库 | **配对确认/拒绝/改派/解除/标陌生/忽略** |
| 配对建议（仅 `suggested`） | 人员增删改与排序 |
| 归档计划（preview 零副作用） | **归档执行**（dry-run 默认勾选） |

阈值全部固化：聚类 0.5 / 0.4 / 0.0（低质量门禁用）、样本匹配 0.40；UI 无调整入口。

---

## 6. 已确认 / 未确认

**已确认（代码证据充分）**：§1 十条 + §2–§5 全部；`roster_order` 的 6 处真实用途；观测的三类不落库分支；兼容行的存在性守卫；归档的唯一输入；rerun 的追加语义。

**未确认（Stage 2 不应假定）**：
1. ~~全量 pytest 是否通过~~ **已由 Stage 4.1 复审实跑复现：1310 passed / 6 skipped**（2026-09-28）。
2. 真实生产库中 `person_embeddings` 是否为空、`recognition_results.person_id` 非空比例。
3. 生产数据中 `face_clusters.status` 与 `cluster_person_assignments` 的实际使用程度。
4. 真实库中是否出现过 `parameters["photo_scope"]=="retry"`（代码推论为不可能）。
5. 聚类阈值/质量公式的最终裁决（Owner 缩略图复核未做）。
6. E-SG-4「合格样本」定义、E-SG-5「样本恢复语义」（报告自陈 Spec Gap）。
7. `people.source_batch_id` 无 FK 约束是否有意为之（迁移 003 未加 REFERENCES）。

---

## 7. Stage 2 必须重点复核的问题

1. **兼容层是"投影"还是"事实源"？** 归档、审核、筛选、徽标、就绪、导出全部只认 `recognition_results`；观测/簇/指派不参与。作图时若把新链路画成归档输入即为事实错误。请核对 `archive_planner.py:17-23` 与 `:116`。
2. **删人员丢指派历史**（FK CASCADE vs 计划 B-2 的"置 unassigned"）——会影响"人员删除后映射状态迁移"的图与文档（`test_stage_e_remediation.py:297` 的 A→B→C 链未覆盖人员删除路径）。
3. **E-3 未实现造成的新旧割裂**：`person_face_embeddings` 只进建议生成、不回识别；新 run 的 `person_id` 恒 NULL。核对 `run_recognition_service.py:66` 与 `suggest_pairings_service.py:110`。
4. **重试标签丢失**：`scope_label` 无调用者，重试运行参数记为 `selected`（`main_window.py:1451-1454`）。
5. **簇状态六态 vs 三态实写**，以及无 `MergeClustersService`/`SplitClusterService`——不要把"合并/拆分簇"画成已实现能力。
6. **`recognition_run_scopes` 写活读死**、`ImportBatch.cancelled` 定义未用、`face_clusters.confirmed` 定义未用——作图时勿据此推断功能存在。
7. **文档时效**：执行计划 C-1/D-1 的 schema 草案、PROJECT_STATUS §7 的迁移链（缺 004–007）、Stage F 校准报告 §5 的范围声明均已过期；**以代码与 `alembic/versions/` 为准**。
8. **导入确认的事务边界**：`people` 写入在 UoW 内，批次状态 `confirmed` 在 UoW 外——如需精确画"原子性"边界须注意。
