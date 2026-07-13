# PhotoArchiver 项目结构说明（Project Structure Guide）

> Version：1.0
> Last Updated：2026-07-01

---

# 1. 文档目的

本文档用于说明 PhotoArchiver 项目的整体目录结构、模块职责以及各目录之间的关系。

项目采用企业级分层架构（DDD + Clean Architecture），遵循**高内聚、低耦合**原则，并结合 PySide6 桌面应用开发规范设计。

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
├── .trae/
├── assets/
├── config/
├── data/
├── docs/
├── examples/
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

---

# 3. 顶层目录说明

## .ai

AI 开发规则库。

用于存放：

- AI Prompt
- AI 编码规范
- AI 业务规则
- 架构说明
- 模板

该目录仅供 AI 辅助开发使用，不参与程序运行。

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

项目配置文件。

后续将包括：

- 环境配置
- 日志配置
- 主题配置
- 应用配置

所有配置统一管理。

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

项目所有文档。

包括：

- 架构设计
- API
- 部署文档
- 开发规范
- Roadmap

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

## requirements

Python 依赖管理。

包括：

- base.txt
- dev.txt

后续所有依赖统一在这里维护。

---

## resources

程序运行资源。

包括：

- 图标
- 字体
- UI
- 图片
- AI 模型

程序运行时直接读取该目录。

---

## scripts

项目维护脚本。

例如：

- 初始化项目
- 创建目录
- 构建
- 打包

所有自动化脚本统一放置。

---

## src

项目源码目录。

所有业务代码均放在这里。

---

## tests

测试代码。

包括：

- 单元测试
- 集成测试
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
├── common/
├── domain/
├── infrastructure/
├── plugins/
├── presentation/
└── workers/
```

---

## ai

AI 能力模块。

负责：

- 人脸检测
- 人脸识别
- 特征提取
- 人脸聚类
- 模型加载

不负责业务流程。

---

## app

应用启动模块。

负责：

- QApplication
- 生命周期
- 启动流程
- 全局初始化
- 运行时依赖装配

整个程序只有一个入口。

当前启动流程由 `bootstrap_application()` 负责装配运行时上下文：

- 加载并校验应用配置
- 初始化日志系统
- 初始化 SQLite Repository schema
- 构建 `ApplicationContext`

`ApplicationContext` 暴露：

- `settings`：运行时配置
- `repositories`：SQLite-backed Repository 容器

---

## application

应用业务层。

负责：

- Use Case
- Service
- Command
- DTO

它连接：

UI → Domain → Infrastructure

属于整个系统的大脑。

---

## common

公共模块。

包括：

- 工具类
- 配置
- 日志
- 常量
- 异常
- 通用函数

任何模块都可以依赖 common。

---

## domain

领域层。

这是整个系统最核心的一层。

包括：

- Entity
- Repository Interface
- Domain Service
- Value Object

特点：

不依赖任何第三方框架。

---

## infrastructure

基础设施层。

负责：

- SQLite
- Excel
- TXT
- 文件系统
- AI 模型加载
- 持久化

负责和外部世界通信。

---

## plugins

插件系统。

未来可以扩展：

- OCR
- 云存储
- 第三方接口
- AI 插件

第一版项目不会大量使用。

---

## presentation

界面层。

负责：

- PySide6 UI
- Dialog
- Widget
- View

不处理业务逻辑。

---

## workers

后台线程。

负责：

- AI 推理
- 文件扫描
- Excel 导入
- 图片处理

避免阻塞 UI。

---

# 6. 分层调用关系

项目遵循如下依赖关系：

```text
Presentation
      │
      ▼
Application
      │
      ▼
Domain
      ▲
      │
Infrastructure
```

说明：

- Presentation 不直接访问数据库。
- Domain 不依赖 PySide6。
- Infrastructure 不包含业务规则。
- 所有业务统一由 Application 调度。

---

# 7. 资源目录说明

resources 用于存放运行时资源：

```text
resources/
├── fonts/
├── icons/
├── images/
├── models/
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

建议文档分类如下：

```text
docs/
├── api/
├── architecture/
├── deployment/
├── design/
├── development/
├── roadmap/
└── user-guide/
```

保持文档与代码同步更新。

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
