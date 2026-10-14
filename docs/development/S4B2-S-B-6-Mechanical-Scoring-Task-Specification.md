# S4B2 S-B-6 Mechanical Scoring — Task Specification（修订版 R3）

- **状态**：`READY-FOR-OWNER-REVIEW`（R3 修订完成，待 Owner 审查）/ `IMPLEMENTATION-NOT-AUTHORIZED`
- **依据**：Owner Approval Token `S4B2-OWNER-V2-ARCH-FINAL-MANIFEST-DUALBIND-ISOLATION-ATTESTATION-APPROVED`；《S4B2 Prediction Artifact v2 — Final Architecture Decision》（APPROVED WITH CONDITIONS，登记 `docs/decisions/S4B2-v2-architecture-final-decisions.md`）；Prediction Artifact v2 Architecture Specification v2.2（**会话交付版；仓库无独立文件——不得声称其已存在于仓库**）；S4B2 治理链决策文档
- **执行角色**：经 Owner 对本任务书**明确批准开发**后，由 dev-AI 实施；完成后由 review-AI 独立审计
- **编制日期**：2026-10-09（R3）
- **修订记录（R3 相对 R2）**：B1 §5.1 恢复 `source_member_count`（独立计数 + 哈希域 + Layer A 一致性检查边界 + 4 类新测试）；B2 §4.1 I-5 三层语义修订（历史存储值 ≠ 当前字节；v2 Isolation Revalidation 要求评估侧同样实算当前字节；无冻结新鲜度机制 → `unprovable`）+ 负向测试 T-A14/T-A15；B3 §4.7 Assurance 全条件映射 + 四场景 + 维度责任分离；B4 T-A3/T-A4 拆分（未重算哈希的篡改 vs 重算哈希后的语义伪造）；B5 `computed_at` 唯一放置（Envelope，**提案非已批准**，ORD-6）；B6 §5.2 规则逐条来源标注【①/②/③】+ 新增 ORD-8 + 字段编码约定统一（§5.2.7）；B7 测试编号全量统一（§6.0 索引；T-P*/T-L*/T-R* 悬空引用修复）+ Input Classification Gate 与 v1 拒绝语义分离。§五 附加检查 5.1–5.4 全部落地。
- **编制纪律**：所有代码引用为仓库实证；"不存在"的能力如实标注；证据缺口显式记录；**新设计不得冒充冻结契约**。

---

## §1 硬前置（进入实现前必须逐项核验）

1. **最终架构决策**已登记且 Token 有效（APPROVED WITH CONDITIONS；条件表见决策文档 §2）。
2. **S-B-1..5 = VERIFIED**（独立审计探针 89 / 30 / 18 / 45 / 44 全过）。
3. **质量门基线**（2026-10-09 实测）：pytest **1703 passed / 8 skipped / 0 failed**；ruff 全绿；mypy **279 文件**零问题。
4. **前序语义冻结**（逐项核验）：K=A+C；Evaluation Scope=DEFERRED；Cluster Roll-up 不属 S-B-6；PFE=MINIMAL-SCHEMA；D7=NO。
5. **结构事实**（代码实证）：v1 = reference-entry-keyed（禁作评估工件）；src 中**无** `sb-member-max-cosine-v1` producer、**无** Target Manifest 实现、**无** Mechanical Scoring 实现、**无** UUIDv5/namespace 常量。

## §2 职责与禁止（固定）

**职责**：`Frozen Prediction Artifact v2 + Frozen Target Manifest + Reference Snapshot + Frozen Ground Truth → member-level mechanical scoring`（按冻结 Evaluation Unit）。**当前 Consumer 有权处理的 prediction source 仅 S-B**（阶段范围 = S-B-6；schema 枚举含 S-A/S-C ≠ 阶段授权，见 §5.2.4 / §4.7）。

**禁止**：原十条（修改工件/GT/Assignment、补 score、重跑 matcher、重新生成 prediction、决定 Evaluation Scope、threshold 搜索、ROC/PR、Precision/Recall、FA/FR、Coverage、Auto-confirm、Auto-archive）+ 不得暗示生产预测；fixture ≠ 真实预测；不得凭架构批准开始实际评分；不得创建/发布生产 Manifest/Artifact；不得改 S-B-1..5 冻结行为；不得新增 Migration；不得改 PFE Schema；不得修改 v1 契约；不得静默修正非法预测记录。

## §3 能力清单（区分：已有 / 计划新增 / 未证实）

### 3.1 已有（复用；接口名以现实现为准，代码实证）

| 能力 | 实际接口 | 位置 |
|---|---|---|
| 不可变文件层 | `SnapshotStore.write_atomic / read_bytes / path_exists`（`.part`+`os.replace`、拒绝覆盖） | `application/ports/snapshot_store.py` + `infrastructure/filesystem/snapshot_store.py` |
| Snapshot 读/验 | `ReferenceSnapshotService.read_document / verify_snapshot(cross_check_current_state)` | `application/services/reference_snapshot_service.py` |
| 隔离守卫（S-B-2，**摄入期语义，冻结不改**） | `ReferenceIntakeService.build_evaluation_photo_set / evaluation_content_hashes / evaluation_member_observations / verify_reference_photos / verify_reference_cluster_samples` | `application/services/reference_intake_service.py` |
| 资格证据链（S-B-3） | `ReferenceEligibilityService.evaluate_samples`（E-01..E-06；E-05 四查 `:418-446`） | `application/services/reference_eligibility_service.py` |
| 字节哈希 | `ContentHashCalculator.calculate` = **文件原始字节 SHA-256**（`:7-27`） | `infrastructure/image/content_hash_calculator.py` |
| v1 工件构建/验证 | `PredictionArtifactService.build_artifact / verify_artifact`（**保留，仅 v1 用途**） | `application/services/prediction_artifact_service.py` |
| 冻结 GT 只读读取 | `CalibrationAnnotationRepository.list_ground_truth(dataset_id, dataset_version)`（mode=ro 纪律） | `domain/repositories/calibration_annotation_repository.py` |

### 3.2 计划新增（本任务书范围；设计细节在实现方案定稿）

`target-manifest-v1` builder+verifier（§5.1）；`prediction-artifact-v2` builder+verifier（§5.2）；`isolation-attestation-v1` builder+verifier（§4.1）；Mechanical Scoring consumer + GT 三态派生（§4.7/§6）；验证层级六维状态机与准入判定（§4.7）；确定性 `prediction_id` 派生（§4.4）。

### 3.3 未证实 / 不存在（不得宣称已存在）

- **`sb-member-max-cosine-v1` Prediction Producer：NOT IMPLEMENTED**（全仓仅字符串常量/元数据 `prediction_artifact_service.py:26/:88` + 测试构造）。
- **生产 Manifest / 生产 Artifact：未发布、未经授权**；**Actual Evaluation 与正式指标：未授权**。
- **守卫侧规则版本常量：不存在**（§4.1 RULESET 为新契约标识）。
- **UUIDv5 namespace 常量：不存在**（§4.4 候选值待裁）。
- **字节哈希"缓存新鲜度"证明机制：不存在**——生产库仅存扫描/回填时点的 `metadata_modified_at / metadata_file_size_bytes / metadata_content_hash`（R1 会话内 %TEMP% 副本只读检查实证），**无任何冻结契约**定义"以 stat 相等证明哈希仍代表当前字节"的语义；不得虚构该机制（§4.1 I-5）。
- **v2.2 Architecture Specification：仓库无独立文件**（会话交付）。

## §4 八项强制携带项（每项含验收标准）

### §4.1 隔离证明契约（`isolation_attestation`）

**RULESET（标识已冻结）**：

```text
规范标识值（本任务书冻结，实现不得更改）: isolation-attestation-rules-v1
代码常量变量名（实现阶段确定，候选）    : ISOLATION_ATTESTATION_RULESET
规则集内容 = §4.1 表 I-1..I-7 的检查集合 + 各检查输入定义 + canonical 规范化 + 哈希域
```

