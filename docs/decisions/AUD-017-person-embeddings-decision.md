# AUD-017 — `person_embeddings` 零生产写入者 · Owner 决策材料

- **编号**: AUD-017（全面工程健康体检 2026-09-28，台账 P2）
- **版本**: v2（Stage 11A 重新核验闭环：全部结论本轮对源码/Git/真实数据库重新取证，非转引）
- **基准**: HEAD `a01f11b`（业务代码仍为 `2823d1c` 内容，`a01f11b` 仅含治理文档）｜ 探针日期 2026-09-28
- **性质**: 技术决策准备——只陈述事实与方案边界，**不做最终业务选择**

---

## 1. 现状（本轮重新核验的代码事实）

### 1.1 写路径 = 0

```text
唯一写方法: infrastructure/database/sqlite_face_embedding_repository.py:27 save()
            （:42 INSERT INTO person_embeddings）
生产调用方: 0 —— grep 全 src 零命中（其余 .save( 命中均为 PIL/Qt/Excel 无关对象）
Git 历史:   SQL 引入于 002e3b6（仓储实现本身）；`git log --all -G` 对调用方检索零命中
            —— 历史上从未存在过任何写入者
```

### 1.2 读路径（完整清单）

| 读取方 | 位置 | 用途 | 现状 |
|---|---|---|---|
| `match_persons_service.py:159` `_build_candidate_embeddings → list_all()` | legacy 直配链 | 匹配候选集 | 候选恒空 |
| `run_recognition_service.py:66` `candidates = list_all()` | 新可追溯运行链 | 匹配候选集 | 候选恒空 |
| `delete_person_service.py:65` `list_all()` 键计数 | 删除级联预览/计数 | 统计将随人级联清空的行数 | 恒计数 0 |
| `find_by_person()`（repo :67） | — | — | **生产零调用**（仅仓储自测），彻底死方法 |

### 1.3 候选生成 → matcher 链路

```text
person_embeddings（恒空）
   └─ list_all() → candidates: dict[UUID, FaceEmbedding] = {}
        └─ CosinePersonMatcher.match(embedding, candidates)
             └─ candidates 为空 → 恒返回 None（ai/similarity_matcher.py 空候选守卫）
                  └─ 识别兼容行 person_id 恒 NULL
                       └─ 归档计划在无人工身份指定时恒为空（D-1 前提示告警）
```

### 1.4 测试 stub 对真实行为的遮蔽点（明确记录）

- `tests/unit/application/test_match_persons_service.py:58` `_StubFaceEmbeddingRepository`：
  测试手工注入候选字典并实现内存版 `save()`——**全部 matcher 单测从未 exercised 真实空表生产路径**；
  "匹配成功"类断言均建立在注入数据之上。
- 同型：`run_recognition_service` 的候选读取无专门空表行为回归（现状 = 静默零匹配）。
- 结果：单测全绿与"自动匹配从未工作过"并存（体检 X-1"三层合谋"结论）。

## 2. 真实数据库探针（2026-09-28，只读）

> 方法：将生产库 `%LOCALAPPDATA%\PhotoArchiver\photo_archiver.db` **拷贝**至临时目录后查询
> （原库零接触，探针副本用后即删）。此探针闭合业务基线 Stage1_BusinessFacts §附录
> UNKNOWN-2（"生产库 person_embeddings 是否真的为空——需读用户数据目录"）。

| 项 | 实测值 |
|---|---|
| alembic 版本 | **`003_import_batches_and_roster`**（004–008 从未在生产库执行） |
| `person_embeddings` 行数 | **0**（写路径为零的直接数据证明） |
| `person_face_embeddings` / `face_observations` / `face_clusters` / `cluster_person_assignments` | **表不存在**（生产库尚无任何样本/观测/聚类数据） |
| people / photos / folders | 546 / 473 / 2 |
| `recognition_results` | 472 行，**全部 pending、person_id 全部 NULL** |
| `archive_records` | 0（生产库从未归档） |

