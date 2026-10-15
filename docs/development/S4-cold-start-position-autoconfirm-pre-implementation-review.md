# S4 冷启动位置自动确认 — 实现前只读审查与开发任务书

> **审查角色**：审核 AI（只读）
> **日期**：2026-10-10
> **审查对象**：Owner 已批准的冷启动位置自动确认业务决策（7 条，见 §0）
> **方法**：只读审查——零代码修改、零测试修改、零文档改动（本文档为新建交付物）、零数据库写入、不提交、不推送。全部结论基于当前工作区源码逐文件核对，引用格式 `路径:行号`。未运行 pytest；"存在对应测试"仅指测试文件与断言可见。
> **范围边界**：不触碰 S-B-1..S-B-6 已冻结行为（机械评分/评估基线链路，已核对互不影响，见 §2.4）。

---

## 0. 已批准的业务决策（审查输入，逐条编号）

| # | 决策 |
|---|---|
| BD-1 | 沿用现有 FaceCluster、`sort_key` 和 `roster_order` |
| BD-2 | 配对输入数量相等且所有前置条件有效时，按位置形成 `auto_confirmed` 身份分配 |
| BD-3 | 数量不一致时，整个当前识别批次禁止自动确认，相关记录交由人工处理 |
| BD-4 | 位置配对的 `score` 必须保持 NULL，不得伪造相似度证据 |
| BD-5 | `auto_confirmed` 不直接生成任何后续人脸样本；只有人工最终确认后才允许样本沉淀 |
| BD-6 | 保留 Assignment SSOT、下游投影单向性和现有人工变更规则 |
| BD-7 | 不改变人脸检测、聚类、已有样本匹配算法及阈值 |

---

## 1. 现有流程与调用链图（实测代码链）

### 1.1 冷启动位置配对现状链（生成建议 → suggested 落库）

```
PairingWorkbenchDialog「生成建议」按钮
  pairing_workbench_dialog.py:89-91（按钮）、:287-301（_on_generate_clicked）
  └→ StartSuggestPairingsCommand(cluster_run_id)                      application/commands/pairing.py
     └→ SuggestPairingsService.execute                                suggest_pairings_service.py:70-163
        读入（5 路数据 + 3 路排除域）：
        ├─ FaceClusterRepository.get_cluster_run / list_clusters / list_members   当前聚类代际
        ├─ FaceObservationRepository.list_by_run(cluster_run.recognition_run_id)  当前识别运行观测
        ├─ PersonFaceSampleRepository.list_enabled()                        :110  全库启用样本
        ├─ PersonRepository.list_all()                                 :116-120  全库名单（含 roster_order）
        ├─ list_rejected_pairs(cluster_run_id)                         :130-132  代际内 rejected (簇,人) 对
        ├─ list_active_by_cluster_run(cluster_run_id)                  :133-138  已有有效指派的簇
        └─ list_confirmed_person_ids(cluster_run_id)                   :139-141  已确认人员
        └→ 领域纯函数 suggest_pairings                                  domain/services/pairing.py:60-146
           ① sample_match：成员观测 × 启用样本 max 余弦 ≥ 0.40 → suggested(score=真实余弦)   :92-120
           ③ ordered 一对一：剩余簇 sort_key 升序 × 剩余人员 roster_order 升序
              → suggested(source=ordered_suggestion, score=None)                    :122-145
        └→ _persist：全部产物以 status=suggested 落库（add_assignments 批量 INSERT）  :165-181
```

要点：
- **规则③就是现状"冷启动位置配对"**——产物是 `ordered_suggestion` 建议（score=NULL），永不是确认（`pairing.py:15` 注释"本函数从不产生 confirmed"；业务规则 CORE-04）。
- 排除域全部按 `cluster_run_id` 求值（换代际后重新计算）；样本与名单是**全库**读取（PR-01）。
- 人员排序：`roster_order` 升序，无顺序者排有序之后、按 person_id 兜底全序（`pairing.py:76-86`）——BD-1"沿用现有 roster_order"即此语义。
- 簇排序：`sort_key` 物化文本 `"{time}|{path}|{tiebreak:06d}"`，时间缺失用 `~` 哨兵排末（`face_clustering.py:294-301`；`cluster_faces_service.py:197-223` 生成依据）。
- **无任何事务包装**：`SuggestPairingsService` 裸调仓储；`add_assignments` 单次 `executemany` + `with connection`（`sqlite_cluster_assignment_repository.py:50-82`）——单批 INSERT 自身原子，但"读取→判定→写入"跨多个独立连接，无一致性边界（对比 §4）。

### 1.2 人工确认 → 样本沉淀 + 归档投影链

