# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**"项目现在开发到哪里了？"**
>
> 每次开发结束后刷新；不保留历史状态。
>
> Version: 1.17.0 · Last Updated: 2026-09-13 · Status: Live

---

## 1. Roadmap（开发路线图概览）

权威 15 步路线图：`.ai/business/roadmap.md`。

| Step | 名称 | 状态 |
|---|---|---|
| 0.5–11 | Walking Skeleton、基础设施、Domain、导入、扫描、缩略图、人脸识别、归档 | ✅ Completed |
| 12–14 | Main UI、Settings、Export | ✅ Completed |
| 15 | Plugin System | ✅ Completed |

M1–M7 及 Step 0.5–15 全部完成；阶段 B 业务增强 B1–B5 与收官加固阶段 0–3 均已落地。此后进入发布工程与桌面验收驱动的迭代修复（已发布至 v2.8.0）。

---

## 2. Current Step（当前开发阶段）

**v2.8.0 已发布并产出安装包（Windows 桌面交付轮，2026-09-13）**——ADR-031 方案B 落地：release.yml build-windows job 自动构建 **PhotoArchiver-v2.8.0-setup.exe（152MB 在线，windowed 无控制台）+ PhotoArchiver-v2.8.0-offline-setup.exe（439MB 含模型）** 双产物（run #31 三 job 全绿）；`PhotoArchiver-cli.exe` 独立命令行入口；`download-models` 内置命令（sha256 fail-closed）；frozen 适配（alembic 随 bundle / 模型目录锚定 / windowed 流 shim）；macOS 扫描稳定性重构（ADR-041 枚举前置，实验性支持披露）+ **离线模型路径缺陷修复（insightface root 语义，真机验收发现）**；CI 自愈（139 重试）。已真机验收两轮：第一轮暴露离线模型路径缺陷 + 控制台窗口问题（均已修复）；第二轮待 owner 用 **14:20Z 之后构建的新安装包**重验（关键区别：启动日志首行应显示 `Starting PhotoArchiver v2.8.0` 构建版本戳 + 识别不再报错不再下载）。**Release 资产已随重打更新（14:20Z）**。

**v2.7.0（Phase G 运营轮，2026-09-12）**——recognize CLI（FEAT-15 全闭环）、归档根目录设置（FEAT-14 闭环）、照片墙状态角标；LIMIT-006 判据 6/5 达成后 skip 解除即复现段错误（run #80）→ 判据重置、skip 恢复；崩溃边界确认为全量套件上下文；公开取证通道（崩溃栈→注解）已建成；owner 供日志后 faulthandler 栈定位 scandir C 层为崩溃点 → 实验三阴性（listdir 变体仍崩）→ 结论：与枚举 API 无关，疑似 PySide6 上游缺陷（worker 枚举 + 主线程事件循环并发）；darwin skip 恢复；D-3 排查结论（实验五回滚后修正）：**不可仓内修复**——64MB 大栈实验（run #97）证伪栈假设，崩溃点第 4 次漂移（PIL Image.open）；确证崩溃 = macOS arm64 后台线程任意原生调用 + 主线程事件循环并发的概率性 SIGSEGV，与枚举 API/PySide6 版本/线程类型/栈大小全部无关。CI 自愈（run #99 最终定性后）：macOS/Linux runner 环境漂移致 pytest 概率性 SIGSEGV（139）与代码无关——pytest 步骤对 139 自动重试 ≤3 次（真实失败不重试）。darwin skip 恢复为长期项——**owner 处置（2026-09-13）：方案 3 维持现状**，macOS 定性实验性支持并已在 user-guide/FAQ 披露；上游 issue 草稿备提交；ADR-041 的枚举前置保留（架构上仍正确：主线程枚举 0.14s/2000 文件可接受，且消除了已知的枚举面并发）；实验四阴性结论（与 PySide6 版本无关）在案；上游 issue 草稿备提交。待 owner 签核。

**v2.6.0（审计清零后的首个发版，2026-09-12）**——收录 v2.5.0 后全部变更：插件目录生产接线（ADR-038）、并行匹配分片 flush（ADR-037）、cleanup-thumbnails、antelopev2 摘要钉定、'未匹配' UI 筛选、migrate CLI（ADR-039）、分层 AST 断言（T-1）。待 owner 签核。

