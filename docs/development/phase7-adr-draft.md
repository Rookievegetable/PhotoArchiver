# Phase 7 ADR 前置门草案 — 识别管线非推理段加固（W2-segment）

| 项 | 内容 |
|---|---|
| 状态 | **Accepted（owner 拍板 2026-08-29：W2-1=A / W2-2=A（前提确认：近期无性别/年龄功能规划）/ W2-3=A）**——W2-segment 段内分解证据已闭合，进入执行轮 |
| 日期 | 2026-08-29 |
| 前序 | ADR-032（phase6 并行化 1.28×）/ phase6 W1 尖刺（批推理证据性出局、瓶颈定址非推理段）/ 证据工具 `tools/spike_segment_profile.py`（v2，账目闭合） |
| 目标版本 | v2.2.0（minor，纯性能，不动 Schema/公共 API/输出语义） |

---

## §0 背景与动机

phase6 并行化实测仅 1.28×（4 workers，2600 张），未达预期。W1 尖刺（`tools/spike_batch_inference.py`）两轮证伪了「线程超订阅」与「batch 批推理」假设，把瓶颈定址在**非推理 GIL 串行段**（端到端 5.06 vs 纯推理天花板 ≈13.7 photos/s，落差 2.7×）。owner 拍板 A 路线后，W2-segment 尖刺完成段内分解与移除实验，**发现了两个零风险的死重模型**——证据表明最大增益不是复杂的并发改造，而是两行加载配置。

## §1 W2 证据链（`tools/spike_segment_profile.py` v2 实测）

v1 计量器污染 bug 已修正（阶段边界快照法，v1 教训留档于脚本 docstring）；v2 账目闭合：分解和 251.3 ≈ `analysis.get` 总账 249.4 ≈ 端到端墙钟 254.4 ms/张。

| # | 事实 | 数字 | 锚点 |
|---|---|---|---|
| F1 | 串行端到端 | 254.4 ms/张（样张单脸，F=1） | spike v2 serial wall |
| F2 | 段内分解：det.detect 96.2（内含 ORT ≈57）＋ rec.get 107.8（内含 ORT ≈30，余为 cv2 对齐）＋ genderage 9.8 ＋ **landmark 双模型 35.4** ＋ imread 1.9 ＋ 残差 0.2 | 合计 251.3 | spike v2 decomposition |
| F3 | **landmark 双模型（1k3d68 + 2d106det）为纯死重**——生产仅消费 bbox+kps+embedding，68/106 点 landmark 无人读取 | 剔除后 254.4→167.1 ms（**1.522×**） | spike v2 A/B 实验 |
| F4 | **genderage 亦为死重**——`Person` 域实体无性别/年龄字段，src 全库 grep 零消费 | 再剔后 167.1→128.2 ms（**合计 1.985×**） | spike v2 A/B；src 全库 grep |
| F5 | loader 裸构造 `FaceAnalysis(name, root)` 未传 `allowed_modules` → 全包 5 模型全部加载并随每次 `get()` 执行 | 剔除落点即此一行 | `infrastructure/ai/insightface_loader.py:75` |
| F6 | 并发段 4 线程：5.66 photos/s（1.44×）；ORT 累计时长 = 墙钟的 390% → 推理重叠良好，剩余瓶颈为非推理段串行化 | 1.44× | spike v2 concurrency |
| F7 | W1 关联结论：intra 线程是推理侧唯一杠杆（生产默认 intra=8 已近膝点）；批推理全格 ≤1.04× 证据性出局 | — | `tools/spike_batch_inference.py` docstring |
| F8 | 尖刺并发 1.44× 略高于生产 1.28× 属口径差（尖刺不含 DB 持久化与异构库容），非矛盾 | — | spike 口径注记 |

## §2 裁决点（拍板表）

