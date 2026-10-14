# S4B2 S-B Reference Scope Amendment — Owner Decisions（Scope 修订正式裁决登记）

- **登记日期**：2026-10-07
- **裁决载体**：Owner 会话内正式裁决（核心逐字引用于 §1）
- **修订对象**：`docs/decisions/S4B2-sb-reference-design-decisions.md` 的 **D-SB-2**（Reference Minimum Count）——拆分为分阶段策略；其余 D-SB-* 项与 14 条永久硬约束**不变**
- **决策门材料**：《S4B2 S-B Reference Scope Amendment Owner Gate》（2026-10-07，含统计影响分析与一致性核对）
- **状态**：`S-B-REFERENCE-SCOPE-AMENDMENT = APPROVED`；`ACTUAL-CALIBRATION-EVALUATION = NO`（D7 = NO 不变）

---

## 1. Owner 裁决原文（核心逐字）

```text
1 = 批准
2 = 批准
3 = 批准
4 = 批准
5 = 批准
6 = 批准
7 = 批准
8 = 批准
9 = 批准
```

### 1. S-B 分阶段策略
批准 `S-B-Pilot → S-B-Certification`。S-B-Pilot 仅用于验证：独立 Reference 评分链、photo_id 隔离、same-cluster / cross-run 防泄漏、Reference Snapshot、Prediction Artifact、scorer 实际可行性。S-B-Certification 才用于未来的独立身份性能认证。

### 2. Pilot minimum
批准 `minimum = 1 reference / covered person`。规则：0 reference → 不进入 scorer candidate set → 单独报告 coverage gap；1 reference → 允许 → 必须标记 single-reference variance risk。

### 3. Pilot target
批准 `target = 8–12 covered persons`。如果实际只能提供 4–7 人：降级为 **MICRO-PILOT**，仅允许验证 pipeline / leakage / score-domain / artifact validation，不得用于性能认证。

### 4. Certification reference
批准 `recommended = 3–5 references / person`。完整 Certification 的目标是逐步提高 Reference Coverage，最终尽可能覆盖 Frozen PERSON 集合。

### 5. 多人物 Reference Photo
批准 **ALLOWED**。一张独立 Reference Photo 可以经过独立 clustering 和人工确认，为多个 Person 提供 Reference Samples。仍必须满足 `photo_id ∉ EvalPhotoSet`。Reference Photos 与 Reference Persons 必须分开统计。

### 6. Coverage 单独报告
批准 `Coverage = mandatory`。Coverage 与 scorer identity quality 必须分开报告。禁止：无 Reference → 静默从结果中删除；无 Reference → 自动解释为 identity error。

### 7. Pilot Metrics
批准 `Conditional only`。如果后续获得 Owner 对指标计算的单独授权，Pilot 指标只能限定在 `Frozen PERSON ∩ Reference-covered PERSON`，并且必须明确标记为 `conditional scorer evaluation`，不得称为 full-population certification / production performance certification。

### 8. Micro-Pilot
批准 `4–7 persons = allowed`，但必须标记为 **MICRO-PILOT**，不得产生任何性能认证结论。

### 9. 完整 Certification
批准 **POSTPONED**。必须在 Reference Coverage 足够后，重新进入独立认证阶段。

## 2. 修订摘要（D-SB-2 → D-SB-2A / D-SB-2B）

```text
D-SB-2A — S-B Pilot:
  minimum = 1 reference / covered person
  target  = 8–12 covered persons（4–7 → MICRO-PILOT 降级标签）
  single-reference variance risk = REQUIRED FLAG

D-SB-2B — S-B Certification:
  recommended = 3–5 references / person
  Coverage 逐步扩大 → 尽可能覆盖全部 Frozen PERSON（36）
  POSTPONED：在 Coverage 足够后重新进入
```

## 3. 随裁决冻结的定义

