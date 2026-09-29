# TEST_QUALITY_AUDIT.md — 全面工程健康审计 · 测试体系审计（Stage 4）

- **审计日期**: 2026-09-28 ｜ 对象: HEAD `2823d1c` ｜ 性质: READ-ONLY
- **方法**: 结构统计（AST/文本扫描 169 文件）+ 全量套件两跑（250.55s / 263.36s，均 1310 passed / 6 skipped）+ 本轮覆盖率实测（JSON 证据 `evidence/coverage_stage4.json`）+ 抽样读码核验断言质量

---

## 1. 测试体系结构 [VERIFIED]

- 规模：169 个测试文件 / 31,530 行（测试:源码 ≈ 1.09:1）；1310 用例 + 6 skip。
- 分布：presentation 44 ｜ application 35 ｜ integration 24（+子目录 export 4 / face_detection 4 / database 1）｜ infrastructure 系 24 ｜ domain 9 ｜ plugins 4 ｜ app 4 ｜ workers 3 ｜ architecture 2 ｜ scripts 2。
- 分层齐全：unit（六层全覆盖）/ integration（真实 SQLite、真实 Executor+UoW、pytest-qt 无头、**subprocess 进程级** CLI/路径锚定/cwd 变更）/ 架构守卫 / 迁移专项 / 1000–2000 张级压测（PA_STRESS 门控）。
- 共享 fixture 极少（根 conftest 仅 34 行）——测试自包含，无隐式共享状态。

## 2. 质量正面结论 [VERIFIED]

1. **零零断言文件**（AST 全扫）；mock 密度低（仅 `test_archive_planner.py` 因仓储替身偏高，合理）。
2. **行为级断言样本**（抽验 `test_review_dialog_review_board.py`）：文案含精确数值、按钮计数、确认门控（No→`bulk_approve` 零调用）、`assert_called_once_with(expected_ids, None)`——断言业务行为而非实现细节（少量布局序断言为 Qt 特性务实取舍）。
3. **真实感 e2e**：`test_step11_archive_e2e.py` 用真实 ArchivePlanner+Executor+SQLiteUnitOfWork+磁盘文件（6 场景含 dry-run/skip/重跑）；CLI 走 subprocess 进程级（`test_cli_entrypoint.py`、`test_path_anchoring_process_level.py`、`test_cwd_change_process_level.py`）。
4. **确定性生命周期套件**：`test_stage_f_lifecycle.py`（1200 张：全量完成/中途取消持久化/取消后重试/反复取消重试/坏图隔离）——直接覆盖任务书要求的取消/重试/恢复场景。
5. **守卫三件套常驻 CI**：分层 AST 断言（T-1）、迁移 13 项（含幂等/回滚/CRUD-after-migration）、repository Protocol 接受性。
6. skip 全部为显式平台/环境门控（darwin LIMIT-006 豁免机制、PA_STRESS 专用 job、win32 junction、openpyxl/Pillow 存在性），reason 字段完整。
7. 时序依赖可控：`time.sleep`/`qWait` 全仓仅 6 处且各有正当理由（stress 轮询、Windows sqlite 连接释放、故意锁保持、慢速替身）；本轮两跑 + Stage 0 一跑共三次全绿，无 flaky 复现。

## 3. 覆盖率实测 [VERIFIED]

**总量 93.2%**（10,363/11,115 行，752 missing；与登记基线 92% 一致）。核心业务文件：

| 文件 | 覆盖 | | 文件 | 覆盖 |
|---|---|---|---|---|
| archive_planner / export_service / match_persons / review_recognition / recognition_failure / workspace_readiness | **100%** | | pairing_workbench_service | 89.8%（14 行缺口=校验 raise+score 钳制） |
| archive_executor | 91.7% | | workers/application_tasks | **74.1%**（30 行缺口=任务回退/错误分支 5 簇） |
| task_coordinator | 99.1% | | model_deployment | 66.7%（网络下载失败路径） |
| main_window（746 语句） | 90.8% | | sqlite_face_cluster_repository | 76.1% |

### 高价值盲区清单（按风险排序）

1. **F1-1 全链贯通回归缺失**（承 AUD-004）：两段式导入（Parse→Confirm）→配对确认（PairingWorkbench.confirm）→ArchiveExecutor.execute 无单条测试串联；`tools/validate_stage_f.py:272-355` 直造名单且止于 plan()。各段分别有测试，段间接缝无回归网。
2. **workers 错误路径**（AUD-019）：`application_tasks.py` 30 行未覆盖——use_case 无 `bind_progress_reporter` 时的回退分支、ImportConfirmTask 等 5 个任务包装器的异常/回滚分支。>500 行导入确认走 Worker（CONFIRM_SYNC_LIMIT），这些分支失败时的 UI 终态行为未经行为验证。
3. **配对服务守卫分支**（并入 AUD-019）：并发删除 ValidationError、score 钳制 `max(0.0, min(1.0, …))`（`pairing_workbench_service.py:67,124,146,164,169,193,216,243,251,257,262,265`）未测——Stage 2 确认这些守卫存在但无回归网。
4. **模型下载失败路径**（model_deployment 66.7%）：sha256 fail-closed 的失败分支主要靠 CI 下载脚本间接验证。
5. **平台盲区（在案接受）**：darwin 4 组 skip（AR-01/LIMIT-006）——macOS 上扫描/取消一致性、stress 套件零执行。
6. **覆盖范围声明**：`main.py`（根 CLI，~800 行）不在 `--cov=src` 范围，仅 subprocess 级覆盖（AUD-021）；`tools/` 与 `scripts/` 未纳入（开发工具，可接受但应明示）。

## 4. 发现

- **AUD-019（P2）错误/守卫路径测试缺口**：workers 任务包装器错误分支（74.1%）+ 配对服务并发删除/钳制守卫（14 行）无行为测试。触发条件：任务执行中异常、确认期间并发修改。影响：错误路径回归无网，可靠性主张部分依赖代码审读。
- **AUD-020（P3）**：`test_repository_contracts.py` 名实不符——名为"契约对等"实为**类型级**（Protocol 接受性）检查（`:112,126,139`），InMemory 替身与 SQL 实现的行为一致性依赖各 repo 自测散点，无统一对等套件（roster 排序契约曾靠手工补齐，PROJECT_STATUS 在案）。
- **AUD-021（P3）**：`main.py` 与 `tools/`/`scripts/` 在覆盖率统计范围外且无声明——覆盖率 93.2% 的分母是 `src/photo_archiver`，不含根入口 CLI。

## 5. 结论

测试体系**质量高于数量**：真实感高、断言行为级、守卫常驻、生命周期确定性覆盖、零 flaky 证据。缺口集中在**错误/守卫分支**（workers、配对服务）与**段间全链贯通**（F1-1），均为可机械补齐的回归网问题，不影响现有绿盘的可信度。
