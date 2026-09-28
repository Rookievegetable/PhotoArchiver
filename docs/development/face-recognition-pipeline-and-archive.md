# 人脸识别功能全链路梳理：运行、处理与归档逻辑

> 背景：owner 反馈「运行人脸识别后，所有照片状态都是：人员=未知人员 ·
> 置信度：较低（0.00）· 状态：待审核」。本文以当前代码为准，完整梳理人脸
> 识别的运行链路、结果处理逻辑与识别后的归档逻辑，并在 §7 对该现象给出
> 机制级解释与排查路径。
> **本文仅为现状梳理，不含任何代码修改。** 基线：`6bb1461`（2026-09-23）。
> 相关旧文：`analysis-face-recognition.md`（针对「0 条待审核」现象的排查
> 记录，含中文路径读图修复史），本文为其全链路升级版。

---

## 1. 结论速览（先说清楚现象是什么）

「人员=未知人员 · 置信度：较低（0.00）· 状态：待审核」三个字段分别对应：

| 界面字段 | 数据来源 | 当前值的含义 |
|---|---|---|
| 人员=未知人员 | `RecognitionResult.person_id is None` | 匹配器**没有给出任何候选人**（`match()` 返回 `None`） |
| 置信度：较低（0.00） | `RecognitionResult.confidence == 0.0` | 这是 `_analyze_one` 在「无匹配」时写入的**硬编码占位值 0.0**，不是模型算出来的相似度；`较低` 只是 0.00 落入文字分级最底档（<0.60）的措辞 |
| 状态：待审核 | `MatchStatus.PENDING` | 所有识别结果创建即 PENDING，等待人工通过/拒绝，属正常生命周期起点 |

即：**人脸大概率被成功检测到了（否则会连记录都没有），但 1:N 匹配全部未命中**。
未命中的原因只有两类（详见 §7）：

1. **候选特征集为空**——`person_embeddings` 表没有任何行。当前产品代码中
   **不存在任何「为人员登记人脸特征」的写入路径**（导入人员名单只写姓名/
   工号/部门/备注，不产生人脸向量），因此候选集恒为空，`match()` 第一步
   即返回 `None`。这是与现象吻合度最高的**结构性根因**。
2. 候选非空但全部低于阈值 0.40（余弦相似度域）——属于模型/参数问题，
   本场景可能性低（详见 §7 排查步骤可一锤定音地区分两者）。

---

## 2. 业务全景：从扫描到归档的五段链路

```text
① 扫描登记          ② 运行人脸识别           ③ 人工审核
扫描照片文件夹   →   「开始识别」按钮     →   审核中心通过/拒绝
Photo 落库           RecognitionResult         status: pending
                     (PENDING) 落库             → approved / rejected
                          │
                          ▼
              ④ 归档（仅消费 APPROVED）   ⑤ 导出（仅消费 APPROVED）
              ArchivePlanner 规划目标路径     ExportService 出报表
              → ArchiveExecutor 复制落盘
              + ArchiveRecord 落库
```

要点：**归档与导出的唯一输入是 `status=approved` 的识别结果**。待审核
（pending）与已拒绝（rejected）的照片永远不会进入归档计划。

---

## 3. 「运行人脸识别」的触发与前置门

入口：`MainWindow._on_match_clicked()`（`presentation/views/main_window.py:1354`）。

两道门，缺一不可：

1. **就绪引导门** `WorkspaceController.match_guidance()`：依次检查 人员存在 →
   照片存在 → 有待识别照片 → 模型可用（`AVAILABLE/MISSING/UNKNOWN`）。
   不满足则按钮置灰并给出原因与「下一步」直达按钮。
2. **权威门** `MatchPersonsController.start_match()`
   （`presentation/controllers/match_persons_controller.py`）：防重入
   （有任务在跑则拒绝）、无人/无照片拒绝，然后执行**续跑语义**：

