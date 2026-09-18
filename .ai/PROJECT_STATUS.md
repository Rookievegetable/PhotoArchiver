# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**"项目现在开发到哪里了？"**
>
> 每次开发结束后刷新；不保留历史状态。
>
> Version: 1.21.0 · Last Updated: 2026-09-18 · Status: Live

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

**UI/UX Batch 3：主窗口信息架构与首次引导（2026-09-18 实施，待 owner 验收）**——MainWindow 重构为流程驱动工作台壳：左侧 QListWidget 导航（概览 / 照片库 / 审核中心 / 数据工具 / 设置）+ QStackedWidget 三页；窗口级 Main 工具栏精简为五个频繁主操作（流程序：导入 / 扫描 / 识别 / 审核 / 归档，插件动作 ADR-038 挂载契约不变）；维护操作（导出数据 / 检测重复 / 删除人员）移入数据工具页（Owner 决策 4 的信息架构落地），删除登记留在照片库页（选区态，Batch 2 语义不变）；设置改为触发式导航项（Ctrl+, 快捷键经 window.addAction 保留）；取消动作移入状态栏常驻 QToolButton（objectName="CancelTask"，QAction 契约不变）。新增概览页：`controllers/overview_presenter.py`（纯逻辑）+ `views/overview_page.py`——五步检查清单（导入人员 → 扫描照片 → 运行人脸识别 → 人工审核 → 安全归档）逐步由 Batch 2 WorkspaceController 快照驱动（Widget 零仓储访问），唯一主 CTA 指向最合理的下一步（优先级 match → model → import/scan → review → archive → settings，全部完成时引导继续扫描；允许先扫描再导入，识别需人员与照片双齐由 CTA 归位表达），底部本地处理隐私说明。审核中心/设置导航行为触发式（打开模态不切页，高亮自动回贴）。文案全入 ui_text.py；未改审核业务规则、归档默认值、CURRENT_BATCH 展示、controller API、Schema/CLI/CI/扫描线程模型。

