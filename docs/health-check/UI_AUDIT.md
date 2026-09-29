# UI_AUDIT.md — 全面工程健康审计 · UI / Presentation 审计（Stage 7）

- **审计日期**: 2026-09-28 ｜ 对象: HEAD `2823d1c` ｜ 性质: READ-ONLY（未启动 GUI；以代码行为 + 44 个 presentation 测试文件 + 集成闭环测试为证据）
- **范围**: presentation 层 13 控制器 + 21 视图 + task_coordinator；UI 状态来源、刷新汇聚、交互防御、假按钮/半实现、错误呈现

---

## 1. UI 状态来源 [VERIFIED]

- **就绪快照模式**：UI 动作可用性来自 `WorkspaceReadinessService` 单查询快照（七字段），经 `WorkspaceController` 翻译为 enabled/tooltip/next_action；Widget 零仓储访问（项目自设规则，`test_main_window_workspace_state.py` 11+ 项 + 新增分级行为 2 项佐证）。
- **快照刷新时机**：启动（`main_window.py:252`）、任务终态、审核/设置对话框返回、结构变化（`people_changed` 信号分级——纯顺序变化不级联，AR-05 口径）。
- **过期状态风险**：终态刷新按任务名分派且**失败/取消的任务也刷新**（`_refresh_task_results:955` 注释"Failed/called tasks may already have persisted a partial batch"）——与 Stage F 的"取消持久部分观测"语义闭环。未发现"操作完成但 UI 未刷新"通路。

## 2. 刷新汇聚 [VERIFIED]

| 汇聚点 | 覆盖 |
|---|---|
| `_on_terminal` → `_refresh_task_results(task_name)` | 全任务刷照片墙；import_people/import_confirm 刷人员轴（带 QSignalBlocker 防瞬态筛选）；match/run_recognition 刷审核队列；face_clustering 刷聚类页；恒刷工作区快照 |
| 对话框返回 | 审核/设置/归档根询问关闭后同轮 `_refresh_workspace_state`（+照片墙）；导入预览确认后经任务终态或同步路径刷新（`test_second_import_refreshes_the_people_page_without_restart` 佐证） |
| 设置重入 | Batch 6 方案：归档根缺失询问**在既有预约内**内联打开设置（`_open_settings_dialog`），显式注释避开嵌套 `@_exclusive` 死锁；返回即重探测 |

## 3. 交互防御 [VERIFIED]

- **双击/重复点击**：`@_exclusive(label)` 装饰器 = 任务预约准入，二次点击被拒并显示 `STATUS_TASK_BUSY`（`main_window.py:193-211`）；模态对话框 `exec()` 天然串行化。
- **GUI 边界异常网**：装饰器内 `except Exception` → `logger.exception` + 状态栏 + `QMessageBox.warning` + finally 释放预约——**无异常吞没**（32 个 except 块逐一核查：无一 `pass`；11 处启发式命中均为自定义 `_warn` UI 呈现或文档化降级）。
- **取消**：状态栏常驻 QToolButton（objectName="CancelTask"，QAction 契约，带 accessible name）；coordinator `cancelling` 标志保证一次请求；终态前保持准入（Stage 6 全景）。
- **窗口重开/重启**：用户偏好经 QSettings（`qsettings_user_settings_store`，infrastructure/persistence 声明位）；启动即刷工作区快照。
- **降级路径（文档化）**：缩略图单张失败→无图标不崩溃（`photo_list_controller.py:59-64`，finally 释放 in-flight）；扫描预枚举 OSError→拒绝原因入 controller 状态（`scan_controller.py:71-75`）。

## 4. 假按钮 / 半实现排查 [VERIFIED]

- **按钮接线全查**：10 个视图文件 QPushButton/QToolButton 与 `.clicked.connect` 逐一比对——全部接线（含 next-step 双按钮的循环接线 `main_window.py:501`、空态 CTA、取消按钮的 `setDefaultAction(QAction)`）。
- **CURRENT_BATCH**：已从导出对话框移除（Batch 6，owner 决策"不以禁用单选框伪装功能"）；服务层契约 fail-closed raise——**无伪装入口**。
- **筛选占位**：NEXT_PHASE 计划记载的"人员轴/日期轴禁用占位"已于后续批次实装（现 FilterBar 三轴可用，`test_filter_criteria_combinations.py` 佐证）。
- **错误呈现**：任务失败 → TaskFailed → coordinator 终态 → `_on_failed` 模态反馈（终态期间保持预约）；服务级校验错误 → 对话框 `_warn` 中文文案（阶段 B 复审修复项）。

## 5. 发现

- **AUD-025（P3）审核队列读侧失败静默渲染为空队列**：`review_dialog.py:313-317` `except Exception: return []`（注释"UI must not fail on a read-side stub"）——DB 读失败时用户看到"0 条待审核"而非错误提示，与真实空队列不可区分。降级设计本身合理（对话框不应因读失败崩溃），但缺"读取失败"状态区分。触发条件：审核打开瞬间读库异常（锁超时/IO 错误）。影响：用户误判"没有待审核项"。
- **正面**：无假按钮、无半实现伪装、无异常吞没；UI 状态全部可追溯到后端快照；刷新路径闭环且有测试锚点。

## 6. 用户工作流逐条验证（测试佐证链）

| 工作流 | 链路证据 |
|---|---|
| 两段式导入 | `test_excel_import_ui_closed_loop.py`（真实 .xlsx → 预览 → 确认 → 页面免重启刷新、批次列更新）|
| 扫描 | `test_scan_and_register_workflow.py` + `test_scan_cancel_consistency.py`（取消后库态一致）+ single-flight |
| 识别 | `test_recognition_run_controller.py` + `test_match_ui_wiring.py` + 识别任务终态刷新 |
| 审核 | `test_review_dialog_review_board.py`（11 项行为断言）+ D-1 身份选择器（Stage 2 全链核验）|
| 归档 | `test_step11_archive_e2e.py`（真实 Executor）+ 控制器 preview→execute 路径 + 试运行默认勾选 |
| 聚类/配对 | `test_cluster_faces_controller.py` / pairing_workbench_dialog 刷新模式 + D4 UI 入口（c543828）|
| 导出 | `test_export_ui_closed_loop.py` + `test_export_scope_integration.py`（CURRENT_BATCH fail-closed）|
| 删除人员/登记 | `test_people_admin_flow.py`（重开库持久 + 级联语义）+ 确认对话框预选/焦点 |

**结论**：UI 层质量与其测试覆盖（44 文件，presentation 为最大测试域）匹配；唯一新发现为 AUD-025 一处降级语义区分缺失。
