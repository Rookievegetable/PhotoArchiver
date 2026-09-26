# Stage F 校准与性能证据报告（真实 473 张中文路径照片库）

> Stage F（校准、性能与生产验证）证据基线。**本文只记录证据与 Owner 裁决
> 点，不含任何阈值变更**——阈值/质量公式变化必须走 Owner/规格裁决
> （执行计划 Stage F："结论写入 ADR 候选，若形成长期裁决，先请求 owner
> 批准"）。
>
> 数据来源：真实生产照片库 `E:\BaiduNetdiskDownload\测试Photo`（473 张，
> 全部绝对路径、中文文件名，与生产库 photos 表一致）。全部数据写入一次性
> 验证库，生产库未触碰。
>
> 复现：`python tools/validate_stage_f.py --report docs/development/evidence/stage-f-real-run.json`
> （识别 `--workers 4`；验证库 001→007 全部迁移执行）。

## 1. 全链路真实数据验证（2026-09-25，InsightFace buffalo_l CPU）

| 阶段 | 结果 |
|---|---|
| 扫描登记 | 473/473 成功，0 失败，0.96s（中文路径无障碍） |
| 识别（4 workers） | **1441 张脸**，未读 0，无脸 1，检测异常 0；83.05s ≈ **5.7 photos/s**；status=completed |
| Stage D 聚类 | **44 簇 / 1441 成员**；8.29s；tracemalloc 峰值 **70.21 MB**；excluded 0 |
| 聚类 rerun | 2 代并存，历史保留 ✅（两代 cluster_count 均 44） |
| Stage E 建议 | 10 条（roster 10 人，ordered 全部；无样本库故无 sample_match） |
| 确认 ×6 | 兼容层 **199 条 APPROVED**（每照片一条 × 6 人），样本 199 |
| ArchivePlanner | planned **199** / skipped 0——(person, photo) 多 attribution 全部进入归档计划 ✅ |

faces_per_photo 分布：1 脸 ×399、7 脸 ×43、8×4、11×5、13×1、23×1、36×17、0 脸 ×1
——双峰：单人照 + 活动密集连拍（17 张连拍每张 36 脸）。

## 2. 校准证据（当前值 → 验证结果 → Owner 依据）

| 规则 | 当前值 | 真实数据验证结果 | 依据/裁决点 |
|---|---|---|---|
| `quality_score` 公式 | = det_score（Stage C 占位） | 分布紧密：p10 0.837 / p50 0.872 / p90 0.908；**0 条 < 0.50**，267 条 ≥ 0.90 | 方案 §5.2"公式 F 校准"——无真值标注无法评估公式优劣，维持现状 |
| low-quality threshold | 0.0（禁用） | 真实分布下"低质量带"几乎不存在（<0.30 为 0）——启用与否当前不影响聚类输入 | Owner 裁决 2026-09-25（默认禁用待 F 校准）；维持 |
| `cluster_sim_threshold` | 0.5（candidate 门） | 1441 脸 → 44 簇（36 簇 21-50 人、4 单例）；无全局巨簇 | 方案 §D-2 默认值；**聚类质量需 Owner 以缩略图人工复核**（无 ground truth 不做数值裁决） |
| `consistency_threshold` | 0.4（完全链接，包含 ≥） | 完全链接未产生链式巨簇（最大簇 < 51）；与 626/1441 两轮一致 | 方案 §D-2；维持 |
| qualified sample | 全部有有效嵌入成员 | 6 次确认沉淀 199 样本（≈ 每簇全部成员照片） | **Spec Gap E-SG-4**：合格样本未定义，维持现状待裁决 |
| similarity 量化 | 6 位小数 | 两轮聚类结果完全一致（确定性复现） | Stage D 实现；维持 |

**结论：无任何阈值变化提案。** 校准数据显示当前默认值在真实数据上行为
稳定、无病态结构（无巨簇/无碎片化爆炸）；聚类质量的人工复核（缩略图）
是 Owner 侧后续动作，不属于本轮数值裁决。

## 3. 性能证据

### 3.1 识别吞吐（真实 473 张，4 workers）

**5.7 photos/s**（83.05s）。参照 bench_recognition 基线（同机，纯管线
4-worker 11.22 photos/s，无观测持久化）——全脸管线含逐脸观测/兼容行
持久化后吞吐约一半，符合预期（写放大 ~1441 观测 + 473 兼容行）。

### 3.2 聚类 CPU / 内存（真实 1441 观测）

- 耗时 8.29s；tracemalloc 峰值 70.21 MB。
- 矩阵理论值 n²×8B = 16.6 MB @1441。

### 3.3 相似度矩阵规模风险（合成基准，`tools/bench_clustering_scale.py`）

