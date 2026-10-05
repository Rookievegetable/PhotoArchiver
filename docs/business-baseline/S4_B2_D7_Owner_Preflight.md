# S4-B-2 — D-7 / Owner Decision Preflight 报告

- 日期：2026-10-03
- 前置：S4-B-2 Entry/Preflight = **CONDITIONAL**（`S4_B2_Entry_Preflight.md`）
- 性质：**只读 + 隔离副本实验** —— 生产库零写入；识别/聚类/迁移实验全部在系统临时目录的
  生产库一致性快照上执行；临时文件已清理
- 代码基线：HEAD `27bdc64`；**零源码修改**（全部经既有公共构造器/命令装配）
- 结论：D-7 DRY-RUN = **SAFE**；S4-B-2 Next Gate = **CONDITIONAL**（§9）

---

## 1. D-7 Dry-Run Result

### 1.1 参数链与生产口径确认（CP2.1）

```text
RecognitionScopeDialog（5 档预设，默认全选）
  → RecognitionRunController.start_run(selected_ranges)
    → StartRecognitionRunCommand.selected_ranges（parameters 快照可追溯）
      → domain classify_scope(photo_face_count, selected_ranges)   ← 唯一裁决点
        → face_observations.scope_verdict（识别期一次性落定）
          → ClusterFacesService._select_participating（仅 in_selected_scope 参与聚类）
```

生产历史口径 = `face_count_ranges=["1"]`（实测：399 in-scope / 1042 out-of-scope）。
对话框默认值实为**全选**（= `FaceCountRange(1, None)` 同口径）——`["1"]` 是操作员
当时的选择，不是代码限制。

### 1.2 快照 identity（CP2.2）

```text
source:  %LOCALAPPDATA%\PhotoArchiver\photo_archiver.db（只读连接）
method:  sqlite3 backup API（一致性快照，规避 WAL 撕裂）
copy:    %TEMP%\s4b2_dryrun\snapshot.db
size:    19,296,256 bytes   md5: b7c968bd1ec7669f3ef14873fb6504df
head:    008_archive_identity_and_confidence
counts:  photos 473 / obs 1441 / clusters 36 / members 399 / cpa 0 / rr 472 / pfe 0
```

### 1.3 三轮实测（CP2.3 / CP2.4）

| 轮 | 内容 | 结果 |
|---|---|---|
| 副本迁移 | `build_sqlite_repositories` 打开快照 | **008 → 011 自动升级成功**（兼作 CP8 的 001→011 生产数据副本预演） |
| Run A 对照 | 识别 `["1"]` + 聚类 | 识别 77.0s：1441 faces / 0 unreadable / 1 no-face / **399 in-scope photos**（逐数复现生产）；聚类 0.5s：**36 簇 / 399 members**（复现代次 `5e914d83`，与生产 `1192d499` 同构） |
| Run B 放宽 | 识别五档全开 + 聚类 | 识别 71.8s：1441 faces / **1441 全部 in_selected_scope**（472 有脸照片全入域）；聚类 1.6s：**44 簇 / 1441 members** |

**业务表隔离（CP2.4）——两轮识别 + 两轮聚类全程 delta**：

```text
cluster_person_assignments: 0    recognition_results: 0
person_face_embeddings:     0    archive_records:      0
```

写入只落在管线自有表（face_observations / face_cluster_runs / face_clusters /
face_cluster_members / recognition_runs / run 快照表）。

如实记录的边界：`run_recognition_service.py:153` 的 compat 写入路径**存在**——对
in-scope 且无 rr 行的照片会补一条 pending rr。本库当前状态永不触发（唯一无 rr 照片
正是 no-face 照片，无脸即不入域），故本次实测为 0；换库重跑时该路径可能新增审核
队列行（业务预期行为，非身份状态污染）。**不构成 BLOCKED**。

### 1.4 Before / After（Run B 放宽代次 `7a028a94`）

```text
before:  photos 473 / observations 1441 / clusters 36 / members 399
after:   observations 1441（新代次，全部 in-scope）
         in-scope 1441（旧代次保持 399 不变）
         clusters 44 / members 1441
         multi-face clustered 1042（73 张照片全覆盖）
         one-photo-multiple-cluster 73 张（100%）
         max clusters/photo 36（36 人合影）
         new clusters 44（新代次；旧 36 簇代次原样保留）
```

