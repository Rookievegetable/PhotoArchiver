# S4-B-2 — Production Preparation（执行报告 · COMPLETE）

- **日期**: 2026-10-04
- **任务**: S4-B-2 Production Preparation（任务书 2026-10-04 重新下发后执行）
- **授权来源**: `docs/decisions/S4B2-owner-decisions.md`（2026-10-04 Owner 八项裁决，已核验
  OWNER-DECISION-COMPLETE）+ Gate §10 回填矩阵
- **代码基线**: HEAD `27bdc64`，工作树零改动（执行全程零源码修改，全部经公共服务构造器）
- **结果**: **PRODUCTION-PREP COMPLETE**
- **执行时间线**: 09:45 CP0 基线 → 09:52 CP1 冷备 → 09:53 CP2/CP3 迁移 → 10:00–10:01 CP4/CP5
  识别重跑（75.57s） → 10:07 CP6 聚类（1.63s） → 10:07–10:17 CP7–CP10 核验 → 10:17 CP11 快照
  → 10:18–10:25 CP12–CP16 只读收尾

---

## 1. Owner Authorization（逐项原样）

来源：Owner 裁决会话 2026-10-04，正式记录 `docs/decisions/S4B2-owner-decisions.md` §1：

```text
D-7 = APPROVE，scope = 全部现有 face-count ranges（["1"] ["2-3"] ["4-5"] ["6-10"] ["11+"]）
C-1 = APPROVE
D-1 = APPROVE
D-2 = APPROVE（2 独立标注员；100% 双标；无抽样复核；100% 仲裁；第三人仲裁；append-only）
D-3 = p 0.50 / z 1.96 / confidence 95% / e 5% / u 10% / acceptable false-auto-confirm ≤1%
C-4 = DEFER
D-4 = DEFER
D-5 = DEFER
```

本任务消费项：D-7（CP4 scope）、C-1（CP1/CP2）。D-1/D-2/D-3/C-4/D-4/D-5 属后续标注阶段，
本轮**未**触发（无标注、无抽样执行、无 GT、无 margin、无自动确认、无自动归档）。
授权完备性核验：八项全部显式、无冲突、D-3 五值齐备——通过 Hard Stop 检查（§1）。

## 2. Production Baseline（CP0，只读，2026-10-04 09:45）

| 项 | 实测 | 预期 | 漂移 |
|---|---:|---:|---|
| HEAD | `27bdc64` | `27bdc64` | 无 |
| 工作树 | 31 M + 29 ??（登记态，无本轮新增） | 同 | 无 |
| production DB | `%LOCALAPPDATA%\PhotoArchiver\photo_archiver.db` | — | — |
| migration head | `008_archive_identity_and_confidence` | 008 | 无 |
| photos / observations | 473 / 1441 | 473 / 1441 | 无 |
| clusters / members | 36 / 399 | 36 / 399 | 无 |
| cpa / pfe / archive | 0 / 0 / 0 | 0 / 0 / 0 | 无 |
| recognition_results | 472（全 pending、person_id 全 NULL legacy） | 472 | 无 |
| journal 模式 / WAL | wal / 0 字节（已 checkpoint） | — | — |
| PhotoArchiver 进程 | 未运行（停机窗口成立） | 未运行 | — |

## 3. Backup（CP1）

```text
方式        = 项目自带 backup_database()（VACUUM INTO 一致性快照，WAL 安全）
路径        = %LOCALAPPDATA%\PhotoArchiver\backups\photo_archiver_20261004_095201.db
大小        = 19,226,624 bytes
integrity   = PRAGMA integrity_check = ok
sha256      = a5d788125c398b9412690120cdc7815b2f6fef2e0451e2af750902c9d2cfc869
md5         = f0019f8ec6bfcaaae175cf8dc42fd4f0
备份时 head = 008_archive_identity_and_confidence
备份内计数  = photos 473 / obs 1441 / clusters 36 / members 399 / rr 472 / cpa 0 / pfe 0 / archive 0
既有 3 份备份（20261001_151502 / 172553 / 175427）全部保留（keep=4）
```

## 4. Migration（CP2 + CP3）

- **入口**: `run_alembic_migrations()`（应用启动同款公共路径，无任何迁移文件修改）。
- **执行链**: `008 → 009_projection_ownership → 010_assignment_source_review → 011_calibration_annotations`，三步全部成功，耗时 <1s。
- **head = `011_calibration_annotations`** ✓
- **CP2 校验**: `calibration_annotations` 存在（含 role/verdict CHECK、difficulty_reason 耦合 CHECK）；`calibration_ground_truth` 含 **difficulty_reason** 列；`calibration_datasets` **PRIMARY KEY (id, version)** 复合主键 + **`CHECK (status IN ('frozen'))`**（frozen-only）✓
- **CP3 安全**: 迁移后业务数据零变化——photos 473 / obs 1441 / clusters 36 / members 399 / cpa 0 / pfe 0 / archive 0；`recognition_results` 新增 `assignment_id` 列 + 3 索引（009）；`cluster_person_assignments.source` CHECK 扩 `review`（010）；**legacy 472 pending 逐条原样**（472 行、person_id 全 NULL、状态全 pending）✓

