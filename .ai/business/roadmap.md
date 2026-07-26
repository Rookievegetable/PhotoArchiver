# PhotoArchiver 开发路线图与分步交付清单

Version: 1.1.1

Status: Stable

Last Updated: 2026-07-26

---

# 1. Purpose

本文档定义 PhotoArchiver 的 15 步开发顺序，以及每步的：

- 交付物清单
- 涉及目录
- 验收标准

并纳入 Application 层、Repository 模式、User Review、测试与装配等补充项。

每步完成后再进入下一步，避免跨步返工。

> 📌 **Phase 1 历史路线图已并入**（2026-07-24 裁决3授权执行）：原 `docs/roadmap/phase-1-core-workflow.md` 已物理删除，其权威信息（Phase 1 目标 / 完成状态 / 开发顺序 / 阶段完成标准 / 约束）由本文件 §2-§17 正文承载，人类入口历史快照见 `README.md` 已完成段。删除理由：双路线图无存在必要，phase-1 横幅已并入本文件，避免分散承载漂移。

---

# 2. 开发顺序总览

| Step | 名称 | 核心交付 |
|------|------|----------|
| 0.5 | Walking Skeleton（建议） | 最小可运行闭环 |
| 1 | Logging | 统一日志体系 |
| 2 | Configuration | 集中配置加载 |
| 3 | Database | Schema + 迁移 + Repository 实现 |
| 4 | Domain Model | 实体、值对象、仓储接口 |
| 5 | Excel Import | 人员信息导入 |
| 6 | Folder Scanner | 目录扫描与元数据 |
| 7 | Thumbnail Generator | 缩略图生成 |
| 8 | Face Detection | 人脸检测 |
| 9 | Face Recognition | 人脸特征提取 |
| 10 | Matching Engine | 人员匹配 + 审核状态 |
| 11 | Archive Generator | 归档整理 |
| 12 | Main UI | 正式主界面 |
| 13 | Settings | 设置与偏好 |
| 14 | Export | 报告导出 |
| 15 | Plugin System | 插件扩展机制 |

---

# 3. 建议里程碑

| 里程碑 | 完成 Step | 可演示能力 |
|--------|-----------|------------|
| M1 基础就绪 | 1–4 (+0.5) | 启动、配置、建库、领域模型 |
| M2 数据入口 | 5–6 | 导入人员、扫描照片 |
| M3 媒体管线 | 7 | 缩略图、列表预览数据就绪 |
| M4 AI 管线 | 8–10 | 检测、识别、匹配与审核 |
| M5 归档闭环 | 11 | 审核通过后自动归档 |
| M6 产品化 | 12–14 | 完整 UI、设置、导出 |
| M7 可扩展 | 15 | 插件加载 |

---

# 4. 每步通用验收（所有 Step 均需满足）

- [ ] 架构分层正确，无 forbidden imports
- [ ] 公共 API 有 type hints；public 类/函数有 docstring
- [ ] 使用 Loguru，无 `print()`
- [ ] Ruff / MyPy 通过
- [ ] 本 Step 相关测试通过
- [ ] 无占位 `pass` / TODO 留在生产路径
- [ ] 提交信息符合 Conventional Commits

---

# 5. Step 0.5 — Walking Skeleton（建议，在 Step 5 前完成）

## 交付物清单

- [ ] `app/` 依赖装配入口（Composition Root 雏形）
- [ ] 一条端到端演示路径：启动 → 读配置 → 连库 → 写入/读取一条测试数据 → 日志可见
- [ ] 首个 Alembic migration 可执行
- [ ] 首个 Repository 集成测试（或 smoke test）
- [ ] CI 或本地脚本：`ruff` + `mypy` + `pytest` 可跑

## 涉及目录

```text
main.py
src/photo_archiver/app/
src/photo_archiver/common/
src/photo_archiver/domain/
src/photo_archiver/infrastructure/database/
src/photo_archiver/infrastructure/repositories/
tests/integration/
alembic/                    # 若采用 Alembic
```

## 验收标准

- [ ] `python main.py` 能启动，无未捕获异常
- [ ] 日志文件与控制台均有输出
- [ ] 数据库文件/连接按配置创建成功
- [ ] `pytest` 至少 1 个集成测试通过
- [ ] 无 Presentation 直接访问 SQLite
- [ ] 无 Domain 依赖 PySide6 / OpenCV 等框架

---

# 6. Step 1 — Logging

## 交付物清单

