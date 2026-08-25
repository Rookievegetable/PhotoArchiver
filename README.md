# PhotoArchiver

[![CI](https://github.com/Rookievegetable/PhotoArchiver/actions/workflows/ci.yml/badge.svg)](https://github.com/Rookievegetable/PhotoArchiver/actions/workflows/ci.yml)

PhotoArchiver 是一个面向长期维护的企业级桌面照片归档管理系统，目标是帮助学校、政府机构、企业、档案馆、博物馆、摄影工作室和个人用户管理大量历史照片。

> **当前进度唯一权威**：`.ai/PROJECT_STATUS.md`。本节仅作人类入口概览，不承载任何会过期的状态陈述——所有 Step 状态、测试计数、lint 数字均以 `PROJECT_STATUS.md` 为准。
>
> **项目开发已全面收官**（全部 15 Step 完成，ruff 0 + mypy 0，Alembic 迁移体系已激活）。详见 `.ai/PROJECT_STATUS.md`。
>
> 📖 **最终用户指南**：安装配置、业务闭环操作与常见问题见 [`docs/user-guide/`](docs/user-guide/)——[安装与首次运行](docs/user-guide/installation.md) ｜ [核心操作流程](docs/user-guide/workflow.md) ｜ [常见问题](docs/user-guide/faq.md)。

## 核心目标

PhotoArchiver 计划支持以下能力：

- 导入 Excel / TXT 人员信息。
- 扫描指定照片目录并提取图片元数据。
- 生成缩略图与缓存数据。
- 使用 AI 进行人脸检测、特征提取和人员匹配。
- 由用户复核识别结果。
- 按人员、时间、来源或业务规则自动归档照片。
- 导出归档结果和统计报告。
- 提供跨平台 PySide6 桌面界面，优先支持 Windows 和 macOS。

标准业务流程：

```text
Import Personnel Information
        ↓
Select Photo Directory
        ↓
Scan Directory Structure
        ↓
Extract Image Metadata
        ↓
Generate Thumbnails
        ↓
Detect Faces
        ↓
Recognize Persons
        ↓
Match Recognition Results
        ↓
User Review
        ↓
Archive Organization
        ↓
Export Results
```

## 技术栈

> **技术栈权威清单**：`.ai/rules/dependency-rules.md` §13（含层归属、延后批注）。本节为人类入口概览，若与彼冲突以彼为准。

核心运行栈：Python 3.11、PySide6、SQLite（Alembic 迁移管理，ADR-024）、InsightFace + ONNX Runtime、OpenCV、Pillow、openpyxl、Pydantic + pydantic-settings、Loguru。开发栈：pytest、pytest-qt、Ruff、Black、isort、MyPy、pre-commit。已批准但当前未使用：pandas（当前零 import，openpyxl 用于 Step 14 Excel 导出）、watchdog（filesystem watcher 用途预留，当前零 import）。SQLAlchemy 仅被 Alembic 使用（ORM 未引入）。完整清单与层归属见 `.ai/rules/dependency-rules.md` §13。

## 快速开始

### 1. 创建虚拟环境

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Windows CMD：

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

macOS / Linux：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 2. 安装依赖

运行依赖：

```bash
pip install -r requirements/base.txt
```

开发依赖：

```bash
pip install -r requirements/dev.txt
```

### 3. 配置环境变量

复制示例配置：

```bash
cp .env.example .env
```

Windows CMD 可使用：

```cmd
copy .env.example .env
```

然后按本地环境调整 `.env`。配置详情见 `docs/development/configuration.md`。

### 4. 运行应用

启动桌面应用：

Windows CMD：

```cmd
python main.py
```

PowerShell：

```powershell
python main.py
```

macOS / Linux：

```bash
python main.py
```

查看 CLI 帮助：

```bash
python main.py --help
```

扫描并注册照片目录到 SQLite：

```bash
python main.py scan /path/to/photos --name "Archive Folder"
```

默认会递归扫描子目录。只扫描当前目录可使用：

```bash
python main.py scan /path/to/photos --no-recursive
```

将已审核通过的照片归档到 `ARCHIVE_ROOT/{person}/{date}/{file}`：

```bash
python main.py archive --archive-root /path/to/archive --conflict-strategy skip
```

可选参数：

- `--archive-root <path>`：覆盖 `AppSettings.archive_root` 仅本次运行。
- `--conflict-strategy {skip,overwrite,rename}`：目标已存在时处置策略（默认 `skip`，配置键 `ARCHIVE_CONFLICT_STRATEGY`）。
- `--dry-run`：只记录计划操作不触文件系统，便于预审整批归档计划。

## 开发命令

```bash
pytest
pytest tests/unit tests/integration
ruff check .
black .
isort .
mypy src
```

当前已建立面向 Domain、Application、Infrastructure、App bootstrap、扫描注册服务和 CLI 入口的单元测试与集成测试。真实图片元数据相关集成测试依赖 Pillow；安装 `requirements/base.txt` 后会执行，否则会被 pytest 跳过。后续会随 UI、Worker、缩略图、Excel 导入和 AI 流程继续补充集成测试。

## 项目结构

```text
PhotoArchiver/
├── .ai/                  # AI 开发知识库和强制规则
├── alembic/              # Alembic 迁移脚本（ADR-024）
├── assets/               # 设计素材，不参与程序运行
├── config/               # 项目配置目录
├── data/                 # 运行数据、数据库、缓存、导入数据
├── docs/                 # 面向人类开发者和维护者的项目文档
├── examples/             # 示例数据
├── requirements/         # Python 依赖清单
├── resources/            # 程序运行资源：图标、字体、样式、UI、图片
├── scripts/              # 项目维护脚本
├── src/photo_archiver/   # 应用源码
├── tests/                # 单元测试和集成测试
├── tools/                # 开发辅助工具
├── main.py               # 程序入口
└── pyproject.toml        # Python 工程配置
```

源码分层位于 `src/photo_archiver/`：

```text
app/             # 应用启动、生命周期、依赖装配
presentation/    # PySide6 UI、窗口、控件、用户交互
application/     # Use Case、应用服务、工作流编排
domain/          # 实体、值对象、领域服务、仓储接口
infrastructure/  # 配置、日志、数据库、文件系统、外部适配器
workers/         # 后台任务与线程封装
ai/              # AI 能力适配器和模型相关能力
plugins/         # 插件扩展预留
common/          # 通用工具，不能堆积业务逻辑
```

完整结构说明见 `docs/deployment/project-structure.md`。

## 架构原则

项目采用 DDD + Clean Architecture + 分层架构：

```text
Presentation
      ↓
Application
      ↓
Domain
      ↑
Infrastructure
```

关键约束：

- `Domain` 保持纯净，不依赖 PySide6、OpenCV、SQLite、pandas、InsightFace 等外部框架。
- `Presentation` 不直接访问数据库、文件系统仓储、OpenCV 或 AI 模型。
- `Application` 负责编排业务用例，不承载 UI 细节。
- `Infrastructure` 实现技术细节和外部系统适配，不写业务决策。
- 长耗时任务必须通过 `workers/` 执行，并通过 Qt Signals 与 UI 通信。
- 新增依赖、调整公开 API、修改数据库 Schema 或改变架构边界前需要明确确认。

架构详情见 `docs/architecture/overview.md`。

## 文档入口

- `docs/development/getting-started.md`：开发环境、运行、测试和质量检查。
- `docs/development/configuration.md`：`.env`、日志、数据库、模型和目录配置。
- `docs/architecture/overview.md`：分层架构、模块职责和依赖方向。
- `docs/deployment/project-structure.md`：项目目录结构说明。
- `.ai/`：AI 编码助手专用知识库和规则体系。

## 当前开发进度

> **唯一权威**：`.ai/PROJECT_STATUS.md`。本节为历史快照，为保持稳定性不再随 Step 更新。
>
> **项目开发已全面收官**：全部 15 个 Roadmap Step 完成，飘带清零（ruff 0 + mypy 0），Alembic 迁移体系已激活（ADR-024）。

已实现核心能力：

- Walking Skeleton、Python 工程配置、运行依赖与开发依赖规划。
- 应用启动入口、配置加载与运行目录创建、Loguru 日志初始化。
- PySide6 桌面主窗口（MainWindow + 7 controller + ArchivePhotosTask + ArchivePreviewDialog + ExportDialog + ReviewDialog + SettingsDialog）。
- domain/ 完整实体、值对象、异常和仓储接口。
- application/ Command、DTO、Use Case 协议和应用服务。
- 人员 TXT + Excel 导入、照片目录扫描、注册、缩略图生成、AI 人脸检测/识别/匹配、用户复核、归档组织、导出全闭环。
- SQLite + Alembic 迁移管理（ADR-024）。
- Plugins 插件系统（Plugin interface + loader + 示例插件 + MainWindow 注册）。
- Workers 通用执行器框架（QtWorkerExecutor）。
- Settings 闭环（QSettings/InMemory 双适配器）。
- 单元测试与集成测试体系。
- 单元测试与集成测试体系（pytest 226 passed / 8 skipped）。
- AI 开发知识库 AI Runtime Context 四文档体系 + 工程规则 + 文档体系导航。

待实现：

- Step 14 Export：`ExportService` + Excel/CSV 导出器 + `ExportWorker` + `ExportDialog`，导出范围全量/当前批次/筛选结果。
- Step 15 Plugin System：插件接口 + 发现/加载机制 + 生命周期管理 + 示例插件。
- SQLAlchemy/Alembic 迁移体系替代当前 `PRAGMA user_version`（roadmap Step 3 收尾）。
- 既有 19 mypy + 2 ruff 飘带单独一轮清理。

## 下一阶段计划

> 详见 `.ai/business/roadmap.md`（15 步权威路线图）与 `.ai/PROJECT_STATUS.md`。

1. Step 14 Export 导出与统计报告。
2. Step 15 Plugin System 插件扩展机制。
3. SQLAlchemy/Alembic 迁移体系（roadmap Step 3 收尾）。
4. 既有飘带单独一轮清理。

## AI 协作说明

本项目包含 `.ai/` 知识库，用于约束 AI 编码助手的行为、架构边界、代码风格和审查标准。AI 助手在修改代码前必须从 `.ai/AI_ONBOARDING.md` 入口开始，按 `.ai/PROJECT_STATUS.md` → `.ai/ARCHITECTURE_DECISIONS.md` → `.ai/KNOWN_ISSUES.md` → `.ai/DOCUMENT_INDEX.md` 顺序加载 AI Runtime Context，再按需阅读 `.ai/rules/` 与 `docs/`。

根目录 `README.md` 面向所有项目读者；`.ai/` 面向 AI 协作流程。两者职责不同，应保持同步但避免重复维护规则正文。
