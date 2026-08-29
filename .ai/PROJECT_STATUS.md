# PROJECT_STATUS.md — PhotoArchiver 当前运行状态

> **本文档是项目当前运行状态（Current Runtime State）的唯一快照。**
>
> 回答：**“项目现在开发到哪里了？”**
>
> 每次开发结束后刷新；不保留历史状态。
>
> Version: 1.7.1 · Last Updated: 2026-08-26 · Status: Live

---

## 1. Roadmap（开发路线图概览）

权威 15 步路线图：`.ai/business/roadmap.md`。

| Step | 名称 | 状态 |
|---|---|---|
| 0.5–11 | Walking Skeleton、基础设施、Domain、导入、扫描、缩略图、人脸识别、归档 | ✅ Completed |
| 12–14 | Main UI、Settings、Export | ✅ Completed |
| 15 | Plugin System | ✅ Completed |

M1–M7 及 Step 0.5–15 已全部完成；阶段 B 业务增强 B1–B5 与收官加固阶段 0–3 均已落地。

---

## 2. Current Step（当前开发阶段）

项目主路线图已完成，当前处于完成后的架构加固与可选能力扩展阶段。

- 阶段 0（质量基线与文档收口）：✅ 完成。
- 阶段 1（PluginContext 公共边界加固，ADR-026）：✅ 完成。
- 阶段 2（Alembic 接管 Schema DDL，ADR-027）：✅ 完成。
- 阶段 3（插件写能力 import_people，ADR-028）：✅ 完成（仅 import_people；export 经 ADR-030 裁决 YAGNI 正式关闭）。
- 阶段 4（技术债轮：search_photos N+1 加固 ADR-029 + 轮次裁决 ADR-030）：✅ 完成（兼容路径移除原挂账 v2.0.0，已于 v2.0.0 轮兑现——见下表「v2.0.0 破坏性窗口」行；审批门续暂缓）。
- 阶段 5（识别管线吞吐加固，ADR-032）：✅ 完成——线程并行 + `add_many` 单事务批下推 + 基准工具入库（全网格基线落档；线程扩展 1.28× 弱于建议阈值）。二轮证据链闭合：batch 批推理经 W1 尖刺证据性出局；W2-segment 尖刺段内分解定址两个死重模型（landmark 35.4ms + genderage 9.8ms，生产零消费）——phase7 执行轮完成（ADR-033，owner 三项全 A 拍板 2026-08-29）：landmark 双模型 + genderage 死重剔除（loader `allowed_modules=("detection","recognition")` 一行配置），全网格复测 2600 串行 656.94→332.02s（**1.98×**）、4-worker 5.06→**11.22** photos/s（**2.22×**），等价不变量全程保持（pytest 417），v2.2.0。

当前无已登记的未解决问题；`KNOWN_ISSUES.md` 为空。

---

## 3. Project Status（项目当前状态）

