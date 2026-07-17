# PhotoArchiver 会话间交接文档

> 生成时间：2026-07-17 18:12（本地） ｜ 生成者：AtomCode (GLM-5.2) ｜ 会话范围：Phase 2 Step 8-10 + 三轮 Review + P0-P3 修复
> 新会话入职顺序：① 本文档 ② `AI_ONBOARDING.md` ③ `.ai/Consistency-Audit-2026-07-13.md` ④ 本文 §6 未决事项

---

## 1. 本会话完成的工作

### 1.1 Phase 2 Step 8-10 实现（3 commits）

| Step | commit | 内容 |
|---|---|---|
| Step 8 | `8d245ab` | AI 识别预备：FaceBox/FaceEmbedding 值对象、RecognitionResult 实体 + MatchStatus enum、FaceDetector/Recognizer/Matcher 三端口 Protocol、检测/识别/匹配 DTO、InsightFaceDetector stub、21 契约测试 |
| Step 9 | `75a865d` | 真实 InsightFace detector/recognizer/matcher 实现、RecognitionRepository + SQLite 实现、recognition_results 表（PRAGMA v2）、scripts/download_models.py、requirements 补 insightface/onnxruntime |
| Step 10 | `947b428` | MatchPersonsService（detect→extract→match→persist 闭环，1:N Top-1）、ReviewRecognitionService（approve/reject/bulk_approve/bulk_reject）、AppSettings.match_threshold、E2E 集成测试 |

### 1.2 三轮 Review 与修复（7 commits）

| 轮次 | commit | 范围 | 结果 |
|---|---|---|---|
| 第一轮 Review | — | 评审 Step 8-10，出 0 Critical / 6 Major / 10 Minor | — |
| 第一轮修复 | `002e3b6` `b66de27` | 架构拆分（ai→infrastructure/ai/InsightFaceLoader）+ M-1~M-5 + m-1~m-10 | 138 passed |
| 第二轮 Review | — | 评审修复，出 1 Critical（C-1 pickle）/ 3 Major / 10 Minor | — |
| 第二轮修复 | `e3bcbfb` `25ed13a` | C-1 pickle→JSON、M-1 补测试、M-2 内存注释、M-3 update_status 返回 int、m-1~m-10 | 143 passed |
| 第三轮 Review | — | 收尾评审，0 Critical / 0 Major / 3 Minor（全延后） | **可 merge** |

### 1.3 P0-P3 问题清单核验与修复（3 commits）

| 批次 | commit | 修复项 |
|---|---|---|
| A（必修） | `1e1bc45` | P0 qt_executor 补日志、P1-b scan N+1→预取去重、P1-c UI 取消按钮/失败详情 |
| B（应修） | `4415d23` | P1-a except 收窄、P1-d 嵌套事务文档、P2-a max_workers 绑定、P2-b 删 model_path 惰建、P2-c cache 防御、P2-d 相对路径统一 |
| C（延后处置） | `a118bf5` | P3-a base.txt 保留注释、P3-b FolderRepository docstring；P3-c 合并 P1-c；P3-d 延后 |

**最终 HEAD**：`a118bf5`，工作树干净，pytest **143 passed / 8 skipped**（8 skip = 缺模型集成测试），ruff/mypy clean。

---

## 2. 当前代码状态快照

### 2.1 Phase 2 进度

| Step | 状态 | commit |
|---|---|---|
| 7 缩略图缓存 | ✅ 已完成（上一会话 `4d48a5c`） | — |
| 8 AI 检测端口 + DTO | ✅ 已完成 | `8d245ab` |
| 9 AI InsightFace 实现 + 识别闭环 | ✅ 已完成 | `75a865d` |
| 10 用户复核数据模型 | ✅ 已完成 | `947b428` |
| 11 归档组织 + 去重 | ⛔ **未开始** — 待裁决 §6.1 | — |
| 12 完整 UI 工作台 | ⛔ 未开始 | — |
| 13 设置持久化 | ⛔ 未开始 | — |

