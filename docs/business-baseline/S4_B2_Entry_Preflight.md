# S4-B-2 Entry / Preflight — Ground Truth 校准进入前置复核与样本获取方案

- 日期：2026-10-03
- 前置状态：S4-B-1 = **COMPLETE-WITH-LIMITATIONS**（报告：`S4_B1_Ground_Truth_Annotation_Readiness.md`）
- 性质：**只读前置复核** —— 零生产写入、零迁移执行、零识别重跑、零标注、零 sampling executor、零 margin 计算
- 代码基线：HEAD `27bdc64`（main）
- 结论：**S4-B-2 ENTRY = CONDITIONAL**（§8）

---

## 1. S4-B-2 Entry Baseline（CP0 / CP1）

### 1.1 生产库只读实测（2026-10-03，`%LOCALAPPDATA%\PhotoArchiver\photo_archiver.db`）

| 项 | 实测值 | 与任务书数字 |
|---|---|---|
| alembic head | `008_archive_identity_and_confidence` | 一致 |
| migration 011 在 repository | 存在（md5 `d710042e…`，与 S4-B-1 验收指纹一致） | 一致 |
| production calibration tables | **不存在** | 一致 |
| photos | 473 | 一致 |
| observations | 1441（in_selected_scope 399 + out_of_selected_scope 1042） | 一致 |
| clusters / cluster_members | 36 / 399 | 一致 |
| single-face clustered | 399 | 一致 |
| multi-face photos | 73 | 一致 |
| multi-face observations | 1042 | 一致 |
| multi-face clustered | **0** | 一致 |
| max clusters/photo | 1 | 一致 |
| cluster_person_assignments | **0** | 一致 |
| person_face_embeddings | **0** | 一致 |
| recognition_results pending | **472**（= rr 全量，无其他状态行） | 一致 |
| people | 546（补充事实） | — |

**任务书数字与当前事实零漂移，全部沿用。**

### 1.2 Run 拓扑（样本获取路径的关键事实）

- **单一识别 run** `dafcf284…` 持有全部 1441 条 observation（399 in-scope + 1042 out-of-scope）
- **单一聚类 run** `1192d499…`（`cosine-centroid-completelink-v1`，2026-10-01）→ 36 簇
- **1042 条多脸 observation 已全部带 embedding**（`length(embedding)>10` = 1042/1042）——
  检测与向量提取早已完成，缺的只是 scope 门与聚类参与

### 1.3 Entry Conditions（CP1）

| # | 条件 | 判定 |
|---|---|---|
| E1 | Ground Truth 数据层：Domain / Repository / SQLite / UI / `dataset_truth` | **全部 available**（S4-B-1 CP10 验收 31/31） |
| E2 | production migration 011 = NOT APPLIED | **确认**。记录：生产标注若要真正执行，必须先完成 Owner 批准的 migration 部署（§6）。不执行 |
| E3 | multi-face clustered = 0 | **确认** |
| E4 | one-photo-multiple-cluster = 0 | **确认** |
| E5 | person_face_embeddings = 0 → candidate margin = NOT COMPUTABLE | **确认** |

---

## 2. Missing Data Sources

```text
multi-face:                UNAVAILABLE（聚类态）—— 但 1042 条检测+embedding 已在库，
                           仅 scope_verdict='out_of_selected_scope' 挡在聚类门外
one-photo-multiple-cluster: UNAVAILABLE —— 算法本身支持（§3），缺多脸输入所以自然为 0
margin:                    NOT COMPUTABLE —— 全代码无 top1/top2 计算点（§3）
difficulty:                N/A —— difficulty_reason 是标注产物（undecidable 的输出），
                           不是首轮抽样的输入轴；第二轮起可用于再分层
folder:                    NOT EXECUTABLE —— DISTINCT folder_id = 1（单一有效 folder）
```

不得为分层平衡制造样本（CP4.1 记录在案）。

---

## 3. Acquisition Path（CP2 / CP7 静态取证）

### 3.1 multi-face acquisition：**AVAILABLE**（Owner 决策门 = D-7）

`face_count_ranges` 真实调用链（静态追踪）：

