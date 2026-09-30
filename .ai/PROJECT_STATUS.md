# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**"项目现在开发到哪里了？"**
>
> 每次开发结束后刷新；不保留历史状态。
>
> Version: 1.45.0 · Last Updated: 2026-09-30 · Status: Live

---

## 1. Roadmap（开发路线图概览）

权威 15 步路线图：`.ai/business/roadmap.md`。

| Step | 名称 | 状态 |
|---|---|---|
| 0.5–11 | Walking Skeleton、基础设施、Domain、导入、扫描、缩略图、人脸识别、归档 | ✅ Completed |
| 12–14 | Main UI、Settings、Export | ✅ Completed |
| 15 | Plugin System | ✅ Completed |

M1–M7 及 Step 0.5–15 全部完成；阶段 B 业务增强 B1–B5 与收官加固阶段 0–3 已落地；发布工程至 v2.8.0（2026-09-13）。**2026-09-20 立项「人员名单导入与人脸分组匹配」重设计**：阶段 A（两段式导入，09-21 owner 验收 ✅）→ 阶段 B（人员与分组页，09-23 owner 验收 ✅）→ **阶段 C/D/E/F（2026-09-24 ~ 09-28 全部实施完成并冻结审查）**。**2026-09-28 完成全面工程健康体检（Stage 0–9，判 ATTENTION）与治理基线恢复（Stage 10）**；业务基线冻结正式生效待 owner 签核（Stage4.2 复审 8 项条件已满足，见 `docs/business-baseline/`）。

## 2. Current Step（当前开发阶段）

**照片库选中态可视化与多选可发现性（2026-09-30，feature，仅 Presentation 层）**——Owner 需求（选中状态更清晰 + 多选入口）；两轮只读方案审查 + 运行时探针确立事实基线：**多选机制早已存在**（`ExtendedSelection` + Ctrl/Shift/Ctrl+A + IconMode 框选 + B3 批量消费链全选集透传），真实缺口是**反馈不可见**——平台选中底色被缩略图覆盖（深色主题下不可察）、`selectionRectVisible=False` 时框选选区照常发生但矩形零渲染（探针实证 0 vs 820 变化像素）。实施（Owner 终版方案口径：修正 1(b) 选择操作簇 + 修正 2 内缘描边）：①`photo_list_delegate` 选中态三重反馈——缩略图**内缘描边**（活调色板 Highlight，笔宽 2、中心线内缩半笔宽，只覆盖照片边缘 ≤2px 且任意纵横比下不越出 image_box/不侵文件名条）+ **左上角几何勾选章**（Highlight 填充 + HighlightedText 三点折线对勾，零字体/字体回退依赖）+ 文件名 HighlightedText（既有行为，抽纯函数 `name_color` 钉契约）；②主窗口**选择操作簇**——「全选」常驻（`selectAll` 作用于模型行 = 当前筛选结果）+「清除选择」有选区可见 + 业务批量动作右对齐（行为/参数/测试语义零变化，仅视觉位置分组）；③`setSelectionRectVisible(True)`——只负责框选矩形可见性，不启用框选能力。业务语义零变更：共享归档入口 B3 语义（有选区归所选/无选区归全部 APPROVED）、移除登记、筛选全部保持并回归验证；Domain/Application/Infrastructure/QSS/迁移零触碰。**测试 16 项新增**（直绘渲染探针 5：选中/未选中/hover 组合/无缩略图文档化降级/调色板相对断言——全部对比交给委托的 palette 对象，禁止固定 RGB；页面交互 11：全选常驻与筛选作用域、空库 no-op、清除、busy 置灰、模型重载清空选区、QTest Ctrl/Shift、拖拽手势、**offscreen 子进程框选探针**——运行时探针发现 Windows 原生平台下 QTest/QCursor 合成的移动不携带鼠标按键、框选不推进（QtTest 平台限制，真实用户鼠标拖拽不受影响），框带可见性与真实扫掠选区在 offscreen 子进程钉死：框带像素可见 + 框带只覆盖 cell-0 时选区恰好 [0]）。全量 **1394 passed / 8 skipped / 0 failed**、ruff 全绿、mypy 261 文件零错。

**Stage 14 前置确认与跨平台视觉探针收敛（Stage 14-CI，2026-09-30）**——Owner 推送落地（origin/main = `fb573cf`）后首次远端三平台验证 **run #126**：windows ✅ / macos-stress ✅ / **ubuntu ❌（1 failed, 1380 passed）/ macos ❌（2 failed, 1379 passed）**——失败全部为 `test_visual_system.py` 渲染探针的真实断言失败（exit 1，非 LIMIT-006）。定性：探针要求单采样像素与期望 RGB 绝对相等，而原生按钮样式按平台**调制亮度、保留色相家族**（ubuntu primary `#247bc1` vs `#308cc6` value ×0.97；macOS `#16415c` ×0.46；macOS danger `#d66666` 白向调和；hue Δ≤3.6°）——绝对像素相等是 Windows 渲染路径巧合而非视觉契约；该文件位于 `35f9007..fb573cf` 首验区间，此前从未在 Linux/macOS 执行。修复（Stage 14-CI，`02e8cef`）：探针收敛为平台无关契约——无文字按钮内区 5 点采样取中位 + primary 相对**活调色板 Highlight** 的色相族窗口（±15°）/饱和度 ≥0.35/明度 ≥0.25 + danger 品牌红 QSS 字面量与渲染双验证（红相窗口环绕 0° ±15°）+ 与 normal 按钮饱和度差 ≥0.30（全部窗口取实测跨度 ≥1.4× 裕度并在测试内注明依据）。防御不降级：5 项突变负向验证（删 primary 规则 / 删 danger 规则 / 改涂 palette(Button) ×2 / 改涂 #2e8b57）逐一被捕获，生产文件逐字节还原；无新增 skip、无 fusion 强制、无平台豁免、生产行为零变更。本地验证：test_visual_system 18/18（本机深色主题 + 紫色强调色调色板亦绿，佐证活调色板相对断言）、全量 **1378 passed / 8 skipped / 0 failed**、ruff 全绿、mypy 261 文件零错。**[同日 Stage 14 Final 更新：owner 已推送 `02e8cef`+`5525d95`，run #127 三平台全绿，AUD-002 已闭环——见下段。]**

