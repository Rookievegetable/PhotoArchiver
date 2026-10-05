# S4-B-1 Ground Truth 标注体系 — 最终验收报告（Checkpoint 10）

- 日期：2026-10-03
- 验收对象：S4-B-1 Ground Truth 校准标注体系（独立于业务 Assignment 链）
- 验收模式：**只读验收** —— 除本报告文件外零文件修改；所有探针在临时数据库上运行，生产库仅只读连接
- 代码基线：HEAD `27bdc64998f5a2eaece8bf561c5957ab8e8d7e80`（main，9 commits ahead of origin）
- 结论：**S4-B-1-COMPLETE-WITH-LIMITATIONS**（交付范围全部通过；归档限制见 §7，均属 Owner 待决事项或后续阶段范围，不阻塞本阶段关闭）

---

## 1. 验收基线（CP10-A）

### 1.1 迁移文件指纹（与 CP3/4 完成时逐字节一致）

| 迁移 | md5 |
|---|---|
| 001_initial_v4 | `8977a73208f4a58d506f21f56ae5ce1e` |
| 002_split_create_ddl | `5b97e1e9bdadf9d49e56ccb912f8f139` |
| 003_import_batches_and_roster | `9bccbfa7d835937ee4e31fe59c2840aa` |
| 004_recognition_runs_and_observations | `b8b4aad4b6c975a05ffe5a448292b994` |
| 005_recognition_run_error_count | `f7128ce01b7fde31322de4e6d061e00c` |
| 006_face_clusters | `c267068e7ce1ff377ad5ee664b092b0c` |
| 007_assignments_and_person_samples | `364ccbb90c050151c2ff70daadc68a00` |
| 008_archive_identity_and_confidence | `e3a469d3714ba61c264a0180f24de0de` |
| 009_projection_ownership | `235fb3cd02ac36f886ca0c6af60d3fed` |
| 010_assignment_source_review | `ef79b466aaec59fda5a2ef6a9edaa56b` |
| **011_calibration_annotations** | **`d710042e138b9a0f1126e5b0580617b5`** |

### 1.2 生产库状态（只读核实，验收前后一致）

- 路径：`%LOCALAPPDATA%\PhotoArchiver\photo_archiver.db`
- `alembic_version` = **`008_archive_identity_and_confidence`** —— 009/010/011 未应用（Owner 决策待定，非缺陷）
- `calibration_*` 三表：**不存在**（与未迁移一致，生产零污染）
- `recognition_results.assignment_id` 列：**不存在**（同理）

### 1.3 工作树

- `git status --porcelain` 53 项（验收前后数量一致，唯一新增为本报告文件）
- S1/S1-F/S4-B-1 全部变更均未提交，等待 Owner 统一推送（见记忆库待办）

---

## 2. 行为验证探针（临时库，全部通过）

### 2.1 CP10-B — Domain 构造校验（9 类拒绝全数命中）

`CalibrationAnnotation` / `CalibrationGroundTruth` / `CalibrationDataset` 的
`validate_verdict_payload()` 与 `__post_init__` 不变量：
person 缺 person_id 拒、undecidable 缺 difficulty_reason 拒、undecidable 带 person_id 拒、
out_of_roster 带任一载荷拒、标注人数 <2 拒、source_annotation_ids 空拒、
agreed/adjudicated 互斥拒、dataset usable > cluster 拒、非 frozen status 拒。

### 2.2 CP10-D — 冻结数据集真实 SQLite 行为（D1–D4）

| 探针 | 结果 |
|---|---|
| D1 对已冻结 v1 重复 freeze | **REJECTED**（`UNIQUE constraint failed: calibration_datasets.id, version`），v1 行逐列不变 |
| D2 同 (id, v1) 二次写入 | REJECTED —— 复合主键 `(id, version)` 生效（B-2 修复落库） |
| D3 (id,v1)+(id,v2) 共存 | v1 行不变，v2 行存在 —— 版本共存成立，新版本是新行 |
| D4 `dataset_truth(id, 'v1')` vs `'v2'` | 按 version 精确隔离，互不串集 |

