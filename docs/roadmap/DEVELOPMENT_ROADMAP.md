# PhotoArchiver — 后续开发路线图（Development Roadmap）

> **文档性质**：基于 2026-09-02 全项目体检（`docs/health-check/PROJECT_HEALTH_CHECK.md`）的后续开发计划
> **制定基线**：HEAD `3a2ef0a`（== origin/main，clean）
> **排序原则**：按 User Value / Blocking Relationship / Architecture Impact / Risk / Effort / Release Impact 排序，**禁止按 Feature ID 顺序机械开发**
> **工作量口径**：AI 工程工作量（XS < 0.5d ｜ S = 0.5–1d ｜ M = 1–3d ｜ L = 3–7d ｜ XL > 7d），非日历承诺
> **状态**：Phase A 已获 Owner 授权执行（2026-09-02）——P0-10 已完成；P0-1 → P0-4 按序执行，每项独立提交并在完成后按停止规则等待指令；Phase B–E / P1 / P2 未授权，本计划不自动启动任何阶段

---

## 1. Product Goal

基于 DDD + Clean Architecture 的企业级桌面照片归档系统，面向学校/政府/企业/档案馆/摄影工作室管理大量历史照片，自动化 导入 → 扫描 → 识别 → 审核 → 归档 → 导出 全流程。

**v1.0 的用户价值定义**：目标机构用户（以技术管理员陪同部署为前提）能够在 Windows 上以可重复的流程完成照片库的识别、审核、归档与导出，数据有安全底线（不丢、不静默换库、可恢复），界面功能与文档宣传一致。

## 2. Current State

- 主管线 10 环节 7 个真实闭环；15 步路线图 + Phase B 增强 + Phase 4.2–9 全部落地；四质量门全绿（pytest 570 passed / ruff / mypy 171 files / pip check）。
- **3 项用户可见功能失效**（后端已建成，UI 断线）：插件动作不加载（`main_window.py:191` 死路径）、缩略图不渲染（无 delegate 消费 THUMBNAIL_ROLE）、Excel 导入断线（装配只接 TXT reader）。
- **数据安全底线缺位**：无 WAL/busy_timeout、零备份、损坏库启动硬崩、数据库路径 CWD 相对、导入无事务、并行匹配整批末次持久化。
- **文档漂移**：PROJECT_STATUS 未随 Phase 9 更新、`docs/health-check` 悬空指针、FAQ 宣传失效功能。
- **F-002 恶化**：已知 flake 本轮单跑 ×2 均失败（失败点=单飞守卫断言；持久化断言通过）。
- 完整证据与 Gap Matrix：见体检报告 §3–§19。

## 3. Release Target

**v1.0**（产品首次面向目标受众的可交付版本；与已发布的 GitHub tag v2.x 版本号体系并行，是否更名/对齐由 owner 裁决）。

两个形态选项（**owner 决策点 D-0**）：
- **形态一（源码形态 v1.0）**：维持 ADR-031，交付对象为有技术管理员的机构；Minimum Path ≈ **8–10 工作日**（Phase A + Phase B 核心 + 发布门）。
- **形态二（含安装态 v1.0）**：触发 ADR-031 方案 B（console 入口 + package_data + 用户目录默认值 + 打包）；Minimum Path ≈ **13–17 工作日**（另加 Phase D）。

未裁决前，Phase A / Phase B 不受影响可先行；Phase D 阻塞等待。

## 4. P0（Must — v1.0 阻塞项）

