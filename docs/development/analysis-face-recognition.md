# 运行人脸识别 业务逻辑分析（配合验收问题排查）

> 背景：UI/UX 验收第 3 项发现"识别完成 · 0 条识别结果待审核"，与
> "照片按识别结果分类"的预期不符。本文详细解释人脸识别的完整实现逻辑并
> 附带关键步骤源码，末节给出与该现象的对照分析（含一个重要的功能性发现）。
> **本文仅为现状分析，不含任何代码修改。** 基线：`30dedd2`（2026-09-19）。

---

## 1. 业务流程总览

```text
用户点「运行人脸识别」
  → MainWindow._on_match_clicked()
      → WorkspaceController.match_guidance()      第一道缓存就绪门（Batch 2）
      → MatchPersonsController.start_match()      第二道权威门（数据前置条件）
          → 组装 MatchPersonsCommand（只含"尚无识别结果"的照片）
      → MatchPersonsTask（Worker 线程执行）
  → MatchPersonsService.execute()                 Application 层管线
      → FaceEmbeddingRepository.list_all()        候选人特征（person_id → 512 维向量）
      → 逐张照片（可多线程）：
          InsightFaceDetector.detect_with_embeddings(image)   检出人脸 + 特征
          → 无脸：MatchResult(box=None)，不落任何记录
          → 有脸：取检测置信度最高的一张脸（Top-1）
              → CosinePersonMatcher.match(特征, 候选)   1:N 余弦相似度
              → RecognitionResult(PENDING) 持久化（person_id 可能为 None）
  → completed 信号 → 状态栏"识别完成" + " · N 条识别结果待审核"
      （N = ReviewController.list_pending()，即 PENDING 状态记录数）
```

---

## 2. 关键步骤源码解析

### 2.1 入口双重门：就绪引导 + 权威拒绝

`presentation/views/main_window.py`：

```python
def _on_match_clicked(self) -> None:
    guidance = self._workspace_controller.match_guidance()
    if not guidance.enabled:
        # 缺人员 / 缺照片 / 全部已识别 / 模型缺失 → 置灰原因 + 下一步按钮
        self._status_label.setText(guidance.tooltip)
        return
    runnable = self._match_controller.start_match()
    if runnable is None:
        reason = self._match_controller.last_refusal_reason
        self._status_label.setText(reason or STATUS_MATCH_UNAVAILABLE)
        return
    ...
    self._connect_task_signals(runnable, self._match_controller.connect_signals)
```

就绪门（Batch 2 的 `match_guidance`）依次检查：人员存在 → 照片存在 →
有待识别照片 → 模型可用（`AVAILABLE/MISSING/UNKNOWN`）。任何一环不满足都会
**置灰并给出原因与"下一步"直达按钮**。

### 2.2 控制器：续跑语义（只提交没有识别结果的照片）

`presentation/controllers/match_persons_controller.py`：

```python
def start_match(self):
    if self._active_runnable is not None:
        self.last_refusal_reason = REFUSAL_MATCH_IN_FLIGHT; return None
    if not self._people.list_all():
        self.last_refusal_reason = REFUSAL_NO_PERSONS; return None
    photos = self._photos.list_all()
    if not photos:
        self.last_refusal_reason = REFUSAL_NO_PHOTOS; return None
    photo_ids = tuple(photo.id for photo in photos if photo.id is not None)
    already_matched = self._recognition.list_first_by_photo_ids(photo_ids)
    pending_ids = tuple(pid for pid in photo_ids if pid not in already_matched)
    if not pending_ids:
        self.last_refusal_reason = REFUSAL_ALL_MATCHED; return None
    command = MatchPersonsCommand(
        photo_ids=pending_ids,
        images=tuple(photo.path.raw_path for photo in photos
                     if photo.id in pending_set),     # ← 用原始路径读图
    )
    task = MatchPersonsTask(self._use_case, command)
    runnable = self._executor.submit(task)
```

要点：**只要一张照片已有任何识别结果（无论通过/拒绝/未知），它就不会被再次
提交**（续跑防重复）。`images` 用的是扫描时登记的**原始磁盘路径**。