```python
already_matched = self._recognition.list_first_by_photo_ids(photo_ids)
pending_ids = tuple(pid for pid in photo_ids if pid not in already_matched)
if not pending_ids:
    self.last_refusal_reason = REFUSAL_ALL_MATCHED; return None
command = MatchPersonsCommand(photo_ids=pending_ids, images=...)
```

> **续跑语义**：只要照片已有任何一条识别结果（无论通过/拒绝/未知人员），
> 本轮就不会再被提交。想全量重跑，必须先清除既有识别结果（当前无 UI 入口）。

通过两道门后组装 `MatchPersonsTask`，由 `QtWorkerExecutor` 提交到 Worker
线程执行（`workers/application_tasks.py:113`），UI 不冻结。

---


## 4. 识别管线：候选特征 → 检测 → Top-1 → 余弦匹配 → 落库

核心：`application/services/match_persons_service.py` 的
`MatchPersonsService.execute()`。

### 4.1 候选特征集构建（一切匹配的前提）

```python
def _build_candidate_embeddings(self) -> dict[UUID, FaceEmbedding]:
    return self._face_embedding_repository.list_all()   # person_embeddings 表全量
```

- 候选人 = `person_embeddings` 表（人员 id → 512 维人脸向量，JSON 序列化，
  ADR-016 禁 pickle）。
- **该表的唯一写入方法是 `SQLiteFaceEmbeddingRepository.save(person_id,
  embedding)`，而在全部产品代码（`src/`）中没有任何调用方**——仅测试与
  `tools/bench_recognition.py` 基准工具写入。导入人员名单
  （`ImportPeopleService`）只写 `people` 表的基本信息。
- 每轮运行开始时快照一次，整批共享（内存中 dict）。

### 4.2 单张照片的处理（`_analyze_one`）

```text
detect_with_embeddings(image)
  ├─ ImageUnreadableError  → MatchResult(read_failed=True)，不落记录
  ├─ 其他异常（推理失败等）→ 失败隔离：记 ERROR 带堆栈，降级为无脸，不落记录，整批继续
  └─ 正常返回 list[FaceBoxEmbedding]
       ├─ 空（无脸）→ DEBUG 日志，不落记录
       └─ 非空 → best_pair = max(pairs, key=box.confidence)   ← Top-1（ADR-017）
                 → matcher.match(embedding, candidates)
                     ├─ None        → person_id=None, confidence=0.0   ← 现象来源
                     └─ (pid, conf) → 采用之
                 → RecognitionResult(photo_id, person_id, confidence, status=PENDING)
```

读图细节（2026-09-20 修复）：`np.fromfile` + `cv2.imdecode`，Unicode/中文
路径安全；不可解码抛 `ImageUnreadableError`，完成文案单独计数
「无法读取 K 张」，不再冒充无脸。

**多人合影只产生一条记录**：Top-1 只取检测置信度最高的一张脸（裁决 #5，
Top-K/多候选明确出范围）。

### 4.3 匹配器：余弦相似度 + 阈值（`ai/similarity_matcher.py`）

```python
if not candidates:
    return None                       # ← 候选集为空，直接 None
similarity = dot(q, c) / (|q|·|c|)    # 余弦相似度，域 [-1, 1]
if similarity >= self._threshold and similarity >= best: ...   # Top-1 过阈
reported = (best + 1.0) / 2.0         # 仅展示用：映射到 [0,1]
```

- **阈值比较在余弦 [-1,1] 域**（review Major 修复：旧的 `(sim+1)/2` 映射曾把
  阈值 0.40 变成「余弦 ≥ -0.2 即命中」，几乎人人匹配）。
- **有效阈值来源 = `AppSettings.match_threshold`**（环境变量
  `MATCH_THRESHOLD` 或 `.env`，默认 **0.40**，`app/services.py:325` 在启动
  装配时一次性注入）。
- ⚠️ **设置对话框里的「匹配阈值」（`UserPreferences.match_threshold`）当前
  不会回流到匹配器**——匹配器只在启动时构造一次，无任何运行期重接线。
  改对话框阈值后重跑识别**不会改变结果**；要改有效阈值须设
  `MATCH_THRESHOLD` 环境变量并重启。（现状陈述，是否属缺陷待立项裁决。）

