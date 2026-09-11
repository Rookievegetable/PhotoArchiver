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

**v2.4.0 已发布（Phase E 库管理收官，2026-09-08）**——tag `v2.4.0` → `93b7a15`，CI 三平台绿。**待 owner 收尾 v2.4.0**：核对 GitHub Release 资产 + 粘贴 `CHANGELOG.md` 第 9–54 行 `[2.4.0]` 段进 body 后签核。

**Phase F（数据正确性与长期运营收尾）三候选已实施完成（ADR-035 登记，2026-09-08）**，全量回归 **728 passed / 3 skipped / 0 failed**：

- **F-1 captured_at 回填 CLI**：Issue-019 后历史照片拍摄时刻一次性纠错——`PhotoRepository.update_capture_time`（只动快照列）+ `BackfillCaptureTimeService`（全量重读对齐，dry-run 默认、幂等、异常降级）+ `backfill-capture-time` 子命令。
- **F-2 默认路径锚定 P1**：数据库/日志默认值由 CWD 相对改为 platformdirs 用户数据目录锚定（显式 `.env`/env 完全优先、零破坏）；bootstrap 增旧 CWD 库首启迁移引导（不自动搬库）；N4b 进程级反向实证（陌生 CWD + 无显式配置 → 库落锚定目录）。
- **F-3 LIMIT-006 D-1**：CI macOS job 崩溃时自动收集 `.ips` crash report 为 artifact（追查从被动变主动）；D-2 复现与 D-3 修复待 macOS 调试手段立项。

以上变更（含依赖批准 platformdirs 与默认行为变化）未发版——是否 prepare v2.5.0 由 owner 决定。

### 历史发版锚点

| 版本 | tag → 提交 | 主题 |
|---|---|---|
| v2.3.0 | `e14409e` | 数据安全底线 + 运行时正确性（Phase A/B/C，D-B1~D-B8 裁决） |
| v2.3.1 | `90c46db` | 桌面 UI 中文化 + 工具栏纯化 + 人员筛选智能搜索（owner 裁决多轮折入单一发布；tag 二次重打至 CI 绿树） |
| v2.3.2 | `2aadcee` | 桌面复验修复：EXIF 拍摄时刻 + 照片墙 + 占位 |
| v2.4.0 | `93b7a15` | 库管理：删除登记 / 删除人员 / 重复处置 / 重扫对账 / prune-missing CLI（Phase E） |
| （未发版） | — | Phase F：captured_at 回填 CLI + 默认路径锚定 + CI macOS 崩溃诊断（是否 v2.5.0 待 owner） |

更早锚点：v1.0.0→`49b2ac6`、v2.0.0→`ba3ad02`、v2.1.0→`bd52fbb`、v2.2.0→`f9fb8c5`。

---

## 3. Project Status（项目当前状态）

| 范围 | 状态 | 当前事实 |
|---|---|---|
| 15 步产品路线图 | ✅ | Step 0.5–15 全部实现并验证。 |
| 版本链 | ✅ | v2.4.0 三处一致（pyproject / .env.example / CHANGELOG `[2.4.0] - 2026-09-08`）；历史锚点 v2.3.2 保留。 |
| CI | ✅ | 三平台绿（macOS LIMIT-006 darwin skip 4 个真实执行器压力用例生效后通过——skip 为测试面处置，非产品缺陷）；Windows/Linux 全量 728/3/0 本地实证；Phase F 增 CI macOS 崩溃诊断收集（LIMIT-006 D-1）。 |
| 桌面复验 | ✅ | 机制项（N1–N4 自动化：1200 行导入闭环/取消一致性/备份恢复演练/换目录子进程）+ 感知项（J1–J7 owner 逐项判定）全部通过。 |
| 未决问题 | ✅ 清零 | ISSUE-019 已修复并经真机终验关闭（条目同提交删除）。 |
| Limit 登记 | 4 项 | LIMIT-001（真实缺模型 E2E 未入 CI）/ LIMIT-002（取消为任务边界粒度，设计特征）/ LIMIT-004（Windows 本地子集顺序原生崩溃）/ LIMIT-006（macOS CI runner 压力扫描段错误，darwin skip），均 Low、不阻塞。 |
| Release body | ⏳ 待 owner | GitHub Release 已由 tag `v2.4.0` 触发生成（`generate_release_notes` 自动摘要 + `dist-*` 资产）；`CHANGELOG.md` 第 9–54 行 `[2.4.0]` 段需 owner 粘贴进 body 后签核（v2.3.2 同流程）。 |

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
| 会话范围 | 交接恢复 → **E-2 收尾** → **E-3 实施** → **E-4 实施** → **E-5 实施** → **E-6 收尾发版** → **v2.4.0 发布收官**（macOS CI 段错误处置）→ **Phase F 三候选实施**（captured_at 回填 + 路径锚定 + CI 崩溃诊断）。 |
| 关键产出 | ① E-2~E-6：Phase E 全部完成（追加 38 测试）；② v2.4.0 发布 + macOS CI 段错误 darwin skip 扩展（LIMIT-006 第三形态，产品代码无因果）；③ **Phase F-1**：`update_capture_time` 协议/双实现 + `BackfillCaptureTimeService`（dry-run 默认）+ `backfill-capture-time` CLI + 11 测试；④ **Phase F-2**：默认路径锚定用户数据目录（platformdirs，显式配置优先）+ 旧 CWD 库首启引导 + N4b 反向实证 + 7 测试；⑤ **Phase F-3**：CI macOS 崩溃报告收集（D-1）；⑥ ADR-035 登记（回填通道 + 锚定 + platformdirs 批准）+ dependency-rules §13 + base.txt；⑦ 质量门全绿：ruff 0 / mypy 191 files 0 / pytest **728 passed / 3 skipped / 0 failed**。 |
| 当前质量门 | `ruff check .` 通过；`mypy src` 191 个源文件无问题；pytest 全量 **728 passed / 3 skipped / 0 failed**（本地实测）。 |
| 工作区 | Phase F 三 commit 本地完成（`7707bc1` 为最新），待 owner push；此前提交已同步 origin；tag `v2.4.0` = `93b7a15`。 |
| Remaining | v2.4.0 签核（owner：Release 资产核对 + body 粘贴）· Phase F 是否发版 v2.5.0（owner 决定）· LIMIT-006 D-2/D-3（需 macOS 调试手段立项）。 |

---

## 6. Next Step（下一步开发计划）

v2.4.0 已发布待签核；Phase F（captured_at 回填 + 路径锚定 + CI 崩溃诊断）三候选已实施完成。可选后续（均需 owner 另行立项）：

| Next Step | **owner 汇总决策**：① v2.4.0 签核（Release 资产核对 + body 粘贴）；② Phase F 是否合入发版 prepare **v2.5.0**（新增能力 minor + 默认路径行为变化——需 CHANGELOG `[2.5.0]` 段 + 指南已补章）；③ **LIMIT-006 D-2/D-3**（macOS 追查：需 macOS 调试手段；plant 候选 `os.scandir` 重写 scanner——既收窄竞态窗口又省 N 次 stat）；④ 下一候选立项（如：旧 CWD 库自动迁移 `migrate` 子命令、CURRENT_BATCH 导出 P2-4）。 |

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
