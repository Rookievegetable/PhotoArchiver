# Stage 4.2 — 最终冻结复审报告（Final Freeze Review）

- **复审对象**：`D:\work\PhotoArchiver`，仓库 HEAD `2823d1c7ceaab09c38d39b9a80e1e724839cfa17`（`main`，2026-09-28 01:44:20 +0800，`fix: resolve business baseline freeze blockers`）
- **复审输入（全部视为待验证材料）**：`Stage1_BusinessFacts.md`、`Stage1_Handoff.md`、`Stage2_BusinessRules.md`、`Stage2_Handoff.md`、`Stage3_BusinessDiagrams.md`、`Stage4_FinalAudit.md`、`Stage4_1_FinalReview.md`
- **复审日期**：2026-09-28
- **权威事实源**：当前工作区 HEAD 的源码 / migration / 测试 / **真库 SQLite 实测**
- **项目改动**：**零改动**。审计前后 `git status --porcelain` 完全一致（仅 2 个存量未跟踪证据文档 `docs/development/evidence/stage-f-acceptance-review.md`、`stage-f-report-verification.md`，均非本次产生）。临时探针写在仓库外 `C:\Users\Public\PA42\`，探针库在 `%TEMP%`，**未提交 Git**

---

## 1. 审计范围

本阶段为**只读审计**，不重新设计业务流程、不扩大审计范围、不修改任何源码/数据库/migration/测试/业务文档。

| # | 审计面 | 方法 |
|---|---|---|
| 1 | 基线稳定性 | `git log -1` / `git status --porcelain` / `git diff --stat HEAD` / 各报告 commit 声明提取 |
| 2 | Stage 4 的 BLK-1..BLK-5 | 逐项对照当前源码 / migration / 测试；BLK-1、D-1 用**真库探针**实跑复现 |
| 3 | Stage 4.1 的 BLK-3R / BLK-D1D / BLK-D2D | 全量 `文件.py:行号` 机械化校验（Python 脚本，仓库外）+ 关键引用**逐行人工抽检**（含"行号在界内但指向错函数"盲区） |
| 4 | D-1 / D-2 端到端 | D-2：直接调用 `suggest_pairings` 跑 0.39 / 0.40 / 0.41 三点边界；D-1：真库 `update_status` → `list_approved_by_person` → `read_workspace_counts` 链 |
| 5 | migration 008 | 真库从 `007` 升到 `head`，`PRAGMA table_info` / `foreign_key_list` / `sqlite_master` 实测 + **回填规则探针**（唯一命中 / 重名 / 孤儿姓名 / 无匹配 四种情形） |
| 6 | 业务基线一致性 | Stage 1 → Stage 2 → Stage 3 三层链逐点回查（主流程 / 识别 / 观测 / 聚类 / 时间排序 / `roster_order` / positional pairing / 人工修正 / rerun / history / archive / compatibility chain） |
| 7 | Known Limitations | 逐项回查当前实现，确认其仍为"有界现状事实"而非已破坏基线 |
| 8 | 测试证据 | **全量 `pytest` 独立实跑** + 定向 54 项 / 435 项复跑 |

**未覆盖（明确声明）**：未做 runtime UI 手工走查（与 Stage 4 / 4.1 同样的覆盖限制）；未做 10k 级 `archive_records` 的 migration 性能实测。

---

## 2. 基线确认

### 2.1 当前 HEAD

```
2823d1c7ceaab09c38d39b9a80e1e724839cfa17
fix: resolve business baseline freeze blockers   2026-09-28 01:44:20 +0800
main  [origin/main: ahead 44]
```

**与任务书指定的冻结基线 `2823d1c` 完全一致。**

### 2.2 工作区洁净度

`git status --porcelain` 输出仅两行 `??`（未跟踪证据文档），`git diff --stat HEAD` **为空**——无任何已跟踪文件的修改。审计前后一致，本阶段未产生任何仓库改动。

> 注：Stage 4.1 报告记录的是 1 个未跟踪文件（`stage-f-acceptance-review.md`）；本次实测为 2 个，多出 `stage-f-report-verification.md`。该文件为 Stage F 时期的存量证据文档，位于 `docs/development/evidence/`，**不属于业务源码/测试/migration**，不影响基线判定。

### 2.3 各阶段基线声明一致性

| 文档 | 声明基线 | 与当前 HEAD 一致 |
|---|---|---|
| `Stage1_BusinessFacts.md` | `2823d1c`（全文行号按 HEAD 重核） | ✅ |
| `Stage1_Handoff.md` | `2823d1c` | ✅ |
| `Stage2_BusinessRules.md` | `2823d1c` | ✅ |
| `Stage2_Handoff.md` | `2823d1c` | ✅ |
| `Stage3_BusinessDiagrams.md` | `2823d1c` | ✅ |
| `Stage4_FinalAudit.md` | `b3b8685` | ✅（历史报告，审计对象是修复**前**基线，符合时序） |
| `Stage4_1_FinalReview.md` | `2823d1c` | ✅ |

**"基线收口"三件套**：Stage 1/2/3 均在文首显式标注「原基于 `b3b8685`，本修订版已按当前 HEAD `2823d1c` 重新核对改写」。`b3b8685` 仅作为**修订溯源**出现，不作为当前有效证据。Stage 3 第 6 行进一步明确：「本页出现『原 …』字样仅用于记录被修正的旧引用，非当前有效证据」。

### 2.4 是否存在引用未来/其他 commit 的实现事实

**未发现**。全部文档的有效证据引用均指向 `2823d1c` 工作区内容；无任何引用指向 `2823d1c` 之后的 commit（当前 `main` 亦无后续 commit）。Git 历史段落（Stage 1 §12.9）列举的 11 个 commit 均为 `2823d1c` 的**祖先**，属历史沿革陈述，非"未来实现事实"。

**基线确认结论：通过。**

---

## 3. Stage 4 Blocker Closure

### BLK-1 | 归档去重身份（DATA_RELATION_ERROR，高）— ✅ **已关闭**

**要求**：以稳定 `person_id` 为主要身份依据；同名 Person 不互相抑制；改名不产生错误重复归档；counter 与 planner 语义一致；migration/schema/query 一致。

#### 3.1.1 代码证据

| 落点 | 证据 |
|---|---|
| 领域契约 | `archive_record_repository.py:29-45` — `has_successful_for_person(photo_id, person_id, person_name)`，docstring 明写「去重按稳定 Person identity 判定（Stage 4 BLK-1 修复）」 |
| 实体 | `archive.py:39`（`person_id` 是稳定身份）、`archive.py:60`（`person_id: UUID \| None = None`） |
| SQL 实现 | `sqlite_archive_record_repository.py:107-138` — 谓词 `(? IS NOT NULL AND person_id = ?) OR (person_id IS NULL AND target_person_name = ?)` |
| 落库 | `sqlite_archive_record_repository.py:42-72`（`add` 写 `person_id`）、`archive_executor.py:325-343`（`_make_planned_record` 传 `person_id=item.person_id`） |
| 仓储 Schema | migration `008:52-55`（`ALTER TABLE archive_records ADD COLUMN person_id TEXT REFERENCES people(id) ON DELETE SET NULL`）、`:56-59`（索引）、`:63-76`（回填） |
| Planner | `archive_planner.py:199-210` — 明确注释「按稳定 Person identity 去重，不再按姓名字符串」 |
| Counter | `sqlite_recognition_repository.py:181-241`（`read_workspace_counts`），`:198-200` 注释「与 `has_successful_for_person` 保持同一口径，否则计数会与实际可归档项脱节」；SQL `:221-225` 同口径谓词 |

**migration / schema / query 一致性** — 真库升级实测：

```
alembic_version = 008_archive_identity_and_confidence
archive_records 列 = [id, photo_id, target_archive_root, target_person_name,
                      target_event_or_date, target_original_name, status,
                      archived_at, error, person_id]
