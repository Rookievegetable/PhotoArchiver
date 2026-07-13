# PhotoArchiver 架构总览

> Version: 1.0  
> Last Updated: 2026-07-03

本文档面向开发者和维护者，说明 PhotoArchiver 的架构目标、分层职责、依赖方向和后续功能开发边界。

## 1. 架构目标

PhotoArchiver 是长期维护型桌面应用，架构目标是：

- 保持业务逻辑稳定、可测试、可复用。
- 隔离 UI、数据库、文件系统、AI 模型等外部技术细节。
- 支持人员导入、目录扫描、图片处理、人脸识别、归档导出等功能逐步扩展。
- 让人类开发者和 AI 编码助手都能在清晰边界内协作。

项目采用：

- Domain-Driven Design
- Clean Architecture
- Layered Architecture

## 2. 分层关系

核心依赖方向：

```text
Presentation
      ↓
Application
      ↓
Domain
      ↑
Infrastructure
```

含义：

- `Presentation` 调用 `Application` 执行用例。
- `Application` 编排业务流程并依赖 `Domain` 抽象。
- `Domain` 保存核心业务模型和规则，不依赖外部框架。
- `Infrastructure` 实现 `Domain` 或 `Application` 需要的技术细节。
- `workers/` 承载耗时任务，与 UI 通过 Qt Signals 通信。
- `ai/` 提供 AI 能力，不直接决定业务归档规则。

## 3. 模块职责

### `app/`

负责应用启动和依赖装配。

当前包含：

- `bootstrap_application()`
- 应用上下文 `ApplicationContext`
- PySide6 应用生命周期封装

不应在 `app/` 中编写业务规则。

### `presentation/`

负责桌面界面和用户交互。

允许包含：

- Window
- Dialog
- Widget
- Controller
- ViewModel
- UI 状态展示

禁止：

- 直接执行 SQL。
- 直接操作 Repository 实现。
- 直接调用 OpenCV 或 InsightFace。
- 在 UI 类中编写归档、匹配、识别等业务决策。

### `application/`

负责业务用例和流程编排。

适合放置：

- Use Case
- Application Service
- Command
- DTO
- 工作流编排
- 事务边界

示例用例：

- 导入人员信息。
- 扫描照片目录。
- 生成缩略图。
- 匹配识别结果。
- 执行归档任务。

### `domain/`

负责纯业务模型和规则。

适合放置：

- Entity
- Value Object
- Domain Service
- Repository Interface
- Domain Exception

预期核心模型包括：

- `Person`
- `Photo`
- `Folder`
- `ArchiveRecord`
- `RecognitionResult`

禁止依赖：

- PySide6
- SQLite / SQLAlchemy
- OpenCV
- InsightFace
- pandas
- 文件系统实现细节

### `infrastructure/`

负责技术实现和外部系统适配。

适合放置：

- 配置加载。
- 日志初始化。
- SQLite 数据库连接。
- Alembic 迁移。
- Repository 实现。
- Excel / TXT 读取适配器。
- 文件系统扫描实现。
- 图片元数据读取实现。

Infrastructure 可以依赖 Domain 中的接口和模型，但不应把技术细节反向泄漏进 Domain。

### `workers/`

负责后台任务。

适合承载：

- 文件夹扫描。
- Excel 导入。
- 缩略图生成。
- AI 推理。
- 批量归档。
- 导出报告。

约束：

- Worker 不直接更新 UI Widget。
- Worker 通过 Qt Signals 报告进度、结果、错误和完成状态。
- Worker 应支持取消和异常处理。
- Worker 中的业务操作应调用 Application 用例，而不是绕过应用层。

### `ai/`

负责 AI 能力封装。

适合放置：

- 模型加载。
- 人脸检测。
- 特征提取。
- 人脸识别。
- 聚类或相似度计算适配器。

AI 模块提供能力，不负责最终业务决策。人员匹配、用户复核和归档策略应由 Application / Domain 协作完成。

### `common/`

负责真正通用的工具。

适合放置：

- 常量。
- 通用异常基类。
- 小型辅助函数。

