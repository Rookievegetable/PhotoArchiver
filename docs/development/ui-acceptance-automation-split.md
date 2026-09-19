# UI/UX 验收脚本自动化切分（companion to ui-acceptance-script.md）

> 基线：HEAD `6a8fd73`（UI/UX Batch 7）。本文把 `ui-acceptance-script.md` §0–§10
> 的每个验收步骤切分为两类：
>
> - **Part A — 可脚本自动化**：断言对象是文案、状态、计数、enabled/visible、
>   文件落盘等**可编程判定的行为事实**，可在 pytest-qt（offscreen）或集成测试
>   中无人值守执行。
> - **Part B — 必须人工判断**：断言对象是**真实视觉观感、真实缩放/主题矩阵、
>   真实操作流畅性或环境特异性行为**，自动化无法给出可信判定。
>
> 切分同时标注每个自动化项的**当前状态**：
> `已锁定`（现有测试已覆盖，1036 passed 实测全绿）/ `待补自动化`（行为可由脚本
> 判定但当前无测试锁定，属 AUDIT-UI-002 防线缺口）。
>
> 关联审计结论：AUDIT-UI-001（QSS `palette.X` 点语法致视觉层级失效）证明
> "按钮高亮/危险红/焦点环"类断言**不能靠字符串测试**，要么进 Part B 人工确认，
> 要么用渲染级探针自动化（见 §A.7）。

---

## Part A — 可脚本自动化执行

### A.1 §1 空库首次使用（除视觉高亮外全部可自动化）

| 验收步骤 | 自动化断言点 | 状态 |
|---|---|---|
| 默认落在「概览」页 | `_nav_list.currentRow()==0` 且 `_pages.currentIndex()==0` | 已锁定（test_main_window_navigation） |
| 五步检查清单内容与 ✓/○ 标记 | 五个 step label 文本含步骤名与状态标记 | 已锁定（test_overview_presenter） |
| 唯一主 CTA 指向「导入人员」 | `OverviewModel.primary == "import"` 且按钮 label/可见 | 已锁定（test_overview_presenter） |
| 底部本地处理/不上传说明 | privacy label 文本存在 | 已锁定（overview page 构造断言） |
| 照片库空态："库中还没有照片"+扫描 CTA；无"筛选无结果"文案；无批量按钮 | `_photo_list_stack.currentIndex()==1`；空态按钮可见；批量栏 `isVisible()==False` | 已锁定（test_photo_library_page） |

### A.2 §2 导入人员（就绪状态机）

| 验收步骤 | 自动化断言点 | 状态 |
|---|---|---|
| 导入完成后清单"导入人员"变 ✓、CTA 切换「扫描照片」 | 注入导入终态后 `OverviewModel` 步骤 done 标记与 primary=="scan" | 已锁定（test_overview_presenter 五态矩阵） |
| 识别按钮置灰 + 缺照片原因 + 「下一步」直达扫描 | `match_guidance().enabled==False`、tooltip 文案、next_action=="scan"、按钮点击路由 | 已锁定（test_workspace_controller / test_main_window_workspace_state） |
| 真实 Excel 导入闭环 | 集成测试真实 service+DB | 已锁定（test_excel_import_ui_closed_loop） |

### A.3 §3 扫描→识别（任务协调与取消）

| 验收步骤 | 自动化断言点 | 状态 |
|---|---|---|
| 运行期间冲突入口置灰 + tooltip 说明原因 | `_conflicting_actions` 全部 disabled 且 tooltip 含当前任务名 | 已锁定（test_main_window_task_coordination / test_main_window_navigation） |
| 「取消任务」按钮可见、仅 busy 时可用 | CancelTask 按钮存在、enabled==can_cancel、accessibleName | 已锁定（test_visual_system / test_main_window_workspace_state） |
| 取消语义："当前处理单元完成后停止，已完成部分保留" | 取消后终态= cancelled、状态文案、已持久化部分仍在库 | 已锁定（test_cancellation_and_ux / test_scan_cancellation） |
| 终态后按钮恢复 + 概览计数与照片库同步刷新 | 五任务 × 三终态的刷新断言（真实 SQLite） | 已锁定（test_task_terminal_refresh，15 项） |
| 进度显示（已知总数百分比 / 未知总数不伪造） | QProgressBar range/value 与状态文本 | 已锁定（task coordination 套件） |

### A.4 §4 审核中心（除缩略图实拍外全部可自动化）