| 范围 | 状态 | 当前事实 |
|---|---|---|
| 15 步产品路线图 | ✅ | Step 0.5–15 全部已实现并验证。 |
| 阶段 B 业务增强 B1–B5 | ✅ | 重复图片、搜索/筛选、批量归档、HTML 导出、只读插件上下文均已落地。 |
| 阶段 0 质量基线 | ✅ | 质量门和文档收口已完成。 |
| 阶段 1 PluginContext | ✅ | ADR-026：`ContextAwarePlugin` 生命周期、Plugin DTO 边界、结构化 `PluginReport`。 |
| 阶段 2 Schema DDL 所有权 | ✅ | ADR-027：`002_split_create_ddl` 为 Schema DDL 唯一权威。 |
| 阶段 3 插件写能力 | ✅ | ADR-028：`PluginContext.import_people` 已实现——插件经 `PluginImportPeopleCommand`/`PluginImportPersonRow` 写入人员实体（宿主补 row_number），结果 `PluginImportResult` 以 str ids 脱 Domain；无宿主审批门；export 写能力经 ADR-030 裁决 YAGNI 正式关闭。示例插件 `examples/plugins/import_people_demo_plugin.py` 端到端演示。 |
| 阶段 4 技术债轮 | ✅ | ADR-029：插件查询识别状态批量联查——2600 张库单次查询 1137.9ms → 62.5ms（18.2×），往返 O(N)→O(1)；ADR-030：兼容路径移除挂账 v2.0.0（已兑现，见「v2.0.0 破坏性窗口」行）、export 暂缓终结、审批门续暂缓。基线工具 `tools/bench_plugin_search.py` 入库可复跑。 |
| M8 可发布里程碑 | ✅ | MIT License 落定（占位已删除）；pyproject 元数据落位（version 1.0.0 / license / classifiers / readme / description）；`.github/workflows/release.yml` 增补（tag 触发 sdist+wheel 构建并发布 GitHub Release）；`CHANGELOG.md` 建立；tag `v1.0.0` 已推送，GitHub Release v1.0.0 资产挂载确认（sdist+wheel）。 |
| M9 分发定位裁决 | ✅ | ADR-031 登记并执行完毕——运行形态定位为「源码/clone 唯一受支持」；Release v1.0.0 body 置顶安装态标注已由 owner 粘贴（2026-08-26 API 实测生效，B5-3 销账）；ISSUE-018 以 by-design 正式终结（KNOWN_ISSUES 回归空态）。 |
| v2.0.0 破坏性窗口 | ✅ | ADR-030/B4-1 兑现——旧 `enable(context)` 分发分支移除（loader 三分叉收敛为二分叉：ContextAware / 无参 enable），生产与示例代码零消费者 grep 实证；测试矩阵净减 3 个 legacy 用例（413→410 全绿）；CHANGELOG `[2.0.0]` BREAKING 标注落定；版本链 bump 2.0.0（pyproject + .env.example 示例值；settings 回退值按 configuration.md 口径保持不动）。发版链实证——tag `v2.0.0` 已推送并触发 release workflow（run 33071797649 双 job success）：GitHub Release v2.0.0 自动创建且双资产挂载 API 实测确认（wheel 220KB / sdist 152KB）；发布前实现提交 `ba3ad02` CI 三平台全绿（run 33070707134）。Breaking Notes 已由 owner 粘贴（2026-08-27 API 复验：body 859 字符、文案逐字到位，紧随自动生成的 Full Changelog 行呈现，Review MINOR-4 销账）。 |
| Phase 6 吞吐加固 | ✅ | ADR-032 五项裁决落地——ThreadPoolExecutor per-photo 并行（并行段限纯推理、持久化回主线程、`max_workers=1` 逐字节串行原路径）；Domain `RecognitionRepository` 扩 `add_many`、SQLite 端单事务批量提交（往返 O(N)→O(1)）；基准工具 `tools/bench_recognition.py` 入库（全网格基线落 docstring：2600 张串行 656.9s → 4 workers 514.0s = **1.28×**；InsightFace session 跨线程共享实测安全）；等价不变量测试锁定（pytest 410→**417** passed）。线程扩展弱于 ≥2× 建议阈值——batch 批推理（A-2=B）二轮证据已触发；W1 尖刺实测完成（`tools/spike_batch_inference.py`，2026-08-29）：纯推理天花板 ≈13.7 photos/s、线程超订阅假设证伪、瓶颈定址非推理段（~143ms/张）；W2-segment 尖刺（`tools/spike_segment_profile.py` v2，账目闭合 251.3≈249.4≈254.4 ms/张）定址两个零消费死重模型——landmark 双模型 35.4ms（剔除 1.522×）、genderage 9.8ms（合计 1.985×），剔除落点为 loader `allowed_modules` 一行配置；phase7 前置门草案待 owner 拍板（W2-1/W2-2/W2-3）。 |
| Phase 7 死重剔除（v2.2.0） | ✅ | ADR-033 三项裁决全 A（W2-1 landmark 剔除 / W2-2 genderage 一并剔除，owner 确认近期无性别年龄功能规划 / W2-3 剩余非推理段本轮不改造）——loader `allowed_modules=("detection","recognition")` 落地，bbox/kps/embedding 逐字节不变；`tools/bench_recognition.py` 全网格复测落 docstring：2600×1 656.94→332.02s（**1.98×**）、2600×4 514.00→231.68s（**2.22×**）、600×4 2.45×，全部格子 100% 产出 / 全 PENDING 等价保持；门禁本地全绿（ruff 0 / mypy 168 ✓ / pytest **417** passed）；证据链 `tools/spike_segment_profile.py` v2（账目闭合）+ phase7 定稿（`docs/development/phase7-adr-draft.md`）。CI 实证已回填（owner push 后 API 实测 head `4fe8aa4` CI run completed/success 三平台全绿，2026-08-29）。 |
| CI | ✅ | GitHub Actions 三 OS 矩阵、模型缓存与 AI/UI 断言已启用。 |

