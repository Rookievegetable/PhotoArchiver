# PhotoArchiver Dependency Rules

Version: 1.2.0

Status: Stable

Last Updated: 2026-09-28

---

# 1. Purpose

This document defines the dependency rules for the PhotoArchiver project.

The objective is to maintain:

* Low coupling
* High cohesion
* Clear module boundaries
* Stable architecture
* Predictable code organization

All source code MUST comply with these dependency rules.

---

# 2. Dependency Principle

The project follows the Dependency Inversion Principle (DIP).

Core business logic must never depend on implementation details.

Allowed dependency direction:

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

The Domain layer is the center of the architecture.

---

# 3. Approved Modules

> **模块职责 SSOT**：`.ai/rules/architecture-rules.md` §4（ARC-001~009，含子包与特殊目录补录）。本节仅列模块清单与依赖授权，不重复职责正文。

The following modules are recognized by the project:

```text
photo_archiver
├── app
├── presentation
├── application
├── domain
├── infrastructure
├── workers
├── ai
├── common
└── plugins
```

Dependencies outside these modules require explicit approval.

---

# 4. Dependency Matrix

> **修订（2026-09-28，全面工程健康体检 AUD-009 整改）**：本矩阵与实际 import（AST 实测）及分层守卫测试 `tests/unit/architecture/test_layer_boundaries.py` 对齐——此前 5 行为端口迁移到 Application 层与 TaskCoordinator 接线之前的历史快照。守卫测试是"机器可判定禁令"的常驻自动化；本矩阵是其声明口径。

| Module         | May Depend On                                     | 备注（对齐守卫测试与现状） |
| -------------- | ------------------------------------------------- | --- |
| app            | presentation, application, domain, infrastructure, workers, ai, plugins, common | 组合根/装配层，import 全开（守卫测试明确豁免 app） |
| presentation   | application, domain, common, workers, plugins（ADR-038 插件宿主）, app（仅 `app.context` 类型引用） | 禁止 infrastructure / ai / sqlite3 / cv2 / insightface（DEP-002，守卫测试强制） |
| application    | domain, common                                    | 无 GUI、无 SQL/图像栈；依赖倒置只经 ports |
| domain         | common                                            | 零框架依赖（DEP-020/021） |
| infrastructure | domain, common, **application（ports + dtos）**   | application/ports 为系统侧端口（exporter/unit_of_work/user_settings_store/photo_file_scanner/thumbnail_generator/person_import_reader 等），适配器实现端口并消费其 DTO——Clean Architecture 合法方向 |
| workers        | application, common, domain, PySide6.QtCore (threading) | domain 仅实体/枚举引用（application_tasks/export_task）；Qt 限 QtCore（WRK-002） |
| ai             | infrastructure, domain, common                    | 现状仅依赖 domain（比声明更严格） |
| plugins        | application, common                               | DEP-060 |
| common         | Standard Library only                             | DEP-071 |

---

# 5. Presentation Rules

## DEP-001

Presentation MAY import:

* application
* domain（实体/值对象/域异常——视图与控制器消费业务对象）
* common
* workers（任务提交与事件，经 `TaskCoordinator`/`QtWorkerExecutor` 边界）
* plugins（仅 MainWindow 插件宿主持有 `PluginRegistry`，ADR-038）
* app（仅 `app.context.ApplicationContext` 类型引用）

---

## DEP-002

Presentation MUST NOT import:

* infrastructure
* sqlite3
* cv2
* insightface
* pandas
* openpyxl

---

## DEP-003

Presentation MUST communicate with business logic through Application Services only.

---

## DEP-004

Presentation MUST NOT instantiate repository implementations.

Correct:

```python
service.import_photos(...)
```

Wrong:

```python
SQLitePhotoRepository(...)
```

---

# 6. Application Rules

## DEP-010

Application MAY depend on:

* domain
* common

---

## DEP-011

Application MUST NOT import PySide6.

---

## DEP-012

Application MUST NOT execute SQL.

---

## DEP-013

Application MUST use repository interfaces.

Correct:

```python
PhotoRepository
```

Wrong:

```python
SQLitePhotoRepository
```

---

# 7. Domain Rules

## DEP-020

Domain MUST remain framework independent.

---

## DEP-021

Domain MUST NOT import:

* PySide6
* OpenCV
* InsightFace
* sqlite3
* pandas
* openpyxl

---

## DEP-022

Domain MAY use:

* dataclasses
* enum
* pathlib
* typing

---

## DEP-023

Domain defines interfaces but never implementations.

---

# 8. Infrastructure Rules

## DEP-030

Infrastructure MAY depend on:

* domain
* common
* application（**ports + dtos**——适配器实现 `application/ports/*` 系统侧端口并消费其 DTO；这是依赖倒置的正确方向，守卫测试放行。禁止依赖 application/services 内部实现细节）

---

## DEP-031

Infrastructure implements repository interfaces.

---

## DEP-032

Infrastructure MAY use:

* sqlite3
* OpenCV
* InsightFace
* pandas
* openpyxl

---

## DEP-033

Infrastructure MUST NOT depend on Presentation.

---

# 9. Worker Rules

## DEP-040

Workers MAY depend on:

* application
* common
* domain（实体/枚举引用，如 `RecognitionRun`/`ExportScope` 消费）
* PySide6.QtCore (threading primitives only, e.g. QObject, QRunnable, QThreadPool, Signal, Slot)