| ID | Item | Gap Ref | Effort | 说明 |
|---|---|---|---|---|
| P0-1 | 插件加载路径修复 + `_load_plugins` 首测 | G-01 | XS | 补一层 parent；新增真实加载断言测试（防复发） |
| P0-2 | 缩略图渲染（delegate/DecorationRole）+ photo_list_model docstring 修正 | G-02 | S | 新增 QStyledItemDelegate；断言图标实际渲染 |
| P0-3 | Excel 导入接线（扩展名 dispatch 双 reader）+ ExcelPersonImportReader 测试 | G-03 | S | `app/services.py:140` 装配层修复；xlsx 解析路径零测试是当前盲区 |
| P0-4 | 取消信号接线（scan/import）+ 扫描单飞防护 | G-04 | S | `_connect_task_signals` 补 cancelled；扫描按钮运行期禁用 |
| P0-5 | SQLite 开启 WAL + busy_timeout | G-05 | XS | `sqlite_connection.py` PRAGMA 两行 + 锁场景测试 |
| P0-6 | 损坏库友好失败 + 最小备份机制 | G-09 | S–M | 启动校验、用户可读错误、首启/定期自动副本（`VACUUM INTO` 或文件复制） |
| P0-7 | 导入事务化 + 无 identity 行查重 | G-06 | M | UoW 或分批提交（原子性口径需 owner 一句话裁决）；identity 为空时按 name+department 查重或显式允许并文档化 |
| P0-8 | 模型摘要固定（EXPECTED_SHA256 + CI 移除 `--allow-unverified`） | G-10 | S | 需一轮 CI 验证（digest 首次 pin） |
| P0-9 | 数据库/模型路径锚定策略（若 v1.0 承诺 macOS 则必做） | G-08 | M | 需 owner 裁决锚定方式（env 展开为绝对路径 / 用户目录）；触碰 ADR-010/022 语境，需 ADR 备注 |
| P0-10 | 文档收口：PROJECT_STATUS 刷新（Phase 9 + 体检）、悬空 `docs/health-check` 指针、FAQ 插件宣传修正 | G-14 | XS | 本报告交付后立即执行，恢复 AI 上下文可信 |

**P0 合计：≈ 9–11 工作日**（若 v1.0 限 Windows 源码形态，P0-9 可降级 P1，合计 ≈ 7–9 日）。

## 5. P1（Should — v1.0 后第一个修复窗 / RC 强化）

| ID | Item | Gap Ref | Effort | 说明 |
|---|---|---|---|---|
| P1-1 | 并行匹配分片 flush（每 N 张 add_many） | G-07 | M | 需等价性/崩溃丢失窗口测试；默认 4 workers 路径丢批收窄 |
| P1-2 | F-002 重新定性并处置（修守卫释放时序或重设计测试） | G-11 | S–M | **前置：owner 解除"禁止修复"定性**（本轮已证明单跑不稳定） |
| P1-3 | tests/conftest.py 共享 fixture（真实 SQLite tmp_path 基建） | T-1 | S | 消除 ~12 处重复装配 |
| P1-4 | CI "no SKIPPED" 守卫修正（运行期 skip 统计） | T-5 | XS | `ci.yml:86-107` |
| P1-5 | CLI 对等：import-people / export 子命令 | G-15 | S | 复用既有 Application 服务，零新边界 |
| P1-6 | Windows 保留名/非法字符净化（ArchivePath VO） | G-12 | S | 保留设备名 + 尾点尾空格 + `: * ? " < > \|` |
| P1-7 | pytest-cov 引入 + 覆盖率基线（不设门槛，先可见） | T-2 | XS | dev.txt + 一次基线记录 |

**P1 合计：≈ 6–8 工作日。**

## 6. P2（Could — 条件触发 / 长期运营）

