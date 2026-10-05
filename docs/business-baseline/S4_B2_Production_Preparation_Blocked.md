# S4-B-2 — Production Preparation（阻塞报告）

- 日期：2026-10-04
- 任务：`S4-B-2 Production Preparation`（011 部署 + D-7 生产重跑）
- 结果：**PRODUCTION-PREP BLOCKED**
- 停止位置：**CP1 之前** —— 未创建备份、未迁移、未重跑、未做任何生产写入
- 触发条件：任务书第「Owner 已裁决事项」节的六项裁决全部为**未填充占位符**

---

## 1. Owner Decisions（逐项原样列出 —— 全部为空）

任务书提供的裁决位与本报告读到的实际状态：

| 决策 | 任务书占位符 | 磁盘实际状态 | 裁决 |
|---|---|---|---|
| D-7 expanded face scope | `<APPROVE / REJECT / DEFER>` | 决策矩阵第 259 行：`☐ APPROVE ☐ REJECT ☐ DEFER`（全未勾选） | **缺失** |
| C-1 migration 011 | `<APPROVE / REJECT / DEFER>` | 第 260 行：同上全未勾选 | **缺失** |
| D-1 human annotation | `<APPROVE / REJECT / DEFER>` | 第 261 行：同上全未勾选 | **缺失** |
| D-2 annotation protocol | `<具体批准内容>` | 第 262 行：`☐ APPROVE ☐ MODIFY ☐ DEFER`；四个子项（是否全量双人 / 是否抽样复核 / adjudicator 身份归属 / 仲裁是否 100% 覆盖冲突）均无答复 | **缺失** |
| D-3 statistical parameters | `p = <VALUE>` / `confidence = <VALUE>` / `e = <VALUE>` / `u = <VALUE>` / `acceptable false-auto-confirm rate = <VALUE>` | 第 263 行：`☐ values: p=__ z=__ e=__ u=__ ☐ DEFER`，无任何数值 | **缺失** |
| C-4 margin | `<DEFER / BUILD / REJECT>` | 第 264 行：`☐ DEFER ☐ BUILD ☐ REJECT` | **缺失** |
| （关联）D-4 自动确认范围 | 未在本任务列出 | 第 265 行：待决 | 缺失 |
| （关联）D-5 自动确认后归档行为 | 未在本任务列出 | 第 266 行：待决 | 缺失 |

**核查方式与结果**：
- `S4_B2_Owner_Decision_Gate.md` §10 决策矩阵八行**全部保持空白勾选框**（无 ☒/☑）；
- `docs/business-baseline/` 下无任何裁决/裁定文件（仅 4 份报告 + 早期 Stage 文档）；
- `git log` 无 Owner 裁决提交（HEAD 仍为 `27bdc64`）；
- 工作树无新增裁决文件。

**未自行填写任何默认值。** 按任务书与 Owner 工作流的既定规则，「UI 已完成」不等于
「Owner 已批准投入」，占位符不得由 AI 代填。

---

## 2. Backup Evidence

**未执行。** 备份是 CP1–CP11 执行链的第一步，而执行链的准入条件是 D-7 与 C-1 均获
批准；在裁决缺失时创建生产冷备份没有对应的授权依据，故未创建、未触碰生产文件。

（若后续批准：备份目标为 `%LOCALAPPDATA%\PhotoArchiver\photo_archiver.db`，
主回滚手段，须含 md5/sha256 + `PRAGMA integrity_check` 复核。）

## 3. Migration Result

**未执行。** C-1 未裁决 → 禁止执行 008→011。生产库 `alembic_version` 仍为
`008_archive_identity_and_confidence`（本轮只读复核确认）。

## 4. Recognition Result

**未执行。** D-7 未裁决 → 禁止以任何 scope 重跑生产识别。生产 observations 仍为 1441。

## 5. Clustering Result

**未执行。** 无新 recognition run 即无聚类对象。生产 clusters/members 仍为 36 / 399。

## 6. Business Isolation

**无需隔离核查** —— 本轮零生产写入。生产 `cluster_person_assignments = 0`、
`person_face_embeddings = 0`、`archive_records = 0`，与 CP1 基线一致。

## 7. Calibration Schema

生产仍**无** `calibration_*` 表（C-1 未裁决 → 011 未部署）。S4-B-1 交付的
`difficulty_reason` 列、复合主键 `(id, version)`、`status CHECK` 已在 repository 中
（011 md5 `d710042e…`）并经副本预演验证，但**不在生产库内**。

## 8. Production Snapshot

**未创建。** 快照身份依赖新 `recognition_run_id` / `cluster_run_id`，二者均不存在。

## 9. Sample Size

**无法计算。** p / z / e / u 四参数均为 OWNER DECISION REQUIRED（仓库与正式文档零
冻结值，本任务不得代填）。CP11 的 N / n0 / FPC n / gross / expected effective /
annotation events 六项输出全部**待参数输入**，故不产出数字。

（机制已就绪、仅缺输入：`n0 = z²p(1−p)/e²`；`n = N·n0/(N+n0−1)`；FPC 必用；
`gross = min(ceil(n/(1−u)), N)`；`expected_effective = gross × (1−u)`；
`events = gross × annotators`。CP11.1 强调：`gross == N`（普查）时
`expected_effective ≠ n` 恒成立，必须如实报告有效分母低于理论目标。）

## 10. Remaining Preconditions

进入 `PRODUCTION-PREP COMPLETE` 所需的**全部**条件，均为 Owner 侧输入：

| # | 前置 | 当前 | 阻塞的步骤 |
|---|---|---|---|
| P-1 | **C-1** = APPROVE | 缺失 | CP2 Migration（并阻塞后续全部生产写入） |
| P-2 | **D-7** = APPROVE + 批准的 scope 档位清单 | 缺失 | CP3 Recognition（并阻塞 CP5 Clustering 及之后） |
| P-3 | **D-1** = APPROVE | 缺失 | 不阻塞本次执行，但阻塞 CP10 之后的标注阶段 |
| P-4 | **D-2** = 规程内容（4 子项） | 缺失 | 不阻塞本次执行，阻塞标注阶段启动 |
| P-5 | **D-3** = p / z / e / u（+ 可接受错误率） | 缺失 | CP11 Sample Size（唯一被本任务直接消费的参数） |
| P-6 | **C-4** = DEFER / BUILD / REJECT | 缺失 | 不阻塞 CP1–CP10；BUILD 会改变 CP10 候选视图字段 |

最小解锁组合：**P-1 + P-2 + P-5** 即可完成 CP1–CP12 的生产前置并输出 sample size；
P-3/P-4 属下一阶段（人工标注）准入；P-6 决定 CP10 是否附加 margin 字段。

## 11. Final Gate

```text
PRODUCTION-PREP BLOCKED
```

**阻塞原因**：Owner Decision 缺失（八项全部未裁决，含本任务直接依赖的 D-7 / C-1 / D-3）。
**已遵守的硬约束**：未创建备份、未执行 migration、未重跑识别、未重跑聚类、未写
Calibration、未执行抽样、未实现 margin、未自动确认/归档；未自行填写任何 Owner 裁决；
未修改任何源码（生产库全程只读连接）。

**解除条件**：Owner 在下列任一载体中给出明确裁决后重新下发本任务 —— 任务书裁决节的
占位符替换为实际值，或在 `S4_B2_Owner_Decision_Gate.md` §10 矩阵中勾选并注明数值。
届时按固定顺序执行：backup → verify backup → migration → verify schema → recognition
rerun → verify run → clustering → verify generation → verify business isolation →
verify calibration schema → snapshot → **STOP**（任一步失败即停，不自动续行）。