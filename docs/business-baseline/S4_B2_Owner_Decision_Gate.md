# S4-B-2 — Owner Decision Gate（生产变更 / 校准进入决策）

- 日期：2026-10-04
- 前置：`S4_B1_Ground_Truth_Annotation_Readiness.md`（B-1 = COMPLETE-WITH-LIMITATIONS）、
  `S4_B2_Entry_Preflight.md`（ENTRY = CONDITIONAL）、`S4_B2_D7_Owner_Preflight.md`（D-7 DRY-RUN = SAFE）
- 性质：**决策门** —— 本轮**零生产变更**（无迁移、无重跑、无标注、无抽样、无 margin 实现、无自动确认）
- 代码基线：HEAD `27bdc64`
- 结论：**S4-B-2 EXECUTION GATE = CONDITIONAL**（§11）
- 2026-10-04 追记：Owner 八项裁决已送达并按原文回填 §10（正式记录：`docs/decisions/S4B2-owner-decisions.md`）；§11 解除条件满足。生产动作仍为零，执行等待 Production Preparation 任务书重新下发。

> （2026-10-04 追记）原版本报告未代 Owner 填任何决策项；当日 Owner 裁决送达后，
> §10 已按原文登记性回填，正式记录见 `docs/decisions/S4B2-owner-decisions.md`。

---

## 1. Current Baseline（CP1 只读复核，2026-10-04）

| 项 | 实测 | 任务书值 | 漂移 |
|---|---:|---:|---|
| production migration head | `008_archive_identity_and_confidence` | 008 | 无 |
| photos | 473 | 473 | 无 |
| observations | 1441 | 1441 | 无 |
| clusters | 36 | 36 | 无 |
| cluster_members | 399 | 399 | 无 |
| multi-face photos | 73 | 73 | 无 |
| multi-face observations | 1042 | 1042 | 无 |
| multi-face clustered | **0** | 0 | 无 |
| max clusters/photo | 1 | 1 | 无 |
| cluster_person_assignments | 0 | 0 | 无 |
| person_face_embeddings | 0 | 0 | 无 |
| recognition_results pending | 472 | 472 | 无 |
| calibration tables | 不存在 | 不存在 | 无 |

**零漂移。** 生产未发生任何变更——前两轮全部实验在 `%TEMP%` 快照上完成并已清理。

---

## 2. D-7 Technical Evidence（CP2 —— 归档既有 Dry-Run，本轮未重跑）

### 2.1 两轮对照

```text
Run A（对照，face_count_ranges=["1"]）:
  识别 77.0s → 1441 faces / 0 unreadable / 1 no-face / 399 in-scope photos
  聚类  0.5s  → 36 clusters / 399 members          ← 逐数复现生产
Run B（放宽，五档全开 [1][2-3][4-5][6-10][11+]）:
  识别 71.8s → 1441 faces / 1441 全部 in_selected_scope（472 有脸照片全入域）
  聚类  1.6s  → 44 clusters / 1441 members
```

### 2.2 关键计数（CP2 归档值）

```text
multi-face observations clustered      = 1042
multi-face photos with multiple clusters = 73/73（100%）
max clusters/photo                    = 36（36 人合影逐脸分簇）
empty cluster                         = 0
orphan member                         = 0
business tables changed               = 0（cpa / rr / pfe / archive_records 全零 delta）
```

### 2.3 支撑事实

- **无需新增检测作为数据前提**：1042 条多脸 observation 已在库且全部带 embedding，
  缺的只是识别期落定的 `scope_verdict` 门；
- **放宽必须重跑识别**：scope_verdict 只在识别期由 `classify_scope` 落定，系统无回填能力；
- **代次并存**：三代（生产 36/399、Run A 36/399、Run B 44/1441）互不覆盖，旧行零突变；
- **结构自洽**：44/44 簇满足 members == distinct photos（任何簇至多从一照片取一张脸）；
- 附带预演证据：`build_sqlite_repositories` 在生产数据副本上完成 008→011 自动升级
  （migration 预演 PASSED）。

---

## 3. Sample Size Calculation（CP7）

### 3.1 三个量严格区分（CP7.1）

```text
unique calibration units   = 抽样的独立统计单位 = Cluster（precision 分母单位）
annotation events          = units × annotators（双人制 → ×2）
annotators                 = 独立自然人数（≥2 独立 + 仲裁人另计）
```

例：36 units × 2 = **72 events**（不是 72 units）。events **不可**当作独立统计样本。

### 3.2 公式与层级（CP7.2）