### 4.4 落库与并行

- 结果写入 `recognition_results` 表（`id, photo_id, person_id, status,
  confidence, created_at`，ADR-009）。
- 串行路径（`max_workers=1`）：逐张 `add()`。并行路径（默认
  `max_workers=4`，ThreadPoolExecutor，onnxruntime 推理释放 GIL，ADR-037）：
  推理并行、持久化回主线程，每消费 50 条 `add_many()` 单事务批量落库
  （崩溃丢失窗口 ≤49 条）。
- 进度上报：首末张 + 每 10 张。
- 完成文案（状态栏）：`处理 N 张 · 检出人脸 M 张（· 无法读取 K 张）` +
  ` · P 条识别结果待审核`（P = `list_pending()` 计数）。

### 4.5 日志线索（排查用）

| 日志 | 级别 | 含义 |
|---|---|---|
| `MatchPersonsService processed N photo(s) against M candidate(s)` | INFO | **M=0 ⇒ 候选特征表为空（根因 1）**；M>0 但全 0.00 ⇒ 根因 2 |
| `MatchPersonsService summary: processed=… faces_found=… unreadable=…` | INFO | 人脸检出与读图失败计数 |
| `MatchPersonsService persisted … recognition result(s)` | INFO | 实际落库条数 |
| `No faces detected in photo {id}` | DEBUG | 该照片无脸（不产生记录） |
| `Face analysis failed for photo {id} — isolated` | ERROR | 单张异常被隔离，整批继续 |

日志位置：安装版 `%LOCALAPPDATA%\PhotoArchiver\Logs\photo_archiver.log`；
源码运行 `./logs/photo_archiver.log`（`LOG_LEVEL=DEBUG` 可看到无脸明细）。


## 5. 识别结果的人工处理：审核中心

### 5.1 数据与置信度显示

- 存储：`recognition_results`（SQLite，ADR-009 阶段 B 单文件数据库；
  `photo_archiver.db`，安装版位于 `%LOCALAPPDATA%\PhotoArchiver\`）。
- 置信度文字分级（`presentation/views/review_dialog.py:90`，`confidence_band`）：
  `≥0.90 很高 / ≥0.75 较高 / ≥0.60 中等 / 其余 较低`。**纯展示**，不写库、
  不影响审核或归档。`0.00 → 较低` 即此分级的最底档措辞。
- 「未知人员」展示名：`UNKNOWN_PERSON_DISPLAY_NAME = "未知人员"`，当
  `person_id is None` 时由审核中心渲染。

### 5.2 通过 / 拒绝（`ReviewRecognitionService`）

```python
def approve(self, result_id):
    result = self._recognition_repository.find_by_id(result_id)
    if result.status is not MatchStatus.PENDING:
        raise NotPendingError(...)      # 非待审核不可重复操作
    with self._unit_of_work:            # ISSUE-005 修复：内存翻转与 DB 提交原子化
        result.approve()                # person_id 为 None 也可通过
        self._recognition_repository.update_status(...)