| scale | matrix_MB | matrix_build_s | cluster_total_s | peak_MB |
|---|---|---|---|---|
| 250 | 0.50 | 0.004 | 0.248 | 1.05 |
| 500 | 2.00 | 0.004 | 0.593 | 4.09 |
| 1000 | 8.00 | 0.008 | 1.698 | 16.19 |
| 2000 | 32.00 | 0.037 | 4.666 | 64.37 |
| 4000 | 128.00 | 0.132 | 15.983 | 256.74 |

**结论**：当前规模（1441 观测）内存/耗时可接受（<10s、<100MB）。
外推 10k+ 观测 → 矩阵 ~800MB+、candidate 阶段分钟级——分块/流式
相似度为 10k+ 库的记录在案后续项，**当前不构成阻塞，未做优化**
（无证据支持现在重构）。

## 3.4 千级生命周期压力（Stage F Wave 3，2026-09-26）

`tools/stress_lifecycle_stage_f.py`，真实 InsightFace + 真实 SQLite，1000 张
单脸样本（唯一像素变体，确保内容哈希去重后 1000 张全部登记），4 workers：

| 阶段 | 结果 |
|---|---|
| Phase 1 取消（t+30s） | status=**cancelled**；取消传播 60.0s（协作式：当前检测批完成后返回）；elapsed 90.0s；**已保留 337 条观测**（已消费并提交的批次） |
| Phase 2 重试（663 张剩余） | status=**completed**；63.3s；663 条观测；**新 run id**（历史 run 未被覆盖） |
| Phase 3 一致性 | run_rows=2 / distinct_run_ids=2；photo_rows=1000；跨 run 照片重叠 **0**；重复 (run, photo, face_index) **0**；两代观测并集覆盖 **1000/1000**；tracemalloc 峰值 **79.2 MB** |

结论：取消为协作式传播（无死锁、无锁泄漏、无重复终态）；重试按 Stage F
语义只处理未产出观测的照片并创建新运行；历史运行及其 337 条观测完整保留。

## 3.5 老旧数据库升级完整性（Stage F Wave 3，2026-09-26）

`tools/verify_upgrade_integrity.py`：生产库**副本**（源库只读、零触碰，
版本 alembic 003、546 人 / 473 照片 / 472 识别结果 / 3 导入批次 / 544 草稿行）
→ alembic upgrade head：

| 检查 | 结果 |
|---|---|
| 版本 | 003 → **007_assignments_and_person_samples** |
| 既有表计数 | 全部不变（people 546 / photos 473 / recognition_results 472 / import_batches 3 / import_draft_rows 544） |
| people 关键字段（id/name/created_at/roster_order/source_batch_id 抽样 20） | **零未授权变化** |
| Stage C/D/E 新表 | 9 张全部空初始化 = 预期（非数据丢失） |
| FK 检查 | 升级前 0 违规 / 升级后 **0 违规** |
| 历史人员回填交互 | 8 人回填成功（538 已关联者跳过），roster_order 追加不覆盖，**重复执行 no-op** |

确定性回归测试：`tests/integration/test_upgrade_integrity.py`（3 项：逐行
对比零丢失 / 新表空初始化 / 升级→回填交互幂等）与
`tests/unit/application/test_stage_f_lifecycle.py`（5 项：1200 张完整运行、
中途取消部分保留、重试建新 run、连续 cancel/retry/complete 循环、
unreadable/error 亦可重试）。

## 4. 数据一致性证据

- rerun：两代并存、首代簇数不变 ✅
- 确认 → 兼容行 → planner：199 行 → 199 计划项，一一对应 ✅
- 多 attribution：6 人 × 各自照片集合全部进入计划（(person, photo) 作用域）✅
- 失败分类：473 张中 unreadable=0 / no_face=1 / error=0——失败清单机制就绪
  （失败明细导出属 Stage F 后续提交的"重分析入口 + 失败报告"项）

## 5. 本轮 Stage F 范围说明

本轮覆盖 Owner 任务书 4 个检查点（校准/真实数据/性能/一致性）。
执行计划 Stage F 的其余两项（历史人员 source_batch_id/roster_order 回填、
历史照片重分析入口 + 失败清单导出）属 Stage F 后续提交，本轮未实施。

## 6. 遗留 Owner 裁决点（不阻塞本轮）

1. 聚类质量人工复核（44 簇缩略图抽样）——决定 0.5/0.4 是否进入 ADR。
2. E-SG-4 合格样本定义。
3. E-SG-5 改派后旧样本停用（已实现）之外的样本恢复语义。
4. 低质量门启用阈值（当前证据：真实分布无低质量带，启用无实际效果）。
