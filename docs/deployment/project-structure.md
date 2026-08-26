# PhotoArchiver 项目结构说明（Project Structure Guide）

> Version：1.1
> Last Updated：2026-07-24
>
> **目录结构权威**：`.ai/rules/architecture-rules.md` §4 ARC-009（子包与特殊目录补录表）。本节为人类入口详解，若与 ARC §4 冲突以彼为准。

---

# 1. 文档目的

本文档用于说明 PhotoArchiver 项目的整体目录结构、模块职责以及各目录之间的关系。

项目采用企业级分层架构（DDD + Clean Architecture），遵循**高内聚、低耦合**原则，并结合 PySide6 欌面应用开发规范设计。

项目支持：

- Windows
- macOS

后续所有功能开发都将在当前目录结构下完成，不再调整顶层目录。

---

# 2. 项目整体结构

```text
PhotoArchiver/
│
├── .ai/
├── .github/
├── .trae/
├── assets/
├── config/
├── data/
├── docs/
├── examples/
├── logs/
├── requirements/
├── resources/
├── scripts/
├── src/
├── tests/
├── tools/
│
├── main.py
├── pyproject.toml
├── README.md
└── LICENSE
```

整个项目可以划分为六大部分：

1. 工程管理
2. 文档体系
3. 源代码
4. 测试
5. 项目资源
6. AI 开发辅助

> `AI_ONBOARDING.md`（根目录旧版）已废，新入口为 `.ai/AI_ONBOARDING.md`，保留作历史参考不列入上方树。

---

# 3. 顶层目录说明

## .ai

AI 开发知识库与强制规则（AI Runtime Context 体系）。

包括：

- `AI_ONBOARDING.md`（AI 入口）、`PROJECT_STATUS.md`（实状态）、`ARCHITECTURE_DECISIONS.md`（ADR Register）、`KNOWN_ISSUES.md`（问题清单）、`DOCUMENT_INDEX.md`（文档体系导航）
- `rules/`（10 份工程规则：ai/coding/architecture/dependency/ui/worker/git/review/audit-methodology + README）
- `business/roadmap.md`（15 步路线图，含 Phase 1 历史并入横幅）
- 原 11 份 Placeholder 占位 + 7 份 Deprecated 废弃文档已于 2026-07-24 裁决1/2物理删除（见 `.ai/DOCUMENT_INDEX.md` §4/§6）

该目录仅供 AI 辅助开发使用，不参与程序运行。完整体系导航见 `.ai/DOCUMENT_INDEX.md`。

---

## .github

GitHub 工程配置。

包括：

- CI 流水线（`workflows/`）
- Issue / PR 模板

---

## .trae

Trae IDE 专用配置目录。

包括：

- Prompt
- Rules
- Context
- Checklist
- Template

作用：

保证 Trae 每次生成代码时遵循统一规范。

---

## assets

项目设计资源。

包括：

- Logo
- 宣传图片
- 截图
- PSD
- AI 源文件

说明：

该目录资源不会参与程序运行。

---

## config

项目静态配置文件目录（非 Python 模块，不进依赖矩阵）。

包括：

- `env/`（环境配置）
- `logging/`（日志配置）
- `settings/`（应用配置）
- `themes/`（主题配置）

所有配置统一管理。注：`config/` 在 ARC §4 ARC-009 补录表标注为"仅静态配置文件目录，非 Python 模块，不进 DEP §4 矩阵"。

---

## data

运行过程中产生的数据。

包括：

- SQLite 数据库
- 导入文件
- 导出文件
- 缓存
- 临时数据

注意：

data 目录属于运行数据，不属于源代码。

---

## docs

人类开发者文档。

包括：

- `architecture/overview.md`（架构详解）
- `deployment/project-structure.md`（本文，目录结构详解）
- `development/{getting-started,configuration}.md`（开发入门 + 配置详解）

任何设计决策都应该形成文档。

---

## examples

示例数据。

例如：

- Excel 示例
- TXT 示例
- 测试照片
- Demo 数据

主要用于测试和开发。

---

## logs

Loguru 日志运行输出（轮转 10MB / 保留 30 天）。运行时生成，不进版本控制。

---

## requirements

Python 依赖管理。

包括：

- `README.md`（依赖清单说明）
- `base.txt`（运行依赖，含 AI 核心库 insightface/onnxruntime）
- `dev.txt`（开发依赖，含 base）
- `ai.txt`（AI 扩展依赖挂载点，当前空，AI 核心库已在 base）

后续所有依赖统一在这里维护。

---

## resources

程序运行资源。

包括：

- 图标
- 字体
- UI
- 图片
- AI 模型（`resources/models/`，ADR-012，走 `scripts/download_models.py` 手动下载，禁止自动下载）

程序运行时直接读取该目录。

