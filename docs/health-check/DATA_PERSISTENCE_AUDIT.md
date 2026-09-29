# DATA_PERSISTENCE_AUDIT.md — 全面工程健康审计 · 数据模型与持久化审计（Stage 3）

- **审计日期**: 2026-09-28 ｜ 对象: HEAD `2823d1c` ｜ 性质: READ-ONLY
- **方法**: 迁移链 001–008 DDL 逐表提取 → 17 个 SQLite 仓储 SQL 写/读语句对账 → 迁移运行时（新库/旧库/升级/回滚/幂等）+ 事务边界 + 备份/完整性机制核验

---

## 1. Schema 清单 [VERIFIED]

11 张业务表（002 建基座 → 003/004/005/006/007 增量 → 008 改造）：

| 表 | 迁移 | 关键约束 |
|---|---|---|
| people | 002+003 | `identity UNIQUE`、roster_order/source_batch_id 扩列+索引 |
| folders | 002 | `UNIQUE(raw_path, path_base)` |
| photos | 002 | `UNIQUE(raw_path, path_base)`、FK folder ON DELETE SET NULL、metadata_* 6 列 |
| recognition_results | 002→008 | FK photo CASCADE / person SET NULL；confidence 经 008 重建为可空；索引 photo_id/person_id |
| person_embeddings | 002 | FK person CASCADE —— **全 git 历史零生产写入者**（AUD-017） |
| archive_records | 002+008 | person_id FK SET NULL+索引；status 无 CHECK |
| import_batches / import_draft_rows | 003 | draft FK CASCADE、merge_target FK SET NULL、action DEFAULT 'create' |
| recognition_runs / run_photos / run_scopes / face_observations | 004+005 | status/计数列 CHECK 约束、observations `UNIQUE(run_id,photo_id,face_index)` |
| face_cluster_runs / face_clusters / face_cluster_members | 006 | cluster status CHECK（6 态）、members `UNIQUE(cluster_id,observation_id)` |
| cluster_person_assignments / person_face_embeddings | 007 | status/source CHECK、score CHECK [-1,1]、samples `UNIQUE(person_id,observation_id)`、**assignment.person_id ON DELETE CASCADE** |

**表×读写对账**：17 张表全部有 ≥1 写入者与 ≥1 读取者，无孤儿表。独有"定义未用"列：`import_batches.file_hash`（parse 服务写入，全仓无读取方——同文件重复导入不去重，P3 登记入 AUD-018）。

## 2. 迁移审计 [VERIFIED]

- **顺序/链**：001→002→…→008 线性链，down_revision 逐一衔接；每迁移含 upgrade+downgrade。
- **新库初始化**：`initialize_schema` 不再持 DDL——mkdir + PRAGMA（foreign_keys ON / busy_timeout / WAL / 仅新库 `user_version=4` stamp）+ 交由 Alembic `upgrade head`（`sqlite_connection.py:136-155`、`alembic_runner.py:23-39`；专项测试 `test_initialize_schema_uses_alembic_not_raw_sql`）。
- **旧库升级**：每次启动自动 upgrade head；frozen 适配（`sys._MEIPASS` 解析 alembic 数据文件）；旧 v1–v3 库经 user_version 探测兼容（ADR-024 路径）。
- **008 幂等/回滚**：upgrade 先探测列存在；回填仅在姓名**唯一**命中时执行（重名保持 NULL 不猜身份）；downgrade 先 `UPDATE … SET confidence=0 WHERE confidence IS NULL` 再重建 NOT NULL 表（`:124`）——回滚路径数据安全。
- **测试覆盖**（`test_alembic_migrations.py` 11 项 + `test_upgrade_integrity.py` 3 项）：全表/全索引创建、head stamp、downgrade 幂等、upgrade 幂等、迁移后 CRUD、008 专属（person_id+可空 confidence+按唯一名回填）、升级逐行数据零丢失、D/E 新表空初始化、升级后回填幂等。**覆盖面良好**。
- 未执行项（诚实声明）：真实生产库（%LOCALAPPDATA%）上的升级演练本轮未跑（READ-ONLY 约束）；证据 `stage-f-upgrade-real.json` 声称已在生产库副本实测（untracked 证据文档，待 Stage 5 核对其真实性）。

