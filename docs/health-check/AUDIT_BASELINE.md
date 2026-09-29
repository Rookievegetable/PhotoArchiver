# AUDIT_BASELINE.md — 全面工程健康审计 · 审计基线（Stage 0）

- **审计日期**: 2026-09-28
- **审计对象**: D:\work\PhotoArchiver（工作区快照，审计开始时状态）
- **审计性质**: READ-ONLY（未修改任何业务代码/测试/配置；仅新增本目录审计报告）
- **审计方法**: 证据驱动；每条结论标注 VERIFIED（本轮直接取证）/ INFERRED（结构推断）/ UNKNOWN（资料不足）
- **测试基线实测**: `python -m pytest -q` → **1310 passed / 6 skipped / 0 failed，250.55s**（本轮实测，exit 0）

---

## 1. Git 基线 [VERIFIED]

| 项 | 值 |
|---|---|
| Branch | `main` |
| HEAD | `2823d1c7ceaab09c38d39b9a80e1e724839cfa17`（2026-09-28 01:44 +0800，"fix: resolve business baseline freeze blockers"） |
| 与远端关系 | **领先 `origin/main` 44 个提交，未推送**（`git status` 原文："Your branch is ahead of 'origin/main' by 44 commits"） |
| Remote | `https://github.com/Rookievegetable/PhotoArchiver.git` |
| Working tree | 干净（无已跟踪文件修改）；**2 个 untracked**：`docs/development/evidence/stage-f-acceptance-review.md`、`docs/development/evidence/stage-f-report-verification.md` |
| Stash | 空 |
| Tags | `v1.0.0` … `v2.8.0`（最新 v2.8.0，2026-09-13） |
| `git describe` | `v2.8.0-47-g2823d1c`（最新 tag 之后已有 **47 个提交**，含阶段 A–F 全部工作） |
| 分支 | `main`、`backup/pre-audit-history-cleanup`（本地备份分支） |

**推断（INFERRED，供 Stage 5/8 核查）**: 44 个未推送提交意味着 `.github/workflows/ci.yml`（push→main 触发）**未对 HEAD 所在区间运行过**；远端 CI 绿徽章只反映已推送历史。

## 2. 版本基线 [VERIFIED]

| 载体 | 值 | 一致性 |
|---|---|---|
| `pyproject.toml` | `version = "2.8.0"` | = 最新 tag |
| `CHANGELOG.md` | 最新段 `[2.8.0] - 2026-09-13`；**无 Unreleased 段** | 未覆盖 v2.8.0 之后 47 个提交（阶段 A–F 用户可见功能） |
| `.ai/PROJECT_STATUS.md` | `Version: 1.34.1 · Last Updated: 2026-09-23` | **滞后于 HEAD**（见 §10/§11） |

## 3. 技术栈 [VERIFIED]

- **语言**: Python 3.11.9（`.venv` 实测；`requires-python >= 3.11`），Windows 平台开发（pyproject classifiers 含 macOS，macOS 为实验性支持——见 KNOWN_ISSUES LIMIT-006）
- **GUI**: PySide6 6.11.1（Qt6 桌面，pytest-qt 无头测试）
- **持久化**: SQLite；仓储层为**裸 sqlite3**（非 ORM）；SQLAlchemy 2.0.43 仅作为 Alembic 1.16.4 的连接层（`requirements/base.txt` 注释明示 "The ORM is NOT used"）；迁移链 `alembic/versions/001…008`（8 个迁移，含 upgrade/downgrade）
- **AI**: insightface 1.0.1 + onnxruntime 1.27.0 + opencv-python 4.12.0.88 + numpy 2.2.6；模型包 buffalo_l（`resources/models/buffalo_l/` 本地在场，不受 git 跟踪）；模型下载 sha256 fail-closed（`scripts/download_models.py`）
- **图像**: Pillow 11.3.0
- **数据/导入**: openpyxl 3.1.5（.xlsx/.xlsm）、xlrd 2.0.1（.xls，D-1 owner 批准）、pydantic 2.11.7 / pydantic-settings 2.10.1
- **日志**: loguru 0.7.3
- **声明但未使用（base.txt 注释自述）**: pandas==2.3.1（零 import）、watchdog==6.0.0（零 import）
- **打包**: PyInstaller onedir + Inno Setup（`packaging/windows/`），在线/离线双安装包；sdist+wheel（release.yml）
- **入口**: `main.py`（CLI + GUI 双入口，约 31KB；frozen 适配；`sys.path` 注入 src）

