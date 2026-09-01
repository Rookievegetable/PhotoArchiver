# PhotoArchiver — Next Phase Feature Development Plan

> **文档性质**：下一阶段功能开发规划（2026-09-02 制定，Owner 已据此授权 Phase 9 P0 实施）
> **制定基线**：HEAD `4c0cc8c`（== origin/main，工作树干净；Phase 4.1→8 全部 COMPLETE，Git History Cleanup + Remote Alignment 完成）
> **方法论**：Evidence > Assumption——Feature Inventory 全部结论基于当前 HEAD 代码/测试实测，不将"文档说 COMPLETE"等同于"实现 COMPLETE"
> **状态**：P0（Filter Completeness）已经 Owner 授权并实施（见 `docs/development/PHASE_9_FILTER_COMPLETENESS_REPORT.md`）；P1/P2 待授权

---

## 1. Current Baseline

| 项 | 值 |
|---|---|
| Git | HEAD == origin/main == `4c0cc8c`；working tree clean |
| 已完成阶段 | Phase 4.1 / 4.2 / 5 / 6 / 7 / 8 Contract Revision / 8 Post-Revision Audit / History Cleanup / Remote Alignment |
| 质量门（规划时实测） | pytest 534 passed / 3 skipped（+1 已知 flake）；ruff ✓；mypy 170 files ✓；pip check ✓ |
| 开放 Finding | 无 P0/P1/P2；LIMIT-001/002（Known limitation）+ F-002（审计级 flake）维持登记 |

## 2. Completed Capabilities（当前 HEAD 实测闭环）

Import People、Folder Scan（EXIF captured_at）、Thumbnails、Face Detection/Recognition + Matching（真实模型、Worker 链）、Review approve/reject（持久化）、Archive（预览/冲突策略/dry-run/CLI）、Export ALL + FILTERED（真实 SQLite CSV/XLSX 集成证据，Phase 7）、Duplicate Detection（只读报告）、Settings、Plugin System（读 + import_people）、Persistence（Alembic 001+002，ADR-027）、Error Handling（TaskFailed → UI 面）、Logging。

## 3. Missing / Partial Capabilities（缺口与证据）

| 缺口 | 状态 | 证据 |
|---|---|---|
| 筛选人员轴 | PARTIAL（规划时） | `filter_bar.py` person combo 禁用占位（"reserved for a follow-up round"）；`search(person_id)` 后端已支持；Application 无人员读取用例 |
| 筛选日期轴 | PARTIAL（规划时） | `filter_bar.py` From/To 禁用占位；captured_at 数据链完整（EXIF→photos 表→search SQL→导出/归档） |
| CURRENT_BATCH 导出 | BLOCKED | 契约拒绝（§2/D4）；需批次持久化 → schema/migration（owner 门） |
| 照片删除/库管理 | MISSING | `PhotoRepository` 无 remove API；照片只进不出 |
| 重复处置 | MISSING | 检测只读；删除/保留语义需业务裁决（FK 级联潜在 schema 影响） |
| CLI 对等 | PARTIAL | 仅 scan/archive/backfill；import-people/match/export 无 CLI |
| 安装态分发 | BLOCKED | ADR-031 by-design（源码/clone 唯一支持）；需求触发门未开 |

## 4. Known Risks

| 风险 | 级别 | 处置 |
|---|---|---|
| F-002 match controller 线程池时序 flake | F3/INFO Known limitation | 全量偶发、单跑 ×2 稳定（历轮复判一致）；不修复 |
| LIMIT-001 缺模型 E2E 未入 CI | Low | 设计/覆盖限制，维持 |
| LIMIT-002 batch-level 取消粒度 | Low | 设计特征，维持 |
| Tier-3 人类文档历史状态陈述 | P3 | 指针化治理，另轮处理 |

## 5. Recommended Next Phase

**A. Feature Development —— Phase 9「Filter Completeness」（已获授权实施）**。理由：两项禁用轴是全库存量代码中唯一"后端完整、UI 未接"的用户能力（源码注释自认预留后续轮）；启用后与 Phase 7 FILTERED 导出/`_current_criteria` 持有点形成完整工作流（按人/按日期筛选 → 审阅 → 导出）；零 schema、零新依赖、低风险。