The PySide6.QtCore allowance is a threading boundary dependency required to satisfy WRK-002. Workers MUST NOT import widgets or any other PySide6 submodules outside QtCore.

---

## DEP-041

Workers MUST NOT manipulate UI widgets directly.

---

## DEP-042

Workers communicate through Qt Signals.

---

# 10. AI Module Rules

## DEP-050

The AI module MAY depend on:

* infrastructure
* domain
* common

---

## DEP-051

The AI module MUST NOT update the UI.

---

## DEP-052

Recognition results MUST be returned to the Application layer.

---

# 11. Plugin Rules

## DEP-060

Plugins MAY depend on:

* application
* common

---

## DEP-061

Plugins MUST NOT modify internal project modules.

---

## DEP-062

Plugins communicate only through public interfaces.

---

# 12. Common Module Rules

## DEP-070

The common module provides reusable utilities.

Examples:

* constants
* exceptions
* helpers
* validators
* base classes

---

## DEP-071

Common MUST NOT depend on any project module.

---

# 13. Third-Party Libraries

Approved libraries:

* PySide6
* InsightFace
* OpenCV
* pandas (Infrastructure data layer only) — 已批准未使用：Step 14 Export 落地启用，当前零 import。
* openpyxl
* loguru
* pydantic
* pydantic-settings
* Pillow (Infrastructure image layer only)
* SQLAlchemy (Infrastructure database layer only) — 已投入使用：Alembic 迁移体系（`alembic_runner.py`）依赖 SQLAlchemy Engine 连接到 SQLite。仓储层仍使用 raw sqlite3（ORM 未引入），SQLAlchemy 仅被 Alembic 使用。MUST NOT leak into Application or Domain.
* alembic (Infrastructure database migrations only) — 已投入使用：Schema 迁移管理（`alembic/` 目录 + `alembic.ini`）。每次启动由 `alembic_runner.run_alembic_migrations()` 自动 upgrade head。
* watchdog — 已批准未使用：filesystem watcher 用途预留，当前零 import。若未来启用须落 Infrastructure filesystem 层并补本节层归属注。
* platformdirs (Infrastructure config layer only) — 已投入使用（ADR-035）：默认数据库/日志路径锚定用户数据目录（`settings.py` 的 `default_database_url` / `default_log_directory`）。MUST NOT leak into Domain, Application or Presentation.
* pytest-qt (dev-only, UI smoke tests)

ONNX Runtime is approved as the AI model runtime when InsightFace models require it; it MUST remain inside the `ai/` layer or `infrastructure/` adapters and MUST NOT leak into Domain or Presentation.

Note: `insightface` pulls transitive dependencies (scikit-image, scipy, networkx, protobuf, onnx) that are not individually approved in this list — they are introduced transitively through the `insightface` approval. Project code MUST NOT directly import these transitive dependencies; only insightface's own internals may use them. Direct imports of these transitive deps in project source require separate approval.

Additional third-party dependencies require project approval.

---

# 14. Import Guidelines

> **命名/导入规范权威**：`.ai/rules/coding-rules.md` §3 Imports（COD-010~013，含导入顺序、wildcard/unused/circular 禁令）。本节不重复 COD-010~013 正文——依赖矩阵视角的导入约束已与 COD-010~013 完全一致，详见彼处。

---

# 15. Dependency Injection

Application Services SHOULD receive dependencies through constructors.

Example:

```python
class ImportService:
    def __init__(self, repository: PhotoRepository):
        self._repository = repository
```

Avoid creating dependencies internally.

Wrong:

```python
repo = SQLitePhotoRepository()
```

---

# 16. Repository Pattern

> ⚠ **SQLite 仓储位置例外（A1 收口，2026-07-24）**：`architecture-rules.md` §8 已加例外条款——SQLite-backed 仓储实现归 `infrastructure/database/`，`infrastructure/repositories/` 保留非 SQLite 实现（如 InMemory 测试替身）。本节下表是对齐后的表述。

Repository interfaces belong to:

```text
domain/repositories/
```

Repository implementations belong in:

```text
infrastructure/repositories/      ← 非 SQLite 实现（InMemory 等）
infrastructure/database/           ← SQLite-backed 实现（见 ARC §8 例外，ADR R-2/R-4 已执行）
```

Application depends only on interfaces.

---

# 17. External Resources

Only Infrastructure may access:

* File System
* SQLite
* Image Files
* Configuration Files

Business logic must remain independent of external resources.

---

# 18. Circular Dependency Policy

Circular dependencies are strictly prohibited.

If detected:

1. Extract shared abstractions.
2. Move interfaces to Domain.
3. Refactor responsibilities.

Never solve circular imports with delayed imports unless there is no reasonable architectural alternative.

---

# 19. Review Checklist

> **总表权威**：`.ai/rules/review-rules.md` §22。本节是 §22 在依赖层的细化，不重复总表。

Before merging code, verify:

* [ ] Dependency direction is correct.
* [ ] No forbidden imports.
* [ ] Domain is framework independent.
* [ ] Application uses interfaces.
* [ ] Infrastructure contains implementations.
* [ ] No circular dependencies.
* [ ] Workers communicate via Signals.
* [ ] Plugins use public APIs.
* [ ] Common remains dependency-free.

---

# 20. Summary

The dependency rules protect the architectural integrity of PhotoArchiver.

Every new module, service, worker, repository, and plugin must comply with these dependency constraints.

Violations should be corrected before code is merged into the main branch.

---

End of Document
