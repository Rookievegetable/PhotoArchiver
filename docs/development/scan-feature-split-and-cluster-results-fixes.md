# 任务书：识别流程两段式拆分 + 聚类结果界面两项修复

- 日期：2026-10-28
- 状态：**实施完成（2026-10-29），全门禁绿，待提交裁决**
- 授权：Owner 对方案批复「按推荐」（2026-10-28，会话内），D1–D6 全部按推荐项执行。
- 方案全文见会话记录；本任务书为实施契约，含裁决、设计与验收。

## 0. 实施记录（2026-10-29）

- **门禁终态**：全量串行 pytest **2012 passed / 8 skipped / 0 failed**（含集成）；ruff 全绿；mypy 全绿（299 文件）。
- **实施偏差（均在授权范围内）**：
  - 新增 `cluster_range_dialog.py`（D2 五档弹窗，默认 [1]）；`RecognitionScopeDialog` 及其测试退役（D1）。
  - 「记住上次范围选择」确认记 backlog（§7）。
- **实施中发现并修复的既有缺陷**：
  1. `main_window._build_controllers` 曾仍把旧扫描服务装给 ScanController（组合任务收到的结果缺 `scan` 字段 → 任务失败）——已改挂 `scan_register_analyze`。
  2. `_DecodeDispatcher` 单例无父对象，pytest-qt 时序下其 C++ 对象被回收 → worker 线程 emit 报 "Signal source has been deleted"（真宿主路径可演化为 access violation）——已挂 `QCoreApplication.instance()` 为父（生命周期与应用一致）。
- **PySide6 6.11.1 + pytest-qt 拆除时序竞态（记录备查）**：在飞高清解码任务 × 详图 `deleteLater` × 测试体结束后的事件处理组合，可触发原生崩溃（access violation）；独立脚本/生产事件循环复现不出、仅 pytest 真宿主路径复现，且与导航控件布局方式无关（QGridLayout 重叠/平铺/子控件定位均同）。处置：P6 关闭路径断言测试在体内 `qtbot.wait(100)` 让解码与延迟销毁沉降；详图覆盖控件改用预览 QLabel 子控件 + `setGeometry` 定位（不用 QGridLayout 重叠单元），样式迁入 `visual_style.py` 单源（`NavOverlayButton`/`NavPositionLabel` 选择器，`test_no_widget_scatters_setstylesheet` 守卫通过）。

## 1. 裁决表（Owner 已批，均按推荐项）

| # | 决策点 | 裁决 |
|---|---|---|
| D1 | 旧「运行人脸识别」主工具栏入口 | **移除**；数据工具页新增「重新分析全部照片」维护入口（模型/算法升级用，走既有 RecognitionRunController 全库路径） |
| D2 | 聚类脸数范围 UI 与默认 | 运行聚类前轻量弹窗（复用五档预设 [1][2-3][4-5][6-10][11+]），**默认 [1]**（与历史口径一致，防重聚类漂移）；「记住上次选择」记 backlog |
| D3 | 修复 1 路径 | **A3：聚类完成后自动生成建议**（名单非空时调用既有 SuggestPairingsService）；「生成建议」按钮保留 |
| D4 | 修复 2 布局 | **B1 覆盖式**：高清预览框左右中间叠放 ‹ › 按钮 + "第 x/y 张"计数 + 键盘 ←/→ |
| D5 | 聚类数据集实现 | **零迁移**：`FaceClusterRun.parameters` 快照记 `dataset='library'` 与 `face_count_ranges`；锚点 `recognition_run_id` = 发起聚类时所选运行（控制器/页面接线不变） |
| D6 | 兼容审核行随扫描生成的范围口径 | 扫描期默认 **[1]**（合影不入审核队列，与 Owner 现行实践一致） |

## 2. 现状事实（基线 = 本任务书落盘时工作树）

