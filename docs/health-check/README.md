# 全面工程健康审计产物（2026-09-28）

> **性质**: READ-ONLY 审计产物（Stage 0–9 体检 + Stage 10–13D 整改闭环）——记录**审计时点**的事实与结论，不随代码演进而自动更新。
>
> **审计基准**: `2823d1c`（体检执行 HEAD）→ 整改在 `a01f11b`…`a5fb7aa`（见 §版本谱系）
> **审计日期**: 2026-09-28（整改 09-28 ~ 09-30）
> **当前权威**: 项目**当前状态**以 `.ai/PROJECT_STATUS.md` 为准；本目录是"这些状态为何如此"的证据底稿。

## 文件索引

| 文件 | 内容 | 状态 |
|---|---|---|
| `AUDIT_BASELINE.md` | 审计基线：HEAD/版本/技术栈/结构/测试与工具基线/审计限制/未知项 | 审计时点快照（部分数字已被 Stage 12/13 更新，见 `PROJECT_STATUS.md` 覆盖率行） |
| `ARCHITECTURE_AUDIT.md` | 分层/依赖方向/循环依赖/规模热点（Stage 1） | 结论已落地为 ADR-049/050/051 |
| `CODE_LOGIC_AUDIT.md` | 业务链行为审计、状态机、幂等矩阵（Stage 2） | 结论已落地（Stage 11B/12A/12D） |
| `DATA_PERSISTENCE_AUDIT.md` | Schema/迁移/仓储/约束对账（Stage 3） | 结论已落地（ADR-048/052） |
| `TEST_QUALITY_AUDIT.md` | 测试结构/质量/覆盖盲区（Stage 4） | 盲区已由 Stage 12B/12C/13A/13B/13C-C 补齐 |
| `DOCUMENTATION_AUDIT.md` | 文档体系一致性（Stage 5） | 结论已落地（Stage 10 治理恢复） |
| `RELIABILITY_SECURITY_PERFORMANCE_AUDIT.md` | 任务生命周期/安全/性能（Stage 6） | 取消延迟结论已落地（Stage 12C） |
| `UI_AUDIT.md` | UI 状态/交互/工作流（Stage 7） | — |
| `CROSS_DIMENSION_RECONCILIATION.md` | 十维交叉矩阵（Stage 8） | — |
| `FINAL_HEALTH_CHECK.md` | 体检终判（Stage 9）：**ATTENTION** | **历史快照**——结论已被 Stage 10–13D 整改取代（当时 P1×1/P2×10/P3×15） |
| `FINDINGS_LEDGER.md` | **Finding 统一台账**（25 条：P1×1 / P2×10 / P3×14） | **当前有效**——状态字段为权威（2026-09-30 Stage 14 终态：23 FIXED + 1 ACCEPTED-RISK + AUD-002 CLOSED，无 OPEN） |
| `evidence/` | 可复现证据：依赖扫描脚本+结果、覆盖率 JSON | 审计时点数据（coverage_stage4.json = 体检基线；stage13b = 整改后） |
| `../development/evidence/stage-f-*.md` | Stage F 冻结评审报告与其真实性核验记录（历史评审材料） | 历史材料（评审对象为 `b3b8685`/`2823d1c`） |

## 与当前项目状态的关系

- **Finding 台账是当前权威**：25 条发现全部终态（2026-09-30 Stage 14 Final Re-Audit）——P0 = 0、P1 = 0、P2 = 0、P3 = 0 OPEN，无 BLOCKED；23 FIXED + `AUD-024` ACCEPTED-RISK（ADR-053）+ `AUD-002` CLOSED（run #127 对最终 HEAD `5525d95` 三平台全绿）。
- **整改结论均已进入 SSOT**：每条 FIXED 的处置落在 `.ai/ARCHITECTURE_DECISIONS.md`（ADR-042~053）、`.ai/PROJECT_STATUS.md`（§2 逐阶段记录）、`CHANGELOG.md`、`docs/development/`。
- **历史快照标注**：`FINAL_HEALTH_CHECK.md` 与 `AUDIT_BASELINE.md` 中的数字反映审计时点，**不代表当前**（当前测试/覆盖率基线见 `PROJECT_STATUS.md` §5/覆盖率行）。

## 版本谱系（审计 → 整改）

```
2823d1c（体检基准）
 ├ a01f11b Stage 10  治理基线恢复（AUD-001/003/009/014/017 决策准备）
 ├ 0e47cc8 Stage 11B AUD-017 Option C 闭环（ADR-047）
 ├ bea9272 Stage 12A AUD-004 全链回归（+ 聚类时间排序接缝修复）
 ├ 0a27970 Stage 12B AUD-019 workers/pairing 守卫
 ├ a7a6f6c Stage 12C AUD-023 取消延迟
 ├ 0a5c8d1 Stage 12D AUD-015 归档一致性（ADR-048）
 ├ 928981a Stage 12E AUD-010 文件 I/O 端口化（ADR-049/DEP-072）
 ├ 1ad9791 Stage 13A P3 治理卫生（AUD-005/006/007/008/022）
 ├ eabb685 Stage 13B P3 契约/覆盖率/命名（AUD-012/020/021）
 ├ 935866d Stage 13C-A P3 架构结构（AUD-011/013，ADR-050/051）
 ├ 94e57a5 Stage 13C-B 命令契约/数据模型（AUD-016/018，ADR-052）
 └ a5fb7aa Stage 13C-C 连接生命周期/审核错误语义（AUD-024/025，ADR-053）
```

## 使用规则

1. 引用本目录任何"当前状态"前，先读 `.ai/PROJECT_STATUS.md`——**SSOT 优先于本目录**。
2. 台账状态变更（Finding 关闭/改判）必须同步 `KNOWN_ISSUES.md` 与 `PROJECT_STATUS.md`，不得只改本目录。
3. 报告正文不改写（历史记录）；需要补充判定时追加带日期的记录。