- **Pilot 定位**：`S-B-Pilot ≠ Independent Performance Certification`；仅验证隔离链/独立沉淀/raw cosine/snapshot 复现/artifact 完整/泄漏守卫/小规模 score distribution。
- **Pilot Evaluation Subset**：由 Frozen round-1 **派生**（covered PERSONs → 对应 cluster_id），不修改 Frozen Dataset、不修改 round-1；选择规则在 scorer 运行前确定（结构性满足：coverage 在沉淀时确定、先于任何 score 存在）。
- **Coverage** = 拥有 ≥1 合法独立 Reference 的 PERSON 数 / Frozen PERSON 数（36）；**仅描述 Reference availability，不得解释为 Recognition accuracy**。
- **Conditional Scorer Population** = Frozen PERSON ∩ Reference-covered PERSON；Pilot 指标（若获单独授权）必须标记 conditional。
- **两阶段状态机**：`S-B-Pilot → 证明链路有效 → 扩大 Reference Coverage → S-B-Certification`；`Pilot PASS ≠ Certification PASS`。
- **0-reference person**：不进入 Conditional Scorer Population，Coverage Gap += 1；禁止用 Evaluation Photo 补齐、复制评估照片、同照片跨 run observation 冒充独立 Reference。

## 4. 不变项（裁决原文确认）

不修改：photo_id isolation、fail-closed、same-cluster guard、cross-run photo_id dedup、raw cosine、sb-member-max-cosine-v1、Reference Snapshot、Prediction Artifact、near-duplicate residual-risk policy、S-A ≠ S-B、Calibration score ≠ Production Auto-confirm threshold。以下决策继续有效：`ACTUAL-CALIBRATION-EVALUATION = NO`、`D7 = NO`。**本 Amendment 不授权绕过 Reference Photo 输入门。**

## 5. 决策门材料随裁决一并冻结的审核要点

1. **零代码影响**：已实现的 `ReferenceIntakeService` 对数量天然无感知（不含 count 阈值）；D-SB-2 数量规则为协议/报告层规则；single-reference 标志属 S-B-4 Snapshot——本修订零代码变更。
2. **多人物参考照片依赖性注记**：同一照片产出的多人的参考彼此相关（同一次拍摄条件）；未来 conditional pilot metrics 的 CI 须在"簇内跨照片相关"之上再叠注此参考侧相关。
3. **预选规则结构性满足 + 封存要求**：coverage 在沉淀时确定、先于任何 score；可审计性要求 covered-person 清单与 single-reference 标志在 S-B-4 Snapshot 封存、且先于任何评分。
4. **Conditional 分母（GT 双射可精确重建）**：36 PERSON ↔ 36 簇一一对应；Conditional Recall/Precision 分母 = covered persons 数 / covered persons 簇上的接受数。
5. **统计影响（2026-10-07 精确计算）**：Pilot n=8/10/12 全对 → Wilson95 下界 0.676/0.722/0.758（±32/28/24pp）；0-FA CP 单侧 95% 上界 31.2/25.9/22.1%；Micro n=4 → 下界 0.510、上界 52.7%——**Pilot/Micro-Pilot 在数学上不可能支撑阈值认证**；覆盖率算例 8/36=22.2%、10/36=27.8%（gap 26）、12/36=33.3%（gap 24）。

## 6. 下一阶段与边界

下一阶段仅允许进入 **S-B-1 Reference Photo Intake，Scope = S-B-Pilot**（原任务书流程与守卫不变，仅覆盖目标改为 Pilot 规模）。生产导入仍等待 Owner 提供：①真实、独立的 Reference Photo 目录；②人工确认方式（UI 配对工作台 / 会话内委托）。禁止自动执行：导入、创建 PFE、Recognition、Clustering、Snapshot、Prediction、Scoring、任何指标。

## 7. 可逆性

Pilot target（8–12）与 Certification 节奏可随实施证据再裁决；MICRO-PILOT 为降级标签而非否决；本修订不触碰 14 条永久硬约束——修改任一条仍须新 Owner Gate。

---

**登记完成。`S-B-REFERENCE-SCOPE = AMENDED`（Pilot → Certification）；`ACTUAL-CALIBRATION-EVALUATION = NO`。**

*本文件为治理登记（untracked，未提交；提交与推送均属 Owner 操作）。*