```
PairingWorkbenchService.confirm（仅 suggested → confirmed）          pairing_workbench_service.py:165-197
  ├→ assignment.confirm(sort_snapshot)          保存排序快照 + confirmed_at   cluster_assignment.py:144-151
  └→ _sink_confirmation                                              pairing_workbench_service.py:364-414
     ├→ 样本沉淀：簇成员观测 → person_face_embeddings（查重跳过 + UNIQUE 兜底）
     └→ 投影：ProjectionReconciler.reconcile_pair → recognition_results APPROVED
              confidence：sample_match=clamp(真实余弦)；ordered/manual=NULL（BLK-5"无证据"）

解除/改派（unassign :211-248 / assign_person :252-312）
  └→ _retract_confirmation :416-450：按「(photo,person) 是否仍有 active 支撑」重算投影
       （多支撑 retarget，最后一个支撑才终结 approved→rejected）+ 样本 enabled=0

审核中心「通过+指定人员」→ IdentityDecisionService.confirm_from_review
  新建 source=review, status=confirmed 行 + 沉淀 + reconcile，全程单 BEGIN IMMEDIATE 事务
                                                     identity_decision_service.py:206-309

归档门槛：ArchivePlanner 只读 recognition_results 的 APPROVED 行  archive_planner.py:119-146（CORE-05）
```

### 1.3 决策事件与状态机（SSOT）

- `ClusterPersonAssignment` 四态：`suggested → confirmed/rejected/unassigned`；`confirmed/rejected → unassigned`；`unassigned` 终态。转移表 `cluster_assignment.py:96-107`。
- 来源四值：`ordered_suggestion / manual / sample_match / review`（`:61-72`）；`MANUAL_ASSIGNMENT_SOURCES={manual, review}`（`:77-79`）。
- 同簇"当前身份" = 最新一条决策事件（INV-1，`list_latest_decision`，`sqlite_cluster_assignment_repository.py:128-141`）；当前有效 = status ∈ `ACTIVE_ASSIGNMENT_STATUSES = {suggested, confirmed}`（`cluster_assignment.py:45-47`）。
- `source` 不可变（`update_assignment` 不写 source 列，`sqlite_cluster_assignment_repository.py:92-117`）——人工最终性由"新行"承载，不允许机器建议行原地升格（S1-F 实证，`identity_decision_service.py:254-261`）。
- actor 守卫 `_assert_mutable_by_machine`（`pairing_workbench_service.py:66-92`）：非 `HUMAN_ACTOR` 一律按机器（fail-closed）；机器不得触碰 manual/review 来源行，**且不得撤销任何 confirmed 行（无论来源）**。当前生产代码**无任何调用方传 MACHINE_ACTOR**——自动确认服务将是第一个机器调用方。
- Assignment 与识别运行的关系是**间接**的：行上无 run 列，经 `cluster_id → face_clusters(cluster_run_id, run_id)` 悬挂（`face_cluster.py:153-165`）。冷启动 auto_confirmed 行沿用同一关系即可表达"对应当前识别运行"，无需新列。

### 1.4 审查任务书所列"通用 auto_confirm() 的 score=NULL 守卫"——**不存在**

全仓 `grep -rni auto_confirm src tests` 仅命中一处注释：`cluster_assignment.py:58`
> `# S4 引入 ``auto_confirmed``（自动确认）时在此加入，不改动上者的语义。`

即：**现状没有任何 `auto_confirm()` 方法、没有 score=NULL 守卫、没有 auto_confirmed 状态**。该注释位于 `PROJECTION_SUPPORT_STATUSES` 定义块内，是一处 S1 时期的**展望性预留**（含义为"加入投影支撑集"），与本次批准决策的关系需 Owner 裁决（见决策表 D1）。守卫须随本特性新建（§5、§9 C-2）。

---

## 2. 关键审查问题逐项结论

### 2.1 A. 自动确认合法性 —— **现有 Assignment 契约无法表达，缺口明确**

| 表达需求 | 现状 | 结论 |
|---|---|---|
| `status=auto_confirmed` | 状态词表 `{suggested, confirmed, rejected, unassigned}`（`cluster_assignment.py:31-43`），转移表无此态 | **缺失**：需新状态常量 + 转移边（§5） |
| 来源=冷启动位置规则 | `ASSIGNMENT_SOURCES={ordered_suggestion, manual, sample_match, review}`（`:61-72`） | **缺失**：需新来源常量（建议 `ordered_auto_confirm`） |
| DB 层表达 | `cluster_person_assignments.status` 与 `source` 列均有 **CHECK 约束**（migration `007:38-41`，source 词表经 `010` 重建扩展过一次）；SQLite 无法 ALTER CHECK | **需要 Migration 013**（表重建，§7） |
| `score=NULL` | 实体 `score: float \| None`（`:118`，范围守卫 `:138-139`）；投影侧 confidence NULL"无证据"语义已有（BLK-5，`recognition.py:34-38`） | **可表达**；守卫须新建为强约束 |
| 对应当前识别运行与 Cluster/Person 关系 | 经 cluster 间接悬挂（§1.3） | **可表达**，无需新列 |
| 人工最终确认入口 | 工作台 `confirm()` 仅接受 `suggested` 起点（`pairing_workbench_service.py:168-171`） | **需扩展**接受 `auto_confirmed` 起点 |

**结论**：无法用既有数据模型表达 → 按任务书约束**停止并报告**，不自行修改。所需结构变更唯一项 = Migration 013（CHECK 词表扩展，010 已有成熟重建模式）。