**UI/UX Batch 2：工作区就绪状态与防呆动作可用性（2026-09-17 实施；2026-09-18 owner 验收通过并随 Batch 1 一并提交入库，未发布）**。Application 层新增只读工作区查询：`WorkspaceStatus` DTO（`application/dtos/workspace.py`，七字段：人员存在/照片存在/待识别数/待审核数/可归档数/归档根可用/模型 available·missing·unknown）+ `WorkspaceReadinessService`（`application/services/workspace_readiness.py`）；计数由 `RecognitionRepository.read_workspace_counts()` 单条 SQL 聚合（不物化实体、不重复扫描大库、无新 Schema），可归档数与 ArchivePlanner 语义对齐（绝对路径 + 存在人员 + APPROVED + 排除成功归档历史），归档根探测只查最近存在祖先目录可写性（不创建、不用异常判断），模型状态装配时一次性判定（真实 MatchPersonsService→AVAILABLE，`_UnavailableMatchService`→MISSING，UNKNOWN 可注入测试）。Presentation 侧 `WorkspaceController` 将缓存快照翻译为各动作的 enabled/tooltip/next_action：识别缺人员/缺照片/全部已识别/模型缺失时置灰并给出可直达的下一步按钮（导入/扫描/审核/设置/模型说明）；审核 0 条时对话框保持打开显示空态（不再"一闪而过"），通过/拒绝按钮按队列+选区启用；归档无根/无可归档时置灰并直达设置/审核；删除登记仅在照片墙有选区时可用；取消动作维持 Batch 1 语义。刷新时机：启动、任务终态、审核/设置对话框返回；任务进行中保存原状态、终态后恢复为最新快照（一次查询）。服务层原有校验保留为第二道防线（TOCTOU）。文案全部入 `ui_text.py`。Batch 1 全局任务协调与取消语义同批在案（`TaskCoordinator`、五任务互斥、LIMIT-002 取消、终态恢复、异常路径修复）。本轮质量门见 §5；均未发布安装包。

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
| 时间 | 2026-09-18（本地 Windows / Python 3.11.9 / PySide6 6.11.1）；Batch 3 实施于 Batch 0–2 提交（`378e26b` / `6649a96`）之后 |
| 会话范围 | UI/UX Batch 3（主窗口信息架构与首次引导）。不改变审核业务规则、归档默认值、CURRENT_BATCH 展示、既有 controller API 或扫描线程模型。 |
| 关键产出 | ① 新增 `presentation/controllers/overview_presenter.py`（五步清单 + 主 CTA 推导，纯逻辑消费 WorkspaceController 缓存快照，零仓储）与 `presentation/views/overview_page.py`（渲染视图 + `primary_clicked` 信号 + `render_model`/`set_busy`）。② `main_window.py`：`_build_actions()` 集中创建 11 个 QAction（实例属性契约保留）→ `_build_toolbar()` 精简 Main 工具栏（五主操作流程序 + 插件挂载）→ `_build_central()` 改为导航 + 三页（照片库页 = 原 FilterBar/引导行/照片墙/空态 + 页内删除登记工具栏；数据工具页收纳导出/查重/删除人员）→ `_build_status()` 状态栏常驻取消 QToolButton → 触发式导航行（审核中心/设置，`_snap_nav_to_page` 高亮回贴）→ 概览渲染接 `_refresh_workspace_state`、busy 接 `_on_task_state_changed`。③ `ui_text.py` 新增导航/概览文案区段 24 项。④ 用户手册 §4 重写（导航结构 + 概览页）、§3.1/④/⑥/§5 入口更新。⑤ 测试：新增 `test_overview_presenter.py`（12 项五态矩阵）+ `test_main_window_navigation.py`（14 项：工具栏契约/数据工具分置/五态 CTA/真实 picker 路由/页面切换/触发式导航回贴/任务面板常驻/busy 置灰恢复/导航标签）；适配 `test_main_window_workspace_state.py`（3 处切照片库页后断言 isVisible）与 `test_photo_thumbnail_rendering.py`（grab 前切照片库页）。 |
| 当前质量门 | 提交前实测（本轮）：Ruff 全库通过；MyPy `mypy src`（CI 同款）**199 source files** 无问题；完整 pytest **988 passed / 6 skipped / 0 failed，181.45s，104 warnings**（首轮 1 failed 为缩略图 grab 在非当前页白屏，修复后第二轮全量全绿）；presentation 定向 **163 passed**（66.17s）+ 导入闭环集成 2 passed + 缩略图渲染 3 passed。未运行 pip check 或覆盖率测量。 |
| 工作区 | main；本轮 Batch 3 改动以单提交入库：`<commit>`（feat(ui)）；工作树干净、**未推送**（push 属 owner，GIT-020）。本轮不构建安装包、不更新 CI 或 Release。 |
| Remaining | **owner Batch 3 验收** · **Batch 4 实施**（照片库：筛选、空态、选择态与详情——蓝图 §Batch 4，需 owner 明确命令）· v2.8.0 二轮真机验收 · GitHub Release v2.8.0 body 待 owner 粘贴 CHANGELOG `[2.8.0]` 段 · A-1 CURRENT_BATCH 导出挂起（Batch 6 落地）· A-3 代码签名证书采购决策 · 上游 PySide6 issue 是否提交（草稿就绪）· A-2 大库分块枚举——硬前置：上游并发缺陷需先有结论 · B 类触发式（模型镜像/导出流式化/检查更新）信号到达才动 · 第 4 轮全面体检候审。 |

---

### Batch 1 验收证据与边界

- 准入/取消/早到终态：`tests/unit/presentation/test_task_coordinator.py`（9 项）与 `test_main_window_task_coordination.py`（36 项）。覆盖模态重入、五任务互斥、取消对象、三类 early replay、旧任务事件拒绝、失败重试、原 QAction 状态恢复、取消/刷新异常恢复。主要为真实 Qt 信号 + 受控提交替身，不冒充五条完整 Worker 闭环。
- 实库刷新：`tests/integration/test_task_terminal_refresh.py`（15 项，五任务 × 三终态），真实 SQLite + 当前人员/状态组合筛选 + 照片墙 ID 集合；终态使用受控信号，数据库行模拟任务已持久化部分。
- 配置插件：`tests/integration/test_plugin_directory_loading.py::test_loaded_plugin_action_obeys_window_admission`，真实目录加载/挂载 QAction，执行方法替身断言 busy 时零调用、终态后可执行且 tooltip 恢复。
- 深层保护：现有 `test_scan_single_flight.py`、`test_match_persons_controller.py` 和真实执行的 `test_scan_cancellation.py` 均由 Qt 回归及完整套件覆盖；Controller、Worker 源码未改。
- 开发中曾出现新协调器测试组合的原生崩溃，单项独跑通过；将 route 对 owner 的强引用改为弱引用后，同文件、Presentation 全套和最终全量均通过。此局部修复不构成 LIMIT-004/006 已根治的结论，也未以新增 skip 掩盖。
- 仅单 MainWindow 的宿主入口互斥，不提供跨窗口/跨进程锁或插件沙箱；同步对话框期间取消按钮不可用。ADR-041 枚举前置、Schema/Alembic、CLI、CI、打包、依赖均未改变。未做人工桌面视觉验收。

