# PhotoArchiver 开发入门指南

> Version: 1.2  ｜ Last Updated: 2026-08-01

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

安装开发依赖（**跑测试必须装 dev.txt 全套**，非可选）：

```bash
pip install -r requirements/dev.txt
```

> dev.txt 首行 `-r base.txt`，一条命令即装齐全套（含 PySide6 6.11.1 + pytest-qt 4.5.0）。`tests/unit/presentation/` 的 UI 测试用 `pytest.importorskip` 守卫——缺 PySide6 / pytest-qt 时这些测试会 skipped 而非 failed，静默掩盖缺口。装齐 dev.txt 是运行测试集的硬前提。

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

### 诊断 skipped 测试

缺 PySide6 / pytest-qt 或缺 buffalo_l 模型时，相关测试会 skipped 而非 failed。查看 skip 原因：

```bash
pytest -rs
```

两类典型 skip 原因：

- **缺 PySide6 / pytest-qt**：装 `pip install -r requirements/dev.txt`（见 §4，跑测试的硬前提）。
- **缺 buffalo_l 模型**：跑 `python scripts/download_models.py`（见 §12，ADR-012 禁自动下载）。

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

## 9. 持续集成（CI）

项目配备 GitHub Actions 工作流 `.github/workflows/ci.yml`，在每次 push 到 `main` 与所有 pull request 时自动运行，三平台矩阵（Ubuntu / Windows / macOS）× Python 3.11 全跑。

**流水线步骤**：

1. `ruff check .` — 静态分析
2. `mypy src` — 类型检查
3. `pytest -v --tb=short` — 全量测试，含 AI 集成测试

**AI 模型供给**：CI 用 `actions/cache@v4` 缓存 `resources/models/buffalo_l` 模型包，缓存命中时秒退；未命中时跑 `scripts/download_models.py` 幂等下载。模型就绪后追加一步显性断言 `test -d resources/models/buffalo_l` 防止缓存静默失败导致 8 条 AI 集成测试 skipped 而非 failed（ISSUE-008 关闭判据）。

**本地复现 CI**：

```bash
pip install -r requirements/dev.txt
python scripts/download_models.py
ruff check .
mypy src
pytest -v --tb=short
```

**Linux 无头环境**：CI 设 `QT_QPA_PLATFORM=offscreen` 让 pytest-qt 无显示运行；Linux runner 预装 Qt 系统库（`libgl1 libegl1 libxkbcommon0 libdbus-1-3 libfontconfig1`）。本地远程终端跑 UI 测试可同设此环境变量。

## 10. 开发流程建议

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

AI 编码助手必须遵守 `.ai/AI_ONBOARDING.md`（新 AI Runtime Context 入口，取代旧 `.ai/TASK_WORKFLOW.md`）。

## 11. 关键开发约束

- 不要绕过 `application/` 直接从 UI 调用基础设施。
- 不要在 `domain/` 中导入 PySide6、OpenCV、SQLite、pandas、InsightFace 等框架。
- 不要在 UI 类中编写业务逻辑。
- 不要在主线程执行目录扫描、AI 推理、批量导入、缩略图生成等耗时任务。
- 使用 `pathlib.Path` 处理文件路径。
- 使用 Loguru 记录日志，不使用 `print()`。
- 新增依赖、修改公开 API、调整数据库 Schema 或改变架构前需要明确确认。
- 修改代码时保持最小范围，避免无关重构。

## 12. 常见问题

### 找不到 `photo_archiver` 包

确认运行命令前已设置 `PYTHONPATH=src`，或未来以可编辑模式安装项目。

### PySide6 无法启动窗口

确认当前环境支持桌面 GUI，远程终端或无显示环境可能无法启动图形界面。

### 数据库文件不存在

启动时 `AppSettings.ensure_runtime_directories()` 会创建数据库所在目录。Schema 由 `infrastructure/database/sqlite_connection.py` 集中初始化并走 Alembic 迁移管理（`alembic_runner.py`，ADR-024，当前 `001_initial_v4`）。

### AI 模型目录为空

AI 推理已接入（InsightFace / ONNX Runtime，Step 8-10）。`MODEL_PATH` 默认 `resources/models`，**不自动创建该目录**（ADR-012）——由 `scripts/download_models.py` 手动下载模型，禁止自动下载。首次运行前需先跑该脚本。

### 为什么有测试被 skip？

两类原因：

- **缺 PySide6 / pytest-qt**：`tests/unit/presentation/` 的 UI 测试用 `pytest.importorskip` 守卫，缺装即 skip。装齐 `pip install -r requirements/dev.txt`（见 §4，跑测试的硬前提）后即转为真实运行。
- **缺 buffalo_l 模型**：`tests/integration/face_detection/` 的 AI 集成测试缺模型即 skip。跑 `python scripts/download_models.py` 后即转为真实运行。

用 `pytest -rs` 查看每条 skip 的具体原因（见 §7）。装齐 dev.txt + 模型后全量测试应无 skip（CI 流水线已用硬断言锁定此判据，见 §9）。

## 13. 下一步阅读

- `README.md`
- `docs/development/configuration.md`
- `docs/architecture/overview.md`
- `docs/deployment/project-structure.md`
- `.ai/AI_ONBOARDING.md`（AI Runtime Context 入口）
- `.ai/PROJECT_STATUS.md`（当前开发状态唯一权威）
- `.ai/rules/`（9 专项工程规则 + README + audit-methodology）