### 2.2 B. 整批数量保护 —— 比较集合定义 + 全有或全无准入

**两个比较集合的严格定义**（全部来自当前识别运行的有效范围与现有排除规则，零全库统计）：

- `E_c`（参与位置配对的簇集）= 当前 `cluster_run_id` 的簇中，满足：①无有效指派（`list_active_by_cluster_run`，现硬编码 `{suggested, confirmed}`，**须加 auto_confirmed**）；②本轮未被规则① sample_match 消耗；③簇内存在有效嵌入观测（`suggest_pairings_service.py:97-103` 防御性跳过的语义）。
- `E_p`（参与位置配对的人员集）= `list_all()` 人员中，满足：①非 `persons_confirmed`（`list_confirmed_person_ids`，现 SQL 硬编码 `status='confirmed'`，**语义须扩为"身份已占"**）；②未被规则①消耗（`consumed_persons`）。

**混合样本匹配与冷启动回退的批次级路径**（现状执行顺序）：

```
同一代际一次 execute 内：规则①先跑（消耗人员）→ 规则③只对剩余集做一对一
                                                  pairing.py:92-120 → :122-145
```
因此**批次级自动确认判定必须发生在规则①之后**：`|E_c| == |E_p|` 用的是 sample_match 消耗后的剩余集（决策表 D2 的推荐口径）。数量不一致（无论方向）→ 整批规则③产物**一律不 auto_confirmed**，按 D3 推荐回退为现状 suggested 行——不存在"部分位置配对被阻断、同批其他位置配对仍自动确认"的路径（BD-3）。

**统一准入判定**（写入前单点判定，纯函数）：

```
admit = (|E_c| == |E_p|)
      ∧ (∀c ∈ E_c: c.first_captured_at 非 None)          # 场景5：时间缺失不自动确认（D5）
      ∧ (∀ 位置对 (c_i, p_i): (c_i, p_i) ∉ rejected_pairs)  # 严格位次（D4）
      ∧ E_c、E_p 非空
admit=true  → 规则③产物整批 status=auto_confirmed
admit=false → 规则③产物整批 status=suggested（现状行为，D3）
```
拒绝原因落日志 + summary（供 UI 展示"整批转人工"），不落库为持久状态。

**不变量证明**：判定为纯函数（输入 = 已在内存中的两集合快照），输出只有"整批 auto / 整批 suggested"二值；写入经 §4 单事务 → 任何数量不一致（及任何写入中途失败）都不可能产生部分 auto_confirmed。

### 2.3 C. 样本与投影保护

**样本不沉淀（BD-5）**：样本沉淀的全部生产入口只有两个——`_sink_confirmation`（工作台 confirm/assign_person，`pairing_workbench_service.py:364-414`）与 `_deposit_samples`（审核身份确认，`identity_decision_service.py:326-343`），**均只在人工动作后执行**。自动确认服务只写 assignment 行、不调用任何沉淀入口 → 设计上 auto_confirmed 路径零样本写入。人工最终确认（auto_confirmed → confirmed 走扩展后的 `confirm()`）后按现有规则沉淀——与现状 suggested→confirmed 完全同链。

**投影与归档（核心决策点 D1）**：`PROJECTION_SUPPORT_STATUSES = {confirmed}`（`cluster_assignment.py:59`）是投影与归档可见性的唯一闸门（`projection_reconciler.py:163`；`archive_planner.py:119-146` 只读 APPROVED）。
- 推荐 **D1=A：不加入** → auto_confirmed 不产生投影、不影响归档计划；归档仍必须经人工确认（与基线 CORE-05/BA-01"配对确认=归档门槛、机器不得把照片送进归档链"一致，与 BD-5"样本只在人工终审后"对称）。
- 若 Owner 裁决 D1=B（加入）→ 投影/归档即刻生效，且必须接受"未被人工看过的位置配对可驱动归档"这一基线变更，并补投影回收的整链测试。
- 遗留投影防护（人工改派/拒绝/解除）：现有机制足够——reconciler 按"是否仍有 active 支撑"重算（多支撑 retarget / 末支撑终结），legacy 行（`assignment_id IS NULL`）完全不被触碰（`projection_reconciler.py:19-23`）。D1=A 下 auto_confirmed 行无投影可遗留，风险为零。

**S-B-1..6 冻结行为不受影响**：`reference_eligibility_service.py:379-396` 的 E-02 门要求 `status == "confirmed" 且 source ∈ {manual, review}`——auto_confirmed（机器来源）天然不满足；`list_latest_decision` 等读路径按最新行取值，新状态不会漏入冻结判定。

### 2.4 D. UI 与审计

