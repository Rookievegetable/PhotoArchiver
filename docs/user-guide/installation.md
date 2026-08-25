# 安装与首次运行

> 本文档面向 PhotoArchiver 的最终使用者。开发者环境准备请参阅 [`docs/development/getting-started.md`](../development/getting-started.md)。

## 1. 前置要求

| 项目 | 要求 |
|---|---|
| Python | **3.11**（不向后兼容） |
| 操作系统 | Windows（优先）/ macOS |
| 网络 | 首次下载人脸识别模型包需要联网（约 300 MB） |

## 2. 获取与安装

```bash
git clone https://github.com/Rookievegetable/PhotoArchiver.git
cd PhotoArchiver

python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements/base.txt
```

> 只使用图形界面与命令行时安装 `base.txt` 即可；参与开发或运行测试套件需改装 `requirements/dev.txt`（其已包含 base 全集）。

## 3. 初始化配置

复制示例配置并按需修改：

```bash
cp .env.example .env    # Windows CMD: copy .env.example .env
```

最终用户最常调整的三项：

| 配置项 | 说明 |
|---|---|
| `ARCHIVE_ROOT` | **归档根目录（归档功能必填）**。归档目标结构为 `{ARCHIVE_ROOT}/{人员名}/{日期或事件}/{原文件名}` |
| `OUTPUT_ROOT` | 导出报告等产物的默认输出目录 |
| `MATCH_THRESHOLD` | 人脸匹配置信度阈值，范围 `[0.0, 1.0]`，默认 `0.40`（越低越宽松） |

完整配置项（含数据库路径、模型路径、日志等级、并发数等）见 `.env.example` 注释与 `docs/development/configuration.md`。

## 4. 下载人脸识别模型（必需）

识别功能依赖 InsightFace `buffalo_l` 模型包，出于体积考虑**不入仓库**，需手动下载一次：

```bash
python scripts/download_models.py
```

模型会被解包至 `resources/models/`。未下载模型时，"识别匹配"相关动作会明确报错提示，其余功能（导入、扫描、审核、归档、导出、查重）不受影响。

## 5. 启动

### 图形界面

```bash
python main.py
```

入口脚本会自动完成：配置加载 → 运行目录创建 → 日志初始化 → 打开主窗口。

### 命令行（可选）

| 命令 | 用途 |
|---|---|
| `python main.py scan <照片目录>` | 扫描并注册照片（默认递归，加 `--no-recursive` 仅扫一层） |
| `python main.py archive --archive-root <目录>` | 将全部已审核通过的照片归档（支持 `--dry-run` 预演、`--conflict-strategy skip/overwrite/rename`） |
| `python main.py backfill-content-hash` | 为历史数据一次性补齐内容哈希（幂等，重复执行无副作用） |

## 6. 数据与日志位置

| 内容 | 默认位置 |
|---|---|
| 业务数据库（单文件 SQLite） | `data/photo_archiver.db`（由 `DATABASE_URL` 控制） |
| 缩略图缓存 | 输出目录下 `thumbnails/` |
| 运行日志 | `logs/photo_archiver.log`（10 MB 轮转，保留 30 天） |

备份时仅需拷贝数据库文件即可完整保留人员、照片登记、审核状态与归档记录。