- **权威来源**：S-B-2 / S-B-3 冻结规则（14 硬约束 #1/#4/#8 + E-05 四查 + 守卫检查集；逐条代码引用见映射表）+ 本任务书 §4.1 映射与规范化定义；
- **变更规则**：检查集合 / 输入 / 规范化 / 哈希域任一变化 → 新标识值（`…-v2`）+ 新 Owner Gate；
- **旧版 Attestation**：按其自身记录的 RULESET 值验证；不得自动升级/迁移/按最新规则回退验证；
- **fail-closed**：RULESET 缺失 / 未知 / 不兼容 → 拒绝（不得 auto-pass）；
- **守卫现状如实**：守卫源码无规则版本常量；本标识只作为新契约的治理标识。

**检查 ↔ 冻结规则 ↔ 现实现 ↔ attestation 记录**：

| 检查 ID | 冻结规则（权威） | 现实现 | attestation 记录 |
|---|---|---|---|
| I-1 `photo_id 集合互斥`（主不变量） | 14 硬约束 #1/#4；S-B-2 `verify_reference_photos`（`reference_intake_service.py :160-165`） | 参考照片集 ∩ EvalPhotoSet=∅（EvalPhotoSet 经 `_evaluation_membership :283-322` 动态重建） | `reference_photo_set_sha256` / `eval_photo_set_sha256` / `intersection_count=0` |
| I-2 `same-cluster` | E-05-same-cluster（`:425-429`）；S-B-2 (b)（`:227-231`） | observation ∉ eval member observations | `eval_member_observations_sha256` / `offending_count=0` |
| I-3 `photo-on-eval` | E-05-eval-photo-isolation（`:420-424`）；S-B-2 (c)（`:233-237`） | photo_id ∉ EvalPhotoSet | 逐 photo 结果 |
| I-4 `cross-run` | E-05-cross-run（`:435-438`） | 参考照片全部 observation 的 run ⊆ 参考 Run 集 | **参考 Run 集权威派生**（见下）+ 逐 photo 比对结果 |
| I-5 `byte-hash`（R3 修订，见下） | E-05-content-hash（`:439-444`）；S-B-2 `_verify_content_hashes`（`:324-344`） | 两侧均以**当前文件字节实算** SHA-256 后比对（v2 契约；守卫冻结语义见边界注） | 两侧照片逐张 `current_byte_sha256` + 比对结果 + 不可读清单 |
| I-6 `dangling/existence` | S-B-2（`:222-226`） | 成员 observation / photo 可解析 | 构建期执行证据引用 |
| I-7（辅助，非隔离判定） | 14 硬约束 #8（enabled 按 snapshot 冻结） | snapshot entries `enabled` | 引用 snapshot 内容 |

**I-4 参考 Run 集权威派生（不得臆造字段）**：
- Snapshot schema 实录（`SnapshotEntry :106-136`）：每条 entry 携带 `provenance.recognition_run_id / cluster_run_ids / assignment_ids / eligibility_decision`；**快照无顶层 Run 集字段**；
- **权威派生**：`reference_recognition_run_ids := {entry.provenance.recognition_run_id}`（全 entries 集合并，canonical 排序）→ 写入 attestation payload；
- **来源交叉核对**：调用方另行提供 Run 集参数时 → 必须与派生集**逐元素相等**，否则拒绝（**不得接受任意调用方 Run 集并入档后声称验证成功**）；
- **执行**：对每张参考照片重读其全部 observation 的 recognition run（源端只读），必须 ⊆ 派生集；不可解析 → `unprovable`；entry 的 `recognition_run_id` 缺失/格式非法 → 拒绝。

**I-5 字节证据三层语义（R3 修订，B2）**：

```text
历史存储值 = metadata_content_hash（回填时点计算并存储；时点语义）
当前实算值 = 验证时点对文件字节重新计算的 SHA-256（ContentHashCalculator；实证为原始字节哈希）
可证明的缓存新鲜度 = 以已有冻结机制证明"存储值仍代表当前字节"
```

- **合法格式的历史哈希不必然代表当前文件字节**——仅凭 64 位十六进制格式合法**不得**声称"已证明当前内容"；
- **v2 Isolation Revalidation 契约（新增，评估期）**：参与字节互斥判定的**评估照片与参考照片均在验证时点实算当前字节 SHA-256**（`current_byte_sha256`）；历史存储值仅可作为**信息性记录**（不得作为当前字节证据）；参考侧与评估侧一致适用本契约；
- **缓存新鲜度路径**：仓库中**不存在**可依据的冻结新鲜度证明机制（§3.3 实证）→ 该路径不可用，不得虚构；**当前字节不可获得（文件缺失/不可读）→ 该项 `unprovable`，不得通过**；
- **S-B-2 冻结边界（不得修改、不得互斥）**：S-B-2 守卫的"评估侧 stored 优先 / 缺失实算"是其**摄入期**冻结行为（`evaluation_content_hashes`，语义 = 摄入加速），**不修改**；v2 Isolation Revalidation 是**评估期新契约**，定义更严格的证据标准；guard 的历史判定不因 v2 契约无效化；v2 判定**不得**只凭 guard 存储值成立；两者不得互相回写或互相引用为对方证据；
- **禁止以 embedding 哈希替代照片字节哈希**（任何层级）。

**Attestation canonical payload**：

```text
schema_version : "isolation-attestation-v1"
ruleset        : "isolation-attestation-rules-v1"
dataset_id / dataset_version
cluster_run_id
target_manifest_id / target_manifest_sha256
reference_snapshot_id / reference_snapshot_sha256
reference_recognition_run_ids[]（canonical 排序，按上方派生）
checks[]       : { check_id, rule_ref, inputs_digest, result: pass|fail|unprovable,
                   evidence_refs[], detail }
unprovable_reasons[]
（envelope，不入哈希域：attestation_id / created_at）
isolation_invariant_sha256 = sha256(canonical(payload))
```

**语义**：`isolation_invariant_sha256` 的摘要对象 = 上述结构化记录；**摘要本身不构成隔离证明**；通过的声明条件 = 实际验证执行 ∧ 全部检查 `pass` ∧ 证据完整可复核 ∧ 身份绑定正确。
**参考照片字节不可读的处置**：可生成仅用于**诊断**的失败结果 / `unprovable` 记录；**不得**发布有效 Attestation；**不得**生成"隔离验证通过"结论；**不得**进入评分。
**验收标准**：T-A1..T-A16（§6 A 类）。

### §4.2 在线与离线证据边界

| 层（维度见 §4.7） | 能证明 | **不能**证明 | 输入类型 |
|---|---|---|---|
| Layer A（Manifest / Artifact / Attestation 文件自身完整性） | 文件未篡改（SHA 重算）、计数自洽、身份唯一、集合与**记录值**相等、结构合法 | 源成员完整；隔离检查重执行 | 纯文件（离线） |
| Layer B（源成员完整性） | 指定 Run ∩ Dataset Cluster Set 的成员**无漏项/多项/重复/跨 Run/photo_id 错配** | ——（源完整性权威即本层） | 重读源（DB 只读） |
| Isolation Revalidation | 隔离检查在验证时点的实际结果（含两侧当前字节实算） | —— | DB + 两侧照片当前字节 |

**规则**：文件不可读 / 源数据不完整 / 源端核验未完成 → **不得自动通过**；按 §4.7 六维逐维报告；**禁止以文件自哈希代替源成员完整性证明**；Layer A 通过不得替代 Layer B。
**验收标准**：T-R1（离线六维报告断言）/ T-M6（Layer A 通过但源遗漏之检出）/ T-A11（维度不得互相冒充）/ T-A12（必需层 not-run → 拒绝评分）。

### §4.3 `photo_id` 集合互斥（明确隔离不变量）

