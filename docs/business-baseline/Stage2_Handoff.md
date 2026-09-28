# Stage 2 → Stage 3 交接摘要

> 基线：HEAD `2823d1c`（2026-09-28，`fix: resolve business baseline freeze blockers`）。完整证据与规则逐条编号见 `Stage2_BusinessRules.md`。
> **基线收口（2026-09-28）**：原基于 `b3b8685`；`2823d1c` 落地 Stage 4 BLK-1/BLK-5 修复与 D-1/D-2 裁决后，本文件 §1.7（阈值边界）、§7-1（原未裁决项）、§7-9（身份补写路径）已按当前实现对齐。行号引用以 `Stage2_BusinessRules.md` 修订版为准。
> 本文件只保留 Stage 3 建模/画图必需的最小事实集。全部结论已由当前仓库源码复核。

---

## 1. 核心业务规则（画流程图时不可违背）

1. **导入两段式**：解析选文件即落草稿（`import_batches` draft + `import_draft_rows`）；**确认是唯一写 `people` 的路径**；确认按草稿 `order_index` 逐行、从全局 `MAX(roster_order)+1` 续号写入。取消零写人员。（RO-01/03/05）
2. **名单顺序参与业务**：`roster_order` 决定 ①名单展示序 ②照片筛选人员轴序 ③**配对规则③的人员顺序轴**。重新导入并合并会更写既有人员的 `roster_order` 到新批次位置（RO-04）。
3. **识别对手片四分支**：不可读→unreadable+1；检测异常→error+1；0脸→no_face+1；N脸→**N 条 FaceObservation**。前三者都不建观测。（RE-01~04）
4. **范围判定是照片级**：命中任一选中人脸数范围 → in_selected_scope；同照片全部观测共享；范围外照片仍落观测但不写兼容行。默认范围 [1][2-3][4-5][6-10][11+] 全勾选。（RE-05/06）
5. **兼容行 PENDING**：in_scope 且该照片**历史无任何** `recognition_results` 行时，才用最高置信度脸写 1 条 PENDING（person 常 NULL，因为匹配候选表 `person_embeddings` 生产无写者）。（RE-07~09）
6. **聚类输入** = 指定 recognition run 内 in_selected_scope 且嵌入非空的观测；两段式算法（簇心贪心 **≥0.5** → 完全链接合并 **≥0.4 含等号**）；低质量（默认禁用）不驱动合并。（CL-03/05/06/07）
7. **配对三条自动规则**：①样本匹配 max 余弦 **>= 0.40**（恰等于 0.40 命中，Stage 4 D-2 裁决）→ sample_match；②跳过 rejected 对；③剩余 簇(sort_key) × 人(roster_order) 一对一 → ordered_suggestion。**建议恒为 suggested，从不自动确认**。（PR-02/03/04/11）
8. **确认三连写**：人工确认/指派一条 assignment 时同事写 `person_face_embeddings` 样本 + `recognition_results` APPROVED 兼容行（每 (person,photo) 至多一条当前有效）。（PR-12）
9. **解除/改派三连回收**：旧行 →unassigned + 删旧 person 的 APPROVED 行 + 停样本(enabled=0)。（PR-14/15）
10. **rerun 恒新增**：识别新 run、聚类新代际；旧 run/观测/簇/指派一律保留，不覆盖。（RR-01~05）
11. **归档只消费 `recognition_results` APPROVED**：+ `people.name` + `photos` + `archive_records` 去重（成功 4 态按 (person,photo)）；观测/簇/指派表不参与。未确认/未配对数据不会进归档计划。（AR-02/03/05）

---

## 2. 核心状态（作图的状态节点）

| 对象 | 状态值 | 说明 |
|---|---|---|
| import_batches | draft → **confirmed**；cancelled 定义未使用 | 无清理 |
| recognition_runs | created → running → **completed / failed / cancelled** | 终态不可回退 |
| face_cluster_runs | 同上五态 | 代际容器 |
| face_clusters | 实写 **pending / unknown / ignored**；confirmed / split / merged 仅定义未使用 | 确认配对 **不改** 簇状态 |
| cluster_person_assignments | suggested → **confirmed** / rejected；confirmed·rejected → unassigned | 当前有效 = suggested+confirmed；同簇历史多行 |
| recognition_results | pending → approved / rejected | 配对写入的 APPROVED 绕过实体状态机（直接构造） |

## 3. 核心分支（画图必备）

- 导入确认时的行动作三分支：`create / merge_existing / skip`（identity 冲突自动降级为 merge）。
- 识别每照片后置分支：unreadable / error / 0-face / N-face → N-face 再分 in-scope / out-of-scope。
- 兼容行守卫：照片已有任何历史行 → 跳过写入（不重写、不更新）。
- 聚类参与过滤：in_selected_scope 且 embedding 非空；`excluded_count`。
- 建议排除：有有效指派的簇、已确认人员、rejected 对（三者均按**代际** cluster_run 作用域）。
- 数量三分支：组=人 / 组<人 / 组>人（前两者之后剩余方无任何持久化标记）。
- 归档计划跳过分支：相对路径、缺照片、(person,photo) 已成功归档、冲突策略（skip/overwrite/rename）。