## 4. 项目结构 [VERIFIED]

```text
src/photo_archiver/            258 个 .py，28,887 行
├── app/                       组合根（bootstrap/application/context/repositories/services/ui_assembly）
├── application/               commands(13) / dtos(17) / ports(18) / services(39) / use_cases(11)
├── domain/                    entities(10) / repositories(11 Protocol) / services(2) / value_objects(9)
├── infrastructure/            database(17，sqlite_* 仓储+alembic_runner+backup+integrity)
│                              exporters(5，含 _atomic_write/_spreadsheet_safety) / filesystem / image
│                              importers(4) / logging / persistence / ai / config
├── presentation/              controllers(13) / views(21) / task_coordinator / ui_text / visual_style
├── workers/                   task/events/qt_executor/application_tasks/export_task
├── plugins/                   loader.py
└── ai/                        insightface detector/recognizer/types/similarity_matcher
tests/                         169 个测试文件，31,530 行（unit / integration / unit/architecture）
alembic/versions/              001_initial_v4 … 008_archive_identity_and_confidence
docs/                          architecture / deployment / development(计划+ADR 草稿+evidence) /
                               health-check(旧体检 2 份) / roadmap / user-guide
.ai/                           PROJECT_STATUS / ARCHITECTURE_DECISIONS(ADR-031~041) / KNOWN_ISSUES /
                               DOCUMENT_INDEX / AI_ONBOARDING / business/roadmap.md / rules/(10 份)
.github/workflows/             ci.yml（3-OS×py3.11 矩阵）+ release.yml（sdist/wheel + Windows 安装包）
scripts/                       bootstrap / download_models / limit006_streak / ui_acceptance_automation
tools/                         bench_* / spike_* / stress_lifecycle_stage_f / validate_stage_f /
                               verify_upgrade_integrity / backfill_historical_people
packaging/windows/             photo_archiver.spec / installer.iss / ChineseSimplified.isl
```

分层方向（文件布局推断，INFERED → Stage 1 用 `tests/unit/architecture/test_layer_boundaries.py` 与依赖实测证实）：`presentation → application ← infrastructure`，`domain` 无内向依赖；`app/` 为组合根。

## 5. 依赖基线 [VERIFIED]

- 三层 requirements：`base.txt`（直接依赖，逐条注释）→ `dev.txt`（-base + 质量工具）→ `lock.txt`（全传递闭包 60+ 包全钉定，P2-001）
- dev 工具链：black 25.1 / ruff 0.12.7 / isort 6.0.1 / mypy 1.17.1 / pytest 8.4.1(+cov,qt) / pre-commit 4.3.0
- **缺 `.pre-commit-config.yaml`**（dev.txt 声明 pre-commit 但仓库根无配置文件）→ 见台账 AUD-007
- 无 lock 更新自动化；lock.txt 注释要求 base.txt 变更后手工刷新

## 6. 质量工具基线（本轮实测）[VERIFIED]

| 工具 | 命令 | 结果 |
|---|---|---|
| ruff 0.12.7 | `ruff check src tests main.py scripts tools` | **All checks passed** |
| mypy 1.17.1 | `mypy src` | **Success: no issues found in 258 source files** |
| pytest 8.4.1 | `python -m pytest -q`（全量） | **1310 passed / 6 skipped / 0 failed，250.55s** |
| pre-commit 4.3.0 | — | **未配置**（无 `.pre-commit-config.yaml`）→ Verification Not Executed（无可运行对象） |
| 构建检查 | `python -m build` 等 | 本轮未执行（避免副作用/耗时）→ Verification Not Executed，CI release.yml 承担 |

已知测试平台限制（来自 `.ai/KNOWN_ISSUES.md`，VERIFIED-文档在案）：LIMIT-004（特定子集顺序原生崩溃，仅本地调试）、LIMIT-006（macOS/Linux runner 概率性 SIGSEGV→CI 139 重试自愈 + 4 处 darwin skip）。本轮 Windows 本地全量无 skip 异常（6 skips 为既有门控/平台跳过）。

## 7. 测试体系基线 [VERIFIED]