**Stage 14 Final Re-Audit / Release Readiness（2026-09-30）**——Owner 推送 `02e8cef`+`5525d95`（origin/main = `5525d95`）后完成最终审计（只读优先，生产代码零修改）：**远端 CI run #127（id 36673035844，2026-09-30T05:21Z，attempt=1）对最终 HEAD `5525d95` 三平台全绿**——windows ✅ / ubuntu ✅ / macos ✅ / macos-stress ✅，SHA 完全对齐（run head_sha = HEAD = origin/main，GitHub API 实查）；pytest 摘要 ubuntu/macos 各 **1381 passed / 5 skipped**（Stage 14-CI 前的 1F/2F 视觉探针全部转绿）、windows **1384 passed / 2 skipped**；skip 全部为已登记豁免（2×PA_STRESS 专用 job + 3×Windows 专属 junction），no-skip 守卫步骤全过，无 skip 掩盖失败。**AUD-002 = CLOSED**（KNOWN_ISSUES v1.20.0 整条删除、台账改判 FIXED、三方同步）。台账终态（25 条 HEAD 抽查复核——Stage 13D 后生产代码零变更：fb573cf=docs、02e8cef=test-only、5525d95=docs，代码级结论沿用 + AUD-010/011/014/015/016/018/022/023 与 8 个审计测试文件在位确认）：**P0 0 / P1 0 / P2 0 / P3 0 OPEN，无 BLOCKED**——23 FIXED + AUD-024 ACCEPTED-RISK（ADR-053 维持）+ AUD-002 CLOSED；AUD-011 维持 Option C 收口（ADR-050，三 Protocol 在位、公开导出 3/3）。SSOT 一致性收口：无 OPEN/Decision Required 残留；health-check README 当前状态注与 DOCUMENT_INDEX v1.6.1 两处陈旧指针修正。Unknown 分类：远端 CI=已验证；生产库实际状态/安装包二轮验收（现 v2.8.0 资产对应 `fe7f46f` 旧基线，须随下次发版重新出包）/阶段 B 五点复验/业务基线签核/Release body/CHANGELOG 切版 = Owner 外部动作；依赖 CVE 审计（pip-audit）无既有门禁 = Known 可选加固（非 Finding、不阻塞）。**Final Re-Audit = PASS，Release Readiness = READY FOR OWNER RELEASE**（≠ RELEASED：切版/tag/Release/安装包决策均属 Owner）。

**v2.8.1 版本切分（2026-09-30，Owner 裁决）**——发布元数据统一 2.8.1：pyproject `version` 与 `.env.example` `APP_VERSION` 已切 **2.8.1**；CHANGELOG `[Unreleased]` 整理为 **`[2.8.1] - 2026-09-30`**（Added = 阶段 A–F；Changed = 语义裁决 + 应用层端口化；Fixed = AUD-015/016/018/023 与跨平台视觉探针修复；Docs = 治理；两个重复 Changed 段归并，两条行为加固条目自 Docs 归位 Fixed），顶部保留空 `[Unreleased]`，历史 `[2.8.0]` 未改写。**tag / GitHub Release / 安装包尚未创建**——不把未执行操作写成已发布，为 owner 后续操作（§6 #2）。切版为纯元数据/文档变更，业务代码与整改逻辑零变更。

**AUD-011 决策闭合（Stage 13D-A，2026-09-30）**——Owner 裁决 **Option C**：`RegisterPhotoUseCase` / `ScanPhotoFolderUseCase` / `PruneMissingPhotosUseCase` **保留**，定位为**兼容性 / 公开 API 层面的 Protocol，不要求作为 Service 的强制抽象**；不删除、不改公开导出（`application/__init__.py` 3/3 在位）、不改生产行为。HEAD `36a1d0f` 复核：三者无 presentation/workers/plugins/tests 消费者，所描述的服务为活的组合根能力（`ApplicationServices` 具体类字段；CLI `prune` 真实驱动），Protocol 作为已发布类型契约保留；"零边界消费者"为结构性事实，**不再作为待处理项**。AUD-011 决策门**关闭**（ADR-050「Owner 决策」段 + 台账）。整改链 Finding 全部落地：**P1 0 OPEN · P2 1 OPEN（AUD-002，Owner 推送/远端 CI）· P3 0 OPEN**。

