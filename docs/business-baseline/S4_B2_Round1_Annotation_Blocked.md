# S4-B-2 — Round 1 真实双人盲标（阻塞报告）

- 日期：2026-10-04
- 任务：S4-B-2 Round 1 —— 固定 Snapshot 内 44 FaceCluster 全覆盖双人独立盲标
- 结果：**ROUND-1-BLOCKED**（阻塞点 = CP1 标注员身份缺失；CP0 已全数通过）
- 本轮生产写入：**零**（全程只读连接；calibration 三表保持 0 行）

---

## 1. Snapshot（CP0 —— 独立复核，全部通过）

复用 Production Preparation 已固定身份（`S4_B2_Production_Preparation_Complete.md` §10），
本报告**独立重算验证**，不转信：

```text
snapshot_id          = cdc17bfdf824fa8ffa97dee84a519f66200576354eab6493887669df7d8e379e
  复算               = SHA-256(db_bytes || 0x1F || utf8("011_calibration_annotations") || 0x1F
                        || utf8(recognition_run_id) || 0x1F || utf8(cluster_run_id))
  复算结果           = cdc17bfd… 7e379e   —— 与登记值**逐字节一致**
                        （= 快照时点后生产库零字节变更）
alembic_version      = 011_calibration_annotations          ✓
recognition_run_id   = fe983920-eefb-4078-801d-0ce8a5bc9d0d （completed, 1441 faces, 472 in-scope）
cluster_run_id       = a66943e7-1407-4b1c-836e-27c307a649a7 （completed, 44 / 1441）
```

候选池计数（本轮独立 SQL 实测，与任务书及 Prep 报告逐项吻合）：

```text
clusters                       = 44      ✓
members                        = 1441    ✓
multi-face photos → 多簇       = 73/73   ✓
max clusters/photo             = 36      ✓
empty clusters                 = 0       ✓
orphan members                 = 0       ✓
calibration_annotations 行数   = 0（标注未开始）
```

**CP0 结论：无数字漂移，不触发 STOP。**

## 2. Annotator Identity（CP1 —— **BLOCKED**）

任务书要求：`ANNOTATOR_A / ANNOTATOR_B 必须由调用方明确提供`。核查结果：

| 载体 | 核查结果 |
|---|---|
| 本任务书 | **未提供**任何标注员身份（无姓名/账号/角色） |
| `docs/decisions/S4B2-owner-decisions.md`（D-2 裁决） | 裁决了**规程**（2 独立标注员、100% 双标、100% 仲裁、第三人仲裁、append-only），**未指定自然人身份** |
| `S4_B2_Production_Preparation_Complete.md` §13 | 明确记录遗留项："自然人数身份登记待标注阶段执行（**人员未指定姓名/账号**）" |
| 全库 grep（docs/ src/ .ai/） | 无 `ANNOTATOR_A` / `ANNOTATOR_B` 的人名指定（仅服务文档提及该概念） |

按任务书硬停规则：

```text
BLOCKED: annotator identity missing
停止，不开始标注。
```

**同样缺失的还有 adjudicator 身份**（D-2 = 100% 冲突仲裁、第三位独立人员；CP16 要求
不得由 A/B 兼任）——冲突解决（CP15–CP17）在其到位前同样无法执行。

**结构性说明（为什么 AI 不能代标）**：双人盲标的效力基础是**两名独立自然人**经 UI
（`cluster_results_dialog` + `CalibrationAnnotationPanel`，blind view）各自独立判断。
由同一会话/同一智能体完成 A、B 两遍将构成任务书明令禁止的"同一人充当 A+B"，且盲评
隔离在同一意识内无意义——GT 的独立性前提即被破坏。因此标注执行**必须**由两名真实
标注员人工完成；AI 的职责边界是环境就绪核验、过程审计与后续统计。

### 2.1 解除阻塞所需（Owner 一次性提供即可）

```text
ANNOTATOR_A = <真实自然人姓名/账号>
ANNOTATOR_B = <另一真实自然人姓名/账号>   （不得与 A 相同）
ADJUDICATOR = <第三位独立自然人>          （D-2：100% 冲突仲裁需要）
```