## 5. Recognition（CP4 + CP5）

- **执行**: 公共构造器布线（同 Dry-Run/`tools/validate_stage_f.py` 模式，零源码修改）：
  `InsightFaceLoader(resources/models)+InsightFaceDetector+CosinePersonMatcher(0.40)+RunRecognitionService(max_workers=4)`，
  473 张全量照片，**严格使用批准的五个现有档位**（`FaceCountRange(1,1)/(2,3)/(4,5)/(6,10)/(11,None)`）。
- **新 run**: `fe983920-eefb-4078-801d-0ce8a5bc9d0d`，status=completed
- **实测**: face_count **1441** / unreadable 0 / no_face 1 / error 0 / **in_scope 472 / out_of_scope 0**，wall **75.57s**（6.26 photos/s）
- **批准范围落库**: `recognition_run_scopes` 五行 = (1,1),(2,3),(4,5),(6,10),(11,∞) ——批准档位被持久化记录；run `parameters` JSON 为 `{}`（驱动直接调用命令构造器，与 Dry-Run 同；范围以 scopes 表为准）
- **scope 分布**: 1441/1441 observations = `in_selected_scope`（vs 旧 run 399 in / 73 out）
- **脸数分布**: 1×399 照片、3×2、7×43、8×4、11×5、13×1、23×1、36×17 ——有脸照片共 472
- **旧数据未破坏**: 旧 run `dafcf284` 1441 observations 原样（det_score 总和 1255.973523 指纹不变）
- **业务面**: rr/cpa/pfe/archive 全零变化（compat writer 未触发——唯一无 rr 照片即无脸照片，不产生观测）

## 6. Clustering（CP6 + CP7）

- **执行**: `ClusterFacesService`（算法零修改），仅针对新 recognition run。
- **新代次**: cluster_run_id `a66943e7-1407-4b1c-836e-27c307a649a7`，status=completed，wall 1.63s
- **实测 vs Dry-Run 预期**（生产实测为准，逐项吻合）:

| 指标 | 生产实测 | Dry-Run 预期 | 一致 |
|---|---:|---:|---|
| clusters | **44** | 44 | ✓ |
| members | **1441** | 1441 | ✓ |
| excluded | 0 | — | — |
| multi-face obs clustered | **1042** | 1042 | ✓ |
| 多脸照片→多簇 | **73/73（100%）** | 73/73 | ✓ |
| max clusters/photo | **36** | 36 | ✓ |
| empty clusters | **0** | 0 | ✓ |
| orphan members | **0** | 0 | ✓ |
| members==distinct photos | **44/44 簇成立** | 44/44 | ✓ |

- **规模分布**: 1×4（单例，均源自 7 人合影）、2–5×1、6–10×3、21–50×36（p50 规模 39，max 41，均值 32.75）

## 7. Generation Isolation（CP8）

- 旧识别代次 `dafcf284`（completed，1441/399/73，created 2026-09-30T20:27:19）**逐字段原样**；
- 旧聚类代次 `1192d499`（completed，36 簇/399 成员/排除 1042，created 2026-10-01T12:26:52）**原样**；
- 新旧并存：recognition_runs = 2、face_cluster_runs = 2；无删除、无覆盖、无改派。

## 8. Business Isolation（CP9）

| 表 | 变更前 | 变更后 | delta | 定性 |
|---|---:|---:|---:|---|
| cluster_person_assignments | 0 | 0 | 0 | FORBIDDEN 业务写入 = 无 ✓ |
| person_face_embeddings | 0 | 0 | 0 | FORBIDDEN 业务写入 = 无 ✓ |
| archive_records | 0 | 0 | 0 | FORBIDDEN 业务写入 = 无 ✓ |
| recognition_results | 472（全 pending） | 472（全 pending） | 0 | EXPECTED RECOGNITION CHANGE = **无变化**（compat 未触发）✓ |

## 9. Calibration Schema（CP10，未开始人工标注）

- `calibration_annotations`：9 列（含 role/verdict/difficulty_reason/protocol_version），索引 idx_calib_ann_annotator / idx_calib_ann_cluster + PK，FK→people、face_clusters
- `calibration_ground_truth`：12 列（含 **difficulty_reason**、resolution、source_annotation_ids、adjudicated_by），索引 idx_calib_gt_dataset / idx_calib_gt_cluster，FK→people、face_clusters
- `calibration_datasets`：**复合 PK (id, version)** + `CHECK (status IN ('frozen'))`，cluster/usable/excluded 计数列
- 三表均 **0 行**（本任务零写入）——标注未开始 ✓

## 10. Production Snapshot（CP11）