**整改收口与发布基线核验（Stage 13D，2026-09-30）**——体检整改全链收口：①**Finding 台账归一**（25 条：P1×1 / P2×10 / P3×14）——四行（AUD-001/003/009/014）此前收尾证据只在提交记录与 SSOT、行内状态未更新，本阶段经**当前 HEAD 复核后**归位；另对三处曾被体检结论证伪的项（AUD-016 无校验 / AUD-025 队列吞错 / AUD-010 直接 I/O）做 HEAD 证据抽查，全部与台账一致——**台账反映当前 HEAD，非历史报告**。②**审计产物入库**：`docs/health-check/`（README 索引 + 10 份报告 + 台账 + evidence）与 `docs/development/evidence/stage-f-*.md` 正式纳入 Git，使 SSOT 引用有效（此前指向未入库路径）。③**历史幽灵任务清理**：Stage B 五点复验确认为 Owner 人工验收项（非代码遗留）——其五项修复均有回归测试，仅桌面复验待 Owner。④**发布基线核对**：pyproject/`.env.example`/最新 tag 一致为 2.8.0（`git describe` = v2.8.0-59-ga5fb7aa），56 提交未推送（Owner 操作）。⑤质量门 HEAD 实测复现：**1378 passed / 8 skipped / 0 failed**、ruff 全绿、mypy 261 文件零错。⑥**Owner 决策（Stage 13D-A 落地）**：ADR-050 附属项闭合为 **Option C**——3 个零边界消费者 Protocol 保留、定位为兼容性/公开 API 层面 Protocol、非强制 Service 抽象；无生产行为变更。

**P3 连接生命周期与审核错误语义清偿（Stage 13C-C，2026-09-30）——体检 P3 全部 15 项处置完毕**（14 FIXED + AUD-024 ACCEPTED-RISK）。**AUD-024 ACCEPTED-RISK**：复核确认 per-call 连接不跨方法持有/不缓存/不跨线程共享（thread-local provider），UoW/backup/integrity 三路径均**显式 close**；剩余风险仅"依赖 CPython 引用计数"（项目钉定 3.11）+ 异常 traceback 下延后至 GC——有界非泄漏，**不机械插入 close()**；契约以 7 项行为测试钉死（连接唯一性、UoW commit/rollback/异常 close、嵌套拒绝、**真实 UNIQUE 冲突后不滞留写锁**）。**AUD-025 FIXED（前提证伪 + 契约固化）**：体检所指吞错点实为 D-1 **身份选择器**读取（`_available_persons`），**审核队列读取链无 blanket catch**——真实读失败向上冒泡，空态仅表示成功的空查询；4 项真实 SQLite 测试钉死（空态业务状态 / 读失败冒泡且 `REVIEW_EMPTY` 从未出现 / 故障恢复后重读正常 / 真实读路径对照）。选择器降级保留为文档化设计（失败后果由既有"未指定身份"显式告警覆盖），为其加独立错误提示属产品取舍不阻塞。ADR-053。验证：全量 **1378 passed / 8 skipped**、ruff/mypy（261 文件）绿。

**P3 命令契约与数据模型清偿（Stage 13C-B，2026-09-29）**——**AUD-016 FIXED（体检前提经复核证伪）**：应用边界早已存在权威校验（`ArchivePhotosService._resolve_conflict_strategy`：自有常量 + strip/lower 归一 + 非法值 ValueError，`test_archive_photos_service.py:135` 专项测试在案），体检"命令层无校验"结论不完整；本轮补两项防御纵深：executor 未知策略 `else` fail-closed（此前目标已存在时静默落入复制 = 等同未授权覆盖）、application/settings 两侧合法集合同值测试防漂移。**AUD-018 三子项全部 FIXED（ADR-052，登记既有设计）**：**018-A 级联**——recognition_results/archive_records person_id = SET NULL（记录描述照片，删人后照片与归档事实保留、身份匿名化）vs cluster_person_assignments/person_face_embeddings = CASCADE（映射与样本从属于人，无独立生命期），与业务基线记载一致，**不改 migration**；**018-B status**——裁定**域枚举为唯一状态机**，不为 002/008 冻结表补 DB CHECK，仅补齐唯一缺口：`RecognitionResult.__post_init__` 增加 status 类型校验（dataclass 不强制类型，此前可构造非法状态直达 DB，与 ArchiveRecord 同口径）；**018-C file_hash**——定性为溯源 metadata（Type D），**不做去重键**（同文件编辑后重导是合法业务行为，按内容去重会静默跳过合法重导），保留字段、明确用途。新增契约测试 12 项。验证：全量 **1367 passed / 8 skipped**、ruff/mypy（261 文件）绿。

**P3 架构与结构债务清偿（Stage 13C-A，2026-09-29）**——AUD-011（UseCase Protocol 双轨制）**FIXED**：盘点 11 文件/14 Protocol（每个恰一实现；11 个有 presentation/worker 边界标注消费者，3 个无但服务为活的组合根能力，测试引用 2/14）→ 核心问题以代码事实定案：**本项目单进程 + 单一组合根（`ApplicationServices` 具体类字段），Protocol 是跨边界标注机制而非 service 强制壳**；确立 **ARC-010** 使用准则 + **ADR-050**（含 3 个契约冗余候选的删除变体——触及 `application/__init__.py` 公开导出，属 Owner API 决策，记录为待决项，代码零变更）。**该待决项已于 2026-09-30 由 Owner 裁决闭合：Option C——三个 Protocol 全部保留，定位为兼容性/公开 API 层面 Protocol、非强制 Service 抽象（见 ADR-050「Owner 决策」段与 §2 Stage 13D-A）**。AUD-013（`common/` 空置 + main_window 规模）**FIXED**：①`common/` 为 1 行空骨架、全仓零导入 → **删除**并同步 DEP §3/§4 矩阵、ARC-008（改写为 Removed）、project-structure（ADR-051）；②main_window 职责盘点（63 方法 = 事件路由 29 / UI 构建 8 / 状态同步 5 / 编排辅助 11，业务规则与文件/SQL 触点为零）→ 判定"大但职责已外移"，**不做代码拆分**（行数非拆分理由），确立 **ARC-011** 职责边界规则防业务逻辑回潮。验证：全量 **1355 passed / 8 skipped**、ruff/mypy（261 文件）绿。

