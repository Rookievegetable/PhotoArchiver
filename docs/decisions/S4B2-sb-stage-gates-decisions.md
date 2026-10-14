# S4B2 S-B 阶段四项 Owner 决策冻结（K / 2 / 3 / 4 正式裁决登记）

- **登记日期**：2026-10-09
- **裁决载体**：Owner 会话内正式裁决《S4B2 S-B 阶段四项 Owner 决策冻结》（四项"最终冻结文本"逐字引用于 §1）
- **决策门材料**：S-B 链会话交接核验报告（2026-10-09 交付，含四项挂起 OWNER-GATE 决策表与建议项；核验基线：pytest 1703/8/0 + ruff 全绿 + mypy 279 零问题，生产库 %TEMP% 副本只读核验全部命中）
- **Owner Decision Token**：`S4B2-OWNER-KAC-SCOPE-DEFER-NOSNAPSHOT-PFE-MINIMAL-APPROVED`
- **关联裁决**：`docs/decisions/S4B2-scoring-architecture-decisions.md`（D0–D7）；`docs/decisions/S4B2-sb-reference-design-decisions.md`（D-SB-1..12 + 14 条永久硬约束）；`docs/decisions/S4B2-sb-reference-scope-amendment.md`（D-SB-2A/2B）；`docs/decisions/S4B2-owner-decisions.md`（八项基础裁决）；ADR-047
- **状态**：`OWNER-GATE K/2/3/4 = CLOSED (A+C) / DEFERRED / RATIFIED / CLOSED (MINIMAL-SCHEMA)`；`S-B-6 / S-B-Scoring = AUTHORIZED TO START`（开发进入仍按程序经 Owner 任务书，草案已随本登记一并交付）；`ACTUAL-CALIBRATION-EVALUATION = NO`（D7=NO 不变）

---

## 1. Owner 裁决原文（最终冻结文本逐字）

### 1.0 决策总表

| # | 裁决事项 | Owner 决策 | 当前执行结论 |
|---|---|---|---|
| **K** | Phase K：`predicted + score=NULL` | **A + C**：允许该形态，但采用来源感知校验；S-B 当前强制 `predicted ⇒ score` | S-C 可合法出现 `predicted + NULL`；S-B 当前模型不得出现 |
| **2** | Evaluation Scope（eligible vs eligible-and-coverage-only） | **留待 Actual Evaluation 任务书裁决** | 当前不冻结，不阻塞 S-B-6 |
| **3** | 空候选（eligible = 0） | **追认现行 `NO SNAPSHOT` 规范** | 空候选不得创建空 Snapshot |
| **4** | PFE schema-level provenance | **维持现有最小 batch-level schema** | 不新增 schema 列，不做迁移 |

### 1.1 K.7 — Phase K 不完整预测语义（最终冻结文本）

> **`predicted + score=NULL` 不是全局非法状态。Prediction Artifact 是否允许该形态由 Prediction Source 的正式 Contract 决定。当前 S-B 的 `sb-member-max-cosine-v1` 契约规定：一旦产生 `predicted`，score 必须存在，因此 S-B 中 `predicted + score=NULL` 必须 fail-closed。D3=A 所定义的 S-C 语义不受影响，S-C 可以合法产生 `predicted + score=NULL`，不得为满足 schema 而伪造分数。**

附随冻结（K.4 禁止静默转换，逐字）：

> **无论哪个 Source，都禁止：`NULL → 0`、`NULL → 默认分数`、`NULL → no-candidate`、`NULL → 自动推导 score`。尤其不得因为 Evaluation 将来需要 score，就在 Artifact 层伪造一个分数。Artifact 必须忠实冻结其来源允许产生的结果。**

裁决理由（Owner 载明）：B（全局 fail-closed）不可接受——与 D3=A 直接冲突，将迫使修改 D3=A 或迫使 S-C 产生并非真实来源的分数；score 不是 Prediction 类型本身的普遍必要字段，而是**特定 Prediction Source 的模型输出契约**的一部分。当前契约：S-B `sb-member-max-cosine-v1` = `predicted ⇒ score required`；S-C（D3=A）= `predicted ⇒ score may be NULL`。

对 S-B-5 的影响（K.5）：`S-B-5 = VERIFIED` 不需要推翻；Builder 仍为"冻结合法输入"，不替 Source 决定 score 语义；新增要求 = **S-B source 在进入 Artifact Builder 前必须满足该 source 的 prediction contract**（producer 侧执行；消费侧 S-B-6 按其任务书做防御性复验，见 §3.3）。

