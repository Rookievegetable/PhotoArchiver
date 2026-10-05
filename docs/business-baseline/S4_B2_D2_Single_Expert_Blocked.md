# S4-B-2 — D-2 单人工专家 Ground Truth 最小改造（阻塞报告）

- 日期：2026-10-04
- 任务：D-2 协议变更（双标 ≥2 人 → 单人工专家）的 Domain/Service/Repository/Test 最小改造
- 结果：**S4B2-SINGLE-EXPERT-BLOCKED**
- 阻塞点：**诚实的 resolution 标签必须新增词表值 → 被生产实库 CHECK 锁死 → 必须 schema/migration 变更 → 触发任务书 Hard Constraint 5 停止门**
- 本轮代码/文档/schema 修改：**零**（CP0 全程只读；生产库只读连接）

---

## CP0 — 变更基线（"≥2 人"约束的精确层级分布）

| 层 | 位置 | 内容 | 性质 |
|---|---|---|---|
| **Domain** | `calibration_annotation.py:196-199` | `CalibrationGroundTruth.__post_init__`：`annotator_count < 2` → `ValidationError("...a single annotation is never truth")` | **正式 invariant**（任务书明确授权修改） |
| **Domain** | `calibration_annotation.py:72-74` | `RESOLUTIONS = frozenset({agreed, adjudicated})`；`:188` 未知值拒绝；`:192` agreed 禁带 adjudicator；`:194` adjudicated 必带 adjudicator | **正式 invariant** |
| **Domain** | `:190-191` | 空 `source_annotation_ids` 拒绝 | 保持（新协议仍要求） |
| **Service** | `calibration_annotation_service.py:21`（docstring）、`agreement()` :137、`adjudicate()` :156、`resolve_ground_truth()` :185 | 双分支：仲裁优先（→`RESOLUTION_ADJUDICATED`）/ ≥2 人一致（→`RESOLUTION_AGREED`）；**无单标注路径** | 逻辑性约束（随协议改造） |
| **Repository** | SQLite `add_ground_truth` :156 / in-memory 同名 | **纯透传**，无 ≥2 校验 | 无需修改 |
| **Schema** | 011 DDL :74-75 + 生产实库 PRAGMA 实测 | `resolution TEXT NOT NULL CHECK (resolution IN ('agreed','adjudicated'))`；`annotator_count INTEGER NOT NULL`（**DB 层无 ≥2 CHECK**，`adjudicated_by` 可空无绑定） | **本报告的 blocker 所在** |
| **Tests** | 5 文件约 79 处命中（domain 28 / lifecycle e2e 20 / parity 14 / service 12 / sqlite 5） | 依赖 ≥2 人、agreement、adjudication 语义 | 随协议批量更新（已定位） |
| **UI** | presentation 层 grep | **零 adjudication 暴露**（面板仅独立标注） | 无需修改 |

补充事实：`docs/decisions/` 中**不存在新 D-2（单专家）的正式裁决记录**——现存的
`S4B2-owner-decisions.md`（10-04 09:11）登记的仍是双人协议。任务书声明"Owner 已批准"，
但按本项目裁决登记惯例，正式记录应在解锁时一并补齐（见 §3 决策点 3）。

---

## Blocker（精确链条）

新协议要求单专家 GT 携带**诚实的来源标签**。逐一检验现有词表：

1. **`agreed`**：语义 = "≥2 名独立标注员一致"。`annotator_count=1` 的 agreed 行是
   自相矛盾数据（共识由一人达成）——正是任务书 CP1 禁止的伪兼容状态。
2. **`adjudicated`**：语义 = "仲裁人对冲突的权威裁决"。实体 `:194` 强制
   `adjudicated_by` 非空；而新协议明确 **"不再执行……adjudication"**。用
   `adjudicated` 标注"专家直接判断"会制造虚假仲裁溯源（adjudicated_by 指向一个
   并不存在的仲裁过程）——同样是任务书明令禁止的伪兼容状态（"不得保留'看起来支持
   adjudication、实际语义已经不存在'的伪兼容状态"）。
3. **新增诚实值**（如 `expert`）：Domain 层在授权范围内可加，但生产实库
   `CHECK (resolution IN ('agreed','adjudicated'))` 会在 **INSERT 时拒绝**——
   SQLite 路径（真实持久化）断裂，仅 in-memory 假绿。

结论：**诚实的单专家 GT 在当前 schema 契约下无法落库，必须修改
`calibration_ground_truth` 的 resolution CHECK = schema/migration 变更**。
按任务书 Hard Constraint 5 与 Scope Guard：停止、报告、等待 Owner。

**为什么不绕行**：不存在不改 schema 的诚实替代。禁止项已封死全部旁路
（伪造第二 annotator、复用 agreed/adjudicated、Repository 层改写标签均属
伪兼容/数据失真）。

---

## Required Owner Decision（解锁所需，三项）

### 决策点 1 — Migration 012（schema 变更授权 + 词表方案二选一）

生产 `calibration_ground_truth` 为**空表**、head=011、dual 协议已废弃，重建成本低。
两个方案（只读设计，未实施）：

