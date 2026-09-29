# RELIABILITY_SECURITY_PERFORMANCE_AUDIT.md — 全面工程健康审计 · 可靠性/并发/异常/性能/安全（Stage 6）

- **审计日期**: 2026-09-28 ｜ 对象: HEAD `2823d1c` ｜ 性质: READ-ONLY
- **方法**: 任务生命周期全景读码（task.py → qt_executor.py → task_coordinator.py）→ 取消路径逐行追踪 → DB 连接/事务生命周期 → 安全模式全仓扫描 → 性能热点定点核查

---

## 1. 任务生命周期全景 [VERIFIED]

```text
Task ID → Owner → Lifecycle → Terminal State
{name}_{uuid8}   TaskCoordinator    reserve → bind(connect+replay) → QThreadPool.run    terminal 事件（三型）
                 （唯一准入预留）     → cooperative cancel（边界检查）                     去重后恰好一次投递 UI
```

- **身份路由**：事件携带 task_id，coordinator 仅接受当前预留且 id 匹配的事件——已结束任务无法修改新任务 UI、跨任务事件串扰不可能（`task_coordinator.py:158-160`）。
- **终态恰好一次**：`reservation.terminal` 先置位再去刷 UI/弹错误框（`:162-172`），迟到排队事件随路由 `deleteLater` 丢弃；接线失败仍保所有权并兜底连接 + `replay_pending_terminal`（`:128-138`）。
- **快失败竞态**：任务在 submit 与 connect 之间结束 → 终态留存待重放（`qt_executor.py:30-48`，注释记载真实事故：macOS 导出动作永久禁用）；文档明示可能双重投递且"消费者槽全部幂等"。
- **取消**：GUI 线程置布尔（GIL 原子）+ worker 边界 `raise_if_cancelled`；coordinator `cancelling` 标志保证仅一次请求、终态前保持准入。

**未发现**：一个任务更新另一个任务的 UI、已结束任务再次修改 UI、cancel 后回调仍生效、replay 重复副作用（幂等声明 + 终态去重 + 身份守卫三层防护）。

## 2. 发现 AUD-023（P2）——识别取消延迟 = 剩余队列全排空，F-04"60s 根因"得到解释

- **机制**（`run_recognition_service.py:69-75`）：全部照片**一次性** `pool.submit(...)`（1000 张 = 1000 个 futures 入队）；取消路径只 `break` 消费循环并 `future.cancel()` 当前一个；`with ThreadPoolExecutor` 退出 = `shutdown(wait=True)`（无 `cancel_futures=True`）→ **所有已入队未启动的 futures 照常执行**，run 标记 cancelled 但后台线程继续计算剩余全部照片。
- `FaceAnalysisTask` 不感知取消事件（`face_analysis_task.py:31-37` 仅持 detector）——排队任务无法提前退出。
- **后果**：取消延迟 = 剩余批次的完整处理时间（千张 × ~60ms ≈ 60s，与 Stage F 验收审查记录的"取消延迟 60.0s"吻合，F-04 称"根因与既有说明不符"——本审计给出真根因）。UI 期间持续显示"取消中"；CPU 持续满载；状态一致性无损（部分观测已持久化、run 终态正确——Stage 4 lifecycle 测试证明）。
- **同型**：`match_persons_service._execute_parallel:261-265` 同样 submit-all（且服务层无取消通道，取消完全依赖任务边界——LIMIT-002 的"batch-level"实为**批尾**粒度）。
- **修复方向（仅记录）**：取消时批量 `future.cancel()` + `shutdown(wait=True, cancel_futures=True)`，或让 FaceAnalysisTask 感知 cancel_event 短路返回。

## 3. 资源生命周期 [VERIFIED] + AUD-024（P3）