当前 HEAD：phase7 实现提交 `9f0bede`（死重剔除 loader 一行配置 + 全网格复测数字落档 + 版本链 2.2.0 + CHANGELOG `[2.2.0]`/ADR-033/phase7 定稿核销）→ 本状态登记提交随本笔并入；本地领先 origin/main（= `028675b`）4 笔（`bd52fbb` W1 尖刺证据 → `ce3f49c` phase7 草案登记 → `9f0bede` phase7 实现轮 → 本登记），沿 GIT-020 由 owner push 携带。tag `v2.0.0` 指向 `ba3ad02`；发版待办：tag `v2.1.0` 建议指向 `bd52fbb`（pyproject=2.1.0 基准点，CHANGELOG `[2.1.0]` 在位）、tag `v2.2.0` 指向 `9f0bede`。历史链：`14cfe1b`（phase6 登记）、`0871048`（phase6 实现，CI run 33237717725 三平台实证）、`eea3c1b`/`eddc8ee`/`2bbbfb8`（v2.0.0 周期）。

---

## 4. Current Modules（当前模块状态）

| 模块 | 状态 | 关键位置 |
|---|---|---|
| Logging / Configuration | ✅ | `infrastructure/logging/`、`infrastructure/config/` |
| Database | ✅ | Alembic 已启用；`002_split_create_ddl` 为 Schema DDL 唯一权威（ADR-024、ADR-027）。 |
| Domain / Import / Scan / Thumbnail | ✅ | `domain/`、`application/services/`、`infrastructure/`；`ImportPeopleService.import_rows` 提供预解析行导入入口（文件路径 `execute()` 委托同一落库核心）。 |
| Recognition / Review | ✅ | InsightFace detect/recognize/match 与审核闭环已完成。 |
| Archive | ✅ | Planner → Plan → Executor，支持 dry-run、captured_at 和批量筛选归档。 |
| UI / Settings / Export | ✅ | 主窗口、设置闭环、Excel/CSV/HTML 导出和 Worker 路径已完成。 |
| Plugins | ✅ | 发现/加载/生命周期 + PluginContext 读方法（search_photos/detect_duplicates）+ 写方法 `import_people`（ADR-028）；宿主经通用 PluginReportDialog 渲染插件报告。 |

### 数据库 Schema

`PRAGMA user_version = 4`。Schema 演进由 `alembic/` 与 `alembic_runner.py` 管理；表与索引 DDL 属于 Alembic 迁移（ADR-027）。阶段 3 未改 Schema、未新增依赖。

---

## 5. Last Session（最近一次开发记录）