| 审查点 | 现状 | 缺口 |
|---|---|---|
| 状态词表 UI | `PAIRING_WORKBENCH_ASSIGNMENT_LABEL` 只有 4 态（`ui_text.py:506-511`）；来源标签缺新来源（`:512-516`） | **必须新增** auto_confirmed 文案（明确"顺序规则自动确认，非相似度识别；待人工最终确认"） |
| 工作台渲染 | `_assignment_text` 分支 `status in ("suggested","confirmed","rejected")` 否则渲染"未指派"（`pairing_workbench_dialog.py:211-229`） | **不改即出 bug**：auto_confirmed 会显示成"未指派" |
| 确认入口 | `confirm()` 服务层拒绝非 suggested（`:168-171`） | 扩展接受 auto_confirmed；按钮文案不变（人工最终确认语义） |
| 选中联动 | 仅 suggested 预选人员下拉（`:270-274`） | auto_confirmed 同样应预选 |
| 数量不一致呈现 | summary 只有 3 计数（`:527-529`） | 需展示"数量不一致，整批转人工处理"原因 |
| 审计可追溯 | 决策行多行历史 + `sort_snapshot` + `source` + `list_by_cluster` 已备 | 结构足够；auto_confirmed 行的 `sort_snapshot` 应在自动确认时记录位次依据（sort_key/first_captured_at/auto_confirmed_at），供追溯 |
| 与 confirmed 区分 | — | UI 文案必须区分"自动确认（待终审）"与"已确认（人工最终）"，不得把不可见状态当完成体验 |

---

## 3. 文件级影响清单

| 层 | 文件 | 变更 |
|---|---|---|
| 迁移 | `alembic/versions/013_assignment_auto_confirm.py`（新建） | status CHECK 加 `auto_confirmed`、source CHECK 加 `ordered_auto_confirm`；按 010 模式表重建（`PRAGMA legacy_alter_table=ON` + 重建 3 索引 `idx_cluster_person_assignments_cluster_id/person_id` + `idx_cpa_cluster_latest`）；downgrade 有损：auto_confirmed→suggested、新来源→ordered_suggestion |
| 领域 | `domain/entities/cluster_assignment.py` | 新常量 `ASSIGNMENT_STATUS_AUTO_CONFIRMED`、`ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM`；词表加入；`ACTIVE_ASSIGNMENT_STATUSES` 加 auto_confirmed；`PROJECTION_SUPPORT_STATUSES` 按 D1；转移表加 `suggested→auto_confirmed`、`auto_confirmed→{confirmed, rejected, unassigned}`；新方法 `auto_confirm()`（内含 score 非 None 即抛 `ValidationError` 的守卫 + `sort_snapshot` 记录）；构造期交叉校验：status=auto_confirmed ⇒ source=ordered_auto_confirm ∧ score is None |
| 领域 | `domain/services/pairing.py` | 规则③产物增强为可携带 auto 标志的输出（或新增纯函数 `evaluate_positional_auto_confirm`，输入两集合+rejected_pairs，输出 admit 二值+理由）；现有排序/阈值零改动（BD-7） |
| 端口 | `domain/repositories/cluster_assignment_repository.py` | `list_confirmed_person_ids` 语义扩为"身份已占人员"（status ∈ {confirmed, auto_confirmed}）——建议同步更名 `list_identity_taken_person_ids`（唯一调用方是建议服务） |
| 仓储 | `infrastructure/database/sqlite_cluster_assignment_repository.py` | `list_active_by_cluster_run` 过滤加 auto_confirmed（`:158-162`）；`list_confirmed_person_ids` SQL 加状态（`:183-197`）；`add_assignments/update_assignment` 不动 |
| 仓储 | `infrastructure/repositories/in_memory_cluster_assignment_repository.py` | 同步两处硬编码（`:80`、`:97`） |
| 应用 | `application/services/suggest_pairings_service.py` | 注入 `transaction_runner`（缺省 None 裸跑，生产接 `run_immediate`，S1-F 先例 `app/services.py:235`）；execute 内规则①后做批次准入判定；`_persist` 按 admit 写 auto_confirmed/suggested；summary 增 `auto_confirmed` 计数与 `auto_confirm_blocked_reason` |
| 应用 | `application/services/pairing_workbench_service.py` | `confirm()` 接受 auto_confirmed 起点（终审语义不变）；`_assert_mutable_by_machine` 扩展：机器不得撤销 auto_confirmed 行（保守 fail-closed） |
| 表现 | `presentation/ui_text.py` | 新状态/来源标签；summary 模板；hint 文案补充自动确认说明；数量不一致提示 |
| 表现 | `presentation/views/pairing_workbench_dialog.py` | `_assignment_text` 分支（`:215`）、预选联动（`:270-274`）、生成结果状态栏（`:294-300`） |
| 装配 | `app/services.py` | `SuggestPairingsService` 构造加 `transaction_runner=connection_provider.run_immediate`（`:369-376`） |
| 不动 | 投影/归档/审核/聚类/识别 | `projection_reconciler.py`、`archive_planner.py`、`identity_decision_service.py`、`run_recognition_service.py`、`cluster_faces_service.py`、S-B 全部服务——零改动（D1=A 时） |

---

## 4. 事务与批次级准入方案

