# S4-B-2 — Owner Decisions（正式裁决记录）

- **Decision ID**: `S4B2-OWNER-DECISIONS-2026-10-04`
- **日期**: 2026-10-04
- **裁决人**: Owner
- **送达渠道**: Owner 裁决会话（2026-10-04，本文 §1 为原文逐字记录）
- **登记性质**: 登记性回填 —— 依据《S4_B2_Owner_Decision_Recording.md》§5 既定登记计划与
  《S4_B2_Production_Preparation_Blocked.md》§11 解除条件；AI 未代决任何值，未增删语义
- **登记时基线**: HEAD `27bdc64`；生产库（`%LOCALAPPDATA%\PhotoArchiver\photo_archiver.db`，
  mode=ro 只读复核）head=`008_archive_identity_and_confidence`、photos=473、
  face_observations=1441、face_clusters=36、face_cluster_members=399、recognition_results=472、
  cluster_person_assignments=0、person_face_embeddings=0、archive_records=0、无 calibration 表
- **验证分类**: **OWNER-DECISION-COMPLETE**（8/8 项明确裁决，D-3 参数完整）

---

## 1. 裁决原文（逐字）

```text
OWNER裁决项决策：
D-7 = APPROVE
批准 scope = 全部现有 face-count ranges

C-1 = APPROVE

D-1 = APPROVE

D-2 = APPROVE
独立标注员 = 2
100% Cluster 双人独立标注 = YES
抽样复核 = NO（首轮全量双标）
冲突 = 100% adjudication
adjudicator = 第三位独立人员
re-annotation = append-only

D-3:
p = 0.50
z = 1.96
confidence = 95%
e = 5%
u = 10%
acceptable false-auto-confirm rate = ≤1%

C-4 = DEFER

D-4 = DEFER

D-5 = DEFER
```

## 2. 裁决矩阵（登记后）

| 决策 | 裁决 | 值 / 细则 |
|---|---|---|
| D-7 face scope | **APPROVE** | scope = 全部现有 face-count ranges：`["1"]`、`["2-3"]`、`["4-5"]`、`["6-10"]`、`["11+"]`（= Dry-Run Run B 已验证配置，预期 44 簇 / 1441 members）；「现有」之外的新档位不在本裁决内 |
| C-1 migration 011 | **APPROVE** | 允许生产 008 → 011（含 009/010 顺次执行）；执行前置 backup / schema verification / rollback 清单保持为硬前置 |
| D-1 human annotation | **APPROVE** | 允许进入真实人工标注（按 D-2 规程） |
| D-2 annotation protocol | **APPROVE** | 独立标注员 = 2；100% Cluster 双人独立标注 = YES；抽样复核 = NO（首轮全量双标）；冲突 = 100% adjudication；adjudicator = 第三位独立人员；re-annotation = append-only |
| D-3 statistical parameters | **values（已给定）** | p = 0.50（expected precision，比例）；z = 1.96；confidence = 95%；e = 5%（±5 个百分点，比例语义）；u = 10%（预期 undecidable 率）；acceptable false-auto-confirm rate = ≤1% |
| C-4 margin | **DEFER** | 首轮不做 margin 分层（显式协议降级项；不得声称系统具备 margin 能力） |
| D-4 auto-confirm scope | **DEFER** | 首轮零自动确认；≤1% 为未来自动确认设计的边界值 |
| D-5 post-confirm archive | **DEFER** | 首轮零自动归档；归档仍为手动任务 |

## 3. 派生计算（非裁决 —— D-3 参数代入既定公式的输出）

D-7 = APPROVE ⇒ 抽样框架为放宽重跑后的新代次，N = 44 clusters。

```text
unique calibration units   = Cluster（N = 44）
n0                  = z²·p(1−p)/e² = 1.96²×0.50×0.50/0.05² = 384.16
n (FPC)             = N·n0/(N+n0−1) = 44×384.16/427.16 ≈ 39.57 → 整数目标 40
gross               = min(ceil(n/(1−u)), N) = min(ceil(40/0.90), 44) = min(45, 44) = 44
                      —— 普查封顶：放大后 45 > N，gross = N（普查）
expected_effective  = gross×(1−u) = 44×0.90 = 39.6
                      —— 低于整数目标 40（差 0.4）；普查上限损失不可经扩样消除，如实报告
annotation_events   = gross×annotators = 44×2 = 88（双人全量双标）
adjudication（预期）= gross×u ≈ 4.4 起冲突（100% 覆盖，第三位独立人员仲裁，append-only）
```

**单位分离**：units（44）≠ events（88）≠ annotators（2 + 仲裁 1）。precision 分母为有效
units（期望 39.6），不是 88。

**与 D-2 交叉印证**：D-3 计算结果（普查 44、全量双标）与 D-2「100% Cluster 双人独立标注
= YES」完全一致 —— 首轮即全量 44 簇 × 2 人 = 88 events，无需抽样执行器削减标注量
（抽样协议 s4b1/s4b2-sampling-v1 的价值在可复现与可审计，非省量）。

## 4. 一致性核验

| 检查 | 结果 |
|---|---|
| z = 1.96 ↔ confidence = 95% | 一致（均为 Owner 显式给定，无推导回填） |
| C-4 = DEFER ⇒ 无 margin 分层 | 成立（协议降级项，非遗漏、非缺省） |
| D-4 = DEFER ⇒ 零自动确认 ⇒ ≤1% 边界当前不可违反 | 成立（边界值为未来自动确认设计输入） |
| D-5 = DEFER 与 D-4 = DEFER 耦合 | 一致 |
| D-2 全量双标 + 100% 仲裁 vs S4-B-1 已实现机制（2 标注员 + 仲裁 + append-only） | 一致 |
| D-7 scope（现有五档）= Run B 已验证配置 | 一致（44 簇 / 1441 / 0 空簇 / 0 孤儿） |
| C-1 APPROVE + 执行前置（backup / schema verify / rollback） | 前置保持（Gate §8/§9） |

## 5. Scope & Consequences

- **授权完备 ≠ 执行开始**：生产执行（backup → verify backup → migration → verify schema →
  recognition rerun（五档全开）→ cluster → verify generation → verify business isolation →
  verify calibration → sampling snapshot → STOP，任一步失败即停）等待 Production
  Preparation 任务书重新下发后启动。
- 本记录登记时点**未执行任何生产动作**（零备份、零迁移、零重跑、零标注、零抽样、
  零 margin、零自动确认/归档）。
- 旧代次（36 簇 / 399 members）在新代次生成前保持生产唯一状态；新代次按 Gate §8 生成，
  新旧三代并存、旧行零突变（Dry-Run 已证）。
- D-7 批准范围限于「现有」五档；如未来提出新档位，需另行裁决。

## 6. Reversibility

- 本记录为授权与参数裁决；Owner 可随时以新裁决修订或撤销（修订须更新本记录并注明
  日期与来源）。
- 已执行的生产步骤各自受《S4_B2_Owner_Decision_Gate.md》§9 回滚边界约束：
  migration 失败 → backup 文件整体还原（主）/ alembic downgrade（次）；
  识别/聚类失败 → 保留旧代次，新 run 记 failed/partial；calibration 故障不外溢业务链。
