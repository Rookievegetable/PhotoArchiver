# Phase 6 ADR 前置门草案 — 识别管线批量吞吐性能加固

| 项 | 内容 |
|---|---|
| 状态 | **Accepted（前置门拍板 2026-08-28，五项全按默认推荐）——本文件已转定稿，执行轮依据 §3 清单实施** |
| 日期 | 2026-08-28 |
| 前序 | ADR-029（插件查询 18.2×，SQL 下推先例）/ ADR-030（基准脚本入库先例 B4-3）/ ISSUE-001（detect+embed 单 pass 合并优化先例） |
| 目标版本 | v2.1.0（minor，纯性能，不动 Schema/公共 API） |

---

## §0 背景与动机

ADR-029 修的是**插件查询路径**（18.2×）；AI 识别管线本身（检测→嵌入→匹配→持久化）自 Step 10 落地以来从未有过基准测量与优化轮。大库（5,000 张+）场景下它是唯一未量化的吞吐瓶颈，且无需任何外部需求触发，属技术债主动清偿。本草案经全量代码摸底后产出，所有事实均带文件行号锚点。

## §1 现状摸底（事实表）

| # | 事实 | 锚点 |
|---|---|---|
| F1 | 批量识别为**串行 for 循环逐张处理**——无任何并行 | `application/services/match_persons_service.py:100-105` |
| F2 | 单张链已含 Issue-001 合并优化：`detect_with_embeddings` 单次 `FaceAnalysis.get` 同时出检测框+嵌入，recognizer 不再二次检测 | `match_persons_service.py:131-136` |
| F3 | 候选嵌入**全量内存加载** `list_all()`，代码注释自记「Step 12 应改为分批 lazy 加载或 snapshot」 | `match_persons_service.py:95,114-121` |
| F4 | 识别结果**逐条 `add()` 持久化**——N 张照片即 N 次 DB 往返 | `match_persons_service.py:153-158` |
| F5 | **管线已完整装配但零生产消费者**——`MatchPersonsCommand` 生产代码零构造，presentation 层无任何识别触发点（含缺模型 `_UnavailableMatchService` 占位守卫）；基准工具将同时成为唯一可复跑驱动入口 | `app/services.py:153-197`；presentation 全层 grep 零命中 |
| F6 | 线程池 worker 体系已存在（scan 在用，`MAX_WORKERS` 配置项现成），识别未接入 | `workers/qt_executor.py`、`workers/application_tasks.py`、`.env.example` `MAX_WORKERS=4` |
| F7 | 推理引擎为 onnxruntime CPU 推理——**推理段释放 GIL，线程并行有效前提成立**；`CosinePersonMatcher` 为纯 numpy 余弦（同样释放 GIL） | `ai/insightface_detector.py`、`ai/similarity_matcher.py` |
| F8 | 基准脚本入库 + docstring 数字续记惯例已有两处先例 | `tools/bench_plugin_search.py:17-28`、ADR-030 B4-3 |

## §2 裁决点（拍板表）

| # | 项 | 裁决点 | 选项 | 默认推荐 |
|---|---|---|---|---|
| A-1 | 基准工具归属 | `tools/bench_recognition.py` 去留 | A. 入库长期保留（库容梯度 × workers 梯度，数字续记 docstring）/ B. 本轮证据用完删除 | **A**——B4-3 先例；F5 决定了它还是当前唯一可复跑驱动入口 |
| A-2 | 并行形态 | 逐张推理段的并行轴 | A. `ThreadPoolExecutor` per-photo（复用 `MAX_WORKERS`）/ B. onnxruntime batch 维度批量推理 / C. 进程池 | **A 先行拿测量数据，B 视 A 证据决定是否二轮**；C 排除（模型多份加载 + 进程序列化开销不划算） |
| A-3 | 持久化批量化 | 逐条 `add()` 是否下推 | A. 协议扩 `add_many`，SQLite 端单事务批量提交（往返 O(N)→O(1)）/ B. 维持逐条 | **A**——ADR-029/B4-2 端口扩展+等效细化先例直接覆盖 |
| A-4 | 进度语义 | 并行化后进度上报口径 | A. 保持「完成张数」逐张计数（边界+每 10 张上报规则不变）/ B. 允许批量粒度 | **A**——UI 进度契约不变，实施零波及 |
| A-5 | 范围边界 | UI 触发点（识别入口按钮）是否本轮补齐 | A. 本轮补 / B. 不补，维持 F5 现状 | **B**——触发点属功能开发，本轮纯性能+基准；避免范围蔓延，触发点另立轮次 |

## §3 拟议变更清单（A-2=A / A-3=A 时）

