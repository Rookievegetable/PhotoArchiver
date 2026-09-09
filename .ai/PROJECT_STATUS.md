# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**"项目现在开发到哪里了？"**
>
> 每次开发结束后刷新；不保留历史状态。
>
> Version: 1.15.5 · Last Updated: 2026-09-08 · Status: Live

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

**v2.3.2 已发布并经 owner 签核（2026-09-06）——发布轮正式收官**。本版本为桌面复验驱动的修复版：

**Phase E 库管理实施中（owner 选定路径二）**：完整开发计划落 `docs/development/phase-e-deletion-plan.md`（实证 schema 级联矩阵 + ADR-034 裁决点 D1–D6 + 实施分期 E-1~E-6，≈7–8 天）。**D1–D6 已全部拍板**（2026-09-06，全部按建议执行——ADR-034 定稿登记 `ARCHITECTURE_DECISIONS.md`）：E-1 完成；**E-2 完成**（Domain 协议扩删 + SQLite 分块 DELETE + InMemory 替身 + 级联矩阵测试 4 用例）；**E-3 完成**（Application 层四删除/对账用例 + 级联预览 DTO + 审计 + 装配 + 真库测试 14 用例）；**E-4 完成**（UI：照片列表多选「删除登记」→ 确认对话框（级联计数 + D3 磁盘不动明示）→ 刷新；「删除人员」交互对话框（下拉选人 + 实时预览嵌入删除/识别置空 + 照片保留明示）；重复报告「按建议处置」（每组保留最早注册，二次确认 + 完成反馈）；全中文化走 ui_text + 8 用例）；**E-5 完成**（重扫对账 D5：`PhotoRepository.update_metadata` 双实现（只刷 metadata 列，captured_at 快照保留）+ `ScanAndRegisterPhotosService` 内容变更检测（hash 强比对，无 hash 退化 mtime+size；updated_count 进 DTO/CLI 输出）+ `prune-missing` CLI 子命令（dry-run 默认，--execute 才清理，失联路径逐行列出供核实）+ 12 用例）。

- **EXIF 拍摄时刻修正（ISSUE-019，已修复关闭）**：元数据读取器此前只读 IFD0 顶层 tag，真实相机/手机照片（标准 Exif 子 IFD 结构）的 `captured_at` 被文件修改时间冒名顶替。现按降级链读取：子 IFD DateTimeOriginal(36867) → 子 IFD DateTimeDigitized(36868) → IFD0 顶层（历史兼容）→ mtime。真机终验通过：手机直出照 IMG_20240713_164201.jpg（EXIF 2024:07:13 16:42:01）经真实 UI 扫描全链精确命中；已入库照片不回填（快照语义）。条目已自 KNOWN_ISSUES 删除。
- **照片墙布局**：照片列表由"一行一张巨图"改为换行多列网格（约 160px 缩略格 + 文件名条）；委托器单元格尺寸恒定化（修复 uniformItemSizes + 异步缩略图导致的单元坍缩）。
- **人员筛选占位修复**：可编辑人员下拉的"全部人员"占位此前在 Windows 桌面不渲染，改由内部 lineEdit 承载后显示可靠。

### 历史发版锚点

| 版本 | tag → 提交 | 主题 |
|---|---|---|
| v2.3.0 | `e14409e` | 数据安全底线 + 运行时正确性（Phase A/B/C，D-B1~D-B8 裁决） |
| v2.3.1 | `90c46db` | 桌面 UI 中文化 + 工具栏纯化 + 人员筛选智能搜索（owner 裁决多轮折入单一发布；tag 二次重打至 CI 绿树） |
| v2.3.2 | `2aadcee` | 桌面复验修复：EXIF 拍摄时刻 + 照片墙 + 占位（本版） |

更早锚点：v1.0.0→`49b2ac6`、v2.0.0→`ba3ad02`、v2.1.0→`bd52fbb`、v2.2.0→`f9fb8c5`。

---

## 3. Project Status（项目当前状态）

| 范围 | 状态 | 当前事实 |
|---|---|---|
| 15 步产品路线图 | ✅ | Step 0.5–15 全部实现并验证。 |
| 版本链 | ✅ | v2.3.2 三处一致（pyproject / .env.example / CHANGELOG `[2.3.2] - 2026-09-06`）。 |
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
| 会话范围 | 交接恢复 → **E-2 收尾**（级联测试修复 + 补 D1 归档断言）→ **E-3 实施**（Application 四删除用例 + 装配 + 真库测试 14）→ **E-4 实施**（UI 删除入口）→ **E-5 实施**（重扫对账 + prune-missing CLI）。 |
| 关键产出 | ① E-2：`test_deletion_cascade.py` 修复补强 4 用例；② E-3：四个删除/对账 Service + DTO/Command/UseCase + 审计 + 装配 + 14 测试；③ E-4：`PhotoDeletionConfirmDialog`、`PersonDeletionDialog`、重复报告处置按钮 + controller 二次确认编排、main_window 工具栏双入口、ui_text 中文化、8 测试；④ E-5：`PhotoRepository.update_metadata`（Protocol + SQLite/InMemory 双实现，只刷 metadata 列保留 captured_at 快照）、`ScanAndRegisterPhotosService` 变更检测（hash 强比对 / mtime+size 弱退化 / reader 缺失与读失败保守 skip、DTO 加 updated_count、CLI scan 输出加 updated）、`prune-missing` CLI 子命令（dry-run 默认逐行列失联路径、--execute 才清理、无失联友好提示）、deletion 命令补进 application 顶层导出、12 测试；⑤ 质量门全绿：ruff 0 / mypy 189 files 0 / pytest **710 passed / 3 skipped / 0 failed**。 |
| 当前质量门 | `ruff check .` 通过；`mypy src` 189 个源文件无问题；pytest 全量 **710 passed / 3 skipped / 0 failed**（本地实测）。 |
| 工作区 | HEAD = `eeb9c21` → 本轮 E-5 提交，领先 origin/main 8 commit；PROJECT_STATUS 同步刷新。 |
| Remaining | Phase E E-6（收尾发版）：全量回归（已连续三轮全绿，发版前再跑一轮）+ 用户指南补章（删除/对账/CLI 新能力）+ 版本链 bump（pyproject/.env.example/CHANGELOG → 2.4.0）+ release 流程。 |

---

## 6. Next Step（下一步开发计划）

**v2.3.2 已签核收官**（2026-09-06）；Phase E 实施中（D1–D6 已拍板，E-1/E-2 完成）。可选后续候选（均需 owner 另行立项）：
- 历史照片 `captured_at` 回填 CLI（参照 backfill-content-hash 先例）；
- LIMIT-006 macOS 原生崩溃追查（需 macOS 调试手段）；
- 完整路径锚定 P1（用户目录/注册表定位）。

| Next Step | **Phase E-6**（收尾发版 v2.4.0）：用户指南补章（删除登记/删除人员/重复处置/重扫对账/prune-missing CLI）+ 版本链 bump（pyproject / .env.example / CHANGELOG `[2.4.0]`）+ 全量回归 + owner 签核发版（计划见 `docs/development/phase-e-deletion-plan.md` §4）。 |

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