| ID | Item | Gap Ref | Effort | 触发条件 |
|---|---|---|---|---|
| P2-1 | 照片/人员删除 + 删除语义 ADR + FK 级联验证 | G-16 | L | owner 立项（**ARCHITECTURE IMPACT = YES**，schema 门） |
| P2-2 | 重扫对账（变更重读/删除清理/mtime 或 content hash 比对） | G-16 | M | 与 P2-1 同轮或独立 |
| P2-3 | 重复照片处置（删除/保留语义） | G-16 | M | 依赖 P2-1 删除语义 |
| P2-4 | CURRENT_BATCH 批次持久化 + 导出 | G-17 | M | schema/migration owner 门（**ARCHITECTURE IMPACT = YES**） |
| P2-5 | 导出 temp+rename 原子写 | G-18 | XS | 随手修 |
| P2-6 | UX 收尾包：审核行人类可读（姓名/文件名）、照片列表空态、语言占位控件移除、ReviewDialog 运行中刷新 | §6 体检 | S | 无需门 |
| P2-7 | 架构文档化：DEP 矩阵补记（infra→ports、presentation→workers、app 组合根）、QSettings 例外登记、app↔presentation 循环登记 | A-1~A-4 | XS | 仅文档，不解环 |
| P2-8 | junction 扫描防护或 Python 下限升级评估 | G-13 | S | 与依赖升级轮合并 |
| P2-9 | 大库导出流式化 | G-18 | XL | 仅当真实用户报内存问题（YAGNI 门） |
| P2-10 | i18n 实装 | G-19 | XL | 仅当出现非中文/英文受众需求信号 |
| P2-11 | 安装态分发（ADR-031 方案 B） | G-18/体检 §14 | L | **D-0 裁决触发**（见 Phase D） |

**P2 合计（不含条件项 9/10）：≈ 12–16 工作日；全部条件项触发另计 ≈ 12+ 工作日。**

## 7. Phase Sequence

> 每阶段独立交付、独立验证、独立提交；阶段间除注明依赖外可并行度有限（同一文件冲突面）。

### Phase A — 用户可见正确性修复（P0）
- **Goal**：让"文档宣称的功能"与"用户看到的"一致——插件、缩略图、Excel 导入、取消反馈全部真实可用。
- **Features**：P0-1 / P0-2 / P0-3 / P0-4 / P0-10。
- **Dependencies**：无（可立即开始）。
- **Architecture Impact**：无 schema/依赖/边界变更；presentation 层新增一个 delegate 组件（IN-SCOPE）。
- **Tests**：`_load_plugins` 加载断言、缩略图 delegate 渲染断言（qtbot）、xlsx reader 单测 + UI 链集成、cancelled 信号复位断言、扫描运行期按钮禁用断言。
- **Acceptance Criteria**：① 真实启动后插件动作出现在工具栏且 PluginReportDialog 可达；② 扫描后照片列表显示缩略图；③ .xlsx 人员文件导入成功入库；④ 取消扫描后状态栏复位 Ready；⑤ 扫描运行中 Scan 动作禁用；⑥ `git diff` 零越界（无 schema/依赖/规则改动）。
- **Estimated Effort**：3–4 天。
- **Risk**：低。最大风险是缩略图 delegate 引入渲染回归——用现有 17 个 FilterBar/模型测试 + 新增渲染断言覆盖。
- **Out-of-Scope**：i18n、视觉美化、删除功能。

### Phase B — 数据安全底线（P0）
- **Goal**：库数据"不静默损坏、不静默换库、可恢复、可并发"。
- **Features**：P0-5 / P0-6 / P0-7 / P0-8（/ P0-9 若含 macOS）。
- **Dependencies**：P0-7 的原子性口径需 owner 一句话裁决（整文件原子 vs 按批原子）；P0-9 需 owner 路径锚定裁决。
- **Architecture Impact**：sqlite_connection PRAGMA 变更（连接层）；导入服务事务包装（application 层既有 UoW 复用）；**P0-9 触碰配置语义需 ADR 备注并同步 configuration.md**。
- **Tests**：并发读写锁场景测试（扫描 UoW 期间审核写不炸）、损坏库启动错误路径测试、备份产物可恢复性测试、导入中断回滚测试（中断注入）、无 identity 重复导入行为测试、CI 全平台 digest 校验绿。
- **Acceptance Criteria**：① 扫描运行中同步审核不再出现 `database is locked`；② 损坏库启动给出中文可读指引而非 traceback；③ 备份文件可还原且应用可启动；④ 导入中途注入异常后库中零残留半批人员；⑤ CI 在无 `--allow-unverified` 下三平台模型校验通过；⑥ DATABASE_URL 指向锚定位置（若 P0-9 实施）。
- **Estimated Effort**：4–6 天（含 P0-9 为 6–8 天）。
- **Risk**：中。WAL 在网络盘/挂载盘有已知限制——需在文档注明（受支持形态为本地盘）；导入事务化改变部分提交行为（原行为是"错误行跳过、好行入库"——需保留逐行错误隔离、仅包裹 DB 写入段，避免把弹性导入变成全有全无）。
- **Out-of-Scope**：完整备份系统（版本化/增量）、恢复 UI。