- **先例**：`IdentityDecisionService` 注入 `transaction_runner=connection_provider.run_immediate`（`app/services.py:227-236`）；`run_immediate` 以"读→校验→写→COMMIT 的完整 attempt"为重试单位（`sqlite_connection.py:143-177`），busy 冲突整attempt回滚重来，**任何部分写入都不存活**。
- **方案**：`SuggestPairingsService.execute` 的"读集合 → 规则① → 批次准入判定 → 规则③ → 整批持久化"包进同一 `BEGIN IMMEDIATE` 事务。仓储经 thread-local `connect()` 自动加入（`sqlite_connection.py:92-104`）。自动确认行与（若有）suggested 行同事务写入：中途任何异常 → 整体 ROLLBACK → 0 auto_confirmed（验收场景 10）。
- 现状 `add_assignments` 单批 INSERT 已原子（单 executemany），但批次级要求的是"判定依据与写入结果一致"——单事务同时消除 TOCTOU（判定后、写入前他人确认/删除）。
- 幂等（验收场景 9）：重复 execute 时 `clusters_with_active` 跳过已有 auto_confirmed 的簇（前提：词表扩展后 active 含 auto_confirmed）、`identity_taken` 排除已占人员 → 第二次运行为 no-op，不重复创建、不覆盖已有决定；跨代际按 RR-04 全新求值，旧行不动。

---

## 5. 需要新增或调整的 API / 状态 / 测试契约

**状态与来源**（`cluster_assignment.py`）：
```
ASSIGNMENT_STATUS_AUTO_CONFIRMED = "auto_confirmed"
ASSIGNMENT_SOURCE_ORDERED_AUTO_CONFIRM = "ordered_auto_confirm"
ACTIVE_ASSIGNMENT_STATUSES += auto_confirmed
PROJECTION_SUPPORT_STATUSES   按 D1（推荐：不加）
_ALLOWED_ASSIGNMENT_TRANSITIONS += {suggested→auto_confirmed,
                                    auto_confirmed→{confirmed, rejected, unassigned}}
def auto_confirm(self, sort_snapshot) -> None   # suggested→auto_confirmed；score 非 None 即 ValidationError
构造期校验：status==auto_confirmed ⇒ source==ordered_auto_confirm ∧ score is None
```

**服务契约**：
- `SuggestPairingsService.execute(StartSuggestPairingsCommand) -> SuggestPairingsSummary`（签名不变）：
  - 新增 summary 字段：`auto_confirmed: int`、`auto_confirm_blocked_reason: str | None`。
  - 行为契约：admit=true ⇒ 规则③产物 `status=auto_confirmed, source=ordered_auto_confirm, score=None, sort_snapshot={sort_key, first_captured_at, auto_confirmed_at}`；admit=false ⇒ 产物与现状完全一致（`ordered_suggestion` suggested 行）。
- `PairingWorkbenchService.confirm`：起允许集从 `{suggested}` 扩为 `{suggested, auto_confirmed}`；终审后照常 `_sink_confirmation`（样本+投影）。
- `PairingWorkbenchService.reject / unassign / assign_person`：接受 auto_confirmed 起点（人工词表内；机器 actor 被扩展守卫拒绝）。

**测试契约**（关键断言）：
1. 实体：状态机矩阵新边 + 非法边抛错；`auto_confirm(score=0.9)` 抛 ValidationError；构造期交叉校验三条。
2. 领域纯函数：admit 判定的全组合（相等/不等、时间缺失、rejected 干扰、空集）。
3. 服务（SQLite 集成）：10 场景（§6）+ 重复执行幂等 + 故障注入回滚。
4. 迁移：`test_upgrade_integrity.py` 模式——逐行零丢失 + 新 CHECK 词表可写 + downgrade 路径。
5. 回归：现有 `test_stage_e_pairing_domain/services`、`test_aud004_full_chain_regression`（A-D 场景）、`test_aud017`、`test_s1f/s1g` 全部保持绿——数量不等/无样本路径行为不变是 BD-3/BD-7 的直接验收。

---

## 6. 完整验收矩阵