**P3 文档与治理卫生清偿 · 第一轮（Stage 13A，2026-09-29）**——体检 P3 共 14 项，按类别分批处置；本轮仅处理文档/治理/仓库卫生类 5 项：**AUD-006**（仓库杂物：`jobs34.json`/`jobs_tmp.json`/`runs_all.json`（93KB CI 查询 dump）/`release_check_tmp.yml`（工作流草稿副本）——经核验无任何代码/测试/文档引用（仅体检台账提及），`git rm` 出库 + `.gitignore` 增加 `jobs*.json`/`runs_all.json`/`*_tmp.yml`/`*.part` 规则并探针验证生效）；**AUD-007**（pre-commit 声明与配置脱节——处置 Option B：删除 dev.txt 钉定与 README 开发栈提及。理由：项目自始无 `.pre-commit-config.yaml`、`.ai/rules/git-rules.md` 无 hook 规范，真实质量门禁是 CI（`ruff check .` + `mypy src` + pytest）+ 手动工具调用；引入 hooks 属开发工作流变更，须 owner 立项而非卫生整改）；**AUD-022**（历史规划文档无标记——`DEVELOPMENT_ROADMAP.md` 与 `NEXT_PHASE_FEATURE_DEVELOPMENT_PLAN.md` 加 `Status: Historical` 横幅：Superseded by / Effective baseline `928981a`+ / 逐条列明已知失真点；历史正文原样保留）；**AUD-005 / AUD-008** 标记 RESOLVED BY PRIOR STAGE（Stage 10 合并 LIMIT 双表、LIMIT-006 去重、Stage 12C 更新 LIMIT-002 说明；LIMIT-001/004 经复核仍准确）。本轮零生产代码行为变更。剩余 9 项 P3（设计/测试/数据/UI 类：AUD-011/012/013/016/018/020/021/024/025）留 Stage 13B/13C。

**AUD-010 Application 文件 I/O 架构边界定性与处置（Stage 12E，2026-09-29）**——**DEP §17 定性 = Type B（规则过度严格）**：全量盘点确认 application 层真实文件 I/O 恰 3 处且全部业务性（归档复制+containment、名单批次哈希、失败清单导出），非业务性 I/O 为零；原禁令"应用层永不触碰文件"与本项目的工作流编排定位冲突。**处置 = 端口化（不取消禁令、不建通用 framework）**：新增 `ArchiveFileStore` / `FailureListWriter` 业务语义端口 + `RosterTableReader.read_bytes` 协议扩展 + 两个基建实现（FS 逻辑逐字迁移，行为零变化）+ **DEP-072** 取代 §17 绝对表述 + 守卫测试 `test_application_has_no_direct_file_io`（AST 逐文件断言，负向验证已捕获注入违规）。行为不变：三冲突策略、dry-run、containment/symlink 防护、M-4 mtime 语义、AUD-015 原子复制与 FS/DB 一致性模型全部由既有套件证明。ADR-049。验证：全量 **1355 passed / 8 skipped**（2 项为 Windows symlink 平台门控）、ruff/mypy 绿。

**AUD-015 归档 FS/DB 一致性定性与处置（Stage 12D，2026-09-29）**——故障注入定性（真实 SQLite + commit 边界崩溃注入，6 项测试）：**一致性模型定案（ADR-048）：Accepted Partial State + retry 幂等收敛**——批级 DB 原子 × 非事务 FS 复制为声明的设计取舍（伪事务否决：SQLite 无法回滚 FS 副作用）；窗口 1（批级回滚→孤儿）经重试幂等收敛（skip→SKIPPED/overwrite→ARCHIVED/rename→RENAMED+dup 兄弟）；**窗口 2（mid-copy 半写 + skip = 永久锁定损坏归档）为 Type B 恢复缺口 → 最小修复**：`_copy_file` 经同目录 .part + os.replace 原子落位（目标"存在即完整"，失败清理 .part，符号链接拒绝语义不变）；窗口 3（DB 成功后文件外部消失）executor 无法产生、无主动检测——已知边界。成功定义 = FS+DB 均成功。验证：全量 **1348 passed / 6 skipped**、ruff/mypy 绿。

**AUD-023 取消延迟整改（Stage 12C，2026-09-29）**——根因（体检 Stage 6/F-04）：`RunRecognitionService.execute` 一次性 submit 全部 futures，取消仅 break 消费循环，with 块退出 `shutdown(wait=True)` 排空全部已入队任务（千张 ≈60s）。**组合策略最小修复**：①取消分支内阻塞等待前批量取消 `futures[index:]`（executor 为任务内私有实例）；②`FaceAnalysisTask` 入口取消检查（闭合条目完成→下一轮检查间 worker 拾取竞争；`FaceAnalysisResult` 增 `cancelled` 标记，不产统计计数）；③with 块内兜底取消全部 future。语义不变：PENDING 不再启动 / RUNNING 单张安全点完成 / COMPLETED 保留，LIMIT-002 粒度不变，AR-02 维持。证据：修复前确定性复现（Event 门控，join 30s 超时、61s 排空）→ 修复后 4 场景 14/14 轮稳定（0.72–0.87s）；全量 **1342 passed / 6 skipped**。MatchPersons 遗留并行路径（无服务级取消，UI 已解绑 ADR-042）不在本阶段范围。