```text
n0 = z² · p(1−p) / e²                       无穷总体下的二项 precision 样本量
n  = N · n0 / (N + n0 − 1)                   有限总体修正（FPC）—— 本库 N 极小，必须启用
u  调整层级 = gross sample size 层：
  gross_units   = ceil( n / (1 − u) )        招入标注的总体单位数
  events        = gross_units × 2            标注事件（双人）
  adjudication  ≈ gross_units × u            预期仲裁事件（u 比例分歧）
  expected effective (precision 分母) = n    ← 统计目标是它，不是 gross/events
```

明确禁止裸套 `n/(1−u)×2` 而不定义每层含义：**u 放大的是 gross 层，不是统计目标本身；
×2 只发生在 events 层。** 封顶规则：若 `ceil(n/(1−u)) > N`，取 `gross_units = N`（普查，
u 不再放大样本量）。

### 3.3 参数入口（CP7.3 —— 全部为 Owner 输入，不得代填）

| 参数 | 值 |
|---|---|
| N（当前可抽样 Cluster 总量） | **36**（现状） / **44**（D-7 批准后） |
| p（expected precision） | **OWNER DECISION REQUIRED** |
| z（confidence level） | **OWNER DECISION REQUIRED** |
| e（margin of error） | **OWNER DECISION REQUIRED** |
| u（expected undecidable rate） | **OWNER DECISION REQUIRED** |
| acceptable false-auto-confirm rate | **OWNER DECISION REQUIRED** |
| baseline precision（当前系统无自动确认，故无 baseline） | **OWNER DECISION REQUIRED** |
| unique clusters required | **计算结果 —— 待 p/z/e/u 输入** |
| annotation events | **= unique × annotators（待定）** |

仓库与正式文档中**不存在**任何已冻结的 p/z/e/u/置信水平/可接受错误率数值（前两轮
全库 grep 核实）——不得从历史聊天示例推断为 Owner 已批准。

### 3.4 机制示意（非决定，仅供量级感知；z=1.96 / p=0.5 假设）

| N | e | n0 | FPC n | 占比 |
|---:|---:|---:|---:|---:|
| 36 | ±10% | 96.0 | 27 | 75% |
| 36 | ±7% | 196.0 | 31 | 86% |
| 36 | ±5% | 384.2 | 33 | 92% |
| 44 | ±10% | 96.0 | 31 | 70% |
| 44 | ±7% | 196.0 | 37 | 84% |
| 44 | ±5% | 384.2 | 40 | 91% |

**量级事实**：N=36/44 时 FPC 使任何合理 e 都逼近全量普查（70–92%）。首轮标注大概率
就是"全量或近全量 × 双人"，抽样执行器的价值在**可复现与可审计**而非节省标注量。
u 示意（N=44, e=±7%）：u=10% → 41 units/82 events；u=20% → 46 > N → **封顶为普查 44**。

---

## 4. Margin Decision Options（CP11）

事实基线：`FaceObservation.embedding` 已在库（1042 条合影脸，检测管线产物）；
`person_face_embeddings` 是 Business Person Sample 数据（0 行）；`CosinePersonMatcher.match`
**只返回单一 best**，top1−top2 能力不存在，不得声称可算。

### Option A —— 首轮不做 margin 分层

- 优点：不触碰 Business sample writer；不引入新模型语义；§3.4 显示首轮接近普查，
  margin 分层的省样本价值本就极小；先建立基础 GT；
- 代价：首轮无 margin 分层轴（记为**显式协议降级项**，非缺省、非遗漏）。

### Option B —— 独立只读 candidate-margin 组件（本阶段只决策，不实现）

```text
FaceObservation.embedding / 簇心
  → 独立纯余弦候选计算（只读 face_observations）
    → top1 / top2 → margin
```

约束（设计已核可行）：**不写** `person_face_embeddings`、**不写** Assignment、
**不触发** Archive。可行性依据：余弦原语为纯 Python 可独立复用；person-质心方案受
冷启动约束（0 行样本）故不推荐。

**Owner 选择（§10 C-4）：DEFER / BUILD / REJECT —— AI 推荐 A（defer），不代填。**

---

## 5. Sampling Protocol（CP12 —— 正式冻结）

```text
protocol   = s4b2-sampling-v1
seed       = 20260101   （proposed protocol parameter —— 仓库无 seed 代码落点，
                          非 already implemented；由未来 executor 固化入库）
seed_round = "{seed}:{round_index}"  的 UTF-8 字节    例 "20260101:1"
cluster_id = UUID canonical string（小写 8-4-4-4-12）的 UTF-8 字节
separator  = 0x1F (ASCII Unit Separator)   —— 不出现在任一字段中，保证无歧义
hash_key   = SHA-256( seed_round_bytes || 0x1F || cluster_id_bytes )  → raw 32 bytes
排序键     = (hash_key ASC, cluster_id ASC)      ← 二元组，保证全序、消除平局歧义
选择       = 先分层 → 层内按排序键升序 → 取前 K
```