### 2.3 服务管线：候选特征 → 检测 → Top-1 → 余弦匹配

`application/services/match_persons_service.py`：

```python
def execute(self, command: MatchPersonsCommand):
    candidates = self._build_candidate_embeddings()   # ← person_id → 特征
    ...
    for index, (photo_id, image) in enumerate(
        zip(command.photo_ids, command.images), start=1):
        result = self._match_one(photo_id, image, candidates)
        ...

def _build_candidate_embeddings(self) -> dict[UUID, FaceEmbedding]:
    """Return person_id → embedding for every known person."""
    return self._face_embedding_repository.list_all()
```

单张照片的处理（`_analyze_one`，顺序与并行路径共用）：

```python
try:
    pairs = self._detector.detect_with_embeddings(image)   # InsightFace 单次推理
    if not pairs:
        logger.debug("No faces detected in photo {}", photo_id)
        return MatchResult(photo_id=photo_id, box=None), None   # ← 不落任何记录

    best_pair = max(pairs, key=lambda p: p.box.confidence or 0.0)  # ← 只取一张脸
    embedding = best_pair.embedding
    match = self._matcher.match(embedding, candidates)     # 1:N Top-1 余弦匹配

    person_id: UUID | None = None
    confidence = 0.0
    if match is not None:
        person_id, confidence = match
    recognition = RecognitionResult(
        photo_id=photo_id, confidence=confidence, person_id=person_id,
    )                                                        # ← status 默认 PENDING
    return MatchResult(photo_id=photo_id, box=best_pair.box), recognition
except Exception:
    # 失败隔离：单张异常不中断整批，该照片降级为"无脸"（同样不落记录）
    logger.exception("Face analysis failed for photo {} — isolated", photo_id)
    return MatchResult(photo_id=photo_id, box=None), None
```

匹配器（`ai/similarity_matcher.py`）：余弦相似度 Top-1，阈值来自
`AppSettings.match_threshold`（默认 **0.40**）；无候选时必然返回 `None`。

**"待审核"的确切含义**：`RecognitionResult` 创建即 `PENDING` 状态（含
`person_id=None` 的未匹配结果），审核对话框 `list_pending()` 按
`status = 'pending'` 查询。**照片没有检出人脸 → 该照片不产生任何记录 → 也不
出现在待审核里。**

### 2.4 模型装配：缺模型时诚实失败

`app/services.py`：

```python
loader = InsightFaceLoader(model_root=settings.model_path)
if not loader.is_available():
    return _UnavailableMatchService(ModelPackMissing(
        f"InsightFace model pack not found at {loader.pack_path}; "
        "run scripts/download_models.py to fetch it"))
analysis = loader.load()
detector = InsightFaceDetector(analysis)
recognizer = InsightFaceRecognizer(analysis)
matcher = CosinePersonMatcher(threshold=settings.match_threshold)
return MatchPersonsService(..., max_workers=settings.max_workers)
```

缺模型 → 执行时抛 `ModelPackMissing` → 任务 `failed` 信号 → UI 显示失败
（不会出现"识别完成"）。因此"识别完成"意味着模型已成功加载并跑完了推理。

### 2.5 完成反馈："识别完成 · 0 条识别结果待审核"的来源

`presentation/views/main_window.py`：

```python
def _refresh_review_pending(self) -> None:
    """Re-query recognition results so newly created PENDING entries surface."""
    pending = self._review_controller.list_pending()
    self._status_label.setText(
        self._status_label.text() + " · "
        + STATUS_PENDING_REVIEW_COUNT.format(count=len(pending)))
```

`list_pending()` 查的是数据库 `recognition_results` 表中 `status='pending'`
的行。**显示 0 条 = 本次识别（以及此前所有运行）没有给任何照片留下 PENDING
记录。** 结合 2.3：只有"检出了人脸"才会落记录，所以 0 条 ⇒ 所有提交的照片
都没有检出人脸，或全部单张分析抛异常被隔离。