**AUD-019 workers/配对守卫测试补强（Stage 12B，2026-09-29）**——补齐体检覆盖缺口（真实 SQLite 集成测试 15 项，生产代码零改动）：**Workers**（`test_aud019_worker_lifecycle_sqlite.py` 6 项）：ConfirmImportTask 主路径（此前完全未覆盖：事件序列+真实落库+完成进度标记）、真实失败（批次不存在）→ failed terminal（错误信息保留、恰好一次、无假成功）→ 重试成功零重复副作用、ClusterFacesTask/Scan/Run 无 binder 兜底分支走真实链（Cluster 天然无 binder；Scan/Run 经真实 execute 绑定方法的 binder 剥离代理）、取消→cancelled terminal 且零 run 产生、多订阅者失败终态 exactly-once；**Pairing 守卫**（`test_aud019_pairing_guards_sqlite.py` 9 项）：不存在对象/双重确认/reject 后确认/非法簇状态/人员删除真实级联后陈旧建议被拒/簇删除 FK CASCADE 后作用域隔离（其他簇建议不受影响）/TOCTOU delete-then-update 注入触发受影响行数守卫/双实例竞争单胜者/clamp 边界。覆盖率：application_tasks 74.1%→81%（定向）、pairing_workbench 89.8%→92%。验证：全量 **1338 passed / 6 skipped**、ruff/mypy 绿。

**AUD-004 全链贯通回归（Stage 12A，2026-09-29）**——补齐体检遗留的"两段式导入→扫描→识别→聚类→配对建议→人工确认→归档规划→归档执行"单条真实链回归：`tests/integration/test_aud004_full_chain_regression.py` 4 场景（真实 SQLite/仓储/服务，仅 AI 检测器按任务书允许用可控假件）：A 标准冷启动（重复 execute 去重 + 全批重跑不覆盖人工决定/兼容 (person,photo) 幂等/归档零重复，且第二代建议自动切换 sample_match 路径——双路径语义得证）、B 簇<人不强配、C 簇>人未确认簇不归属、§9 单项失败隔离+FAILED 重试（现状语义钉定，不涉 AUD-015）。**期间暴露并修复真实接缝缺陷（AUD-004 范围内最小修复）**：`RunRecognitionService` 构造 run_photos 快照时丢弃照片 captured_at → 聚类 sort_key 经真实链路恒为 `~|~|创建序`，Stage D 时间排序从未真实生效；最小修复=服务注入 `PhotoRepository`（可选参数，兼容既有构造）+ 快照填充 captured_at + 装配接线 + 测试快照接缝断言；生产链时间排序自此真实生效。验证：全量 **1323 passed / 6 skipped**、ruff/mypy 绿。

**AUD-017 实现闭环（Stage 11A 决策 + 11B 实现，2026-09-28）**——owner 正式裁决 **Option C**（`person_face_embeddings` 作为后续批次样本相似度候选来源）+ **K-3=suggested 建议层**（样本相似度仅生成 `similarity_suggestion`，不得直接形成身份确认），并附加约束：冷启动 FaceCluster → sort_key → roster_order → ordered_suggestion → 人工确认 → 样本沉淀 链不变、`person_embeddings` 不恢复生产写入路径。**实现核验结论：Option C 的生产链在阶段 E 已存在**（`SuggestPairingsService` 经 `list_enabled()`（enabled=1，person_id 确定序）读候选样本 + `NumpyCosineSimilarityFactory` 多样本 max 余弦 + 规则① `sample_match` 建议 ≥0.40 + 规则③冷启动补位，全部落 suggested 层），本阶段完成证明与登记：**真实 SQLite 闭环集成测试 4 项**（`tests/integration/test_aud017_sample_suggestion_sqlite.py`——主闭环含 disabled 样本排除与解除→重建议→重复确认样本幂等 / 零样本冷启动仅 ordered / 平分 tie-break 确定性 / 维度不一致 fail-closed）、domain 规则钉定 3 项（cluster<persons 不强配 / 平分首位 / 高分胜出）、kernel 钉定 2 项（量化 0.4/0.6 边界 + 混维 fail-closed）；**生产代码零改动**。登记：ADR-047、决策文档 §7 已填裁决、KNOWN_ISSUES 移除 AUD-017（闭环）。遗留边界（ADR-047 登记）：识别兼容链对 `person_embeddings` 的遗留读不动（候选可证恒空）；多样本大库性能路径为实现期关注点；识别侧阈值边界证据随实现轮补校准报告（F1-2）。

**治理基线恢复与 AUD-017 决策准备（Stage 10，2026-09-28）**——全面工程健康体检（同日，Stage 0–9，只读，判 **ATTENTION**：P0×0 / P1×1 / P2×10 / P3×15）后的第一轮整改，严格限定五项：