### Phase C — 匹配韧性与测试健康（P1）
- **Goal**：收窄崩溃丢失窗口；恢复测试信号可信度；降低测试基建重复。
- **Features**：P1-1 / P1-2 / P1-3 / P1-4 / P1-7。
- **Dependencies**：P1-2 依赖 owner 对 F-002 的重新定性（本轮证据：单跑 ×2 失败，"已知 flake"描述已过时）。
- **Architecture Impact**：无边界变更；分片 flush 在既有 `add_many` 协议上多次调用（Domain 协议不变）。
- **Tests**：分片边界等价性（串行 vs 并行 vs 分片结果逐字节等价）、分片中断丢失窗口断言；conftest 迁移后全量回归。
- **Acceptance Criteria**：① 全量 pytest 在本轮与下轮**连续两次全绿**（F-002 处置后）；② 并行匹配中断最多丢 N 张（N=分片大小）；③ conftest 迁移后测试数不减。
- **Estimated Effort**：4–6 天。
- **Risk**：低–中。分片 flush 与 ADR-032"持久化收敛主线程"裁决兼容（仍在主线程、只是多次）。
- **Out-of-Scope**：识别管线性能再优化（W2-3=A 已有意收尾）。

### Phase D — 发布工程（P0-for-Release，D-0 门控）
- **Goal**：按 D-0 裁决交付形态一或形态二的 v1.0 发布链。
- **Features**：形态一 → P2-5（原子写）+ 发布验收清单 + 发布说明；形态二 → P2-11（console 入口、package_data、用户目录默认值、打包脚本、便携 zip/installer）+ 首启体验（模型包检测与下载指引）+ D-3/D-4/E4-E6 断点全清（ADR-031 反例守护条款：禁止半支持安装态）。
- **Dependencies**：**owner D-0 裁决**；Phase A/B 完成（不带病发布）。
- **Architecture Impact**：形态二触碰配置默认值语义（ADR-010/022）与打包布局——必须走正式 ADR（方案 B 草案已有 v1.1.0 候选记录）。
- **Tests**：打包产物冒烟（安装态/便携态真实启动、插件目录可达、库落在用户目录）；CI 增加产物构建 job。
- **Acceptance Criteria**：① 发布产物在干净机器（无开发环境）按 README 完成 安装→下载模型→导入→扫描→识别→归档→导出 全流程；② Release 说明与实际形态一致（不夸大）；③ 版本链（pyproject/CHANGELOG/.env.example）三处一致。
- **Estimated Effort**：形态一 ≈ 1–1.5 天；形态二 ≈ 5–8 天。
- **Risk**：形态二中——安装态是运行形态级重构（ADR-031 已实测确认），路径语义重构可能连锁触碰设置体系。
- **Out-of-Scope**：代码签名、自动更新、多语言安装器。

### Phase E — 库管理与长期运营（P2，owner 立项门）
- **Goal**：库从"只进不出"变为可运营。
- **Features**：P2-1 / P2-2 / P2-3。
- **Dependencies**：owner 立项 + 删除语义 ADR（**schema 门：photo 删除级联 recognition/archive_record/embeddings 需逐表裁决**）；Phase B 完成（删除必须建立在有备份的基础上）。
- **Architecture Impact**：**YES**——Domain 协议扩 remove、schema 可能扩软删除标记、UI 新确认流。
- **Tests**：级联删除矩阵（每张 FK 表 × 每种 ON DELETE 行为）、删除后归档文件处置语义（DB 记录删/文件留？需 ADR）、对账幂等性。
- **Acceptance Criteria**：① 删除照片后库与磁盘状态符合 ADR 语义且可审计；② 对账重扫不误删不漏判；③ 全量测试不减。
- **Estimated Effort**：7–12 天。
- **Risk**：高（数据破坏面 + 语义裁决复杂）——必须 ADR 先行。
- **Out-of-Scope**：回收站/撤销、云同步。

