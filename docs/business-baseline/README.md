# PhotoArchiver 业务基线（Business Baseline）

> **收录日期**: 2026-09-28 ｜ **收录裁定**: 全面工程健康体检 AUD-003 整改（Stage 10）
> **性质**: 只读基线材料——本目录文档**原样收录**，正文未做任何改写；业务结论以原文为准，本文档不重新解释业务规则。

## 1. 来源与有效性

| 文档 | 来源 | 对应基准 | 日期 | 当前有效性 |
|---|---|---|---|---|
| `Stage1_BusinessFacts.md` | `D:\workFile\PhotoArchiver-BusinessReview\`（仓库外，已按裁定收入） | HEAD `2823d1c`（行号按该 HEAD 重核） | 2026-09-28（18:53 更新） | **✅ 当前有效业务基线**（业务事实层） |
| `Stage1_Handoff.md` | 同上 | `2823d1c` | 2026-09-28 | 历史材料（Stage 1 会话交接记录） |
| `Stage2_BusinessRules.md` | 同上 | `2823d1c` | 2026-09-28（18:53 更新） | **✅ 当前有效业务基线**（业务规则层） |
| `Stage2_Handoff.md` | 同上 | `2823d1c` | 2026-09-28 | 历史材料（Stage 2 会话交接记录） |
| `Stage3_BusinessDiagrams.md` | 同上 | `2823d1c` | 2026-09-28（18:53 更新） | **✅ 当前有效业务基线**（业务流程图层，13 张 Mermaid 图 [IMPL] 节点经 Stage4.2 逐点核验） |
| `Stage4_FinalAudit.md` | 同上 | `b3b8685`→`2823d1c` 演进期 | 2026-09-28（00:01） | 历史（Stage 4 独立审计，判 NOT-FREEZE-READY；阻断项已由 `2823d1c` 修复） |
| `Stage4_1_FinalReview.md` | 同上 | `2823d1c` | 2026-09-28（02:05） | 历史（Stage 4.1 复审：代码级阻断闭合，余 3 文档级阻断 BLK-3R/D1D/D2D；该 3 项已由 2026-09-28 基线收口会话修复） |
| `Stage4_2_FinalFreezeReview.md` | 同上 | `2823d1c` | 2026-09-28（19:21） | **✅ 当前冻结复审**（8 项冻结条件全部满足；**冻结正式生效仍待 owner 签核**） |

## 2. 冻结结论与历史材料的关系

1. **现行业务基线 = Stage1（事实）+ Stage2（规则）+ Stage3（流程图）**，三者已统一到 HEAD `2823d1c`，是"业务规则是什么"的唯一完整载体；与 `.ai/` 状态文档、`docs/development/people-import-face-clustering-*.md` 计划文档互补（计划文档承载"如何走到这里"，本目录承载"现在是什么"）。
2. **Stage4 → Stage4.1 → Stage4.2 是同一轮冻结审查的演进链**：Stage4 发现阻断 → `2823d1c` 修复 → Stage4.1 复审收窄 → Stage4.2 终审。Stage4/4.1 保留为历史证据链，其结论被 Stage4.2 取代；Stage4.2 §9 的 8 项条件核对（含 D-1 七层一致、D-2 边界实测 0.39 不命中/0.40 命中）是当前冻结状态的权威记录。
3. **冲突裁决顺序**：若本目录与代码事实冲突，以 HEAD 代码为准并按 `.ai/rules/audit-methodology.md` 登记状态漂移；若本目录与 `.ai/PROJECT_STATUS.md` 冲突，两者都声明基线 `2823d1c`，业务语义以本目录（更细）为准。
4. **已知限制**：Stage1–3 末尾 §13/附录登记的 KL-1..6 与 GAP-1..5（如 person_embeddings 无 producer）为**有界现状事实**，处置追踪见 `.ai/KNOWN_ISSUES.md` 与 `docs/decisions/AUD-017-person-embeddings-decision.md`。