- **AUD-001（P1）SSOT 恢复**：本文件与 KNOWN_ISSUES/ARCHITECTURE_DECISIONS/DOCUMENT_INDEX/CHANGELOG 全部刷新至 HEAD `2823d1c` 口径（阶段 C–F 完成态、迁移链 001–008、体检发现登记）；根因（阶段收尾义务无书面登记载体）已在体检 DOCUMENTATION_AUDIT 立案。
- **AUD-003（P2）业务基线入库**：Stage1_BusinessFacts / Stage1_Handoff / Stage2_BusinessRules / Stage2_Handoff / Stage3_BusinessDiagrams / Stage4_FinalAudit / Stage4_1_FinalReview / Stage4_2_FinalFreezeReview 八份自 `D:\workFile\PhotoArchiver-BusinessReview\` 原样收入 `docs/business-baseline/`（正文零改写；来源/基准/有效性表见该目录 README）。
- **AUD-009（P2）依赖矩阵三方对齐**：`dependency-rules.md` §4 矩阵 5 行过期口径修正（app 组合根全开；infrastructure 增 application ports/dtos；presentation 增 domain/workers/plugins/app-context；workers 增 domain）+ DEP-001/030/040 同步——与 AST 实测及守卫测试 `test_layer_boundaries.py` 一致。
- **AUD-014（P2）Top-1 归档残留清理（F1-4）**：`archive_planner.py` docstring、`face-recognition-pipeline-and-archive.md` §6.2、`plugin-context-design.md` §3.1 三处全部改为 (person, photo)（E-SG-6）口径；识别侧 Top-1（ADR-017 语义）不受影响。
- **AUD-017（P2）决策与实现**：Owner 裁决 **Option C + K-3=suggested 层**（2026-09-28），已实现并登记 ADR-047；决策材料 `docs/decisions/AUD-017-person-embeddings-decision.md`（现状/数据链/三方案对比，§7 结论为已裁决 Option C）。

**阶段 C–F 实施摘要（2026-09-24 ~ 09-28，全部已入库并冻结审查）**：

- **阶段 C 可追溯识别运行**（`73657ec`/`7ec3173`/`a9f15b3`）：`RecognitionRun`/`FaceObservation` 数据链（migration `004`/`005`）；`RunRecognitionService` 逐脸观测 + recognition_results PENDING 兼容双写（审核/归档/导出/就绪全绿）；UI 入口切 `RecognitionScopeDialog`（范围 + 脸数档位 + 仅重试失败照片），重跑=新建 run；AST 守卫禁止旧 MatchPersons UI 路径回接。
- **阶段 D 人脸聚类**（`5c3c6d2`/`8d4c342`/`c543828`）：两段式算法（贪心簇心候选 ≥0.5 → complete-linkage 合并 **≥0.4 含等号**，owner 裁决修正实现偏差并以三点边界测试钉死）；低质量门限默认 0.0 禁用待 F 校准；表 `006_face_clusters`；时间排序 sort_key；D-4 UI 入口（人员页聚类区 + 结果对话框）。
- **阶段 E 配对工作台**（`ee5d7d4`/`f6e70b0`）：簇→人建议（sample-match max-cosine ≥0.40 优先，排除 rejected 对；顺序建议次之；**永不自动写归属**）；确认→sort_snapshot + D3 兼容 APPROVED + 整簇样本沉淀（007 `person_face_embeddings`，UNIQUE 幂等）；**E-SG-6**：兼容/归档去重作用域 = (person, photo)，不同人各自持有同照片归属；改派/解除回撤旧投影并 disable 旧样本（E-SG-5）；unassign 覆盖三入口撤销。
- **阶段 F 历史/性能/上线**（`e7d2735`/`d47d984`/`b3b8685`/`2823d1c`）：真实数据校准（473 照片/1441 脸/44 簇全链实测）；人员历史回填（幂等）；失败重试入口 + 失败清单导出；1000 张生命周期压测（取消→部分持久→重试覆盖剩余）+ 升级完整性演练（生产库副本 003→007 零丢失）；**冻结阻断修复**：BLK-1 归档按稳定 person_id 去重（migration `008`：archive_records.person_id 回填 + confidence 可空三态）+ D-1 审核批准可携身份 + D-2 阈值 `>=0.40`。
- **冻结审查链**：Stage4 独立审计（NOT-FREEZE-READY）→ `2823d1c` 修复 5 阻断 + 2 裁决 → Stage4.1 复审（代码级闭合）→ 基线收口（Stage1–3 文档对齐 2823d1c）→ **Stage4.2 终审：8 项冻结条件全部满足**（真库探针 + D-1 七层一致 + D-2 边界 0.39 不命中/0.40 命中），**待 owner 签核**。

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
| 人员导入重设计（阶段 A–F） | ✅ 实施完成 | 全部入库至 `2823d1c`；业务基线见 `docs/business-baseline/`；冻结待 owner 签核。 |
| 版本链 | 🟡 切版/tag 完成、待发行 | pyproject / .env.example = **2.8.1**（owner 裁决 2026-09-30）；CHANGELOG `[2.8.1] - 2026-09-30` 段已切分；**v2.8.1 annotated tag 已创建并推送**（→ `8d8a126`，本地 + 远端 `git ls-remote` 双实查；历史 v2.8.0 未动）；**GitHub Release / 新安装包产出与二轮验收为 owner 剩余操作**。 |
| 测试基线 | ✅ | 全量 **1394 passed / 8 skipped / 0 failed**（2026-09-30 实测 248.92s；含照片库选中态优化新增 16 项）；行覆盖 **93.9%**（10541/11229，AUD-021 可复现口径，见 §5 覆盖率行）；此前已知盲区（workers 错误分支、配对守卫）已由 Stage 12B 补齐（AUD-019）。 |
| CI | ✅ | run #127/#128 对 `5525d95`/`57fb8d5` 三平台全绿（windows 1384+2 / ubuntu、macos 各 1381+5，skip 全为已登记豁免）；`8d8a126`（切版）已推送，**其后的照片库选中态优化 feature 提交待推送触发远端验证**；本地三质量门绿（ruff / mypy 261 文件 / pytest）。 |
| 业务基线 | ✅ 已入库 | `docs/business-baseline/`（Stage1–3 现行有效 + Stage4/4.1 历史 + Stage4.2 冻结复审），基线 `2823d1c`，来源与有效性表见其 README。 |
| 未决问题 | ✅ 清零 | 体检 25 条 Finding 终态（2026-09-30 Stage 14 Final）：**P0 0 / P1 0 / P2 0 / P3 0 OPEN，无 BLOCKED**——23 FIXED + AUD-024 ACCEPTED-RISK + AUD-002 CLOSED（run #127 三平台绿）；详见 `docs/health-check/FINDINGS_LEDGER.md`。 |
| Limit 登记 | 4 项 | LIMIT-001（真实缺模型 E2E 未入 CI）/ LIMIT-002（取消粒度——说明已按体检修正：识别取消延迟=剩余队列排空，AUD-023）/ LIMIT-004（Windows 本地子集顺序原生崩溃）/ LIMIT-006（macOS/Linux runner 环境漂移 SIGSEGV，CI 自愈 + darwin skip 维持），均 Low、不阻塞。 |
| Release body | ⏳ 待 owner | GitHub Release v2.8.0 资产已发布；body 签核流程同前。 |

### 数据库 Schema

Alembic 管理，迁移链 **`001_initial_v4` → `002_split_create_ddl` → `003_import_batches_and_roster` → `004_recognition_runs_and_observations` → `005_recognition_run_error_count` → `006_face_clusters` → `007_assignments_and_person_samples` → `008_archive_identity_and_confidence`**（head = 008）。003 导入批次/草稿 + roster_order；004/005 识别运行/观测；006 聚类；007 配对/样本；008 archive_records.person_id 回填 + recognition_results.confidence 可空（BLK-1/BLK-5，幂等守护 + downgrade 先回填 NULL）。每次启动 `alembic_runner` 自动 upgrade head（frozen 适配）。

---

## 4. Current Modules（当前模块状态）

| 模块 | 状态 | 关键位置 |
|---|---|---|
| Logging / Configuration | ✅ | `infrastructure/logging/`、`infrastructure/config/`（ADR-035 用户数据目录锚定） |
| Database | ✅ | Alembic 001–008（ADR-024/027）；17 张表全有读写方（体检对账） |
| Domain / Import / Scan / Thumbnail | ✅ | `domain/`、`application/services/`、`infrastructure/`；扫描枚举前置主线程（ADR-041） |
| 模型部署（下载/解包/校验/frozen） | ✅ | `model_deployment.py`（sha256 fail-closed）+ `insightface_loader.py` + `download-models` CLI |
| Recognition / Review（兼容链） | ✅ | InsightFace 检测/识别 + 审核闭环（D-1 身份选择器，`2823d1c`） |
| 可追溯识别运行（阶段 C） | ✅ | `run_recognition_service.py` + `recognition_runs`/`face_observations`（004/005）+ `recognition_scope_dialog.py`（范围/重试/失败清单导出） |
| 人脸聚类（阶段 D） | ✅ | `domain/services/face_clustering.py`（两段式 ≥0.5/≥0.4 含等号）+ `cluster_faces_service.py` + `006` + 结果查看 |
| 配对工作台（阶段 E） | ✅ | `pairing_workbench_service.py` + `domain/services/pairing.py` + `007`；E-SG-6 (person, photo) 兼容语义；样本沉淀/回撤 |
| 归档（身份去重） | ✅ | `archive_planner.py`/`archive_executor.py`——(person, photo) 去重（E-SG-6 + BLK-1 稳定身份，migration 008）；**docstring 已同步 E-SG-6 口径（AUD-014 整改）** |
| 历史回填 / 失败重试（阶段 F） | ✅ | `backfill_historical_people_service.py`（幂等）+ `recognition_failure_service.py` |
| UI / Settings / Export | ✅ | 主窗口、设置闭环、Excel/CSV/HTML 导出；CURRENT_BATCH fail-closed 延迟项 |
| 人员筛选 | ✅ | 三轴组合筛选 + 人员轴智能搜索（`presentation/person_name_ranker.py`） |
| 人员名单导入（阶段 A） | ✅ 已验收（09-21） | 两段式：`parse_import_draft_service.py`/`confirm_import_service.py`/`import_preview_dialog.py`（003） |
| 人员与分组页（阶段 B） | ✅ 已验收（09-23） | `manage_people_service.py`/`people_admin_page.py`；导航 5→6 |
| Plugins | ✅ | 发现/装载/生命周期 + PluginContext 读方法 + import_people（ADR-026/028/038） |
| 业务基线（文档） | ✅ 已入库 | `docs/business-baseline/`（Stage1–3 有效 / Stage4 系演进链）；决策材料 `docs/decisions/AUD-017-person-embeddings-decision.md` |

---

## 5. Last Session（最近一次开发记录）

| 项目 | 值 |
|---|---|
| 时间 | 2026-09-30（Windows 11 build 26200 / Python 3.11.9 / PySide6 6.11.1）；**照片库选中态可视化与多选可发现性 feature 轮**（v2.8.1 切版/tag 之后第一个功能优化） |
| 会话范围 | 两轮只读方案审查（运行时探针实证选中/多选/框选行为基线与 QTest 平台限制）→ Owner 终版方案定稿（修正 1(b) 选择操作簇 + 修正 2 内缘描边）→ 实现 → 16 项新测试 → 三质量门 → SSOT 同步 |
| 关键产出 | `photo_list_delegate`：选中态内缘描边（活调色板）+ 左上角几何勾选章 + `name_color` 纯函数；`main_window`：选择操作簇（「全选」常驻 /「清除选择」有选区可见 / 批量动作右对齐）+ `setSelectionRectVisible(True)`；`ui_text`：2 条新文案；`CHANGELOG [Unreleased]` 3 条（明确不写成"新增多选底层能力"）；测试：直绘渲染探针 5 + 页面交互 11（含 offscreen 子进程框选探针——QTest/QCursor 原生合成移动不带按键的平台限制已登记在测试 docstring） |
| 当前质量门 | 本地：1394 passed / 8 skipped / 0 failed（248.92s）、ruff 全绿、mypy 261 文件零错（2026-09-30 实测）；远端 run #127/#128 对 5525d95/57fb8d5 绿，本 feature 提交待推送验证 |
| 覆盖率（可复现） | **93.9%（10541 / 11229 行语句，coverage 7.16.0，branch coverage 关闭）**——测量范围 `src/photo_archiver/`（经 `pyproject` 的 `pythonpath = ["src"]` 解析）；**分母不含**：根入口 `main.py`（CLI）、`tools/`、`scripts/`、`tests/`、`alembic/`；无 `[tool.coverage]` 配置、无 omit 规则（仅 `# pragma: no cover`）。复现命令：`.venv/Scripts/python.exe -m pytest tests/ -q --cov=src/photo_archiver --cov-report=json`（本地）；CI 门禁命令 `pytest --cov=photo_archiver --cov-fail-under=90`（仅 Linux job，见 `.github/workflows/ci.yml`） |
| 工作区 | main；本 feature 收口提交后 1 提交领先 origin（push 属 owner，GIT-020），未执行 push |
| Remaining | 见 §6 Next Step。 |