```text
presentation/views/recognition_scope_dialog.py
  5 档预设 FaceCountRange(1,1)/(2,3)/(4,5)/(6,10)/(11,None)，默认全选
    ↓ start_run(selected_ranges, …)
presentation/controllers/recognition_run_controller.py:103
  StartRecognitionRunCommand.parameters["face_count_ranges"] 快照（可追溯）
    ↓
application/services/run_recognition_service.py:144
  domain classify_scope(photo_face_count, selected_ranges)   ← 唯一裁决点
    → face_observations.scope_verdict（识别期一次性落定）
    ↓
application/services/cluster_faces_service.py:230 _select_participating
  仅 scope_verdict == in_selected_scope 且 embedding 非空者参与聚类
```

- **默认值**：UI 对话框默认全选（与命令默认 `FaceCountRange(1, None)` 同口径）；生产历史
  运行实际只勾了 `[1-1]`（399/1441 in-scope）——`["1"]` 是操作员选择，不是硬编码。
- **放宽能否让多脸进聚类**：能。新识别运行对多脸照片重新 classify_scope → in_selected_scope
  → 下一步聚类即收。**必须重跑识别**：scope_verdict 只在识别期落定，且控制器契约
  "reruns re-detect everything"；现无 scope_verdict 回填能力。
- **对已有单脸结果影响**：零。rerun = 新代次（新 recognition_run + 新 cluster_run），
  36 簇 / 399 members 原样保留（Stage D 冻结行为：history kept）。
- **业务触发**：无。聚类只写 face_clusters/members；Assignment 仅由 review/pairing 流产生；
  归档是手动任务。compat 兼容行几乎不新增（472 张照片已有 rr 行，仅 1 张无 rr 照片
  若 in-scope 会补一行 pending）。
- **person_face_embeddings**：不写。writer 仅两处（§3.3），均需人工确认动作。

### 3.2 multi-cluster acquisition（一图多簇）：**AVAILABLE**（算法天然支持）

代码证据（`domain/services/face_clustering.py`）：

- 聚类输入 `ClusteringItem(observation_id, quality_score)` —— **不含 photo_id**，
  全算法路径（`_form_candidates` 质心余弦贪心 → `_merge_candidates` complete-linkage）
  纯在 embedding 空间运作，**没有任何"同照片不得分簇"约束**；
- 持久层 `face_cluster_members` 亦无同照片跨簇限制（Stage D 审计 P2-b 已runtime证明
  跨簇重复可插入）。

结论：**algorithm supports it** —— 一旦多脸 observation 参与聚类，同一照片的不同人脸
自然落入不同簇（一图多簇将作为聚类产物自然产生），无需任何代码修改，也不修改 clustering。

### 3.3 margin acquisition（candidate top1/top2）：**POSSIBLE（需新的 calibration 侧组件）**

writer 与计算路径事实：

1. **谁写 `person_face_embeddings`**：`SQLitePersonFaceSampleRepository.add_samples`
   （sqlite_cluster_assignment_repository.py:212）。
2. **什么时候写**：仅两个调用方 —— `identity_decision_service.py:343`（review 确认存样）
   与 `pairing_workbench_service.py:400`（工作台指派存样）。**两者都是业务 Assignment 流**。
3. **前置数据**：已确认归属的 observation（含 embedding）。
4. **写入是否触发业务 Assignment**：写入本身是 Assignment 的**伴生产物**，方向相反 ——
   不存在"写 embedding 导致 Assignment"的路径。
5. **是否存在仅用于 calibration 的安全计算路径**：存在雏形。`CosinePersonMatcher`
   （ai/similarity_matcher.py）是纯 Python 余弦计算（`_dot/_norm`），数学原语可独立复用；
   但其 `match()` **只返回单一 best**（`similarity >= best_confidence` 保留最大者），
   **top1/top2 margin 在任何代码中都不存在**。两条未来设计选项（均不绑定业务写入）：
   - person-质心 margin：依赖 person_face_embeddings —— 当前 0 行，**先有确认才有样本**（冷启动依赖业务流）；
   - **cluster-质心 margin**：直接对 face_observations.embedding 做簇心间 top1/top2 余弦，
     零业务表读取，零写入 —— calibration 安全路径，推荐为未来实现方向（本阶段不实现）。
6. **是否已有测试证明候选 top1/top2**：**无** —— 无任何 top1/top2 测试（该能力不存在）。

判定：margin 获取**不被架构阻断**（可独立于业务 Assignment 构建），但当前
**NOT COMPUTABLE**（无能力、无样本），实现属后续阶段。

---

## 4. Sampling Plan（CP3 / CP4 / CP4.2）

