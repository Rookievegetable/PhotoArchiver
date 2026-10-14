# S4B2 S-B-6 F-1 关闭 — Owner 决策登记（S-B-6 子链收口）

- **登记日期**：2026-10-09
- **裁决载体**：Owner 会话内正式裁决《Owner 决策：正式关闭 S-B-6 Finding F-1》（五点逐字于 §1）
- **依据**：独立复审终态 `S-B-6-F1-REAUDIT-VERIFIED`（2026-10-09，review-AI）：20/20 独立探针通过（含独立纯数学余弦 oracle、量化并列语义、漂移/缺键/非法 ID/不可读向量等全部负向路径）；ruff、mypy 284、定向 60、全量 pytest 1763/8/0 独立复跑通过；新发现 Finding = 0
- **关联登记**：`docs/decisions/S4B2-v2-architecture-final-decisions.md`（v2 终架构 + OG 状态表）；`docs/decisions/S4B2-sb-stage-gates-decisions.md`（K/2/3/4）；`docs/development/S4B2-S-B-6-Mechanical-Scoring-Task-Specification.md`（R3 任务书，审查时点快照——其 §7.2 的 ORD 表为审查时状态，不回改）
- **状态**：`F-1 = CLOSED`；`S-B-6 子链 = IMPLEMENTATION VERIFIED + AUDIT VERIFIED + F-1 CLOSED`；`O-1 = 非阻断结构性观察（保留登记）`

---

## 1. Owner 决策原文（五点逐字）

> 依据：独立复审终态 `S-B-6-F1-REAUDIT-VERIFIED`；20/20 独立探针通过；ruff、mypy、定向测试及全量 pytest 独立复跑通过；新发现 Finding = 0。
>
> 1. 正式关闭 F-1，确认 `evidence_winning_reference_observation_id` 字段、ORD-2 tie-break 与 verifier 重验证契约满足验收要求。
> 2. 保留 O-1 为非阻断结构性观察，不将其误记为缺陷。
> 3. 不追溯修改 S-B-1..S-B-5，不处理 NB-1/NB-2。
> 4. 本决定不授权 Producer 实现、Actual Evaluation、生产工件发布、数据库迁移、commit 或 push。
> 5. 关闭后停止，下一阶段另行提交 Owner 审批。

## 2. S-B-6 子链裁决链登记（收口汇总；各环证据为会话交付报告 + 仓库文件）

| 环节 | 时间 | 依据/证据 | 状态 |
|---|---|---|---|
| ORD-1..8 裁决（全 A）+ fixture-only 开发授权 + NB-1/2 明确范围外 | 2026-10-09 | Owner 会话裁决（本登记为链上首次落盘汇总；ORD 逐项裁决内容已固化于 R3 任务书 §7.2 建议栏与实现代码） | EXECUTED |
| S-B-6 fixture-only 实施 | 2026-10-09 | 5 新 src 模块 + 5 新测试文件（10 文件 4355 行，零既有文件修改） | IMPLEMENTED |
| 独立验收审计 | 2026-10-09 | 25/25 探针；门复跑 1760/8/0 + ruff + mypy 284；生产零接触双实证；BLOCKING 0 / NB 1（F-1）/ OBS 3 | `S-B-6-AUDIT-VERIFIED` |
| F-1 限界补充授权（方案 A：补字段 + ORD-2 tie-break + verifier 重验证 + 3 测试） | 2026-10-09 | Owner 会话裁决（限界：仅 S-B-6 模块与测试） | EXECUTED |
| F-1 补充实施 | 2026-10-09 | 4 文件修订（sb6_contract / prediction_artifact_v2_service / test_sb6_common / test_sb6_prediction_artifact_v2），零新文件；T-EV-1/2/3 | `S-B-6-F1-FIX-COMPLETE-PENDING-REAUDIT` |
| F-1 独立复审 | 2026-10-09 | 20/20 探针（独立纯数学 oracle + 全部负向路径）；门复跑 1763/8/0；新 Finding 0；共同错误风险经 oracle 排除 | `S-B-6-F1-REAUDIT-VERIFIED` |
| **F-1 关闭（本登记）** | 2026-10-09 | 本文件 §1 | **`F-1 = CLOSED`** |

## 3. 关闭确认内容

1. `evidence_winning_reference_observation_id`：入 `ARTIFACT_V2_ITEM_KEYS`（键必填可空、入 canonical payload 与哈希域）——验收通过；
2. ORD-2 tie-break：现有内核量化网格严格相等判并列 → 规范化 `observation_id` 字符串序最小者——经独立 oracle 验证；
3. verifier 重验证：硬约束（∈ Snapshot ∧ person == top1）+ winning 独立重推导；漂移/不可读 → `unprovable` 且 fail-closed——验收通过。

## 4. 保留观察与不授权事项

- **O-1（非阻断结构性观察，非缺陷）**：builder 与 verifier 共用 `_derive_evidence` 函数；verifier 重验证的独立性经 **oracle 层**实证（独立纯数学余弦、快照文件直算 min-ID、漂移/不可读负向），符合复审任务 §6 的共同错误排除标准。未来重构该函数时保留独立 oracle 断言（T-EV-1/2 已固化于常设套件）。
- **本决定不授权**（逐字）：Producer 实现、Actual Evaluation、生产工件发布、数据库迁移、commit 或 push。
- **持续不变**：不追溯修改 S-B-1..S-B-5；NB-1 / NB-2 维持登记未修复；D7=NO；Evaluation Scope / Cluster Roll-up / 统计政策仍 DEFERRED/未批；生产 Snapshot/Manifest/Artifact 发布 = Owner-controlled NO；commit/push = Owner-only。

## 5. 后续

关闭后停止。下一阶段任何动作（OG-3 Producer 任务书、Actual Evaluation 任务书、生产工件发布指令、commit/push 等）均须 Owner 另行审批。

---

**登记完成。`S-B-6 FINDING F-1 = CLOSED`；S-B-6 子链全链收口（实施 → 审计 → 修复 → 复审 → 关闭）。**

*本文件为治理登记（untracked，未提交；提交与推送均属 Owner 操作）。*
