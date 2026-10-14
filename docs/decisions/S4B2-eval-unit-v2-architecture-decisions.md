# S4B2 Prediction Evaluation Unit / Artifact v2 — Owner 架构决策登记

- **登记日期**：2026-10-09
- **裁决载体**：Owner 会话内正式裁决《PhotoArchiver — Prediction Evaluation Unit / Artifact v2 Owner 架构决策》（核心冻结文本逐字引用于 §1）
- **决策门材料**：S-B-6 前置只读分析《Prediction Evaluation Unit（OPEN-5 → BLOCKING ARCHITECTURE GATE）》= READY-FOR-OWNER-ARCHITECTURE-DECISION（2026-10-09，9 项，全部代码引用）
- **Owner Decision Token**：`S4B2-OWNER-EVAL-UNIT-V2-TARGET-MEMBER-ARCHITECTURE-APPROVED`
- **关联裁决**：`docs/decisions/S4B2-sb-stage-gates-decisions.md`（本裁决更新其中 S-B-6 状态并落地其 §4 预告的 artifact-v2 Gate）；`docs/decisions/S4B2-sb-reference-design-decisions.md`（D-SB-3/4/5/7 + 14 条永久硬约束）；`docs/decisions/S4B2-scoring-architecture-decisions.md`（D5）；`docs/decisions/S4B2-sb-reference-scope-amendment.md`（D-SB-2A/2B）；ADR-047
- **状态**：`EVALUATION-UNIT = FROZEN (Target Cluster Member)`；`prediction-artifact-v1 = VERIFIED CONTRACT / NOT AUTHORIZED FOR ACTUAL EVALUATION`；`prediction-artifact-v2 = ARCHITECTURE DESIGN AUTHORIZED`；`S-B-6 implementation = BLOCKED PENDING TASK SPEC REISSUE`；`ACTUAL-CALIBRATION-EVALUATION = NO`；**Spec 修订冻结 1+2 已落地（v2.2）→ `READY-FOR-OWNER-FINAL-ARCHITECTURE-REVIEW`**

---

## 1. Owner 裁决原文（核心逐字）

### 1.1 核心架构决策（§一）

> **S-B 正式模型评估不得采用当前 prediction-artifact-v1 的 entry-keyed 自指认结构作为 Evaluation Artifact。**

该结构（Reference Person × Reference Observation，reference-entry-keyed）可以用于机械工件完整性验证 / pilot / fixture / contract testing，但**不得将其解释为 D-SB-3 / D-SB-4 所定义的认证式模型 Evaluation Prediction**。

### 1.2 三层冻结（§二）

- **Scoring Primitive** = `Target Cluster Member × Reference Person`（即 `target_observation × candidate_person`）；`score(target_observation, person) = max(该 Person 全部 enabled Reference Samples 的 raw cosine)`；禁止 centroid（D-SB-3 / D-SB-4 继续）。
- **Prediction Item** = `Target Cluster Member` = `(cluster_id, observation_id)`，在冻结的 cluster generation / cluster run 上唯一身份；保存 top-1（predicted_person_id + score）；top2 经后续字段 Gate 批准后保存。
- **Evaluation / Reporting Unit** = Cluster（Frozen GT 为 cluster-level）。member-level mechanical outcome 与 cluster-level evaluation outcome **必须区分，不得由 S-B-6 自行假设二者相同**；Cluster-level roll-up 规则另由 Evaluation 任务书冻结。

### 1.3 Ground Truth 连接语义（§三、§四）

> **Ground Truth 的身份真值来自 Target Cluster 的 Frozen Ground Truth，而不是 Reference Snapshot Entry 的 `person_id`。**

禁止 `predicted_person_id == entry.person_id → automatically correct` 式的"自证"。正确链条：Target Cluster Member → 所属 Frozen Target Cluster → Frozen Ground Truth → 该 Cluster 的真实 verdict / Person → 与 model prediction 比较。

传播规则：**PERSON(X)** → 该 Cluster 的目标成员机械继承 `GT person = X`（用于 member-level mechanical scoring）；**UNDECIDABLE** → 不得人为生成 GT person，只能得 `gt-cluster-undecidable`（或等价机械状态）；**OUT_OF_ROSTER** → 不得映射为 roster Person，保留 `gt-cluster-out-of-roster` 语义。

### 1.4 v1 正式处置（§五）