**结论**：真实部署上，①自动匹配从未产生过任何归属（候选 0 行 + 472 行识别结果 person_id 全 NULL 互相印证）；②样本/观测类"未来候选来源"在生产库为**零数据**——任何方案（A/C）都从空状态起步，不存在存量迁移负担；③生产库下次启动应用时 alembic 将自动执行 004→008 升级（体检已核 13 项迁移测试与升级完整性演练）。

## 3. 业务语义（先于实现细节的回答）

**问句**："首次识别时没有人员 embedding 数据，系统是否仍应当能够通过人脸聚类 + 名单顺序完成归档；后续通过人工校准/样本积累建立人员人脸样本，并用于未来自动匹配？"

### 事实（文档与代码一致的部分）

1. **前半句 = 已实现且有真库证据**：识别（观测）→ 聚类 → 配对工作台人工确认（名单顺序参与建议排序）→ 兼容 APPROVED → 归档；无需任何人员 embedding 即可闭环（D-1：人工身份即最终结果）。Stage2 规则 PR-03（样本匹配建议，≥0.40）已实现+三点边界测试。Stage3 图 B2 明确"candidates 恒空 → person_id 恒 NULL"，且**禁止**在业务图中画"自动身份确认"。
2. **后半句 = 执行计划的明文要求，但未实现**：执行计划 **E-3「后续照片匹配切换」**——"`MatchPersonsService` 匹配段改为：候选 = `person_face_embeddings`（启用态）多样本 max 余弦（D4）；≥阈值 → suggested 映射或旧链路 PENDING；低于阈值 → 进入分组审核队列"；E-4 验收判据含"**新照片优先匹配已确认样本**；低置信度进人工队列"。开发计划 :155 同向（"后续 1:N 匹配基于多样本或中心特征"）。业务基线 Stage1 :459 如实登记："多样本匹配（1:N max 余弦）接入识别 | **PLANNED（未实现）**——执行计划 E-3 未落地"。

### 冲突（需要 owner 注意的口径分歧）

| # | 冲突 | 位置 |
|---|---|---|
| K-1 | **需求 ↔ 实现**：E-3/E-4 要求"新照片优先匹配已确认样本"未实现；识别侧仍读恒空 `person_embeddings` | 执行计划 E-3/E-4 vs `run_recognition_service.py:66` |
| K-2 | **候选模型二义**：匹配读 `person_embeddings`（无生产者）、配对建议读 `person_face_embeddings`（现役）——同一"与已确认人员比对"语义存在两个候选源；基线 Stage3 B2 将其标记为"身份事实源二义"并以 [PART] 显式成框 | `run_recognition_service.py:66` vs `suggest_pairings_service.py` |
| K-3 | **E-3 的产出口径未决**：若激活新照片样本匹配，E-3 原文给出两个可选产出（"→ suggested 映射（仍需确认）**或**按旧链路 PENDING（以 D3 决策为准）"）——两种口径对"自动归属是否需要再次人工确认"的语义不同 | 执行计划 E-3 括注 |

### 待决策项

1. 三选一：Option A / B / C（§5）。
2. 若选 A/C：E-3 产出口径二选一（suggested 建议层 vs 旧链 PENDING 兼容行）——即 K-3。
3. 若选 A/C：识别侧阈值边界证据补入 Stage F 校准报告（顺带闭合体检 F1-2）。

## 4. 已有数据来源的承担能力评估