- **事务连接**：UoW scope 显式 close（`sqlite_connection.py:101-102`）；`_SharedConnection.__exit__` 正确抑制 close 使仓储 `with` 块不误关事务连接（`:47-48`）。
- **嵌套事务**：同线程二次 `transaction()` 显式 RuntimeError（`:111-112`）——边界清晰。
- **AUD-024（P3）**：非事务路径的 per-call 连接（每次仓储调用 `sqlite3.connect` + 3 条 PRAGMA）**无显式 close**，依赖 CPython 引用计数在 with 块结束时回收（`sqlite3.Connection.__exit__` 只 commit 不 close）。CPython 3.11（项目钉定）下可靠；非 refcount 实现将泄漏。连接churn 与每调用 PRAGMA 为简化设计代价，量级可接受（SQLite 打开廉价）。
- **文件句柄**：元数据/缩略图/导出路径均 context manager 或立即写完；导出经 `_atomic_write`（同卷 `.part` + `os.replace` + 失败清理，`:13-25`）——中断导出不留半文件。
- **崩溃恢复**：启动备份（VACUUM INTO 快照 + 滚动窗口）+ quick_check + WAL；并行匹配按 `_PARALLEL_FLUSH_SIZE` 分片持久化（崩溃最多丢一片，ADR-037 注释）；观测按 50 张分片 flush。恢复语义良好。

## 4. 性能 [VERIFIED，声明值 + 代码证据]

| 项 | 现状 | 证据/口径 |
|---|---|---|
| 人员重排 | P0 已收口（88→21.7 / 477→115.6 / 2132→391ms @ 50/300/1000 人），P1/P2 owner 裁决不做（AR-05） | PROJECT_STATUS §2（文档）；Stage 2 见回归测试 |
| 工作区计数 | 单条聚合 SQL，零实体物化 | `sqlite_recognition_repository.py:181-248` |
| 缩略图 | 异步 QThreadPool + QueuedConnection 回投 + 防重复分发守卫 | `photo_list_controller.py:41-111` |
| 搜索 | SQL 下推 WHERE/ORDER BY；重复分组按 content_hash 聚合 | `sqlite_photo_repository.py:229,257` |
| 匹配候选驻留 | `list_all()` 整批驻留（数百人 × 512 float ≈ 数十 MB）——代码注释明示已知并可分批 | `match_persons_service.py:112-114` |
| 规划器 O(persons×approved) | 代码注释明示典型 <50ms 可受，留优化方向 | `archive_planner.py:89-91` |
| `list_all()` 全表物化 | `SELECT *` 无分页（维护操作路径） | `sqlite_photo_repository.py:179` |

结论：无未声明的 O(n²)/N+1 热点；两处已知内存/复杂度取舍均有代码内声明。

## 5. 安全 [VERIFIED]

| 项 | 结果 |
|---|---|
| 危险原语 | `eval/exec/pickle/marshal/shell=True/os.system/yaml.load/subprocess` **全仓零命中**（命中均为注释明示"刻意用 JSON 避免 pickle 代码执行面"）|
| 网络出口 | 唯一 urlopen（模型下载）：URL 钉定 + `EXPECTED_SHA256` 字典 fail-closed + certifi CA（`model_deployment.py:31-74`）|
| 路径遍历 | 归档三层防护（词法 + resolve 跟随 + 拒 symlink，Stage 2 已核）；根目录经 settings validator；`PhotoPath/ArchivePath` 值对象约束 |
| 导出注入 | OWASP 口径公式注入防护（`=`/`+`/`@`/TAB/CR 前缀中和，负数保号）+ `test_export_injection.py` 专项 |
| 临时文件 | 导出原子写 `.part` 同卷替换，失败清理 |
| 密钥 | `.env.example` 无敏感值；日志不含凭据 |
| **插件信任边界** | 任意 .py 装载 = 全权限代码执行；**已明文声明**"not a security sandbox — trusted local Python plugin model"（`plugin-guide.md:141-142`），且默认 `plugins_directory=None` 不自动装载——**设计已声明，不立案** |
| 依赖漏洞 | 本轮未做 CVE 数据库比配（超出只读审计手段）；钉定版本清单在 `lock.txt`，建议发布前例行 `pip-audit`（记入 Stage 9 建议）|

## 6. Findings 汇总

- **AUD-023（P2）**：识别/匹配取消延迟 = 剩余队列全排空（submit-all + shutdown 排空 + 任务体无取消感知）；解释 F-04 现象；状态一致性无损，属用户体验/资源占用缺陷。
- **AUD-024（P3）**：per-call DB 连接依赖 CPython 引用计数隐式关闭 + 每调用连接churn——CPython 下无害，记录在案。
- **正面**：任务生命周期三层防护成熟（身份路由/终态去重/重放幂等）；崩溃恢复与分片持久化设计完整；安全面干净（危险原语零命中、模型 sha256 fail-closed、注入防护、原子写）。
