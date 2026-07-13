# PhotoArchiver 配置说明

> Version: 1.0  
> Last Updated: 2026-07-03

本文档说明 PhotoArchiver 当前支持的环境变量、默认值、运行目录和配置约束。

## 1. 配置来源

应用配置由 `src/photo_archiver/infrastructure/config/settings.py` 中的 `AppSettings` 管理。

配置加载顺序：

1. `AppSettings` 默认值。
2. 项目根目录 `.env` 文件。
3. 当前进程环境变量。

字段名会映射到大写环境变量，例如 `app_name` 对应 `APP_NAME`。

项目提供 `.env.example` 作为本地配置模板。开发时应复制为 `.env` 后再修改：

```bash
cp .env.example .env
```

Windows CMD：

```cmd
copy .env.example .env
```

## 2. 当前配置项

| 环境变量        | 默认值                             | 说明                                       |
| --------------- | ---------------------------------- | ------------------------------------------ |
| `APP_NAME`      | `PhotoArchiver`                    | 应用名称。                                 |
| `APP_VERSION`   | `0.1.0`                            | 应用版本回退值。安装为包后优先读取包版本。 |
| `ENV`           | `development`                      | 当前运行环境。                             |
| `DEBUG`         | `false`                            | 是否启用调试模式。                         |
| `LOG_LEVEL`     | `INFO`                             | 日志等级。                                 |
| `LOG_DIRECTORY` | `logs`                             | 日志输出目录。                             |
| `DATABASE_URL`  | `sqlite:///data/photo_archiver.db` | SQLite 数据库 URL。                        |
| `MODEL_PATH`    | `models`                           | AI 模型目录。                              |
| `PHOTO_ROOT`    | 空                                 | 默认照片根目录，可留空。                   |
| `OUTPUT_ROOT`   | 空                                 | 默认输出目录，可留空。                     |
| `MAX_WORKERS`   | `4`                                | 后台任务最大 Worker 数量。                 |

## 3. 日志配置

支持的日志等级：

```text
TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL
```

日志配置由 `src/photo_archiver/infrastructure/logging/configuration.py` 初始化。

当前行为：

- 启动时会创建 `LOG_DIRECTORY`。
- `DEBUG=true` 且未显式设置 `LOG_LEVEL` 时，有效日志等级为 `DEBUG`。
- 日志必须使用 Loguru，不应使用 `print()`。

示例：

```env
DEBUG=true
LOG_LEVEL=DEBUG
LOG_DIRECTORY=logs
```

## 4. 数据库配置

当前仅支持 SQLite URL，必须使用 `sqlite:///` 前缀。

有效示例：

```env
DATABASE_URL=sqlite:///data/photo_archiver.db
```

无效示例：

```env
DATABASE_URL=postgresql://localhost/photo_archiver
DATABASE_URL=sqlite:///
```

启动时会创建数据库文件所在目录，但数据库表结构、迁移和仓储实现会在后续 Infrastructure 模块中完成。

## 5. 模型目录

`MODEL_PATH` 用于存放 AI 模型文件。

默认值：

```env
MODEL_PATH=models
```

启动时会自动创建该目录。当前 AI 推理流程尚未接入，因此该目录可以暂时为空。

后续接入 InsightFace / ONNX Runtime 时，模型加载逻辑应位于 `ai/` 或 `infrastructure/` 的适配器中，不能泄漏到 `domain/` 或 UI 层。

## 6. 照片根目录

`PHOTO_ROOT` 是可选配置，用于指定默认照片来源目录。

示例：

```env
PHOTO_ROOT=D:/Photos/Input
```

留空时配置值为 `None`，由 UI 或应用用例在运行时选择目录。

所有文件路径处理应使用 `pathlib.Path`。

## 7. 输出目录

`OUTPUT_ROOT` 是可选配置，用于指定归档结果或导出文件的默认输出目录。

示例：

```env
OUTPUT_ROOT=D:/Photos/Archived
```

留空时配置值为 `None`。如果设置了该值，启动时会自动创建目录。

## 8. Worker 数量

`MAX_WORKERS` 控制后台任务的并发上限。

当前限制：

```text
1 <= MAX_WORKERS <= 32
```

示例：

```env
MAX_WORKERS=4
```

目录扫描、Excel 导入、缩略图生成、AI 推理、批量导出等耗时任务后续都应通过 Worker 执行，避免阻塞 UI 主线程。

## 9. 示例 `.env`

```env
APP_NAME=PhotoArchiver
APP_VERSION=0.1.0
ENV=development
DEBUG=true

LOG_LEVEL=DEBUG
LOG_DIRECTORY=logs

DATABASE_URL=sqlite:///data/photo_archiver.db
MODEL_PATH=models
PHOTO_ROOT=
OUTPUT_ROOT=

MAX_WORKERS=4
```

## 10. 配置修改原则

- 新增配置项时，应先确认使用场景和所属层。
- 配置字段应集中在 `AppSettings` 管理。
- 修改配置格式可能影响启动流程，需同步更新 `.env.example`、README 和本文档。
- 不应在业务代码中散落读取环境变量。
- 不应在 `domain/` 层读取配置。
