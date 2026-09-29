# PhotoArchiver Architecture Rules

Version: 1.1.1

Status: Stable

Last Updated: 2026-07-24

---

# 1. Purpose

This document defines the architectural rules of the PhotoArchiver project.

All source code MUST comply with these architecture constraints.

These rules protect the long-term maintainability, scalability and testability of the project.

---

# 2. Architecture Overview

PhotoArchiver adopts:

- Domain Driven Design (DDD)
- Clean Architecture
- Layered Architecture

> **分层依赖图+矩阵权威**：`.ai/rules/dependency-rules.md` §2（依赖原则与方向图）+ §4（模块依赖矩阵，含 `ai` / `workers` / `plugins` 全方向）。本节不复制图与矩阵正文，详见该处。当本文件 §5 与 DEP §4 矩阵表述不同时，以 DEP §4 为准（ADR R-8 已裁决，见 `ARCHITECTURE_DECISIONS.md`）。

Dependencies MUST always point toward the Domain layer.

---

# 3. Project Layers

The source code is organized under:

```

src/photo_archiver/

```

The following modules are approved:

```

app/

presentation/

application/

domain/

infrastructure/

common/

workers/

ai/

plugins/

```

No additional top-level package may be introduced without approval.

---

# 4. Layer Responsibilities

## ARC-001 Presentation

Responsible for:

- UI
- Windows
- Dialogs
- Widgets
- User Interaction
- View Models
- Signal Connections

May depend on:

- Application
- Common

Must NOT depend on:

- Infrastructure
- SQLite
- OpenCV
- InsightFace

---

## ARC-002 Application

Responsible for:

- Use Cases
- Workflow Coordination
- Command Processing
- Service Orchestration

Application Services coordinate business operations.

Application MUST NOT contain GUI logic.

---

## ARC-003 Domain

Responsible for:

- Business Rules
- Entities
- Value Objects
- Repository Interfaces
- Domain Services
- Business Exceptions

Domain is the core of the project.

---

## ARC-004 Infrastructure

Responsible for:

- SQLite
- File System
- Image IO
- Repository Implementations
- Configuration
- Logging
- OpenCV
- InsightFace Adapter

Infrastructure implements interfaces defined by Domain.

---

## ARC-005 Workers

Responsible for:

Background execution.

Workers MUST execute:

- Image scanning
- Folder creation
- Face recognition
- Thumbnail generation
- Excel import
- Export

Workers MUST NOT contain business rules.

---

## ARC-006 AI

Responsible for:

- Face Recognition
- Face Encoding
- Similarity Search
- Model Management

The AI layer provides AI capability only.

Business decisions belong elsewhere.

---

## ARC-007 Plugins

Responsible for:

Optional extension modules.

Plugins MUST communicate through public interfaces.

Plugins MUST NOT modify internal architecture.

---

## ARC-008 Common（**Removed 2026-09-29，Stage 13C-A / AUD-013**）

The `common/` package was an empty one-line skeleton with **zero** importers
across `src/`, `tests/` and `main.py`; every "responsibility" listed for it
(constants, helpers, shared exceptions, base classes, validators) was either
unused or already lives in a more appropriate module (`domain/exceptions.py`,
`infrastructure/logging/`, `application/dtos/`). An approved-but-empty package
invites either dead code or misplaced utilities, so it was **removed** together
with its entries in the DEP §3 module list / §4 matrix (Stage 13C-A). Utilities
MUST be placed in the module that owns the concern (domain value objects,
application ports, infrastructure adapters) rather than a shared bag.

---

## ARC-010 UseCase Protocol 使用准则（新增 2026-09-29，Stage 13C-A / AUD-011）

**Protocol 与 Service 不要求一一映射**（ADR-050）。准则：

1. **需要 Protocol**：能力跨越 application 边界（presentation 控制器、worker 任务
   注入、组合根替换、插件可替换点）——调用方按接口类型标注，组合根注入实现。
2. **不需要 Protocol**：仅由组合根经 `ApplicationServices`（具体类字段标注）暴露的
   应用内能力；当前全部消费者与具体实现同进程同根，无替换需求。
3. **不得为凑齐而批量新建**：新增 service 不自动要求 Protocol；仅在出现第二个消费者
   或替换需求时再提取。
