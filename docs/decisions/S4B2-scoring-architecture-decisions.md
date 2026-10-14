# S4B2 Scoring Architecture — Owner Decisions（D0–D7 正式裁决登记）

- **登记日期**：2026-10-06
- **裁决载体**：Owner 会话内正式裁决（原文逐字引用于 §1）
- **决策门材料**：《S4B2 Scoring Architecture Owner Decision Gate》（基于 `SCORING-ARCHITECTURE-REVIEW = READY-FOR-OWNER-DECISION`）
- **前置证据**：Frozen Evaluation Baseline = PASS（71/71，`scripts/audit_s4b2_frozen_evaluation_baseline.py`）；Calibration Evaluation Protocol 草案已交付（**11 项统计裁决仍待 Owner 批准**，即 D4 重入条件 2）
- **关联裁决**：`docs/decisions/AUD-017-person-embeddings-decision.md`（ADR-047：`person_embeddings` 恒空死读路径）；`docs/decisions/S4B2-owner-decisions.md`（D-7/C-1/D-1/D-2/D-3/C-4/D-4/D-5 八项）

---

## 1. Owner 裁决原文（逐字）

```text
正式裁决 S4B2 Scoring Architecture Owner Decision Gate：

D0 = A
D1 = A
D2 = A
D3 = A
D4 = A
D5 = A
D6 = C
D7 = NO
```

具体含义冻结如下：

### D0 — Round-1 评分架构
批准 **A：S-C deterministic baseline + S-A member-level LOO in-sample calibration**。

明确：
- S-C = Round-1 确定性基线；
- S-A = 仅用于 in-sample calibration；
- 两者必须永久带架构标签，不得混称；
- 认证级身份性能评估仍处于 S-D，不因 D0=A 而解除。

### D1 — S-A
批准 **A**。

允许用途：
- 同人 / 异人原始 cosine 分布；
- 相似度量级标定；
- 阈值量级参考。

永久禁止：
- 独立身份性能认证；
- production-ready 宣称；
- 簇级 Precision / Recall；
- Auto-confirm 安全证明。

S-A 必须采用 **member-level Leave-One-Out**，不得使用会产生自包含偏差的簇级 GT centroid 直接评价。

### D2 — S-B
批准 **A：建设 S-B**。

S-B 为未来唯一合法的独立身份性能认证链。

建设方向固定为：
- 新增评估集之外的独立参考照片；
- photo_id 级隔离；
- 摄取期隔离守卫；
- 评估期 fail-closed 复验；
- enabled sample snapshot；
- versioned prediction artifact。

本决策仅批准"建设方向"，**不代表现在立即实施**。

### D3 — S-C
批准 **A：保留 S-C**。

S-C 定位：`deterministic baseline`。

允许产生：单点 Precision、单点 Recall、单点 False-Accept。

禁止：伪造 score；threshold search；margin；ROC/PR；将其描述为带分数身份模型。

S-C 评估必须只读重算，禁止写入 Assignment / cpa。

### D4 — S-D
批准 **A：接受延期，并绑定五项重入条件**。

只有以下全部满足后，才允许重新启动认证级 Calibration Evaluation：

1. S-B 独立参考数据与 photo_id 隔离链完成；
2. Calibration Evaluation Protocol 统计裁决完成；
3. Prediction Artifact 契约批准并实现；
4. D0–D6 Owner 决策全部完成；
5. Owner 单独发出 Evaluation Start 指令。

### D5 — Prediction Artifact
批准 **A：必须建立 versioned prediction artifact**。

