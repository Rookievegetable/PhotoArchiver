# ADR-027 草案 — 阶段 2 Alembic migration 接管 Schema DDL（前置门产出）

> **文档性质**：ADR 草案（Proposed 状态），阶段 2 开工前置门产出。
>
> 按 `AI_ONBOARDING.md §6` 与 B5-a / ADR-026 前置门先例：架构基础设施变更须先出草案评审拍板，拍板后才进实施。拍板后本草案定稿内容写入 `.ai/ARCHITECTURE_DECISIONS.md` ADR-027 Accepted 条目，本文件保留作设计依据。
>
> **产出时间**：2026-08-12 ｜ **产出者**：AtomCode (GLM-5.2) ｜ **状态**：Proposed（待评审拍板）

---

## 0. 裁决点（待拍板）

本草案涉及 3 项设计裁决，属你的决策（非我可自行拍板或查阅替代）：

| 裁决点 | 选项 | 推荐 |
|---|---|---|
| 1 — migration 是否**接管全部** DDL | A. 全接管（6 表 + 6 索引 DDL 全迁 migration，`initialize_schema()` 仅留 `PRAGMA user_version` 兼容 stamp 或完全移除）/ B. 部分接管（migration 持 DDL，`initialize_schema()` 保留 `CREATE TABLE IF NOT EXISTS` 作 fallback）/ C. 新增 `002_split_create_ddl` 而非改造 `001` | A |
| 2 — `001_initial_v4` 改造策略 | A. 原地改造 `001` upgrade/downgrade 持 DDL（downgrade 需 DROP TABLE，但首次 migration 无前版本可回）/ B. 新建 `002_split_create_ddl` 持 DDL，`001` 保留空 stamp 形态 / C. 拆为 `001` stamp + `002` DDL 两步 | B |
| 3 — `PRAGMA user_version` 兼容路径 | A. 完全移除（Alembic 独管版本，`alembic_version` 表替代）/ B. 保留作旧库（v1-v3）迁移探测 stamp / C. 保留仅新库 stamp=4 兼容 | C |

**推荐理由**：裁决点 1=A 全接管线纯粹（Alembic 独管 Schema，无重复路径）；裁决点 2=B 新建 `002` 避免改造 `001` 的 downgrade 难题（首次 migration 无前版本可回，DROP TABLE 无意义）；裁决点 3=C 保留仅新库 stamp=4 兼容旧库迁移路径（ADR-024 已述"新数据库上仍写 `PRAGMA user_version = 4` 保持与旧代码兼容"）。

---

## 1. 背景

### 1.1 ADR-024 现状（实测 2026-08-12）

ADR-024（Accepted 2026-07-25）落地了 Alembic 迁移体系雏形：

- `alembic/` + `alembic.ini` + `alembic/env.py` + `alembic/script.py.mako` 已存
- `alembic/versions/001_initial_v4.py` 已存——**但是空 stamp migration**（upgrade/downgrade 全 `pass`，未真正管理 Schema DDL）
- `infrastructure/database/alembic_runner.py` 的 `run_alembic_migrations()` 已集成 bootstrap
- `requirements/base.txt` `alembic==1.16.4` 已在

**关键缺口**：`sqlite_connection.py:109-206` 的 `initialize_schema()` 仍用 raw SQL `CREATE TABLE IF NOT EXISTS` 创建 6 表 + 6 索引（people/folders/photos/recognition_results/person_embeddings/archive_records），Alembic 仅 stamp 版本未接管 Schema DDL。这是 ADR-024 妥协形态，非 roadmap §190 期望的"Alembic 接管 Schema 版本管理"完整态。

### 1.2 roadmap §18 交付物对照

| roadmap §190 交付物 | 现状 |
|---|---|
| Alembic 初始化与首个 migration | ✅ 已落（但空 stamp） |
| 基础表结构（与 Step 4 实体对齐） | ⚠️ 在 `initialize_schema()` raw SQL 非 migration |
| `alembic upgrade head` 成功 | ✅ 已落（bootstrap 集成） |
| 迁移脚本可重复执行 | ⚠️ 空动作可重复但无 DDL 真迁移 |
| Repository 基类 / Session 生命周期工具 | ❌ 未落（raw sqlite3 非目标 metadata=None 路线） |
| ORM models | ❌ 未落（ADR-024 选择 raw SQL 非ORM 路线） |

