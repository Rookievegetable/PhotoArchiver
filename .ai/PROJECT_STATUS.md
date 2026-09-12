# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**"项目现在开发到哪里了？"**
>
> 每次开发结束后刷新；不保留历史状态。
>
> Version: 1.16.0 · Last Updated: 2026-09-12 · Status: Live

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

**v2.7.0 已发布（Phase G 运营轮，2026-09-12）**——recognize CLI（FEAT-15 全闭环）、归档根目录设置（FEAT-14 闭环）、照片墙状态角标；LIMIT-006 判据 6/5 达成后 skip 解除即复现段错误（run #80）→ 判据重置、skip 恢复；崩溃边界确认为全量套件上下文；公开取证通道（崩溃栈→注解）已建成；owner 供日志后 faulthandler 栈定位 scandir C 层为崩溃点 → 实验三阴性（listdir 变体仍崩）→ 结论：与枚举 API 无关，疑似 PySide6 上游缺陷（worker 枚举 + 主线程事件循环并发）；darwin skip 恢复；D-3 排查结论（实验五回滚后修正）：**不可仓内修复**——64MB 大栈实验（run #97）证伪栈假设，崩溃点第 4 次漂移（PIL Image.open）；确证崩溃 = macOS arm64 后台线程任意原生调用 + 主线程事件循环并发的概率性 SIGSEGV，与枚举 API/PySide6 版本/线程类型/栈大小全部无关。darwin skip 恢复为长期项，上游 issue 草稿备提交；ADR-041 的枚举前置保留（架构上仍正确：主线程枚举 0.14s/2000 文件可接受，且消除了已知的枚举面并发）；实验四阴性结论（与 PySide6 版本无关）在案；上游 issue 草稿备提交。待 owner 签核。

**v2.6.0（审计清零后的首个发版，2026-09-12）**——收录 v2.5.0 后全部变更：插件目录生产接线（ADR-038）、并行匹配分片 flush（ADR-037）、cleanup-thumbnails、antelopev2 摘要钉定、'未匹配' UI 筛选、migrate CLI（ADR-039）、分层 AST 断言（T-1）。待 owner 签核。

**v2.5.0（Phase F 正确性收口，2026-09-12）**——Phase F 全部六期完成：前三候选（captured_at 回填 CLI + 路径锚定 + CI macOS 崩溃诊断，ADR-035）与正确性收口五项（Windows 文件名净化 + 扫描环防护 / 查询去重 + 未匹配哨兵 / 取消接线与 UX / 质量基建 / CLI 对等，ADR-036，owner 2026-09-12 按建议批准 D4–D9）。待 owner 收尾 v2.5.0：核对 GitHub Release 资产 + 粘贴 `CHANGELOG.md` 第 9–44 行 `[2.5.0]` 段进 body 后签核。

全量回归 **783 passed / 4 skipped / 0 failed**；覆盖率基线 **92%**（pytest-cov 首次引入，dev-only，不设门槛）。

### 历史发版锚点
### 历史发版锚点

| 版本 | tag → 提交 | 主题 |
|---|---|---|
| v2.3.0 | `e14409e` | 数据安全底线 + 运行时正确性（Phase A/B/C，D-B1~D-B8 裁决） |
| v2.3.1 | `90c46db` | 桌面 UI 中文化 + 工具栏纯化 + 人员筛选智能搜索（owner 裁决多轮折入单一发布；tag 二次重打至 CI 绿树） |
| v2.3.2 | `2aadcee` | 桌面复验修复：EXIF 拍摄时刻 + 照片墙 + 占位 |
| v2.4.0 | `93b7a15` | 库管理：删除登记 / 删除人员 / 重复处置 / 重扫对账 / prune-missing CLI（Phase E） |
| v2.7.0 | 2026-09-12 | Phase G 运营轮：recognize CLI + 归档根设置 + 状态角标 + LIMIT-006 计数器 + 覆盖率门槛 |
| v2.6.0 | 2026-09-12 | 审计清零轮：插件目录接线 + 并行匹配分片 flush + cleanup-thumbnails + migrate + 未匹配筛选 + antelopev2 钉定（ADR-037/038/039） |
| v2.5.0 | 2026-09-12 | Phase F：captured_at 回填 + 路径锚定 + CI 崩溃诊断 + Windows 保留名净化/扫描环防护 + 查询去重/未匹配哨兵 + 取消接线/UX + 覆盖率基线 + CLI 对等（ADR-035/036） |

更早锚点：v1.0.0→`49b2ac6`、v2.0.0→`ba3ad02`、v2.1.0→`bd52fbb`、v2.2.0→`f9fb8c5`。

---

## 3. Project Status（项目当前状态）

| 范围 | 状态 | 当前事实 |
|---|---|---|
| 15 步产品路线图 | ✅ | Step 0.5–15 全部实现并验证。 |
| 版本链 | ✅ | v2.4.0 三处一致（pyproject / .env.example / CHANGELOG `[2.4.0] - 2026-09-08`）；历史锚点 v2.3.2 保留。 |
| CI | ✅ | 三平台绿；本地全量 783/4/0 实证；CI no-skip 守卫改为运行期统计（F-5/体检 T-5）；macOS 崩溃报告收集在位（LIMIT-006 D-1）。 |
| 桌面复验 | ✅ | 机制项（N1–N4 自动化：1200 行导入闭环/取消一致性/备份恢复演练/换目录子进程）+ 感知项（J1–J7 owner 逐项判定）全部通过。 |
| 未决问题 | ✅ 清零 | 体检 N-1~N-9 全部处置：N-1 插件接线（ADR-038）、N-3/N-2/F-10/F-11/F-13 随 Phase F 修复、N-5 实证不复现（测试锁定）、N-7/N-8 技术债修复（摘要补钉 + cleanup-thumbnails CLI）。仅余 LIMIT-* 设计/环境限制。 |
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
| UI / Settings / Export | ✅ | 主窗口、设置闭环（含归档根目录，G-2）、Excel/CSV/HTML 导出、照片墙网格布局 |
| 人员筛选 | ✅ | 三轴组合筛选 + 人员轴键入即时搜索（`presentation/person_matcher.py` 四级智能排名） |
| Plugins | ✅ | 发现/加载/生命周期 + PluginContext 读方法 + import_people 写方法；`PLUGINS_DIRECTORY` 配置后启动自动加载并挂载工具栏动作（ADR-038）；示例插件仍不自动加载 |