| 文件 | 改动 |
|---|---|
| `tools/bench_recognition.py` | **新建**——合成图像库容梯度（100/600/2600）× workers 梯度（1/2/4），以 `MatchPersonsService.execute` 为锚驱动（临时 stub repository 收集结果），基线数字落 docstring（沿 `bench_plugin_search.py` 惯例） |
| `application/services/match_persons_service.py` | F1 串行段改线程池并行；**架构约束：并行段仅限纯推理（detect_with_embeddings + cosine match），持久化收敛回主线程单点**（规避 SQLite 跨线程限制）；`add` 调用改批量收集后一次 `add_many` |
| Domain `RecognitionRepository` 协议 + InMemory/SQLite 双实现 | 协议扩 `add_many(results)`；SQLite 端单事务批量 INSERT；InMemory 端逐条等价（详细设计发现落点需调整时，沿 ADR-029 等效细化论证惯例在定稿补记） |
| `tests/unit/`（新增等价性对照测试） | 串行 vs 并行结果集逐字段等价（photo_id/confidence/person_id 全等，顺序按输入序还原）；`add_many` 单事务断言；进度上报次数语义回归 |

## §4 不变量（全部必选约束，非选项）

1. **结果等价**——识别结果集与串行版逐字段等价（每张独立 Top-1，无跨张状态，天然可并行；浮点余弦按张独立计算不受并行顺序影响）
2. **SQLite 线程安全**——任何 repository 调用不跨线程；并行段只触 ports（detector/matcher），不触 repository
3. **进度语义**——上报规则（首末张 + 每 10 张）与计数口径不变
4. **失败隔离**——单张推理异常不中断整批（与现状一致：异常路径逐张已经隔离语义，实施时保持并补测试）

## §5 风险

| 风险 | 缓解 |
|---|---|
| InsightFace 模型对象跨线程共享是否安全（onnxruntime session 并发推理） | 基准工具先行：A-1 基线阶段即用多线程实测验证，异常则回退 A-2=B（batch 单线程批推理） |
| `list_all()` 候选全量加载在大人像库下的内存占用 | 本轮维持现状（F3 lazy 化不纳入），基准工具记录候选集内存占用作观察数据，超标另立轮次 |
| 并行下进度乱序 | 完成计数用线程安全原子（`itertools.count`/锁），语义仍为完成张数 |

## §6 完成标准（转定稿后执行轮逐项核验）

- [x] 五项裁决点均有明确拍板记录（本文件转定稿）——§8 落档 2026-08-28。
- [x] 基准工具入库并附基线数字（docstring 续记惯例）＋ InsightFace 多线程安全性实测结论——`tools/bench_recognition.py` 全网格 exit 0（2026-08-29，37.4 min）；2/4 workers 各档 100% 产出、结果等价不变量全程成立 → session 跨线程共享实测**安全**（§5 首项风险解除）；基线数字已落 docstring。
- [x] 并行化落地且等价性对照测试通过——`test_match_persons_service.py` 新增串/并等价、失败隔离（参数化覆盖双路径）、进度语义用例；本地 pytest 全量绿。
- [x] 持久化批量下推，往返 O(N)→O(1)——Domain 协议扩 `add_many`，SQLite 端单事务批量提交；diff 审查 0 Critical / 0 Major / 0 Minor。
- [ ] 性能目标达成——**未达建议起点**：实测 4 workers 1.28× @2600 张（建议 ≥2×），与 §5 预判吻合（onnxruntime intra-op 池单次推理已吃满核心，per-photo 线程仅重叠 Python 侧开销）。证据已触发 §8 A-2=B 二轮裁决条件（batch 批推理）——**是否立项由 owner 拍板**（REV-AI-003：不以修改代替裁决）。
- [x] 全量质量门绿——本地 ruff ✓ / mypy 168 文件 ✓ / pytest 全量 ✓（417 passed）；CI 三平台实证全绿（owner push 后 run 33237717725 @ `14cfe1b`，2026-08-29 API 实测 windows/macos/ubuntu 三 job completed/success）——本行为 push 后回填。

## §7 文档触碰清单（执行轮）

`tools/bench_recognition.py`（新）、`match_persons_service.py`、Domain `RecognitionRepository` 协议与双实现、等价性测试（新）、`CHANGELOG.md`（v2.1.0 Changed 段 + 基准数字）、`.ai/PROJECT_STATUS.md`、本文件转定稿（§8 拍板记录 + checkbox 核销）。

## §8 拍板记录（owner 填写后本文件转定稿）

| # | 裁决点 | 拍板结果 |
|---|---|---|
| A-1 | 基准工具归属 | **A 入库**——`tools/bench_recognition.py` 长期保留（库容 × workers 双梯度，数字续记 docstring；兼作管线唯一可复跑驱动入口） |
| A-2 | 并行形态 | **A 先行**——ThreadPoolExecutor per-photo 复用 MAX_WORKERS，并行段限纯推理；A-1 基线阶段实测 InsightFace session 多线程安全性，异常回退 B（batch 单线程批推理） |
| A-3 | 持久化批量化 | **A 批准**——Domain `RecognitionRepository` 扩 `add_many`，SQLite 端单事务批量提交；落点需调整时沿 ADR-029 等效细化论证惯例在定稿补记 |
| A-4 | 进度语义 | **A 保持**——「完成张数」口径与上报规则（首末张 + 每 10 张）不变 |
| A-5 | 范围边界 | **B 不补**——UI 识别触发点属功能开发另立轮次，本轮纯性能 + 基准 |