- 规模：169 个测试文件 / 31,530 行测试代码（对比源码 28,887 行，测试:源码 ≈ 1.09:1）
- 分层：`tests/unit`（应用/域/基础设施/presentation/app/architecture）+ `tests/integration`（数据库迁移、导出、人脸识别 E2E、扫描/取消/压力、升级完整性、插件装载等）
- 架构守卫测试在案：`tests/unit/architecture/test_layer_boundaries.py`（分层 AST 断言 T-1）、`test_recognition_entry_migration.py`
- 覆盖率：仓库根有 `.coverage`（2026-09-13）；PROJECT_STATUS 记载覆盖率基线 92%（pytest-cov dev-only，不设门槛）[VERIFIED-文档]；本轮未重测覆盖率 → Verification Not Executed
- AI 集成测试使用真实模型包（`resources/models/buffalo_l` 在场，本轮实测通过）

## 8. CI / 发布基线 [VERIFIED]

- `ci.yml`: push(main)/PR/workflow_dispatch 触发；矩阵 ubuntu/windows/macos × py3.11；步骤 = 装依赖(dev.txt) → 模型缓存+sha256 校验下载 → （后续步骤含 lint/type/pytest，QT_QPA_PLATFORM=offscreen，PYTHONFAULTHANDLER=1，pytest exit 139 重试 ≤3）
- `release.yml`: tag `v*` 触发；sdist+wheel；Windows 安装包（PyInstaller 6.22.2 钉定 + Inno Setup，在线/离线双产物，模型包 sha256 fail-closed）
- 最近发布：v2.8.0（2026-09-13，run #31 三 job 全绿，PROJECT_STATUS 记载）[VERIFIED-文档，远端 run 状态本轮未核 → UNKNOWN]

## 9. 文档体系基线（SSOT 地图）

| SSOT | 职责 | 版本/更新日 | 状态 vs HEAD |
|---|---|---|---|
| `.ai/PROJECT_STATUS.md` | 当前运行状态唯一快照 | v1.34.1 / 2026-09-23 | **陈旧**：正文与 Next Step 停留在"阶段 A 完成、B–F 待立项"，而 HEAD 已含阶段 C/D/E/F 提交；§7 记载迁移链"001→002→003"，实际 alembic 已有 001–008 |
| `.ai/KNOWN_ISSUES.md` | 未解决问题 | v1.16.0 / 2026-09-21 | 无 Open issue；LIMIT-001/002/004/006 登记；LIMIT-006 在两张表中重复承载 |
| `.ai/ARCHITECTURE_DECISIONS.md` | ADR-031~041 | v1.2.0 / 2026-09-06（041 于 09-13 追记） | 无阶段 C–F 期间决策（D-3 兼容写入、E-SG-6、inclusive>= 等未见条目） |
| `.ai/DOCUMENT_INDEX.md` | 文档体系导航 | v1.3.1 / 2026-07-26 | 未登记 stage-f/calibration/evidence 新文档 |
| `docs/user-guide/manual.md` | 用户手册 | 覆盖至阶段 A/B | 聚类/配对工作台/重新分析/失败清单关键词 **0 命中**（本轮 grep 实测） |
| `CHANGELOG.md` | 用户可见变更摘要 | 止于 2.8.0 | 无 Unreleased 段 |
| `.ai/rules/audit-methodology.md` | 文档一致性审计方法论 SSOT | v1.0.1 | 本审计的严重度分级与其对齐（Critical/Major=真实矛盾、Minor=状态漂移） |

