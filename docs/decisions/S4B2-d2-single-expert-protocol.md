# S4-B-2 — D-2 协议变更：单人工专家 Ground Truth（正式裁决记录）

- **Decision ID**: `S4B2-D2-SINGLE-EXPERT-PROTOCOL-APPROVED`
- **日期**: 2026-10-04
- **裁决人**: Owner
- **性质**: 取代 `S4B2-owner-decisions.md` §2 中的 **D-2** 行（旧裁决 = 双人独立 + 100%
  双标 + 100% 仲裁）；其余裁决（D-7 / C-1 / D-1 / D-3 参数 / C-4 / D-4 / D-5）不变。
- **实施**: Migration 012 + Domain/Service/Repository 最小改造（本文件 §3）

---

## 1. 新 D-2（逐字）

```text
Single Human Expert Ground Truth
- 44/44 FaceCluster 全量人工判断
- 每个 Cluster 一个专家 Annotation
- 专家判断直接形成 Ground Truth
- 不再要求第二标注员
- 不再计算 inter-annotator agreement
- 不再进行 conflict adjudication
- Calibration 保持 append-only
- Calibration 与业务 Assignment 保持隔离
```

**旧 D-2 → SUPERSEDED**：

```text
2 independent annotators          → 废止
100% double annotation            → 废止
conflict adjudication             → 废止
```

## 2. Resolution 词表收敛

```text
旧: resolution ∈ {agreed, adjudicated}   → SUPERSEDED
新: resolution ∈ {expert}（唯一合法值）
    agreed      = ≥2 人共识语义     → 废止（count=1 的 agreed 是自相矛盾数据）
    adjudicated = 仲裁裁决语义       → 废止（新协议无仲裁过程，adjudicated_by 移除）
```

禁止任何伪兼容路径：不得伪造第二 Annotation / 第二标注员 / adjudicator；
`annotator_count == 1 == len(source_annotation_ids)` 由 Domain 实体与
DB CHECK（012）双侧强制。

## 3. 实施记录（Migration 012 + 代码）

- **Migration 012**（`012_single_expert_ground_truth`）：按 008/010 rename/copy/drop
  模式重建 `calibration_ground_truth` —— `CHECK (resolution IN ('expert'))`、
  新增 `CHECK (annotator_count = 1)`、移除 `adjudicated_by` 列；upgrade/downgrade
  均清空该表（旧词表行与 'expert' 不可诚实映射，生产库为空，有损策略显式记录）。
- **Domain**：`RESOLUTION_EXPERT` 唯一词表值；GT `__post_init__` 强制
  count==len(source)==1；`annotator_id` 非空守卫加固（None 亦拒）。
- **Service**：`resolve_ground_truth` 单专家直通（最新一条标注即真值）；
  删除 `agreement()` / `adjudicate()` / `independent_annotations()` 死路径。
- **Repository**：mapper/INSERT 同步（SQLite 与 in-memory 语义一致）。
- **UI**：零修改（面板本就只做独立标注；身份 fail-closed 保持）。

## 4. D-3 派生数字重述（仅派生性更新，统计方法不变）

| 项 | 旧（双人协议派生） | 新（单专家协议派生） |
|---|---|---|
| annotation events | 88（= 44×2） | **44**（= 44×1，每簇一条） |
| 预期仲裁 | ≈ 4.4 起冲突 | **0**（无 adjudication） |
| N / n0 / FPC | N=44，n0=384.16，FPC n≈39.57→40 | **不变** |
| gross | min(ceil(40/0.9), 44) = 44（普查） | **不变** |
| expected_effective | 44×(1−0.10) = 39.6 | **不变**（u 仍作用于普查分母） |
| 精度语义 | precision vs 双标共识 GT | **precision vs 单人工专家参考标准** —— 不得表述为"多标注员共识 Ground Truth"；无标注者间信度可测 |

Owner 给定的统计参数（p=0.50 / z=1.96 / 95% / e=5% / u=10% / ≤1%）与
样本量原则**不被本变更触及**。

## 5. Consequences & Reversibility

- Round-1 执行面简化为：1 名专家 × 44 簇 × 1 标注 = 44 events；无仲裁人前置。
- 本轮 Ground Truth 是**单专家人工参考标准**；未来若恢复双人制度，须新裁决 +
  新数据集 version（append-only 保证旧集可复现）。
- Reversibility：Migration 012 downgrade 完整（清空 GT 表后还原 011 形态）；
  本裁决可由 Owner 以新裁决取代（修订须更新本文件并注明日期与来源）。