### 1.5 判定

```text
D-7 technical feasibility: SAFE
```

依据：复现对照成立（治具可信）；放宽后聚类结构自洽（§2）；三代并存零突变；
零业务表写入；空簇 0 / 孤儿 member 0；全程 71–77s 量级，单机可执行。

---

## 2. Multi-face / Multi-cluster Result（CP3）

**样本语义的实质发现**：多脸照片不是"同人多脸"，而是**多人合影**——脸数高度规整：
43 张 × 7 脸、17 张 × 36 脸、其余 3–23 脸；全体 1441 脸聚成 44 簇，其中 32 簇
38–41 人（≈ 同一人跨 ~39 张照片复现，每人每张合影贡献一张脸）。

结构一致性核验（排除伪影的关键证据）：

| 检查 | 结果 |
|---|---|
| `members == DISTINCT photos` 的簇 | **44/44** —— 任何簇都至多从同一照片取一张脸 |
| 同一照片在同一簇贡献 ≥2 脸 | 0 例 |
| 一图多簇照片 | 73/73（100%；multi-face ⊃ 多簇，两者严格分开统计，未混同） |
| max clusters/photo | 36（= 36 人合影，逐脸不同簇，正确行为） |
| 空簇 / 孤儿 member | 0 / 0 |
| 单例簇 | 4 个，全部来自 7 人合影（LEI01315/LEI01289/LEI01394×2，det 0.80–0.89）—— 真实难例候选 |
| 合影脸 vs 人像脸 det_score | p50 0.869 vs 0.881，min 0.780 vs 0.755 —— **无低质带**，检测质量不构成标注难度来源 |
| 2 脸照片 | 0 张（多脸照片最少 3 脸） |
| 代次保持 | 生产 36/399 + Run A 36/399 + Run B 44/1441 三代并存，旧行零突变 |

注意：`multi-face clustered = 1042` 与 `one-photo-multiple-cluster = 73 张` 是两个
独立指标，本报告全程分开统计；**一人一簇跨照片**是聚类产出与 GT 标注单元
（cluster = 一名自然人的脸集合）天然对齐的结构。

---

## 3. Sample Size Semantics（CP4）

三个概念严格区分：

```text
unique calibration units（簇）   = 抽样与 GT 裁决的总体，precision 的分母单位
annotation events（标注事件）     = units × 每单元标注员数（双人制 ×2）
annotators（标注员）             = 独立自然人（≥2 独立 + 仲裁人另计）
```

例：44 units × 2 = 88 events，**不是** 88 units。

### 3.1 公式与参数（CP4.1 / CP4.2）

```text
n_eff = z² · p(1−p) / e²          （二项 precision 估计，p 保守取 0.5 为最坏情形）
有限总体修正（FPC）——本库 N 极小，必须启用：
n_fpc = n_eff / (1 + (n_eff − 1)/N)
gross unique units = ceil(n_fpc / (1 − u))     （u = 预期 undecidable 率）
annotation events  = gross × 2 + 仲裁事件（预期 ≈ gross × u）
```

参数现状：`p / z / e / u` 仓库与正式文档**均无 Owner 冻结值**（上轮已全库核实，
本轮复核不变）→ **OWNER DECISION REQUIRED（D-3）**，不从历史聊天示例推断为已批准。
`baseline/target precision` 亦无冻结值，同属 D-3。

### 3.2 示例表（示意非决定；N=44 即 Dry-Run 实测放宽后簇数）

| e | n_eff (95%, p=.5) | FPC 后 @N=44 | gross @u=20% | events（×2，不含仲裁） |
|---|---|---|---|---|
| ±10% | 97 | 31 | 39 | 78 |
| ±7% | 196 | 40 | 50 | 100 |
| ±5% | 385 | 40（→ 全域普查 44） | 44（→ 全域） | 88（→ 全域） |

**要点**：N=44 时 FPC 使 ±7% 以内的精度要求直接坍缩到**接近全量普查** ——
首轮标注大概率就是"44 簇 × 2 人"量级，抽样器的主要价值在**可复现与可审计**，
不在省标注量。这是 D-2 定规程时的重要量级事实。

