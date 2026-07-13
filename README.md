# PhotoArchiver

PhotoArchiver 是一个面向长期维护的企业级桌面照片归档管理系统，目标是帮助学校、政府机构、企业、档案馆、博物馆、摄影工作室和个人用户管理大量历史照片。

项目当前处于核心业务闭环建设阶段：工程结构、配置加载、日志初始化、最小 PySide6 启动链路、领域模型、应用服务、SQLite 仓储、文件系统扫描、Pillow 元数据读取和 CLI 扫描注册路径已经建立；完整桌面 UI、后台 Worker、缩略图缓存、Excel 导入、归档流程、AI 识别和用户复核仍在后续阶段实现。

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

- Python 3.11
- PySide6
- SQLite、SQLAlchemy、Alembic
- pandas、openpyxl
- OpenCV、Pillow
- InsightFace、ONNX Runtime
- Pydantic、pydantic-settings
- Loguru
- watchdog
- pytest、pytest-qt
- Ruff、Black、isort、MyPy、pre-commit

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

已完成：

- 顶层目录结构。
- Python 工程配置。
- 运行依赖与开发依赖规划。
- `.env.example` 示例配置。
- 应用启动入口。
- 配置加载与运行目录创建。
- Loguru 日志初始化。
- 最小 PySide6 主窗口。
- `domain/` 基础实体、值对象、异常和仓储接口。
- `application/` Command、DTO、Use Case 协议和应用服务。
- 人员 TXT 导入、Excel 导入、照片目录扫描、照片注册的基础应用服务。
- 本地照片文件扫描器和 Pillow 图片元数据读取适配器。
- 扫描目录、读取元数据、注册照片、更新文件夹统计的应用服务闭环。
- `python main.py scan <folder>` CLI 扫描注册入口。
- SQLite 连接、Schema 初始化、Repository 容器和基础仓储实现。
- App bootstrap 对配置、日志、运行目录和 SQLite 仓储的装配。
- Domain、Application、Infrastructure Repository、App bootstrap、扫描注册闭环和 CLI 入口测试。
- Worker 任务基类、事件模型、Qt 执行器和人员导入/扫描注册任务包装器。
- `ProgressReporter` 端口与扫描注册服务的进度回调契约。
- `UnitOfWork` 端口与 SQLite 事务边界，扫描注册闭环在事务内原子提交。
- PySide6 最小工作台：扫描目录按钮 + 进度条 + 状态栏 + ScanController 接入 QtWorkerExecutor。
- AI 开发知识库和工程规则。
- AI_ONBOARDING.md 统一入职指南与规则一致性审计报告。

待实现：

- SQLite 迁移体系和 Schema 版本演进规范（当前以 `PRAGMA user_version` 管理，SQLAlchemy/Alembic 推迟）。
- 缩略图生成与缓存数据。
- 人脸识别和匹配流程。
- 归档组织、导出结果和统计报告。
- UI、缩略图和 AI 流程相关集成测试与端到端工作流测试。

## 下一阶段计划

建议优先顺序：

1. 校准文档与当前代码状态，并维护 `docs/roadmap/` 阶段路线图。
2. 安装并验证完整运行依赖，让 Pillow 相关集成测试从 skipped 转为 passed。
3. 缩略图生成与缓存策略。
4. 在核心业务闭环稳定后接入 AI 人脸检测、识别、匹配和用户复核流程。
5. 归档组织、导出结果和统计报告。
6. SQLite 迁移体系（SQLAlchemy/Alembic）替代当前 `PRAGMA user_version` 管理。

## AI 协作说明

本项目包含 `.ai/` 知识库，用于约束 AI 编码助手的行为、架构边界、代码风格和审查标准。AI 助手在修改代码前必须阅读 `.ai/START_HERE.md`、`.ai/PROJECT_CONTEXT.md`、`.ai/TASK_WORKFLOW.md` 和 `.ai/rules/`。

根目录 `README.md` 面向所有项目读者；`.ai/` 面向 AI 协作流程。两者职责不同，应保持同步但避免重复维护规则正文。