- [ ] Loguru 统一配置（控制台 + 文件）
- [ ] 日志级别可配置（与 Step 2 预留接口）
- [ ] 日志格式、轮转、保留策略常量化
- [ ] 日志目录自动创建
- [ ] 启动时记录应用版本/环境（可选）
- [ ] 单元测试：配置函数可被调用且不抛异常

## 涉及目录

```text
main.py
src/photo_archiver/infrastructure/logging/
  ├── __init__.py
  └── configuration.py
logs/                       # 运行时生成
tests/unit/infrastructure/logging/
```

## 验收标准

- [ ] 禁止使用 `print()` 输出运行信息
- [ ] 默认写入 `logs/photo_archiver.log`
- [ ] 支持 `INFO` / `DEBUG` 等级切换（硬编码或读 env 均可，Step 2 再完全打通）
- [ ] 日志格式含：时间、级别、模块、行号、消息
- [ ] 文件轮转与保留策略生效（可手动验证大文件或 mock）
- [ ] Worker 线程写日志不导致崩溃（Step 5+ 再正式验证，此处架构上无阻塞即可）
- [ ] Ruff / MyPy 无新增告警

**当前状态**：基础已实现，本 Step 以验收 + 与 Config 对接预留为主。

---

# 7. Step 2 — Configuration

## 交付物清单

- [ ] `AppSettings`（pydantic-settings）
- [ ] 支持 `.env` + 环境变量
- [ ] 配置项：`APP_NAME`、`APP_VERSION`、`ENV`、`DEBUG`、`LOG_LEVEL`
- [ ] 路径类：`DATABASE_URL`、`MODEL_PATH`、`PHOTO_ROOT`、`OUTPUT_ROOT`
- [ ] 运行时：`MAX_WORKERS`
- [ ] 配置校验与默认值文档
- [ ] 更新 `.env.example`
- [ ] 单元测试：默认值、覆盖、非法值校验

## 涉及目录

```text
.env.example
config/                     # 可选：静态默认配置
src/photo_archiver/infrastructure/config/
  ├── __init__.py
  └── settings.py
src/photo_archiver/app/application.py   # 注入/读取 settings
src/photo_archiver/infrastructure/logging/configuration.py  # 读 LOG_LEVEL
tests/unit/infrastructure/config/
docs/deployment/            # 可选：配置说明
```

## 验收标准

- [ ] 无硬编码业务路径（如数据库、模型、导入根目录）
- [ ] 缺失 `.env` 时使用合理默认值，应用仍可启动
- [ ] 非法 `LOG_LEVEL` / `DATABASE_URL` 有明确错误信息
- [ ] Logging 读取 `LOG_LEVEL`（或 `DEBUG` 联动）
- [ ] 配置对象在 `app/` 层创建，其他层通过注入或参数获取
- [ ] 不在 Widget / Domain 内直接 `os.environ` 读取

---

# 8. Step 3 — Database

## 交付物清单

- [ ] SQLAlchemy Engine / Session 管理
- [ ] Alembic 初始化与首个 migration
- [ ] 基础表结构（与 Step 4 实体对齐，可迭代）
- [ ] Repository 基类或 Session 生命周期工具
- [ ] 至少 1 个 Repository 实现（如 `PersonRepository`）
- [ ] 数据库文件/目录按 `DATABASE_URL` 创建
- [ ] 集成测试：migration up/down（或 up + CRUD）

## 涉及目录

```text
alembic/
  ├── env.py
  └── versions/
data/                       # sqlite 文件默认位置
src/photo_archiver/infrastructure/database/
  ├── __init__.py
  ├── engine.py
  ├── session.py
  └── models/               # ORM models（仅 Infrastructure）
src/photo_archiver/infrastructure/repositories/
  └── sqlite_person_repository.py   # 示例
src/photo_archiver/domain/repositories/
  └── person_repository.py          # 接口（与 Step 4 同步）
tests/integration/database/
```

## 验收标准

- [ ] 仅 Infrastructure 层出现 SQL / SQLAlchemy ORM
- [ ] Application / Presentation 不 import `sqlite3` / SQLAlchemy
- [ ] `alembic upgrade head` 成功
- [ ] Repository 实现 Domain 接口，不泄漏 ORM 到 Domain
- [ ] Session 正确关闭，无连接泄漏（测试或上下文管理器保证）
- [ ] 事务边界清晰（写操作可 commit/rollback）
- [ ] 迁移脚本可重复执行

