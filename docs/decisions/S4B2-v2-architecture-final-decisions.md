# S4B2 Prediction Artifact v2 — Final Architecture Decision（Owner 最终架构冻结登记）

- **登记日期**：2026-10-09
- **裁决载体**：Owner《S4B2 Prediction Artifact v2 最终架构决策》（2026-10-09 草案）→ Owner **APPROVED WITH CONDITIONS**（同日指令载明批准范围、必须保留的条件与 Token）
- **Owner Approval Token**：`S4B2-OWNER-V2-ARCH-FINAL-MANIFEST-DUALBIND-ISOLATION-ATTESTATION-APPROVED`
- **决策状态**：**APPROVED WITH CONDITIONS** —— **有条件批准；不得改写为无条件全面批准**
- **决策门材料**：Prediction Artifact v2 Architecture Specification v2.2（会话交付 = READY-FOR-OWNER-FINAL-ARCHITECTURE-REVIEW；**仓库无独立文件**）+ 草案只读一致性评审（2026-10-09，与冻结记录零矛盾）
- **关联裁决**：`docs/decisions/S4B2-eval-unit-v2-architecture-decisions.md`（含修订冻结 1/2；本文件为其最终批准登记，不改其原文）；`S4B2-sb-stage-gates-decisions.md`（K/2/3/4）；`S4B2-sb-reference-design-decisions.md`（D-SB-1..12 + 14 条永久硬约束）；`S4B2-scoring-architecture-decisions.md`（D5）；`S4B2-sb-reference-scope-amendment.md`；ADR-047

---

## 1. 批准的十项冻结（Owner 清单逐字）

```text
1. Prediction Artifact v2 以 Target Cluster Member 为预测条目身份
2. Frozen Dataset 唯一决定 Target Cluster Set
3. Target Manifest 必须完整冻结所选 Cluster 在指定 Run 中的全部成员
4. Reference Snapshot 与 Target Manifest 均实施 ID + SHA-256 双绑定
5. Frozen Ground Truth 是唯一 Target Truth 来源，Reference Entry 不得作为 truth anchor
6. isolation_invariant_sha256 的摘要对象是经过实际验证的结构化隔离证明记录，
   而非普通工件绑定摘要
7. top1/top2 是权威预测字段，派生字段不能形成第二事实源
8. v1 保留但不得用于正式认证式 Actual Evaluation
9. Prediction Producer 及实际发布继续实行独立授权
10. S-B-6 只做 Mechanical Scoring，Evaluation Scope、Cluster Roll-up 和正式指标政策仍未批准
```

另冻结：v2.2 §2 / §2A 获批 —— Dataset 权威来源链（Dataset → Target Cluster Set → Run 世代锚 → Members → Manifest）、Dataset Cluster Set ⊆ Run Cluster Set（单向；Run 额外 Cluster 非失败、不进 Manifest）、Manifest Cluster Set == Dataset Cluster Set（严格）、完整成员集五类校验（漏项/多项/重复/跨 Run/photo_id 错配）、Layer A（离线内部完整性）与 Layer B（源成员完整性）分层。

## 2. Owner-Gate 条件状态（必须保留）

| # | Gate | 状态 |
|---|---|---|
| OG-1 | `isolation_invariant_sha256` | **设计方向已批准（方案① + 证据契约）；证据契约待任务书逐项对齐** —— 批准不代表实际隔离证据契约已经完整 |
| OG-2 | Target Manifest 绑定 | **CLOSED** —— ID + SHA-256 双绑定（与 Reference Snapshot 对称） |
| OG-3 | Prediction Producer | **NOT STARTED** —— 未获开发或发布授权 |
| OG-4 | 字段清单 | **须按修订版任务书验收要求逐项对齐** |
| OG-5 | Cluster Roll-up | **DEFERRED**（Actual Evaluation Policy） |
| OG-6 | Evaluation Scope | **DEFERRED**（Actual Evaluation 任务书） |
| OG-7 | Reference Quality Threshold | **OPEN**（不因本决策关闭） |
| OG-8 | PFE Schema Provenance | **CLOSED / MINIMAL-SCHEMA** |