附带观察（归档为 §7-L5）：`add_ground_truth` 为纯 append-only，**(cluster_id, dataset_id,
dataset_version) 无唯一约束** —— 仓储层不做业务裁决，"每次 freeze 每 cluster 恰一行 GT"
由服务层纪律保证；绕过服务的直写不受约束（与"仓储是无知存储"的架构决策一致）。

### 2.3 CP10-E — `get_dataset(id, version=None)` 最新版语义（双适配器对等）

创建序 **v10 → v8 → v9**（字典序与创建序反向）：

| 适配器 | version=None | 显式命中 | 未命中 |
|---|---|---|---|
| SQLite | `v9`（最后创建者） | v10/v8/v9 各自精确命中 | `'v7'` → None |
| InMemory | `v9` | 同上 | 同上 |

字典序（v10 < v9 < v8）未泄漏进 latest 判定；两适配器语义逐项一致。
已知可接受前提：依赖 `created_at` 单调（服务层 `_next_timestamp` 保证），不引入 sequence 字段。

### 2.4 CP10-F — SQL 级 CHECK 强制 + 双向 import 隔离

直连 SQLite 插入非法行（绕过全部 Domain/Service）：

| 非法行 | 结果 |
|---|---|
| `verdict='person'`, `person_id=NULL` | REJECTED —— `CHECK (verdict='person' AND person_id IS NOT NULL) OR …` |
| `verdict='out_of_roster'`, person_id 绑定真实 people 行 | REJECTED —— 同上 CHECK 第二分支 |
| `verdict='undecidable'`, `difficulty_reason=NULL` | REJECTED —— `CHECK (verdict <> 'undecidable' OR difficulty_reason IS NOT NULL)`（**B-1 修复在 SQL 层生效**） |
| `verdict='bogus'` | REJECTED —— `CHECK verdict IN ('person','out_of_roster','undecidable')` |

import 双向隔离（grep 全量核实）：
- 5 个 calibration 模块（entity/protocol/service/SQLite repo/in-memory repo）对业务层 import = **0**
- 4 个业务服务（projection_reconciler / identity_decision / pairing_workbench / review_recognition）对 calibration 的引用 = **0**

---

## 3. Schema 落地摘要（migration 011）

三表均 `CREATE TABLE IF NOT EXISTS`，downgrade 全部 DROP：

1. **calibration_annotations** —— 原始标注；`role IN (independent, adjudication)`；FK
   `cluster_id → face_clusters ON DELETE CASCADE`、`person_id → people ON DELETE SET NULL`；
   verdict 词表 CHECK + person-payload CHECK + difficulty CHECK
2. **calibration_ground_truth** —— 最终真值；`resolution IN (agreed, adjudicated)`；
   **B-1 修复**：`difficulty_reason TEXT` 列 + 两条 CHECK（undecidable 必须带原因、
   非 undecidable 不得带原因），保证难例分类贯通 Annotation → GT → Dataset
3. **calibration_datasets** —— **B-2 修复**：`PRIMARY KEY (id, version)` 复合主键
   （单列主键会让同 id 多版本静默覆盖）；`status CHECK IN ('frozen')`（draft 不落库）
   ；冗余 `idx_calib_dataset_version` 已随复合主键移除

---

## 4. 31 项验收矩阵

图例：✅ = 本轮或既有测试/探针直接证实。证据列中 `…e2e` 指
`tests/integration/test_s4b1_calibration_lifecycle_e2e.py`（20 例），
`…parity` 指 `tests/integration/test_calibration_repository_parity.py`（38 例），
`…domain` / `…svc` / `…panel` 指对应 unit 测试文件（45/23/22 例）。

### A. Domain 层（7 项）

| # | 项 | 证据 |
|---|---|---|
| 1 | Annotation 实体冻结不可变，role 词表 independent/adjudication | …domain |
| 2 | person 裁决必须带 person_id（缺失拒绝） | …domain + CP10-F SQL 级 |
| 3 | undecidable 必须带 difficulty_reason 且禁 person_id | …domain + CP10-F SQL 级 |
| 4 | out_of_roster 不得携带 person_id / difficulty_reason | …domain + CP10-F SQL 级 |
| 5 | GT 构造：annotator_count ≥ 2、source_annotation_ids 非空 | …domain |
| 6 | agreed 与 adjudicated 互斥 | …domain |
| 7 | Dataset：status 仅 frozen、usable ≤ cluster、复合标识 (id, version) | …domain（注：usable≤cluster 为实体级约束，DDL 无对应 CHECK，见 §7-L6） |