> **注**：当前以 sqlite3 + `PRAGMA user_version` 临时实现（ADR-005），SQLAlchemy/Alembic 推迟到 roadmap Step 3 收尾或后续阶段。Schema 版本当前 v4。

---

# 9. Step 4 — Domain Model

## 交付物清单

- [ ] 核心 Entity：`Person`、`Photo`、`Folder`（按业务需要取舍）
- [ ] 值对象：如 `PhotoMetadata`、`FaceBox`、`MatchScore`（按需）
- [ ] 枚举：如 `MatchStatus`、`ArchiveStatus`、`ImportStatus`
- [ ] Repository 接口：`PersonRepository`、`PhotoRepository` 等
- [ ] Domain 异常：`PhotoArchiverError` 及子类
- [ ] Domain Service（如有纯业务规则）：如 `PersonValidator`
- [ ] 单元测试：Entity 行为、值对象不变性、校验规则

## 涉及目录

```text
src/photo_archiver/domain/
  ├── entities/
  ├── value_objects/
  ├── repositories/
  ├── services/
  └── exceptions.py
src/photo_archiver/common/
  └── exceptions.py           # 可选：基类异常
tests/unit/domain/
```

## 验收标准

- [ ] Domain 不 import：PySide6、OpenCV、InsightFace、sqlite3、pandas、SQLAlchemy
- [ ] Entity 不含 QWidget、不含 SQL
- [ ] Repository 只有接口，实现在 Infrastructure
- [ ] 业务规则（如姓名必填、路径合法性）在 Domain 可测
- [ ] 与 Step 3 Schema 字段一致，无「表有字段、实体无属性」遗漏
- [ ] 公共 API 有 type hints 与 docstring

---

# 10. Step 5 — Excel Import

## 交付物清单

- [ ] `ImportPersonService`（Application）
- [ ] Excel/TXT 解析器（Infrastructure）
- [ ] 导入 DTO / Command（Application）
- [ ] `ImportWorker`（后台导入）
- [ ] 导入结果：成功数、失败数、错误明细
- [ ] 可选：极简 Dev Dialog / 脚本入口用于验证
- [ ] 单元测试：解析、校验；集成测试：导入写入 DB

## 涉及目录

```text
src/photo_archiver/application/
  ├── services/import_person_service.py
  └── dto/                    # 或 commands/
src/photo_archiver/infrastructure/
  ├── importers/excel_importer.py
  └── repositories/           # 复用 PersonRepository
src/photo_archiver/workers/
  └── import_worker.py
src/photo_archiver/presentation/
  └── controllers/import_controller.py   # 可选 Dev 用
examples/                     # 示例 Excel
tests/unit/application/
tests/integration/import/
```

## 验收标准

- [ ] UI/脚本只调用 Application Service，不直接读 Excel
- [ ] pandas/openpyxl 仅出现在 Infrastructure
- [ ] Worker 通过 Signal 上报 progress / finished / error
- [ ] Worker 不直接操作 Widget
- [ ] 非法行、空文件、重复人员有明确处理策略并写日志
- [ ] 导入后 Person 可通过 Repository 查询验证
- [ ] 大文件导入 UI 不阻塞（Worker 验证）

---

# 11. Step 6 — Folder Scanner

## 交付物清单

- [ ] `ScanFolderService`（Application）
- [ ] 递归目录扫描（Infrastructure filesystem）
- [ ] 图片格式过滤（jpg/png/… 常量集中定义）
- [ ] 元数据提取：尺寸、路径、修改时间等
- [ ] `FolderScanWorker` / `ImageScanWorker`
- [ ] Photo 实体持久化
- [ ] 扫描进度与统计（总数、已处理、跳过）
- [ ] 可选：文件哈希字段（为重复检测预留）

## 涉及目录

```text
src/photo_archiver/application/services/scan_folder_service.py
src/photo_archiver/infrastructure/filesystem/
src/photo_archiver/infrastructure/image/        # 元数据读取
src/photo_archiver/workers/folder_scan_worker.py
src/photo_archiver/domain/entities/photo.py
src/photo_archiver/domain/repositories/photo_repository.py
tests/unit/infrastructure/filesystem/
tests/integration/scan/
```

## 验收标准

