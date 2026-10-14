# S4B2 S-B Reference Data / Isolation — Owner Decisions（D-SB-1…D-SB-12 正式裁决登记）

- **登记日期**：2026-10-07（Owner 裁决原文落款日按会话时序为 2026-10-06/07 之交，以本文件登记日为准）
- **裁决载体**：Owner 会话内正式裁决（核心内容逐字引用于 §1）
- **设计前置**：`S-B-REFERENCE-ISOLATION-DESIGN = READY-FOR-OWNER-DECISION`（开发前架构审查报告，2026-10-06）
- **关联裁决**：`docs/decisions/S4B2-scoring-architecture-decisions.md`（D0–D7；其中 D2=建设 S-B、D5=工件必须、D6=DB+封存双层、D7=NO）；`docs/decisions/S4B2-owner-decisions.md`（八项基础裁决）；ADR-047（`person_embeddings` 恒空死读路径）
- **状态**：`S-B-REFERENCE-DESIGN = APPROVED`；`ACTUAL-CALIBRATION-EVALUATION = NO`

---

## 1. Owner 裁决原文（核心逐字）

### D-SB-1 — Reference Photo 来源 = **C 专门参考批次**

```text
独立 Reference Photo 目录
→ 独立扫描
→ 独立 recognition run
→ 独立 clustering run
→ 人工确认
→ person_face_embeddings
→ Reference Snapshot
```

底层隔离不变量 = `photo_id`；不是 observation_id / file path / filename / folder_id。

### D-SB-2 — Reference Minimum Count = **minimum 1，recommended 3–5**

| Reference 数量 | 处理 |
|---:|---|
| 0 | 不进入评分候选集，单独报告 coverage gap |
| 1 | 允许，标记 `single-reference` variance risk |
| 2–3 | 合法，达到基础可用区间 |
| 3–5 | 推荐目标 |
| 全部来自 EvalPhotoSet | fail-closed，禁止 |

特别冻结：**禁止为了凑齐 36 人，将 Evaluation Photo 作为 Reference。**

> **2026-10-07 修订**：本项已被 Scope Amendment 拆分为分阶段策略——D-SB-2A（S-B Pilot：minimum 1 / covered person，target 8–12，single-reference flag 必打；4–7 降级 MICRO-PILOT）+ D-SB-2B（S-B Certification：recommended 3–5 / person，POSTPONED 至 Coverage 足够）。见 `docs/decisions/S4B2-sb-reference-scope-amendment.md`；上表的 0/1/全来自 EvalPhotoSet 规则与"禁止凑数"冻结不变。

### D-SB-3 — Person Representation = **sb-member-max-cosine-v1**

```text
cluster member embedding × 该 Person 所有 enabled Reference Sample → max raw cosine
```

score = raw cosine，domain = [-1,1]，higher = better。禁止：`recognition_results.confidence`、`(cos+1)/2`、`det_score`、`quality_score`、`FaceClusterMember.confidence`。centroid / medoid / multi-prototype 不进入 S-B v1；未来研究必须用新 scorer_version 并重新 Owner 决策，不得混入 S-B v1 主认证链。

### D-SB-4 — Cluster Representation = **成员 embedding 直评，无 centroid**

评估对象直接使用 cluster → members → each member embedding → Person Reference Samples → max cosine。不做 cluster centroid / medoid / persistent cluster embedding。任何未来 centroid scorer：必须独立 scorer_version、独立统计解释、不得与 sb-member-max-cosine-v1 混算。

### D-SB-5 — Reference Snapshot = **必须存在**

评估开始前生成并封存。最低字段：

```text
snapshot_id
person_id
observation_id
photo_id
embedding_sha256
enabled
quality_score
provenance
snapshot_created_at
```

规则：只使用 snapshot；禁止正式评估期间实时读取 `person_face_embeddings`；快照必须 immutable / reproducible / hash-verifiable；样本变化 → 新 snapshot_id，不得修改旧 snapshot。

### D-SB-6 — Snapshot 存储 = **文件 + SHA256 必选；DB snapshot table 可选**

正式实施时优先遵循 D6（DB + immutable archive），即优先评估 DB Snapshot + Immutable Snapshot Archive；但 Schema 实施任务必须**先报告 migration 成本，再执行 Owner 已批准的最小方案**。

### D-SB-7 — Prediction Artifact 扩展字段 = **批准新增 reference_snapshot_id + reference_snapshot_sha256**

正式 Prediction Artifact 推荐字段（12）：

```text
dataset_id
dataset_version
cluster_id
top1_person_id
top1_score
top2_person_id
top2_score
scorer_version
computed_at
isolation_invariant_sha256
reference_snapshot_id
reference_snapshot_sha256
```

S-B → `reference_snapshot_*` 必填；S-A / S-C → NULL。**scorer_version + dataset_id/version + reference_snapshot 三者共同组成可复现实验身份。**

### D-SB-8 — Near-Duplicate 策略 = **content hash + Owner 独立性声明 + 人工确认检查点**

perceptual hash = NOT IMPLEMENTED，不在本轮 S-B 实施中强行加入。编辑后 near-duplicate = residual risk，必须 documented，不能声称已技术解决。Future backlog：perceptual hash 二级检测（若开发，另行标定，不与本轮规则混淆）。

### D-SB-9 — Schema Scope = **最小必要 Schema 变更**