### 2.2 数据库 Schema 版本

`PRAGMA user_version = 3`，含 4 表：`people` / `folders` / `photos` / `recognition_results`（Step 9 建）/ `person_embeddings`（Step 10 M-1 修建）。

### 2.3 依赖状态

`requirements/base.txt` 已含 `insightface==1.0.1` + `onnxruntime==1.27.0`。SQLAlchemy/Alembic 保留（审计 C-7 决策，注释已标）。

---

## 3. 保留的 6 项 Phase 2 裁决（全 Phase 2 适用）

| # | 裁决 | 落地状态 |
|---|---|---|
| 1 | recognition_results 表 Schema：id, photo_id, person_id, status, confidence, created_at，FK photos/people | ✅ Step 9 |
| 2 | 归档目录命名：`{archive_root}/{person_name}/{event_or_date}/{original_name}` | ⛔ Step 11 待落代码 |
| 3 | 路径冲突策略：默认 skip，可配 overwrite / rename | ⛔ Step 11 待落代码 |
| 4 | AI 模型文件位置：`resources/models/`，不提交 Git，走 download_models.py | ✅ Step 9 |
| 5 | 缩略图缓存目录：`data/cache/thumbnails/` | ✅ Step 7 |
| 6 | Git：每 Step 完成后独立提交 | ✅ 全程遵守 |

---

## 4. 关键架构决策（本会话确立）

1. **ai 层职责拆分**：`ai/` 只做检测/识别/匹配，`infrastructure/ai/InsightFaceLoader` 持模型加载+路径探测。DEP-050 合规。
2. **FaceEmbedding 持 tuple 不持 numpy**：Domain 层零框架依赖。
3. **Embedding 序列化用 JSON 非 pickle**：SEC-030，pickle.loads 是任意代码执行向量。
4. **匹配策略固定 1:N Top-1**：`max(boxes, key=confidence)` 锁定检测置信度最高的脸。Top-K/多候选留后续版本。
5. **MatchResult.box 字段 `FaceBox | None`**：无人脸时 box=None，契约诚实。
6. **update_status 返回 int（受影响行数）**：service 检查 0 防并发删除静默失败。
7. **ensure_runtime_directories 不建 model_path**：loader/download_models.py 自管，避免隐藏 AI 依赖。

---

## 5. 已知技术债与延后项

| 项 | 延后到 | 理由 |
|---|---|---|
| recognizer.extract 双检测 | Step 12 Worker | 批量 detect+extract 单次 get 可 halve 成本；本轮 Application-only 范围可接受 |
| 结构化埋点（logger.bind task_id/folder_id） | Step 12 | 需 Worker 接入后统一规划，当前无 task_id 概念 |
| FaceEmbeddingRepository.list_all 分页 | Step 12 | Person 数千时内存压力，当前量小可接受 |
| SQLAlchemy/Alembic 引入 | roadmap Step 3 | 审计 C-7 决策保留，PRAGMA user_version 足够当前 |
| 既有文件 3 个 ruff 未用导入 + 16 个 mypy 类型错 | 单独清理轮 | 在 unit_of_work/sqlite_unit_of_work/application_tasks/register_photo_service/qt_executor/main_window/scan_controller，非本轮引入 |
| RecognitionResult.id 类型 `UUID | None` 靠 type: ignore | 未来重构 | __post_init__ 保证非空但类型签名未表达，应改 UUID 非 None |
| ReviewRecognitionService 无事务边界 | Step 11 | 若 update_status 异常，内存已 approve 而 DB 未 approve；Step 11 archive 应包 UnitOfWork |

---

## 6. 未决事项（新会话首要处理）

### 6.1 Phase 2 Step 11 启动需 3 项裁决