---

## 5. Last Session（最近一次开发记录）

| 项目 | 值 |
|---|---|
| 时间 | 2026-09-12（本地） |
| 会话范围 | 交接恢复 → 体检报告核验 → Phase F 正确性收口实施（F-2/F-5/F-1/F-3/F-6/F-7，ADR-036）→ v2.5.0 发版 + 签核 → CI 双修复（stat 常量平台性 + LIMIT-006 守卫白名单）→ **ISSUE-021 分片 flush（ADR-037）** → **LIMIT-006 D-2 解除实验**（os.scandir 下段错误仍复现，已回退并登记证据）。 |
| 关键产出 | **v2.5.0 后续轮（ADR-037/038 + 技术债清零）**：⑦ **ISSUE-021**：并行匹配持久化分片 flush（每 50 条 add_many，崩溃丢失窗口 ≤49 条，ADR-037）；⑧ **ISSUE-020**：`PLUGINS_DIRECTORY` 生产接线（ADR-038，opt-in 加载 + 工具栏挂载 + 错误隔离）；⑨ **LIMIT-006 D-2**：darwin skip 解除实验——os.scandir 下段错误仍复现（CI exit 139），崩溃面非 pathlib glob，已回退留证；⑩ **ISSUE-022**：N-5 证伪（elif 分支误读，测试锁定）；⑪ **ISSUE-023**：`cleanup-thumbnails` CLI（端口扩 compute_key/cleanup，dry-run 默认）；⑫ **ISSUE-024**：antelopev2 摘要补钉（真实包校验后钉定）。原 v2.5.0 轮产出：① **F-2**：识别轴 JOIN DISTINCT 去重 + `UNMATCHED` 哨兵（LEFT JOIN IS NULL，Domain 导出）；② **F-5**：`tests/conftest.py` 共享 SQLite 工厂 fixture（3 模块重构采用）+ pytest-cov 7.1.0（覆盖率基线 92%）+ CI no-skip 守卫运行期化；③ **F-1**：`sanitize_windows_filename` Domain 净化（保留设备名矩阵/非法字符/尾点尾空格）+ builder 审计日志 + 扫描器迭代式 os.scandir 重写（realpath 环检测 + 深度上限 + junction reparse-tag 识别，2000 文件 0.037s vs glob 0.218s）；④ **F-3**：import cancelled 接线 + 导出取消通道 + 照片墙空态占位 + 审核行姓名化 + 语言占位标注 + .xlsm 过滤器 + `_active_runnable` 终态清零；⑤ **F-6**：CLI `import-people`/`export` 子命令 + CLI 启动备份对齐（D8）；⑥ **F-7**：README 矛盾段删除 + user-guide 新命令表 + 配置默认路径文档修正 + v2.5.0 发版。 |
| 当前质量门 | ruff 0 / mypy 191 files 0 / pytest **783 passed / 4 skipped / 0 failed** / pip check 通过（本地实测）。 |
| 工作区 | Phase F 正确性收口 + v2.5.0 发版提交完成并 push。 |
| Remaining | G-1 CLI recognize + G-2 归档根目录设置已落地（未发版，CHANGELOG Unreleased）· CURRENT_BATCH 导出（roadmap §13.12 owner 门控；owner 2026-09-12 再次确认挂起）· 分层边界 AST 断言已常驻（体检 T-1 关闭）· 覆盖率门槛 90% 已入 CI（Linux job 采集）· G-3 实验二（豁免直跑崩溃用例）进行中· G-3 实验一完成（stress-macos 非 qtbot 形态通过 → 嫌疑收敛 qtbot 交互，LIMIT-006 已更新）· G-4 状态角标已落地· LIMIT-006 D-3（macOS 调试手段立项；D-2 已实证非 pathlib glob）· CI 偶发 flake 观察：Linux SIGSEGV（run #65）、macOS pytest exit 1（#71/#75/#76，非确定、与提交无关，重跑绿）——已加 -rf + ::error:: 注解机制，复现时自动报出失败用例名（#77 修复了注解被 -e/pipefail 吞掉的取证盲区）。`migrate` 子命令与"未匹配"UI 筛选已落地（ADR-039 / ADR-036 D6 闭环），未发版（CHANGELOG Unreleased）。 |

---

## 6. Next Step（下一步开发计划）

v2.5.0 已发布待签核。可选后续（均需 owner 另行立项）：

| Next Step | **owner 汇总决策**：① v2.5.0 签核；② ISSUE-020 插件可见性二选一（接入可配置插件目录 vs 收回 README/FAQ 宣传）；③ ISSUE-021 并行匹配分片 flush（F-8）；④ 下一候选立项（如旧 CWD 库自动迁移 `migrate` 子命令、CURRENT_BATCH 导出 P2-4、"未匹配"筛选的 UI 暴露）。

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