```

- 状态机：`pending → approved | rejected`（终态，不可回退）。
- 「通过未知人员」= 确认该照片不属于名单中的任何人，属合法操作；但归档
  按计划按人员分类，person 为空的已通过记录不归属任何人员目录（见 §6.3）。
- 审核中心 UI（`ReviewDialog`，Batch 5「可审阅而非盲批」）：顶部常驻待审核
  总数；每条记录两行——「照片={文件名}　人员={姓名}」+「置信度：{分级}
  （{精确值}）· 状态：待审核」；行缩略图经主窗口注入的异步通道加载（对话框
  零磁盘 IO，photo 缺失即无图标降级）。操作：`通过所选（n）` /
  `拒绝所选（n）` / `全部通过（N）`（二次确认，默认「否」），通过后照片墙
  角标与概览计数同轮刷新。空队列不再自动关闭对话框（Batch 2 空态）。

### 5.3 照片墙状态角标（`ui_text.py:244-248`）

| 角标 | 来源 |
|---|---|
| 待审核 | 该照片存在 PENDING 识别结果 |
| 已通过 / 已拒绝 | 该照片最新结果为 APPROVED / REJECTED |
| 未匹配 | 照片已登记但**无任何识别结果**（未跑过识别 / 无脸 / 读图失败） |
| 已归档 | 存在 success 态归档记录 |

> 注意「待审核」与「未匹配」的区别：用户看到的「待审核」恰恰说明识别
> **跑过且检出了人脸**，只是没匹配到人。

---

## 6. 识别完成后的归档逻辑

### 6.1 触发

`MainWindow` 归档动作 → `ArchiveController.preview()`（同步、无副作用，
planner 为纯领域计算）→ 预览对话框 `ArchivePreviewDialog`：首行声明范围
（全部已通过 / 已选 N 张）、目标根目录、计划条数/跳过条数、按人聚合明细、
前 8 条「源 → 目标」样本、冲突策略下拉（附后果说明）、**「仅预览」复选框
默认勾选**（owner 决策：首次归档默认不写盘；按钮随模式显示「执行试运行」/
「开始归档」，武装真实写入时按钮转危险色、默认焦点移到「取消」）→
确认后 `ArchiveController.execute()` 包 `ArchivePhotosTask` 走
`QtWorkerExecutor` 后台执行（真碰文件系统，数百张秒级）。

### 6.2 规划：`ArchivePlanner.build_plan()`

```python
for person_id in 目标人员集合:                      # 空 = 所有有 APPROVED 照片的人
    approved = recognition_repository.list_approved_by_person(person_id)
    for result in approved:
        # B3 批量归档：photo_ids 非空时只保留用户选定集
        if result.photo_id in seen_photo_ids: continue   # 同照片只规划一次
        photo = photo_repository.find_by_id(result.photo_id)
        # 跳过：照片已被并发删除 / 路径非绝对 /
        #       已有成功态归档记录（ARCHIVED/SKIPPED/RENAMED/OVERWRITTEN）
        target = path_builder.build(root, person.name, photo.captured_at, 原名)