保留 v1，不删除、不篡改其历史契约，明确重新标注适用范围：`prediction-artifact-v1 = reference-entry-keyed prediction artifact`。允许继续用于 S-B-5 已完成的机械契约测试 / fixture / regression / 历史验证；**Actual Evaluation 不得消费 v1 作为认证式 Prediction Dataset**。`S-B-5 = VERIFIED` 继续有效；同时 `v1 = NOT THE AUTHORIZED EVALUATION ARTIFACT`。

### 1.5 v2 授权与设计方向（§六–§十一）

v2 获准进入**架构设计（不批准立即编码）**。最小核心身份：`cluster_run_id + cluster_id + observation_id + photo_id`；`(cluster_id, observation_id)` = Target Member identity；`cluster_run_id` 必须钉定冻结 Cluster generation，防止跨世代串用。

建议字段（§七）：逐项 `prediction_id / cluster_run_id / cluster_id / observation_id / photo_id / prediction_type / predicted_person_id / score / rank / margin`；artifact 级保留 `artifact_id / artifact_sha256 / reference_snapshot_id / reference_snapshot_sha256 / dataset_id / dataset_version / prediction_source / prediction_source_version / threshold=None / input_population_scope`。**`person_id` 不再作为 Target Prediction 的主键身份**；Reference Person 是 `predicted_person_id` 或 candidate score 的语义对象。

Reference Sample Evidence（§八）：`winning_reference_observation_id` 暂不强制进入 v2 核心 Prediction Identity；若未来记录 → ① 明确作为 evidence 字段；② 不改变 Prediction Unit；③ 建立 deterministic tie-break；④ 不把 evidence observation 当成 Target Observation（三实体概念分离：Target Observation / predicted Person / winning Reference Observation）。

Top-2（§九）：**v2 必须优先与正式 D-SB 字段契约保持一致，不得继续通过 `margin` 替代缺失的 top-2 原始结果**——`margin = top1_score − top2_score` 不能反向恢复 `top2_person_id / top2_score`；如 D-SB-7 的 top-2 字段仍属冻结契约则 v2 必须保留；具体字段清单在 v2 Task Specification 逐项对齐确认，**不得擅自删掉已冻结字段**。

Target Population（§十）：**必须通过 Frozen Target Manifest 固定**（记录 `cluster_run_id / cluster_id / observation_id / photo_id`，并以 manifest SHA 形成不可变身份）；**不得仅通过 current DB `face_cluster_members` 动态推导目标成员**。

职责分离（§十一）：`Reference Snapshot = 冻结"模型拿什么作为 Reference"`；`Target Manifest = 冻结"模型评估哪一些 Target"`。完整 Evaluation 输入 = `Reference Snapshot + Frozen Target Manifest + Prediction Artifact + Frozen Ground Truth`；**任何一项漂移，都不能被隐式接受**。

### 1.6 S-B-6 / roll-up / scope（§十二–§十四）

S-B-6 仍为 Mechanical Scoring，但必须基于 **v2 Evaluation Unit**；**不得使用 reference-entry self-key 作为 truth anchor**。**Cluster roll-up 不属于 S-B-6**（候选政策 A. 全成员正确 / B. 多数正确 / C. 任一正确 / D. 按照片加权 / E. 其它——属于 Actual Evaluation Policy，必须在 Evaluation Task Specification 中单独冻结）。Evaluation Scope 继续 DEFERRED；S-B-6 可产生 member-level mechanical outcomes，但不得决定 Evaluation / Coverage / Precision / Recall denominator。

### 1.7 不变项（§十五、§十六）

**K = A + C 继续有效**：S-B `predicted ⇒ score required`；S-C `predicted + score=NULL` 合法；Source Contract source-specific；S-B-6 仍可做 consumer-side defensive validation，但不是 Source Contract 的唯一实现者。**PFE provenance = MINIMAL-SCHEMA 继续**：不新增 PFE schema-level provenance 列，沿用 batch carrier + S-B-4 sample-level provenance。

### 1.8 状态与下一交付（§十七、§十八）

`S-B-6 = BLOCKED PENDING TASK SPEC REISSUE`（S-B-6 Authorization = 架构方向已批准；S-B-6 Implementation = 暂不开始）。顺序：`v2 architecture specification → Owner review → revised S-B-6 task specification → Dev-AI implementation`。

下一阶段只交付《Prediction Artifact v2 Architecture Specification》，最低 16 项内容（Target Member Identity / Target Manifest / Reference Snapshot linkage / PredictionRecord v2 / GT linkage / member-level scoring unit / cluster-level roll-up placeholder / top1-top2-margin contract / evidence reference semantics / deterministic ordering / SHA-immutable-atomic rules / v1 compatibility-legacy policy / migration requirement / test matrix / impact on S-B-6 / impact on D-SB-3/4/D5/D-SB-7）。**本阶段禁止直接编码。**