| 项目 | 值 |
|---|---|
| 时间 | 2026-08-29（本地） |
| 生成者 | Cline |
| 会话范围 | Phase 6 吞吐加固执行轮全程实施（并行化 + 批持久化 + 基准实测 + 文档收官）＋ W1 batch-inference 尖刺（ADR-032 二轮证据采集，owner 指令启动）＋ W2-segment 段内分解尖刺与 phase7 前置门草案（owner 拍板 A 路线启动）。 |
| 已完成 | ① 草案转定稿（2026-08-28 owner 五项全按默认推荐拍板）并登记 **ADR-032**；② 实施落地——`match_persons_service.py` 串行段改 ThreadPoolExecutor 并行（并行段限纯推理、持久化收敛主线程、`max_workers=1` 逐字节原路径）、Domain 协议扩 `add_many` + SQLite 单事务批量 INSERT、等价/失败隔离/进度/单事务测试新增（pytest **410→417**）；③ 基准工具 `tools/bench_recognition.py` 完成五处 SIG-PATCH 真实签名对齐（`load()`/构造参/实体形状/`list_all()` dict 返回）+ 6 处修正后冒烟通过；④ 全网格基线实测（37.4 min，exit 0）：2600 张串行 656.94s → 4 workers 514.00s（**1.28×**），session 跨线程共享实测安全，数字落 docstring 防回退；⑤ 主 diff 合规审查 **0 Critical / 0 Major / 0 Minor**；⑥ 门禁全绿：ruff ✓ / mypy 168 文件 ✓ / pytest **417 passed**；⑦ 文档收官——CHANGELOG `[2.1.0]` 段、phase6 §6 核销（4/6 勾销 + 性能目标与 CI 两项诚实注记）、版本链 bump 2.1.0（pyproject + .env.example）、ADR-032 登记、GIT-020 工作流规则入库（commit-only）。⑧ W1 尖刺执行与落档（`tools/spike_batch_inference.py`，ORT 1.27.0 CPU / Ryzen 7 5800H 8C16T）——三模型 IO 探测（rec/genderage 输入 batch 维动态、det 固定 1）；det 线程扫描 intra=8→57.0ms vs intra=1→249.6ms（≈串行端到端全额，线程配置为检测器生死线）；复合并发矩阵（det+rec 共享会话同生产）：1×8=9.05、4×8=13.73、4×4=13.55、8×1=13.21 photos/s——**线程超订阅假设证伪**（全区间 13.2–13.7）；瓶颈改址：端到端 5.06 vs 纯推理 ≈13.7 photos/s，2.7× 落差定址非推理 GIL 串行段（~143ms/张：imread/预处理/SCRFD 解码/对齐/DB，天花板 ≈7.0 photos/s）。⑨ rec/genderage 网格纯净复跑（stdout 直写文件取数）：**批推理在纯推理侧亦证伪**——同 intra 全格 ≤1.04×（intra≥4 区 0.82–0.98× 回退），动态 batch 维是红鲱鱼（能用但不增益）；intra 线程是推理侧唯一杠杆（rec B=1 118.84→27.34 ms/img，**4.3×**，生产默认 intra=8 已近膝点）；genderage 代价可忽略（~0.31ms/张）且批化回退。**W2-batch 证据性出局**，二轮题设收敛为「W2-segment 主攻非推理段 / 止于 v2.1.0」二选一。完整数据表落脚本 docstring。⑩ W2-segment 尖刺执行（`tools/spike_segment_profile.py` v1→v2）——v1 计量器污染 bug（分解行在并发阶段后计算，产出 886ms 混合垃圾值）当场诊断并修正为阶段边界快照法（v1 教训留档脚本 docstring）；v2 账目闭合（分解和 251.3 ≈ analysis.get 249.4 ≈ 端到端 254.4 ms/张）。⑪ 段内分解与 A/B 移除实验出数：**landmark 双模型（1k3d68+2d106det）35.4ms 纯死重**（生产仅消费 bbox+kps+embedding；Person 域无性别年龄字段，genderage 9.8ms 同为死重，src 全库 grep 零消费实证）——剔除实验 254.4→167.1（1.522×）→128.2（**1.985×**）ms/张；剔除落点锁定 `insightface_loader.py:75` 裸构造未传 `allowed_modules`；并发段 4 线程 5.66 photos/s（1.44×，ORT 累计 390% 墙钟，推理重叠良好）。**phase7 前置门草案产出**（`docs/development/phase7-adr-draft.md`：§1 证据链 F1-F8 + §2 三裁决点 W2-1/W2-2/W2-3 + §3 拟议变更 + §4 不变量 + §6 完成标准，预估端到端 1.8–2.2×），待 owner 拍板转定稿。⑫ **owner 三项全 A 拍板（2026-08-29：W2-1=A / W2-2=A 附前提确认「近期无性别/年龄功能规划」/ W2-3=A）→ phase7 转定稿执行轮**：loader `allowed_modules=("detection","recognition")` 落地（死重剔除，bbox/kps/embedding 逐字节不变）；`bench_recognition.py` 全网格复测落 docstring——2600×1 656.94→332.02s（**1.98×**）、2600×4 514.00→231.68s（**2.22×**）、600×4 2.45×，九格全 100% 产出 / 全 PENDING；门禁 ruff 0 / mypy 168 ✓ / pytest **417 passed**；CHANGELOG `[2.2.0]` 段 + ADR-033 登记 + 版本链 2.2.0 + phase7 §6 checkbox 五勾全清（CI 项已按 phase6 惯例回填，2026-08-29）。 |
| 当前质量门 | `ruff check .` 通过；`mypy src` 168 个源文件无问题；pytest 全量 **417 passed**（本地实测）。CI 三平台实证全绿（run 33237717725 @ `14cfe1b` 及 phase7 push 后 head `4fe8aa4` CI run，windows/macos/ubuntu 三 job completed/success，2026-08-29 API 实测）。 |
| 工作区 | W2 轮：代码 2 文件（loader `allowed_modules` 一行配置 + `bench_recognition.py` 复测数字 docstring）+ 收官文档（CHANGELOG `[2.2.0]` / ADR-033 / phase7 定稿 / 版本链 2.2.0）分两笔提交（实现 / 状态登记）；证据工具 `tools/spike_segment_profile.py` 已随 `ce3f49c` 入库；无过程脚本遗留。 |
| Remaining | 无代码/文档阻塞项。剩余均为 owner 发版动作（沿 GIT-020 手动执行）：① push main（携带 `bd52fbb` / `ce3f49c` / phase7 实现轮 / 本登记 4 笔本地提交）；② tag `v2.1.0` @ `bd52fbb` 推送（该提交 pyproject=2.1.0 且 CHANGELOG `[2.1.0]` 段在位——v2.1.0 tag 此前从未创建，补齐后 SemVer 链完整）；③ tag `v2.2.0` @ phase7 实现提交推送。CI 三平台实证已回填（head `4fe8aa4` API 实测 completed/success；phase7 §6 末行 checkbox 已勾销）。 |
| Next Step | 发版两步曲（tag 与 push 均归 owner，GIT-020）：tag `v2.1.0` @ `bd52fbb` 推送（含 phase6 并行化 + W1 证据，pyproject=2.1.0 已验证）→ tag `v2.2.0` @ 登记链最终 HEAD 推送（构建产物与 @ `9f0bede` 相同，含登记文档更完整）；两个 Release body 分别粘贴对应 CHANGELOG 段摘要。吞吐线正式收敛关闭（W2-3=A：剩余非推理段 ~38ms/张 deliberate deferral）；此后项目回归条件触发休眠区。 |