- **不变量**：`ReferencePhotoSet（snapshot entries）∩ TargetPhotoSet（manifest entries）= ∅`；且快照照片 ∉ EvalPhotoSet（动态重建）；
- **输入证据**：两侧工件内容（photo_id 集 + 各自 SHA）；比对基准 = 两侧**当前字节实算**哈希（§4.1 I-5）与 photo_id 集合；
- **失败条件**：交集非空 / 任一侧不可重建 / 任一侧当前字节不可得（→ `unprovable`）→ fail-closed；
- **验收标准**：T-A8（photo_id 交集拒绝）/ T-A9（同字节异 `photo_id`）/ T-A13（两侧集合摘要离线可复算）/ T-A10（跨 Run 归属）。**编号说明**：R2 中的自定义编号 T-P1/T-P2/T-P3 已**退役**，分别映射至 T-A13 / T-A9 / T-A10（见 §6.0）。

### §4.4 `prediction_id` 确定性（UUIDv5 规范化）

- **条目权威身份** = `(cluster_run_id, cluster_id, observation_id)`（复合键，必入 canonical payload 与哈希域）；
- **派生规则（固定）**：

```text
prediction_id = uuid5(NAMESPACE, identity_string)
identity_string = "<cluster_run_id>|<cluster_id>|<observation_id>"
    每个 UUID = RFC 4122 小写带连字符标准文本形式；分隔符 "|"（U+007C）；
    编码 ASCII/UTF-8 兼容；字段次序固定 cluster_run_id → cluster_id → observation_id
NAMESPACE = 固定 UUIDv5 namespace 常量（候选见下）
```

- **跨进程独立重派生**：任意进程按同 namespace + 同 identity_string 重派生必须等于记录值；不一致 → 拒绝；
- **哈希域**：`prediction_id` 属于 canonical payload 与哈希域；
- **namespace 候选（仓库无既有批准值——grep 实证）**：

```text
候选值: 4b60862f-952f-5094-98d2-09df3f32d886
配方  : uuid5(uuid.NAMESPACE_URL,
             "https://photoarchiver.local/s4b2/prediction-artifact-v2/prediction-item")
状态  : OWNER-DECISION-REQUIRED（ORD-4；候选未经批准，不得表述为已批准常量）
```

- **理由**：唯一同时满足"确定性 + 可独立复算 + 不依赖调用方纪律"的方案；**禁止重复 v1 的"默认 uuid4 + 入哈希域"模式**。
- **验收标准**：T-D1（三分确定性）/ T-D2（缺失拒绝）/ T-D3（篡改重派生不一致拒绝）/ T-D4（跨进程重派生相等）。

### §4.5 双绑定（Target Manifest + Reference Snapshot）

- 字段：`target_manifest_id` + `target_manifest_sha256` + `reference_snapshot_id` + `reference_snapshot_sha256`；
- **校验（对称）**：①ID 与读取文档 id 一致；②SHA-256 按**实际文件内容重算**；③不变量只认 ID+SHA（禁 path/filename/mtime/size）；④同内容不同 ID 不得视为相同身份（拒绝）；⑤任一缺失/不匹配/篡改/无法验证 → 拒绝评分；⑥artifact ↔ manifest 逐项双射（每 entry 恰一条预测；禁 orphan/缺失）；
- **注意**：绑定成功**不等于**内容合法——Snapshot 的 schema / 内部完整性 / 源端核验为独立准入条件（§4.7 Reference Snapshot Validation）。
- **验收标准**：T-B1..T-B8（T-B1..T-B4 共享同一断言位置——ID/SHA 各自匹配）/ T-S1..T-S5。

### §4.6 D5 / D-SB-7 全字段对齐

- 逐项对齐表 = §5.2.1 / §5.2.2 / §5.2.3（7 属性 + **来源标注【①/②/③】**）；v1 派生字段逐项追溯 = §5.2.5；编码约定 = §5.2.7；
- **声明**：未静默删除任何已冻结强制字段；无"约等于"式未决映射；命名与时间语义歧义按 §5.2.2 专项处理（含 ORD-5 / ORD-6）；
- **验收标准**：T-C1..T-C12 + T-D1..T-D4 + §7.2 的 ORD 确认。

### §4.7 验证层级与准入状态机（含 B3/B7 修订）

**Gate 0：Input Classification Gate（B7.2，前置且终止性）**：

```text
input_class ∈ {prediction-artifact-v2, prediction-artifact-v1, unknown}
    v2      → 进入准入公式
    v1      → REJECT-TERMINAL（按契约拒绝；报告字段见下；测试断言成功；无评分产物）
    unknown → REJECT-TERMINAL（按契约拒绝）
```

**六维分离（不得合并为单一总判）**：

| 维度 | 必须表达的事实 | 枚举 |
|---|---|---|
| Layer A | Manifest / Artifact / Attestation 文件自身完整性与内部一致性（Attestation 文件专项结果由 Attestation Integrity 单独给出；Layer A 非笼统总判） | `pass / fail / not-run` |
| Layer B | 从指定 Run 与 Dataset 源数据重核成员完整性 | `pass / fail / not-run / unprovable` |
| Attestation Integrity | Attestation 记录自身哈希 + schema + canonical 重算 | `pass / fail / not-run` |
| Isolation Revalidation | 隔离检查是否实际执行及独立复核结果（对齐真实源证据） | `pass / fail / not-run / unprovable` |
| Attestation Assurance | 证据支持的保障级别（派生） | `valid-and-verified / internal-only / unprovable / invalid` |
| Scoring Admission | 准入判定（**由公式导出，非独立输入**） | `true / false` |

**Attestation Assurance 确定性映射（B3，全条件）**：

```text
Support（支撑条件，三者必须）:
    ① Ruleset = known-and-compatible（RULESET 已知且兼容）
    ② Bindings = pass（Target Manifest 与 Reference Snapshot 的 ID+SHA 绑定正确）
    ③ Evidence = complete-and-reviewable（必要证据完整且可复核）

Integrity = fail                                        → Assurance = invalid
Revalidation = fail                                     → Assurance = invalid
Integrity = pass ∧ Revalidation = pass ∧ Support=fail    → Assurance = invalid
Integrity = pass ∧ Revalidation = pass ∧ Support 无法判定 → Assurance = unprovable
Integrity = pass ∧ Revalidation = pass ∧ Support=pass    → Assurance = valid-and-verified
Integrity = pass ∧ Revalidation = not-run               → Assurance = internal-only
Integrity = pass ∧ Revalidation = unprovable            → Assurance = unprovable
Integrity = not-run（文件缺失/不可读）                    → Assurance = unprovable
```

- **文件完整性验证通过 ≠ 隔离验证通过**（显式分离，不得互相代替）；
- **维度责任分离（不得对同一失败输入给出矛盾结论）**：Integrity 只判"记录自身"；Revalidation 必须**独立复核检查结果与真实源证据**（承担语义伪造检出责任）；Layer A 不承担源端真实性；Assurance 只做确定性汇总；Admission 只由公式导出。

**必须覆盖的四场景（断言见 T-A16）**：

```text
场景1 仅 Attestation 自身哈希有效、隔离检查未执行 → internal-only           → 拒绝评分
场景2 真实源检查发现隔离失败                        → invalid（或对应 fail 维） → 拒绝评分
场景3 检查无法执行或必要证据缺失                    → unprovable               → 拒绝评分
场景4 文件完整性、检查、证据与绑定全部通过          → valid-and-verified       → 允许（需其余准入全过）
```

不可通过把枚举字段填为 `pass` 替代真实验证。

**评分准入公式（含 §五 附加条件的完整版）**：

```text
（Gate 0 通过，input_class = v2 后）
admit_scoring ⇔
    LayerA = pass
    ∧ LayerB = pass
    ∧ Attestation Integrity = pass
    ∧ Isolation Revalidation = pass
    ∧ Attestation Assurance = valid-and-verified
    ∧ Manifest Binding = pass
    ∧ Snapshot Binding = pass
    ∧ Manifest Contract = pass                    （§5.1 全部不变量）
    ∧ Artifact Contract K = pass                   （§5.2.4 合法状态组合）
    ∧ Prediction Source Authorization = pass       （本阶段仅 S-B；S-A/S-C → 拒绝）
    ∧ Frozen GT Validation = pass
    ∧ Reference Snapshot Validation = pass
    ∧ v1 Rejection Check = pass
```