- [ ] 使用 `pathlib.Path`，无字符串拼路径
- [ ] 不支持格式被跳过并记录，不中断整批扫描
- [ ] 空目录、无权限目录有明确错误/警告
- [ ] Worker 支持 cancel（至少架构预留 `is_cancelled`）
- [ ] 扫描结果写入 DB，可按目录/批次查询
- [ ] Presentation 未直接调用 OpenCV / os.walk 业务逻辑

---

# 12. Step 7 — Thumbnail Generator

## 交付物清单

- [ ] `ThumbnailService`（Application）
- [ ] 缩略图生成器（Infrastructure/image）
- [ ] 缓存目录策略（如 `data/cache/thumbnails/`）
- [ ] `ThumbnailWorker`
- [ ] 与扫描流程挂接：扫描后排队或批量生成
- [ ] 跳过已存在缩略图
- [ ] 单元/集成测试：生成、缓存命中、损坏原图处理

## 涉及目录

```text
src/photo_archiver/application/services/thumbnail_service.py
src/photo_archiver/infrastructure/image/thumbnail_generator.py
src/photo_archiver/workers/thumbnail_worker.py
data/cache/thumbnails/
src/photo_archiver/domain/value_objects/thumbnail_spec.py  # 可选
tests/unit/infrastructure/image/
tests/integration/thumbnail/
```

## 验收标准

- [ ] 缩略图尺寸等 magic number 使用命名常量
- [ ] 原图读取失败不导致 Worker 崩溃，错误可记录
- [ ] 已生成缩略图不重复生成（可通过 DB 标记或文件存在判断）
- [ ] 内存及时释放，批量处理无 obvious leak
- [ ] OpenCV/Pillow 仅在 Infrastructure
- [ ] 进度可报告（x / total 或百分比）

---

# 13. Step 8 — Face Detection

## 交付物清单

- [ ] `FaceDetector`（ai/）
- [ ] 模型加载器（Infrastructure 或 ai/ 内 adapter）
- [ ] `FaceDetectionService`（Application）
- [ ] `FaceDetectionWorker`
- [ ] 检测结果持久化：`FaceBox` / detection record
- [ ] 模型路径从 Configuration 读取
- [ ] 无模型/加载失败时的降级策略与日志

## 涉及目录

```text
src/photo_archiver/ai/
  └── face_detector.py
src/photo_archiver/infrastructure/ai/            # 可选：模型加载
resources/models/ 或 models/                     # 模型文件
src/photo_archiver/application/services/face_detection_service.py
src/photo_archiver/workers/face_detection_worker.py
src/photo_archiver/domain/entities/face_detection.py  # 或 value object
tests/unit/ai/
tests/integration/face_detection/               # 需样例图片
```

## 验收标准

- [ ] InsightFace/OpenCV 不出现在 Presentation / Domain
- [ ] 检测只做「找脸」，不做身份识别（与 Step 9 职责分离）
- [ ] 无人脸、多人脸图片行为明确（记录数量，不 silent fail）
- [ ] 模型路径错误时错误信息可理解，写日志
- [ ] Worker 不更新 UI，只发 Signal
- [ ] 检测结果可关联到 Photo 记录

---

# 14. Step 9 — Face Recognition

## 交付物清单

- [ ] `FaceEncoder` / `RecognitionEngine`（ai/）
- [ ] 特征向量存储结构与 Repository
- [ ] `FaceRecognitionService`（Application）
- [ ] `FaceRecognitionWorker`
- [ ] 批量处理与进度报告
- [ ] 特征缓存/复用策略（避免重复编码）

## 涉及目录

```text
src/photo_archiver/ai/
  ├── face_encoder.py
  └── recognition_engine.py
src/photo_archiver/application/services/face_recognition_service.py
src/photo_archiver/workers/face_recognition_worker.py
src/photo_archiver/domain/entities/face_embedding.py
src/photo_archiver/infrastructure/repositories/face_embedding_repository.py
tests/unit/ai/
tests/integration/face_recognition/
```

## 验收标准

- [ ] 输入为 Step 8 的检测结果或 Photo，输出为 embedding
- [ ] embedding 维度、序列化方式固定且可测试
- [ ] 同一张脸重复识别可配置：跳过或覆盖
- [ ] Application 协调流程，ai/ 不做归档/匹配业务决策
- [ ] 异常图片不拖垮整批任务
- [ ] 性能：批量处理无明显重复加载模型

---

# 15. Step 10 — Matching Engine

## 交付物清单