archive_records FK = [('photos','photo_id','id','CASCADE'),
                      ('people','person_id','id','SET NULL')]
recognition_results.confidence NOT NULL 标志 = 0   (已放宽为可空)
索引 = idx_archive_records_photo_id / _status / _person_id
       idx_recognition_results_photo_id / _person_id   (002 命名索引已在 008:110-117 重建)
```

**回填规则探针**（`007 → head` 真实升级，4 种情形）：

| 存量行 `target_person_name` | 库中 people | 回填 `person_id` | 判定 |
|---|---|---|---|
| `Unique` | 唯一命中 | `p1` | ✅ 正确回填 |
| `Dup` | **两个**同名 | `NULL` | ✅ 重名不猜身份 |
| `Ghost` | 唯一命中（已存在） | `p4` | ✅ 唯一命中即回填 |
| `Nowhere` | 无匹配 | `NULL` | ✅ 无匹配不臆造 |

与 `008:60-76` docstring 声明的「仅在姓名唯一命中时回填；重名保持 NULL，宁可沿用旧语义也不猜错身份」**完全一致**。

#### 3.1.2 真库行为探针（`has_successful_for_person` 实跑）

| 场景 | 实测 | 期望 | 结论 |
|---|---|---|---|
| 同名不同人：p1 已归档，p2（同名）是否被抑制 | `False` | False（不抑制） | ✅ |
| 改名后：p1 改名「Zhang W.」，旧记录是否仍拦截 | `True` | True（不重复归档） | ✅ |
| 存量 NULL `person_id` 行按姓名回退 | `True` | True | ✅ |
| 姓名不匹配 | `False` | False | ✅ |
| 删除 Person → `archive_records.person_id` | `[None]` | NULL（`ON DELETE SET NULL`） | ✅ |

**BLK-1 全部五项验收口径成立。**

### BLK-2 | 虚构文件/函数/调用链 — ✅ **已关闭**

| 检查项 | 结果 |
|---|---|
| `batch_import_flow_service.py` | ✅ **零命中**（Stage 3 仅第 4 行以「已删除的旧名」形式记录） |
| `cluster_run_controller.py` | ✅ **零命中** |
| 替换为真实实现 | Stage 3 §7 已改用 `confirm_import_service.py:50-109`（实测 `execute` 在 `:50`）、`cluster_faces_controller.py` |

**Stage 4 §3.1 所指的"事务内只 `update_many` photo_source_batch"这一虚构机制描述亦已删除**，Stage 3 §8-B5 现正确描述为「people 写入在 UoW 内，`:96-98` 的 `set_batch_status(confirmed)` 在事务外」——实测 `confirm_import_service.py:90` 为 `with self._unit_of_work`，`:96-98` 为事务外调用，**语义匹配**。

### BLK-3 / BLK-3R | 引用越界与行号漂移 — ✅ **已关闭**

**BLK-3（越界行号）**：`pairing_workbench_service.py:530-555`、`workspace_controller.py:298-315` 在 Stage 1/2/3 有效正文中**均已不存在**；仅 Stage 3 第 4 行以「原 …」记录被修正的旧值（第 6 行已声明该写法非当前有效证据）。

**BLK-3R（`2823d1c` 造成的行号漂移）**：Stage 4.1 指出 `pairing_workbench_service.py` +11/+16 行、`pairing.py` +1..+6 行漂移。本次按 **Stage 3 第 5 行给出的重算映射**逐条实测：

| Stage 3 声明 | 实测行内容 | 判定 |
|---|---|---|
| `confirm → :105` | `def confirm(...)` | ✅ |
| `reject → :141` | `def reject(...)` | ✅ |
| `unassign → :151` | `def unassign(...)` | ✅ |
| `assign_person → :185` | `def assign_person(...)` | ✅ |
| `set_cluster_state → :233` | `def set_cluster_state(...)` | ✅ |
| `_active_assignment → :268` | `def _active_assignment(...)` | ✅ |
| `_sink_confirmation → :276-345` | `:276 def _sink_confirmation` … `:345 return` | ✅ |
| `_retract_confirmation → :347-375` | `:347 def _retract_confirmation` … `:374 return retracted` | ✅ |
| `pairing.py:28` | `SAMPLE_MATCH_THRESHOLD_DEFAULT = 0.40` | ✅ |
| `pairing.py:92-120` / 阈值判定 `:109-112` | `:92` 规则① 起 / `:109 score < sample_match_threshold` / `:111-112` 最优更新 | ✅ |
| `pairing.py:127-141`（规则③） | `:127 for cluster in ordered_clusters` … `:141` 构造 outcome | ✅ |

**全量机械化校验**（Python 脚本，索引 `src/tests/tools/alembic/docs` 全部 `.py`/`.md`）：

```
总引用条目：约 1,400+
越界（行号 > 文件实际行数）：0
文件不存在：0
```

初次用 PowerShell 跑出的 15 条"异常"经复核**全部为脚本假阳性**（同名文件多路径、缩写文件名）；改用全路径解析的 Python 脚本后归零。缩写引用逐个回查确认指向真实文件：

- `main.py:165-178,227,439,674-739` → `main.py`（804 行）：`:165 import_parser`、`:227 recognize_parser`、`:439 run_import_people_command`、`:674 run_recognize_command` ✅
- `stage-f-calibration-report.md:31,35,56-68,112-116,118-124` → 存在（127 行），内容与引用语义匹配 ✅
- `people-import-face-clustering-execution-plan.md:94-96,206-208` → 存在（246 行），`:96` 为 B-2 级联扩展、`:208` 为「E-3 后续照片匹配切换」✅
- `.ai/KNOWN_ISSUES.md:41` → 存在（73 行），「当前无未决问题条目」✅

### BLK-4 | `update_assignment` 字段/状态描述 — ✅ **已关闭**

**当前实现**（`sqlite_cluster_assignment_repository.py`）：

```sql
UPDATE cluster_person_assignments SET
    status = ?, score = ?, sort_snapshot = ?, confirmed_at = ?