- **v1 Rejection Check 语义（B7.2，与执行状态/输入判定分离）**：
  `v1 Rejection Check = pass ⇔ 输入分类与处置一致`——v2 输入 → `not-required`（=pass）；v1 输入 → 已按契约 `rejected-as-required`（=pass，且运行在 Gate 0 终止）；v1 输入未被拒绝 → **fail**，且运行以拒绝告终、不得进入评分。**报告三字段分离**：`input_class` / `rejection_outcome ∈ {rejected-as-required, not-required, bypassed-error}` / `admission`。正确拒绝 v1 = 测试断言成功 ∧ `admission=false`，不得记为测试失败，也不得因拒绝检查通过而放行 v1。
- **Prediction Source Authorization**：`pass ⇔ prediction_source == "S-B"`；S-C / S-A / 未知 → 拒绝（**schema 枚举合法 ≠ 阶段授权**；fixture 来源声明不能替代 source eligibility / Snapshot / Manifest / GT / 隔离验证）。
- **Frozen GT Validation（六查，只读派生）**：①GT Target Cluster Set 与 Dataset Target Cluster Set 严格一致；②每目标 Cluster 恰一有效 verdict；③无缺失/无重复；④PERSON 身份可解析；⑤三态独立（枚举携带来源，禁止 NULL 塌缩）；⑥只读——不写 Manifest、不改 Frozen GT。
- **Reference Snapshot Validation**：schema_version 合法 + 内容哈希重算 + 计数/身份唯一/provenance 完整 + 源端核验（`verify_snapshot(cross_check_current_state=True)`）通过；不得仅凭 ID/SHA 绑定成功认为内容合法。
- **失败语义**：任一条件 `fail / 缺失 / not-run / unprovable` → **NO SCORING**（显式"不可评分状态"，附六维明细与拒绝原因）。
- **验收标准**：T-A11 / T-A12 / T-A16、T-S1..T-S5、T-G1..T-G6、T-R1..T-R3、T-C10 / T-C12。

### §4.8 生产无关性声明（含 Fixture-only 边界）

```text
1. Actual Evaluation 的统计口径和指标政策尚未批准。
2. sb-member-max-cosine-v1 Prediction Producer 尚未实现。
3. 测试 Fixture 不等于真实生产预测。
4. 本任务书不授权创建或发布生产 Manifest / Artifact，也不授权启动 Actual Evaluation。
```

Fixture 仅用于授权的契约/离线测试路径；必须在测试定义、输入来源与报告中标注；不得推导生产 Artifact 已存在；不得据代码/测试通过启动 Actual Evaluation；生产工件受独立授权；**不得把"无 Producer 时只接受 Fixture"实现为绕开来源验证的通用生产准入规则**；**Fixture 来源声明不能替代** Manifest / Snapshot / GT / 隔离证据与哈希验证（准入公式不因 fixture 减免任何条件）。
**验收标准**：T-N1 / T-N2 / T-N3。

## §5 Target Manifest 与 Prediction Artifact v2 契约

### §5.1 Target Manifest 契约（`target-manifest-v1`，含 B1 修订）

- **权威来源链**：`Frozen Dataset → Target Cluster Set（权威）→ cluster_run_id（仅世代锚）→ Target Cluster Members → Manifest`；禁止以"Run → 全部 face_cluster_members"为人口来源；
- **Content（B1 恢复）**：`schema_version / dataset_id / dataset_version / cluster_run_id / dataset_cluster_ids[]（canonical 排序）/ cluster_count / entry_count / source_member_count / entries[]: {cluster_id, observation_id, photo_id}`；**Envelope**：`manifest_id（不入哈希域）/ created_at（不入哈希域）/ manifest_sha256`；
- **两计数分别定义、分别计算（不得相互代替）**：

```text
source_member_count = 构建时从钉定 Run 中属于 Dataset Cluster Set 的源成员
                      实际观察到的数量（构建期实测计数）
entry_count         = 实际写入 Manifest 的成员条目数
两者均进入 canonical payload 与 SHA-256 哈希域（确定性输入）；
Layer A 内部计数一致性检查：entry_count == source_member_count
```

- **Layer A 计数相等只证明记录内部自洽，不证明源成员完整**（显式边界）；
- **Layer B**：重读钉定 Run ∩ Dataset Cluster Set 的全部源成员，验证 **漏项/多项/重复/跨 Run/photo_id 错配** 五类；
- **Build（fail-closed）**：①读冻结 dataset membership → Target Cluster Set；②读锚定 Run cluster 集；③单向包含校验 `Target Cluster Set ⊆ Run Cluster Set`（缺失 → NO MANIFEST）；④**Run 额外 Cluster：不得导致失败**，仅构建报告记录（信息项）；⑤`Manifest Cluster Set == Dataset Cluster Set`（严格）；⑥成员读取 + 五类校验（任一非空 → NO MANIFEST；photo_id 取源 observation 实际值）；⑦canonical → sha → 原子发布 → 发布后验证；
- **`run_cluster_count`（若保留）**：Run 全量 Cluster 的诊断计数，**与 `source_member_count` 完全不同、不得互为替代**；其字段位置与哈希地位 = **ORD-3（待裁）**；
- Round-1 锚：44 clusters / 1441 members（fixture 参照）。
- **验收标准**：T-M1（集合严格相等）/ T-M2（额外 Cluster 非失败）/ T-M3（缺失拒绝）/ T-M4a..e（成员五类）/ T-M5（两计数不一致拒绝）/ T-M6（计数相等但源遗漏——Layer A 不得冒充完整性，Layer B 必须检出）/ T-M7（Layer A pass ∧ Layer B fail 显式区分）。

### §5.2 Prediction Artifact v2 契约（`prediction-artifact-v2`）

> **规则来源标注（B6）**：【①】已批准的 Owner 决策原文；【②】已冻结契约（D5 / D-SB-7 / K / §25 / D3=A）；【③】本任务书提出的新设计——等待 Owner 决策（ORD 项）。**新设计不得冒充冻结契约。**

#### §5.2.1 逐项预测字段（canonical payload 内；7 属性）

| 字段（canonical） | 业务含义 | 必填性 | 哈希域 | 派生? | 权威来源 | v1 兼容 |
|---|---|---|---|---|---|---|
| `cluster_run_id` | 目标簇世代（身份） | 必填非空 | ✓ | 否 | 【①】最终架构决策（Target Member identity） | v1 无（新） |
| `cluster_id` | 目标簇（身份） | 必填非空 | ✓ | 否 | 【①】+【②】D5 | v1 无 |
| `observation_id` | 目标成员观测（身份） | 必填非空 | ✓ | 否 | 【①】 | **v1 同名不同义**（不迁移） |
| `photo_id` | 目标照片 | 必填非空 | ✓ | 否 | 【①】 | **v1 同名不同义**（不迁移） |
| `prediction_id` | 逐项身份（UUIDv5） | 必填非空 | ✓ | **是**（派生） | 【③】§4.4（ORD-4 namespace） | v1：uuid4 默认（模式弃用） |
| `prediction_type` | `predicted / no-candidate` | 必填非空 | ✓ | 是（由 top1 空否导出，仍落盘） | 【②】§25 | v1 同义 |
| `top1_person_id` | 模型 top-1 | no-candidate 时必填可空（NULL）；否则必填非空 | ✓ | 否 | 【②】D5 权威字段#7 + 【①】 | v1 `predicted_person_id`（映射） |
| `top1_score` | top-1 原始分（S-B=raw cosine） | 条件（§5.2.4） | ✓ | 否 | 【②】D5 + K=A+C | v1 `score`（映射） |
| `top2_person_id` | 模型 top-2 | 必填可空（NULL 合法） | ✓ | 否 | 【②】D5（保留） | v1 无 |
| `top2_score` | top-2 原始分 | 条件（§5.2.4） | ✓ | 否 | 【②】D5 + 【③】成对规则（ORD-8） | v1 无 |
| `rank` | top1 序位（1 / NULL） | 必填可空 | ✓ | **是** | 【③】派生规则（ORD-1） | v1 `rank` |
| `margin` | top1−top2（或 NULL） | 必填可空 | ✓ | **是** | 【①】公式（修订冻结 1 §4）+ 【③】表达（ORD-1） | v1 `margin` |
| `evidence_winning_reference_observation_id` | 取得 max cosine 的参考样本（证据） | 必填可空 | ✓ | 否 | 【①】§六.3 约束 + 【③】tie-break（ORD-2） | v1 无 |