**本草案范围**：补"Alembic 接管 Schema DDL"+"迁移脚本可重复执行"+"alembic upgrade head 成功"深化，不动 ORM models / Repository 基类（ADR-024 raw SQL 路线已裁决，不推翻）。

---

## 2. 裁决正文

### 2.1 migration 接管全部 DDL（裁决点 1=A）

`initialize_schema()` 的 6 表 + 6 索引 raw SQL DDL 全迁入 migration，`initialize_schema()` 仅留：
- `database_path.parent.mkdir()` 目录创建
- 兼容 `PRAGMA user_version` stamp（裁决点 3=C，仅新库）
- 调用 `run_alembic_migrations()` 触发 migration（已集成 bootstrap，但 `initialize_schema()` 内部也应确保 Alembic 接管）

**6 表 DDL**（来自 `sqlite_connection.py:117-188`）：
1. `people` — id PK / name / identity UNIQUE / department / note / created_at
2. `folders` — id PK / raw_path / path_base / display_name / total_photos / scanned_photos / created_at + UNIQUE(raw_path, path_base)
3. `photos` — id PK / raw_path / path_base / folder_id FK / original_name / created_at / captured_at / metadata_* / UNIQUE(raw_path, path_base) + FK folder_id
4. `recognition_results` — id PK / photo_id FK / person_id FK / status / confidence / created_at + FK photo_id CASCADE + FK person_id SET NULL
5. `person_embeddings` — person_id PK / embedding BLOB / created_at + FK person_id CASCADE
6. `archive_records` — id PK / photo_id FK / target_* / status / archived_at / error + FK photo_id CASCADE

**6 索引**：idx_photos_folder_id / idx_recognition_results_photo_id / idx_recognition_results_person_id / idx_archive_records_photo_id / idx_archive_records_status

### 2.2 新建 `002_split_create_ddl`（裁决点 2=B）

保留 `001_initial_v4` 空 stamp 形态（避免改造 upgrade/downgrade 的难题——首次 migration 无前版本可回，DROP TABLE 无意义），新建 `002_split_create_ddl.py`：

```python
"""split create DDL from initialize_schema — ADR-027 phase 2.

Revision ID: 002_split_create_ddl
Revises: 001_initial_v4
Create Date: 2026-08-12
"""
revision = "002_split_create_ddl"
down_revision = "001_initial_v4"

from alembic import op

def upgrade() -> None:
    """Create 6 tables + 6 indexes (迁自 initialize_schema raw SQL).
    
    在已由 initialize_schema() CREATE TABLE IF NOT EXISTS 的库上幂等——
    IF NOT EXISTS 守护重复执行不报错。
    """
    op.execute("""
        CREATE TABLE IF NOT EXISTS people (...);
        -- 6 表 + 6 索引 DDL 全迁此
    """)

def downgrade() -> None:
    """DROP 6 表（回滚到空 stamp 状态）。"""
    op.execute("DROP TABLE IF EXISTS archive_records;")
    # 按 FK 依赖逆序 DROP
```

**幂等守护**：`CREATE TABLE IF NOT EXISTS` + `DROP TABLE IF EXISTS` 保留——migration 在已由 `initialize_schema()` 创建的库上重复执行不报错。

### 2.3 `PRAGMA user_version` 兼容路径（裁决点 3=C）

保留 `initialize_schema()` 仅新库（current_version == 0）stamp `PRAGMA user_version = 4`——ADR-024 已述"保持与旧代码兼容"。Alembic 的 `alembic_version` 表独立管 migration 版本，`PRAGMA user_version` 仅作旧库（v1-v3）迁移探测兼容。

**移除条件**：未来确认无旧库（v1-v3）后，可单独裁决移除 `PRAGMA user_version` 全路径。

---

## 3. 影响范围

| 模块 | 变更类型 | 文件 |
|---|---|---|
| Alembic migration | 新增 | `alembic/versions/002_split_create_ddl.py`（6 表 + 6 索引 DDL） |
| Infrastructure database | 改造 | `infrastructure/database/sqlite_connection.py`（`initialize_schema()` 移除 CREATE TABLE 重复路径，仅留 mkdir + PRAGMA stamp + 调 Alembic） |
| Tests | 新增 | `tests/integration/database/test_alembic_migrations.py`（migration up/down + Schema 版本一致 + Repository 对照回归） |
| Docs | 改造 | `.ai/PROJECT_STATUS.md`（§3/§5/§6 阶段 2 落地）+ `.ai/ARCHITECTURE_DECISIONS.md`（ADR-027 入 Register）+ `.ai/DOCUMENT_INDEX.md`（本草案登记） |