## 8. Dependency Graph

```text
D-0（owner：v1.0 形态裁决）
 ├──────────────────────────────┐
 ▼                              ▼
Phase A（可见性修复）      Phase B（数据安全底线）
   │ P0-10 文档收口先行          │ P0-7 原子口径裁决
   │                            │ P0-9 路径锚定裁决（含 macOS 时）
   ▼                            ▼
Phase C（韧性/测试健康）──► Phase D（发布工程）
   │ F-002 定性解除              │ 依赖 A+B 完成
   ▼                            ▼
（发布 v1.0）
   │
   ▼
Phase E（库管理，P2 立项门）── 独立于上方全部阶段，但依赖 Phase B 的备份能力
```

关键阻塞关系：
1. **P0-10（文档收口）必须最先做**——它恢复 AI 上下文可信度，成本 XS。
2. Phase D 依赖 A + B（不带病发布）；Phase C 可与 D 并行（不同文件面）。
3. Phase E 依赖 Phase B（无备份不删除）与独立 owner 立项。
4. P2-9/P2-10（流式/i18n）为纯需求信号触发，不进入任何排期。

## 9. Effort Estimate

| 桶 | 内容 | 合计 |
|---|---|---|
| **P0** | Phase A（3–4d）+ Phase B（4–6d；含 P0-9 为 6–8d） | **≈ 7–10 工作日** |
| **P1** | Phase C（4–6d）+ P1-5/6（1–1.5d） | **≈ 6–8 工作日** |
| **P2** | Phase E（7–12d）+ P2-4/5/6/7/8（≈ 3–4d） | **≈ 10–16 工作日**（条件项 P2-9/10/11 另计 ≈ 5–12d） |
| **Release 准备** | 形态一 1–1.5d ｜ 形态二 5–8d（含 ADR + 打包 + 冒烟） | **≈ 1.5–8 工作日** |

**Minimum Path to v1.0**：
- 形态一（源码）：Phase A + Phase B 核心（P0-5/6/7/8）+ 发布门 ≈ **8–10 工作日**。
- 形态二（含安装态）：上者 + Phase D 形态二 ≈ **13–17 工作日**。
- 若 v1.0 承诺 macOS：P0-9（+2d）必做，且形态二为实质必选（Finder 启动场景）→ ≈ 15–19 工作日。

## 10. Testing Strategy

1. **真实链路优先**（既有文化，延续）：真实 SQLite（tmp_path 文件库）、真实 QtWorkerExecutor、真实文件系统；边界 double 仅限模态 Dialog/QMessageBox 且明示 What-remains-real。
2. **新增"真实启动冒烟"断言类**：针对本次体检暴露的可见性断层（插件加载、缩略图渲染、xlsx 导入），每项修复必须带"用户视角"断言（组件出现在 UI 上 / 像素级渲染断言），防止再次"AC 全过、用户看不见"。
3. **每 Feature 门**：targeted 测试 → 相关 integration → 全量 pytest → ruff / mypy / pip check 四门全绿。
4. **并发/安全专项**：WAL 锁场景、损坏库注入、导入中断注入、digest 校验失败路径——全部落为可重复自动化测试。
5. **基建补强**（P1）：conftest 共享 fixture；pytest-cov 基线；CI skip 守卫修正。
6. **F-002 处置原则**：先定性（owner），后修复或重设计；处置后要求连续两个发布轮全量全绿才解除观察。

## 11. Release Gate

v1.0 tag 前必须全部满足：