不应把业务逻辑堆积到 `common/`。

### `plugins/`

预留扩展机制。

当前阶段不建议优先实现插件系统。核心应用不应依赖插件。

## 4. 允许和禁止的依赖

推荐依赖：

```text
presentation -> application
application -> domain
infrastructure -> domain
app -> presentation / infrastructure / application
workers -> application
```

禁止依赖：

```text
domain -> presentation
domain -> infrastructure
domain -> PySide6 / OpenCV / InsightFace / SQLAlchemy / pandas
presentation -> infrastructure repository implementation
presentation -> SQLite / OpenCV / InsightFace
infrastructure -> presentation
```

## 5. 典型功能开发路径

以“导入人员信息”为例：

```text
domain
  定义 Person、PersonRepository 接口、必要值对象

application
  定义 ImportPersonsUseCase、输入 DTO、结果 DTO

infrastructure
  实现 Excel / TXT 读取适配器和 PersonRepository SQLite 实现

workers
  封装 ImportPersonsWorker，发出进度和完成信号

presentation
  提供文件选择、进度展示和结果提示
```

以“AI 人脸识别”为例：

```text
ai
  提供模型加载、人脸检测、特征提取能力

application
  编排照片读取、识别、匹配和保存结果

domain
  表达 RecognitionResult、匹配状态和业务规则

workers
  在后台执行批量识别任务

presentation
  展示识别进度和用户复核界面
```

## 6. 当前实现状态

当前已实现：

- `main.py` 应用入口（CLI 扫描模式 + PySide6 桌面模式）。
- `app/bootstrap.py` 启动和依赖装配。
- `app/context.py` 应用上下文（含 `QtWorkerExecutor`）。
- `infrastructure/config/settings.py` 配置加载和校验。
- `infrastructure/logging/` Loguru 初始化。
- `domain/` 核心实体（Person/Photo/Folder）、值对象（PhotoPath/PhotoMetadata/PersonIdentity）、仓储 Protocol、异常。
- `application/` Command/DTO/UseCase Protocol/Service 四组：ImportPeople/RegisterPhoto/ScanPhotoFolder/ScanAndRegisterPhotos；端口 ProgressReporter/UnitOfWork。
- `infrastructure/database/` SQLite 连接（含事务边界 `transaction()`）、Schema 初始化、Repository 容器、基础仓储实现、`SQLiteUnitOfWork`。
- `infrastructure/filesystem/` 本地照片文件扫描器、Pillow 元数据读取适配器。
- `infrastructure/importers/` TXT 与 Excel 人员导入适配器。
- `workers/` 任务基类、事件模型、Qt 执行器、人员导入与扫描注册任务包装器。
- `presentation/views/main_window.py` 最小工作台（扫描按钮 + 进度条 + 状态栏 + ScanController）。
- `presentation/controllers/scan_controller.py` UI↔Worker 桥接。
- 扫描注册闭环的事务原子性与进度回流契约。

当前尚未实现：

- SQLite 迁移体系与 Schema 版本演进规范（当前以 `PRAGMA user_version` 管理，SQLAlchemy/Alembic 推迟）。
- 缩略图生成与缓存。
- AI 推理流程（人脸检测/识别/匹配/用户复核）。
- 归档组织、导出结果和统计报告。
- 完整 UI 工作流（照片列表预览、用户复核界面）。

## 7. 后续优先级

建议后续按以下顺序扩展：

1. 缩略图生成与缓存策略。
2. 完整 PySide6 工作台（照片列表预览、用户复核界面）。
3. AI 能力接入（人脸检测、识别、匹配）。
4. 归档组织与导出。
5. SQLite 迁移体系（SQLAlchemy/Alembic）替代 `PRAGMA user_version`。

## 8. 与 `.ai/` 的关系

`docs/architecture/overview.md` 面向人类开发者解释架构。

`.ai/` 是 AI 编码助手的知识库和规则来源。

如果本文档与 `.ai/rules/` 出现冲突，开发前应暂停并确认；规则类约束以 `.ai/rules/` 为准，面向用户和开发者的操作说明以 `README.md` 和 `docs/` 为准。