---

## 3. 与验收现象"识别完成 · 0 条识别结果待审核"的对照分析

### 3.1 可能成因（按可能性排序）

| # | 成因 | 判定方法 |
|---|---|---|
| 1 | **照片文件已不在原路径**（扫描后移动/删除/换盘/网盘未同步）——解码失败走异常隔离，静默无记录 | 日志中搜 `Face analysis failed for photo`，会有带堆栈的记录 |
| 2 | **照片确实无人脸或人脸不可检**（远景/侧脸/遮挡/分辨率过低） | 日志 DEBUG 级有 `No faces detected in photo {id}`（默认 INFO 级不可见，见 §4） |
| 3 | **图像解码失败**（损坏文件/不支持的编码格式） | 同成因 1，异常堆栈在日志中 |
| 4 | 此前某次运行已给这些照片留下过识别记录（本次全部跳过，即使之前运行其实失败） | 数据库 `recognition_results` 行数 vs 照片数 |

### 3.2 一个重要的功能性发现（与"按识别结果分类"预期直接相关）

**当前产品中不存在"登记人员人脸样本"的功能。** 全代码检索证实：

- 候选特征唯一来源是 `FaceEmbeddingRepository.list_all()`（人脸特征表）；
- 但该表的写入方法 `SQLiteFaceEmbeddingRepository.save(person_id, embedding)`
  **在整个产品代码（src/）中没有任何调用方**——导入人员只写 `Person` 基本信息
  （姓名/工号/部门/备注），不产生任何人脸特征；
- 因此**候选集恒为空字典**，`CosinePersonMatcher.match` 对任何检出的人脸都
  返回 `None`；
- 后果：即使照片成功检出人脸，产生的识别结果也全部是 `person_id=None` 的
  **"未知人员"待审核记录**，不可能与已导入的人员姓名关联；
- 另注意：**每张照片只取检测置信度最高的 1 张脸**（Top-1，裁决 #5），多人
  合影只会产生一条记录。

换言之：识别管线的"检测/提特征"半边是通的，"与人员关联"的半边缺少特征来源
——这不是本次验收操作的问题，而是当前产品能力边界（1:N 匹配的人脸样本登记
能力尚未实现）。这与导入人员格式问题相互独立：即使名单格式完全正确，识别
结果也无法按人员分类。

### 3.3 建议的排查顺序（不改代码）

1. 打开日志文件（路径见 §4），搜索 `Face analysis failed`——有则按堆栈处理
   （多为文件路径/解码问题，对应成因 1/3）；
2. 临时把 `LOG_LEVEL` 环境变量设为 `DEBUG` 后重跑识别，看
   `No faces detected in photo` 出现的张数（成因 2 定量确认）；
3. 搜索日志中 `MatchPersonsService processed N photo(s) against M candidate(s)`
   ——**M 一定为 0**，可直接印证 §3.2 的候选集为空；
4. 核对照片墙中照片是否可见（照片墙缩略图正常 = 原文件可读，可排除成因 1/3）。

---

## 4. 配合排查的运行日志

项目使用 Loguru，双汇出（控制台 stderr + 文件），配置位于
`infrastructure/logging/configuration.py`：

| 项 | 值 |
|---|---|
| 安装版日志目录 | `%LOCALAPPDATA%\PhotoArchiver\Logs\photo_archiver.log` |
| 源码运行（默认） | `./logs/photo_archiver.log`（可用 `LOG_DIRECTORY` 环境变量覆盖） |
| 默认级别 | `INFO`（`LOG_LEVEL` 环境变量可调至 `DEBUG`） |
| 轮转/保留 | 单文件 10 MB，保留 30 天 |
| 格式 | `时间 \| 级别 \| 模块:函数:行 - 消息` |

与本问题直接相关的日志语句：