---

## 6. Next Step（下一步开发计划）

Phase 7 死重剔除执行轮（ADR-033，owner 三项全 A 拍板 2026-08-29）已全部收尾——loader `allowed_modules=("detection","recognition")` 落地、全网格复测 1.98×（串行）/ 2.22×（生产 4-worker）落档 docstring、门禁本地全绿（ruff 0 / mypy 168 ✓ / pytest 417 passed）、CI 三平台实证全绿（owner push 后 API 实测 head `4fe8aa4`，2026-08-29）、文档链收官（CHANGELOG `[2.2.0]` / ADR-033 / phase7 §6 五勾全清 / 版本链 2.2.0）。剩余全部为 owner 发版动作：

1. ~~**push main**~~ ✅ 已完成（2026-08-29，origin/main = `4fe8aa4`，CI run API 实测 completed/success 三平台全绿；phase7 §6 CI checkbox 与本文件均已回填）。
2. **tag `v2.1.0` @ `bd52fbb` 推送发版**——该提交 pyproject=2.1.0（已验证）且 CHANGELOG `[2.1.0]` 段在位，release workflow 自动出包（v2.1.0 tag 此前从未创建，补齐后 SemVer 链完整）；Release body 建议粘贴 `[2.1.0]` 段摘要。
3. **tag `v2.2.0` @ 登记链最终 HEAD 推送发版**（构建产物与 @ `9f0bede` 相同，含登记文档更完整）——Release body 建议粘贴 `[2.2.0]` 段摘要（~2× 端到端提升 + bbox/kps/embedding 逐字节等价 + W2-3 诚实注记）。