- **方案 A（最小 diff）**：012 重建 GT 表，CHECK 扩为
  `resolution IN ('agreed','adjudicated','expert')`；Domain 词表同步加
  `RESOLUTION_EXPERT`，保留旧值（旧值成为"已定义但新流程不产生"的历史词）。
  改动小、S4-B-1 冻结语义兼容；代价是 Domain 保留两个不再产生的值。
- **方案 B（干净语义，推荐）**：012 重建 GT 表，CHECK 收敛为
  `resolution IN ('expert')`（表空无历史包袱）；Domain 删除
  agreed/adjudicated 及 agreement()/adjudicate() 双分支，`resolve_ground_truth`
  单专家直通。彻底消灭伪兼容，但 diff 更大（含 5 个测试文件 ~79 处）。
  方案 B 实施时同步保留 `adjudicated_by` 列为可空冗余或一并删除（Owner 定）。

两方案均需：012 含 upgrade/downgrade + 迁移回归测试；生产部署随下次停机窗口。

### 决策点 2 — 正式裁决登记

将新 D-2（单人工专家、44/44 全覆盖、每簇 1 标注、无 agreement/adjudication）
按 `docs/decisions/` ADR 惯例登记（含对本轮任务书声明"Owner 已批准"的原文记录），
并标注其**取代** `S4B2-owner-decisions.md` §2 的 D-2 行。

### 决策点 3 — D-3 派生数字重述（CP6 影响清单，本任务未改任何统计）

D-2 变更自动使以下**已登记的派生数字**失效，需 Owner/后续任务重述（公式本身不动）：

| 位置 | 现值（双人协议派生） | 单专家协议下的性质变化 |
|---|---|---|
| `S4B2-owner-decisions.md` §3 | `annotation_events = 44×2 = 88` | → **44**（每簇 1 标注） |
| 同上 | `预期仲裁 ≈ 4.4 起冲突` | → **0**（无 adjudication） |
| 同上 | `expected_effective = 44×0.90 = 39.6` | 公式不变，仍适用（u 仍作用于普查分母） |
| 同上 §4 一致性表 | "D-2 全量双标 + 100% 仲裁"交叉印证 | → 失效，需重述 |
| Gate §10 / Round-1 阻塞报告 §10 | events=88、adjudicator 身份前置 | → events=44、无仲裁人前置 |
| 精度语义 | precision vs 双标共识 GT | → **precision vs 单专家参考标准**（无标注者间信度可测；报告时不得表述为共识 GT——任务书 CP5 已明确） |

95% CI / e=5% / acceptable ≤1% 等 Owner 给定参数**不被本变更触及**（D-3 参数本身维持）。

---

## 解锁后的执行计划（已备好，待授权后一轮完成）

1. Migration 012（按决策点 1 选定方案）+ 迁移回归测试；
2. Domain：`annotator_count < 2` → `< 1`（错误信息同步改写）、resolution 词表按方案调整、
   GT 一致性校验（`annotator_count` 与 source 标注的真实标注者数一致，service 层核验）；
3. Service：`resolve_ground_truth` 单专家直通（1 标注 → GT，无 agreement/adjudicate 分支）；
   `annotate`/`latest_own_annotation`/freeze/`dataset_truth` 不动；
4. Tests：5 文件按 CP4 A–I 清单更新（单专家成立 / 空来源拒 / 零人拒 / 防伪造 /
   三态 + difficulty 保持 / append-only / business isolation / identity fail-closed /
   dataset version isolation）；
5. 文档同步（CP5）：决策记录 + 协议表述改为单专家参考标准；
6. 质量门 + 生产零触碰复核（本报告 §CP0 方法复用）。

## 本轮合规声明

- **零代码修改、零文档修改、零 schema 变更、零迁移**（CP0 全程只读）；
- 生产库只读连接：head=011、calibration 三表 0 行、cpa/pfe/archive=0（未开始 Round-1）；
- 未伪造任何身份/标注/裁决；未顺手修复任何问题；未自行修改统计协议。

---

```text
Decision:
S4B2-SINGLE-EXPERT-BLOCKED

Blocker:
诚实 resolution 标签（新增 'expert' 或收敛词表）被生产实库
CHECK (resolution IN ('agreed','adjudicated')) 拒绝 —— 必须 migration 012
重建 calibration_ground_truth 约束；现有两值均为任务书禁止的伪兼容标签
（agreed=≥2 共识矛盾；adjudicated=指向不存在的仲裁过程）。

Why current approved scope is insufficient:
授权范围 = Domain/Service/Repository/Test/协议文档，明确排除 Migration/Schema；
而不触碰 schema 的任何实现路径都只能产出伪兼容 GT（伪造第二标注员、假 agreed、
假 adjudicated），被任务书自身原则封死。

Required Owner decision:
① migration 012 授权 + 词表方案 A/B 二选一（建议 B）；
② 新 D-2 正式裁决登记（docs/decisions/ ADR，取代旧 D-2 行）；
③ D-3 派生数字重述确认（events 88→44、仲裁项归零、精度语义改为 vs 单专家参考）。
```