允许：Prediction Artifact table + 必要的 Reference Snapshot table。**PFE provenance 专列暂不自动批准**——只有在开发前审查证明现有 `created_at + 触发业务行` 无法满足可审计 provenance 要求时，才能重新提交 Owner Decision。禁止为"设计更完整"顺手扩大 schema。

### D-SB-10 — Reference Quality Gate = **OPEN PARAMETER**

暂不冻结 det_score / quality_score 数值下限；S-B v1 先不加入未经标定的质量阈值。未来若设置，必须重新提供统计依据、误差影响、覆盖率影响、Owner Decision，不得凭经验写死。

### D-SB-11 — Implementation Split = **S-B-1 → S-B-6 按序**

```text
S-B-1 Reference Photo Intake → S-B-2 Photo Isolation Guard → S-B-3 Reference Eligibility
→ S-B-4 Reference Snapshot → S-B-5 Prediction Artifact → S-B-6 Isolation / Leakage Acceptance Tests
```

允许 S-B-2 / S-B-3 的纯测试先行，但不得绕过 S-B-1 的数据来源约束构造生产 Reference。

### D-SB-12 — Actual Evaluation = **继续保持 D7 = NO**

S-B architecture approval ≠ Evaluation authorization。S-B implementation = NOT STARTED；Calibration Evaluation = NOT STARTED。

## 2. 永久硬约束（立即进入 S-B 实施基线，14 条逐字）

```text
1. photo_id 是唯一主隔离不变量
2. observation_id 不能单独用于隔离
3. file path / filename 不能作为隔离判据
4. EvalPhotoSet ∩ ReferencePhotoSet = ∅
5. same-cluster leakage = fail-closed
6. cross-run 必须 photo_id 去重
7. Reference Snapshot 必须冻结
8. enabled 状态必须按 snapshot 冻结
9. embedding 必须可 hash 验证
10. scorer 使用 raw cosine
11. recognition_results 永不作为正式 prediction artifact 来源
12. Calibration score ≠ Production Auto-confirm threshold
13. S-A ≠ S-B
14. S-B 未完成前不得进入认证级 Evaluation
```

## 3. 登记矩阵

| Decision | Owner Decision |
|---|---|
| Reference Photo 来源 | **C — 专门参考批次** |
| Reference minimum | **1** |
| Recommended reference count | **3–5** |
| Representation | **sb-member-max-cosine-v1** |
| Cluster Representation | **成员 embedding 直评（无 centroid）** |
| Reference Snapshot | **必须** |
| Snapshot 存储 | **文件 + SHA256 必选；DB 表可选（实施时先报 migration 成本）** |
| Prediction Artifact extension | **增加 reference_snapshot_id + reference_snapshot_sha256** |
| Near-duplicate | **content hash + Owner 声明 + 人工检查；pHash backlog** |
| Schema | **最小必要 migration；Artifact 必须，Snapshot 按实施设计确定** |
| PFE provenance 专列 | **暂不冻结** |
| Reference quality threshold | **暂不设置，OPEN PARAMETER** |
| Implementation split | **S-B-1 → S-B-6** |
| Actual Calibration Evaluation | **NO** |

## 4. 一致性注记（登记时核对）

- D-SB-7 是对 Scoring Gate **D5** 已批准字段集的正式扩展（D5 明言"必须能够区分三种 scorer"，本扩展把参考侧钉死）。
- D-SB-6 是 Scoring Gate **D6=C** 在快照侧的操作化，且附加了"先报 migration 成本再实施"的程序性约束。
- D-SB-3/D-SB-4 与 Scoring Gate **D1**（S-A 独立、LOO、in-sample-only）共同维持 S-A ≠ S-B 边界。
- D-SB-12 与 Scoring Gate **D7 = NO** 完全一致：架构批准 ≠ 评估授权。
- 状态链：Frozen Baseline PASS → Scoring Architecture DECIDED → **S-B Reference Design APPROVED** → S-B Implementation NEXT（须独立任务书）→ Independent Evaluation FUTURE。

## 5. 下一阶段授权边界

下一阶段只能进入 **S-B-1 Reference Photo Intake**，且必须拥有独立开发任务书（执行角色：开发 AI），至少明确：Owner 提供 Reference Photos、输入目录、导入/扫描规则、run 隔离、cluster 隔离、人工确认路径、PFE 写入边界、事务边界、验收测试。

在对应开发任务书下发前，禁止自动执行：导入新照片、创建 PFE、运行 recognition/clustering、确认人物、生成 snapshot、创建 prediction artifact、运行 S-B scorer、计算 Precision/Recall、搜索 threshold。

## 6. 可逆性

- D-SB-10（质量门槛 OPEN PARAMETER）与 D-SB-8（pHash backlog）显式保留未来再裁决空间。
- D-SB-9 的 PFE provenance 专列为条件再议项（须开发前审查举证），非永久否决。
- D-SB-2 的数量策略、D-SB-6 的快照存储形态可随实施证据再裁决；14 条永久硬约束不在此列——修改任一条须新 Owner Gate。

---

**登记完成。`S-B-REFERENCE-DESIGN = APPROVED`；`ACTUAL-CALIBRATION-EVALUATION = NO`。**

*本文件为治理登记（untracked，未提交；提交与推送均属 Owner 操作）。*