| 日志内容 | 级别 | 含义 |
|---|---|---|
| `MatchPersonsService processed N photo(s) against M candidate(s)` | INFO | 本轮提交张数与候选人数（M 恒为 0 ⇒ 特征集为空） |
| `No faces detected in photo {id}` | **DEBUG** | 该照片未检出人脸（默认级别下不落盘） |
| `Face analysis failed for photo {id} — isolated` | ERROR | 单张分析异常（含完整堆栈；整批不受影响） |
| `MatchPersonsService persisted N recognition result(s)` | INFO | 实际持久化的识别记录数 |
| `ListPersonsService: N person(s) available for filtering` | INFO | 库内人员数（验证导入结果） |

---

## 6. 实证更新（2026-09-20，依据人工验收会话日志与数据库只读检查）

§3.1 的成因已由运行记录定量证实，**直接根因是成因 1 的一个具体技术形态**：

- 识别两次运行共提交 473 张照片，产生 **946 条**
  `InsightFaceDetector could not read image` WARNING（= 2 × 473，全军覆没）；
  `MatchPersonsService persisted 0 recognition result(s)`、
  `processed 473 photo(s) against 0 candidate(s)`——与"识别完成 · 0 条待审核"完全吻合。
- 根因代码：`ai/insightface_detector.py` 的 `_read_and_detect` 使用
  `cv2.imread(str(image))`。**OpenCV 的 imread 在 Windows 上不支持非 ASCII
  （中文）路径**，返回 None 后被当作"无脸"静默跳过。本次照片全部位于
  `E:\BaiduNetdiskDownload\美至大2黄磊\1组\1曹徽文\...`（中文目录）。
- 对照证据：照片墙缩略图正常（Pillow 读图支持 Unicode 路径），扫描登记
  473 张成功，唯独 cv2 读图失败——问题被精确定位在检测器的读图这一行。
- 数据库佐证（只读）：`recognition_results=0`、`person_embeddings=0`、
  `photos=473`、`people=9`（名单合并问题见 §3.2 与导入分析文档 §3）。
- 修复方向（供立项参考，本文档不实施）：标准做法是
  `cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)` 或
  改用 Pillow 解码后转 ndarray；同时把"读取失败张数"纳入识别完成文案，
  杜绝 473/473 失败却显示"识别完成"的静默误导。

> **✅ 已修复（2026-09-20，本节所述两项均已落地）**：①检测器读图改为
> `np.fromfile` + `cv2.imdecode`（Unicode 安全），不可解码文件抛
> `ImageUnreadableError`（新增域异常），不再冒充"无脸"；②`MatchResult`
> 新增 `read_failed` 字段，识别完成文案携带
> 「处理 N 张 · 检出人脸 M 张 · 无法读取 K 张（文件缺失或路径不可用）」，
> 服务层同步输出 processed/faces_found/unreadable 汇总日志。
> 端到端实证：真实模型对中文路径照片检出 1 张脸（512 维特征）；
> 回归测试见 `tests/unit/ai/test_insightface_workflow.py`（中文路径、
> 不可解码、文件缺失）与 `test_match_persons_service.py`（read_failed
> 串行/并行双路径）、`test_match_ui_wiring.py`（完成文案计数）。

## 5. 相关文件索引

| 职责 | 文件 |
|---|---|
| UI 入口（双重门） | `src/photo_archiver/presentation/views/main_window.py`（`_on_match_clicked`/`_refresh_review_pending`） |
| 控制器（前置条件 + 续跑） | `src/photo_archiver/presentation/controllers/match_persons_controller.py` |
| 识别管线 | `src/photo_archiver/application/services/match_persons_service.py` |
| 人脸检测适配器 | `src/photo_archiver/ai/insightface_detector.py` |
| 余弦匹配器 | `src/photo_archiver/ai/similarity_matcher.py` |
| 模型装配 | `src/photo_archiver/app/services.py`（`build_match_persons_service`） |
| 人脸特征仓储 | `src/photo_archiver/infrastructure/database/sqlite_face_embedding_repository.py` |
| 识别结果仓储 | `src/photo_archiver/infrastructure/database/sqlite_recognition_repository.py`（`list_pending`） |
| 日志配置 | `src/photo_archiver/infrastructure/logging/configuration.py` |