#### §5.2.2 工件级字段（canonical payload 内）

| 字段（canonical） | 业务含义 | 必填性 | 哈希域 | 派生? | 权威来源 | v1 兼容 |
|---|---|---|---|---|---|---|
| `schema_version` | `"prediction-artifact-v2"` | 必填非空 | ✓ | 否 | 【②】本链 schema 模式 | v1 不同值（并列不混淆） |
| `prediction_source` | `S-B / S-A / S-C` 源判别 | 必填非空 | ✓ | 否 | 【①】§七（保留）+ v1 既有 | v1 同名同义 |
| `scorer_version` | 预测方法/模型版本 | 必填非空 | ✓ | 否 | 【②】**D5 正式名**；命名归并 = ORD-5（待裁） | v1 `prediction_method_version`（映射备注） |
| `isolation_invariant_sha256` | `sha256(canonical(isolation_attestation))` | 必填非空 | ✓ | 否 | 【②】D5 +【①】OG-1（方案①） | v1 无 |
| `reference_snapshot_id` / `reference_snapshot_sha256` | 参考侧双绑定 | 必填非空 | ✓ | 否 | 【②】D-SB-7 | v1 同名 |
| `target_manifest_id` / `target_manifest_sha256` | 目标侧双绑定 | 必填非空 | ✓ | 否 | 【①】OG-2=A | v1 无 |
| `dataset_id` / `dataset_version` | 数据集身份 | 必填非空 | ✓ | 否 | 【②】D5 | v1 同名 |
| `threshold` | 恒 NULL（未批准前） | 必填（值恒 NULL） | ✓ | 否 | 【②】D5 §19 / v1 冻结继续 | v1 同名 |
| `input_population_scope` | 参考侧冻结人口政策**逐字记录**（**非 Evaluation Scope 语义**，§5.2.5） | 必填非空 | ✓ | 否 | 【①】§七（保留）+ v1 §10 | v1 同名（语义收窄） |
| `entry_count` | 预测条目数 == manifest entry 数 | 必填非空（int） | ✓ | 是（计数一致性可复算） | 【③】本任务书 | v1 有（语义对齐目标侧） |
| `cluster_count` | 目标簇数 == manifest cluster_count | 必填非空（int） | ✓ | 是 | 【③】本任务书 | v1 无（新） |
| `score_semantics` | sb-member-max-cosine-v1 描述性元数据 | **定位待裁（ORD-7）**：建议保留为必填可空、非权威 | ✓（若保留） | 否 | 【③】降级提案（ORD-7） | v1 §18 |
| `git_commit` | 构建提交（补充溯源） | **定位待裁（ORD-7）**：建议保留为必填可空、非权威链 | ✓（若保留） | 否 | 【③】降级提案（ORD-7） | v1 §17 |

**`computed_at` / `created_at`（B5 修订）**：`computed_at` = **预测计算时间**；`created_at` = **工件文件创建时间**；两者语义不同，**不得默认等价**。**唯一放置（本任务书提案，未获批准）**：均置 **Envelope（不入 canonical payload、不入哈希域）**——状态 = **ORD-6（OWNER-DECISION-REQUIRED）**；**不得因"希望同输入产生相同哈希"即声称 envelope 排除已获 Owner 批准**；如 Owner 主张 `computed_at` 入 canonical payload，必须重评确定性要求（不得擅自改写冻结架构）。可空规则亦见 ORD-6。

#### §5.2.3 Envelope 字段（不入 canonical payload；【②】v1 冻结模式：`artifact_id/created_at` 不入哈希域）

| 字段 | 业务含义 | 必填性 | 说明 |
|---|---|---|---|
| `artifact_id` | 工件身份 UUID | 必填非空 | 每次构建可变（同输入不同 id 合法）【②】 |
| `created_at` | 工件文件创建时间 | 必填非空 | 与 `computed_at` 分离【②】 |
| `computed_at` | 预测计算时间 | 必填可空（NULL=未提供，不得伪造） | **放置待 ORD-6 确认（提案：envelope）** |
| `artifact_sha256` | canonical payload 哈希 | 必填非空 | = `sha256(canonical(payload))` |

#### §5.2.4 PredictionRecord v2 合法状态组合（规则来源逐条标注）

```text
prediction_type ∈ {predicted, no-candidate}                         【②】§25

no-candidate ⇒ （R5 冻结块，Owner R2 指令原文；其中 top2/rank/margin 项为该指令
                 向 v2 新字段的延伸，效力以 Owner 后续审查为准）        【①】R2 指令
    top1_person_id = NULL ∧ top1_score = NULL
    ∧ top2_person_id = NULL ∧ top2_score = NULL
    ∧ rank = NULL ∧ margin = NULL

predicted ⇒ top1_person_id ≠ NULL                                    【②】§25/K

分数契约（K=A+C，按 source 分列，不得混为一条新规则）：
    S-B: top1_person_id ≠ NULL ⇒ top1_score ≠ NULL                  【②】K
    S-C: top1_score 允许 NULL（不伪造 score）                        【②】K / D3=A
    S-A: 消费不在本阶段范围（§4.7 Source Authorization）              【①】阶段范围

top2 规则（B6 复核结论：无冻结原文——全部为本任务书新设计，ORD-8 待裁）  【③】ORD-8
    提议默认：
      top2_score ≠ NULL ⇒ top2_person_id ≠ NULL                    （两 source）
      top2_person_id = NULL ⇒ top2_score = NULL                    （两 source）
      S-B: top2_person_id ≠ NULL ⇒ top2_score ≠ NULL
      S-C: top2_person_id ≠ NULL 时 top2_score 可 NULL
      top2_person_id ≠ top1_person_id（候选唯一性）

rank 派生（提议，ORD-1）：predicted ∧ top1_score ≠ NULL ⇒ rank = 1；否则 NULL   【③】
margin 公式（【①】已批准）：top1_score ≠ NULL ∧ top2_score ≠ NULL
    ⇒ margin = top1_score − top2_score（canonical repr）；否则 NULL           【①】+【③】表达

非法组合（任一命中 → REJECT，禁止静默修正）：
    · no-candidate 携带任一非 NULL 字段（含 rank/margin）             【①】R2 指令
    · predicted 而 top1_person_id = NULL                             【②】§25
    · S-B predicted 而 top1_score = NULL                             【②】K
    · 孤儿 top2_score（无 top2_person_id）                            【③】ORD-8
    · S-B 有 top2_person_id 而 top2_score = NULL                     【③】ORD-8
    · top2_person_id = top1_person_id                                【③】ORD-8
    · rank / margin 与重算不一致（含应为 NULL 而给出值）               【③】派生规则
```

**冻结语义核对结论**：未发现冻结契约相互矛盾；两处显式细化均已闭合（K 细化 D5 NULL 许可；§25 原则的 v2 字段延伸已按 R2 指令执行）。**凡③项均不声称已冻结。**

#### §5.2.5 v1 派生字段逐项追溯（含编码）