规范化已通过合成串验证（未触碰真实 cluster、未执行抽样）：轮内确定性、round 与 seed
变化均改变置换、分隔符无歧义、二元键唯一。

**明确声明**：`cluster_id ASC` **不是** random sampling（UUID 序为冻结随机且与轮次无关）；
本协议以 SHA-256 置换实现**确定性伪随机**。

**中立性（CP6.1）**：`det_score / quality_score / assignment / recognition_results /
top1 / top2 / margin` 一律**不得**直接决定入选；仅允许"先分层 → hash 层内排序 → 取 K"。
不得读取 `cluster_person_assignments` / `recognition_results` 作为抽样依据。

**可复现记录要求（未来 executor）**：population 快照、seed_round、协议版本
（`s4b2-sampling-v1`）、分层配额写入 `calibration_datasets.notes/params`。

## 6. Leakage Policy（CP13 —— 冻结）

```text
same person_id           → 同一 evaluation split（跨不同校准数据集/用途不得重复）
same photo_id            → 同一 evaluation split
same metadata_content_hash → 同一 evaluation split（473/473 已填充，可执行）
folder split             = UNAVAILABLE —— 单一有效 folder（DISTINCT folder_id = 1），
                            不得伪装成可执行
near-duplicate           = UNAVAILABLE —— 项目无感知哈希能力，不新增算法（记录限制）
```

**跨代次补充规则**：不同 cluster run 会对同一批 observation 重新成簇，故跨数据集版本
必须按 `photo_id`（及 GT 中出现的 `person_id`）去重，不以 cluster_id 为隔离依据。

---

## 7. Legacy 472 Impact（CP14）

复核不变：`recognition_results.pending = 472`（= 全量，2026-09-24 单窗口 legacy 产物，
person_id 全 NULL / confidence 全 0.0 的"空候选库 Unknown"行）。

| 边界 | 结论 |
|---|---|
| Calibration 链路读取 | **否**（协议 9 方法不涉 rr） |
| Ground Truth 读取 | **否** |
| Dataset Truth（`dataset_truth()`）读取 | **否**（只读 calibration 三表） |
| UI Calibration 展示 | **否**（标注界面消费簇与成员缩略图） |
| confirmation bias 通路 | **不存在** |
| 归属 | Business Review 历史队列（业务链 D-1 的 Owner 决策） |

**不得删除/修改。** 本轮未做任何处置。

---

## 8. Production Execution Plan（CP15 —— 只设计）

若 D-7 与 C-1 **均获批准**，执行顺序固定如下：

```text
1. backup（文件冷拷贝 + integrity_check）—— 回滚主手段
2. migration 008 → 011
3. schema verification（head=011；calibration 三表存在；
   photos/obs/clusters/members/rr 逐数与迁移前一致；rr 472 行原样）
4. production recognition rerun with expanded scope（五档全开）
5. cluster generation（新代次）
6. verify new generation（预期 44 簇 / 1441 members / 0 空簇 / 0 孤儿）
7. verify business isolation（cpa / rr / pfe / archive_records 零 delta）
8. verify Calibration tables（可写空、GT 可解析）
9. snapshot for sampling（population 快照 + seed_round 落档）
10. only then begin human annotation（D-1/D-2/D-3 前置未批准则停在此步）
```

**任一步失败即停止，不自动继续下一步。** 预期时长（Dry-Run 实测外推）：
备份秒级 + 迁移秒级 + 核验分钟级 + 识别 ~75s + 聚类 ~2s。

## 9. Rollback Boundary（CP16）

| 失败域 | 回滚/处置边界 |
|---|---|
| **Migration 失败** | 停应用 → 用 backup 文件整体还原（主）；`alembic downgrade`（次，已有迁移回归测试覆盖）。**不**在半迁移态下启动应用 |
| **Recognition / Clustering 失败** | **不得自动修改旧 generation**；保留旧 generation（36/399）完整；记录新 run 状态为 failed/partial；旧数据可继续服务 |
| **Calibration 失败** | **不得影响 Business Assignment**：calibration 链路与业务链 import 双向隔离（S4-B-1 验收 #25/#26）；标注/GT 故障仅限 calibration 三表，业务 Assignment/Projection 不受影响 |
| **重跑 scope 放宽后样本不合预期** | 保留新旧两代并存（已证可行），不删除旧代次；由 Owner 决定后续处置 |

---

## 10. Owner Decision Matrix（CP17 —— 2026-10-04 Owner 裁决已回填）