最低字段：

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
```

其中 `top1_score / top2_score` 允许 NULL；NULL 表示没有 score evidence，不等于 0。

必须能够区分：S-C deterministic baseline；S-A in-sample calibration；未来 S-B independent scorer。

不得直接把 recognition_results 作为正式评估工件。

### D6 — Artifact Storage
批准 **C：DB + immutable archive 双层存储**。

DB 负责：查询；FK / UNIQUE 约束；正式测试；Dataset 关联。

封存文件负责：不可变归档；SHA256；审计复验。

实施时必须设计 export → hash → seal 的一致性步骤。

### D7 — Actual Calibration Evaluation
明确批准值：**NO**。在后续全部前置条件满足前，不得进入实际 Calibration Evaluation。

---

## 2. 登记矩阵

| Decision | 内容 | 裁决 |
|---|---|---|
| D0 Round-1 评分架构 | S-C deterministic baseline + S-A member-level LOO in-sample calibration | **A** |
| D1 S-A | 允许，仅 in-sample calibration（member-level LOO 强制，簇级 GT centroid 直接评价永久禁止） | **A** |
| D2 S-B | 批准建设方向（独立参考照片 + photo_id 隔离 + 双守卫 + enabled 快照 + 工件；不立即实施） | **A** |
| D3 S-C | 保留为 deterministic baseline（只读重算，禁写 Assignment/cpa） | **A** |
| D4 S-D | 接受延期 + 五项重入条件（§5） | **A** |
| D5 Prediction Artifact | 必须建立（10 字段，score 可空，NULL=无证据≠0，三种 scorer 可区分） | **A** |
| D6 Artifact 存储 | C：DB（查询/FK/UNIQUE/测试/Dataset 关联）+ 封存文件（SHA256/不可变归档），实施须设计 export→hash→seal | **C** |
| D7 实际 Calibration Evaluation | NO | **NO** |

## 3. 永久约束（与裁决同时冻结）

```text
S-A score ≠ S-B independent evaluation score

Calibration score ≠ Production Auto-confirm threshold
```

任何从 Calibration threshold 向 Production Auto-confirm threshold 的迁移，必须另开 Owner Decision Gate。

## 4. 跨决策一致性（登记注记）

- D0=A 在逻辑上蕴含 D1=A ∧ D3=A——三项裁决自洽。
- D7=NO 与 D0/D3 的"允许产生单点/标定数字"并不矛盾：**工件的建立与统计裁决先行，评估执行尚未开启**；开启执行（S-C 单点 / S-A LOO 的实际计算）须 Owner 新任务书。
- D6=C 蕴含未来一次 schema migration（工件 DB 表，calibration 命名空间）+ 封存流程设计——均属实施，须开发任务书。

## 5. D4 重入条件（认证级 Calibration Evaluation 重启的唯一路径）

1. S-B 独立参考数据与 photo_id 隔离链完成；
2. Calibration Evaluation Protocol 统计裁决完成；
3. Prediction Artifact 契约批准并实现；
4. D0–D6 Owner 决策全部完成；
5. Owner 单独发出 Evaluation Start 指令。

**五项全部满足**方可重启；缺一即维持 S-D 延期状态。

## 6. 范围与后果（本裁决不授权的事项）

本裁决**不授权**：任何评估执行（D7=NO）；S-B 实施；Prediction Artifact 实施（schema/封存流程）；任何代码、迁移、数据库、业务表变更。

下一阶段**仅允许**进入：
- `S-B Reference Data / Isolation Design`（开发前审查任务）
- 按需补充：`Prediction Artifact Design`、`Calibration Evaluation Protocol Owner Approval`

任何实施动作必须重新经过对应的开发任务和验收门。

当前全部保持 NOT STARTED：S-A LOO evaluation、S-C baseline evaluation、Precision、Recall、False-Accept、Margin、Threshold Search、ROC/PR、Auto-confirm、Auto-archive。

## 7. 可逆性与后续

- **D2** 仅批准方向：S-B 建设方案（参考数据获取方式、隔离守卫实现、流程）须另立开发任务书与验收门；方向本身可由 Owner 重新裁决。
- **D5/D6** 实施属独立开发轮（D6 含 migration 候选 + export→hash→seal 流程设计），未获实施授权。
- **D1** 的允许范围永久绑定 `IN-SAMPLE-CALIBRATION-ONLY` 标签；扩大或解除须新 Owner Gate。
- **D7** 翻转为 YES 的唯一路径 = §5 五项条件全部满足 + Owner 明确 Evaluation Start 指令。

---

**登记完成。SCORING-ARCHITECTURE-OWNER-GATE = DECIDED（D0=A, D1=A, D2=A, D3=A, D4=A, D5=A, D6=C, D7=NO）。**

*本文件为治理登记（untracked，未提交；提交与推送均属 Owner 操作）。*