| v1 字段 | v1 语义 | v2 判定（来源） | 编码 |
|---|---|---|---|
| `input_population_scope` | 输入人口政策逐字记录 | 保留（【①】§七）；= 参考侧冻结人口政策记录；**不构成 Evaluation/denominator/Scope 决策**（Scope 仍 DEFERRED） | 必填非空 |
| `entry_count` / `person_count` | 快照侧条目/人数 | `entry_count` 保留（对齐目标侧）；**`person_count` 排除**（目标侧无对应语义——显式排除并记录） | —— |
| `score_semantics` | 描述性元数据 | 定位待裁（ORD-7：建议保留、必填可空、非权威） | 待 ORD-7 |
| `git_commit` | 补充溯源 | 定位待裁（ORD-7：建议保留、必填可空、非权威链） | 待 ORD-7 |
| `prediction_id` / `rank` / `margin` | v1 逐项字段 | 见 §4.4 / §5.2.4（派生化） | 必填非空 / 必填可空 ×2 |

#### §5.2.6 canonical payload / 哈希域 / Envelope 分离与确定性口径

- **哈希输入** = canonical payload bytes：固定 key 顺序、条目序 `cluster_id → observation_id`（字符串序）、紧凑分隔符、LF 结尾、UTF-8；数字 CPython repr（IEEE754 最短往返）；
- **Envelope 排除**：`artifact_id / created_at`（【②】v1 冻结模式沿用）；`computed_at`（【③】提案，ORD-6）；
- **确定性验收 T-D1（比较对象三分）**：

```text
(a) canonical payload bytes : 跨进程两次构建必须逐字节相同
(b) content SHA-256         : 必须相同
(c) envelope metadata       : artifact_id 必须不同（可变）；
                              created_at / computed_at 允许不同；
    不得要求包含不同 envelope 值的整个文件逐字节相同；
    envelope 差异不得影响 (a)/(b)
（若 ORD-6 裁定 computed_at 入 payload，则须重评本节确定性要求——
  本任务书不得擅自改写冻结架构）
```

- **prediction_id 重派生**：见 §4.4。

#### §5.2.7 字段编码约定（B6/B7 统一，实现不得自由裁量）

- v2 canonical payload 与 envelope 中，**凡 schema 已定义的字段，其键必须出现**（键省略 = 非法 → 拒绝）；
- **缺失值一律以 `null` 表达**（不得以省略键、空字符串、0 或其它哨兵值代替）；
- 每个字段的必填性显式归类为：**必填非空 / 必填可空 / 必填（值恒 NULL）**（§5.2.1–§5.2.3 已逐字段标注）；**不存在"可省略"类**；
- 若 Owner 按 ORD-7 剔除某字段，则该字段从 schema 移除（版本内不得半保留）。

## §6 统一验收矩阵

> 每项测试必须断言**具体失败项**与**错误类别**；全部 fixture 驱动、生产零接触。

### §6.0 编号索引与映射（B7.1；每个验收标准 → 实际存在的唯一编号）

| 章节验收标准 | 测试编号 | 退役编号映射（R2 → R3） |
|---|---|---|
| §4.1 | T-A1..T-A16 | —— |
| §4.2 | T-R1 / T-M6 / T-A11 / T-A12 | **T-L1 → T-R1；T-L2 → T-M6/T-M7** |
| §4.3 | T-A8 / T-A9 / T-A10 / T-A13 | **T-P1 → T-A13；T-P2 → T-A9；T-P3 → T-A10** |
| §4.4 | T-D1..T-D4 | —— |
| §4.5 | T-B1..T-B8 / T-S1..T-S5 | —— |
| §4.6 | T-C1..T-C12 | —— |
| §4.7 | T-A11/T-A12/T-A16、T-S1..T-S5、T-G1..T-G6、T-R1..T-R3、T-C10/T-C12 | —— |
| §4.8 | T-N1..T-N3 | —— |
| §5.1 | T-M1..T-M7、T-M4a..e | —— |

### §6.1 错误类别图例

`ERR-HASH-MISMATCH` / `ERR-IDENTITY-MISMATCH` / `ERR-BINDING-MISSING` / `ERR-EVIDENCE-MISSING` / `ERR-RULESET-UNKNOWN` / `ERR-CONTRACT-FIELDS` / `ERR-DERIVATION-MISMATCH` / `ERR-SOURCE-OUT-OF-SCOPE` / `ERR-V1-INPUT` / `ERR-SET-EQUALITY` / `ERR-COUNT-MISMATCH` / `ERR-MEMBER-CLASS`（missing/extra/duplicate/cross-run/photo-mismatch）/ `ERR-GT-VALIDATION` / `ERR-UNPROVABLE` / `ERR-STATE-IMPERSONATION` / `ERR-FIXTURE-SCOPE`。

### §6.2 矩阵（8 属性：输入与破坏 / 需执行验证 / 预期层级状态 / 拒绝断言与错误类别 / 诊断记录 / 评分 / 依赖 / 权威依据）

**M — Target Manifest（含 B1）**

| ID | 输入与破坏 | 需执行验证 | 预期层级状态 | 拒绝断言（错误类别） | 诊断 | 评分 | 依赖 / 依据 |
|---|---|---|---|---|---|---|---|
| T-M1 | Manifest Cluster Set ≠ Dataset Set（双向任一） | 集合双向比对（对 `dataset_cluster_ids` 与 entries） | ManifestContract=fail | 严格相等断言（ERR-SET-EQUALITY） | 是 | 否 | 新增 / 【①】v2.2 |
| T-M2 | Run 含 Dataset 外 Cluster | 构建（含包含性校验） | ManifestContract=pass | **不失败**；额外 cluster 不在 manifest；诊断记录 | 是 | 依公式 | 新增 / 【①】 |
| T-M3 | Dataset Cluster 缺失于 Run | 单向包含校验 | NO MANIFEST | ERR-SET-EQUALITY | 是 | 否 | 新增 / 【①】 |
| T-M4a..e | 成员漏项 / 多项 / 重复 / 跨 Run / photo_id 错配（逐一注入） | Layer B 重读源五类比对 | LayerB=fail（构建时同类） | 对应 ERR-MEMBER-CLASS | 是 | 否 | 新增+已有（读源）/【①】 |
| T-M5 | `entry_count ≠ source_member_count` | Layer A 内部计数一致性 | LayerA=fail | ERR-COUNT-MISMATCH | 是 | 否 | 新增 / 【③】本任务书 |
| T-M6 | 两计数相等（记录自洽）但源端实际存在遗漏 | Layer A（通过）→ Layer B 检出 | LayerA=pass ∧ LayerB=fail | 断言 Layer A **不得**冒充完整性；ERR-MEMBER-CLASS | 是 | 否 | 新增 / 【①】B1 边界 |
| T-M7 | Layer A pass ∧ Layer B fail（显式区分形态） | 六维报告 | 如上 | 维度不得合并总判（ERR-STATE-IMPERSONATION 邻近） | 是 | 否 | 新增 / 【①】 |

**A — Isolation Attestation（含 B2/B4）**

