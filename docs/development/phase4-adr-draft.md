# 阶段 4 技术债轮前置门草案（兼容路径移除 / 性能加固 / export 与审批门）

> **文档性质**：ADR 草案（Proposed 状态），阶段 4 技术债轮开工前置门产出。
>
> 按 `AI_ONBOARDING.md §6` 与 phase1/2/3 先例：触及公开 API 或架构边界的轮次须先出草案评审拍板。本草案合并承载 P1-B 三项技术债的现状证据、拟议方案与裁决点，**拍板后各项分别登记 ADR 并独立实施提交**。
>
> **产出时间**：2026-08-25 ｜ **产出者**：Cline ｜ **状态**：已拍板定稿（2026-08-25 五项裁决 B4-1~B4-5 全按默认推荐通过；实施结果见 §6）
>
> 前置状态：HEAD 含阶段 3 收官与 P0 收口（`KNOWN_ISSUES.md` 空）；质量门 ruff 通过 / mypy 168 文件零问题 / pytest 402 passed + 8 skipped。

---

## 0. 裁决点汇总（待拍板）

| # | 项 | 裁决点 | 选项 | 默认推荐 |
|---|---|---|---|---|
| B4-1 | 兼容路径移除轮次 | 何时移除旧 `enable(context)` 分发分支 | A. 本轮立即移除 / B. v1.0.0 发布后的首个破坏性窗口（v2.0.0）/ C. 无限期保留 | **B**——兑现 ADR-026"Deprecated 保留一个版本"承诺；若 M8 先发 v1.0.0 则移除自然落在 v2.0.0 |
| B4-2 | 批量查询方案 | N+1 修复的端口扩展形态 | A. `PhotoRepository` 扩 SQL 下推联查方法 / B. `RecognitionRepository` 批量接口 + 内存 join / C. 不修 | **A**——SQL 下推先例（dev-plan B2-a 已拍板模式）；大库最优 |
| B4-3 | 基准脚本归属 | `tools/bench_plugin_search.py` 去留 | A. 入库长期保留作防回退基线 / B. 本轮证据用完删除 | **A**——优化前后可复跑对比 |
| B4-4 | export 插件写能力 | 是否开放插件触发导出 | A. 有真实用例，出 phase5 草案开放 / B. 无用例，YAGNI 正式关闭暂缓项 | **待负责人确认用例后定** |
| B4-5 | 宿主审批门 | 是否为本轮加高危写操作确认门 | A. 本轮加 / B. 继续暂缓 | **B**——无已知高危写用例前不加复杂度（与 ADR-028 裁决点 2=A 同逻辑） |

---

## 1. B1 — 旧 `enable(context)` 兼容路径移除（现状盘点）

### 1.1 消费者盘点（grep 实证 2026-08-25）

| 消费面 | 位置 | 旧签名使用 |
|---|---|---|
| src 生产代码 | 仅 `plugins/loader.py:116-140` `_enable_plugin` 三分叉（ContextAware / 旧 enable(context) / 旧无参）；协议本身 `ports/plugin.py:93,184` 两处 `enable()` 均已无参 | 分发点唯一 |
| examples/plugins | hello_plugin.py:42 / stats_report_plugin.py:44 / import_people_demo_plugin.py:56 | **三个示例全部已是 ContextAware 标准，零旧签名消费者** |
| tests | test_loader.py:72、test_plugin_context.py:125、test_plugin_lifecycle_compatibility.py:122 + :217-226 + :255-277 兼容矩阵断言 | 移除时同步删改 |
| docs | plugin-guide.md §3 表格与 §6 limits 的 legacy 表述；plugin-context-design.md:311（已带取代注记）；phase1-adr-draft.md（历史定稿） | 实施时同步刷新 |

### 1.2 拟议变更（B4-1=B 时挂起至 v2.0.0 轮执行）

- `loader._enable_plugin` 三分叉收敛为二分叉（ContextAware / plain 无参）；`inspect.signature` 探测分支删除。
- 删除上述三处测试 fake 与矩阵断言中"旧 enable(context)"行列；`test_context_none_three_paths_all_degrade_gracefully` 改两类路径。
- plugin-guide §3 表格与 §6 limits 删除 legacy 兼容表述；ADR 登记（编号顺延）。
- **行为风险与缓解**：外部未知插件若仍定义 `def enable(self, context=None)`，移除后将被当作无参直调 → TypeError → 被 `enable_all` 既有异常隔离捕获、记 error 不崩宿主，但该插件失效。缓解：Release Notes 破坏性变更显著标注 + plugin-guide 迁移指引。

### 1.3 完成标准

- [ ] loader 分发二分叉；`grep -n "enable(self, context" src examples` 归零（docs 历史稿除外）
- [ ] 兼容矩阵测试更新且全量 pytest 绿
- [ ] ADR 登记移除裁决 + Release Notes 标注破坏性变更

---

## 2. B2 — `search_photos` 识别联查 N+1 加固（实测证据）

### 2.1 问题定位

`application/services/plugin_context_service.py` search 循环对每张命中照片单独调用 `RecognitionRepository.list_by_photo(photo_id)`（N+1）。该路径被两处 UI 同步消费：插件统计报表（stats_report_plugin）与主窗口筛选刷新（`main_window.py` FilterBar `criteria_changed` → `_on_filter_changed` 同步调 search，无 Worker）。

### 2.2 实测基线（`tools/bench_plugin_search.py`，2026-08-25 本机 SQLite 实测，可复跑）

