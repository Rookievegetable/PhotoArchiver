# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**"项目现在开发到哪里了？"**
>
> 每次开发结束后刷新；不保留历史状态。
>
> Version: 1.15.6 · Last Updated: 2026-09-08 · Status: Live

---

## 1. Roadmap（开发路线图概览）

权威 15 步路线图：`.ai/business/roadmap.md`。

| Step | 名称 | 状态 |
|---|---|---|
| 0.5–11 | Walking Skeleton、基础设施、Domain、导入、扫描、缩略图、人脸识别、归档 | ✅ Completed |
| 12–14 | Main UI、Settings、Export | ✅ Completed |
| 15 | Plugin System | ✅ Completed |

M1–M7 及 Step 0.5–15 全部完成；阶段 B 业务增强 B1–B5 与收官加固阶段 0–3 均已落地。此后进入发布工程与桌面验收驱动的迭代修复（v2.3.x 系列已发布至 v2.3.2）。

---

## 2. Current Step（当前开发阶段）

**Phase E 库管理 E-1~E-5 全部实施完成，v2.4.0 发版准备就绪（2026-09-08）**——版本链已 bump（pyproject / .env.example / CHANGELOG `[2.4.0] - 2026-09-08`）、用户指南已补章（`docs/user-guide/workflow.md` ⑤ 库管理 + 重扫对账 + prune-missing CLI）、发版前全量回归 **710 passed / 3 skipped / 0 failed**。**待 owner 签核发版**（tag + push + release body 为 owner 动作，GIT-020）。开发计划与裁决记录：`docs/development/phase-e-deletion-plan.md` + ADR-034（D1–D6 全部按建议执行）。

本版本为新增能力 minor 版（库管理 P2-1/P2-2/P2-3）：

- **删除登记**（照片，D1/D3）：照片墙多选 → 确认对话框（级联计数：识别/归档随删）→ 事务内幂等移除；磁盘文件一律不动。
- **删除人员**（D2/D3）：下拉选人实时预览（嵌入随删、识别归属置空为"未知人员"、照片全保留）→ 确认执行。
- **重复照片处置**（D6）：重复报告「按建议处置」——每组保留最早注册一张（同刻 id 决胜），执行端逐项复核防误删。
- **重扫对账**（D5）：内容变化（hash 强比对 / mtime+size 弱退化）自动刷新元数据（`update_metadata` 只刷 metadata 列，captured_at 快照保留）；`updated=` 计数进结果 DTO 与 scan CLI 输出。
- **prune-missing CLI**（D5）：失联登记 dry-run 默认列出（含期望路径），`--execute` 才清理；扫描绝不自动删库。
- 全量删除操作走确认流 + loguru 审计行 + Phase B 启动备份兜底。

v2.3.2（上一版，桌面复验修复：EXIF 拍摄时刻 ISSUE-019 + 照片墙 + 占位）已于 2026-09-06 签核收官。

### 历史发版锚点

| 版本 | tag → 提交 | 主题 |
|---|---|---|
| v2.3.0 | `e14409e` | 数据安全底线 + 运行时正确性（Phase A/B/C，D-B1~D-B8 裁决） |
| v2.3.1 | `90c46db` | 桌面 UI 中文化 + 工具栏纯化 + 人员筛选智能搜索（owner 裁决多轮折入单一发布；tag 二次重打至 CI 绿树） |
| v2.3.2 | `2aadcee` | 桌面复验修复：EXIF 拍摄时刻 + 照片墙 + 占位 |
| v2.4.0 | 待 owner 打 tag | 库管理：删除登记 / 删除人员 / 重复处置 / 重扫对账 / prune-missing CLI（Phase E） |

更早锚点：v1.0.0→`49b2ac6`、v2.0.0→`ba3ad02`、v2.1.0→`bd52fbb`、v2.2.0→`f9fb8c5`。

---

## 3. Project Status（项目当前状态）

| 范围 | 状态 | 当前事实 |
|---|---|---|
| 15 步产品路线图 | ✅ | Step 0.5–15 全部实现并验证。 |
| 版本链 | ✅ | v2.4.0 三处一致（pyproject / .env.example / CHANGELOG `[2.4.0] - 2026-09-08`）；历史锚点 v2.3.2 保留。 |
| CI | ✅ | run #46（head `2aadcee`）三平台 success——v2.3.2 发布树的直接实证；run #44（ISSUE-019 修复）亦绿。 |
| 桌面复验 | ✅ | 机制项（N1–N4 自动化：1200 行导入闭环/取消一致性/备份恢复演练/换目录子进程）+ 感知项（J1–J7 owner 逐项判定）全部通过。 |
| 未决问题 | ✅ 清零 | ISSUE-019 已修复并经真机终验关闭（条目同提交删除）。 |
| Limit 登记 | 4 项 | LIMIT-001（真实缺模型 E2E 未入 CI）/ LIMIT-002（取消为任务边界粒度，设计特征）/ LIMIT-004（Windows 本地子集顺序原生崩溃）/ LIMIT-006（macOS CI runner 压力扫描段错误，darwin skip），均 Low、不阻塞。 |
| Release body | ✅ | v2.3.2 body 已由 owner 粘贴并经 API 缓存穿透回读实证（668/3/0 + 全部小节 + 构建自 `2aadcee`）。 |

### 数据库 Schema

Alembic 管理（`001_initial_v4` + `002_split_create_ddl`，ADR-027）；`PRAGMA user_version = 4`。本版未改 Schema。

---