| 验收步骤 | 自动化断言点 | 状态 |
|---|---|---|
| 文字角标四态（非仅颜色） | `STATUS_BADGE_ROLE` 文本值 + delegate 绘制分支 | 已锁定（test_photo_thumbnail_rendering / test_visual_system） |
| 顶部"待审核 N 条"常驻 | header label 文本与布局序 | 已锁定（test_review_dialog_review_board） |
| 两行格式：文件名+人员名 / 置信度文字分级（含精确值）+ 状态 | 行文本断言、confidence_band 边界矩阵 | 已锁定（同上，11 项） |
| 选中 2 条 → 按钮显示（2） | 按钮计数随选区实时更新 | 已锁定（同上） |
| 「全部通过（N）」确认：数量+无批量撤销说明、默认"否"、回车不改数据 | monkeypatch 确认框返回 No → `bulk_approve` 零调用 | 已锁定（同上） |
| 点"是"后列表清空且对话框保持打开显示空态 | 队列刷新 + `isVisible` + 空态文案 | 已锁定（test_review_dialog_empty_queue） |
| 关闭后照片墙角标同步为「已通过」 | 对话框返回后 `_refresh_photo_list` 重查断言 | 已锁定（集成/窗口级测试） |
| 行缩略图经异步安全通道到达 | 注入替身源：逐行请求、到达聚合、None 降级 | 已锁定（review_board 缩略图通道断言） |

### A.5 §5 筛选与空态区分

| 验收步骤 | 自动化断言点 | 状态 |
|---|---|---|
| "全部时间"隐藏起止 / "自定义时间"展开 | 时间模式切换下起止编辑 `isVisible()` | 已锁定（test_filter_bar） |
| from>to → 拦截发 criteria + 内联提示、不渲染空结果 | 无 criteria_changed 发出、warning label 可见、摘要保持旧值 | 已锁定（test_filter_bar） |

### A.7 §6/§8 视觉样式断言的"特殊自动化"（渲染级探针）

按钮高亮、危险红、焦点环属于**可自动化但当前未自动化**项（AUDIT-UI-002）：
断言方式不是字符串包含，而是离屏渲染 + 像素采样（`QWidget.render` →
`QImage.pixelColor`），或 `qInstallMessageHandler` 捕获
`Could not parse application stylesheet` 警告归零。审计探针
`logs/audit_ui001/probe3.py` 已给出可直接转化为测试的参考实现（FIXED sheet
矩阵：primary 命中 Highlight、danger 命中 hex、disabled 命中 Button）。

> **状态更新（2026-09-19，`3d2e71d` AUDIT-UI-001/002 修复）**：下列三项已由
> `tests/unit/presentation/test_visual_system.py` 的渲染探针锁定（解析警告
> 捕获 + 像素采样 + 负向对照），不再是"待补自动化"。可经
> `python scripts/ui_acceptance_automation.py` 作为 Part A 一部分无人值守执行。

| 验收步骤 | 自动化断言点 | 状态 |
|---|---|---|
| 主 CTA「蓝色高亮」 | 渲染 primary 按钮中心像素 == palette(Highlight) | 已锁定（test_render_primary_differs_from_normal_button） |
| 「开始归档」/删除确认红色危险样式 | 渲染 danger 按钮中心像素 == #c62828 | 已锁定（test_render_danger_paints_the_danger_color） |
| 焦点环 2px Highlight 边框 | 聚焦控件边框像素采样 | 已锁定（test_render_focus_ring_is_visible） |

### A.8 §7 筛选导出

| 验收步骤 | 自动化断言点 | 状态 |
|---|---|---|
| 范围列表无「当前批次」 | `ExportScope.CURRENT_BATCH not in _scope_radios` | 已锁定（test_export_ui_wiring） |
| FILTERED 显示当前筛选摘要+预计数量 | hint label 文本含 summary/count | 已锁定（同上） |
| 全部 / 按当前筛选各导出一次，行数核对 | tmp 路径真实导出 + 行数断言 | 已锁定（test_export_ui_closed_loop / test_export_scope_integration） |

### A.9 §8 危险操作确认

| 验收步骤 | 自动化断言点 | 状态 |
|---|---|---|
| 移除登记确认：级联数量+"磁盘文件永远不碰"+"无撤销"、默认焦点「取消」、回车不删除 | 文案断言 + Cancel isDefault + OK danger role | 已锁定（test_deletion_ui_dialogs / test_visual_system） |
| 删除人员：默认焦点「取消」+ 红色；取消后无变化 | 同上模式 | 已锁定（同上） |
| 检测重复只读报告、无确认即无写入 | disposal 未调用断言 | 已锁定（test_detect_duplicates_disposal） |

### A.10 §10 质量门

`ruff check`、`mypy src`、全量 `pytest` —— 天然自动化（CI 已执行；本轮实测
1036 passed / 6 skipped / 0 failed，232.75s）。

---

## Part B — 必须人工判断执行