### 1.9 禁止事项（§十九）

在 v2 Architecture Gate 完成前：不得修改 v1 Artifact / 不得修改 Frozen GT / 不得修改 Assignment / 不得开始 Actual Evaluation / 不得计算 Precision、Recall / 不得 Threshold Search / 不得 ROC、PR / 不得 Auto-confirm / 不得 Auto-archive / 不得新增 PFE migration / 不得 commit / 不得 push。

### 1.10 最终冻结清单（§二十，13 条逐字）

```text
1. 当前 v1 = Reference-entry-keyed artifact
2. v1 不作为正式认证式 Evaluation Artifact
3. 正式 Evaluation Unit = Target Cluster Member
4. Scoring primitive = Target Member × Reference Person
5. Ground Truth truth anchor = Target Cluster Frozen GT
6. Reference Entry person_id 不得作为 truth anchor
7. Target Cluster 与 Target Member 必须概念分离
8. v2 Prediction Artifact 获准进入架构设计
9. Target Population 必须通过 Frozen Target Manifest 固定
10. Cluster-level roll-up 留给 Actual Evaluation Policy
11. Evaluation Scope 继续 DEFERRED
12. K = A + C 继续
13. PFE = MINIMAL-SCHEMA 继续
```

## 2. 登记矩阵

| # | 决策项 | 裁决 |
|---|---|---|
| 1 | v1 定位 | Reference-entry-keyed artifact；**NOT AUTHORIZED FOR ACTUAL EVALUATION**（保留，不删改） |
| 2 | Evaluation Unit | **Target Cluster Member**（`(cluster_id, observation_id)` @ 钉定 cluster_run_id） |
| 3 | Scoring Primitive | Target Member × Reference Person（max raw cosine，无 centroid） |
| 4 | GT truth anchor | **Target Cluster Frozen GT**（Reference Entry person_id 禁用） |
| 5 | GT 传播 | PERSON 继承 / UNDECIDABLE → gt-cluster-undecidable / OUT_OF_ROSTER → gt-cluster-out-of-roster |
| 6 | v2 授权 | **架构设计批准；编码未批准** |
| 7 | Target Manifest | **必须**（冻结目标人口；manifest SHA；≠ Reference Snapshot） |
| 8 | Top-2 字段 | D-SB-7 字段必须保留；margin 不得替代 |
| 9 | Cluster roll-up | 不属于 S-B-6 / 留给 Actual Evaluation Policy |
| 10 | Evaluation Scope | **DEFERRED** 不变 |
| 11 | K=A+C | 不变 |
| 12 | PFE provenance | MINIMAL-SCHEMA 不变 |
| 13 | S-B-6 | **BLOCKED PENDING TASK SPEC REISSUE** |

## 3. 一致性注记（登记时核对）

1. **OPEN-5 关闭**：S-B-6 前置分析中的 BLOCKING ARCHITECTURE GATE（Evaluation Unit）经本裁决冻结；v1 的结构事实（人口 ≡ snapshot entries）从"待确认读法"变为**已裁决定位**：reference-entry-keyed、禁止用于认证评估。
2. **状态更替**：`S4B2-sb-stage-gates-decisions.md` 中 "S-B-6 = AUTHORIZED TO START" 由本裁决更新为 "BLOCKED PENDING TASK SPEC REISSUE"（架构方向授权不变；实现入口前移至 v2 任务书）；该文档 §4 第 2 条预告的"prediction-artifact-v2 设计 + 新 Owner Gate"正式落地。
3. **S-B-5 VERIFIED 不推翻**：v1 契约（快照绑定双 fail-closed、entry 双射、确定性、不可变、零业务写入）原样有效；本裁决仅**重新标注其适用范围**（不得作为认证评估工件）。
4. **D-SB-3 / D-SB-4 回归而非修改**：v2 恢复"评估对象 = 成员 embedding 直评 × 参考样本 max cosine"的正式锚定；v1 从未承载该语义（前置分析 §5 已证）。
5. **D5 / D-SB-7 字段对齐**：`cluster_id` 与 `top1/top2_*` 在 v2 恢复；`isolation_invariant_sha256` 与 `computed_at / scorer_version` 的载体在 v2 Task Specification 逐项对齐确认（见 v2 规范 §16，含提案）。
6. **Gate 2（Evaluation Scope）= DEFERRED**；Cluster roll-up 为显式未裁空白（属 Evaluation Policy）。
7. **暂缓任务书的修正项**（denominator 表述 → "Frozen GT population source"；producer obligation vs consumer defensive check）继续有效，随 revised S-B-6 Task Specification 一并落地；本裁决 §十四 再次明确 S-B-6 不得决定任何 denominator。
8. **永久禁令不变**：无 AI 身份判断 / 无第二标注员 / 无 agreement-adjudication / 无自动确认 / 无归档 / 无 push；14 条永久硬约束不变。