## 3. OG-1 条件冻结的完整语义（依 Owner 批准文本）

- **三分离**：`Isolation Validation`（实际执行隔离检查并验证结果）≠ `Isolation Attestation`（冻结检查规则、输入身份、结果和证据引用的结构化记录）≠ `isolation_invariant_sha256 = SHA256(canonical(isolation_attestation))`。
- **SHA-256 摘要本身不构成隔离证明**；只有实际隔离验证通过、验证记录完整、身份绑定正确，才能声明隔离检查通过。
- 现有冻结资料/数据结构无法提供某项检查所需证据时，**不得自动视为通过**——必须先补足证据契约，或明确报告无法证明。
- 验证器至少区分六种情况：Attestation 哈希有效且证据/检查全过 → 隔离验证通过；Attestation 哈希失配 → 拒绝；快照或 Manifest 身份不匹配 → 拒绝；任一隔离检查失败 → 拒绝；检查结果或必要证据缺失 → 拒绝；仅能验证 Attestation 文件完整性而无法核实源成员完整性 → **只能报告文件完整性通过，不得声称已独立证明源完整性**。
- 源成员完整性与离线内容完整性**必须分开报告**；Manifest 哈希不能替代对指定 Run 和 Dataset 成员的源端核验。
- 与 D5 / D-SB-7 对齐：保留正式字段 `isolation_invariant_sha256`，但在任务书中逐项明确（①字段保存什么；②哈希覆盖什么；③验证器如何验证；④哪些证据可离线复核；⑤哪些检查需重读源数据；⑥验证失败如何 fail-closed）；**不允许仅把 Snapshot SHA、Manifest SHA、Dataset ID/version 拼接后宣称隔离证明已完成**。

## 4. 边界与禁令

本轮授权（已执行完毕）：新增本决策文档 + 按规范更新文档索引 + 新增修订版 S-B-6 任务书（`READY-FOR-OWNER-REVIEW`）。
持续禁令（至修订版任务书另行批准前）：禁止修改 v1 / Frozen Ground Truth / Assignment / PFE Schema；禁止新增 Migration；禁止发布生产 Manifest / Artifact；禁止启动 Actual Evaluation；禁止 Threshold Search / Precision·Recall·FA·FR / ROC·PR / Auto-confirm / Auto-archive；禁止 commit / push。**所有源数据、成员完整性、双绑定、隔离证明或哈希验证失败，均 fail-closed。**

## 5. 一致性注记

1. S-B-1..5 = VERIFIED 不推翻；本裁决不授权 Actual Evaluation（D7=NO 不变）。
2. v1 保留原样，且**禁止**将 reference-entry-keyed 条目直接转换为 Target Member v2 条目（Evaluation Unit 不同，自动转换 = 伪造预测语义）。
3. Producer 独立门禁：架构批准 ≠ Producer 存在；S-B-6 不得暗示已有生产预测 / Fixture 等于真实模型预测 / 可凭架构批准开始实际评分。
4. 目标成员、Ground Truth 与 Prediction 的语义冻结（Evaluation Unit = Target Cluster Member；Scoring Primitive = Target Member × Reference Person；Truth Anchor = Frozen Target Cluster GT；GT 三态 `gt-person(X) / gt-cluster-out-of-roster / gt-cluster-undecidable` 独立、不得经 NULL person 塌缩）。
5. 修订版任务书内含 Owner 强制的八项携带项（每项对应验收标准）与统一验收要求；任务书必须区分"已有代码能力 / 计划新增能力 / 尚未证实能力"。

---

**登记完成。`V2-ARCH-FINAL = APPROVED WITH CONDITIONS`；`S-B-6 SPEC = READY-FOR-OWNER-REVIEW`；`IMPLEMENTATION = NOT AUTHORIZED`。**

*本文件为治理登记（untracked，未提交；提交与推送均属 Owner 操作）。*