```text
checkpoint   = wal_checkpoint(TRUNCATE) → (0,0,0)，计数与 head 跨 checkpoint 稳定
database     = %LOCALAPPDATA%\PhotoArchiver\photo_archiver.db（38,154,240 bytes）
database hash (sha256) = ee9a71274028293f757c3e996529906d047ed9960b934a5e4f8818ea3e23f780
alembic_version        = 011_calibration_annotations
recognition_run_id     = fe983920-eefb-4078-801d-0ce8a5bc9d0d
cluster_run_id         = a66943e7-1407-4b1c-836e-27c307a649a7
sampling protocol      = s4b2-sampling-v1（seed 20260101 为 proposed 参数，未入库固化）
snapshot_id            = cdc17bfdf824fa8ffa97dee84a519f66200576354eab6493887669df7d8e379e
编码规范（固定）       = SHA-256(db_file_bytes || 0x1F || utf8(alembic_version) || 0x1F
                          || utf8(recognition_run_id) || 0x1F || utf8(cluster_run_id))
时间戳                  = 2026-10-04T10:17:04
```

## 11. Candidate Pool（CP12，只读，无 calibration 写入）

```text
candidate cluster count        = 44（新代次全量候选池）
singleton clusters             = 4（均源自 7 人合影）
含合影观测的簇                 = 44/44（无"纯单人照片簇"）
one-photo-multi-cluster 涉及簇 = 44/44（任一簇都存在与他簇共享的照片）
簇规模分布                     = 1×4 | 2–5×1 | 6–10×3 | 21–50×36（min 1 / p50 39 / max 41 / mean 32.75）
成员检测分分布                 = p10 .8365 / p25 .8537 / p50 .8724 / p75 .8944 / p90 .9077，<0.50 计数 0
folder 分布                    = 473 张全部同一 folder（测试Photo；folders 表另一行 2026-09-20 历史扫描根，无照片）
content hash duplicates        = 0（473/473 已填充 metadata_content_hash）
```

## 12. Sample Size（CP13 + CP14；D-3 = COMPLETE）

抽样框架 = 新代次 N = **44**（生产实测候选池）：

```text
n0                 = z²·p(1−p)/e² = 1.96²×0.50×0.50/0.05² = 384.16
n (FPC)            = 44×384.16/427.16 ≈ 39.57 → 整数目标 40
gross              = min(ceil(40/0.90), 44) = 44 —— 普查封顶（放大 45 > N）
expected_effective  = 44×0.90 = 39.6 ≠ 40（如实报告：已到普查上限，undecidable 损失
                     不可通过增加样本消除；39.6 比整数目标低 0.4）
annotation_events  = 44×2 = 88（= D-2 全量双标裁决，与 D-3 计算交叉印证）
预期仲裁           ≈ 44×10% = 4.4 起（100% 覆盖、第三人、append-only）
单位分离           = units 44 ≠ events 88 ≠ annotators 2+1
```

**协议参数验证（s4b2-sampling-v1，仅合成串，未执行抽样）**：轮内确定性 ✓、随 round 变化 ✓、
随 seed 变化 ✓、键唯一 ✓、`cluster_id ASC` 单独使用非随机（协议以 SHA-256 置换实现确定性
伪随机）✓。**未执行任何真实抽样、未写 calibration 三表。**

## 13. Remaining Limitations（继续报告）

```text
multi-face             = 合影语义（7×43 / 36×17 刚性脸数；44/44 簇 members==distinct photos；一照多簇 73/73 为自然结构）
one-photo-multi-cluster = 73/73、max 36——审核/归档语义按代次隔离，历史 pending 队列不受影响
margin                 = C-4 = DEFER：首轮无 margin 分层（显式协议降级项）；matcher 单 best，top1/top2 不存在；簇心 margin 待第二轮
folder                 = folder-level split UNAVAILABLE（473 张单一 folder）
near-duplicate        = 无感知哈希能力，UNAVAILABLE（记录限制）
annotator identity     = D-2 裁决 2 独立标注员 + 第三人仲裁；自然人数身份登记待标注阶段执行（人员未指定姓名/账号）
adjudication UI        = 仲裁无专用 UI（服务 API 可用，L2 维持）
legacy 472 pending     = 原样保留（CP16 复核：472/472 pending）；处置属业务链 Owner 决策
B-plan 自动归属        = 未实施（PROJECT_STATUS §6 #6 立项暂搁置）
```

## 14. Final Gate

```text
PRODUCTION-PREP COMPLETE
```

验收 23 项全部满足（Owner 决策完整 ①、基线无漂移 ②、备份可验证 ③、迁移成功 ④、calibration
schema 正确 ⑤、472 pending 保留 ⑥、批准 scope 严格使用 ⑦、新识别代次成功 ⑧、旧代次保留 ⑨、
新聚类代次成功 ⑩、旧聚类代次保留 ⑪、多脸/多簇实测 ⑫、Assignment/pfe/Archive 零变化 ⑬⑭⑮、
快照可验证 ⑯、协议正确 ⑰、样本量正确（普查封顶如实报告）⑱、无真实标注 ⑲、无抽样执行 ⑳、
无 margin 实现 ㉑、无自动确认 ㉒、无自动归档 ㉓）。

**Hard Stop 遵守**：本任务到此停止。下一阶段（真实人工标注 / 抽样执行 / GT / precision /
margin / 自动确认 / 自动归档）均需 Owner 任务书下发后进行。