### B. Service 层（7 项）

| # | 项 | 证据 |
|---|---|---|
| 8 | 盲评成立：annotate 仅经 `find_latest_own_annotation` 读自己，方法级隔离 | …svc + …e2e |
| 9 | agreement：≥2 名不同标注员同裁决 → agreed GT | …svc + …e2e |
| 10 | 仲裁优先于一致；多条仲裁取**最新**（`adjudications[-1]`） | …svc（本轮复核确认修复在位） |
| 11 | 未达成一致且无仲裁 → `resolve_ground_truth` 返回 None，不产生 GT 行 | …svc + …e2e |
| 12 | `_next_timestamp` 严格单调（微秒级递增），created_at 无同刻竞态 | …svc |
| 13 | freeze：以已解析真值快照写入 GT，draft 数据集不落库 | …svc + SQLite add_dataset 拒 draft |
| 14 | `dataset_truth` 按 (dataset_id, version) 精确隔离 | CP10-D D4 + …e2e |

### C. 仓储协议与双适配器（4 项）

| # | 项 | 证据 |
|---|---|---|
| 15 | 协议仅 9 方法，显式不含任何业务仓储能力 | protocol 文件审查 |
| 16 | in-memory ↔ SQLite 排序/latest 语义逐项对等 | …parity（38 例） |
| 17 | `get_dataset(id, version=None)` = 最近创建版，字典序不泄漏 | CP10-E（双适配器） |
| 18 | draft dataset 双侧均拒收 | …parity + …svc |

### D. SQLite 持久化与迁移（6 项）

| # | 项 | 证据 |
|---|---|---|
| 19 | 011 建三表，FK 挂 face_clusters/people（CASCADE / SET NULL） | DDL 审查 + 迁移回归测试 |
| 20 | verdict 词表 CHECK 在 SQL 层强制 | CP10-F |
| 21 | person-payload CHECK 在 SQL 层强制（正反两分支） | CP10-F（含真实 people FK 行） |
| 22 | difficulty_reason 两条 CHECK 在 SQL 层强制（B-1） | CP10-F |
| 23 | 复合主键 (id, version)（B-2）：重复 v1 拒、v1+v2 共存 | CP10-D D2/D3 |
| 24 | 冻结后经公开 API 不可变；GT append-only | CP10-D D1 |

### E. 与业务链隔离（3 项）

| # | 项 | 证据 |
|---|---|---|
| 25 | calibration 五模块对业务层 import = 0 | CP10-F grep |
| 26 | 业务四服务对 calibration 反向引用 = 0 | CP10-F grep |
| 27 | 标注写入不触碰 assignments / projections / recognition_results | 架构审查 + E2E 全链无交叉断言 |

### F. 表现层（2 项）

| # | 项 | 证据 |
|---|---|---|
| 28 | 标注面板：三态裁决单选 + Domain 词表难度下拉 + 提交/状态反馈 | …panel（22 例） |
| 29 | cluster_results_dialog 仅注入 service 时嵌入面板；只读模式行为不变 | …panel + 既有对话测试全绿 |

### G. 质量门与运维（2 项）

| # | 项 | 证据 |
|---|---|---|
| 30 | pytest 1643 passed / 8 skipped / 0 failed；ruff 全绿；mypy 272 文件零问题 | 本轮复跑（270s） |
| 31 | 生产库零污染：head=008、无 calibration 表、无 assignment_id 列 | §1.2 只读核实 |

---

## 5. 五个核心问题（Q1–Q5）

**Q1：标注体系与业务 Assignment 链是否完全隔离？**
是，且是双向的。calibration 五模块对业务层零 import；业务四服务对 calibration 零反向
引用（矩阵 #25/#26）。标注表的外键只指向 `face_clusters`（只读引用簇身份）与 `people`，
从不指向 `cluster_person_assignments` / `recognition_results`；任何标注写入都不会进入
投影或裁决链（#27）。Ground Truth 完全不参与业务身份判定 —— 它只服务评估。