---

## scripts

项目维护脚本。

例如：

- 初始化项目
- 创建目录
- 构建
- 打包
- `download_models.py`（AI 模型手动下载）

所有自动化脚本统一放置。

---

## src

项目源码目录。

所有业务代码均放在这里。

---

## tests

测试代码。

包括：

- `unit/`（单元测试）
- `integration/`（集成测试）
- 测试资源

---

## tools

开发工具。

例如：

- 数据转换
- 图片处理
- 临时工具

一般不会进入正式程序。

---

# 4. 源代码结构（src）

项目所有核心代码均位于：

```text
src/
└── photo_archiver/
```

这样做的目的：

- 避免包名冲突
- 方便打包
- 统一 import
- 符合 Python 企业项目规范

---

# 5. photo_archiver 模块说明

```text
photo_archiver/
│
├── ai/
├── app/
├── application/
│   ├── commands/
│   ├── dtos/
│   ├── ports/
│   ├── services/
│   └── └
├── common/
├── domain/
│   ├── entities/
│   ├── repositories/
│   └ exceptions.py
│   └── value_objects/
├── infrastructure/
│   ├── ai/
│   ├── config/
│   ├── database/
│   ├── filesystem/
│   ├── image/
│   ├── importers/
│   ├── logging/
│   ├── persistence/
│   └ and repositories/
├── plugins/
├── presentation/
│   ├── controllers/
│   └ and views/
└── workers/
```

> 子包与特殊目录（`application/{commands,dtos,ports,use_cases,services}`、`infrastructure/{persistence,database,repositories,exporters}`、顶层 `config/`）详见 ARC §4 ARC-009 补录表。`infrastructure/exporters/` 已随 Step 14 Export 落地（含 ExcelExporter + CsvExporter）。

---

## ai

AI 能力模块。

负责：

- 人脸检测（`insightface_detector.py`）
- 人脸识别（`insightface_recognizer.py`）
- 人脸匹配（`similarity_matcher.py`，1:N Top-1，ADR-017）

不负责业务流程。模型加载与路径探测归 `infrastructure/ai/InsightFaceLoader`（ADR-014）。

---

## app

应用启动模块。

负责：

- QApplication
- 生命周期
- 启动流程
- 全局初始化
- 运行时依赖装配

整个程序只有一个入口。当前启动流程由 `bootstrap_application()` 负责装配运行时上下文：

- 加载并校验应用配置
- 初始化日志系统
- 初始化 SQLite Repository schema（`PRAGMA user_version = 4`，ADR-024）
- 构建 `ApplicationContext`

`ApplicationContext` 暴露：

- `settings`：运行时配置（`AppSettings`）
- `repositories`：SQLite-backed Repository 容器
- `services`：应用服务编排
- `ui`：UI 装配（`ui_assembly.py`）

---

## application

应用业务层。

包括：

- `commands/`：命令对象（archive / import_people / match_persons / register_photo / scan_and_register_photos / scan_photo_folder）
- `dtos/`：数据传输对象（archive / import_people / photo_scan / recognition / register_photo / scan_and_register_photos / settings）
- `ports/`：端口协议（face_detector / face_recognizer / person_matcher / photo_file_scanner / photo_metadata_reader / progress_reporter / system_settings / thumbnail_cache / thumbnail_generator / unit_of_work / user_settings_store / archive_path_builder / person_import_reader）
- `use_cases/`：用例编排（archive / import_people / match_persons / register_photo / review_recognition / scan_and_register_photos / scan_photo_folder / settings）
- `services/`：应用服务（archive_executor / archive_path_builder_service / archive_photos_service / archive_planner / import_people_service / match_persons_service / register_photo_service / review_recognition_service / scan_and_register_photos_service / scan_photo_folder_service / settings_service）

它连接 UI → Domain → Infrastructure，属于整个系统的大脑。**无 GUI、无 SQL**，必须用 Repository Protocol。

---

## common

公共模块。

仅含标准库的通用工具，**不导入任何第三方框架**（DEP-071，R-7 裁决删除了 `common/logging/` 选项）。当前为空骨架，随模块推进逐步填充。

---

## domain

领域层。这是整个系统最核心的一层。

包括：

- `entities/`（archive / folder / person / photo / recognition）
- `repositories/`（archive_record / face_embedding / folder / person / photo / recognition 仓储接口）
- `value_objects/`（archive_path / face_box / face_embedding / person_identity / photo_metadata / photo_path）
- `exceptions.py`

特点：**零框架依赖**（禁 PySide6/OpenCV/InsightFace/SQLite/pandas/openpyxl/SQLAlchemy/numpy，ADR-003）。`FaceEmbedding` 持 `tuple[float, ...]` 不持 numpy（ADR-015）。

---

## infrastructure