| 库内照片总数 | recognition 仓储调用次数 | 单次 search_photos 墙钟 |
|---|---|---|
| 100 | 100 | 47.1 ms |
| 600 | 600 | 266.8 ms |
| 2600 | 2600 | **1137.9 ms** |

结论：调用次数恒等于照片数（N+1 实锤），耗时 ~0.44 ms/张线性外推——万级库将达 4–5 秒且阻塞 UI 线程，与"管理大量历史照片"目标冲突。

### 2.3 拟议方案（B4-2）

- **方案 A（推荐）**：`PhotoRepository` Protocol 扩展批量联查方法（SQL LEFT JOIN recognition_results 一次取回 photo + match_status 对），SQLite 与 InMemory 双实现 + 一致性对照测试（沿用 dev-plan B2-a"SQL 下推 + InMemory 对照"先例）。属公开 API 向后兼容扩展，需本次拍板批准。
- **方案 B**：`RecognitionRepository` 批量取全量 status 字典，service 层内存 join——端口变更更小，但大库以内存换时间。
- 实施完成标准：同规模复测 2600 张降至 <100 ms 且 calls==1；既有测试全绿；新增对照测试守护双实现一致性；基准脚本前后数字录入 ADR。

### 2.4 基准脚本归属（B4-3）

`tools/bench_plugin_search.py` 为零依赖 stdlib 脚本，入库长期保留作为性能回归的最低基线手段。

---

## 3. B3 — export 写能力与宿主审批门裁决

**待负责人确认的唯一事实问题**：是否存在"插件触发报告/数据导出"的真实业务场景？

- **无** → 记录 YAGNI 结论正式关闭 B5-a/ADR-028 的 export 暂缓项（不再无限期悬挂）；审批门随未来高危写用例出现再议（B4-5=B）。
- **有** → 另出 phase5 草案，复用 ADR-028 双向 DTO 脱 Domain 成熟模式（PluginExportCommand/PluginExportResult），export 与审批门同轮设计。

---

## 4. 执行顺序（拍板后）

```text
B4-2/B4-3 批准 → B2 实施（端口扩展 + 优化 + 复测 + ADR 登记，feat/perf 提交）
B4-1 = B 时挂起；= A 时本轮即做（refactor 提交 + ADR 登记 + Release Notes 标注）
B4-4/B4-5 按负责人答复走对应分支
每项独立提交；收尾刷新 PROJECT_STATUS + DOCUMENT_INDEX + KNOWN_ISSUES（如有）
```

## 5. 总完成标准

- [ ] 三项裁决点均有明确拍板记录（本文件转定稿）
- [ ] B2 优化落地并附前后基准对比；基准脚本入库
- [ ] B1 按 B4-1 裁决执行或明确挂起到 v2.0.0
- [ ] B3 暂缓项状态终结（开放或明示关闭）
- [ ] 全量质量门绿；文档触碰清单自检；PROJECT_STATUS 刷新

> 勘误注（2026-08-27）：B1 已于 v2.0.0 轮兑现执行（提交 `8f317a6`，tag
> `v2.0.0` 已发布）——上列 B1 条目「按 B4-1 裁决执行或明确挂起到 v2.0.0」
> 两支均已走完；复选框依冻结件惯例保留原状。

---

---

## 6. 拍板记录与实施结果（2026-08-25）

| # | 裁决点 | 拍板结果 |
|---|---|---|
| B4-1 | 兼容路径移除轮次 | **B**——旧 `enable(context)` 分发分支移除绑定 v1.0.0 发布后的首个破坏性窗口（即 v2.0.0）执行，兑现 ADR-026 "Deprecated 保留一个版本"承诺；本轮不动 loader |
| B4-2 | 批量查询方案 | **A 批准**——实施细化说明：详细设计发现「PhotoRepository 联查」使 InMemory 测试替身无法独立实现 status 轴（跨聚合耦合），等效细化为 `RecognitionRepository.list_first_by_photo_ids`（IN 下推单往返、排序语义镜像 `list_by_photo[0]`），性能目标不变且端口面更小——论证见 ADR-029 |
| B4-3 | 基准脚本归属 | **A 入库**——`tools/bench_plugin_search.py` 长期保留作防回退基线（零依赖可离线复跑） |
| B4-4 | export 写能力 | **B YAGNI 正式关闭**——经负责人确认无真实用例；B5-a/ADR-028 的 export 暂缓项就此终结（获得确定性终态而非继续悬挂），未来出现用例须另起草案 |
| B4-5 | 宿主审批门 | **B 继续暂缓**——无已知高危写用例前不引入确认复杂度 |

### 实施前后基准对比（tools/bench_plugin_search.py，同机同库形态实测）

| 库内照片总数 | 修复前调用次数 / 墙钟 | 修复后调用次数 / 墙钟 |
|---|---|---|
| 100 | 100 次 / 47.1 ms | **1 次 / 5.4 ms** |
| 600 | 600 次 / 266.8 ms | **1 次 / 16.3 ms** |
| 2600 | 2600 次 / 1137.9 ms | **1 次 / 62.5 ms** |

2600 张库 **18.2× 提速**，识别仓储往返次数从 O(N) 收敛为 O(1)。拍板后质量门实测：ruff 通过 / mypy 168 文件零问题 / pytest 405 passed + 8 skipped。

---

> 📝 本草案由 Cline 于 2026-08-25 产出并同日拍板定稿；裁决已写入 `.ai/ARCHITECTURE_DECISIONS.md` ADR-029 / ADR-030。