# AUD-017 — `person_embeddings` 零生产写入者 · Owner 决策材料

- **编号**: AUD-017（全面工程健康体检 2026-09-28，台账 P2）
- **性质**: 技术决策准备——只陈述事实与可行方案，**不做最终业务选择**
- **基准**: HEAD `2823d1c`（2026-09-28）｜ 证据均经只读核验（grep + `git log -S` 全历史 + 迁移 DDL）

---

## 1. 现状（代码事实）

```text
person_embeddings（migration 002 建表，"每人一条规范嵌入"语义）
→ 当前生产读取路径（2 处，均为匹配候选集来源）:
    application/services/match_persons_service.py:155-159   _build_candidate_embeddings → list_all()
    application/services/run_recognition_service.py:66       candidates = list_all()
→ 当前生产写入路径 = 0:
    唯一写方法 infrastructure/database/sqlite_face_embedding_repository.py:42（INSERT INTO person_embeddings）
    全 src 无调用方（grep 零命中）；全 git 历史 `git log -S "face_embedding_repository.save"` 零提交
    tools/verify_upgrade_integrity.py:30 仅把表名列入升级完整性核对清单（非业务读写）
→ 候选集合因此恒空:
    任何用户的库中 person_embeddings 无行 → matcher.match() 恒返回 None
    → 识别期自动匹配能力无法形成真实闭环
→ 身份归属现状完全依赖:
    ①人工审核（ReviewDialog 身份选择器，D-1——批准时写入 person_id）
    ②配对工作台（PairingWorkbenchService.confirm → D3 兼容层写 recognition_results APPROVED）
```

**设计意图佐证**（非缺陷定性依据，而是演进承诺）：
- `docs/development/people-import-face-clustering-development-plan.md:11`："person_embeddings 没有人员样本登记入口，名单不能作为可识别的人脸候选集。"
- 同文件 :155："确认人员映射时，从该组选择合格样本写入 `person_face_embeddings`；后续 1:N 匹配基于多样本或中心特征，而不是现有单条 `person_embeddings` 覆盖式写入。"
- 该"后续"在已实施完成的阶段 C–F（冻结基线 `2823d1c`）中**未落地**——阶段 C–F 的身份链止于"配对确认写样本 + 兼容层"，未回灌匹配候选。

**测试掩蔽说明**：`tests/unit/application/test_match_persons_service.py:58` 用 `_StubFaceEmbeddingRepository` 手工注入候选——单测全绿但从未 exercising 真实空表生产路径。

## 2. 已有数据来源（现有 embedding/sample/observation/recognition 数据链）

| 数据 | 表/迁移 | 内容 | 与"候选来源"的距离 |
|---|---|---|---|
| 人脸观测 | `face_observations`（004，Stage C） | 每次 run 逐脸 bbox/det_score/quality_score/embedding（JSON 文本），`UNIQUE(run_id, photo_id, face_index)` | 原始嵌入池，按 run 组织，未归属人 |
| 人员样本 | `person_face_embeddings`（007，Stage E） | 配对确认时整簇成员观测沉淀为样本，`UNIQUE(person_id, observation_id)`，`enabled` 开关（改派时旧人样本 disabled=0） | **已按人归属的多样本库**——现役、有幂等保证、有启用/停用生命周期 |
| 聚类 | `face_clusters`/`face_cluster_members`（006，Stage D） | 簇结构与成员（source auto/manual） | 样本的分组来源 |
| 兼容识别行 | `recognition_results`（002/008） | (person, photo) APPROVED 投影（E-SG-6），confidence 三态（BLK-5） | 归档消费面，非候选面 |
| 人员规范嵌入 | `person_embeddings`（002） | `UNIQUE` person_id，embedding BLOB——**旧"每单一规范向量"语义** | 候选面（读），零写入 |
| 人员名册 | `people`（002/003） | 名单（roster_order/批次） | 身份主体 |

## 3. 方案比较（供 Owner 决策）

### Option A — 建立正式 embedding/sample 持久化链（激活 `person_embeddings`）

- **数据流**: 配对确认（confirm/manual assign）时，从该人 enabled 样本计算规范向量（如归一化算术平均，与 `NumpyCosineSimilarityLookup` 簇心口径一致）→ `FaceEmbeddingRepository.save()` 落 `person_embeddings`；改派/解除（unassign/retract）时重算或清除该人规范向量。新样本沉淀自动刷新。
- **修改范围**: `PairingWorkbenchService._sink_confirmation`/`_retract_confirmation`（+规范向量投影）、`domain/repositories/face_embedding_repository.py` 协议扩方法（按人重算）、SQLite 实现与 InMemory 替身、定向测试；**无 Schema 变更**（表已存在）。
- **优点**: 最小改动激活现有读取端（match/run 两链无需动）；"确认后同类照片自动归属"用户预期直接兑现；语义清晰（一人一向量）。
- **风险**: 与开发计划 :155 明示方向相悖（"基于多样本或中心特征，而不是现有**单条** person_embeddings 覆盖式写入"）；单规范向量对多外观人员（正侧面、光照）匹配率低于多样本 max；改派/删人时向量同步是新的状态一致性面（漏更新 → 幽灵匹配）。
- **兼容性**: 存量库 `person_embeddings` 为空 → 需一次性从既有 enabled 样本回填（幂等工具，可复用 backfill 模式）；老数据零破坏。
- **测试影响**: 需补"确认→向量落库→matcher 命中"链路测试（恰好填补 F1-1 全链缺口的组成部分）；现有 stub 候选测试不受影响。
- **人工校准影响**: 规范向量公式（均值/簇心/质量加权）成为新的校准对象，需进 Stage F 校准报告口径。