对 S-B-6 的影响（K.6）：S-B-6 读取 S-B Prediction Artifact 时可直接采用"S-B predicted ⇒ score 一定存在"；`predicted + score=NULL` 不会成为 S-B Scoring 的合法输入。

### 1.2 Gate 2 — Evaluation Scope 政策（DEFERRED）

> **本项留待 Actual Evaluation 任务书正式裁决**（eligible vs eligible-and-coverage-only 二选一当前不冻结；当前 conditional population = 0，两种政策在当前数据上无实际差异）。

随裁决冻结的 S-B-6 边界（§3.3 逐字）：

> **S-B-6 可以产生 per-item scoring outcome，但不得自己决定哪些 item 最终进入 Evaluation denominator，也不得提前实现 Precision、Recall、Coverage、False Accept、False Reject、Threshold Search。这些留待正式 Evaluation 任务书冻结。**

最终状态：`Evaluation Scope Policy = OWNER-GATE / DEFERRED`；`S-B-6 Scoring = 不受阻塞`；`Actual Evaluation = NOT STARTED`。

### 1.3 Gate 3 — 空候选语义（RATIFIED，最终冻结文本）

> **当当前评估条件下 `eligible=0` 时，不创建空 Reference Snapshot，而返回 `NO SNAPSHOT`。该行为定义为规范性的显式失败/不可创建路径，不视为缺陷。合法 `no-candidate` 仅适用于已经存在可评估对象且模型明确产生 no-candidate 输出的情形。**

随裁决冻结的概念区分（§4.4）：`NO SNAPSHOT ≠ empty Prediction Artifact ≠ no-candidate Prediction`——三个概念不得混淆。

### 1.4 Gate 4 — PFE Schema-Level Provenance（MINIMAL SCHEMA，最终冻结文本）

> **PFE provenance 在当前阶段继续采用最小 schema / batch-level carrier，不新增 schema-level provenance 列，不增加 migration。逐样本 provenance 的写入语义已在 S-B-4 闭合，本阶段不重复建设。未来如出现必须区分更细 provenance 的实际需求，再通过独立 Owner 决策处理。**

### 1.5 S-B-6 授权边界（§八 逐字）

> **本决策后，S-B-6 可以正式进入开发。S-B-6 的职责固定为：Frozen Prediction Artifact + Frozen Ground Truth → Mechanical Scoring。**
>
> **S-B-6 不得：修改 Prediction Artifact；修改 Ground Truth；修改 Assignment；补 score；重新运行 matcher；重新生成 prediction；决定 Evaluation Scope；搜索 threshold；计算 ROC / PR；计算 Precision / Recall；执行 Auto-confirm；执行 Auto-archive。**

授权状态（§九 逐字）：`S-B-1..5 = VERIFIED`；`S-B-6 / S-B-Scoring = AUTHORIZED TO START`；`Actual Evaluation / Threshold Search / ROC / PR / Precision / Recall / Auto-confirm / Auto-archive = NOT STARTED`。

## 2. 登记矩阵

| Decision | 内容 | 裁决 |
|---|---|---|
| K — Phase K 不完整预测语义 | 合法性由 Prediction Source Contract 决定；S-B `sb-member-max-cosine-v1` 强制 `predicted ⇒ score`（fail-closed）；S-C 按 D3=A 合法 `predicted + NULL`；禁止一切静默转换 | **A + C** |
| 2 — Evaluation Scope 政策 | eligible vs eligible-and-coverage-only 留待 Actual Evaluation 任务书；S-B-6 不受阻、不得实现指标/分母 | **DEFERRED** |
| 3 — 空候选语义 | `eligible=0 → NO SNAPSHOT` = 规范性显式失败/不可创建路径 | **RATIFIED** |
| 4 — PFE schema provenance | 最小 schema / batch-level carrier；无迁移；S-B-4 逐样本 provenance 已闭合 | **CLOSED（MINIMAL-SCHEMA）** |
| S-B-6 授权 | 职责固定 = 冻结工件 + 冻结 GT → 机械评分；十条禁止 | **AUTHORIZED TO START** |

## 3. 一致性注记（登记时核对）