**v2.5.0（Phase F 正确性收口，2026-09-12）**——Phase F 全部六期完成：前三候选（captured_at 回填 CLI + 路径锚定 + CI macOS 崩溃诊断，ADR-035）与正确性收口五项（Windows 文件名净化 + 扫描环防护 / 查询去重 + 未匹配哨兵 / 取消接线与 UX / 质量基建 / CLI 对等，ADR-036，owner 2026-09-12 按建议批准 D4–D9）。待 owner 收尾 v2.5.0：核对 GitHub Release 资产 + 粘贴 `CHANGELOG.md` 第 9–44 行 `[2.5.0]` 段进 body 后签核。

全量回归 **783 passed / 4 skipped / 0 failed**；覆盖率基线 **92%**（pytest-cov 首次引入，dev-only，不设门槛）。

### 历史发版锚点

| 版本 | tag → 提交 | 主题 |
|---|---|---|
| v2.3.0 | `e14409e` | 数据安全底线 + 运行时正确性（Phase A/B/C，D-B1~D-B8 裁决） |
| v2.3.1 | `90c46db` | 桌面 UI 中文化 + 工具栏纯化 + 人员筛选智能搜索（owner 裁决多轮折入单一发布；tag 二次重打至 CI 绿树） |
| v2.3.2 | `2aadcee` | 桌面复验修复：EXIF 拍摄时刻 + 照片墙 + 占位 |
| v2.4.0 | `93b7a15` | 库管理：删除登记 / 删除人员 / 重复处置 / 重扫对账 / prune-missing CLI（Phase E） |
| v2.5.0 | 2026-09-12 | Phase F：captured_at 回填 + 路径锚定 + CI 崩溃诊断 + Windows 保留名净化/扫描环防护 + 查询去重/未匹配哨兵 + 取消接线/UX + 覆盖率基线 + CLI 对等（ADR-035/036） |
| v2.6.0 | 2026-09-12 | 审计清零轮：插件目录接线 + 并行匹配分片 flush + cleanup-thumbnails + migrate + 未匹配筛选 + antelopev2 钉定（ADR-037/038/039） |
| v2.7.0 | 2026-09-12 | Phase G 运营轮：recognize CLI + 归档根设置 + 状态角标 + LIMIT-006 计数器 + 覆盖率门槛 |
| v2.8.0 | `fe7f46f` | Windows 桌面交付：安装包（在线/离线）+ download-models + frozen 适配 + 离线模型路径修复（ADR-031 方案B / ADR-041） |

更早锚点：v1.0.0→`49b2ac6`、v2.0.0→`ba3ad02`、v2.1.0→`bd52fbb`、v2.2.0→`f9fb8c5`。

---

## 3. Project Status（项目当前状态）

| 范围 | 状态 | 当前事实 |
|---|---|---|
| 15 步产品路线图 | ✅ | Step 0.5–15 全部实现并验证。 |
| 版本链 | ✅ | v2.8.0 三处一致（pyproject / .env.example / CHANGELOG `[2.8.0] - 2026-09-13`）。 |
| CI | ✅ | 三平台绿（run #124 @ main `92bb1e9`）；runner 环境漂移 exit 139 自动重试 ≤3 次自愈常驻；no-skip 守卫运行期统计（F-5/体检 T-5）；覆盖率门槛 90%（Linux job 强制）；macOS 崩溃报告收集在位（LIMIT-006 D-1）。 |
| 桌面复验 | ✅ | 机制项（N1–N4 自动化：1200 行导入闭环/取消一致性/备份恢复演练/换目录子进程）+ 感知项（J1–J7 owner 逐项判定）全部通过。 |
| 未决问题 | ✅ 清零 | 体检 N-1~N-9 全部处置；离线模型路径缺陷（v2.8.0 真机验收发现）已修复并有守卫测试。仅余 LIMIT-* 设计/环境限制。 |
| Limit 登记 | 4 项 | LIMIT-001（真实缺模型 E2E 未入 CI）/ LIMIT-002（取消为任务边界粒度，设计特征）/ LIMIT-004（Windows 本地子集顺序原生崩溃）/ LIMIT-006（macOS/Linux runner 环境漂移 SIGSEGV，CI 自愈 + darwin skip 维持），均 Low、不阻塞。 |
| Release body | ⏳ 待 owner | GitHub Release v2.8.0 已发布（资产：在线 145MB + 离线 419MB 安装包 + wheel/sdist，随 tag 重打更新）；当前 body 为 `generate_release_notes` 自动生成的比较链接（且重复多条），需 owner 粘贴 `CHANGELOG.md` `[2.8.0]` 段进 body 后签核（v2.5.0/v2.7.0 同流程）。 |