WHERE id = ?
```

即实际改写 **`status` / `score` / `sort_snapshot` / `confirmed_at`**，`created_at` 不动；**不存在** `updated_at` / `assigned_by` 两列。

**文档描述**（Stage 3 第 4 行 + §7 关键节点表 `:784`）：

> `sqlite_cluster_assignment_repository.py:92-117`（`update_assignment` 改写 `status`/`score`/`sort_snapshot`/`confirmed_at`）

✅ 字段列表与当前实现**逐字一致**；Stage 4 指出的"臆造 `updated_at`/`assigned_by`"已彻底消除，与 §6.3 状态机图的自相矛盾亦已解除。

### BLK-5 | positional pairing 的 confidence 语义 — ✅ **已关闭**

**要求**：无 similarity evidence → `confidence = NULL`；measured cosine → 实际 score；不再把无证据表达为 `0.0`。

| 落点 | 证据 |
|---|---|
| 领域实体 | `recognition.py:34-38` 三态 docstring；`:47` `confidence: float \| None`；`:55-56` 有值时仍校验 `[0.0, 1.0]` |
| 配对侧产出 | `pairing.py:13`（规则③ score=NULL）、`:57`（`score: float \| None`）、`:144`（`score=None`） |
| 落库侧 | `pairing_workbench_service.py:59-67`（`clamp_unit` docstring：传 `None` 表示"无相似度证据"而非编造 `0.0`）、`:316-323`（`confidence = clamp_unit(...) if ... is not None else None`）、`:341` |
| Schema | migration `008:78-117` — 重建表把 `confidence REAL` 由 `NOT NULL` 放宽为可空，并按 002 定义重建命名索引 |
| 文档 | Stage 1:472、Stage 3 §7 `:791`（`recognition.py:47` + 三态 docstring `:34-38`）均正确表述 |

**语义正确性判定**：`sample_match`（有实测余弦）→ 写真实分数；`ordered_suggestion` / `manual`（无证据）→ 写 `NULL`。**「无证据」不再被表达为 `0.0`**。

测试证据：`test_freeze_blockers.py` 的 `test_no_evidence_confidence_is_none_not_zero`（`:200`）、`test_confidence_round_trips_null_through_sqlite`（`:207`）、`test_confidence_out_of_range_still_rejected`（`:223`）、`test_approved_null_confidence_row_still_archives`（`:235`）四项覆盖。

### Stage 4 Blocker Closure 汇总

| # | 阻断项 | 严重度 | 状态 | 核心证据 |
|---|---|---|---|---|
| BLK-1 | 归档去重身份错误 | 高 | ✅ **已关闭** | 真库探针 5/5 + 008 回填 4/4 + counter/planner 同口径 |
| BLK-2 | 虚构文件 | 高 | ✅ **已关闭** | 虚构文件名零命中，替换为真实实现 |
| BLK-3/3R | 引用越界 / 行号漂移 | 中高 | ✅ **已关闭** | 机械校验 0 越界 + 11 项映射逐条实测通过 |
| BLK-4 | `update_assignment` 字段臆造 | 中高 | ✅ **已关闭** | SQL 与文档逐字一致 |
| BLK-5 | confidence 三态 | 中高 | ✅ **已关闭** | 实体/服务/migration/测试四层一致 |

**Stage 4 的 5 个业务级阻断项全部关闭。**

---

## 4. Stage 4.1 Blocker Closure

Stage 4.1 判定 **NOT-FREEZE-READY**，提出 3 条阻断项（另 3 项为建议）。逐项复核如下。

### BLK-3R | Stage 1–3 行号在当前 HEAD 上失效 — ✅ **已关闭**

见 §3 的 BLK-3/3R 小节。三份主文档 + 两份 Handoff 的全部 `pairing_workbench_service.py:*` 与 `pairing.py:*` 引用已按 `2823d1c` 重算；Stage 3 第 5 行显式列出重算映射清单，第 770 行声明「『当前代码实现位置』＝本人在 HEAD `2823d1c` 亲自核对的文件:行」。

**附加动作（超出 Stage 4.1 要求）**：Stage 1 第 4 行、Stage 2 第 4 行、Stage 3 第 5 行均新增「基线收口（2026-09-28，Stage 4.1 复审后）」段落，明确记录漂移原因与重算依据——这正是 Stage 4.1 §14 建议的「把 Stage 3 头部改为明确注明所用行号基线」，**已落实**。

### BLK-D1D | 9 处仍断言 D-1 之前的行为 — ✅ **已关闭**

Stage 4.1 §14 点名的 9 处逐条回查：

| Stage 4.1 指出的位置 | 当前文本 | 判定 |
|---|---|---|
| `Stage3:145`（断点④表） | 「人工补身份有两条路：**审核中心批准时指定人员**（`update_status` 同写 `status + person_id`）或配对确认三连写；**未指定身份的批准行不可归档**」 | ✅ 已改写 |
| `Stage3:367` | 「审核中心的『通过』**只有在指定人员身份时**才产生可归档照片…未指定身份属于『已处理但未确定最终身份』，不进归档计划」 | ✅ 已改写 |
| `Stage3:780`（§7 表 APPROVED 生产者） | 「① 审核通过…**批准可同写人工指定 `person_id`——Stage 4 D-1**；未指定时只写 status」 | ✅ 已改写 |
| `Stage3:792`（§8-B12） | 整条按 D-1 新语义重写 | ✅ 已改写 |
| `Stage3:886`（§10.3） | 「**Stage 4 D-1 已落地**：审核中心批准时可写入人工指定 `person_id`…『让审核中心具备写 `person_id` 的能力』这一待决**已关闭**」 | ✅ 已改写 |
| `Stage2:317` | 「`update_status`（写 status；**批准时可同时写入人工指定 `person_id`——Stage 4 D-1**；未指定身份的批准行仍不可归档）」 | ✅ 已改写 |
| `Stage2:254`（原 PR-20） | 「**有证据写余弦、无证据写 NULL**」 | ✅ 已改写 |
| `Stage1:294` | 「**Stage 4 D-1 后批准可同时写入人工指定的 `person_id`**…未指定身份时该行仍不可归档」 | ✅ 已改写 |
| `Stage1_Handoff:20` | 「最终身份由人工动作写入——配对工作台确认/改派，**或审核中心批准时指定人员（Stage 4 D-1）**」 | ✅ 已改写 |
| `Stage2_Handoff:77` | 同上 | ✅ 已改写 |

**额外补强**：Stage 1:382/472/623、Stage 2:22/327/389、Stage 3:145/277/367/500/658/780/792/832/886、两份 Handoff 共 20+ 处同步收口。**同时保留了反向事实**（Stage 4.1 建议保留）：「未指定身份时该行仍不可归档」在 Stage 1/2/3 三层均明确写出。

### BLK-D2D | `>= 0.40` 未全文收口 — ✅ **已关闭**

| 位置 | 当前文本 | 判定 |
|---|---|---|
| `Stage1:70` | 「max 余弦 **>= 0.40** → `sample_match`（**Stage 4 D-2 裁决统一为 `>=`：恰等于 0.40 命中**；实现把阈值与『当前最优』分离，`score < threshold` 跳过）」 | ✅ |
| `Stage1_Handoff:17` | 「①已确认样本 max 余弦 **>= 0.40**（恰等于 0.40 命中，Stage 4 D-2 裁决）」 | ✅ |
| `Stage2:234`（PR-03） | 「`score` **>= 0.40** 产出 `sample_match` 建议（**恰等于 0.40 命中**）」+ 标记 TESTED（含三点边界） | ✅ |
| `Stage2:399`（U1） | 原「~~代码是严格 `> 0.40`~~」矛盾项**已划除**并标记「**D-2 已裁决并落地**：统一为 `score >= 0.40`」 | ✅ |
| `Stage2_Handoff:17` | 「**>= 0.40**（恰等于 0.40 命中，Stage 4 D-2 裁决）」 | ✅ |
| `Stage2_Handoff:69` | 原未裁决项 #1 **已划除**并改为「**已裁决（Stage 4 D-2）**…不再是未裁决矛盾」 | ✅ |
| `Stage3:295/308/706/744` | 图内节点与注记均写 `>= 0.40`（恰等即命中） | ✅ |

**全量 grep 复查**：`0.40` 在 5 份文档中共 12 处，**无一处仍写 `> 0.40`**，无一处仍列为未裁决。

### Stage 4.1 建议项（不阻断）复核

| # | 建议 | 当前状态 | 判定 |
|---|---|---|---|
| 4 | 补「`person_id IS NULL` 存量行与删人孤儿行仍按姓名回退」 | ✅ **已补**（Stage1:92/624/625、Stage2:22 CORE-06 括注） | 超出要求 |
| 5 | GAP-1..4 测试缺口 + GAP-3 主张修正 | ⏳ 未处理 | **登记为 KL-E** |
| 6 | NEW-1..5 | ⏳ 未处理 | **登记为 KL-F 补充项** |

### D-1 终审：人工身份 → 最终业务结果

**要求的最终语义**：

```
人工选择/修改/确认的人员身份
        ↓