- 扫描文件夹 = 仅登记/对账，无特征提取：`application/services/scan_and_register_photos_service.py`。
- 运行人脸识别 = 范围对话框 → `RecognitionRunController.start_run` → `RunRecognitionService.execute`：**每次全库重新检测+嵌入**；观测/快照/兼容审核行落库（`run_recognition_service.py:57-141`，兼容行 `:165-169`）。
- 运行人脸聚类 = `ClusterFacesService.execute`：只读**所选运行**观测，参与过滤 = 存储 `scope_verdict == in_selected_scope` 且嵌入有效（`cluster_faces_service.py:245-251`）。
- 生成建议 = `SuggestPairingsService`：样本匹配 → 剩余簇（sort_key 序）× 剩余人员（roster_order 序）位置配对 → C-2 准入（auto_confirmed / suggested）；观测查找回 **锚点运行** `list_by_run`（`suggest_pairings_service.py:115-120`）。
- 聚类结果左列表人名 = 有效指派名，无指派 → "未匹配"（`cluster_results_dialog.py:414-427`）；`CLUSTER_ENTRY_PHOTOS = "第 {ordinal} 组 · {person} · {photos} 照片/{faces} 脸"`（`ui_text.py:670`）。
- 上一张/下一张按钮常驻右侧面板、P6 仅详图打开时启用（`cluster_results_dialog.py:221-230,916-921`）；详图 = 非模态 `PhotoDetailDialog`，宿主经 `replace_photo` 驱动（`photo_detail_dialog.py:264`）。
- `face_observations` UNIQUE(run_id, photo_id, face_index)；`scope_verdict` CHECK 仅两值（migration 004）。
- `FaceClusterRun.parameters` JSON 写入并**回读**（`sqlite_mappers.py face_cluster_run_from_row`）——dataset 标记设计可行。
- workspace：`pending_match_count` = 无任何识别行的照片数（NOT EXISTS）；概览第 3 步与主 CTA 挂 `match_guidance`（要求 has_persons + 模型可用）。

## 3. 阶段 A：扫描 = 登记 + 特征提取；聚类 = 全库特征分类

### A1 扫描组合服务

- 新增 `application/services/scan_register_analyze_service.py`：组合既有 `ScanAndRegisterPhotosService` + `RunRecognitionUseCase`（可为 None=模型缺失）。
- `execute(command)`：登记段（原服务原逻辑，结果 DTO **加列** `registered_photo_ids` / `updated_photo_ids`，默认 `()` 向后兼容）→ 计算增量集 → 分析段。
- **增量集** = `registered ∪ updated ∪ {已登记照片中最近处理结果 ∈ (unreadable, error, not_processed, 未知) 的照片}`；"最近处理结果"按运行 created_at 降序首个含该照片的 run_photos 行判定（与 A3 resolver 同规则，共享实现）。
- 分析段 = `RunRecognitionService.execute(StartRecognitionRunCommand(photo_ids=增量集…))`，parameters 记 `photo_scope="scan"` + 来源文件夹名；**每次扫描产生一个 RecognitionRun**（审计单元不变）；兼容审核行逻辑随迁（D6：范围 [1]）。
- 模型缺失（use_case None）：仅登记，状态明示"未提取特征"，不算失败——增量规则使装好模型后的下次扫描自动补齐。
- `cancel()`：转发分析段 `RunRecognitionService.cancel()`；登记段不设取消点（快）。
- 新 worker 任务 `ScanRegisterAnalyzeTask`（task 名 `scan_photos`，标签"扫描"沿用/调整），进度两段式（登记 x/y → 特征 x/y）。

### A2 聚类数据集 resolver（共享组件）

- 新增 `application/services/cluster_dataset.py`：输入（run 仓储, 观测仓储, FaceClusterRun）→
  - `observations_for(cluster_run)`：`parameters.dataset == 'library'` 时 = 跨所有运行按照片取**最新**观测集（latest wins）；否则 = 锚点运行观测（现状）。
  - `snapshots_for(cluster_run)`：同规则的 run_photos 快照（成员路径/首拍/状态展示）。
  - `outcome_summary_for(cluster_run)`：按同规则的各照片最新 outcome 汇总。
- 消费方改造（全部改为经 resolver）：
  - `ClusterFacesService._cluster_all`：观测来源 + 参与过滤改 `classify_scope(photo_face_count, command.selected_ranges)`（存储 verdict 保留为审计）；`StartClusteringRunCommand` 加 `selected_ranges`（默认 `(FaceCountRange(1, None),)` 保持测试/调用兼容；UI 显式传 [1]，D2）+ 参数快照记 dataset/ranges。
  - `ClusterResultsService.results` / `run_photo_outcome_summary`。
  - `SuggestPairingsService._execute_in_scope`（注入 run 仓储；缺省回退锚点行为，测试兼容）。