### 4.1 抽样单元与分层（AVAILABLE / UNAVAILABLE / NOT COMPUTABLE 严格区分）

抽样单元 = **FaceCluster**（GT 的裁决粒度即簇）。

| 分层轴 | 状态 | 说明 |
|---|---|---|
| 单脸簇 | **AVAILABLE** | 当前全域 = 36 簇全部单脸派生 |
| 多脸簇 | UNAVAILABLE（现） | D-7 重跑后产生 |
| 一图多簇 | UNAVAILABLE（现） | 随多脸聚类自然产生 |
| cluster size | **AVAILABLE** | 成员数已存储，可分层 |
| quality | **AVAILABLE** | det_score / quality_score 已存储（Stage F：p50≈0.872，无低质带） |
| margin | **NOT COMPUTABLE** | §3.3 |
| difficulty | N/A | 标注产物，第二轮起可作再分层轴 |

### 4.2 首轮样本规模（CP3）

**仓库内统计规则盘点结果**：全库（docs/ src/ .ai/）无任何 Wilson / 置信水平 / 目标错误率 /
允许误差的已冻结数值（grep 全量核实；唯一"95%"命中为健康检查审计分，无关）。
S4-B-1 已冻结并落库的只有**指标定义**：precision 的分母排除 `undecidable`
（总标注数 ≠ precision 有效分母），GT 仅经 ≥2 人一致或仲裁产生。

三个风险输入按任务书规则处理：

```text
目标错误自动确认率：  OWNER DECISION REQUIRED（D-3）
置信水平：            OWNER DECISION REQUIRED（D-3）
允许误差：            OWNER DECISION REQUIRED（D-3）
```

**计算机制**（不重新发明，标准 Wilson 下界 / 正态近似给出，供 Owner 填入参数即算）：

```text
基础样本量（precision 有效分母）：
    n = z² · p(1−p) / e²        （p 取保守 0.5 为最坏情形）
考虑 undecidable 后的有效样本量：
    n_eff = n                   （undecidable 不进分母，n 本身就是"有效裁决数"）
建议人工标注总量：
    N_total = n / (1 − u)       （u = 预期 undecidable 率，Owner/首轮实测后校准）
    双人制度 ×2，仲裁另计
```

**示例表（纯示例，非决定，仅供 Owner 量级感知）**：

| e（允许误差） | z=1.96（95%）n | u=20% 时 N_total（含双人） |
|---|---|---|
| ±10% | 97 | 97/0.8 ×2 ≈ 243 |
| ±7% | 196 | 196/0.8 ×2 ≈ 490 |
| ±5% | 385 | 385/0.8 ×2 ≈ 963 |

### 4.3 抽样协议与 seed 语义（CP4.2 —— 本阶段裁决）

**seed 事实**：`sampling seed = 20260101` 在仓库内**零代码、零文档落点**（全库 grep 证实），
仅存在于 S4-B-1 任务书历史 —— 是规格，不是实现。

**裁决：采用方案 A（seed 参与确定性伪随机抽样），实现形态为 hash-based 排序**：

```text
层内选择序 = SHA-256( seed_round ‖ cluster_id ) 升序，取前 k
seed_round = SHA-256( 20260101 ‖ round_index )   （每轮独立置换）
```

技术依据：
- **弃 Python `random`**：`random.sample` 实现跨 CPython 版本有过变更，可复现性绑定
  解释器版本 —— 不可接受；SHA-256 平台无关、逐字节可审计。
- **方案 B（deterministic cluster_id ordering）的缺陷**：a) 裸 UUID 序是"冻结的随机"
  —— 第二轮仍取同一前缀，只能靠排除清单硬剔，轮次扩展性差；b) 若误用簇序数（ordinal）
  排序则**违反中立性** —— 簇持久序跟随确定性输入序（det_score 降序），ordinal 与检测
  质量相关。hash(seed‖id) 每轮给全量一次新的、与模型表现无关的均匀置换，两缺陷皆免。
- **中立性合规**：选择键只取 cluster_id 与 seed，**不读 cluster_person_assignments /
  recognition_results**（CP4.3 硬规则），不按分数、不按 Top-1、不按预测对错、不按已有
  Assignment。

**后续实现要求**（本阶段不实现 executor）：抽样执行器须把 population 快照、
seed_round、选择算法版本写入 `calibration_datasets.notes/params`；逐层配额由
Owner 在 D-2 中给定；leakage 排除（§4.4）在选择前生效。