| 数据 | 表 | 能否承担"候选来源" | 关键差距 |
|---|---|---|---|
| 人员样本 | `person_face_embeddings`（007） | **能**——已按人归属、UNIQUE 幂等、enabled 开关即人工校准控制；配对建议已消费同源（PR-03 同口径 ≥0.40） | 生产库零数据（表未建，003）；识别侧消费路径未接（E-3） |
| 人脸观测 | `face_observations`（004） | 间接能——样本的原始来源；直接作候选则需先归属到人（等于绕过样本层） | 未归属人，噪声大 |
| 聚类 | `face_clusters`/`members`（006） | 间接——样本的分组上下文 | 同上 |
| 兼容识别行 | `recognition_results` | 不能——是归属的**产出**面非候选面 | — |
| 人员规范嵌入 | `person_embeddings`（002） | 语义上能但**无生产者**；且表无 model_version 列（002 仅 person_id/embedding/created_at），混合模型版本向量无从辨识 | 零生产写入、零数据 |

## 5. 方案重估（含 Stage 11A 要求的全部检查项）

### Option A — 激活 `person_embeddings`（建立投影写入链）

- **数据流**：人员/样本 →（确认/重算时投影规范向量，如 enabled 样本归一化均值）→ `person_embeddings` → matcher（现有读取端零改动）。
- **写入时机**：配对确认/手工指派时；样本增删与改派（enabled 变化）时重算。
- **数据来源**：`person_face_embeddings` enabled 样本（生产库现状为零——首次可用数据只能来自未来配对确认）。
- **embedding/模型版本**：**表无 model_version 列**——若未来更换模型（buffalo_l → 其它），新旧向量混存无法辨识，需 migration 009 增列或应用层版本约定（新边界，须 owner 知情）。
- **人员删除**：FK CASCADE 自动清理（002），无残留。
- **样本更新/重算**：每次 enabled 集变化必须重算投影——新增一条"样本↔投影"状态同步义务（漏更即幽灵匹配）。
- **去重**：UNIQUE(person_id) 单行覆盖式（旧语义，与开发计划 :155"不要覆盖式写入"相悖）。
- **migration**：表已存在；若补 model_version 需 009（冻结基线出窗，需 owner 批准）。
- **兼容旧数据**：探针证明生产库 0 行 → 无回填对象，兼容负担实际为零。

### Option B — 当前阶段明确关闭自动匹配（登记受限能力）

- **产品表现**：识别产出观测 + 兼容 PENDING 行；身份归属完全经人工审核（D-1 身份选择器）与配对工作台；现状即如此，无行为变化。
- **UI 表达**：现有审核身份选择器已就绪；建议（可选）在识别运行结果/概览页增加"自动匹配未启用，身份经人工确认"的一句说明，避免用户误以为识别失败。
- **测试策略**：补一条"空候选表 → 恒零匹配"的显式回归，把现状钉死为规格（消除 stub 遮蔽的模糊性）；其余不动。
- **后续启用条件**：owner 未来立项 Option A 或 C 时再切换；E-3 需求保持 PLANNED 登记。
- **边界**：`person_embeddings` 表与读取链保留（不动冻结基线）；E-3 冲突（K-1）以" owner 决定推迟"方式闭合而非实现。

### Option C — 样本/观测模型直读为候选源（多样本 max 余弦）

- **数据流**：`FaceObservation →（配对确认沉淀）→ person_face_embeddings（enabled）→ 多样本 max 余弦 → matcher`——与配对建议规则①（PR-03，≥0.40）完全同口径。
- **是否符合业务基线**：**是**——正是执行计划 E-3 原文与开发计划 :155 的形态；Stage3 B2 指出的"两个候选集二义"被消除（单一候选源）；Stage2 PR-03 语义直接复用。
- **重复数据模型**：`person_embeddings` 成为彻底死表（读路径一并移除）——冻结期内建议保留不删（零出窗），后续清理另行裁决。
- **人工校准**：样本即校准产物；enabled 开关即校准控制；无投影同步义务（样本即真相）。
- **历史兼容**：生产库零样本（探针）→ 无迁移/回填；启用后首批候选只能来自未来配对确认。
- **性能边界**：多样本逐对余弦为 Python 纯算，样本量大时建议复用 `infrastructure/cosine_kernel.py` numpy 矩阵路径（实现期关注点，非决策阻塞）。
- **行为变更提示**：启用后识别开始自动产出带归属建议——按 E-3 原文仍是"suggested（仍需确认）或 PENDING"，不自动写终态，与 D-1/E-SG"永不自动确认"原则兼容，但 K-3 口径需 owner 拍板。