| # | 项 | 裁决点 | 选项 | 默认推荐 |
|---|---|---|---|---|
| W2-1 | landmark 死重剔除 | 如何让加载包跳过两个 landmark 模型 | A. loader 传 `allowed_modules`（加载层跳过，启动更快，零输出变化）/ B. 检测器运行时 pop / C. 不剔除 | **A**——纯配置，F3/F5 实证 |
| W2-2 | genderage 处置 | 是否一并剔除（附加 1.23×，合计 1.985×） | A. 一并剔除——**前提：owner 确认近期无性别/年龄功能规划**（若未来需要，恢复加载即可，无数据迁移问题）/ B. 保留（仅做 W2-1） | **A（附条件）**——需 owner 明确确认功能规划 |
| W2-3 | 剔除后的非推理段再优化 | 剩余 ~38 ms/张（rec 对齐 ~30 + det 前后处理，imread 1.9）是否本轮改造 | A. 本轮不做——S1+S2 落地复测后按剩余占比与真实需求再议 / B. imread/对齐重叠改造 / C. 进程池 | **A**——先拿零风险增益，避免过度工程；进程池已被 W1 排除（模型多份加载不划算） |

**预估收益**（W2-1+W2-2=A）：串行 254.4→128.2 ms/张（≈7.8 photos/s）；端到端 4-worker 预期 **1.8–2.2×**（≈9–11 photos/s vs 现状 5.06），以 `tools/bench_recognition.py` 复测为准。仅 W2-1 时约 1.5–1.7×。

## §3 拟议变更清单（W2-1=A；W2-2=A 时含 genderage）

| 文件 | 改动 |
|---|---|
| `infrastructure/ai/insightface_loader.py` | `FaceAnalysis(...)` 增加 `allowed_modules=("detection", "recognition"[, "genderage"])`；docstring 补死重剔除注记（数字引 spike v2） |
| `tools/bench_recognition.py` | 复测网格（至少 2600 张 × 1/4 workers）并续记 docstring 防回退数字 |
| `tests/` | 现有等价性/失败隔离/进度矩阵全量复跑（模型剔除不改 bbox/kps/embedding，无需新增用例；如 CI 环境无模型包则不受影响——测试本就 mock AI 层） |
| 文档链 | CHANGELOG `[2.2.0]` 段（Performance）＋ phase7 转定稿（拍板记录）＋ ADR-033 登记 ＋ PROJECT_STATUS 刷新 ＋ 版本链 bump |

## §4 不变量（必选约束，非选项）

1. **输出逐字节等价**——被剔除模型的输出本就无消费者；det 的 bbox/kps、rec 的 512 维嵌入、匹配结果、入库顺序全部不变
2. **AI 端口契约不变**——`FaceDetector`/`FaceRecognizer` 协议签名零改动
3. **phase6 并行结构不动**——线程池、`add_many` 批持久化、进度语义原样保留

## §5 风险

| 风险 | 缓解 |
|---|---|
| insightface 版本升级导致 `allowed_modules` 语义变化 | 参数为 insightface 公开 API（`FaceAnalysis.__init__`），锁版本前提下稳定；CI 三平台矩阵回归把关 |
| W2-2 剔除 genderage 后未来功能需要性别/年龄 | 恢复 = 加载参数加回一个名字；无任何数据/接口迁移成本（裁决点已注明前提） |
| 收益不达预估（样张单脸 vs 真实库多脸） | 复测门禁：`bench_recognition.py` 真实网格数字落档后方可核销；多脸样张占比高时 rec 段占比上升、剔除收益占比略降（方向不变） |

## §6 完成标准

- [x] 三项裁决点均有明确拍板记录（本文件转定稿，2026-08-29 三项全 A）
- [x] loader `allowed_modules` 落地（W2-2=A：genderage 一并剔除，owner 确认近期无性别/年龄功能规划）
- [x] `tools/bench_recognition.py` 复测数字落 docstring（全网格九格：2600×1 1.98× / 2600×4 2.22×）
- [x] 门禁全绿（ruff / mypy / pytest 全量）＋ CI 三平台实证（本地三项全绿 2026-08-29：ruff 0 / mypy 168 ✓ / pytest 417 passed；CI 已实证——owner push 后 API 实测 head `4fe8aa4` CI run completed/success 三平台全绿，2026-08-29 回填）
- [x] 文档链收官（CHANGELOG / ADR-033 / PROJECT_STATUS / 版本链 bump → v2.2.0）

---