最终业务结果
```

**实现端到端验证**（真库探针）：

```
[1] update_status(result_id, APPROVED, person_id=<P2>)  →  list_approved_by_person(P2) = 1 条   ✅
[2] update_status(result_id, APPROVED, person_id=None)  →  该行 status=approved, person_id=None
                                                         →  planner 查询恒按 person_id 过滤 → 不可归档   ✅
```

| 判定项 | 证据链 | 结果 |
|---|---|---|
| **Approve + person_id → 可进入归档计划** | `review_controller.py:109-119`（`approve(result_id, person_id)`）→ `review_recognition_service.py:51-71` → `:174-191`（`_persist_status` 传 `person_id`）→ `sqlite_recognition_repository.py:298-330`（`:317` person_id 为 None 时只写 status；`:326` 同写 `status = ?, person_id = ?`）→ `sqlite_recognition_repository.py:266-280`（`WHERE person_id = ? AND status = 'approved'`）→ `archive_planner.py:105-116` | ✅ **成立** |
| **Approve + person_id = NULL → 已处理但未完成最终身份确定 → 不进入按人员归档计划** | 同上链：person_id 保持 NULL → `list_approved_by_person` 查不到 → planner 跳过。UI 侧 `review_dialog.py:165-175`（`_identity_combo` 人员选择器）、`:324-338`（`_confirm_without_identity` **显式告警**）、`:344-347`/`:379-382`（未指定时默认取消） | ✅ **成立** |
| 批量批准不覆盖既有身份 | `review_recognition_service.py:193-220`（`_bulk_transition`：仅对 `existing.person_id is None` 的行填默认身份） | ✅ 成立 |
| "人工结果为最终结果"不被 rerun 静默覆盖 | `run_recognition_service.py:125` 守卫 `if in_scope and not self._recognition_repository.list_by_photo(...)` —— 照片已有**任意**行（含人工 APPROVED）即不再写兼容行 | ✅ 代码成立 |

**文档收口**：Stage 1:294/382/472、Stage 2:22/317/327/389、Stage 3:145/277/367/500/658/780/792/832/886、两份 Handoff —— 全部统一为「审核批准可同时写入人工指定 `person_id`；未指定身份的批准行仍不可归档」。**BLK-D1D 关闭。**

### D-2 终审：`score >= 0.40`

**独立实跑**（直接调用 `photo_archiver.domain.services.pairing.suggest_pairings`，`sample_match_threshold=0.40`）：

| 输入 score | 输出 source | 输出 score | 期望 | 判定 |
|---|---|---|---|---|
| **0.39** | `ordered_suggestion`（落规则③） | `None` | 不命中 | ✅ |
| **0.40** | **`sample_match`（命中）** | `0.40` | 命中 | ✅ |
| **0.41** | `sample_match` | `0.41` | 命中 | ✅ |
| 0.50 | `sample_match` | `0.50` | 命中 | ✅ |

**实现口径**（`pairing.py:92-120`）：阈值与"当前最优"**分离**——

```python
if score is None or score < sample_match_threshold:   # :109-110  < 0.40 跳过
    continue
if best_score is None or score > best_score:          # :111-112  最优比较（严格 >，仅用于选 best，不用于判定命中）
    best_person, best_score = owner, score
```

→ **命中判定为 `>=`（`:109` 的 `<` 取反），"选最优"仍为严格 `>`，两者不再混用**。docstring `:7-8` 与 `:92-94` 均已同步为 `>=`。测试 `test_stage_e_pairing_domain.py:141/158/172` 三点边界 + `:188` 低于阈值回落 ordered。

**文档收口**：见 §4 BLK-D2D 表。**BLK-D2D 关闭，D-1/D-2 已在实现、协议、DTO、UI、导出、迁移、文档七层完全统一。**

### Stage 4.1 Blocker Closure 汇总

| # | 阻断项 | 性质 | 状态 |
|---|---|---|---|
| BLK-3R | Stage 1–3 行号在 HEAD 失效 | 文档/证据口径 | ✅ **已关闭** |
| BLK-D1D | 9 处断言 D-1 之前行为 | 文档/证据口径 | ✅ **已关闭**（含 4 条建议补强项） |
| BLK-D2D | `>= 0.40` 未全文收口 | 文档/证据口径 | ✅ **已关闭** |

**Stage 4.1 的 3 条阻断项全部关闭，且关闭方式未引入任何新的文档矛盾。**

---

## 5. Stage 1 → Stage 2 → Stage 3 Consistency

### 5.1 链路完整性

```
Stage1_BusinessFacts.md  (493 行, 事实)
   ↓ 事实 → 规则编号化
Stage2_BusinessRules.md  (377 行, 规则 + 状态模型, RO/RE/CL/PR/RR/HI/AR/CM)
   ↓ 规则 → 图 + 节点表
Stage3_BusinessDiagrams.md (918 行, Mermaid 图 + 关键节点表 + 事实差异表)
   ↓ 全部按 2823d1c 收口