| # | 场景 | 预期 | 测试层级 / fixture | 现状可测性 |
|---|---|---|---|---|
| 1 | 数量相等 | 完整位次映射，全部 auto_confirmed，score 全 NULL，无样本、无投影（D1=A） | 集成：AUD-004 fixture（`test_aud004_full_chain_regression.py:96-225` 真实 SQLite 链 + `_FakeDetector`）A 场景改造 | 复用，直接可测 |
| 2 | 簇 > 人 | 0 auto_confirmed；前 min 对保持 suggested（D3）；剩余人无持久标记 | AUD-004 场景 B（`:346`）加断言 | 复用 |
| 3 | 人 > 簇 | 0 auto_confirmed；建议行为与现状一致 | AUD-004 场景 C（`:385`）加断言 | 复用 |
| 4 | 数量不一致 + 高分样本匹配 | 批次保护仍生效：0 auto_confirmed；sample_match suggested 照常生成 | 新集成测试：先人工确认 1 簇建样本，再对新代际跑建议（AUD-017 fixture `test_aud017_sample_suggestion_sqlite.py` 可参考） | 需新增（结构现成） |
| 5 | 排序时间缺失 / 顺序不确定 | 不自动确认（整批，D5） | 领域级：构造 `first_captured_at=None` 簇直测 admit=false；全链级需 fixture 扩展——`PillowPhotoMetadataReader` 有 EXIF→mtime 兜底（`pillow_photo_metadata_reader.py:76-117`），真文件难造"无时间"，需 stub reader 或直写 photo 库 | 领域级直接可测；全链级需小 fixture 扩展 |
| 6 | 自动确认不建样本 | `person_face_embeddings` 对应人员 0 行；投影 0 行 | 集成：场景 1 后立即断言 | 复用 |
| 7 | 人工确认后建样本 | auto_confirmed→confirm 后样本/投影按现有规则产生（`test_stage_e_remediation.py:251-330` 同语义） | 集成：场景 1 + `_confirm_all`（`test_aud004:195`） | 复用 |
| 8 | 改派/拒绝/解除/重跑一致 | 状态与投影按 reconciler 支撑重算一致；auto_confirmed 起点全链（S1 模式 `test_s1_projection_ownership_sqlite.py`） | 新集成测试 | 需新增（模式现成） |
| 9 | 同代际重试幂等 | 二次 execute 0 新行、0 覆盖 | 服务级（PR-13 模式 `test_stage_e_pairing_services.py:333`）+ 集成 | 复用 |
| 10 | 批次中途失败 | 0 auto_confirmed 存活（整事务回滚） | 集成故障注入：事务内制造一条违反约束的写入（如删除人员触发 FK），断言全库 0 auto_confirmed | 需新增（接口级，`run_immediate` 语义直测） |
| M | 迁移 013 | 升级前后逐行零丢失；新词表可写 | `test_upgrade_integrity.py` 模式 | 需新增 |

---

## 7. Migration 与 Owner 决策表

**Migration 013 —— 必需**（`cluster_person_assignments` 的 status/source 双 CHECK 硬约束，SQLite 无法 ALTER CHECK；010 已示范 rename/copy/drop 重建 + `legacy_alter_table` 防 `recognition_results.assignment_id` 外键改写 + 三索引重建）。按任务书"不自行实施 Migration"约束，本审查到此停止，迁移脚本列入任务书待批。

**决策表（D1/D2 为方向性裁决，D3-D6 有明确推荐默认值，Owner 可一次性裁定）：**

| # | 问题 | 选项 | 推荐 | 影响 |
|---|---|---|---|---|
| **D1** | auto_confirmed 是否进入 `PROJECTION_SUPPORT_STATUSES`（产生 APPROVED 投影 → 直接进入归档计划）？ | A 不加入（纯指派层状态，终审后才投影归档）；B 加入（位置配对即获得归档可见性） | **A**——与 CORE-05/BA-01"机器建议不得产生可归档投影"基线一致，与 BD-5"终审前不沉淀"对称；`cluster_assignment.py:58` 的 S1 展望注释按 A 处理并同步改写 | B 将改变归档人工门槛基线，需整链重测 |
| **D2** | "配对输入数量相等"按哪个集合比较？ | A 规则① sample_match 消耗后的剩余集（混合场景适用：剩余簇=剩余人即自动确认）；B 仅真冷启动（本轮零样本匹配才启用）；C 全量集（该代际全部簇=全部名单） | **A**——BD-2"配对输入"即位置配对阶段的输入集，与现有两阶段执行顺序（`pairing.py:92-145`）吻合 | B/C 显著缩小或放大触发面 |
| **D3** | 数量不一致时规则③是否仍生成 suggested 建议（现状行为）？ | A 保持现状（suggested 行供人工处理）；B 不生成任何位次建议 | **A**——BD-3 禁止的是"自动确认"而非"建议"；BD-7 保现状 | B 会让工作台空转，人工失去处理载体 |
| **D4** | 严格位次下存在 rejected (簇,人) 对（含被拒导致的顺延）时？ | A 任一位置对被拒 → 整批不自动确认（回退 suggested）；B 允许顺延跳过（现状规则③语义） | **A**——顺延破坏"按位置"语义；"所有前置条件有效"按严格读法 | B 会让"位置"含义失真 |
| **D5** | 时间缺失簇（`first_captured_at=None`）的作用域？ | A 任一参与簇时间缺失 → 整批不自动确认；B 仅时间缺失簇降级、其余仍自动 | **A**——位次映射的整体性：一个不可靠位置污染全序；场景 5 措辞按整批读 | B 出现"半自动"批次，违背整批哲学 |
| **D6** | auto_confirmed 行的人工操作词表？ | A 允许 confirm（终审）/ reject / unassign / 改派，机器一律不得撤销；B 仅 confirm/unassign/改派（无 reject） | **A**——与 suggested 对称，reject 进 rejected_pairs 是更强的"此人非此簇"信号；机器守卫扩展为 fail-closed | B 丢失拒绝证据 |

---

## 8. 下一阶段开发 AI 实现任务书（裁决后直接执行）

> 前置硬门：本任务书生效条件 = Owner 对 Migration 013 + D1-D6 的明确裁决。未裁决前不得动代码。