**仓库外文档资产**（VERIFIED，存在于 `D:\workFile\`）：`PhotoArchiver-BusinessReview\`（Stage1_BusinessFacts / Stage2_BusinessRules / Stage3_BusinessDiagrams / Stage4_FinalAudit / Stage4_1_FinalReview / Stage4_2_FinalFreezeReview 等 8 份，6 份更新于 2026-09-28）与 `photo-archiver\`（13 类文档目录，2026-07-01）。**均不在 git 仓库内、未提交**；其中 Stage4 系列为此前业务基线冻结审查的证据链。

## 10. 已知问题基线（审计出发点）

1. **Stage F 冻结审查史**（untracked 证据文档 + 仓库外 BusinessReview，VERIFIED-文件在案）：
   - `stage-f-acceptance-review.md`（对照 b3b8685）：CONDITIONAL PASS，登记 F-02~F-05 与 3 项冻结收口条件（SSOT 登记、Owner 裁决登记、端到端贯通回归）。
   - `stage-f-report-verification.md`（2026-09-28）：独立核验更严的 §1–§18 报告（判 FAIL / 0×P0 + 4×P1：F1-1 端到端回归未贯通、F1-2 match_threshold 校准缺失、F1-3 阶段收尾义务违约（文档体系全面滞后）、F1-4 废弃 Top-1 归档规则残留 3 载体），核验结论"真实可信"。
   - **HEAD 2823d1c 提交信息声称修复**：BLK-1（归档去重身份错误，migration 008）、BLK-5（位置配对置信度语义，confidence 可空三态）、BLK-2/3/4（Stage 文档事实错误）、D-1（人工操作结果为最终结果）、D-2 等"5 阻断项 + 2 裁决"。**修复完整性尚未独立复核** → Stage 2/4/5 逐项核验（NEEDS-VERIFICATION）。
2. **Owner 侧未决事项**（PROJECT_STATUS Next Step，VERIFIED-文档）：阶段 B 复审五点复验、v2.8.0 二轮真机验收、Release body 签核、A-1/A-3 决策等。
3. **平台限制**：LIMIT-006（macOS 概率性原生崩溃，不可仓内修复，owner 裁决维持现状）、LIMIT-001/002/004。

## 11. 审计范围（Stage 1–9 映射）

| Stage | 对象 | 本仓库映射 |
|---|---|---|
| 1 架构 | 分层/依赖方向/边界 | src/photo_archiver 五层 + app 组合根 + test_layer_boundaries |
| 2 业务逻辑 | 导入→扫描→识别→聚类→配对→审核→归档→导出→删除→搜索→插件→设置→迁移→恢复 | application/commands+services、domain、presentation 控制器、workers |
| 3 数据 | SQLite schema、alembic 001–008、17 个 sqlite 仓储、backup/integrity | infrastructure/database、alembic/versions |
| 4 测试 | 169 文件质量、真实覆盖、假完成识别 | tests/ |
| 5 文档 | .ai/ 四文档+rules、docs/ 全树、CHANGELOG、README 与代码一致性 | 见 §9 |
| 6 可靠性 | 异常/重试/取消/并发（TaskCoordinator、qt_executor）、性能、安全 | workers/、任务生命周期、exporters 安全 |
| 7 UI | PySide6 21 views、状态一致性、假按钮/半实现 | presentation/views + controllers |
| 8 交叉 | 需求↔代码↔测试↔文档↔DB↔Git↔发布 矩阵 | 全部 |
| 9 综合 | 统一健康账本 | FINDINGS_LEDGER + FINAL_HEALTH_CHECK |

**业务功能存在性预判**（Stage 2 逐项确认，N/A 标记延后）：Import/Scan/Recognition/Cluster/Pairing/Match/Review/Archive/Export/Delete/Search/Filter/Batch/Task/Plugin/Settings/Migration/Recovery 均有对应 commands/services/控制器入口；无 Web/API 层（桌面单体）。

## 12. 审计限制（未执行验证登记）

| 项 | 原因 | 影响 |
|---|---|---|
| 远端 CI run 状态 | 未访问 GitHub（只读审计范围；44 提交未推送亦无从触发） | HEAD 质量结论仅基于本地复现 |
| 真实 GUI 运行 | READ-ONLY 审计不启动桌面应用（会在 %LOCALAPPDATA% 产生运行时数据） | Stage 7 UI 结论基于测试+代码行为分析 |
| 覆盖率重测 | 耗时且 92% 为既有登记基线 | Stage 4 以"盲区清单"代替百分比 |
| `python -m build` 打包验证 | 副作用大、CI 承担 | 发布产物↔源码一致性在 Stage 8 以配置/工作流静态核对 |
| 性能复测（476→116ms 等） | 属 Stage 6 专项 | 本阶段仅登记声明值 |

## 13. 未知项 [UNKNOWN]

1. 44 个未推送提交是否曾推送到其他远端/分支（本地不可证）。
2. `%LOCALAPPDATA%` 生产运行库的当前状态（迁移版本、数据规模）——Stage 3 只能以代码+测试推断。
3. v2.8.0 安装包二轮真机验收是否已执行（PROJECT_STATUS 记为待 owner，此后无记录）。
4. 仓库外 `D:\workFile\photo-archiver\`（2026-07-01）文档集与仓库现状的偏离度——Stage 5 抽查。
5. Stage-F 审查报告 §1–§18 原文（判 FAIL 版）"仅存在于会话中，未落盘"（per stage-f-report-verification.md）——其内容只能经由核验记录间接引用。

---

> 本文件为 Stage 0 唯一交付物；问题台账见同目录 `FINDINGS_LEDGER.md`。Stage 1 待指令后开始。
