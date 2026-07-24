# PhotoArchiver Architecture Rules

Version: 1.1.0

Status: Stable

Last Updated: 2026-07-19

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

> **分层依赖图+矩阵权威**：`.ai/rules/dependency-rules.md` §2（依赖原则与方向图）+ §4（模块依赖矩阵，含 `ai` / `workers` / `plugins` / `common` 全方向）。本节不复制图与矩阵正文，详见该处。当本文件 §5 与 DEP §4 矩阵表述不同时，以 DEP §4 为准（ADR R 段已裁决）。

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

## ARC-008 Common

Responsible for reusable utilities.

Examples:

- Constants
- Helpers
- Shared Exceptions
- Base Classes
- Validators

Common MUST remain lightweight.

---

# 5. Allowed Dependencies

> **依赖矩阵权威**：`.ai/rules/dependency-rules.md` §4（完整模块×可依赖矩阵）。本节不复制矩阵正文，详见该处。本文件 §6 列禁令以矩阵为准。

The matrix in DEP §4 is the SSOT for all module-to-module dependency allowances, including `ai`, `workers`, `plugins`, and `common` directions. §6 below enumerates the prohibitions that complement the matrix.

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

SQLite-backed repository implementations are exempted from the location above and MUST reside with the SQLite database layer in `infrastructure/database/` per ARC-014 §14. `infrastructure/repositories/` retains in-memory and other non-SQLite repository implementations.

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

The `common/logging/` option was removed: loguru is a third-party library, and the `common` module is restricted to the Standard Library only per DEP-071.

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