**不变**：Domain Schema、ORM models（ADR-024 raw SQL 路线不推翻）、Repository 基类/Session 生命周期工具、`alembic/env.py` / `alembic.ini` / `alembic_runner.py`（已够用）、`001_initial_v4.py`（保留空 stamp 形态）、依赖（`alembic==1.16.4` 已在）。

---

## 4. 与既有裁决的关系

| 裁决/规则 | 关系 |
|---|---|
| ADR-024（Alembic 迁移体系） | 本草案深化 ADR-024 妥协形态——migration 从空 stamp 接管真实 DDL，不推翻 ADR-024 raw SQL 路线 |
| ADR-005（Superseded by ADR-024） | 无变化——ADR-024 已取代 ADR-005，本草案深化 ADR-024 不重新激活 ADR-005 |
| DEP-030/032（Infrastructure 数据库边界） | 无变化——DDL 仍在 Infrastructure 层，Application/Domain 不触 |
| git-rules §18（大重构拆分） | 提交边界遵循"结构 → 实现 → 测试 → 文档"主题拆分 |

---

## 5. 测试计划

| 测试文件 | 类型 | 验收点 |
|---|---|---|
| `tests/integration/database/test_alembic_migrations.py` | **新建** | (1) `alembic upgrade head` 成功 + Schema 版本一致；(2) migration up 可执行（6 表 + 6 索引创建）；(3) migration down 可执行（6 表 DROP）；(4) 重复执行幂等（IF NOT EXISTS 守护）；(5) Repository 对照回归（CRUD 不退化） |

**回归守护**：现有 `sqlite_connection.py` / Repository 测试不退化（migration 接管 DDL 后，`initialize_schema()` 路径改但 Repository CRUD 路径不变）。

---

## 6. 执行顺序（Protocol-first 调整）

```text
1. 现状已核对完毕（见本草案证据）
2. 改造 002_split_create_ddl.py：6 表 + 6 索引 DDL 迁入 migration upgrade + downgrade
3. 改造 sqlite_connection.py：initialize_schema() 移除 CREATE TABLE 重复路径
4. 补 Alembic 测试：migration up/down + Schema 版本一致 + Repository 对照回归
5. 更新文档与 PROJECT_STATUS（§3/§5/§6）+ ADR-027 入 Register
6. 运行质量门与架构审查
7. 提交（refactor: alembic migrations own schema ddl）
```

---

## 7. 完成标准

- [ ] `alembic upgrade head` 成功且 migration 真正创建 6 表 + 6 索引（非空 stamp）
- [ ] `alembic downgrade base` 可执行且 6 表 DROP
- [ ] migration 重复执行幂等（IF NOT EXISTS 守护）
- [ ] `initialize_schema()` 不再持 CREATE TABLE 重复路径（仅 mkdir + PRAGMA stamp + Alembic 触发）
- [ ] Repository CRUD 对照回归不退化
- [ ] Application / Domain 不 import `sqlite3` / SQLAlchemy（DEP-030/032 守护）
- [ ] 不新增依赖、不改 Domain Schema（`alembic==1.16.4` 已在，DDL 迁移不改表结构）
- [ ] Ruff、MyPy、pytest 全绿（实测）
- [ ] ADR-027 入 Register + DOCUMENT_INDEX 登记 + 文档指针可解析

---

## 8. 拍板后流转

```text
本草案（Proposed）评审拍板
  ↓
写入 .ai/ARCHITECTURE_DECISIONS.md ADR-027 Accepted 条目
  ↓
.ai/DOCUMENT_INDEX.md 登记 phase2-adr-draft.md（若草案落盘）
  ↓
按 §6 顺序进实施
  ↓
提交（refactor: alembic migrations own schema ddl）
  ↓
质量门实测 + 架构审查 + 文档指针现场验证
  ↓
完成标准 §7 全勾
```

---

> 📝 本草案由 AtomCode (GLM-5.2) 于 2026-08-12 产出，属阶段 2 开工前置门评审材料。拍板后定稿内容写入 `.ai/ARCHITECTURE_DECISIONS.md` ADR-027 Accepted 条目。