- [ ] `SimilarityMatcher`（ai/）
- [ ] `MatchingService`（Application）：阈值、Top-K 策略
- [ ] 匹配结果 Entity：`MatchResult` + 状态枚举
- [ ] **User Review 状态**：`pending` / `approved` / `rejected`
- [ ] `MatchingWorker`（可选，视数据量）
- [ ] 审核接口：approve / reject / 批量操作（Application）
- [ ] 单元测试：相似度计算、阈值边界；集成测试：匹配入库

## 涉及目录

```text
src/photo_archiver/ai/similarity_matcher.py
src/photo_archiver/application/services/matching_service.py
src/photo_archiver/domain/entities/match_result.py
src/photo_archiver/domain/repositories/match_result_repository.py
src/photo_archiver/workers/matching_worker.py       # 可选
tests/unit/application/matching/
tests/integration/matching/
```

## 验收标准

- [ ] 匹配阈值为配置或 Domain 规则，不硬编码在 UI
- [ ] 低置信度结果标记为 pending，不自动当最终结论（除非明确配置）
- [ ] Person ↔ Photo 关联可追溯
- [ ] 审核状态变更写日志、可持久化
- [ ] ai/ 只返回相似度/候选，不做「归档到文件夹」决策
- [ ] 无匹配、多候选匹配行为有定义

---

# 16. Step 11 — Archive Generator

## 交付物清单

- [ ] `ArchiveService`（Application）
- [ ] 归档规则：仅处理 `approved` 匹配（或配置策略）
- [ ] 目标目录结构生成（按 Person / 日期等规则）
- [ ] 文件 copy/move 策略（默认 copy，move 需确认）
- [ ] `ArchiveWorker`
- [ ] 归档记录 Entity：`ArchiveRecord`
- [ ] 回滚或 dry-run 模式（建议至少 log dry-run）
- [ ] 集成测试：小样本归档到临时目录

## 涉及目录

```text
src/photo_archiver/application/services/archive_service.py
src/photo_archiver/infrastructure/filesystem/archive_writer.py
src/photo_archiver/workers/archive_worker.py
src/photo_archiver/domain/entities/archive_record.py
data/exports/ 或 OUTPUT_ROOT
tests/integration/archive/
```

## 验收标准

- [ ] 未审核通过的结果默认不归档
- [ ] 不覆盖用户已有文件（冲突有策略：跳过/重命名/报错）
- [ ] 归档操作写 `ArchiveRecord`，可审计
- [ ] 路径校验，防止路径遍历
- [ ] Worker 可 cancel，中断后状态一致
- [ ] Domain 定义「可否归档」规则，Infrastructure 只执行 IO

---

# 17. Step 12 — Main UI

## 交付物清单

- [ ] `MainWindow` 完整布局：MenuBar、Toolbar、Navigation、Workspace、StatusBar
- [ ] Controllers：`presentation/controllers/`
- [ ] 工作流页面/面板：导入 → 扫描 → 识别 → 匹配审核 → 归档
- [ ] Worker 进度：ProgressBar、StatusBar、日志区
- [ ] 错误提示：用户可读 + 详情写日志
- [ ] 所有长任务走 Worker + Signal
- [ ] pytest-qt smoke test（窗口启动、关键按钮存在）

## 涉及目录

```text
src/photo_archiver/presentation/
  ├── views/main_window.py
  ├── views/                  # 各功能面板
  ├── controllers/
  └── widgets/                # 可复用组件
resources/
  ├── icons/
  ├── styles/
  └── ui/                     # 可选 .ui 文件
tests/ui/ 或 tests/integration/ui/
```

## 验收标准

- [ ] UI 无 SQL、无 OpenCV、无 InsightFace、无 pandas 直接调用
- [ ] UI 通过 Controller 调用 Application Service
- [ ] 长任务执行时界面仍可响应（Worker 验证）
- [ ] Worker 回调只在主线程更新 Widget（Signal → Controller → View）
- [ ] 工作流顺序与业务文档一致
- [ ] 空状态、加载中、错误状态有 UI 反馈
- [ ] 窗口尺寸、标题、基本快捷键合理

---

# 18. Step 13 — Settings

## 交付物清单

- [ ] `SettingsDialog` + `SettingsController`
- [ ] 用户偏好持久化（QSettings 或 DB / 配置文件）
- [ ] 可配置项：主题、语言（预留）、默认导入/导出路径、识别阈值、MAX_WORKERS
- [ ] `SettingsService`（Application）
- [ ] 修改后热生效或提示重启策略（文档化）
- [ ] 单元测试：读写 settings；UI 测试：保存/取消