基础设施层。

包括：

- `ai/`：AI 模型加载（`InsightFaceLoader`）
- `config/`：系统配置适配（`AppSettings`）
- `database/`：SQLite 仓储实现 + Schema 初始化 + UnitOfWork（ADR-004，所有 sqlite3 代码唯一归宿）
- `filesystem/`：文件系统适配（`LocalPhotoFileScanner` / `PillowPhotoMetadataReader`）
- `image/`：图片处理（`PillowThumbnailGenerator` / `ThumbnailCache` / `ContentHashCalculator`）
- `importers/`：导入器（`ExcelPersonImportReader` / `TxtPersonImportReader`）
- `logging/`：Loguru 日志配置（ADR-008）
- `persistence/`：用户偏好持久化（`InMemoryUserSettingsStore` / `QSettingsUserSettingsStore`，Step 13）
- `repositories/`：内存仓储实现（测试用 `InMemory{Folder,Person,Photo}Repository`）

负责和外部世界通信，不写业务决策。`exporters/` 子包已随 Step 14 Export 落地（`ExcelExporter`、`CsvExporter`）。

---

## plugins

插件系统（扩展预留，Step 15）。

当前包含 Step 15 插件加载器（`PluginRegistry`）与接口定义（`application/ports/plugin.py`）。未来可以扩展：

- OCR
- 云存储
- 第三方接口
- AI 插件

当前为空骨架。

---

## presentation

界面层（PySide6）。

包括：

- `controllers/`（archive / export / import_people / photo_list / review / scan / settings 七个 controller）
- `views/`（`main_window` / `review_dialog` / `settings_dialog` / `archive_preview_dialog` / `export_dialog` / `photo_list_model`）

不处理业务逻辑。**禁导入 Infrastructure/SQLite/OpenCV/InsightFace**。

---

## workers

后台线程。

包括：

- `qt_executor.py`（`QtWorkerExecutor` 通用执行器框架）
- `application_tasks.py`（任务注册）
- `task.py`（任务抽象）
- `events.py`（事件定义）

仅可导入 `PySide6.QtCore`（线程原语，ADR-007、DEP-040），禁导入 QtWidgets/QtGui。通过 Qt Signals 与 UI 通信，不操作 Widget。

---

# 6. 分层调用关系

项目遵循如下依赖关系（权威矩阵见 `.ai/rules/dependency-rules.md` §2/§4）：

```text
Presentation → Application → Domain ← Infrastructure
Workers → Application
AI → Infrastructure + Domain
Plugins → Application
Common 仅标准库被所有层引用
```

说明：

- Presentation 不直接访问数据库。
- Domain 不依赖 PySide6。
- Infrastructure 不包含业务规则。
- 所有业务统一由 Application �度。
- SQLite 仅在 `infrastructure/database/`（ADR-004）。

---

# 7. 资源目录说明

resources 用于存放运行时资源：

```text
resources/
├── fonts/
├── icons/
├── images/
├── models/      # AI 模型（ADR-012，手动下载，不提交 Git）
├── styles/
└── ui/
```

例如：

- 图标
- 字体
- AI 模型
- Qt StyleSheet

---

# 8. 文档目录说明

当前文档分类：

```text
docs/
├── architecture/    # overview.md（架构详解）
├── deployment/      # project-structure.md（本文）
└── development/     # getting-started.md + configuration.md
```

权威文档体系导航见 `.ai/DOCUMENT_INDEX.md`。保持文档与代码同步更新。

---

# 9. 开发原则

本项目遵循以下原则：

- 单一职责原则（SRP）
- 开闭原则（OCP）
- 依赖倒置原则（DIP）
- 高内聚、低耦合
- DDD 分层架构
- Clean Architecture
- 企业级 Python 工程规范

---

# 10. 后续开发约定

从项目初始化完成后：

- 不再调整顶层目录。
- 所有新增功能均在现有模块中扩展。
- 所有业务逻辑必须经过 Application 层。
- 所有数据访问统一通过 Infrastructure。
- 所有 UI 只负责展示，不承担业务逻辑。

---

# 11. 项目目标

PhotoArchiver 最终将实现以下核心能力：

1. 导入 Excel / TXT。
2. 自动创建目录结构。
3. 扫描指定照片目录。
4. AI 人脸检测与识别。
5. 根据人员信息自动归档照片。
6. 提供可视化桌面管理界面。
7. 支持 Windows 与 macOS 平台。

本项目将以稳定、可维护、可扩展为第一目标，而不是追求快速实现功能。

---

> 📝 本文件由 AtomCode (GLM-5.2) 于 2026-07-24 基于 `src/photo_archiver/` 磁盘实测刷新。权威子包清单以 `.ai/rules/architecture-rules.md` §4 ARC-009 为准。