| ID | 输入与破坏 | 需执行验证 | 预期层级状态 | 拒绝断言（错误类别） | 诊断 | 评分 | 依赖 / 依据 |
|---|---|---|---|---|---|---|---|
| T-A1 | 全检查通过 | 全部 I-1..I-7 + 支撑条件 | Integrity=pass; Revalidation=pass; Assurance=valid-and-verified | ——（准予，需其余准入全过） | 是 | 依公式 | 新增 / 【①】OG-1 |
| T-A2 | 篡改 canonical payload | 哈希重算 | Integrity=fail | ERR-HASH-MISMATCH | 是 | 否 | 新增 |
| T-A3 | **修改 checks[].result，不重算 Attestation 哈希**（B4-1） | 哈希重算 | Integrity=fail | ERR-HASH-MISMATCH（记录级） | 是 | 否 | 新增 |
| T-A4 | **修改 checks[].result 并重算匹配的 payload SHA，但不改真实源证据**（B4-2） | Integrity=pass → **Revalidation 独立复核真实源证据** | Integrity=pass ∧ Revalidation=fail → Assurance=invalid | 伪造 pass 检出（ERR-EVIDENCE-MISSING / ERR-HASH-MISMATCH 按承载） | 是 | 否 | 新增（语义伪造闭环）/【①】B4 |
| T-A5 | RULESET 缺失 / 未知 | RULESET 识别 | Integrity=fail（Support=fail） | ERR-RULESET-UNKNOWN | 是 | 否 | 新增 / 【①】R2 |
| T-A6 | 必要证据缺失（evidence_refs 空） | 证据完整性 | Revalidation=unprovable | ERR-EVIDENCE-MISSING | 是 | 否 | 新增 |
| T-A7 | 参考照片当前字节不可读 | 实算尝试 | Revalidation=unprovable | ERR-UNPROVABLE（无替代证据） | 是 | 否 | 已有 hasher /【①】B2 |
| T-A8 | photo_id 集合交集非空 | I-1 | Revalidation=fail | ERR-SET-EQUALITY | 是 | 否 | 已有（守卫 API）/【②】 |
| T-A9 | 同字节异 photo_id | I-5（当前字节实算） | Revalidation=fail | ERR-HASH-MISMATCH | 是 | 否 | 已有 hasher /【②】D-SB-8 |
| T-A10 | Run 归属不匹配（含调用方集合 ≠ 派生集） | I-4 | Revalidation=fail | ERR-IDENTITY-MISMATCH | 是 | 否 | 新增（派生）+读源 /【①】R8 |
| T-A11 | Layer A pass 冒充 Assurance | 状态机枚举断言 | 断言失败 | ERR-STATE-IMPERSONATION | 是 | 否 | 新增 /【①】B3 |
| T-A12 | 任一必需层 not-run | 准入公式 | Admission=false | 六维明细列出缺失层（ERR-UNPROVABLE 邻近） | 是 | 否 | 新增 |
| T-A13 | 两侧集合摘要离线复算（退役编号 T-P1 承接） | 离线重算 digest | —— | digest 重算相等断言 | 是 | 依公式 | 新增 |
| T-A14 | **评估照片回填哈希 H1；回填后字节变化为 H2（B2 负向）** | 当前字节实算 + 与 H1 对照 | 断言**不得**把合法格式 H1 自动视为当前哈希；实算得 H2；若字节不可得 → unprovable | ERR-UNPROVABLE /（H2 命中时）ERR-HASH-MISMATCH | 是 | 否 | 新增 /【①】B2 |
| T-A15 | 评估照片当前字节不可得（无合法 stored 亦无法实算） | 实算尝试 | Revalidation=unprovable | ERR-UNPROVABLE | 是 | 否 | 新增 /【①】B2 |
| T-A16 | 四场景断言（B3）：hash-only→internal-only；源检查隔离失败→invalid；无法执行→unprovable；全通过→valid-and-verified | Assurance 映射 | 各场景对应枚举 | 映射确定性断言（错误类别按场景） | 是 | 否 | 新增 /【①】B3 |

**B / S — 双绑定与 Snapshot**

| ID | 输入与破坏 | 需执行验证 | 预期层级状态 | 拒绝断言 | 诊断 | 评分 | 依赖 / 依据 |
|---|---|---|---|---|---|---|---|
| T-B1..T-B4 | ID 或 SHA 各错误（Manifest / Snapshot） | 身份一致 + 重算哈希 | Binding=fail | ERR-IDENTITY-MISMATCH / ERR-HASH-MISMATCH | 是 | 否 | 新增 /【①】OG-2 |
| T-B5 | 工件内容篡改 | 重算哈希 | Binding=fail | ERR-HASH-MISMATCH | 是 | 否 | 新增 |
| T-B6 | 同内容不同 ID 替换 | 身份比对 | Binding=fail | ERR-IDENTITY-MISMATCH | 是 | 否 | 新增 /【①】OG-2 |
| T-B7 | 等价位移（relocation） | 内容哈希 | Binding=pass | 不读 path（断言） | 是 | 依公式 | 新增 |
| T-B8 | 绑定字段缺失 | 字段完整性 | Binding=fail | ERR-BINDING-MISSING | 是 | 否 | 新增 |
| T-S1..T-S3 | Snapshot schema 非法 / 内部哈希失配 / provenance 不完整 | verifier 各项 | SnapshotValidation=fail | 各自断言（ERR-HASH-MISMATCH 等） | 是 | 否 | 已有（verifier） |
| T-S4 | 源端核验未执行/不可用 | cross_check | SnapshotValidation=not-run/unprovable | ERR-UNPROVABLE | 是 | 否 | 已有 + 新增 |
| T-S5 | embedding 漂移 | cross_check | SnapshotValidation=fail | drift_free=False 断言 | 是 | 否 | 已有（cross_check） |

**C — 预测契约（含 B7.2 / §五.2）**

| ID | 输入与破坏 | 需执行验证 | 预期层级状态 | 拒绝断言（错误类别） | 诊断 | 评分 | 依赖 / 依据 |
|---|---|---|---|---|---|---|---|
| T-C1 | no-candidate + 任一非 NULL 字段（逐一） | 冻结块校验 | Contract=fail | ERR-CONTRACT-FIELDS | 是 | 否 | 新增 /【①】R2 指令 |
| T-C2 | predicted 无 top1_person_id | 状态组合 | Contract=fail | ERR-CONTRACT-FIELDS | 是 | 否 | 新增 /【②】§25 |
| T-C3 | S-B predicted 且 top1_score=NULL | K 契约 | Contract=fail | ERR-CONTRACT-FIELDS | 是 | 否 | 新增 /【②】K |
| T-C4 | S-C predicted 且 top1_score=NULL | K 契约（合法） | Contract=pass | 不修正、不补分（断言） | —— | 依公式（再经 Source Auth=拒绝） | 新增 /【②】K、D3=A |
| T-C5 | 孤儿 top2_score | 成对约束 | Contract=fail | ERR-CONTRACT-FIELDS | 是 | 否 | 新增 /【③】ORD-8 |
| T-C6 | S-B top2_person + top2_score=NULL | 成对约束 | Contract=fail | ERR-CONTRACT-FIELDS | 是 | 否 | 新增 /【③】ORD-8 |
| T-C7 | top2 == top1 person | 候选唯一性 | Contract=fail | ERR-CONTRACT-FIELDS | 是 | 否 | 新增 /【③】ORD-8 |
| T-C8 | rank / margin 被篡改 | 重算比对 | Contract=fail | ERR-DERIVATION-MISMATCH | 是 | 否 | 新增 /【③】 |
| T-C9 | margin 在 top2=NULL 时给出值 | 派生规则 | Contract=fail | ERR-DERIVATION-MISMATCH | 是 | 否 | 新增 /【①】公式 |
| T-C10 | **v1 工件喂入（B7.2）** | Gate 0：分类 + 拒绝处置 | input_class=v1；rejection_outcome=rejected-as-required；admission=false | **测试断言成功**（正确拒绝）；报告不得记为失败；不得放行 | 是 | 否 | 已有 v1 verifier + 新增 /【①】 |
| T-C11 | 非法输入静默修正探针 | 拒绝 ≠ 改写 | Contract=fail | 断言无变更发生 | 是 | 否 | 新增 |
| T-C12 | S-C 工件（schema 合法）喂入 | Source Authorization | SourceAuth=fail | ERR-SOURCE-OUT-OF-SCOPE（≠ schema 非法） | 是 | 否 | 新增 /【①】阶段范围 |

**D — 确定性（含 B5）**