### 4.4 Leakage Policy（CP5 —— 最终冻结）

| 维度 | 冻结规则 | 当前可执行性 |
|---|---|---|
| Person | 同一 `person_id` 不得跨训练/验证或不同校准用途数据集重复 | 规则冻结（person 归属来自 GT verdict，数据集登记 cluster_ids 可校验） |
| Photo | 同一 `photo_id` 不得跨不同校准数据集重复 | **可执行**（photos.id 全局唯一） |
| Exact duplicate | 相同 `metadata_content_hash` 不得跨数据集 | **可执行**（473/473 行已填充，列已核实） |
| Folder | folder 级分组 | **当前不可执行** —— DISTINCT folder_id = 1，单一有效 folder |
| Near duplicate | 感知哈希 | 项目无此能力，**不新增算法**，记录为限制 |

---

## 5. Owner Decision Matrix（CP6）

| 决策 | 当前事实 | 需要决定 |
|---|---|---|
| **D-1** | Ground Truth 人工投入未裁决；472 条 legacy pending 处置待决（§7） | 是否投入人工标注 |
| **D-2** | 样本量三参数无 Owner 数值（§4.2）；双人制度与仲裁规程未定 | 标注规模 / 双人制度 / 仲裁规程 / 分层配额 |
| **D-3** | 无任何已冻结的错误率容忍参数 | acceptable false-auto-confirm rate + 置信水平 + 允许误差 |
| **D-4** | 自动确认范围无裁决（当前系统**零自动确认**——全部身份经人工确认） | 后续自动确认如何限界 |
| **D-5** | 归档当前均为手动任务 | 自动确认后是否直接归档 |
| **D-7** | multi-face clustered = 0 的直接原因是生产历史运行仅勾选 `[1-1]` 档位；1042 条多脸 observation（含 embedding）在库待用；放宽入口/影响已全部查明（§3.1） | **是否放宽 face_count_ranges 重跑识别** —— 当前样本获取的关键决定 |

---

## 6. Production Deployment Preconditions（CP8 —— 只读设计，不执行）

```text
Production deployment prerequisite checklist
├─ 0. 前置确认
│    ├─ 运行代码 = HEAD 27bdc64（含 009/010/011 与全部新链代码）
│    ├─ 生产库 head = 008（已核实），工作树干净、无挂起事务
│    └─ Owner 书面批准迁移窗口
├─ 1. Backup
│    ├─ 文件级冷拷贝 photo_archiver.db（+ -wal/-shm 若存在），拷贝后作 PRAGMA integrity_check
│    └─ 备份留存至版本化位置（回滚主手段，见 3）
├─ 2. Upgrade（alembic upgrade head，001→011 线性）
│    ├─ 009：rr 表加 assignment_id 列 + 3 索引 —— 纯增量，472 行 assignment_id=NULL，结构不受影响
│    ├─ 010：cpa 重建（source CHECK 增 'review'）—— legacy_alter_table=ON 保护 rr 侧 FK；
│    │        生产 cpa = 0 行，重建零风险
│    ├─ 011：新建 3 张 calibration 空表（无回填、不触碰既有表）
│    └─ 升级后核验：head=011；calibration 三表存在；472 行 rr 原样；36 簇/399 members 原样
├─ 3. Rollback
│    ├─ 主手段：停应用 → 用备份文件整体还原（文件级，最快最完整）
│    └─ 次手段：alembic downgrade（011/010/009 downgrade 已有迁移回归测试覆盖），
│        但 010 表重建型 downgrade 慢于文件还原 —— 仅作备用
├─ 4. calibration table initialization
│     零初始化数据需求（表设计无种子行；数据集经 freeze 流程产生）
├─ 5. Compatibility
│     旧版本应用二进制 + 011 schema：旧代码不认识新表但 Alembic 版本一致性检查会拦截；
│     规则 = 迁移与代码同窗升级，不分离发布
└─ 6. Legacy 472 pending rows 对 Calibration 的影响
      无 —— calibration 链路不读 rr（§7）；迁移对它们零改动
```

---

## 7. Legacy Pending Impact（CP9 —— 472 行只读画像）