4. **已声明的 Protocol 不得无消费者悬挂**：若某 Protocol 除"被其 service 继承"外无任何
   标注方，视为契约冗余候选（当前 3 项：RegisterPhoto / ScanPhotoFolder / PruneMissingPhotos
   ——CLI 经组合根具体类驱动，其删除触及 `application/__init__.py` 公开导出，属 Owner
   API 决策，ADR-050 记录为待决变体）。

## ARC-011 MainWindow 职责边界（新增 2026-09-29，Stage 13C-A / AUD-013）

`presentation/views/main_window.py`（1578 行 / 63 方法）体积大但**职责已外移**：
事件路由（29 个 `_on_*`）、UI 构建（8 个 `_build_*`）、状态同步（5 个 `_refresh_*`）
与编排调用（service `.execute`），**无业务规则、无文件/SQL 触点**。规则：
MainWindow MUST 只做装配/路由/状态同步；任何业务判定 MUST 落入 controller/presenter/
application service。新增能力时按此分流，不以行数为拆分理由（禁止
`MainWindowPart1/2/3` 式机械切分）。

## ARC-009 子包与特殊目录职责补录

> 本节补录代码现状中已存在但 §3 模块清单未显式列出的子包与目录职责。模块顶层归属仍以 §3 + DEP §4 矩阵为准。

| 路径 | 职责一句话 | 归属 |
|---|---|---|
| `application/commands/` | 命令对象（Command DTO），表达用例入参 | Application 子包 |
| `application/dtos/` | 数据传输对象，含用例返回模型与 Settings DTO | Application 子包 |
| `application/ports/` | 端口（Port）抽象，系统侧与用户侧仓储/存储接口 | Application 子包 |
| `application/use_cases/` | Use Case 协议（Protocol），声明用例契约 | Application 子包 |
| `application/services/` | Application Service 编排实现 | Application 子包 |
| `infrastructure/persistence/` | 用户偏好持久化适配器（QSettings/InMemory），不涉 SQLite | Infrastructure 子包 |
| `infrastructure/database/` | SQLite 连接、Schema、`SQLiteUnitOfWork`、SQLite 仓储实现（ARC §8 例外条款） | Infrastructure 子包 |
| `infrastructure/repositories/` | 非 SQLite 仓储实现（如 InMemory 测试替身） | Infrastructure 子包 |
| `infrastructure/exporters/` | 导出器适配器（Excel/CSV），roadmap Step 14 落地 | Infrastructure 子包 |
| `config/`（顶层） | 仅静态配置文件目录（如 `.env`、主题样式），**非 Python 模块**，不进 DEP §4 矩阵 | 非 Python 模块 |

> `infrastructure/persistence/` 与 `infrastructure/database/` 分立：前者管用户偏好（QSettings 平台原生位置），后者管业务数据（SQLite）。二者均不越界。

---

# 5. Allowed Dependencies

> **依赖矩阵权威**：`.ai/rules/dependency-rules.md` §4（完整模块×可依赖矩阵）。本节不复制矩阵正文，详见该处。本文件 §6 列禁令以矩阵为准。

The matrix in DEP §4 is the SSOT for all module-to-module dependency allowances, including `ai`, `workers`, and `plugins` directions. §6 below enumerates the prohibitions that complement the matrix.

---

# 6. Forbidden Dependencies

Presentation

MUST NOT import Infrastructure.

---

Presentation

MUST NOT import SQLite.

---

Presentation

MUST NOT import OpenCV.

---

Presentation

MUST NOT import InsightFace.

---

Domain

MUST NOT import PySide6.

---

Domain

MUST NOT import SQLite.

---

Domain

MUST NOT import OpenCV.

---

Domain

MUST NOT import Pandas.

---

Domain

MUST NOT import NumPy.

---

Application

MUST NOT manipulate UI widgets.

---

Infrastructure

MUST NOT implement business decisions.

---

Workers

MUST NOT access widgets directly.

---

Plugins

MUST NOT bypass public APIs.

---

# 7. Entity Rules

Entities belong only in:

```

domain/entities/

```

Entities represent business concepts.

Examples:

Person

Photo

Folder