## 3. 事务与并发 [VERIFIED]

- `SQLiteUnitOfWork`：thread-local 事务 scope，并发 worker 各持独立 UoW 于共享连接池；正常退出 commit、异常回滚（`sqlite_unit_of_work.py:19-60`）。
- 连接层：`PRAGMA foreign_keys=ON`（FK 真实生效，级联可信）、`busy_timeout`、WAL 模式（`sqlite_connection.py:26-29`）。
- 应用层事务边界：导入确认/审核/配对确认/归档批均 UoW 包裹（Stage 2 已核）；批间无长事务残留。

## 4. 备份与完整性 [VERIFIED]

- `backup.py`：启动时 `VACUUM INTO` 事务一致性快照 + 滚动窗口保留 + 同秒重名回退；恢复演练测试 `test_backup_restore_drill.py`。
- `integrity.py`：只读 `PRAGMA quick_check`，损坏即 `CorruptedDatabaseError`（启动路径，配合 `test_bootstrap_corruption.py`）。

## 5. 发现

### AUD-017（P2）——匹配候选源 `person_embeddings` 全历史零写入者，承诺的样本化匹配未实现

- **事实**：`person_embeddings`（002）唯一写方法 `sqlite_face_embedding_repository.save():42` 在**全 src 与全 git 历史**（`git log -S` 验证）均无调用方；而 `match_persons_service.py:159` 与 `run_recognition_service.py:66` 的匹配候选均来自 `FaceEmbeddingRepository.list_all()` → 该表。
- **后果**：任何用户的库中该表恒空 → 识别期自动匹配永远返回 None；身份归属完全依赖人工审核（D-1）与配对工作台。新链沉淀的 `person_face_embeddings` 样本（007）**不回灌**匹配候选。
- **设计意图 vs 现实**：`people-import-face-clustering-development-plan.md:11` 明文承认"person_embeddings 没有人员样本登记入口"；`:155` 承诺"后续 1:N 匹配基于多样本或中心特征，而不是现有单条 person_embeddings 覆盖式写入"——该"后续"在已冻结的阶段 C–F 中**未实现**。与 D-1 裁决（人工身份=最终结果）方向一致，不构成功能性缺陷，但属于**声明演进路径的未落地项 + 永久死写入路径**，测试以 `_StubFaceEmbeddingRepository` 伪造候选掩盖了生产空转（`test_match_persons_service.py:58`）。
- **判定**：P2（业务预期"确认后同类照片自动归属"未满足；冻结签核前需 owner 知情决策：实现样本化候选 或 显式登记为接受限制）。

### AUD-018（P3）——Schema 一致性 nit 集合

1. **级联策略不一致**：`cluster_person_assignments.person_id ON DELETE CASCADE`（删人即删配对历史，含 suggested/rejected 决策痕迹）vs `recognition_results`/`archive_records` 的 SET NULL（匿名保留）。同一个人身份在三类表中删除语义不同；删除人员审计可见性依赖 `delete_person_service` 的计数日志。
2. **status 列约束不对称**：004/006/007 新表对 status/score 均有 DB 层 CHECK，而 `recognition_results.status`、`archive_records.status` 仅 NOT NULL（枚举合法性只靠应用层）。
3. **`import_batches.file_hash` 只写不读**（§1）。
4. 以上均为低风险一致性债，不阻塞。

## 6. 正面结论（有证据）

- 迁移体系成熟：线性链、双向迁移、幂等守护、回滚数据安全、frozen 适配、启动自动升级、13 项迁移/升级测试。
- 约束密度高：UNIQUE/CHECK/FK 覆盖全面（除 §5 指出的不对称点），FK 强制开启，WAL+busy_timeout 就绪。
- 备份/完整性/恢复演练闭环。
- 无"代码读不存在列"（17 仓储 SQL 与 Schema 全对账通过）。