### 数据库 Schema

Alembic 管理（`001_initial_v4` + `002_split_create_ddl`，ADR-027）；`PRAGMA user_version = 4`。本版未改 Schema。

---

## 4. Current Modules（当前模块状态）

| 模块 | 状态 | 关键位置 |
|---|---|---|
| Logging / Configuration | ✅ | `infrastructure/logging/`、`infrastructure/config/` |
| Database | ✅ | Alembic 管理（ADR-027） |
| Domain / Import / Scan / Thumbnail | ✅ | `domain/`、`application/services/`、`infrastructure/`；`PillowPhotoMetadataReader` 支持 Exif 子 IFD 拍摄时刻（ISSUE-019 修复）；扫描枚举前置主线程（ADR-041 预枚举模式） |
| 模型部署（下载/解包/校验/frozen） | ✅ | `infrastructure/ai/model_deployment.py`（SSOT，zip 顶层拍平 + onnx 存在性校验）+ `insightface_loader.py`（root 语义：传 `model_root.parent`）+ `download-models` CLI（sha256 fail-closed） |
| Recognition / Review | ✅ | InsightFace detect/recognize/match 与审核闭环 |
| Archive | ✅ | Planner → Plan → Executor，captured_at 现对真实相机照片正确分桶 |
| UI / Settings / Export | ✅ | 主窗口、设置闭环（含归档根目录，G-2）、Excel/CSV/HTML 导出、照片墙网格布局 |
| 人员筛选 | ✅ | 三轴组合筛选 + 人员轴键入即时搜索（`presentation/person_matcher.py` 四级智能排名） |
| Plugins | ✅ | 发现/加载/生命周期 + PluginContext 读方法 + import_people 写方法；`PLUGINS_DIRECTORY` 配置后启动自动加载并挂载工具栏动作（ADR-038）；示例插件仍不自动加载 |

---

## 5. Last Session（最近一次开发记录）

| 项目 | 值 |
|---|---|
| 时间 | 2026-09-13（本地） |
| 会话范围 | 交接恢复（git 基线 / 状态文档 / 四门实测 / CI 核查）→ **文档卫生轮**：CHANGELOG [2.8.0]/[2.7.0] 重复陈旧段去重（旧版含被 run #99 证伪的"skip 已移除/segfault 已消除"表述）→ KNOWN_ISSUES 清理（已修复的离线模型缺陷段删除；LIMIT-006 从未决问题段转为"平台与第三方限制"表行，保留 darwin skip reason 的文档锚点）→ PROJECT_STATUS 刷新至 v2.8.0 后状态。 |
| 关键产出 | **文档卫生轮（本会话）**：① CHANGELOG 去重——[2.8.0] 与 [2.7.0] 各删除一整套重复的 Added/Fixed/Internal 旧稿，每版本仅保留与最终事实一致的一套；② KNOWN_ISSUES v1.15.0——未决问题清零，LIMIT-006 转平台限制表行（Mitigated：CI 自愈 + darwin skip 维持）；③ PROJECT_STATUS v1.17.0——Release body 行更新为 v2.8.0 真实状态（body 为自动生成重复比较链接，待 owner 粘贴 `[2.8.0]` 段）、CI/版本链/Limit 登记行刷新、锚点表补 v2.8.0→`fe7f46f` 并按时间排序、§5/§6/§7 重写。**上一会话（v2.8.0 桌面交付轮）**：ADR-031 方案B 落地——PyInstaller onedir + Inno Setup per-user 双安装包（在线 152MB windowed + 离线 439MB 含 buffalo_l，构建期 sha256 校验）+ `PhotoArchiver-cli.exe` 独立 CLI；`download-models` 命令（sha256 fail-closed）；frozen 适配（alembic 随 bundle / 模型目录锚定 / windowed 流 shim / 构建版本戳）；离线模型路径缺陷修复（zip 顶层拍平 + insightface root 语义 + onnx 存在性校验，真机验收第一轮发现）；ADR-041 扫描枚举前置主线程（ADR-040 规避证伪后 Rejected）；CI 自愈（exit 139 重试 ≤3 次 + 崩溃栈公开注解）；`docs/user-guide/manual.md` 安装版端到端手册。 |
| 当前质量门 | ruff 0 / mypy 193 files 0 / pytest **841 passed / 6 skipped / 0 failed** / pip check 通过（2026-09-13 本地实测）。 |
| 工作区 | 干净；main 与 origin/main 同步（`92bb1e9`，v2.8.0 tag `fe7f46f` 之上 2 个 docs 提交）。 |
| Remaining | **owner 二轮真机验收**（新离线安装包；启动日志首行应显示 `Starting PhotoArchiver v2.8.0` 构建版本戳 + 识别不再报错不再下载）· GitHub Release v2.8.0 body 待 owner 粘贴 CHANGELOG `[2.8.0]` 段 · A-1 CURRENT_BATCH 导出挂起（解除则先出批次持久化设计文档）· A-3 代码签名证书采购决策 · 上游 PySide6 issue 是否提交（草稿就绪：`docs/development/limit006-upstream-issue-draft.md`）· A-2 大库分块枚举——硬前置：上游并发缺陷需先有结论，勿盲目开工 · B 类触发式（模型镜像/导出流式化/检查更新）信号到达才动 · 第 4 轮全面体检候审（建议 v2.8.x 稳定后，覆盖 ADR-037~041 + 桌面交付全变更）。 |