| Decision | 状态 | AI 的证据基础（不含推荐性选择） | **Owner choice（2026-10-04 裁决）** |
|---|---|---|---|
| **D-7** 扩大 face scope（["1"] → 全部档位） | 已裁决 | Dry-Run SAFE：44 簇/1441 members、业务表零写入、三代并存、~75s；生产操作需明确批准 | ☑ APPROVE —— scope = 全部现有 face-count ranges：`["1"]`、`["2-3"]`、`["4-5"]`、`["6-10"]`、`["11+"]`（Run B 已验证配置） ☐ REJECT ☐ DEFER |
| **C-1** migration 011（008→011） | 已裁决 | 副本预演 PASSED；011 建 3 空表；009/010 对现有数据零影响；停机 ≈5 分钟；rollback 清单完备 | ☑ APPROVE ☐ REJECT ☐ DEFER |
| **D-1** 人工标注投入 | 已裁决 | 数据层/UI/协议均就绪；**UI 完成不等于 Owner 已决定投入** | ☑ APPROVE ☐ REJECT ☐ DEFER |
| **D-2** 标注规程 | 已裁决 | 基础事实：2 独立标注员 + 仲裁 + append-only（S4-B-1 已实现）。待 Owner 明确：① 是否全部候选簇双人 ② 是否抽样复核 ③ adjudicator 身份归属 ④ 仲裁是否 100% 覆盖冲突 | ☑ APPROVE —— 独立标注员 = 2；100% Cluster 双人独立标注 = YES；抽样复核 = NO（首轮全量双标）；冲突 = 100% adjudication；adjudicator = 第三位独立人员；re-annotation = append-only ☐ MODIFY ☐ DEFER |
| **D-3** p / z / e / u（+ 可接受自动确认错误率） | 已裁决 | 机制完备（§3.2 FPC + gross 层 u 调整）；四个参数仓库零冻结值 | ☑ values: p=0.50 z=1.96（confidence=95%）e=5%（±5 个百分点）u=10%；acceptable false-auto-confirm rate = ≤1% ☐ DEFER |
| **C-4** margin | 已裁决 | A：首轮不做（不碰业务 writer）；B：独立只读簇心 margin 可行（不写 pfe/Assignment/Archive）。**AI 不代选** | ☑ DEFER（首轮不做 margin 分层——显式协议降级项） ☐ BUILD ☐ REJECT |
| **D-4** 自动确认适用范围 | 已裁决 | 当前系统**零自动确认**（全部身份经人工确认），无既有设计 | ☑ DEFER |
| **D-5** 自动确认后行为（是否直接归档） | 已裁决 | 归档当前均为手动任务；与 D-4 耦合 | ☑ DEFER |

> **裁决回填记录（2026-10-04）**：Owner 经裁决会话下达全部八项裁决，本矩阵为按原文的
> 登记性回填（AI 不代决、不增删语义）。裁决原文、派生样本量计算与一致性核验见正式记录
> `docs/decisions/S4B2-owner-decisions.md`。原「任何一项未被 Owner 明确决定前一律保持
> 未决」规则自本回填时点完成使命。

---

## 11. Entry Gate（CP18）

```text
Data layer                          = YES
UI                                  = YES
D-7 acquisition                      = YES（技术路径已验证 SAFE；执行待 D-7 批准）
Migration                           = PENDING OWNER（C-1）
Human annotation                    = PENDING OWNER（D-1 / D-2）
Statistics                          = PENDING OWNER（D-3：p/z/e/u）
Margin                              = DEFERRED / PENDING（C-4）

S4-B-2 EXECUTION GATE = CONDITIONAL
```

不得写 `OPEN`，更不得写 `READY` —— Owner 尚未作出任何一项决定。
CONDITIONAL 的解除条件 = §10 矩阵中 D-7、C-1、D-1、D-2、D-3 至少全部裁决；
C-4 可显式 defer（记为协议降级项）。

**回填后状态（2026-10-04）**：上述解除条件已满足 —— D-7 / C-1 / D-1 / D-2 = APPROVE、
D-3 五值齐备、C-4 / D-4 / D-5 = 显式 DEFER。授权层面完备；生产执行按
`S4_B2_Production_Preparation_Blocked.md` §11 既定流程（backup → verify → migration →
verify → recognition rerun → cluster → isolation verify → calibration verify → snapshot →
STOP，任一步失败即停）等待 Production Preparation 任务书重新下发后启动。
裁决回填本身未执行任何生产动作。

---

## 12. 本轮合规声明

- **零生产操作**：无 migration、无重跑、无聚类重跑、无标注、无抽样、无 pfe 写入、无自动确认/归档；
- 生产复核（§1）：head=008 / obs=1441 / clusters=36 / rr=472，与轮次开始时一致；
- **零源码修改**：本轮仅新增本报告文件；
- Hard Stop 遵守，**停止并等待 Owner 决定**。