## 涉及目录

```text
src/photo_archiver/presentation/views/settings_dialog.py
src/photo_archiver/presentation/controllers/settings_controller.py
src/photo_archiver/application/services/settings_service.py
src/photo_archiver/infrastructure/config/user_settings_store.py
config/themes/
resources/styles/
tests/unit/application/settings/
```

## 验收标准

- [ ] 设置不散落在多个 Widget 硬编码
- [ ] 与 Step 2 系统配置区分：系统 env vs 用户偏好
- [ ] 非法值被拦截，不写入
- [ ] 修改 `MODEL_PATH` / 阈值后，相关 Service 能读到新值（或明确需重启）
- [ ] 用户可见文案支持后续 i18n（避免散落字面量时可接受暂中文）

---

# 19. Step 14 — Export

## 交付物清单

- [ ] `ExportService`（Application）
- [ ] 导出 DTO：人员、照片、匹配、归档汇总
- [ ] Excel / CSV 导出器（Infrastructure）
- [ ] `ExportWorker`
- [ ] `ExportDialog` + Controller
- [ ] 导出范围：全量 / 当前批次 / 筛选结果
- [ ] 集成测试：导出文件可打开、字段完整

## 涉及目录

```text
src/photo_archiver/application/services/export_service.py
src/photo_archiver/application/dto/export_dto.py
src/photo_archiver/infrastructure/exporters/
src/photo_archiver/workers/export_worker.py
src/photo_archiver/presentation/views/export_dialog.py
data/exports/
tests/integration/export/
```

## 验收标准

- [ ] 导出字段与 Domain 模型一致，不手写 magic column
- [ ] 大报告不阻塞 UI（Worker）
- [ ] 输出路径可配置，默认在 `OUTPUT_ROOT`
- [ ] 空数据集导出行为明确（空表或提示）
- [ ] 不暴露内部路径/堆栈给用户
- [ ] openpyxl/pandas 仅在 Infrastructure

---

# 20. Step 15 — Plugin System

## 交付物清单

- [ ] 插件接口定义（Application 层 public API）
- [ ] 插件发现/加载机制（entry point 或目录扫描）
- [ ] 插件生命周期：load / enable / disable
- [ ] 示例插件（如 noop 或 hello plugin）
- [ ] 插件隔离：不得修改 core 内部模块
- [ ] 文档：插件开发指南

## 涉及目录

```text
src/photo_archiver/plugins/
  ├── __init__.py
  ├── loader.py
  └── interfaces.py
src/photo_archiver/application/plugins/     # 或 contracts/
examples/plugins/
docs/development/plugin-guide.md          # 可选
tests/unit/plugins/
```

## 验收标准

- [ ] 核心应用不依赖具体插件实现
- [ ] 插件仅依赖 Application public 接口 + common
- [ ] 恶意/错误插件加载失败不影响主程序启动（可 disable + 日志）
- [ ] 示例插件可加载并注册一个可见能力（菜单项或 hook）
- [ ] 符合 dependency-rules：Plugins → Application，不反向依赖 Infrastructure 内部

---

# 21. 架构对应关系（简要）

```text
Step 1–2  → infrastructure/（logging、config）
Step 3    → infrastructure/database/
Step 4    → domain/
Step 5–6  → application/ + workers/ + infrastructure/
Step 7–10 → workers/ + ai/ + infrastructure/
Step 11   → application/ + domain/
Step 12–13→ presentation/
Step 14   → application/ + workers/
Step 15   → plugins/
```

---

# 22. 补充说明

## Step 3 / Step 4 建议短迭代绑定

更稳妥的做法不是严格 3→4 线性，而是：

```text
Step 4a  Domain Entity + Repository 接口（无框架依赖）
Step 3   Schema + Alembic + Repository 实现
Step 4b  根据实现反哺 Entity / 值对象
```

## Step 5 之后可选 Dev Shell

在 Step 12 正式 Main UI 之前，可在 Step 5 后增加极简 Dev Shell（目录选择 + 按钮 + 日志区 + 进度条），用于 Worker/AI 调试。

## 项目目标中未单列的能力

| 能力 | 建议归属 |
|------|----------|
| 重复图片检测 | Step 6 扫描时做哈希，或 Step 11 归档前 |
| 搜索 / 筛选 | Step 12 Main UI 或 Step 4 查询接口 |
| 批量操作 | Step 12 + Application Service |

---

End of Document