---

## 6. Next Step（下一步开发计划）

v2.8.0 已发布（安装包资产齐备），等待 owner 二轮验收与决策；当前无进行中开发任务。后续均需 owner 立项：

| Next Step | **待 owner**：① 新离线安装包二轮真机验收 + Release body 粘贴 `[2.8.0]` 段后签核；② A-1 CURRENT_BATCH 导出是否解除挂起（解除则先出批次持久化设计文档）；③ A-3 代码签名证书采购决策；④ 是否提交上游 PySide6 issue（草稿就绪）。**可立项**：A-2 大库分块枚举——硬前置：上游并发缺陷需先有结论（枚举回后台线程 = 回到崩溃形态）。**明确不做**：i18n 实装、自动更新、macOS 安装包、批次撤销。 |

---

## 7. Key Files（关键文件索引）

| 职责 | 文件 |
|---|---|
| 运行状态唯一快照 | `.ai/PROJECT_STATUS.md` |
| 架构决策（ADR-031~041，040 Rejected） | `.ai/ARCHITECTURE_DECISIONS.md` |
| 用户使用手册（安装版端到端） | `docs/user-guide/manual.md` |
| 打包定义（PyInstaller + Inno Setup） | `packaging/windows/photo_archiver.spec`、`installer.iss`、`ChineseSimplified.isl`（vendored） |
| 模型部署 SSOT（下载/解包/校验） | `src/photo_archiver/infrastructure/ai/model_deployment.py`（脚本为薄壳） |
| insightface 装载（root 语义） | `src/photo_archiver/infrastructure/ai/insightface_loader.py` |
| 扫描预枚举（ADR-041） | `src/photo_archiver/presentation/controllers/scan_controller.py`（主线程枚举）+ `src/photo_archiver/application/services/scan_and_register_photos_service.py`（`enumerate_files`/`pre_enumerated_items`） |
| 分层边界守卫 | `tests/unit/architecture/test_layer_boundaries.py` |
| LIMIT-006 压力实验 | `tests/integration/test_scan_stress_no_qtbot.py`（PA_STRESS 门控） |
| 上游 issue 草稿 | `docs/development/limit006-upstream-issue-draft.md` |
| UI 文案表（中文化单一置换点） | `src/photo_archiver/presentation/ui_text.py` |
| 数据库初始化/迁移 | `src/photo_archiver/infrastructure/database/sqlite_connection.py`、`alembic_runner.py` |
| 质量验证 / 发布工作流 | `tests/`、`.github/workflows/ci.yml` / `.github/workflows/release.yml` |

---

> 本文件只描述当前状态；历史决策见 `.ai/ARCHITECTURE_DECISIONS.md`，当前问题见 `.ai/KNOWN_ISSUES.md`，路线图见 `.ai/business/roadmap.md`。