### A3 界面与编排

- 主工具栏移除「运行人脸识别」动作与 `_on_match_clicked` 主链（QAction/常量保留供维护入口复用）；数据工具页新增「重新分析全部照片」（确认框 → `start_run(photo_ids=None)`）。
- 人员页聚类组：`运行人脸聚类` 点击 → 聚类范围弹窗（五档，默认 [1]）→ `ClusterFacesController.start_cluster(run_id, selected_ranges)`；选择器保留（锚点/历史代际），文案改"聚类使用全库最新特征数据集"。
- workspace/概览：扫描门不再要求名单（扫描=登记+特征，无需人员）；概览第 3 步文案改"人脸识别（扫描时自动提取特征）"；`match` 主 CTA 重路由至 scan/review 逻辑；相关 ui_text 常量与 `CLUSTER_PAGE_*`、`WORKSPACE_*` 文案同步。
- 兼容：`RecognitionScopeDialog` 退役（主链不再引用），类与其测试删除；`_on_scan_clicked` 提交组合任务。

## 4. 阶段 B：聚类完成后自动生成建议（D3=A3）

- `MainWindow._on_completed` 的 `face_clustering` 分支：task 结果为 `FaceClusterRun` 且 `cluster_count > 0` 时，名单非空则同步调用 `SuggestPairingsService.execute(StartSuggestPairingsCommand(cluster_run.id))`，状态栏追加"已按名单顺序生成 N 条建议（自动确认 M 条）"；名单为空则提示"名单为空，未生成建议"。失败不吞：记日志并在状态栏明示，不影响聚类完成状态。
- 建议生成走既有事务与幂等（新代际无既有指派 → 全量位置配对；「生成建议」按钮行为不变）。

## 5. 阶段 C：详图导航内聚（D4=B1）

- `PhotoDetailDialog` 增加可选 `navigator`（构造参数）：注入后在预览框左右中间叠放 ‹ › 扁平按钮（样式半透明、位于固定 640×480 包围盒内）、底部"第 x/y 张"计数标签、键盘 ←/→；点击发 `navigation_requested(delta)` 信号，**对话框不持有照片列表**。
- 不注入 navigator 的调用点（照片库双击 `main_window.py:867` 等）行为零变化。
- `ClusterResultsDialog`：实现 navigator（现 `_on_detail_prev_next` 的组内循环 + 失效可见反馈逻辑迁入宿主侧槽）；**移除**右侧面板常驻上一张/下一张按钮（P6 生命周期语义随按钮内化：导航按钮随详图存在，无需外部启停）。

## 6. 测试与验收

- 新增：增量集判定（新/变/失败重试/模型缺失降级）、cluster_dataset resolver（latest-wins、旧锚点、参数缺省回退）、范围过滤参与、导航组件信号与计数、自动建议完成分支（名单空/非空/服务异常）。
- 改造：cluster service 参与过滤、扫描结果 DTO 加列、人员页/主窗口文案与动作、`RecognitionScopeDialog` 测试退役。
- 每阶段：定向测试 → 串行全量 pytest + ruff + mypy 全绿 → 独立提交（fix/feat 前缀，不带 push）。
- 验收硬线：
  1. 扫描一次含新照片与历史失败照片的文件夹 → 一个 run 只含增量照片、观测/兼容行落库、状态可证；
  2. 两次扫描不同文件夹后聚类 → 代际覆盖两批照片（全库口径）、与历史 [1] 口径一致；
  3. 聚类完成即左列表显示人名（未点生成建议）；
  4. 双击详图出现 ‹ › 与计数，键盘可用；照片库/审核中心路径回归不变。

## 7. 记账（backlog，不阻塞本任务书）

- 聚类范围"记住上次选择"（QSettings 偏好链）；
- 扫描登记段协作式取消；
- 维护入口"重新分析选中照片"（本轮回退为仅"全部"，选中路径随范围对话框退役）。