ArchiveRecord

RecognitionResult

Entities MUST NOT inherit QWidget.

Entities MUST NOT contain database logic.

---

# 8. Repository Rules

Repository interfaces belong in:

```

domain/repositories/

```

Repository implementations belong in:

```

infrastructure/repositories/

```

SQLite-backed repository implementations are exempted from the location above and MUST reside with the SQLite database layer in `infrastructure/database/` per §14 Database Rules. `infrastructure/repositories/` retains in-memory and other non-SQLite repository implementations.

Application MUST use interfaces.

Never concrete implementations.

---

# 9. Service Rules

Application Services

Location

```

application/services/

```

Responsibilities

- Coordinate workflows
- Call repositories
- Execute use cases

Application Services MUST NOT contain SQL.

---

Domain Services

Location

```

domain/services/

```

Responsibilities

Pure business rules.

No GUI.

No database.

---

Infrastructure Services

Location

```

infrastructure/services/

```

Responsibilities

External systems.

Filesystem.

SQLite.

Image loading.

---

# 10. Controller Rules

Controllers belong in:

```

presentation/controllers/

```

Responsibilities

Receive UI events.

Invoke Application.

Update UI.

Controllers MUST NOT perform business calculations.

---

# 11. View Rules

Views belong in:

```

presentation/views/

```

Views MUST:

Display information.

Receive input.

Emit signals.

Views MUST NOT:

Access database.

Execute OpenCV.

Recognize faces.

---

# 12. Worker Rules

Workers belong in:

```

workers/

```

Workers receive tasks.

Workers emit progress.

Workers emit completion.

Workers MUST NOT update widgets directly.

---

# 13. AI Module Rules

AI components belong in:

```

ai/

```

Examples

FaceDetector

FaceEncoder

RecognitionEngine

SimilarityMatcher

AI modules return results.

They MUST NOT update UI.

---

# 14. Database Rules

SQLite belongs only in:

```

infrastructure/database/

```

No other layer may execute SQL.

---

# 15. File System Rules

Filesystem operations belong only in:

```

infrastructure/filesystem/

```

Never inside:

Presentation

Domain

---

# 16. Image Processing Rules

OpenCV belongs only in:

```

infrastructure/image/

```

Never inside:

Presentation

Application

Domain

---

# 17. Configuration Rules

Configuration loading belongs in:

```

config/

or

infrastructure/config/

```

Configuration MUST be centralized.

Hard-coded configuration is prohibited.

---

# 18. Logging Rules

Logging belongs in:

```

infrastructure/logging/

```

Business code MUST NOT configure loggers.

The `common/logging/` option was removed: loguru is a third-party library. The `common` module itself was removed entirely in 2026-09 (Stage 13C-A / AUD-013, see ARC-008).

---

# 19. Dependency Injection

Application SHOULD depend on interfaces.

Concrete implementations are assembled during application startup.

Avoid global singleton objects.

---

# 20. Module Communication

Preferred communication:

Presentation

↓

Application

↓

Repository Interface

↓

Infrastructure

Avoid skipping layers.

---

# 21. Project Workflow

> **业务工作流权威定义**：`.ai/business/roadmap.md` §2（15 步路线图）。本节不复制工作流正文，详见该处。Application Services coordinate the workflow defined there.

---

# 22. Extension Rules

New modules MUST satisfy:

Correct layer.

Correct dependency.

Clear responsibility.

No duplicated functionality.

Architecture review required.

---

# 23. Review Checklist

> **总表权威**：`.ai/rules/review-rules.md` §22。本节是 §22 在架构层的细化，不重复总表。

Before merging code verify:

- [ ] Layer responsibility respected
- [ ] No forbidden dependency
- [ ] Domain remains framework-independent
- [ ] Infrastructure implements interfaces
- [ ] UI contains no business logic
- [ ] SQL isolated
- [ ] OpenCV isolated
- [ ] AI isolated
- [ ] Workers independent
- [ ] Repository pattern followed

---

# 24. Summary

The PhotoArchiver architecture emphasizes:

- Low coupling
- High cohesion
- Clear responsibilities
- Stable dependencies
- Framework isolation
- Business-first design

Every architectural decision should strengthen these principles.

---

End of Document