---

## 6. Next Step（下一步开发计划）

**待 owner**：

| # | 事项 | 依据 |
|---|---|---|
| 1 | **业务基线冻结签核**（Stage4.2 八项条件已满足，签核即冻结生效） | `docs/business-baseline/Stage4_2_FinalFreezeReview.md` §9 |
| 2 | **发行 v2.8.1**（切版 + tag 均已完成：v2.8.1 annotated tag → `8d8a126` 已推送远端）：GitHub Release（body 粘贴 CHANGELOG `[2.8.1]` 段）→ 新安装包产出与二轮真机验收；手册阶段 C–F 功能章节补齐仍待 | 体检 §11 发布风险 + owner 切版裁决（2026-09-30） |
| 3 | 阶段 B 复审五点复验（中文文案/拖拽无空行/删除预选/导入即刷/移动选区跟随） | 历史在案（09-23） |
| 4 | v2.8.0 Release body 签核 + A-1（CURRENT_BATCH）/ A-3（代码签名）决策 | 历史在案 |
| 5 | AUD-017 尾随项：识别侧阈值边界证据补入校准报告（F1-2 闭合）；`person_embeddings` 遗留读清理与否（清理属独立裁决） | ADR-047 |

**可立项**：全链贯通回归测试（导入→配对确认→归档执行单条）；AUD-023 取消延迟修复。**明确不做**（历史裁决维持）：i18n 实装、自动更新、macOS 安装包、批次撤销、重排性能 P1/P2。