## 4. 自动 / 人工边界

**自动**：解析→草稿；识别检测+观测落库+**PENDING 兼容行**；聚类+簇/成员落库；建议生成（suggested）；归档计划（preview 零副作用）。
**人工**：确认导入（名单落库唯一入口）；识别范围选择；配对确认/拒绝/改派/解除/标陌生/忽略（**确认是唯一产生 APPROVED + 样本的路径**）；审核中心对 PENDING 行通过/拒绝；归档执行确认（dry-run 默认勾选）；人员增删改排序。
**阈值全部固化**：聚类 0.5/0.4/0.0（UI 不可调）；样本匹配 0.40；识别匹配阈值默认 MATCH_THRESHOLD=0.40（`.env` 可配）。

## 5. 必须画进流程图的节点

1. 导入：文件选择 → Parse 草稿落库 → 预览/编辑（整批替换草稿行）→ 确认（UoW 写 people + 状态翻转在事务外）/取消保留草稿。
2. 识别：readiness 门 → 范围对话框（全部/选中/重试）→ 新 RecognitionRun + 三表快照 → 逐照片四分支 → 观测批量 flush（50/批）→ 兼容行条件写入 → 终态（complete/failed/cancelled，已 flush 观测保留）。
3. 聚类：选 run → 新 FaceClusterRun → 过滤参与观测 → 两段式算法 → 落簇+成员（§D-3 排序键）→ 终态。
4. 配对：选代际 → 生成建议（三规则，suggested）→ 人工六操作 → confirm/assign 三写（assignment+samples+APPROVED 兼容行）→ unassign/assign 三回收。
5. 归档：选区 → Planner（APPROVED×(person,photo) 去重、成功态拦截）→ 预览（dry-run 默认）→ Executor（UoW + PLANNED→终态 + copy2）。
6. rerun：恒新建行/代际（分叉不合并）。

## 6. IMPLEMENTED / PARTIAL / PLANNED 速览

- **IMPLEMENTED**：两段式导入、roster 管理（增删改排）、多脸观测、五计数、范围选择、失败清单/重试入口、两段式聚类、组排序、建议三规则、工作台六操作、样本沉淀、兼容投影、归档全链、历史回填。
- **PARTIAL**：① "时间缺失，顺序建议不可靠" 只显示"时间缺失"；② 取消导入后草稿保留但**无重新打开入口**（计划称"供继续编辑"）；③ 组<人/组>人时剩余方的"标记"仅现于瞬时 summary（无持久标记）；④ 不可读/无脸照片仅有计数+CSV 导出，照片库无语义筛选轴；⑤ 配对工作台无成员缩略图网格、无时间轴（仅组条目+首拍时间）。
- **PLANNED（不存在）**：簇合并/拆分服务与 UI；配对工作台内新增人员；样本库回流识别（计划 E-3）；阈值/质量公式校准裁决；`import_batches.cancelled` 的写入路径；`face_clusters` confirmed/split/merged 的写入路径。

## 7. Stage 3 必须注意的歧义

1. ~~**sample_match 阈值边界**~~ **已裁决（Stage 4 D-2）**：统一为 `score >= 0.40`，恰等于 0.40 **命中**——实现 / docstring / 测试三点一致（`pairing.py:92-120`，阈值判定 `:109-112`；`test_stage_e_pairing_domain.py` 三点边界用例），不再是未裁决矛盾。
2. **unknown/ignored 簇会继续收到新建议**（建议管道不过滤簇状态）——"忽略"的真实语义无规格背书。
3. **"rejected 对"只按代际生效**：换代际重跑建议时同一 (组,人) 可再次出现——代码如此，是否为业务意图未确认。
4. **APPROVED 双来源无法区分**：审核通过行与配对确认投影行字段完全相同（无 source 列）——图的"归档来源"只能统一画 `recognition_results.APPROVED`。
5. **人员删除**将物理删除其指派历史与样本（CASCADE），而非转 unassigned——画删除语义时勿画"未分配"。
6. **范围外照片有观测**但此后永不可被聚类/配对/归档（聚类只吃 in_selected_scope）。
7. **重新导入合并会重写 roster_order**（既有人员被移到新批次顺序位）——"顺序稳定"必按"按最新确认批次的行序"理解。
8. **people.source_batch_id 无 FK 约束**（软引用，003 未建 REFERENCES）。
9. 兼容行守卫使**删过人的照片**（person_id→NULL 行仍在）永远不再被识别自动重写兼容行——观测级 rerun 不受影响，身份补写可经配对工作台确认/改派，**或审核中心批准时指定人员（Stage 4 D-1）**。