**Q2：盲评是否成立——标注员是否看不到他人标注？**
成立。读取路径在方法级分离：标注员会话只能走 `find_latest_own_annotation(cluster, annotator)`，
`list_annotations(cluster)` 仅供协议/服务内聚合使用；service 测试与 E2E 均断言了
"提交前看不到他人行、自己的重复提交返回已有行"。仲裁人走显式 role=adjudication 通道，
不属于盲评破坏。

**Q3：冻结数据集的不可变与版本共存是否在真实 SQLite 上成立？**
成立（CP10-D）。复合主键 `(id, version)` 拒绝同版本重复冻结、允许多版本共存；
对已冻结版本的任何公开 API 改写路径均被拒；`dataset_truth` 按 version 精确隔离。
`version=None` 的 latest 语义按创建时间取最新，字典序不干扰（CP10-E，双适配器对等）。

**Q4：difficulty_reason（难例分类）是否贯通全链？**
是。B-1 修复后：实体携带并校验（undecidable 必填、其他禁填）→ GT 继承自标注 →
SQL 层两条 CHECK 兜底（绕过 Domain 直插也拒）→ `dataset_truth` 原样返回。三处
CHECK 探针全部 REJECTED（CP10-F）。

**Q5：生产库是否安全、升级是否可控？**
生产库本轮只读核实未被触碰（head=008，无任何 S1/B-1 结构）。011 的 downgrade
完整删除三表（迁移回归测试覆盖 upgrade/downgrade 往返）；011 仅新增独立表，
不触碰既有表结构，升级风险面极小。**应用 009–011 属 Owner 决策**，本验收不代行。

---

## 6. 质量门（验收时复跑）

| 门 | 结果 |
|---|---|
| pytest（全量） | **1643 passed / 8 skipped / 0 failed**（270.04s）—— 与 CP3/4 完成时完全一致 |
| ruff | All checks passed |
| mypy（src） | Success: no issues found in 272 source files |
| 迁移指纹 | 001–011 与基线逐字节一致（§1.1） |

---

## 7. 归档限制（不阻塞关闭，逐项留痕）

| # | 限制 | 归属 |
|---|---|---|
| L1 | 生产库停在 008；009–011 未应用（生产无 calibration 表、无 assignment_id 列） | Owner 决策待定 |
| L2 | 仲裁（adjudication）暂无 UI：面板覆盖独立标注；仲裁可经服务 API 完成，待身份体系接入后补 UI | S4-B-2+ 范围 |
| L3 | 抽样执行器（sampling executor）未实施：冻结数据集尚无消费方，seed 未参与实际抽样 | S4-B-2 范围（Owner 已明确本次不做） |
| L4 | D-1：472 条 legacy pending recognition 行处置待 Owner 裁决 —— 影响未来 GT 抽样全域，不影响本体系正确性 | 业务链 Owner 决策 |
| L5 | `add_ground_truth` 对 (cluster, dataset, version) 无唯一约束：仓储无知存储，一行/簇纪律由服务层保证；绕过服务直写不受约束（CP10-D D1 附加观察） | 架构已知取舍 |
| L6 | `usable_count ≤ cluster_count` 仅实体级强制，DDL 无对应 CHECK（datasets 表仅 service 写入，风险低） | 防御纵深缺口（低） |
| L7 | `version=None` latest 语义依赖 created_at 单调性（服务层 `_next_timestamp` 保证），未引入 sequence 字段 | 已记录的可接受前提 |

---

## 8. 最终门

```
S4-B-1-COMPLETE-WITH-LIMITATIONS
```

依据：31/31 验收项通过，五个核心问题全部肯定作答，三项质量门全绿且与阶段中基线
完全一致；七项归档限制中无一项属于本阶段交付缺陷 —— L1/L4 为 Owner 待决，
L2/L3 为显式后置范围，L5/L6/L7 为已记录的架构取舍。S4-B-1 阶段关闭。

**边界声明**：本验收不进入 S4-B-2，不执行真实人工标注，不实施 sampling executor，
不实施自动确认。