---

## 7. Key Files（关键文件索引）

| 职责 | 文件 |
|---|---|
| 运行状态唯一快照 | `.ai/PROJECT_STATUS.md`（本文件） |
| 架构决策（ADR-001~053） | `.ai/ARCHITECTURE_DECISIONS.md`（042~046 = 阶段 C–F 裁决补登记；047 = AUD-017 Option C；048 = 归档 FS/DB 一致性模型；049 = Application 文件访问端口化；050 = UseCase Protocol 使用准则；051 = common 移除 + MainWindow 职责边界；052 = 数据生命周期与状态机职责定案；053 = 连接生命周期假设 + 审核错误语义） |
| 当前问题与限制 | `.ai/KNOWN_ISSUES.md`（含体检登记节） |
| 文档体系导航 | `.ai/DOCUMENT_INDEX.md` |
| 业务基线（现行/历史/冻结） | `docs/business-baseline/`（README 含来源与有效性表） |
| Owner 决策材料 | `docs/decisions/AUD-017-person-embeddings-decision.md` |
| 体检报告与台账 | `docs/health-check/`（**已入库**，含 README 索引 + FINDINGS_LEDGER 状态字段为 Finding 权威） |
| 用户使用手册 | `docs/user-guide/manual.md`（阶段 C–F 功能章节待补，Next Step #3） |
| 依赖矩阵（SSOT） | `.ai/rules/dependency-rules.md` §4（v1.2.0 已对齐守卫测试） |
| 数据库初始化/迁移 | `sqlite_connection.py`、`alembic_runner.py`（链 `001`→`008`，`alembic/versions/`） |
| 可追溯识别运行 | `run_recognition_service.py` + `recognition_scope_dialog.py` + `recognition_failure_service.py` |
| 聚类 / 配对 | `domain/services/face_clustering.py` / `pairing.py`；`cluster_faces_service.py` / `pairing_workbench_service.py` |
| 归档（身份去重） | `archive_planner.py` / `archive_executor.py`（E-SG-6 + BLK-1） |
| 分层边界守卫 | `tests/unit/architecture/test_layer_boundaries.py` |
| 质量验证 / 发布工作流 | `tests/`、`.github/workflows/ci.yml` / `release.yml` |

---

> 本文件只描述当前状态；历史决策见 `.ai/ARCHITECTURE_DECISIONS.md`，当前问题见 `.ai/KNOWN_ISSUES.md`，业务基线见 `docs/business-baseline/`，路线图见 `.ai/business/roadmap.md`。
