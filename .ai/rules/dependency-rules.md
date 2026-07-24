# PhotoArchiver Dependency Rules

Version: 1.1.1

Status: Stable

Last Updated: 2026-07-24

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

| Module         | May Depend On                                     |
| -------------- | ------------------------------------------------- |
| app            | presentation, application, common                |
| presentation   | application, common                               |
| application    | domain, common                                    |
| domain         | common                                            |
| infrastructure | domain, common                                    |
| workers        | application, common, PySide6.QtCore (threading)   |
| ai             | infrastructure, domain, common                    |
| plugins        | application, common                               |
| common         | Standard Library only                             |

---

# 5. Presentation Rules

## DEP-001

Presentation MAY import:

* application
* common

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
* pandas
* openpyxl
* loguru
* pydantic
* pydantic-settings
* Pillow (Infrastructure image layer only)
* SQLAlchemy (Infrastructure database layer only) — 延后（ADR-005）：当前用 sqlite3 + `PRAGMA user_version` 管理 Schema 版本，SQLAlchemy/Alembic 迁移体系推迟到 roadmap Step 3 收尾或后续阶段。批准保留在 requirements 但零 import。
* alembic (Infrastructure database migrations only) — 同上延后（ADR-005），与 SQLAlchemy 配套推迟。
* watchdog (Infrastructure filesystem watcher only)
* pytest-qt (dev-only, UI smoke tests)

ONNX Runtime is approved as the AI model runtime when InsightFace models require it; it MUST remain inside the `ai/` layer or `infrastructure/` adapters and MUST NOT leak into Domain or Presentation.

Note: `insightface` pulls transitive dependencies (scikit-image, scipy, networkx, protobuf, onnx) that are not individually approved in this list — they are引入ed transitively through the `insightface` approval. Project code MUST NOT directly import these transitive dependencies; only insightface's own internals may use them. Direct imports of these transitive deps in project source require separate approval.

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