- [ ] 四质量门全绿：pytest 全量 / ruff / mypy src / pip check
- [ ] F-002 已定性并处置（修复或带理由的测试重设计），全量连续两轮全绿
- [ ] 手工验收清单（真实机器、真实模型）：启动 → 导入（txt+xlsx）→ 扫描 → 识别 → 筛选 → 审核 → 归档（含冲突策略）→ 导出（CSV/XLSX，ALL+FILTERED）→ 插件动作可见 → 缩略图显示 → 取消扫描状态复位 → 重启后库数据完整
- [ ] 数据安全验证：备份文件可还原；损坏库给出友好指引；换目录启动库位置符合裁决（P0-9）
- [ ] CI 三平台全绿（含 digest 校验，无 `--allow-unverified`）
- [ ] 文档同步：PROJECT_STATUS / KNOWN_ISSUES（新增 Finding 登记或删除）/ CHANGELOG / user-guide / FAQ 与实际一致，无悬空指针
- [ ] 版本链一致（pyproject = CHANGELOG = .env.example）
- [ ] Release 说明包含形态定位声明（沿用 ADR-031 标注实践）+ 已知限制清单（LIMIT-001/002 等）
- [ ] Owner 签核

## 12. Definition of Done

**每 Feature**：链路真实闭环（UI→Application→Domain→Infrastructure→Persistence）+ 用户视角断言 + 四门绿 + `git diff` 零越界（无 schema/依赖/规则/契约改动，除非该 Feature 显式授权）+ Conventional Commits + 状态文档同轮刷新（PROJECT_STATUS；按需 KNOWN_ISSUES/ADR）。

**每 Phase**：全部 Feature DoD + Phase 验收标准逐条通过 + 无新增未登记 Finding（新发现当轮登记 KNOWN_ISSUES 或明确裁决）+ 提交历史可回溯（Feature 与验证分层提交）。

**v1.0**：Release Gate 全部勾选 + owner 签核。

## 13. Out-of-Scope（Do Not Do Now）

> 以下事项**明确不做**，防止资源错配与审计循环复发：

1. **不再开新的系统性 Audit Phase**（Phase 10/11/12…）：连续 6 轮审计的 Finding 已降至 F1/P3 级，边际收益递减；本体检报告即唯一全项目基线，后续一致性检查走 AI_ONBOARDING §12.1 的轻量节奏（每 2–3 Step 一次）。
2. **不做 Contract Revision 轮**：除非某开发轮实质触碰规则条文。
3. **识别/查询性能再优化**：识别 2.2×、插件查询 18.2× 已达标且 W2-3=A 有意收尾；planner UI 线程 N+1 与导出全内存在当前库规模无可感收益（P2-9 仅由真实用户报告触发）。
4. **架构升级/重构**：app↔presentation 解环、端口下沉 Domain、组合根重写——只做 P2-7 文档化，不动代码。
5. **依赖替换/清理**：不移除 pandas/watchdog（approved-unused 有注释零成本）、不升级 insightface（生态老化但无需求）、不引入新框架（含 DI 容器、ORM、platformdirs 等——除非 P0-9 裁决确需）。
6. **UI 视觉美化**：主题、图标、布局重设计一律不做；仅修"可用性断点"。
7. **i18n 实装**：仅允许移除占位控件（P2-6）；实装（XL）等需求信号。
8. **修复 LIMIT-001/002**：登记在案的设计限制，维持不修。
9. **过度测试**：不为覆盖率百分比写测试；覆盖率工具只做基线可见化。
10. **Excel 导入流式化/行数上限硬化**：本地信任边界内，YAGNI。
11. **自动更新/代码签名/多语言安装器**：Phase D 显式排除。
12. **批次持久化、安装态、删除语义**：三者均为 owner 门控项，AI 不得自行选定或提前实施。

---

> 本计划与 `docs/health-check/PROJECT_HEALTH_CHECK.md` 构成一次完整交付（ONE Health Check + ONE Roadmap）。**PHASE 顺序、P0 范围、D-0 裁决项均需 Owner 确认后方可启动任何开发。**

OWNER DECISION REQUIRED — STOP