### 3.3 Undecidable 语义（CP4.3）

```text
undecidable 不进入 precision 分母（S4-B-1 冻结指标定义，SQL CHECK 双保险已在库）。
effective labeled units = 完成裁决且非 undecidable 的单元（precision 分母）
gross annotated units   = 招入标注的单元总数（×2 为 events）
二者由 u 联系：effective = gross × (1 − u)
禁止把 N_total = n/(1−u)*2 当作"units 数"——×2 只发生在 events 层。
```

---

## 4. Margin Decision（CP5）

事实基线（严格区分两个 embedding 域）：

- `FaceObservation.embedding`：检测管线产物，**1042 条合影脸已在库**，与业务无关；
- `person_face_embeddings`：Business Person Sample 数据（确认/指派时写入），当前 0 行；
- `CosinePersonMatcher.match` 只返回单一 best —— **top1−top2 能力不存在**，不得声称可算。

### 方案 A —— 首轮不做 margin（推荐：defer）

优点：不触碰 Business sample writer；不引入新模型语义；样本量事实（§3.2）表明首轮
接近普查，margin 分层的"省样本"价值本来就小；先建立基础 GT。
代价：首轮无 margin 分层轴（协议记为显式降级项，非缺省）。

### 方案 B —— 新增独立只读候选计算（可行性：确认，本轮不实现）

```text
FaceObservation.embedding（或簇心）
  → 独立候选计算（纯余弦，零业务表读）
    → top1 / top2 → margin
```

可行性证据：余弦原语为纯 Python（`ai/similarity_matcher._dot/_norm`），可独立复用；
簇心 margin 只依赖 face_observations，**不写 person_face_embeddings、不写 Assignment、
不触发 Archive**。person-质心方案则受冷启动约束（0 行样本）。
结论：**B 技术可行且业务隔离可保证，留作第二轮增强；首轮 defer**。

---

## 5. Sampling Protocol（CP6 —— 冻结）

```text
protocol = s4b1-sampling-v1
seed     = 20260101（任务书规格；仓库代码/文档零落点 —— 由未来 executor 固化入库）
层内选择键 = SHA-256( seed_round ‖ cluster_id ) 升序取前 k
seed_round = SHA-256( 20260101 ‖ round_index )
```

- 明确 **`cluster_id ASC` 不是 random sampling**（UUID 序为冻结随机且与轮次无关）；
- 中立性（CP6.1）：`det_score / quality_score / assignment / recognition_results /
  top1 / top2 / margin` 一律不得直接决定入选；只允许 **先分层 → hash 键层内排序 → 取 k**；
- executor 实现要求：population 快照 + seed_round + 算法版本写入
  `calibration_datasets.notes/params`；本阶段不实现。

## 6. Leakage Policy（CP7 —— 冻结）

```text
same person_id    → 同一 evaluation split（跨数据集不重复）
same photo_id     → 同一 evaluation split
same content_hash → 同一 evaluation split（metadata_content_hash，473/473 已填充）
folder split      = UNAVAILABLE（单一有效 folder），不得伪装可执行
near-duplicate    = 无感知哈希能力，不新增算法，记录为限制
```

Dry-Run 补充事实：单代次内 44/44 簇"每照片至多一脸"，代次内 photo 泄漏结构上极低；
**跨代次**不同 cluster run 对同一批 observation 重新成簇 —— 跨数据集版本必须按
photo_id（并按 GT 出现的 person_id）去重，泄漏规则按上表执行。

## 7. Owner Decision Matrix（CP1）

| 决策 | 当前状态 | 不做的后果 | 做了以后 |
|---|---|---|---|
| **D-7** | 未决；Dry-Run 已证 **SAFE**（§1） | 多脸/多簇样本保持 0 | 44 簇全域样本立即可得（识别 72s + 聚类 2s） |
| **C-1 / migration 011** | 未决；已在生产数据副本上预演通过（008→011） | 生产无法落 Calibration | GT 数据层可部署 |
| **D-1** | 未决 | 无真人标注 | 有校准真值 |
| **D-2** | 未决；量级事实：N=44 时接近普查（§3.2） | 无可审计规程 | 双人制+仲裁成文 |
| **D-3** | 未决（p/z/e/u 无冻结值） | 无法定样本量 | 风险边界量化 |
| **D-4** | 未决（当前系统零自动确认） | 自动确认无法设计 | 适用范围可限界 |
| **D-5** | 未决 | 闭环不成立 | 自动确认后行为可定义 |
| **C-4 / margin** | 未决；本报告推荐首轮 defer（§4） | 首轮无 margin 分层（已声明降级） | 二轮可做簇心 margin |