## 4. 可逆性

- v2 架构**设计**可经 Owner review 修订后进入任务书；编码授权须待 revised S-B-6 Task Specification 批准。
- **Evaluation Unit 为规范冻结**：修改（含重新引入任何 reference-entry-keyed 评估路径）须新 Owner Architecture Gate。
- v1 处置（保留 + 重标注）与 top-2 保留原则为最终态；Manifest 必要性为最终态。
- 字段清单在 v2 Task Specification 对齐时仍可细化，但**不得删除已冻结字段**。

---

## 5. 修订冻结 1（2026-10-09，Owner 批复《Prediction Artifact v2 Architecture 修订冻结》）

Spec 首版（v2.0）review 结论：架构方向正确（Evaluation Unit / Scoring Primitive / Truth Anchor / "Reference Entry person_id 不得作 truth" / "v1 不得用于 Actual Evaluation"——自证风险已在架构层消除）。追加六项结构冻结（五项修订 + evidence 约束）：

1. **Target Population 权威来源（修订 1）**：`Frozen Dataset → Target Cluster Set → cluster_run_id → Target Cluster Members → Frozen Target Manifest`。**不得**将"cluster_run_id → 全部 face_cluster_members"直接视为评估人口；`Manifest.cluster_set = Frozen Dataset target cluster set`；Manifest 必须能够**独立证明**其 Target Population 与 Dataset 一致。
2. **GT Cluster → Member 传播（修订 2）**：Frozen GT Cluster 1:N Target Cluster Members；`GT = PERSON(X)` 时该簇内每个 Target Member 的 truth-person 均为 X；链条固定为 `Target Observation → Target Cluster → Frozen GT → truth state`；禁止使用 Reference Snapshot Entry.person_id 作为 truth。
3. **GT 状态独立（修订 3）**：`PERSON(X)` / `OUT_OF_ROSTER` / `UNDECIDABLE` 三态保持独立；**不得**将 OUT_OF_ROSTER 与 UNDECIDABLE 都编码成 NULL truth person 后丢失来源语义；`Evaluation denominator / Precision / Recall / Coverage / FA/FR` 仍继续留待 Actual Evaluation Task Specification。
4. **Top-1 / Top-2 权威字段（修订 4）**：正式采用 `top1_person_id / top1_score / top2_person_id / top2_score` 为 v2 权威 Prediction fields；`rank / margin` 如保留仅为 derived/convenience——producer 根据权威字段产生、consumer 可验证一致性、**不得存在第二个独立事实源**；`margin = top1_score − top2_score` 不得成为 top2 的替代品。
5. **Manifest ↔ Dataset 完整性（修订 5）**：v2 必须机械保证 `Frozen Dataset ↕ Target Manifest ↕ Prediction Artifact v2`——①Dataset 决定 Target Cluster Set；②Manifest 冻结这些 Cluster 的 Target Members；③Artifact v2 与 Manifest 双射；④Artifact 不得包含 Dataset 之外的 Target Cluster；⑤Manifest 不得包含 Dataset 之外的 Target Cluster。
6. **Reference Evidence（§七）**：`evidence_winning_reference_observation_id` 保持 optional；若存在，必须满足 `winning_reference_observation ∈ Reference Snapshot` **且**其 `person_id == predicted_person_id (top1_person_id)`；不得改变 Prediction Unit。

**审批边界（§八 逐字）**：修订后可进入最终 Owner review；在最终 review 前：不得编码 v2 / 不得修改 v1 / 不得 migration / 不得建立生产 Manifest / 不得建立生产 Artifact / 不得 Actual Evaluation / 不得 Threshold Search / 不得 P/R / 不得 ROC、PR / 不得 Auto-confirm / 不得 Auto-archive / 不得 commit / 不得 push。

