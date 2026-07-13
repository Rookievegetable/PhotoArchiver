# PhotoArchiver 开发入门指南

> Version: 1.0  
> Last Updated: 2026-07-03

本文档面向参与 PhotoArchiver 开发的人类开发者，说明如何准备环境、安装依赖、运行应用、执行测试和遵守基本开发约束。

## 1. 前置要求

- Python 3.11
- Git
- pip
- 支持桌面 GUI 的本地开发环境
- Windows 11 或 macOS 优先

项目使用 `src/` 布局，源码位于 `src/photo_archiver/`。

## 2. 获取代码

```bash
git clone https://github.com/Rookievegetable/PhotoArchiver.git
cd PhotoArchiver
```

如果你已经在本地工作区中，可直接进入项目根目录。

## 3. 创建虚拟环境

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

## 4. 安装依赖

安装运行依赖：

```bash
pip install -r requirements/base.txt
```

安装开发依赖：

```bash
pip install -r requirements/dev.txt
```

依赖说明见 `requirements/README.md`。

## 5. 配置本地环境

复制示例环境文件：

```bash
cp .env.example .env
```

Windows CMD：

```cmd
copy .env.example .env
```

然后根据本地环境调整 `.env`。完整配置说明见 `docs/development/configuration.md`。

## 6. 运行应用

开发环境推荐设置 `PYTHONPATH=src` 后运行入口文件。

Windows CMD：

```cmd
set PYTHONPATH=src
python main.py
```

PowerShell：

```powershell
$env:PYTHONPATH = "src"
python main.py
```

macOS / Linux：

```bash
PYTHONPATH=src python main.py
```

当前应用会完成配置加载、运行目录创建、日志初始化，并打开最小 PySide6 主窗口。

## 7. 运行测试

```bash
pytest
```

当前项目已经建立 `tests/` 目录，业务测试会随功能实现逐步补充。

建议新增功能时优先添加：

- Domain 单元测试。
- Application Service 单元测试。
- Infrastructure 适配器测试。
- Worker 行为测试。
- 必要的 UI 手动验证说明。

## 8. 代码质量检查

常用命令：

```bash
ruff check .
black .
isort .
mypy src
```

`pyproject.toml` 中已配置：

- Python 版本：3.11
- Black 行宽：100
- Ruff 行宽：100
- isort profile：black
- pytest 测试目录：`tests`
- MyPy Python 版本：3.11

## 9. 开发流程建议

每个开发任务建议遵循：

```text
理解需求
    ↓
确认影响模块
    ↓
检查现有实现
    ↓
分析架构归属
    ↓
制定实现计划
    ↓
最小范围实现
    ↓
自检和测试
    ↓
同步文档
```

AI 编码助手必须遵守 `.ai/TASK_WORKFLOW.md`。

## 10. 关键开发约束

- 不要绕过 `application/` 直接从 UI 调用基础设施。
- 不要在 `domain/` 中导入 PySide6、OpenCV、SQLite、pandas、InsightFace 等框架。
- 不要在 UI 类中编写业务逻辑。
- 不要在主线程执行目录扫描、AI 推理、批量导入、缩略图生成等耗时任务。
- 使用 `pathlib.Path` 处理文件路径。
- 使用 Loguru 记录日志，不使用 `print()`。
- 新增依赖、修改公开 API、调整数据库 Schema 或改变架构前需要明确确认。
- 修改代码时保持最小范围，避免无关重构。

## 11. 常见问题

### 找不到 `photo_archiver` 包

确认运行命令前已设置 `PYTHONPATH=src`，或未来以可编辑模式安装项目。

### PySide6 无法启动窗口

确认当前环境支持桌面 GUI，远程终端或无显示环境可能无法启动图形界面。

### 数据库文件不存在

启动时 `AppSettings.ensure_runtime_directories()` 会创建数据库所在目录，但业务表和迁移会在后续数据库模块中实现。

### AI 模型目录为空

当前 AI 功能尚未接入。`MODEL_PATH` 目录会被创建，但模型加载流程会在后续 AI 模块中实现。

## 12. 下一步阅读

- `README.md`
- `docs/development/configuration.md`
- `docs/architecture/overview.md`
- `docs/deployment/project-structure.md`
- `.ai/START_HERE.md`
- `.ai/rules/`