## 8. Production Deployment Preconditions（CP8 —— 只读清单，不执行）

```text
C-1 production migration prerequisites
├─ 0. 前置：运行代码 = HEAD；Owner 批准窗口；应用关闭（SQLite 单写者）
├─ 1. backup：文件冷拷贝（19.3MB 量级）+ integrity_check；主回滚手段
├─ 2. migration 001→011：✅ 已在生产数据副本上预演通过（本次 Dry-Run 附带完成）
├─ 3. 009/010/011 依赖：009 纯增量（472 行 assignment_id=NULL 不动）；
│     010 重建 cpa（0 行，legacy_alter_table=ON 护 FK）；011 建 3 空表（无回填）
├─ 4. calibration 初始化：零种子数据需求
├─ 5. rollback：停应用 → 备份文件还原（主）；alembic downgrade（次，已有回归测试）
├─ 6. legacy 472：结构零影响，仍为审核队列内容
├─ 7. downtime：备份秒级 + 迁移秒级 + 核验分钟级 → 停机窗口 ≈ 5 分钟内
└─ 8. post-migration 核验：head=011；calibration 三表存在；
      photos/obs/clusters/members/rr 逐数与迁移前一致；rr 472 行原样
```

## 9. Legacy 472 Pending（CP9）

复核不变：`recognition_results pending = 472`（= 全量）。**Calibration 零读取**
（协议 9 方法与 cluster_results_service 均不涉 rr）；UI 可见性 = 它们就是审核中心
队列内容（业务侧）；confirmation-bias 通路 = 不存在（标注界面不展示 rr）；
处置 = 业务链 D-1 的 Owner 决策，calibration 侧无动作；不删除不修改。

---

## 10. Final Decision Table（CP10）

| Item | Result |
|---|---|
| D-7 dry-run | **SAFE**（对照复现 + 放宽 44 簇 + 零业务写入 + 三代并存） |
| Multi-face samples | **available**（D-7 执行后：1042 faces / 73 photos，实测） |
| Multi-cluster samples | **available**（D-7 执行后：73 photos / max 36 簇，实测） |
| Migration 011 | owner approval required（副本预演已通过） |
| Annotation investment | owner approval required |
| Sample size | **determined（公式+FPC 机制）；数值 = owner decision** |
| Margin | **defer**（首轮；方案 B 可行性已确认，二轮实施） |
| Sampling protocol | **frozen**（s4b1-sampling-v1 + SHA-256 键语义） |
| Legacy 472 | isolated（calibration 零读取；处置归业务链 Owner） |
| Production execution | **prohibited in this task**（全程未触碰生产库写路径） |

## 11. S4-B-2 Next Gate

```text
S4-B-2 NEXT GATE: CONDITIONAL
```

技术侧已全部就绪（Dry-Run SAFE、迁移预演通过、样本量机制完备、协议冻结）；
剩余条件全部为 Owner 裁决，裁决后即可进入"样本准备执行阶段"：

1. **C-1**：批准 migration 011 部署窗口（清单 §8，停机 ≈5 分钟）；
2. **C-2/D-7**：批准生产放宽重跑（识别 ~75s + 聚类 ~2s，预期产出 44 簇/1441 members，
   已实测无业务副作用）；
3. **C-3/D-1+D-2+D-3**：标注投入、双人/仲裁规程、p/z/e/u 四参数；
4. **C-4**：接受 margin 首轮 defer（或改选二轮提前）。

Hard Stop 已遵守：生产迁移/重跑/聚类/标注/抽样/pfe 写入/自动确认/自动归档 —— 全部未执行；
临时目录（snapshot.db 及中间产物）已清理。