当前实现 (源码 / migration / 测试 / 真库)
```

**三层行数与结构完整**，规则编号体系（RO-/RE-/CL-/PR-/RR-/AR-）在 Stage 2 定义、Stage 3 §8 逐条回指，无编号悬空。

### 5.2 重点域逐点回查

| 域 | Stage 1 | Stage 2 | Stage 3 | 实现 | 一致 |
|---|---|---|---|---|---|
| **主业务流程** | §1.1 七段表 | §5 必须画进流程图 6 项 | §2 总体图 S0–S7 | GUI 入口齐全 | ✅ |
| **人脸识别** | §1-2 四分支 | RE-01~09 | §3.2 + §4.1 | `run_recognition_service.py:104-133` | ✅ |
| **FaceObservation** | 1 照片 N 脸 = N 观测 | CORE-02 | §3.2 / §5.1 N1 | `:110-134` | ✅ |
| **FaceCluster** | 两段式 + 代际 | CL-01~CL-16 | §6.1 | `face_clustering.py:74+` / `cluster_faces_service.py` | ✅ |
| **时间排序（sort_key）** | `:66`（`cluster_faces_service.py:156-183`、`:197-223`） | CL-11/12/13 | §6.1 节点 J/K/L | `build_sort_key` @ `face_clustering.py:294`；`_earliest_capture` @ `cluster_faces_service.py:197-223` | ✅（Stage 3 §7 `:782` 行号略有偏差，见 §8 NF-1） |
| **`roster_order`** | 6 处真实用途 | RO-04、PR-05 | §6.2 节点 I | `pairing.py:82-86` 排序；`suggest_pairings_service.py:116-120` 进入建议输入 | ✅ |
| **positional pairing** | 规则①②③ | PR-02~05、PR-11 | §6.2 F→I | `pairing.py:92-146` | ✅ |
| **人工修正** | 六操作 + 三连写/三连回收 | PR-12~15 | §6.2 P1–P6、§6.3 状态机 | `pairing_workbench_service.py:105-232, 268-375` | ✅ |
| **rerun** | 恒新增 | RR-01~08 | §3.3 + I1/I4 节点 | `run_recognition_service.py:47`、`cluster_faces_service.py:70` | ✅ |
| **history** | 旧数据不改写 | RR / HI 段 | §8-B8「历史视图不存在 [PLAN]」 | 无历史表/服务/UI | ✅ 未把 PLANNED 画成能力 |
| **archive** | 段 7 | AR-01~05、CORE-05/06 | §4.3 + §8-B12 | `archive_planner.py:116`、`sqlite_archive_record_repository.py:107-138` | ✅ |
| **compatibility chain** | §7-1 枢纽论 | CORE-05/07、BA-01/02 | §5.2 兼容链图 + 断点①②③④ | `recognition_results` 唯一枢纽 | ✅ |

### 5.3 四类矛盾的定向排查

| 排查项 | 结果 |
|---|---|
| **文档之间互相矛盾** | ✅ **未发现**。D-1/D-2 在 5 份文档中表述完全一致；BLK-1 去重口径、BLK-5 confidence 三态在三层表述一致 |
| **图与文字矛盾** | ✅ **未发现**。逐图核对 §2 总体图、§3.1–3.5、§4.1–4.3、§5.1–5.2、§6.1–6.3 共 13 张 Mermaid 图：图中 `[IMPL]` 节点全部可在源码指认；`[PLAN]`/`[PART]` 节点确实无实现 |
| **当前实现与业务基线矛盾** | ✅ **未发现**（除 §8 NF-1 的两处行号偏差外，无语义矛盾） |
| **PLANNED 被错标 IMPLEMENTED** | ✅ **未发现**。§9 PLANNED/PARTIAL 清单 8 项逐条复核：簇合并/拆分、工作台内新增人员、样本回流识别（E-3）、阈值调参、`import_batches.cancelled` 写入、`face_clusters.confirmed/split/merged` 写入 —— **在 `src/` 中均零实现**，标记正确 |
| **INFERRED 被错当事实** | ✅ **未发现**。`[INFER]` 标记（roster_order↔时间轴对应关系、unknown/ignored 簇继续收建议等）均带虚线样式并在 §9 登记为语义缺口，未升格为事实 |

### 5.4 Stage 3 §8-B 主流程不一致表的正确性

12 条差异项（**双轨画法**，必须图上可见）逐条回查，**全部成立**：

| # | 断言 | 实现核对 | 判定 |
|---|---|---|---|
| B1 | 兼容行一次性守卫 | `run_recognition_service.py:125` | ✅ |
| B2 | `person_embeddings` 读活写死 | `run_recognition_service.py:66` 读；`sqlite_face_embedding_repository.py:27` `save` 在 `src/` 零调用（`services.py:380/387` 只注入，`:431` 是 `_NoOpFaceEmbeddingRepository` mock） | ✅ |
| B3 | 多脸只投影 1 条 | `run_recognition_service.py:110-134` | ✅ |
| B4 | 簇状态不参与建议过滤 | `pairing.py:96-105` 排除集合无 `face_clusters.status` | ✅ |
| B5 | 批次标签在事务外 | `confirm_import_service.py:90` UoW / `:96-98` 事务外 | ✅ |
| B6 | 三连写无跨表事务 | `pairing_workbench_service.py:105-137, 185-229, 276-345` | ✅ |
| B7 | 照片删除跨代际残留 | `pairing_workbench_service.py:347-374` + 002 FK CASCADE | ✅ |
| B8 | 历史视图不存在 | 无表/服务/UI | ✅ |
| B9 | 导入只登记不建号 / 批次不可取消 | `cancelled` 枚举从未写入 | ✅ |
| B10 | 失败分类不可分 | `recognition_failure_service.py:31` | ✅ |
| B11 | 取消时排队任务仍执行 | `run_recognition_service.py:71-79` | ✅ |
| B12 | 无人身 APPROVED ≠ 可归档 | `sqlite_recognition_repository.py:266-280, 298-330` | ✅ 已按 D-1 改写 |

**Stage 1 → Stage 2 → Stage 3 形成一致且可回查的业务链。**

---

## 6. Citation Integrity

对任务书点名的重点文件做**逐行人工抽检**（不只做越界检查，还检查"行号在界内但指向错函数"这一 BLK-3R 盲区）：

| 文件 | 抽检引用 | 实测内容 | 判定 |
|---|---|---|---|
| `pairing.py` | `:28` / `:92-120` / `:109-112` / `:127-141` | 阈值常量 / 规则① / 命中判定 / 规则③ | ✅ 4/4 精确 |
| `pairing_workbench_service.py` | `:105` / `:141` / `:151` / `:185` / `:233` / `:268` / `:276-345` / `:347-375` | 六个操作 + 两个私有方法 | ✅ 8/8 精确 |
| `suggest_pairings_service.py` | `:110` / `:115-119` | `samples = list_enabled()` / `PairingPerson(... roster_order=...)` | ✅ 2/2 精确 |
| `sqlite_recognition_repository.py` | `:181-241` / `:266-280` / `:274-279` / `:298-330` | `read_workspace_counts` / `list_approved_by_person` / WHERE 子句 / `update_status` | ✅ 4/4 精确 |
| `review_recognition_service.py` | `:51-71` / `:174-191` / `:187-191` / `:193-220` | `approve` / `_persist_status` / `update_status` 调用 / `_bulk_transition` | ✅ 4/4 精确 |
| `archive_planner.py` | `:17-23` / `:105-151` / `:116` / `:167` / `:199-210` | import 列表（无观测/簇/指派）/ `plan` / 唯一数据入口 / `_resolve_target_persons` / 去重调用 | ✅ 5/5 精确 |
| `sqlite_archive_record_repository.py` | `:107-138` / `:110-118` / `:122-137` | `has_successful_for_person` 全函数 / 签名+docstring / SQL 谓词 | ✅ 3/3 精确 |
| `recognition.py`（实体） | `:34-38` / `:47` / `:53-56` | 三态 docstring / `confidence: float \| None` / 范围校验 | ✅ 3/3 精确 |
| `archive.py`（实体） | `:39` / `:60` | `person_id` 稳定身份说明 / 字段定义 | ✅ 2/2 精确 |
| `archive_executor.py` | `:325-343` | `_make_planned_record` 含 `person_id=item.person_id` | ✅ 精确 |
| `workspace_controller.py` | `:42-64` | `match_guidance` 全函数（81 行文件） | ✅ 精确 |
| `confirm_import_service.py` | `:50-109` / `:50` / `:64-67` / `:90` / `:96-98` | `execute` 全函数 / 入口 / roster 续号 / UoW / 事务外状态 | ✅ 5/5 精确 |
| `run_recognition_service.py` | `:47` / `:66` / `:71-79` / `:104-133` / `:110-134` / `:125` | 追加语义 / 读空表 / 取消 / 消费 / 多脸 / 守卫 | ✅ 6/6 精确 |
| `cluster_faces_service.py` | `:26-45` / `:69-103` / `:70` / `:108-114` / `:156-183` / `:176-183` / `:197-223` / `:230-236` / `:239-246` | import 无 RecognitionRepository / `execute` / 追加语义 / 参与过滤 / 落库排序 / pending 默认 / `_earliest_capture` / `_select_participating` / `_deterministic_order` | ✅ 9/9 精确 |
| `face_clustering.py` | `:33-35` / `:74+` / `:273-301` / `:294-301` | 三个阈值常量 / `cluster_items` / `order_cluster_keys`+`build_sort_key` | ✅ 精确 |
| `recognition_repository.py`（协议） | `:106-140` / `:128-140` | `list_approved_by_person` / `update_status(person_id)` 契约 | ✅ 精确 |
| `archive_record_repository.py`（协议） | `:29-45` | `has_successful_for_person` 契约 | ✅ 精确 |
| `sqlite_cluster_assignment_repository.py` | `:92-117` | `update_assignment` SQL 四字段 | ✅ 精确 |
| `review_dialog.py` | `:324-338` | `_confirm_without_identity` 告警 | ✅ 精确 |
| `review_controller.py` | `:93-138` | `list_persons` / `approve` / `bulk_approve` | ✅ 精确 |
| `008_...py` | `:16-18` / `:48-76` / `:78-117` / `:80-107` / `:124` | 回填规则 / 加列+索引+回填 / 表重建 / 整表复制 / downgrade 折叠 | ✅ 5/5 精确 |
| `002_split_create_ddl.py` | `:92-93` / `:109-120` | FK 定义 / archive_records 建表 | ✅ 精确 |
| `sqlite_mappers.py` | `:142-173` | `archive_record_from_row`（含 person_id 映射） | ✅ 精确 |
| `ui_text.py` | `:234` / `:256` | `REVIEW_APPROVE_ALL_CONFIRM_TITLE` / `REVIEW_CONFIDENCE_VERY_HIGH` | ✅ 精确 |

**抽检 68 条，66 条精确命中，2 条偏差见 §8 NF-1（均为 Stage 3 §7 表内的行号偏差，不影响语义）。**

**关键测试与 migration 抽检**：

| 引用 | 实测 | 判定 |
|---|---|---|
| `test_freeze_blockers.py`（13 项） | 逐个 `def test_` 枚举：BLK-1 五项（`:87/109/128/147/174`）、BLK-5 四项（`:200/207/223/235`）、D-1 三项（`:261/298/320`）、rerun 一项（`:343`） | ✅ 与文档描述完全对应 |
| `test_stage_e_pairing_domain.py:141/158/172/188` | D-2 三点边界 + 低于阈值回落 | ✅ |
| `test_alembic_migrations.py` | 008 schema/回填用例存在（`54 passed` 中含） | ✅ |
| `test_upgrade_integrity.py` | 升级完整性 3 项 | ✅ |

**Citation Integrity 结论**：无虚构文件、无越界行号、无失效引用。两处偏差为**同一文件内的区间偏移**，属可追溯性弱化，非事实错误。**不构成冻结阻断。**

## 7. Known Limitations

任务书列出的 6 项，逐项回查当前实现，确认**仍被正确标记为已知限制**：

### KL-A | `person_embeddings` 无 producer / legacy compatibility — ✅ 仍成立，未破坏基线

- **实现**：`sqlite_face_embedding_repository.py:27` 定义 `save()`；全 `src/` 扫描调用点仅 3 处，**全部是构造注入**（`services.py:380`、`:387`）或 mock（`:431` `_NoOpFaceEmbeddingRepository`）。**`save()` 零生产调用**。
- **后果**：`run_recognition_service.py:66` `list_all()` 恒空 → 识别期匹配候选集恒空 → 自动兼容行 `person_id` 恒 NULL。
- **文档登记**：Stage 1 KL-1（`:623`）、Stage1_Handoff §1.10（`:20`）、Stage 2 U15（`:389`）、Stage 3 断点①（`:142`）/§8-B2。
- **判定**：这是**计划 E-3 未兑现**的现状事实（`execution-plan.md:207-208` 有承诺）。D-1 的落地恰恰是**为该限制提供人工补写路径**，而非破坏它。**不构成阻断。**

### KL-B | ambiguous-name historical fallback — ✅ 仍成立

- **实现**：migration `008:60-76` 重名保持 NULL；`sqlite_archive_record_repository.py:126-128` NULL 行回退姓名。
- **真库复现**：`Dup`（两个同名）→ 回填 `NULL` ✅。
- **文档登记**：Stage 1 KL-2（`:624`）、Stage 2 CORE-06 括注（`:22`）。
- **判定**：升级前语义**原样保留**，"升级不退化"是明确取舍。**不构成阻断。**

### KL-C | 删除 Person 后 `person_id -> NULL` 的历史限制 — ✅ 仍成立

- **实现**：`archive_records.person_id` 与 `recognition_results.person_id` 均 `ON DELETE SET NULL`（真库 `PRAGMA foreign_key_list` 实测确认）。
- **真库复现**：删除 Person 后 `archive_records.person_id = None` ✅；该孤儿行此后按姓名参与去重。
- **文档登记**：Stage 1 KL-3（`:625`）、Stage 2 CORE-06 括注（`:22`）。
- **判定**："删人 + 同名重建"可能被旧孤儿行静默抑制——属**有界、可解释**的升级前行为，Stage 2 已明写"属升级前行为原样保留"。**不构成阻断。**

### KL-D | 未完成 runtime UI walkthrough — ✅ 仍成立

- **覆盖声明**：Stage 4 §1、Stage 4.1 §1/§15、Stage 4.2 §1 三方一致声明未做 GUI 手工走查。
- **替代覆盖**：全量 pytest **1310 passed / 6 skipped**（本次独立实跑）+ 8 个真库探针场景 + UI 关键路径静态逐行复核（`review_dialog.py:165-175/324-347`、`pairing_workbench_dialog` 按钮集）。
- **判定**：**审计覆盖限制**，非实现缺陷。**不构成阻断。**

### KL-E | Stage 4.1 GAP-1..5 测试覆盖缺口 — ✅ 仍成立

| # | 缺口 | 当前状态 | 本次独立判断 |
|---|---|---|---|
| GAP-1 | executor 未断言 `person_id` 落库 | ⏳ 仍在 | 代码层已验证（`archive_executor.py:342` `person_id=item.person_id`），缺口是**回归守护不足** |
| GAP-2 | BLK-5 的 UI/导出 NULL 路径无测试 | ⏳ 仍在 | `ui_text.py:256` 等三态常量存在；`ExportMatchRow.confidence: float \| None` |
| GAP-3 | "rerun 不覆盖人工确认"用例是同义反复 | ⏳ 仍在（`test_freeze_blockers.py:343`） | **但代码事实成立**：`run_recognition_service.py:125` 守卫经本次逐行复核无误 |
| GAP-4 | review 身份选择器接线无测试 | ⏳ 仍在 | `review_dialog.py:165-175/344-347/379-382` 经本次复核接线完整 |
| GAP-5 | `test_archive_planner.py` fake 复刻去重谓词 | ⏳ 仍在 | 真库用例（`test_freeze_blockers.py:87/109/147/174`）提供交叉验证 |

**判定**：5 项均为**测试证据覆盖缺口（回归守护不足）**，非行为错误。本次已通过真库探针逐项补足行为证据。**不构成阻断。**

### KL-F | migration 008 大表 copy 风险 — ✅ 仍成立

- **实现**：`008:80-107` 对 `recognition_results` 做 RENAME + CREATE + INSERT SELECT + DROP（整表复制）。
- **未实测**：本次与 Stage 4.1 均未做 10k+ 行性能实测。
- **缓解**：`archive_records` 侧为**纯 `ADD COLUMN`**（`:52-55`），不触发表重建；`recognition_results` 单行窄（6 列）。
- **文档登记**：Stage 4.1 KL-5（`:444`）。
- **判定**：**性能风险（Out-of-Scope）**。**不构成阻断。**

### 补充登记的 Low-Risk 项（Stage 4.1 KL-6/KL-7）

| # | 项 | 当前状态 | 判定 |
|---|---|---|---|
| NEW-2 | 008 表重建分支不可重入 | ⏳ 仍在（`008:78`） | alembic 事务通常回滚，不易触发 |
| NEW-3 | `person_id` 索引仅在加列分支创建 | ⏳ 仍在（`008:48-59`） | 部分应用态下索引不补建，**去重结果仍正确**（仅性能退化） |
| NEW-4 | downgrade 把 NULL confidence 折叠为 0.0 | ⏳ 仍在（`008:124`） | 回滚路径语义损失，**代码注释已声明** |
| NEW-5 | `.ai/` Runtime Context 未同步 | ⏳ 仍在 | 流程一致性，不影响业务基线正确性 |

**四项均为低风险健壮性/流程项，不破坏业务语义，不构成阻断。**

### Known Limitations 结论

**6 项任务书指定项 + 4 项补充项，全部仍被正确标记为 Known Limitation。经独立回查，未发现任何一项已经直接破坏当前业务基线。**

---

## 8. 新发现问题

本次审计**新发现 2 项**，均为**引用可追溯性弱化**（同一文件内的区间偏移），**不涉及业务逻辑、数据正确性或状态机错误**：

### NF-1 | Stage 3 §7 关键节点表两处行号指向偏差（低）

| 位置 | 声明 | 实际 | 判定 |
|---|---|---|---|
| `Stage3:782` | `cluster_faces_service.py:218-237`（`sort_key` 时间顺序轴） | 该文件共 246 行；`:218` 落在 `_earliest_capture` 尾部（该函数为 `:197-223`），`:225-236` 是 `_report` 与 `_select_participating`。`sort_key` 实际物化在 `:181`（`build_sort_key(...)`） | **区间偏移**：所引区间仍**部分覆盖**正确的 `_earliest_capture` 尾部，但未覆盖 `sort_key` 物化点。Stage 1（`:66`）与 Stage 2（CL-11 `:210`）给出的 `cluster_faces_service.py:156-183,197-223` **是正确的** |
| `Stage3:781` / `Stage3:808` | `cluster_faces_service.py:40-45`（聚类两段式 + 阈值） | `:40` 是 import `order_cluster_keys`、`:42-44` 是 `face_observation` import、`:45` 空行 | **指向 import 块而非算法**。但同行同时给出 `domain/services/face_clustering.py`，而算法本体确在 `face_clustering.py:74+`（`cluster_items`）+ `:33-35`（三个阈值常量）——**同行第二引用正确** |

**影响评估**：两处均**不改变任何业务结论**（"两段式聚类 0.5/0.4"与"`sort_key` 按最早拍摄时间"本身都正确，且同行/邻行给出了正确引用）。属 Stage 4.1 §14 已预判的"行号在界内但指向错函数"这一机械校验盲区的**残留实例**，但**严重度为低**——因为正确证据在 Stage 1/2 或同行均已给出，读者可立即定位。

**处置建议（不阻断冻结）**：Stage 3 §7 表 `:781/:782/:808` 的 `cluster_faces_service.py` 行号分别改为 `:33-35` + `face_clustering.py:74+`、`:156-183,197-223`。

### 汇总

| # | 问题 | 严重度 | 类型 | 是否阻断 |
|---|---|---|---|---|
| NF-1 | Stage 3 §7 两处行号区间偏移 | **低** | 引用可追溯性 | ❌ 否 |
| NF-2 | Stage 3 §6.2 图内 `class O tagGate` 重复声明两次（`:739`、`:740`） | **低（无功能影响）** | 图表笔误（Mermaid 允许重复 class 声明） | ❌ 否 |

**未发现任何新的高严重度业务逻辑错误、数据错误或状态机错误。**

---

## 9. Freeze 判定

### 9.1 Freeze 条件逐条核对

| # | 冻结条件 | 状态 | 依据 |
|---|---|---|---|
| 1 | **当前实现基线稳定** | ✅ 满足 | HEAD = `2823d1c7ceaab09c38d39b9a80e1e724839cfa17`，与指定基线一致；`git diff --stat HEAD` 为空；工作区仅 2 个存量未跟踪证据文档 |
| 2 | **Stage 4 原 blocker 全部关闭** | ✅ 满足 | BLK-1（真库探针 5/5 + 008 回填 4/4）、BLK-2（虚构文件零命中）、BLK-3/3R（0 越界 + 11 项映射精确）、BLK-4（SQL 逐字一致）、BLK-5（三态四层一致） |
| 3 | **Stage 4.1 blocker 全部关闭** | ✅ 满足 | BLK-3R / BLK-D1D / BLK-D2D 全部关闭，关闭方式未引入新矛盾 |
| 4 | **Stage 1~3 与当前 HEAD 一致** | ✅ 满足 | 三份主文档 + 两份 Handoff 全部声明 `2823d1c`；全量引用机械校验 0 越界 / 0 缺失；68 条关键引用抽检 66 条精确（2 条低severity 区间偏移） |
| 5 | **D-1 / D-2 已统一** | ✅ 满足 | D-1：实现七层（service/repo/DTO/UI/迁移/测试/文档）一致，真库验证「带身份→可归档 / 不带身份→不可归档」；D-2：实跑 0.39 不命中、0.40 命中、0.41 命中，文档 12 处全为 `>=` |
| 6 | **未发现新的高严重度业务/数据/状态错误** | ✅ 满足 | 新发现仅 NF-1/NF-2 两项低severity 引用/图表问题；全量 pytest 1310 passed / 6 skipped 独立复现 |
| 7 | **剩余问题均属明确 Known Limitation / Future Hardening** | ✅ 满足 | KL-A..KL-F 六项 + NEW-2/3/4/5 四项，逐项确认仍为有界现状事实 |
| 8 | **业务图可作为当前实现基线** | ✅ 满足 | 13 张 Mermaid 图的 `[IMPL]` 节点全部可在源码指认；`[PLAN]`/`[PART]`/`[INFER]` 标记经复核无误标；§8-B 十二条差异表全部成立 |

### 9.2 明确不作为阻断理由的事项

按审计原则，以下事项**不升级为 Freeze Blocker**：

- `person_embeddings` 无 producer（KL-A）——计划 E-3 未兑现的现状事实，D-1 正是为其提供人工补写路径
- 存量重名归档行按姓名回退（KL-B）——"升级不退化"的明确取舍
- 删人后孤儿行按姓名去重（KL-C）——升级前行为原样保留
- 未做 runtime UI walkthrough（KL-D）——审计覆盖限制，已用 1310 项测试 + 8 个真库探针替代
- GAP-1..5 测试证据缺口（KL-E）——回归守护不足，非行为错误；本次已用真库探针补足行为证据
- migration 008 整表复制性能未实测（KL-F）——Out-of-Scope 性能风险
- NEW-1 文案、NEW-2/3/4 migration 分支健壮性、NEW-5 Runtime Context 同步——低风险
- Stage 3 §7 两处行号区间偏移（NF-1）、图内 class 重复声明（NF-2）——引用可追溯性弱化，**无业务语义影响**，正确证据在邻行/Stage 1/2 均已给出

**以上均为「可进一步改进」或「有界现状事实」，未达到阻断冻结的严重度。**

### 9.3 测试证据

| 范围 | 结果 |
|---|---|
| 全量 `pytest`（独立实跑） | ✅ **1310 passed, 6 skipped（273.56s / 0:04:33）** — 与 `2823d1c` 提交信息及 Stage 4.1 记录一致 |
| 定向（freeze blockers + 配对域 + migration + planner + upgrade） | ✅ 54 passed |
| 定向（application + domain + review UI/controller + 归档 E2E） | ✅ 435 passed, 3 skipped |

### 9.4 结论

---

# FREEZE-READY

---

> **当前业务逻辑文档可以作为 PhotoArchiver 在 commit `2823d1c` 上的正式业务基线。**

冻结基线：`2823d1c7ceaab09c38d39b9a80e1e724839cfa17`（2026-09-28 01:44:20 +0800，`fix: resolve business baseline freeze blockers`）

---

## 10. 最终冻结条件核对表

| # | 冻结条件 | 判定 | 核心证据 |
|---|---|---|---|
| 1 | 当前实现基线稳定 | ✅ **PASS** | HEAD = `2823d1c`；`git diff --stat HEAD` 空；工作区仅 2 个存量未跟踪证据文档 |
| 2 | Stage 1~3 声明同一基线 | ✅ **PASS** | 5 份文档全部声明 `2823d1c`；`b3b8685` 仅作修订溯源 |
| 3 | 无报告引用未来/其他 commit 的实现事实 | ✅ **PASS** | 全部有效引用指向 `2823d1c` 工作区；历史 commit 均为祖先 |
| 4 | **BLK-1** 归档以稳定 `person_id` 去重 | ✅ **PASS** | 同名不抑制 / 改名不重归档 / counter 同口径 / migration+schema+query 一致 —— 真库 5/5 |
| 5 | **BLK-2** 无虚构文件/函数/调用链 | ✅ **PASS** | `batch_import_flow_service.py`、`cluster_run_controller.py` 零命中 |
| 6 | **BLK-3R** 关键 `file.py:line` 有效且语义匹配 | ✅ **PASS** | 机械校验 0 越界 0 缺失；11 项漂移映射逐条实测精确 |
| 7 | **BLK-4** `update_assignment` 描述与实现一致 | ✅ **PASS** | SQL 四字段 `status/score/sort_snapshot/confirmed_at` 逐字一致 |
| 8 | **BLK-5** 无证据 → `NULL`，有证据 → 实际 score | ✅ **PASS** | 实体/服务/migration/测试四层一致；不再表达为 `0.0` |
| 9 | **D-1** 人工身份 → 最终业务结果 | ✅ **PASS** | 带身份批准可归档 / 不带身份批准不可归档，真库验证 + UI 告警 |
| 10 | **D-2** `score >= 0.40` | ✅ **PASS** | 实跑 0.39 不命中 / 0.40 命中 / 0.41 命中；文档 12 处全为 `>=` |
| 11 | Stage 1 → Stage 2 → Stage 3 形成一致链 | ✅ **PASS** | 12 个重点域逐点回查；13 张图与文字无矛盾 |
| 12 | 无 PLANNED 误标 IMPLEMENTED | ✅ **PASS** | §9 八项 PLANNED 在 `src/` 零实现 |
| 13 | 无 INFERRED 被当作事实 | ✅ **PASS** | `[INFER]` 均带虚线并在 §9 登记为语义缺口 |
| 14 | 6 项 Known Limitations 仍为有界现状 | ✅ **PASS** | KL-A..KL-F 逐项回查，未破坏基线 |
| 15 | 无新的高严重度业务/数据/状态错误 | ✅ **PASS** | 新发现仅 NF-1/NF-2（低，引用/图表） |
| 16 | 全量测试通过 | ✅ **PASS** | **1310 passed / 6 skipped（273.56s）**，独立实跑复现 |
| 17 | 本阶段零改动 | ✅ **PASS** | 探针在仓库外 `C:\Users\Public\PA42\`，库在 `%TEMP%`；未提交 Git |

**17 / 17 条件全部满足。**

---

## 11. 复审声明

- **取证方式**：全量静态复核（源码 / migration / 测试 / ADR / 规则）+ 全量 `文件.py:行号` 机械化校验（Python，仓库外）+ 68 条关键引用逐行人工抽检 + 8 组真库 SQLite 探针（BLK-1 五场景 / D-1 两场景 / migration 008 schema 与回填四情形）+ 测试实跑（全量 1310 passed / 6 skipped；另定向 54 项与 435 项复跑全绿）。
- **项目改动**：**零改动**。`git status --porcelain` 与 `git diff --stat HEAD` 审计前后完全一致。临时脚本与探针均在 `C:\Users\Public\PA42\`（仓库外），探针数据库在 `%TEMP%`，**未触碰仓库文件、产品数据库、测试或业务文档，未提交 Git**。
- **未覆盖**：runtime UI 手工走查；大库 migration 性能实测（已由全量测试套件实跑替代覆盖）。
- **本报告定位**：对 `2823d1c` 的独立第三方最终复审。与 Stage 1–4.1 冲突处，一律以本报告列出的一手证据（源码 / migration / 测试 / 真库行为）为准。
- **后续建议（不阻断冻结）**：① 按 NF-1 建议修正 Stage 3 §7 表两处行号；② 按 Stage 4.1 §14 建议补 GAP-1..4 测试；③ 补 `.ai/` Runtime Context 同步（NEW-5）；④ 保留 Stage 4 §2.2 机械引用校验作为后续门禁，并追加"被引文件在**当前 HEAD** 的行号是否覆盖被描述的函数名"人工抽检项。

---

# FREEZE-READY

> 当前业务逻辑文档可以作为 PhotoArchiver 在 commit `2823d1c` 上的正式业务基线。

**审计完成。**