## 4. Current Modules（当前模块状态）

| 模块 | 状态 | 关键位置 |
|---|---|---|
| Logging / Configuration | ✅ | `infrastructure/logging/`、`infrastructure/config/` |
| Database | ✅ | Alembic 管理（ADR-027） |
| Domain / Import / Scan / Thumbnail | ✅ | `domain/`、`application/services/`、`infrastructure/`；`PillowPhotoMetadataReader` 支持 Exif 子 IFD 拍摄时刻（ISSUE-019 修复） |
| Recognition / Review | ✅ | InsightFace detect/recognize/match 与审核闭环 |
| Archive | ✅ | Planner → Plan → Executor，captured_at 现对真实相机照片正确分桶 |
| UI / Settings / Export | ✅ | 主窗口、设置闭环、Excel/CSV/HTML 导出、照片墙网格布局 |
| 人员筛选 | ✅ | 三轴组合筛选 + 人员轴键入即时搜索（`presentation/person_matcher.py` 四级智能排名） |
| Plugins | ✅ | 发现/加载/生命周期 + PluginContext 读方法 + import_people 写方法；示例插件不自动加载（外部扩展点） |

---

## 5. Last Session（最近一次开发记录）

| 项目 | 值 |
|---|---|
| 时间 | 2026-09-08（本地） |
| 生成者 | Cline |
| 会话范围 | 交接恢复 → **E-2 收尾**（级联测试修复 + 补 D1 归档断言）→ **E-3 实施**（Application 四删除用例 + 装配 + 真库测试 14）→ **E-4 实施**（UI 删除入口）→ **E-5 实施**（重扫对账 + prune-missing CLI）→ **E-6 收尾**（指南补章 + 版本链 bump + 发版前回归）。 |
| 关键产出 | ① E-2：`test_deletion_cascade.py` 修复补强 4 用例；② E-3：四个删除/对账 Service + DTO/Command/UseCase + 审计 + 装配 + 14 测试；③ E-4：`PhotoDeletionConfirmDialog`、`PersonDeletionDialog`、重复报告处置按钮 + controller 二次确认编排、main_window 工具栏双入口、ui_text 中文化、8 测试；④ E-5：`update_metadata` 双实现、扫描变更检测、`prune-missing` CLI、12 测试；⑤ E-6：`docs/user-guide/workflow.md` 补 ⑤ 库管理章（删除登记/删除人员/重复处置/失联清理 + 附加能力表/命令行表更新）+ 版本链 bump 至 **2.4.0**（pyproject / .env.example / CHANGELOG `[2.4.0] - 2026-09-08` 英文全段）+ 发版前全量回归 **710 passed / 3 skipped / 0 failed**（连续四次全绿）；⑥ 质量门全绿：ruff 0 / mypy 189 files 0 / pip check 通过。 |
| 当前质量门 | `ruff check .` 通过；`mypy src` 189 个源文件无问题；pytest 全量 **710 passed / 3 skipped / 0 failed**（发版前实测）。 |
| 工作区 | HEAD = `41f7e3a` → 本轮 E-6 prepare 提交，领先 origin/main 10 commit；PROJECT_STATUS 同步刷新。 |
| Remaining | **v2.4.0 发版动作（owner）**：本地打 tag `v2.4.0`（建议打在 release prepare commit）→ push 分支与 tag（触发 release workflow）→ GitHub Release body 可直接复用 CHANGELOG `[2.4.0]` 段 → 签核收官。 |

---

## 6. Next Step（下一步开发计划）

**v2.3.2 已签核收官**（2026-09-06）；Phase E 实施中（D1–D6 已拍板，E-1/E-2 完成）。可选后续候选（均需 owner 另行立项）：
- 历史照片 `captured_at` 回填 CLI（参照 backfill-content-hash 先例）；
- LIMIT-006 macOS 原生崩溃追查（需 macOS 调试手段）；
- 完整路径锚定 P1（用户目录/注册表定位）。

| Next Step | **v2.4.0 发版（owner 动作，GIT-020）**：本地打 tag `v2.4.0` → push 分支与 tag 触发 release workflow → GitHub Release body 复用 CHANGELOG `[2.4.0]` 段 → 签核收官。Phase E 全部六期（E-1~E-6）实施完成。 |

---

## 7. Key Files（关键文件索引）

| 职责 | 文件 |
|---|---|
| 插件协议与上下文 | `src/photo_archiver/application/ports/plugin.py`、`plugin_context.py` |
| 人员导入服务 | `src/photo_archiver/application/services/import_people_service.py` |
| UI 文案表（中文化单一置换点） | `src/photo_archiver/presentation/ui_text.py` |
| Qt 标准翻译装载 | `src/photo_archiver/presentation/translations.py` |
| 人员搜索智能排名 | `src/photo_archiver/presentation/person_matcher.py` |
| EXIF 元数据读取（子 IFD 修复） | `src/photo_archiver/infrastructure/filesystem/pillow_photo_metadata_reader.py` |
| 数据库初始化/迁移 | `src/photo_archiver/infrastructure/database/sqlite_connection.py`、`alembic_runner.py`、`alembic/versions/002_split_create_ddl.py` |
| 质量验证 | `tests/`、`.github/workflows/ci.yml` |
| 发布工作流 | `.github/workflows/release.yml` |

---

> 本文件只描述当前状态；历史决策见 `.ai/ARCHITECTURE_DECISIONS.md`，当前问题见 `.ai/KNOWN_ISSUES.md`，路线图见 `.ai/business/roadmap.md`。