**交付（§九）**：更新 Spec（重点修订 §2 / §5 / §6 / §8 / §14 / §15；新增 "Dataset ↔ Manifest population invariant"）；完成后终态 `READY-FOR-OWNER-FINAL-ARCHITECTURE-REVIEW`；仍禁止进入代码实现。

---

## 6. 修订冻结 2（2026-10-09，Owner 批复《Prediction Artifact v2 Architecture v2.2 修订要求》）

v2.1 最终架构审查意见落地七项（**仅文档与决策记录修订，不改业务代码**）：

1. **§2 Dataset / Cluster Run 集合校验修正**：①Dataset 集合必须**完整存在于**指定 Run（Target Cluster Set ⊆ Run Cluster Set；缺失 → fail-closed）；②**Run 的额外 Cluster 不得导致失败**（信息项，仅构建报告记录，不得进入 Manifest）；③**Manifest Cluster Set 必须严格等于 Dataset Cluster Set**。本条修正 v2.1 将 run 额外 cluster 视为失败项的双向 reconciliation 口径。
2. **完整 Target Member Set 不变量**：Manifest 必须包含指定 Run 中属于 Dataset Cluster Set 的**全部**成员；验证五类——缺失（漏项）/ 多余（多项）/ 重复 / 跨 Run / photo_id 错配；任一非空 → fail-closed。
3. **验证分层**：区分离线内部完整性验证（Layer A：哈希 / 计数 / 身份唯一 / 集合相等——**不能**证明无源遗漏）与源成员完整性验证（Layer B：重读源双向比对——唯一能证明"没有遗漏源成员"的验证）；**不得宣称 Manifest 自身哈希可以证明没有遗漏源成员**。
4. **Target Manifest ID + SHA 双绑定**：作为**待 Owner 最终批准的明确选项**——选项 A：`target_manifest_id` + `target_manifest_sha256` 双绑定（与 Reference Snapshot 的 `id（身份）+ sha256（内容完整性）` dual fail-closed 规则**完全对称**）；选项 B：仅 `target_manifest_sha256`。对称关系与推荐理由在 Spec §3 列明。
5. **`isolation_invariant_sha256` 正式语义对齐**：普通绑定摘要（snapshot_sha ⊕ manifest_sha ⊕ dataset 摘要）**不等同于隔离证明**——v2.1 的"binding digest"提案定位**撤回**；该字段在 D5/D-SB-7 中的正式语义**无法从现有冻结资料唯一确定** → 明确列为 **Owner-Gate（OG-1）**，候选方向：①冻结隔离四查（S-B-2 / S-B-3 E-05）判定输入 + 结果摘要；②结构性见证（两侧集合证据链摘要）；③显式废弃并载明理由。**不得以绑定摘要冒充隔离证明。**
6. **§14 测试矩阵扩展**：至少覆盖 额外 Run Cluster（非失败）/ 缺少 Dataset Cluster（失败）/ 成员漏项 / 成员多项 / 重复成员 / photo_id 错配 / 跨 Run 成员；并含"Layer A PASS ≠ 源完整性"负向断言。
7. **Producer 未实现显式化**：实际 `sb-member-max-cosine-v1` Prediction Producer **尚未实现**（src 中仅字符串常量/元数据 + 测试构造，无 scorer）；本 v2 架构与后续 S-B-6 Mechanical Scoring 任务**不得暗示已有可用于生产的预测工件**；任何真实 v2 Artifact 的前置 = 独立授权的 producer 任务 + eligible 参考数据 + Owner 发布指令（列为 OG-3）。

**边界（逐字）**：不得修改 v1、Frozen GT、Assignment、PFE 或业务规则；不得新增测试代码、迁移、生产 Manifest、生产 Artifact；不得执行 Actual Evaluation、Threshold Search、Precision/Recall、ROC/PR、Auto-confirm 或 Auto-archive；不得 commit 或 push。

**交付**：Spec v2.2 + 修改摘要 + 各 Owner-Gate 状态表 + 最终待裁事项；终态 `READY-FOR-OWNER-FINAL-ARCHITECTURE-REVIEW`。

---

**登记完成。`EVALUATION-UNIT = FROZEN (Target Cluster Member)`；`prediction-artifact-v2 = ARCHITECTURE DESIGN AUTHORIZED`；v2 Spec v2.2 = `READY-FOR-OWNER-FINAL-ARCHITECTURE-REVIEW`；`S-B-6 = BLOCKED PENDING TASK SPEC REISSUE`；`ACTUAL-CALIBRATION-EVALUATION = NO`。**

*本文件为治理登记（untracked，未提交；提交与推送均属 Owner 操作）。*