建议登记载体：追加到 `docs/decisions/S4B2-owner-decisions.md`（D-2 细则处）或新建
`docs/decisions/S4B2-round1-annotators.md`（同 ADR 格式），此后标注会话即可启动。

## 3. Coverage

```text
clusters          = 44
annotator A       = 0/44（身份未指定，未开始）
annotator B       = 0/44（同上）
annotation events = 0 / 88（目标 88 = 44 × 2，D-2 全量双标裁决）
```

## 4–7. Verdict / Difficulty / Agreement / Ground Truth

**未开始**（CP1 硬停，全部 N/A）。规程与机制已就绪（见 §9 前置核验），启动后按
CP6 三态词表（person / out_of_roster / undecidable + 七项 difficulty_reason）、
CP8 append-only、CP12 只识别冲突不代仲裁、CP13 undecidable 保持第三类、CP14
out_of_roster 不混入 wrong person 执行。

## 8. Dataset

**未创建**（0 行）。CP20 前置（44/44 resolved）未满足。版本命名待定：任务书建议
`round-1`，登记时以项目当前约定为准（`calibration_datasets.version` 为自由文本，
freeze 走 `CalibrationDataset` 服务路径）。

## 9. Business Isolation + 盲标环境就绪核验（本轮已完成的部分）

生产隔离（只读实测，标注未开始即核验基线）：

```text
cluster_person_assignments = 0    person_face_embeddings = 0
archive_records            = 0    recognition_results    = 472（legacy pending 原样）
```

盲标环境就绪（当前树实测，42 项测试通过）：

```text
tests/unit/presentation/test_calibration_annotation_panel.py + tests/integration/test_s4b1_calibration_lifecycle_e2e.py
= 42 passed（含：blind view 仅 find_latest_own_annotation、calibration mode 中性成员条目、
  不显示 machine signal、roster_order 人选、三态词表 + 七项 difficulty、append-only 语义）
```

CP5（禁机器信号）与 CP9（盲评读取路径）的既有测试断言在当前代码上成立。

## 10. Statistics Boundary（按 D-3 派生，登记在案）

```text
Round 1 = Census（固定 Snapshot 内 44 候选 Cluster 全覆盖双人标注）
  —— 不是"随机抽取 44 个 Cluster"；N=44 下 gross=min(ceil(40/0.9),44)=44 普查封顶
expected_effective = 44 × 0.90 = 39.6 < 整数目标 40（普查上限损失不可扩样消除，如实报告）
annotation_events  = 44 × 2 = 88（units ≠ events ≠ annotators 严格分离）
预期仲裁           ≈ 4.4 起冲突（100% 覆盖、第三人、append-only）
观察错误率 ≠ 证明 ≤1%：后续报告必须分别给出 observed rate / confidence interval /
  Owner target（≤1%）三者，不得混同。
```

## 11. Tests

```text
calibration（panel 22 + lifecycle e2e 20） = 42 passed（本轮实测）
full pytest / ruff / mypy                  = 未运行 —— CP29 触发条件是"完成所有标注后"，
  本轮标注未开始且工作树零源码变更（上轮全量基线 1643/8 + ruff + mypy 272 green 仍有效）
```

## 12. Final Gate

```text
ROUND-1-BLOCKED
```

**阻塞原因（唯一）**：`BLOCKED: annotator identity missing` —— ANNOTATOR_A / ANNOTATOR_B
（及 adjudicator）未由调用方提供，任务书 CP1 硬停条款命中。

**已通过的前置**：CP0 快照与候选池全数独立复核通过（含 snapshot_id 逐字节复算一致）；
盲标环境 42 项测试全绿；业务表与 legacy 472 零触碰；calibration 三表 0 行。

**解除路径**：Owner 在任务书或 `docs/decisions/` 载体中一次性提供三名真实自然人身份
（A、B、adjudicator）→ 两名标注员经 UI 对 44 簇各完成一遍独立盲标（A/B 互不可见，
append-only）→ 重新下发核验任务（coverage 88 events → agreement/conflict → 100% 仲裁
→ GT integrity → dataset freeze → CP29 全量质量门）。

Hard Stop 遵守：未开始人工标注、未创建 CalibrationAnnotation、未执行抽样、未实现
margin、未计算 precision、未自动确认、未自动归档。