否决方向：C（分发，owner 门未触发）、D（性能，W2-3=A deliberate closure）、F（Known Limitation 不阻塞）、E（架构边界实测全绿）。

## 6. Feature Priority

| Priority | Feature ID | Feature | Goal | Status |
|---|---|---|---|---|
| **P0** | FEAT-P9-1 | 日期范围筛选 | From/To checkbox 门控启用，criteria 接入既有 search | ✅ 已实施（`d731b17`） |
| **P0** | FEAT-P9-2 | 人员筛选 | ListPersonsService + combo 接线，person_id JOIN 语义 | ✅ 已实施（`4d077fa`） |
| **P0** | FEAT-P9-3 | 三轴联合 + FILTERED 导出联测 | AND 语义矩阵 + 导出泄漏矩阵 | ✅ 已实施（`87f43e5`） |
| P1 | FEAT-P9-4 | CLI 对等补齐 | import-people / export 子命令（同一 Application 入口） | 待授权 |
| P2 | FEAT-P9-5 | 重复处置 / 照片删除 | 需删除语义 + FK 级联裁决（**ARCHITECTURE IMPACT = YES**，可能需 ADR + schema） | 待裁决 |
| P2 | FEAT-P9-6 | CURRENT_BATCH 导出 | 批次持久化（**ARCHITECTURE IMPACT = YES**，schema/migration owner 门） | 待裁决 |
| P2 | FEAT-P9-7 | 安装态分发（ADR-031 方案 B） | 需求信号触发（**ARCHITECTURE IMPACT = YES**） | 门控 |

## 7. Feature Dependency Graph

```text
FEAT-P9-1（日期轴）
   ↓ 共享 FilterBar 接线与测试基建
FEAT-P9-2（人员轴，新增 ListPersonsService）
   ↓
FEAT-P9-3（三轴联合 + FILTERED 导出联测）
   ↓（独立）
FEAT-P9-4（CLI，P1）—— P9-5/6/7（P2，各自独立 owner 门）
```

## 8. Architecture Impact

| Feature | Domain | Application | Infrastructure | Presentation | Workers | 新依赖 | Schema | ADR |
|---|---|---|---|---|---|---|---|---|
| P9-1 | 否 | 否 | 否 | 是（FilterBar） | 否 | 否 | 否 | 不需要 |
| P9-2 | 否 | 是（+ListPersonsService，薄读取） | 否 | 是 | 否 | 否 | 否 | 不需要 |
| P9-3 | 否 | 否 | 否 | 否（仅测试） | 否 | 否 | 否 | 不需要 |
| P9-5/6/7 | 可能 | 可能 | 可能 | 可能 | 可能 | 可能 | **可能** | **需要**（进入前必须前置门） |

P0 全部 **ARCHITECTURE IMPACT = NO**——零 schema/migration/依赖/契约/边界变更（实施后 `git diff` 复核确认）。

## 9. Testing Strategy

- 优先**真实 SQLite 集成测试**（沿用 Phase 7 泄漏矩阵思想）；Widget 级单测用真实 FilterBar（qtbot）。
- 边界 double 仅限模态 ExportDialog / QMessageBox（既有策略，Dependency/Boundary/Reason/What-remains-real 明示）。
- 每 Feature：targeted → P0 integration → full pytest → ruff/mypy/pip check。

## 10. Acceptance Criteria（P0，已全数达成）

见 `PHASE_9_FILTER_COMPLETENESS_REPORT.md` §10 DoD 清单（23 项全过）。

## 11. Execution Order

FEAT-P9-1 → 验证 → FEAT-P9-2 → 验证 → 三轴联合验证 → FILTERED Export 联测 → Final Verification → STOP。（P1/P2 待 owner 逐项授权）

## 12. Out-of-Scope

照片删除/重复处置、CURRENT_BATCH、批次持久化、安装态分发、性能优化、F-002/LIMIT-001/002 修复、`.ai/rules` 修订、schema/迁移、新依赖、UI 改版。

## 13. Definition of Done

每 Feature：链路真实闭环（UI→Application→Domain→Infrastructure→Persistence）、测试覆盖单轴/双轴/三轴/空条件/无命中、真实 SQLite 集成通过、四门绿、`git diff` 零越界、commit 符合 Conventional Commits。Phase 9 P0 DoD 23 项清单见实施报告 §10。