1. **K 与 D5 不矛盾（细化而非推翻）**：D5 "`top1_score/top2_score` 允许 NULL；NULL 表示没有 score evidence，不等于 0" 是 **schema 级许可**；K 将"该形态是否允许出现"细化为 **Source Contract 级规则**。两者层级不同、自洽。
2. **K 与 D3=A 自洽**：S-C 不伪造分数 → `predicted + NULL` 是 S-C 的 by-design 形态；全局 fail-closed（B）被否决的理由已由 Owner 载明（将迫使修改 D3=A 或迫使 S-C 伪造 score）。
3. **K.5 与 S-B-5 VERIFIED**：不推翻、S-B-5 已冻结工件无回改义务。契约执行点 = "S-B source 进入 Artifact Builder 前"（producer 侧，属未来 scorer/工件生产任务书）；S-B-5 审计的 Phase K 发现（builder 原样冻结、不校验该形态）作为事实维持；S-B-6 消费侧将按其任务书做**防御性契约复验**（fail-closed 拒绝，不做任何转换）。
4. **Gate 3 与 S-B-4**：S-B-4 审计 OWNER-GATE #2（空候选语义无冻结规范背书）就此关闭——现行实现被追认为规范。
5. **Gate 4 与 D-SB-9**：D-SB-9 的"PFE provenance 专列条件再议"结构保持——只有真实区分需求出现时经独立 Owner 决策重开；S-B-3/S-B-4 审计 carried gate（未来 provenance 区分）就此关闭。
6. **Gate 2 与 D0–D7 §4**：与"S-C 单点 / S-A LOO 实际计算须 Owner 新任务书"的程序一致；S-B-4 审计 OWNER-GATE #1（scope 政策）转为 DEFERRED，由 Actual Evaluation 任务书承载。
7. **D-SB-11 注记**：S-B-6 阶段定义由本裁决从 "S-B-6 Isolation / Leakage Acceptance Tests" 固定为 **"Mechanical Scoring"**；隔离/泄漏验收职责已由 S-B-1..5 各阶段独立验收审计承载，并作为 S-B-6 输入验证（工件/快照复验 + 契约校验）的组成部分延续。
8. **D7=NO 不变**：S-B-6 授权 ≠ Actual Evaluation 授权；D4 五项重入条件不变；Precision / Recall / Coverage / False Accept / False Reject / Threshold Search / ROC / PR 保持 NOT STARTED。
9. **14 条永久硬约束不变**：本裁决不触碰 S-B 实施基线任何一条；修改任一条仍须新 Owner Gate。

## 4. 结构性事实登记（随裁决一并记录，供 S-B-6 任务书引用）

- **Conditional Scorer Population = 0**（生产 12 条 PFE 全部 COVERAGE_ONLY；5 名业务人物 ∉ 冻结 36 人）→ `eligible` scope = 0 候选 → NO SNAPSHOT（现为规范路径）→ 无 S-B Artifact → **生产端 S-B 机械评分当前结构性不可执行**。S-B-6 首轮交付物 = 机械评分能力 + 契约校验 + 验收测试（fixture 驱动）；生产评分运行不属本阶段；生产 Snapshot / Artifact 发布仍为 Owner-controlled = NO。
- **prediction-artifact-v1 的 S-B 预测人口 ≡ 快照 entry 人口**（`(person_id, observation_id)` 逐条双射，`prediction_artifact_service._validate_sb_predictions` 代码强制）——即 v1 工件可承载的 S-B 预测为 entry-keyed（参考样本自指认型）；认证式"评估簇成员 × 参考样本"预测在 v1 契约下不可承载，若未来需要须经 prediction-artifact-v2 设计 + 新 Owner Gate（自然随 S-B-2B 解冻一并裁决）。此为代码核验事实，非推定。

## 5. 可逆性

- **Source Contract registry 可扩展**：新 scorer_version → 新契约 → 新 Owner 决策；K 不为未来 Source 预裁。
- **Gate 2** 于 Actual Evaluation 任务书再裁；**Gate 4** 于真实 provenance 区分需求出现时经独立 Owner 决策重开。
- **Gate 3 与 K** 为规范性冻结：修改任一处语义须新 Owner Gate。
- 本裁决不修改：D0–D7、D-SB-1..12、Scope Amendment、14 条永久硬约束、永久禁令（无 AI 身份判断 / 无第二标注员 / 无 agreement-adjudication / 无自动确认 / 无归档 / 无 push）。

---

**登记完成。`OWNER-GATES K/2/3/4 = CLOSED (A+C) / DEFERRED / RATIFIED / CLOSED (MINIMAL-SCHEMA)`；`S-B-6 = AUTHORIZED TO START`（经 Owner 任务书进入开发）；`ACTUAL-CALIBRATION-EVALUATION = NO`。**

*本文件为治理登记（untracked，未提交；提交与推送均属 Owner 操作）。*