**C-1 迁移与实体（一个 commit）**
1. 新建 `alembic/versions/013_assignment_auto_confirm.py`：010 模式重建 `cluster_person_assignments`（status CHECK + `auto_confirmed`；source CHECK + `ordered_auto_confirm`；`PRAGMA legacy_alter_table=ON`；重建 `idx_cluster_person_assignments_cluster_id`、`idx_cluster_person_assignments_person_id`、`idx_cpa_cluster_latest`；downgrade 有损改写）。参照 010 全文，注意 009 测试实测过的外键改写陷阱（010:28-30 注释）。
2. `cluster_assignment.py`：新状态/来源常量、词表、转移边、`auto_confirm()` 方法（score=None 守卫）、构造期交叉校验、`ACTIVE_ASSIGNMENT_STATUSES` 扩展、`PROJECTION_SUPPORT_STATUSES` 按 D1、改写 `:48-59` 注释使其与裁决一致。
3. 测试：实体状态机矩阵 + 守卫 + 迁移完整性（`test_upgrade_integrity.py` 模式）。

**C-2 领域批次判定纯函数（一个 commit）**
1. `pairing.py`（或新 `domain/services/positional_auto_confirm.py`）：admit 纯函数（输入两集合快照 + rejected_pairs，输出二值+理由），不触 I/O、不改现有 `suggest_pairings` 行为（BD-7）。
2. 测试：admit 全组合边界（含 `first_captured_at=None`、rejected 干扰、空集、恰等）。

**C-3 服务编排与仓储（一个 commit）**
1. `suggest_pairings_service.py`：`transaction_runner` 注入；规则①后判定；`_persist` 分流；summary 扩展；admit 拒绝原因日志。
2. 仓储两处过滤扩展（SQLite + in-memory + 端口签名/更名）。
3. `pairing_workbench_service.py`：confirm 起点扩展 + 机器守卫扩展（auto_confirmed 机器不可撤）。
4. `app/services.py:369-376` 接线 `run_immediate`。
5. 测试：服务级 10 场景映射（§6）、幂等、故障注入回滚。

**C-4 UI 与文案（一个 commit）**
1. `ui_text.py`：状态/来源标签（"自动确认（位置规则）· 待人工最终确认"）、summary 模板、hint 补充、数量不一致提示。
2. `pairing_workbench_dialog.py`：`_assignment_text:215` 分支、预选 `:270-274`、状态栏 `:294-300`。
3. 测试：dialog 渲染单测（现有 workbench 测试模式）。

**C-5 全链回归收口（一个 commit）**
1. AUD-004 四场景改造断言 + 场景 4/8 新集成测试 + 迁移后全套回归绿。
2. 文档登记：`ARCHITECTURE_DECISIONS.md`/`PROJECT_STATUS.md` 按既有 stage-gate 流程补记。

每阶段验收门 = 阶段 commit → 独立只读验收审计（P0/P1/P2 分级）→ 仅修复确认项的定向整改 commit。

---

## 9. 最终状态

**`BLOCKED`**

阻塞项（均为 Owner 职权，非技术障碍）：
1. **Migration 013 批准**——status/source CHECK 约束使结构变更不可绕过（§2.1、§7）。
2. **D1（投影/归档可见性）与 D2（数量比较集合）裁决**——批准决策 7 条未覆盖这两处业务语义，不同选择实现方向不同（§7）。
3. D3-D6 可随默认推荐值一并确认。

裁决下达并登记后，任务书 §8 即可进入 `READY-FOR-IMPLEMENTATION`。

---

## 10. 实施与闭环登记（追加于 2026-10-11）

> 本节为审查报告交付后的链路登记：Owner 裁决、C-1 实施与验收、F-1 整改闭环。正文 §1–§9 为审查时点结论（含当时的 BLOCKED 判定），历史原文保留不改写。

### 10.1 Owner 裁决正式登记（2026-10-10，C-1 任务书 §2.2）

§7 决策表全部裁定，登记如下：

| # | 裁决 | 含义 |
|---|---|---|
| D1 | **A** | `auto_confirmed` 不加入 `PROJECTION_SUPPORT_STATUSES`，不产生 APPROVED 投影、不驱动归档 |
| D2 | **A** | 数量比较采用规则① sample_match 消耗后的剩余 Cluster 与剩余人员集合 |
| D3 | **A** | 数量不一致时继续生成现有 `suggested` 建议，整批不自动确认 |
| D4 | **A** | 任一严格位置对被拒 → 整批不自动确认；不跳过、不顺延 |
| D5 | **A** | 任一参与 Cluster 缺少有效拍摄时间 → 整批不自动确认 |
| D6 | **A** | 人工可确认/拒绝/解除/改派；机器不得撤销 `auto_confirmed` |
| 迁移降级 | 批准 | Migration 013 有损降级：`auto_confirmed→suggested`、`ordered_auto_confirm→ordered_suggestion` |

### 10.2 C-1 实施（完成，工作树未提交）

Migration 013（010 模式表重建，两 CHECK 词表扩展 + 三索引重建 + 有损降级）与 `cluster_assignment.py` 扩展（新状态/来源、转移边、`auto_confirm()` 专用入口、构造期组合守卫、人工终审必须新建 manual/review 决策行契约）。新增测试：实体 17 项 + 迁移 7 项；两处 head 钉定同步。交付状态 `C-1-IMPLEMENTATION-COMPLETE-PENDING-AUDIT`。

