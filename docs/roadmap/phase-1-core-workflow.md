# Phase 1 Core Workflow Roadmap

> Last Updated: 2026-07-19

> ⚠️ **Phase 1 已完成**（2026-07-19 收尾，Step 0.5-13 全就绪）。
>
> 本文档为 Phase 1 历史路线图，保留作历史参考。**当前权威路线图**：`.ai/business/roadmap.md`（15 步）+ `.ai/PROJECT_STATUS.md`。
>
> 阅读本文件时请知：以下"尚未完成"清单已在 Phase 1 收尾时全部落地，Phase 2 Step 14 Export / Step 15 Plugin System 进行中。

## 目标

Phase 1 的目标是把 PhotoArchiver 从“基础架构可启动”推进到“核心业务闭环可运行”。本阶段不优先实现 AI 识别，而是先稳定人员导入、照片扫描、元数据读取、SQLite 持久化和最小 UI 操作路径。

## 当前状态

已完成：

- `domain/` 基础实体、值对象、异常和仓储接口。
- `application/` Command、DTO、Use Case 协议和应用服务。
- 人员 TXT 导入、照片目录扫描、照片注册的基础服务。
- 本地照片文件扫描器。
- Pillow 图片元数据读取适配器。
- 扫描目录、读取元数据、注册照片、更新文件夹统计的应用服务闭环。
- `python main.py scan <folder>` CLI 扫描注册入口。
- SQLite 连接、Schema 初始化、Repository 容器和基础仓储实现。
- 配置加载、日志初始化、运行目录创建和 App bootstrap 装配。
- 最小 PySide6 主窗口。
- Excel 人员导入适配器，支持有表头、无表头和指定 sheet。
- Worker 任务事件模型、任务基类，以及人员导入/照片扫描注册任务包装器。
- Domain、Application、Infrastructure Repository、App bootstrap、扫描注册闭环、CLI 入口、人员导入 reader 和 Pillow 元数据 reader 测试。

尚未完成：

- 缩略图生成与缓存。
- Qt Worker 执行器和 UI 任务接入。
- 可操作的 PySide6 工作台界面。
- AI 人脸检测、识别、匹配和用户复核。
- 归档组织、导出和统计报告。

## 开发顺序

1. 文档校准
    - 更新 README 当前进度。
    - 保持 `docs/deployment/project-structure.md` 与实际模块职责一致。
    - 后续每个阶段在 `docs/roadmap/` 维护独立路线图。

2. 扫描注册闭环
    - 已新增 `ScanAndRegisterPhotosService`，串联目录扫描、元数据读取、照片注册和 SQLite 写入。
    - 已明确重复照片路径的处理规则：同一路径再次扫描时跳过注册并计入 `skipped_count`。
    - 已明确 Folder 创建、查找、统计更新规则：按绝对路径查找，未存在时创建，扫描后更新总数和已处理数量。

3. 测试补强
    - 已覆盖扫描注册闭环中的重复文件、嵌套目录、空目录和 CLI 缺失目录失败路径。
    - 已补充 SQLite 写入闭环集成测试。
    - 已补充 Pillow 元数据读取的真实图片、损坏图片、目录路径和不存在路径专项测试。

4. Excel 人员导入
    - 已基于现有 `PersonImportReader` 端口实现 Excel reader。
    - 已支持有表头、无表头和指定 sheet。
    - 已统一字段清洗和空行跳过；重复 identity 策略由应用服务继续负责。

5. Worker 体系
    - 已定义后台任务基类、进度事件、完成事件和失败事件。
    - 已先接入人员导入和照片扫描注册任务包装器。
    - 保持 Worker 只负责任务执行和事件通知，不承载业务规则。
    - 待补充 Qt Worker 执行器，把同步任务安全地调度到后台线程。

6. 最小 UI 工作台
    - 增加人员导入入口。
    - 增加照片目录选择和扫描入口。
    - 展示扫描进度、结果数量和基础错误信息。
    - 展示基础照片列表，为缩略图和复核界面预留位置。

7. 缩略图缓存
    - 定义缓存目录、命名规则和失效策略。
    - 增加缩略图生成服务和测试。
    - 在 UI 列表中展示缩略图。

8. AI 识别预备
    - 定义 AI 检测、特征提取和匹配端口。
    - 定义识别结果 DTO 和用户复核数据模型。
    - 在核心闭环稳定后再接入 InsightFace / ONNX Runtime。

## 阶段完成标准

Phase 1 完成时应满足：

- 用户可以导入人员 TXT / Excel 数据。
- 用户可以选择照片目录并完成扫描。
- 系统可以读取图片元数据并把照片、文件夹和人员数据写入 SQLite。
- UI 可以展示导入和扫描的基础进度与结果。
- 长耗时导入和扫描不阻塞 UI。
- 核心业务路径有单元测试和至少一条集成测试覆盖。

## 约束

- `domain/` 不依赖 PySide6、Pillow、SQLite、pandas、OpenCV 或 AI 框架。
- `presentation/` 不直接访问数据库、文件系统适配器或 AI 模型。
- 所有业务流程经由 `application/` 编排。
- `infrastructure/` 只实现技术适配，不写业务决策。
- 新增数据库 Schema 或公开 API 前应先更新文档并补测试。