### Batch 2 验收证据与边界

- 状态矩阵：`tests/unit/application/test_workspace_readiness.py`（22 项）以替身仓储覆盖人员/照片/待识别/待审核/可归档/根可用/模型三态的全部组合与根探测边界；SQL 聚合语义由真实 SQLite 仓储测试与 `test_application_service_workflows.py`（合计与定向 20 passed）覆盖。
- 控制器矩阵：`tests/unit/presentation/test_workspace_controller.py`，快照→guidance 的 enabled/tooltip/next_action 全分支。
- UI 行为：`tests/unit/presentation/test_main_window_workspace_state.py`——初始禁用+下一步按钮、终态/对话框返回后刷新 enabled/tooltip 变化、任务进行中缓存渲染与终态恢复、busy 时下一步按钮禁用、模型缺失下一步弹说明不启动识别、删除登记随照片墙选区变化、取消 tooltip 三态（空闲/可取消/取消中）。`test_review_dialog_empty_queue.py`——0 条时对话框保持打开、按钮置灰、选区启用。
- 适配回归：`test_match_ui_wiring.py` 与 `test_main_window_task_coordination.py` 的快照式原状态断言更新为就绪/未就绪显式期望；原有互斥、取消、恢复语义断言不变。
- 边界：Widget 不触仓储（只经 `WorkspaceController` 缓存快照），可用性判断零异常捕获；`MatchPersonsController.start_match`、删除预览、归档服务校验原样保留为第二道防线；模型状态为装配期快照（装包后不自动探测文件变化，需重启）；归档根探测为咨询性检查，不保证后续文件系统变化；未做人工桌面视觉验收。

### Batch 3 验收证据与边界

- 五态矩阵：`tests/unit/presentation/test_overview_presenter.py`（12 项）——空库 → 导入 / 只有人员 → 扫描 / 只有照片 → 导入（识别需人员与照片双齐）/ 全识别待审核 → 审核 / 可归档 → 归档 / 模型缺失·未知 → 模型说明 / 归档根不可用 → 设置 / 全部完成 → 继续扫描；各步 done 语义与 detail 来源（guidance tooltip）断言；快照未加载 → 无清单无 CTA。
- 导航与常驻可见性：`tests/unit/presentation/test_main_window_navigation.py`（14 项）——Main 工具栏五主操作流程序、数据工具页三维护动作与 Main 无交集、五态 CTA 渲染与真实导入 picker 路由、页面栈切换、审核中心/设置触发式导航开对话框不切页且高亮回贴、状态栏（进度 + CancelTask 按钮）在每页可见、busy 时数据工具动作与概览 CTA 置灰带原因并恢复、导航五项标签。
- 兼容契约保持：ADR-038 插件挂载（findChild(QToolBar,"Main") + isVisible + actions() 文本契约）由 test_plugin_ui_loading / test_plugin_directory_loading 覆盖全绿；bulk/excel 导入闭环经 Main 工具栏触发"导入人员"全绿；Batch 1/2（协调 45、workspace_state 19、审核空态、workspace_controller）经适配后全绿；缩略图渲染/网格布局经切页适配后全绿。
- 边界：概览归档步 done 为中性判定（archivable_count==0 即完成，根不可用阻塞由 detail 说明）；空库审核步 done=True 由 detail 解释（权威引导是主 CTA）；未新增图标（文本符号 ✓/○）、未改主题/QSS、未新增依赖；导航仅本窗口范围，不提供跨窗口状态；未做人工桌面视觉验收。

## 6. Next Step（下一步开发计划）

Batch 3 已完成并交由 owner 验收（2026-09-18）。**Batch 4（照片库：筛选、空态、选择态与详情）需 owner 明确命令后才开工**（蓝图：`docs/development/ui-ux-execution-prompts.md` §Batch 4；前置 Batch 3 已满足）。Batch 5–7 仍需逐批明确命令，不因四项产品方向已批准而自动开工。v2.8.0 发布与安装包验收事项仍独立保留；本轮没有重新核验远端 CI、Release body 或安装包。后续均需 owner 立项：

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