| 脚本位置 | 人工验收项 | 为什么自动化不能判定 |
|---|---|---|
| §0/§1/§6 | **100% / 125% / 150% Windows 真实缩放**下的空库首用与归档确认抽查：文字不截断、布局不重叠、CTA/角标可读 | Qt6 原生缩放只在真实桌面合成器下发生；offscreen 渲染无法暴露 DPI 取整、物理像素对齐与真实字体光栅化问题 |
| §0/§1/§6 | **浅色 / 深色真实系统主题**下主 CTA、正文、状态角标、确认按钮的可读性（对比度） | palette 驱动配色只在真实主题切换时生效；对比度"可读"是主观判定；像素探针可验证"颜色生效"但不能判定"可读" |
| §1 | 主 CTA 高亮、危险按钮红色、焦点环在**真实屏幕上的最终视觉确认**（配合 A.7 探针） | 探针在 offscreen/windows11 验证机制正确性；真实显示器、真实主题、真实缩放下的观感必须人眼确认。**当前 AUDIT-UI-001 未修复时本项必然失败** |
| §3 | 扫描/识别进度"实时显示"的**流畅性与真实性**；真实大目录下点取消后的实际响应时延（LIMIT-002 任务边界粒度） | 自动化断言的是状态值；"实时/流畅"与时延体感依赖真实线程、真实磁盘、真实数据量 |
| §4 | 审核列表缩略图小图的**真实渲染观感**（非占位、不错位、随行刷新） | 异步缩略图到达的真实时序 + 视觉正确性；自动化只锁定"信号聚合到正确行"的机制 |
| §6 | 试运行/正式归档后**真实文件系统核对**（文件管理器确认落盘结构、试运行零新文件） | 集成测试在 tmp 目录已覆盖语义；但验收要求的是真实目标盘上的端到端确认（含权限/杀毒软件等真实环境变量） |
| §8 | 危险确认对话框在真实桌面的**默认焦点观感**（回车安全）——机制已自动化，真实焦点可视反馈需人工抽查 | 焦点环在真实主题下的可见性（与 AUDIT-UI-001 焦点环失效直接相关） |
| §9 | LIMIT-001 真实缺模型环境链路（改名模型目录后启动识别观察友好失败） | 依赖真实缺模型环境，CI 原则性不覆盖 |
| §9 | macOS 实验性支持的抽查（LIMIT-006 概率性崩溃如实记录） | 平台特异性，Windows CI 无法覆盖 |
| 全脚本 | **"非开发者能否照脚本独立走通"**这一可用性结论本身 | 验收的本质目的；脚本文案是否足够无歧义只能由真实验收人验证 |

---

## 执行建议

1. Part A 已锁定项直接由 CI 承担，无需重复人工执行；人工验收只跑 Part B
   + A.7 修复后的抽查（DV-01/DV-02 等效项）。
2. **前置阻断已解除**（2026-09-19，`3d2e71d`）：AUDIT-UI-001 已修复且渲染级
   探针入测试（见 A.7 状态更新），Part B 的视觉确认项可正常安排人工验收。
   Part A 全部章节可由 `python scripts/ui_acceptance_automation.py`
   无人值守执行并按章节聚合判定。
3. Part B 执行时必须记录环境（Windows 版本 / 缩放比例 / 主题），与脚本
   §0 的验收记录要求一致。

| 无结果组合 → 空态"没有照片符合当前筛选条件"+「清除筛选」 | stack index==2 且 CTA 为清除 | 已锁定（test_photo_library_page） |
| 筛选摘要 + 结果计数 | `summary_text` / `set_result_count` 回填断言 | 已锁定（test_filter_bar） |
| 选中 N → 「归档所选（N）/ 移除登记（N）」、取消选中整栏消失 | 批量栏文本计数与可见性随 selectionChanged | 已锁定（test_photo_library_page） |

### A.6 §6 归档安全表达（含真实落盘，均可自动化）

| 验收步骤 | 自动化断言点 | 状态 |
|---|---|---|
| 预览首行"已选 N 张 / 全部已通过" | scope label 文本 | 已锁定（test_archive_export_safety） |
| 计划/跳过数量、按人员分组、前 8 条源→目标示例+截断说明 | 表单行与 `_sample_list` 内容 | 已锁定（同上） |
| 冲突策略切换 → 后果说明文字更新 | hint label 随 combo 切换 | 已锁定（同上） |
| 试运行默认勾选、按钮「执行试运行」为默认 | `_dry_run_check.isChecked()`、accept 按钮文案/default | 已锁定（同上 + test_visual_system） |
| 取消勾选 → 「开始归档」+ 默认焦点「取消」，回车不写盘 | 按钮文案切换、Cancel isDefault、role 切换 danger | 已锁定（文案/焦点/role） |
| 试运行后库不变、磁盘无新文件；正式执行按 `{根}/{人员}/{日期}/{原名}` 落盘、角标追加「已归档」 | tmp 目录端到端执行 + 文件树断言 + DB 状态断言 | 已锁定（归档集成测试） |
| 清空归档根 → 询问「去设置」直达设置页 | monkeypatch 确认框选 Yes → SettingsDialog 被打开 | 已锁定（test_archive_export_safety） |