### Option B — 明确当前阶段不启用自动匹配，登记为受限能力

- **数据流**: 无变化。识别只产出观测 + 兼容行（兼容行 person_id NULL，走 D-1 人工指定）；身份归属全部经人工审核/配对工作台。
- **修改范围**: 仅治理文档——KNOWN_ISSUES 登记受限能力、manual/FAQ 披露、`docs/decisions/` 本文档结论更新为 Accepted-B；可选：删除或保留 `person_embeddings` 表与读取代码（建议**保留不动**，避免冻结基线出窗）。
- **优点**: 零代码风险、零回归面；与 D-1 裁决（"人工操作结果为最终结果"）语义完全一致；冻结基线零扰动。
- **风险**: 用户预期落差长期存在（"为什么识别完了都不自动归人"）；死表 + 死读取路径留存，后续贡献者困惑成本（本次审计已证实会掩盖事实——测试 stub 让空转不可见）；若未来启用仍需走 A/C。
- **兼容性**: 无影响。
- **测试影响**: 无强制项；可选补一条"空候选表行为"的显式回归（把现状钉死为规格）。
- **人工校准影响**: 无（不涉及阈值/公式）。

### Option C — 新数据模型替代 `person_embeddings` 作为候选来源（多样本匹配）

- **数据流**: matcher 候选构建改读 `person_face_embeddings`（enabled=1 样本）：对查询嵌入逐一余弦，取**每人多样本最大值**（max-cosine）超阈值者胜——与 Stage E `suggest_pairings` 的 sample-match 口径（规则①：max cosine ≥ 0.40）完全一致；`person_embeddings` 退役为遗留表（读路径移除，表保留或后续迁移清理）。
- **修改范围**: `match_persons_service._build_candidate_embeddings` 与 `run_recognition_service.execute` 候选段（改读样本仓储）、`domain/repositories/person_face_sample_repository.py` 扩枚举方法、SQLite/InMemory 双实现、匹配器接口语义注释、定向测试 + 与 suggest 口径一致性的交叉测试；**无 Schema 变更**。
- **优点**: 正是开发计划 :155 承诺的形态（"基于多样本或中心特征"）；与配对建议共用同一阈值口径（0.40，D-2），全系统单一匹配语义；无需维护规范向量同步（样本即真相，改派联动已由 enabled 开关天然解决）。
- **风险**: 行为变更——启用后识别期开始自动归属，compat 层与 D-1 人工身份并存时需明确优先级（自动匹配产出 PENDING 行、人工批准覆盖，现有状态机已支持，但需 owner 确认该交互）；大库性能（每人多样本逐对余弦，Python 纯算——样本量大时需复用 numpy 矩阵路径，`infrastructure/cosine_kernel.py` 可复用）；匹配口径从"单向量"变"样本集最大值"，历史可比性说明需记录。
- **兼容性**: 存量库只要有配对确认沉淀的样本即自动获得候选；无样本的人（纯名册导入、未经聚类确认）依旧不参与自动匹配——需在文档明示。
- **测试影响**: 现有 stub 候选测试需适配数据源变更；新增"多样本 max 口径 + enabled 过滤 + 与 suggest_pairings 同阈值"回归；行为变化本身需要 owner 验收。
- **人工校准影响**: 阈值语义需重新表述（样本 max 的分布与单向量不同，0.40 直接沿用需边界实测——Stage4.2 已实测配对侧 0.39/0.40/0.41，识别侧建议同口径复测三点）；进 Stage F 校准报告（同时补上 F1-2 的 match_threshold 证据缺口）。

## 4. 方案对照摘要

| 维度 | A 激活旧表 | B 登记受限 | C 样本直读 |
|---|---|---|---|
| 改动面 | 小（服务层投影） | 零代码 | 中（候选源切换） |
| 与开发计划 :155 一致性 | ❌ 相悖 | ⚠️ 中性（推迟） | ✅ 正是该形态 |
| 与 D-1 裁决兼容 | 兼容 | 完全一致 | 兼容（需定优先级交互） |
| 匹配质量潜力 | 中（单向量） | 无自动匹配 | 高（多样本 max） |
| 新增状态一致性面 | 有（向量同步） | 无 | 无（样本即真相） |
| 冻结基线扰动 | 中 | 零 | 中 |
| 校准义务 | 规范向量公式 | 无 | 阈值三点复测 |

## 5. 结论

```text
Decision Required
```

Owner 需就 Option A / B / C 做出业务选择（或在补充信息后另行裁决）。无论选择何项，建议同步：①把选择登记入 `ARCHITECTURE_DECISIONS.md`（新 ADR）；②若选 A/C，`match_threshold` 在识别侧的边界证据须补入 Stage F 校准报告（顺带闭合体检 F1-2 证据缺口）；③若选 B，KNOWN_ISSUES 与用户手册的预期管理文案须落地。