| # | 待裁决 | 我的建议 |
|---|---|---|
| 1 | `archive_root` 配置位置：走既有 `AppSettings.output_root`（默认 None）还是新增独立 `AppSettings.archive_root`？ | 新增独立字段，语义更清晰 |
| 2 | `{event_or_date}` 段来源：从 `Photo.created_at` 取日期（格式？）还是留空跳过？ | 取 EXIF DateTimeOriginal 或文件 mtime，格式 YYYY-MM-DD |
| 3 | dry-run 模式：本轮就建 `--dry-run` 旗标只 log 不 copy/move，还是推迟？ | 本轮建，roadmap Step 11 验收列了"dry-run 建议" |

### 6.2 样例图与模型包（集成测试前置）

- `tests/integration/resources/sample_face.jpg` 已提交（NASA CC0 astronaut，68KB）
- buffalo_l 模型包**未下载**（裁决禁止自动），CI 需预跑 `python scripts/download_models.py`
- 集成测试 8 条 skip 全因缺模型

### 6.3 既有飘带（非本会话引入）

上一轮 P0-P3 核验时发现既有文件有 3 个 ruff 未用导入 + 16 个 mypy 类型错，全在 Step 8-10 之前的文件。建议新会话单独开一轮清理，不混入 Step 11。

---

## 7. 建议新会话第一步

1. 读本交接文档 §6.1，给出 Step 11 的 3 项裁决
2. 裁决后我（或新会话的 AI）按 `.ai/TASK_WORKFLOW.md` 执行 Step 11：
   - 建 `ArchivePathBuilder`（落裁决 #2 命名规则）
   - 建 `ArchiveConflictStrategy` enum + AppSettings 字段（落裁决 #3）
   - 建 `ArchiveService` + `ArchiveRecord` 实体
   - 建 `--dry-run` 旗标（若裁决 #3 批准）
   - 单元测试 + 集成测试
   - 独立提交

3. Step 11 完成后报告 Step 12 前置就绪状态

---

## 8. 关键文件索引

| 职责 | 文件 |
|---|---|
| AI 模型加载 | `src/photo_archiver/infrastructure/ai/insightface_loader.py` |
| AI 检测/识别/匹配 | `src/photo_archiver/ai/insightface_detector.py` + `insightface_recognizer.py` + `similarity_matcher.py` |
| 匹配服务 | `src/photo_archiver/application/services/match_persons_service.py` |
| 审核服务 | `src/photo_archiver/application/services/review_recognition_service.py` |
| Embedding 持久化 | `src/photo_archiver/infrastructure/database/sqlite_face_embedding_repository.py` |
| Recognition 持久化 | `src/photo_archiver/infrastructure/database/sqlite_recognition_repository.py` |
| Schema 定义 | `src/photo_archiver/infrastructure/database/sqlite_connection.py`（PRAGMA v3） |
| 模型下载 | `scripts/download_models.py` |
| 集成测试 | `tests/integration/face_detection/test_insightface_workflow.py` + `test_step10_e2e.py` |

---

## 9. Git 提交链（本会话 10 commits）

```
a118bf5 fix(docs): fix P3-a/b reserved-dependency note + FolderRepository upsert docstring
4415d23 fix(services/infra): fix P1-a/d + P2-a/b/c/d
1e1bc45 fix(workers/ui): fix P0 qt_executor logging + P1-b scan N+1 + P1-c cancel/error detail
25ed13a fix(recognition): fix second-round Major M-2/M-3 + Minor m-1 through m-10
e3bcbfb fix(recognition): fix Critical C-1 (pickle deserialization) + Major M-1 (missing tests)
b66de27 fix(recognition): address Minor review findings m-1 through m-10
002e3b6 fix(recognition): address Major review findings M-1 through M-5 + architecture split
947b428 feat(recognition): add Phase 2 Step 10 matching service and user-review workflow
75a865d feat(recognition): wire Phase 2 Step 9 real InsightFace detector, recognizer and matcher
8d245ab feat(recognition): add Phase 2 Step 8 AI recognition ports, DTOs and stub detector
```

---

*交接完毕。新会话从 §6.1 的 3 项裁决开始即可。*