| ID | 输入与破坏 | 需执行验证 | 预期 | 断言 | 诊断 | 评分 | 依赖 / 依据 |
|---|---|---|---|---|---|---|---|
| T-D1 | 跨进程两次构建 | 三分比较 | (a)/(b) 相同；(c) 允许不同 | payload bytes 相同 ∧ content SHA 相同 ∧ envelope 差异不影响力(a)(b) | —— | 依公式 | 新增 /【②】+【③】ORD-6 |
| T-D2 | prediction_id 缺失 | 字段完整性 | Contract=fail | ERR-CONTRACT-FIELDS | 是 | 否 | 新增 /【③】§4.4 |
| T-D3 | prediction_id 篡改 | 重派生 | Contract=fail | ERR-DERIVATION-MISMATCH | 是 | 否 | 新增 |
| T-D4 | 跨进程独立重派生 | uuid5 复算 | 重派生 == 记录值 | 相等断言 | —— | —— | 新增 |

**G / N / R — GT、Fixture、报告与准入**

| ID | 输入与破坏 | 需执行验证 | 预期 | 断言（错误类别） | 诊断 | 评分 | 依赖 / 依据 |
|---|---|---|---|---|---|---|---|
| T-G1 | GT cluster set ≠ dataset set | 集合严格比对 | GTValidation=fail | ERR-GT-VALIDATION | 是 | 否 | 读 GT + 新增 |
| T-G2 | GT 缺失 / 重复行 | 恰一 verdict | GTValidation=fail | ERR-GT-VALIDATION | 是 | 否 | 同上 |
| T-G3 | PERSON 身份不可解析 | person 解析 | GTValidation=fail | ERR-GT-VALIDATION | 是 | 否 | 同上 |
| T-G4 | 三态互不混淆（负向：不得 NULL 塌缩） | 状态枚举断言 | GTValidation 断言 | ERR-GT-VALIDATION | 是 | 否 | 新增 /【①】 |
| T-G5 | GT 只读闭包 | 前后计数/哈希 | 不变 | 零写入断言 | —— | —— | 已有（审计模式） |
| T-G6 | 任一 GT 条件单点失败 | 六查逐点 | GTValidation=fail | 逐点断言 | 是 | 否 | 新增 |
| T-N1 | 文本声明存在性 | 静态断言 | —— | 四声明 + 七条边界在位（ERR-FIXTURE-SCOPE 邻近） | —— | —— | 新增 /【①】R9 |
| T-N2 | fixture 标注 | 测试/来源/报告三处 | —— | 标注在位断言 | —— | —— | 新增 |
| T-N3 | fixture 输入走完整公式 | 准入全条件 | 不减免任何条件 | 断言无 fixture 快捷路径（ERR-FIXTURE-SCOPE） | 是 | 依公式 | 新增 /【①】R9 |
| T-R1 | 离线环境（无 DB、照片不在） | 六维报告 | A=pass; B=not-run; Integrity=pass; Revalidation=not-run; Assurance=internal-only; Admission=false | 六维逐维断言；不得出现总判 PASS（ERR-STATE-IMPERSONATION 邻近） | 是 | 否 | 新增 /【①】R3 |
| T-R2 | 全条件单点否决（13+ 项逐点） | 准入公式逐项 | 各点 Admission=false | 每项独立可测（ERR-* 按项） | 是 | 否 | 新增 /【①】R4 |
| T-R3 | 判定顺序一致性 | 报告字段组合 | —— | 同输入不产生跨维度矛盾结论 | 是 | —— | 新增 /【①】B3 |

## §7 实现边界、未决事项与审查门禁

### §7.1 实现边界与顺序

```text
本任务书（READY-FOR-OWNER-REVIEW）
   ↓ Owner 审查（含 §7.2 决项）
明确批准开发
   ↓ dev-AI 实施（仅新增文件；零 Migration；不改 S-B-1..5 冻结行为）
独立 review-AI 审计
```

交付形态预期：新增服务（manifest / artifact-v2 / attestation / mechanical scoring consumer）+ fixture 验收测试；质量门 ≥ §1.3 基线。不授权：生产工件发布、Actual Evaluation、指标计算、commit/push。

### §7.2 Owner Review Decisions（审查提案——**未生效，不得表述为已批准**；R3 起保留 ORD-1..ORD-8）

| ORD | 项目 | 建议默认方案（附依据） | R3 状态 |
|---|---|---|---|
| ORD-1 | `rank` / `margin` | **保留**为派生字段（margin 公式【①】已批准；rank=1/NULL 规则为【③】提议）；保留与否本身待确认 | `OWNER-DECISION-REQUIRED` |
| ORD-2 | evidence tie-break | canonical `observation_id` 字符串序最小（规范化：RFC 4122 小写文本、Unicode 码点序） | `OWNER-DECISION-REQUIRED` |
| ORD-3 | `run_cluster_count` | 诊断语义保留；**建议排除**出 payload 与哈希域（仅构建报告）；字段位置与哈希地位待裁 | `OWNER-DECISION-REQUIRED` |
| ORD-4 | UUIDv5 namespace | 候选 `4b60862f-952f-5094-98d2-09df3f32d886`（配方可复现） | `OWNER-DECISION-REQUIRED` |
| ORD-5 | `scorer_version` 命名 | 基于 D5（正式名）、v1（`prediction_method_version`）与最终架构裁决 §七（`prediction_source_version`）原文证据：三者同概念；**建议 canonical=`scorer_version`**；不得仅凭名称相似强制合并语义 | `OWNER-DECISION-REQUIRED` |
| ORD-6 | `computed_at` | 语义分离已定义；**放置（提案 envelope）与可空规则均未获批准**；若入 payload 须重评确定性 | `OWNER-DECISION-REQUIRED` |
| ORD-7 | `score_semantics` / `git_commit` | 建议保留为必填可空、非权威；字段定位与哈希域待裁 | `OWNER-DECISION-REQUIRED` |
| **ORD-8（新）** | **top2 成对/唯一性规则** | B6 复核确认**无冻结原文**（D5 仅给字段；K/§25 只管 predicted/top1）→ 全部为【③】新设计：S-B top2 person⇒score、S-C top2 score 可空、top2≠top1；影响 T-C5..T-C7 断言集 | `OWNER-DECISION-REQUIRED` |

**关闭条件**：仅当任务书给出准确权威引用且该问题可由冻结契约唯一确定时，方可关闭；否则一律开放。

### §7.3 证据缺口与权威来源冲突

| # | 事项 | 性质 | 处置 |
|---|---|---|---|
| EG-1 | v2.2 Architecture Specification 无仓库文件（会话交付） | 载体缺口 | 引用其冻结内容并注明来源；落盘另行指示 |
| EG-2 | 守卫侧无规则版本常量（实证） | 既有能力事实 | 新契约标识（不追述）；改守卫须新 Gate |
| EG-3 | 命名冲突 D5 `scorer_version` vs §七 `prediction_source_version` | 权威来源冲突（命名层） | ORD-5，禁止静默取舍 |
| EG-4 | 无已批准 UUIDv5 namespace | 缺口 | ORD-4 候选 |
| EG-5 | 无字节哈希"缓存新鲜度"证明机制 | 缺口 | §4.1 I-5：该路径不可用；当前字节不可得 → unprovable（不得虚构） |
| EG-6 | top2 规则无冻结原文（B6 复核） | 缺口 | ORD-8 |
| EG-7 | `computed_at` 放置未获批准（B5） | 设计选择 | ORD-6（不得声称已批准） |
| EG-8 | R5 冻结语义核对 | 无冲突 | 两处显式细化已闭合（§5.2.4 结论） |

### §7.4 审查门禁与终态

```text
V2-ARCH-FINAL  = APPROVED WITH CONDITIONS
S-B-6 SPEC     = READY-FOR-OWNER-REVIEW   （R3 修订完成；待 Owner 审查与 §7.2 决项）
IMPLEMENTATION = NOT AUTHORIZED
```

**下一道门 = Owner 对 R3 任务书的审查与明确开发批准。** 在此之前：不得实现、不得改代码/测试、不得生成生产工件、不得评分、不得计算指标、不得 commit/push。

---

*本文件为任务书（untracked，未提交；提交与推送均属 Owner 操作）。*