```

- **只消费 `MatchStatus.APPROVED`**；待审核/已拒绝永远不会出现在归档计划里。
- 归档去重作用域为 **(person, photo)**（E-SG-6，2026-09-25 owner 裁决）：同一照片
  可同时归属多个 Person（Stage E 多 attribution），各自进入各自的归档记录；
  同一 (person, photo) 对不会重复归档——成功态记录（ARCHIVED/SKIPPED/RENAMED/
  OVERWRITTEN）按稳定 person_id 拦截（BLK-1，migration 008；存量无主行回退按
  姓名命中）。历史上"每照片只归档一次（1:N Top-1）"的旧语义已被本裁决取代。
- 重跑安全（review M-2）：只有成功态记录阻止再次规划；`PLANNED`（上次崩溃
  孤儿）/`DRY_RUN`（预览）/`FAILED`（失败）**允许重试**。
- planner 零 IO 副作用：不碰文件系统、不写归档记录，可反复调用于预览。

### 6.3 目标路径命名规则（`ArchivePathBuilderService`）

- 命名规则（裁决 #2）：`{archive_root}/{person_name}/{YYYY-MM-DD}/{original_name}`
  → `归档根目录\张三\2026-09-23\IMG_001.jpg`。
- 日期段取 `photo.captured_at`（拍摄时间）的日期部分；为空时降级为
  `unknown-date` 段。
- `person_name` 为空时降级为 `unknown-person` 段（正常情况下不会发生，见下）。
- 三段值均经 Domain `sanitize_windows_filename` 净化（Windows 非法字符清洗），
  净化改变了输入时记 WARNING 审计日志（ADR-036 D4）。
- **人员为空（person_id=None）的已通过记录永远不会进入归档计划**——规划器
  按人员遍历 `list_approved_by_person(person_id)`，`person_id=None` 的结果
  不归属任何人员，不会被任何人「带出」。因此「通过未知人员」的实际效果是：
  该照片退出待审核队列，但不参与归档。

### 6.4 执行：`ArchiveExecutor.execute_plan()`

- **复制而非移动**（`shutil.copy2`，保留 mtime/权限位），磁盘原件绝不删除；
  目标目录按需 `mkdir(parents=True)`。
- **写盘前双重包含校验（P2-005）**：词法级（目标须在 `archive_root` 之下）
  + 文件系统级（`resolve` 跟随 symlink/junction 后再校验），并显式拒绝
  向 symlink 目标写入——违规按 FAILED 记录，不落盘。
- **冲突策略**（目标文件已存在时；UI 下拉可选，未选时用
  `AppSettings.archive_conflict_strategy`，默认 **`skip`**）：
  - `skip`：不复制，记录 SKIPPED；
  - `overwrite`：覆盖，记录 OVERWRITTEN；
  - `rename`：复制到 `{stem}.dup-N{suffix}` 的下一个空闲兄弟名，记录 RENAMED。
- **dry_run**：只 log 不碰文件系统，但仍校验源存在与包含关系（缺源按
  FAILED 暴露），记录落 DRY_RUN——这是「该照片被预览过」的唯一持久信号。
- **记录与事务**：每项先落 `PLANNED` 记录（意图留痕），执行后翻转为
  `ARCHIVED/SKIPPED/RENAMED/OVERWRITTEN/FAILED/DRY_RUN`；整批包在
  `ArchivePhotosService` 传入的 UnitOfWork 内原子提交（review M-1：无 UoW
  时中途崩溃会留下孤儿 PLANNED 行）。
- 单条失败不拖垮整批；汇总
  `ArchiveResult(planned/archived/skipped/renamed/overwritten/dry_run/failed)`
  记 INFO 日志并回显状态栏。

### 6.5 与删除操作的联动（现状记录）

- 删除人员（`ManagePeopleService`）：连带删除其识别结果与归档记录，
  目标文件**保留在磁盘**，照片记录保留。
- 删除照片（`PhotoListController`）：归档记录保留（目标文件仍在磁盘），
  识别结果连带删除。

---


---

## 7. 与现象「全部 未知人员 / 0.00 / 待审核」的对照诊断

### 7.1 机制链复述

```text
照片含人脸（检测成功）
  → matcher.match(embedding, candidates) 返回 None
  → RecognitionResult(person_id=None, confidence=0.0, status=PENDING)
  → 审核中心渲染：人员=未知人员 · 置信度=较低（0.00）· 状态=待审核
```

`match()` 返回 `None` 的代码路径共三条（`ai/similarity_matcher.py`）：

```python
if not candidates:
    return None                       # 路径 A：候选特征集为空
query_norm = _norm(embedding.vector)
if query_norm == 0.0:
    return None                       # 路径 B：查询向量为零向量（异常嵌入）
...
for person_id, candidate in candidates.items():
    ...
    if similarity >= self._threshold and similarity >= best_confidence:
        best_id, best_confidence = person_id, similarity
if best_id is None:
    return None                       # 路径 C：所有候选最高相似度仍低于阈值