## 6. 决策表

| 项目 | A 激活旧表 | B 登记受限 | C 样本直读 |
|---|---|---|---|
| 与当前业务基线一致性 | 相悖于开发计划 :155"非覆盖式写入" | 与 D-1/E-SG"人工身份"原则完全一致 | 与执行计划 E-3/E-4、开发计划 :155 **正合**；消除 B2 二义 |
| 数据模型影响 | 需评估 model_version 增列（migration 009） | 零 | 零（死表保留不删） |
| 实现范围 | 服务层投影 + 重算同步 + 回归 | 仅文档/一条钉死现状的回归 | 候选源切换（两服务）+ 仓储扩方法 + 回归 |
| 兼容性 | 生产库 0 行，无回填负担 | 零影响 | 生产库 0 样本，无迁移负担 |
| 测试影响 | 补"确认→投影→命中"链路 | 补空表现状回归 | stub 测试适配 + 多样本 max 口径 + 与 PR-03 同阈值交叉测试 |
| 后续人工校准 | 规范向量公式成为新校准对象 | 无 | 阈值三点复测（复用 D-2 口径）；样本质量即校准 |
| 技术债务 | 延续"单向量覆盖式"旧债 + 新增同步义务 | 死表+死读取链留存；E-3 持续 PLANNED | `person_embeddings` 死表留存（清理另行裁决） |
| 风险 | 幽灵匹配（漏重算）；模型版本混存 | 用户预期落差持续（"识别完不自动归人"） | 行为变更（自动归属建议出现）；样本量性能路径 |

## 7. 结论（Owner 裁决已登记）

```text
Owner Decision（2026-09-28，owner 任务指令正式登记）:
  Option C —— person_face_embeddings 作为后续批次样本相似度候选来源
  K-3     —— suggested 建议层（样本相似度结果仅生成 similarity_suggestion，
             不得直接形成身份确认）
  附加约束 —— 不得改变冷启动 FaceCluster → sort_key → roster_order →
             ordered_suggestion → 人工确认 → 样本沉淀 业务链；
             person_embeddings 不恢复为新的生产写入路径
```

**实现结论（Stage 11B，同日完成）**：Option C 的生产链在阶段 E 已建立并经本轮核验
与钉定——`SuggestPairingsService` 经 `SQLitePersonFaceSampleRepository.list_enabled()`
（enabled=1，`ORDER BY person_id, created_at, id` 确定序）读取候选样本，经
`NumpyCosineSimilarityFactory`（量化 6 位）计算多样本 max 余弦，规则①产出
`sample_match` 建议（≥0.40 恰等命中，D-2）、规则③冷启动位次建议补位，全部落
`suggested` 层（绝不自动确认）；人工确认后样本沉淀幂等（UNIQUE + 已沉淀观测跳过）。
**本阶段新增**：真实 SQLite 闭环集成测试（`tests/integration/test_aud017_sample_suggestion_sqlite.py`，
4 项——主闭环含 disabled 排除与重复确认幂等 / 零样本冷启动 / 平分确定性 tie-break /
维度不一致 fail-closed）、domain 规则钉定 3 项（cluster<persons 不强配 / 平分首位 /
高分胜出）、kernel 维度守卫钉定 2 项；决策登记 ADR-047。**生产代码零改动**（能力已存在，
本阶段完成证明与登记）；`person_embeddings` 读路径保留为兼容链遗留（无写入者、候选可
证恒空，ADR-047 登记），未恢复写入路径。