### 10.3 C-1 独立验收（`C-1-AUDIT-FINDINGS`，2026-10-10）

交付本身全部契约核验通过（迁移 12 项、状态机、人工终审四条升格路径全关、质量门独立复现 1788/8/0）；发现 F-1（P1，s1f 多人测试 flaky，经因果与对照实验证明先于 C-1 存在）与 F-2/F-3/F-4（P2/P3/P3 登记项）。

### 10.4 F-1 整改与复审（2026-10-11）

根因 = **测试夹具歧义**（生产 GUI 链每照片 ≤1 条 PENDING，D-3 域内选择无歧义；同刻 + 随机 UUID 字典序在合成双行状态下随机消费）。Case A 夹具最小整改（仅测试文件）+ 4 个新钉定测试。复审 `C1-F1-REAUDIT-VERIFIED`，含两项**突变实验**（隔离副本：选择改"最晚优先" 6/7 测试失败；禁用占位复用 6/7 失败——证明测试真实锁定机制、未掩盖生产缺陷）。整改后全量 1792 passed / 8 skipped / 0 failed。

### 10.5 F-1 正式关闭（Owner 决策 `C1-F1-CLOSE-APPROVED`，2026-10-11）

1. 依据复审报告正式关闭 F-1（问题台账登记号 **AUD-026**）。
2. 复审结果与两项突变实验已登记（AUD-026 证据列 + 本节 10.4）。
3. F-2/F-3/F-4 维持原登记状态（台账 **AUD-027/028/029**），不因 F-1 关闭而联动。
4. 旧 CLI 多 PENDING 残余风险按 P3 登记（台账 **AUD-030**），本次不修改 D-3 契约。
5. **本决策不授权启动 C-2，不授权生产迁移、生产数据写入、commit、push 或发布。C-2 必须另行取得 Owner 明确授权后才能启动。**

### 10.6 当前链路状态（截至 2026-10-11）

- 已完成：只读审查（§1–§9）→ C-1（Migration 013 + 领域实体 + 24 项新测试，工作树未提交）→ C-1 独立验收 → F-1 整改 → F-1 复审 → F-1 关闭。
- 未启动：C-2（批次准入纯函数）、C-3（服务编排/事务/仓储/工作台）、C-4（UI）、C-5（全链回归）。
- C-3 硬门清单：机器 actor 对 auto_confirmed 的服务层守卫、`list_active_by_cluster_run`/`list_confirmed_person_ids` 词表扩展、工作台人工终审完整写入链（`_next_created_at` 排序验收）、`SuggestPairingsService` 批次准入与 `run_immediate` 事务、UI `_assignment_text` 分支（见台账 AUD-027/029 与 C-1 验收报告 §8）。
- 工作树含未提交交付物（含会话前已有的 S4-B-2 未提交改动）；commit/push 属 Owner 职权。

### 10.7 后续链路状态（截至 2026-10-15，追加于 G-D/R2 治理同步轮）

本节为 §10.6（截至 2026-10-11）之后的事实性追加，不改写历史结论：

- §9 的 BLOCKED 三阻塞项已由 §10.1 Owner 裁决（2026-10-10）解除；§10.5 第 5 条
  “本决策不授权启动 C-2” 的授权前置已由后续 Owner 任务书满足。
- C-2～C-5 已全部实施并完成验收（2026-10-15）：C-1 契约↔实现一致性审查
  PASS WITH FINDINGS（16 项不变量 VERIFIED，隔离快照 102 项测试）；C-2 Migration 013
  离线验收 PASS WITH FINDINGS（25 项测试 + sqlite_master 结构探针恰一词表变化、
  integrity/fk 双绿）；C-3 服务/事务 PASS WITH FINDINGS（73 项 + 批内中途失败探针
  0 行存活 + 双仓储同输入对照全等）；C-4 UI/跨链 PASS WITH FINDINGS（52 项 Qt/回归
  + EOF 单点修正）。
- 本文档已于 2026-10-15 随 G-D/R2 治理文档组正式入库（commit 待 Owner 批准）；
  §8 的开发任务书（R3 修订版）同批入库。
- 冷启动链整组提交：`d3f90e9`（feat(pairing): add cold-start positional
  auto-confirm，26 路径 +2820/−107）；前置提交：AUD-030 `d43ecca`、
  AUD-026/033 `1fde8b5`。
- 仍属 Owner-Gate：生产 Migration 013 执行（生产最近已知 = 012，本迁移未在生产
  执行）；F-C3-2 事务内 kernel 构建性能观察；G0 三文件处置；治理文档组 commit
  批准；push。
- 验收证据：C-1..C-5 各轮隔离快照位于 %TEMP%（c1_audit/c2_migration_013/
  c3_service_transaction/c4_ui_cross_chain/c5_cold_start_final_acceptance_20261015）；
  阶段验收报告为会话交付未落盘（如实标注）。