```

本现象只需区分 A 与 C（B 要求检测到的人脸向量为零向量，实践中不出现）。

### 7.2 根因判定：大概率是路径 A（候选特征表为空）

证据（全部经代码核实，非推测）：

1. `MatchPersonsService` 的候选人 100% 来自
   `face_embedding_repository.list_all()`（`person_embeddings` 表）。
2. 全仓搜索 `face_embedding_repository.save` / `.embeddings.save` 的产品代码
   调用方：**0 处**（仅 `tests/` 与 `tools/bench_recognition.py`）。
3. 「导入人员名单」（CSV/Excel）只创建 `people` 行（姓名/工号/部门/备注），
   不产生任何人脸向量——名单里的人对匹配器而言**没有脸**。
4. 因此在新部署/未做过特征登记的环境中，`candidates` 恒为空 dict，
   `match()` 第一行即返回 `None`——**每张照片**都会落
   `未知人员/0.00/待审核`，与现象完全一致。

> 即：识别管线本身工作正常（检测到了人脸、正常落库、正常进入待审核），
> 缺的是「人员 → 人脸特征」的**登记（enrollment）环节**。相关规划文档
> （人员照片导入 + 人脸聚类登记）见
> `docs/development/people-import-face-clustering-development-plan.md`，
> 尚未实现。

### 7.3 一锤定音的排查步骤

查看本次运行日志（§4.5 路径），找这一行：

```text
MatchPersonsService processed 473 photo(s) against 0 candidate(s)
```

- `against 0 candidate(s)` → **路径 A 坐实**：候选特征表为空，需先实现/
  执行特征登记，识别才有意义。
- `against N candidate(s)`（N>0）→ 路径 C：所有人脸相似度都低于阈值
  0.40，转模型/参数排查（照片质量、侧脸、阈值是否被 `MATCH_THRESHOLD`
  环境变量抬高）。

辅助 SQL（安装版数据库 `%LOCALAPPDATA%\PhotoArchiver\photo_archiver.db`）：

```sql
SELECT COUNT(*) FROM person_embeddings;   -- 0 ⇒ 路径 A
SELECT COUNT(*) FROM recognition_results WHERE person_id IS NULL;
SELECT COUNT(*) FROM recognition_results WHERE status='pending';
```

### 7.4 两个顺带的现状发现（仅记录，不在本文修复）

1. **设置对话框的「匹配阈值」不影响实际识别**（§4.3）：匹配器阈值在启动
   装配时从 `AppSettings`（env/`.env`）取定，用户偏好阈值只进 QSettings，
   无运行期重接线。改对话框阈值不会撞库，但会让用户产生「已调参」的错觉。
2. **全量重跑无 UI 入口**（§3）：已有任何识别结果的照片会被续跑语义跳过；
   若想用新的候选特征/阈值重跑，只能清 `recognition_results` 表。

---

## 8. 关键文件索引

| 环节 | 文件 |
|---|---|
| 运行入口/双重门/状态栏 | `presentation/views/main_window.py`、`presentation/controllers/match_persons_controller.py` |
| 识别编排（核心） | `application/services/match_persons_service.py` |
| 候选特征仓储 | `infrastructure/database/sqlite_face_embedding_repository.py`、`domain/repositories/face_embedding_repository.py` |
| 检测/识别适配器 | `ai/insightface_detector.py`、`ai/insightface_recognizer.py`、`infrastructure/ai/insightface_loader.py` |
| 匹配器（余弦+阈值） | `ai/similarity_matcher.py` |
| 结果落库 | `infrastructure/database/sqlite_recognition_repository.py`、`domain/entities/recognition.py` |
| 审核/置信度分级 | `application/services/review_recognition_service.py`、`presentation/views/review_dialog.py`、`presentation/controllers/review_controller.py` |
| 装配/阈值注入 | `app/services.py`（`_build_match_service`）、`infrastructure/config/settings.py` |
| 归档规划/路径/执行 | `application/services/archive_planner.py`、`archive_path_builder_service.py`、`archive_executor.py`、`archive_photos_service.py` |
| 归档 UI | `presentation/controllers/archive_controller.py`、`presentation/views/archive_preview_dialog.py` |
| 角标/文案 | `presentation/ui_text.py` |
| 后台任务 | `workers/application_tasks.py`（`MatchPersonsTask`/`ArchivePhotosTask`）、`workers/qt_executor.py` |
| 基准工具（唯一写特征的非测试代码） | `tools/bench_recognition.py` |
| 旧排查文档 | `docs/development/analysis-face-recognition.md` |
| 特征登记规划（未实现） | `docs/development/people-import-face-clustering-development-plan.md` |

---