吞吐线状态：**正式收敛关闭**——batch 批推理经 W1 证据出局（ADR-032/phase6 注记）；剩余非推理段 ~38ms/张经 W2-3=A 本轮不改造，如未来需要 >2.2× 增益须另起前置门附页带新证据裁决。其余条件触发行不变：真实高危插件写用例→审批门复审（ADR-028 裁决点 2=B/C）；非技术用户分发需求→phase5 定稿方案 B 另起前置门；UI 识别触发点→功能轮另立（A-5=B）。

## 7. Key Files（关键文件索引）

| 职责 | 文件 |
|---|---|
| 插件协议与上下文 | `src/photo_archiver/application/ports/plugin.py`、`src/photo_archiver/application/ports/plugin_context.py` |
| 插件上下文服务（读映射 + import_people 写编排） | `src/photo_archiver/application/services/plugin_context_service.py` |
| 人员导入服务（文件/预解析行双入口） | `src/photo_archiver/application/services/import_people_service.py` |
| Plugin import DTO | `src/photo_archiver/application/dtos/plugin_context.py` |
| 插件加载与应用装配 | `src/photo_archiver/plugins/loader.py`、`src/photo_archiver/app/bootstrap.py`、`src/photo_archiver/app/context.py` |
| 示例插件 | `examples/plugins/stats_report_plugin.py`（读）、`examples/plugins/import_people_demo_plugin.py`（写） |
| 插件设计与决策 | `docs/development/plugin-context-design.md`、`docs/development/phase3-adr-draft.md`、`.ai/ARCHITECTURE_DECISIONS.md`（ADR-026/028） |
| 性能基线 | `tools/bench_plugin_search.py`（插件查询路径，零依赖可离线复跑，数据见 phase4 定稿 §6）、`tools/bench_recognition.py`（识别管线全网格基线，数字续记 docstring，phase6/ADR-032）、`tools/spike_batch_inference.py`（W1 批推理/线程尖刺，数据落 docstring）、`tools/spike_segment_profile.py`（W2 段内分解 + A/B 死重实验，数据落 docstring，phase7 证据） |
| Schema 初始化与迁移 | `src/photo_archiver/infrastructure/database/sqlite_connection.py`、`src/photo_archiver/infrastructure/database/alembic_runner.py`、`alembic/versions/002_split_create_ddl.py` |
| 质量验证 | `tests/`、`.github/workflows/ci.yml` |

---

> 本文件只描述当前状态；历史决策见 `.ai/ARCHITECTURE_DECISIONS.md`，当前问题见 `.ai/KNOWN_ISSUES.md`，路线图见 `.ai/business/roadmap.md`。