| 问 | 实测/静态证据 |
|---|---|
| 是什么时期产生 | **2026-09-24 00:28:17 → 00:29:30**，单一 73 秒窗口 —— 早于新链（Phase C 提交 09-25），属 legacy MatchPersonsService 链产物 |
| 内容 | 472/473 照片各一行（1 张无）；`person_id` 100% NULL、`confidence` 100% 0.0 —— 空候选库（person_embeddings=0）下 matcher 恒 None 的"Unknown"行 |
| 是否影响 calibration UI | **否** —— `cluster_results_service` 全文零 `recognition_results` 引用；标注面板消费的是簇与成员缩略图 |
| Calibration 是否读取 | **否**（仓储协议 9 方法无一涉 rr） |
| `dataset_truth()` 是否读取 | **否** —— 只读 calibration 三表 |
| 是否造成 confirmation bias | **无通路** —— 标注员界面（cluster_results_dialog 嵌入面板）不展示 rr 行 |
| 是否需要 Owner 决策处置 | **是，但归属业务链**：这 472 行就是审核中心队列的当前内容（ReviewRecognitionService 直接消费 pending rr）。处置 = 既有 D-1 议题，不属于 calibration 侧；本阶段禁止删除/修改 |

---

## 8. Entry Gate（CP10）

```text
Data-layer ready:                YES   （E1 五项全 available，S4-B-1 CP10 31/31）
Annotation UI ready:             YES   （独立标注面板可用；仲裁暂无 UI、服务 API 可达——已知限制）
Multi-face sample ready:         NO    （multi-face clustered = 0；获取路径 AVAILABLE，等待 D-7）
One-photo-multiple-cluster ready: NO   （= 0；算法支持已证，随 D-7 自然产生）
Margin sampling ready:           NO    （NOT COMPUTABLE；未来路径已设计，冷启动/簇心两案待选）
Production deployment ready:     NO    （head = 008；011 未部署，清单见 §6，等待 Owner）
Owner decisions complete:        NO    （D-1/D-2/D-3/D-4/D-5/D-7 全部未决）
```

## S4-B-2 ENTRY: **CONDITIONAL**

**进入"样本准备执行阶段"前必须满足的条件**（全部为 Owner 侧动作，无一是代码缺口）：

1. **C-1（硬前置）**：批准并执行 migration 部署（§6 清单）—— 无 011 则标注无法落库；
2. **C-2（样本主门）**：裁决 D-7。放宽重跑 → 多脸/一图多簇样本自然产生；或明确裁决
   "首轮仅单脸簇"降级执行（技术上可行，36 簇全域可用，但协议分层降级且自动确认
   评估对多脸场景的覆盖推迟）；
3. **C-3（协议量化）**：裁决 D-1/D-2/D-3 —— 投入意愿、双人/仲裁规程、三个统计参数
   （§4.2 机制就绪，填入即算）；
4. **C-4（可选路径）**：margin 能力建设裁决（簇心 margin 推荐案，§3.3）—— 首轮可显式
   放弃 margin 分层，记为协议降级项。

**不进入执行**。Hard Stop 遵守：无生产迁移、无重跑、无标注、无 executor、无 margin/precision 计算、无自动确认。

---

## 附：验收标准对照（20 项）

| # | 验收 | 落点 |
|---|---|---|
| 1 | S4-B-1 基线复核 | §1.1（零漂移） |
| 2 | Entry Conditions 完整 | §1.3 E1–E5 |
| 3 | face_count_ranges 真实入口 | §3.1 调用链 |
| 4 | 多脸样本获取路径 | §3.1 AVAILABLE |
| 5 | 一图多簇生成条件 | §3.2 代码证据 |
| 6 | pfe writer 明确 | §3.3 第 1–4 点 |
| 7 | margin 生成路径 | §3.3 第 5–6 点 |
| 8 | 样本量公式 | §4.2 机制 |
| 9 | undecidable 分母规则 | §4.2（n 即有效分母） |
| 10 | sampling protocol 冻结 | §4.1/§4.3 |
| 11 | seed 现状如实记录 | §4.3（零落点证实） |
| 12 | leakage policy 冻结 | §4.4 |
| 13 | D 系列 Owner Decision | §5（含 D-7 关键性标注） |
| 14 | migration plan | §6 清单 |
| 15 | legacy 472 影响 | §7 |
| 16 | 无生产写入 | 全程只读连接 |
| 17 | 无真实标注 | 未启动 |
| 18 | 无 sampling executor | §4.3 仅实现要求 |
| 19 | 无 margin 计算 | §3.3 仅设计 |
| 20 | 明确 Entry Gate | §8 CONDITIONAL |
