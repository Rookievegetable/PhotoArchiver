# PhotoArchiver Worker Rules

Version: 1.0.2

Status: Stable

Last Updated: 2026-07-24

---

# 1. Purpose

This document defines the standards for all background tasks (Workers) in the PhotoArchiver project.

Workers are responsible for executing long-running operations without blocking the user interface.

All Worker implementations MUST comply with these rules.

---

# 2. Objectives

Workers are designed to:

* Keep the UI responsive.
* Execute long-running tasks safely.
* Report progress.
* Support cancellation.
* Handle exceptions gracefully.
* Isolate background processing from UI logic.

---

# 3. Worker Responsibilities

Workers MAY perform:

* Folder scanning
* Image scanning
* Thumbnail generation
* Face recognition
* Batch import
* Batch export
* Archive generation
* Cache building
* Database synchronization

Workers MUST NOT perform UI rendering.

---

# 4. Worker Architecture

Worker responsibilities:

```text
UI
│
▼
Application Service
│
▼
Worker
│
▼
Infrastructure / AI
│
▼
Result
│
▼
Application
│
▼
UI
```

Workers are execution units.

Business decisions belong to the Application layer.

---

# 5. Approved Worker Framework

The Worker layer is a **generic executor framework**, not a fixed set of named Worker classes. The earlier list of 9 concrete classes (`FolderScanWorker` etc.) was aspirational and never landed in code — the actual implementation is:

* `QtWorkerExecutor` (`src/photo_archiver/workers/`) — the single executor owning a `QThreadPool`.
* `task` / `application_tasks` (`src/photo_archiver/workers/`) — task registration helpers wiring Application services onto the executor.
* `events` (`src/photo_archiver/workers/events.py`) — `TaskStarted` / `TaskProgress` / `TaskFailed` / `TaskCompleted` signal carriers.

New long-running operations are registered as tasks through this framework rather than subclassing a named Worker type. Architecture review is required before introducing a new named Worker class — the default path is registering a task against the executor.

---

# 6. Thread Model

## WRK-001

Workers MUST execute outside the UI thread.

---

## WRK-002

Use Qt threading facilities.

Approved:

* QThread
* QObject + moveToThread()
* QThreadPool
* QRunnable

These primitives are sourced from `PySide6.QtCore`. The Workers-layer threading boundary dependency on `PySide6.QtCore` is authorized by DEP-040. Workers MUST NOT import any other PySide6 submodules (QtWidgets, QtGui, etc.).

---

## WRK-003

Long-running work MUST NOT execute inside QWidget subclasses.

---

# 7. Worker Structure

Each Worker SHOULD contain:

* Initialization
* Execution
* Progress reporting
* Completion notification
* Error reporting
* Cancellation support
* Cleanup

---

# 8. Signal Rules

Workers SHOULD expose signals for:

```python
started
progress
message
warning
finished
error
cancelled
```

Signals provide communication with the Presentation layer.

Workers MUST NOT access UI objects directly.

---

# 9. Progress Reporting

## WRK-010

Workers SHOULD report progress as percentages when possible.

Example:

```text
0 → 100
```

---

## WRK-011

For unknown workloads, Workers SHOULD report completed items.

Example:

```text
Scanning image 135 / 842
```

---

# 10. Cancellation

## WRK-020

Long-running Workers MUST support cancellation.

---

## WRK-021

Cancellation SHOULD be cooperative.

Workers periodically check:

```python
self.is_cancelled
```

---

## WRK-022

Cancellation MUST leave application state consistent.

Partially completed work should be recoverable where practical.

---

# 11. Exception Handling

## WRK-030

Workers MUST catch expected exceptions.

---

## WRK-031

Unexpected exceptions MUST:

* be logged
* emit an error signal
* terminate the Worker safely

---

## WRK-032

Workers MUST NOT silently ignore exceptions.

---

# 12. Logging

> **print 禁令/日志权威**：`.ai/rules/coding-rules.md` COD-050（用 Loguru）+ COD-051（禁 `print()`）。本节不复制正文，详见该处。Workers 层无额外日志规则，遵循 COD-050/051 即可。

Workers MUST use Loguru. `print()` is prohibited per COD-051.

---

# 13. UI Communication

Workers communicate with UI only through Qt Signals.

Correct:

```text
Worker

↓

Signal

↓

Controller

↓

View
```

Wrong:

```python
label.setText(...)
progressBar.setValue(...)
```

inside Worker code.

---

# 14. Resource Management

Workers MUST release:

* file handles
* database connections
* temporary resources
* image buffers

before finishing.

---

# 15. Database Access

Workers MAY access repositories through Application Services.

Workers MUST NOT execute SQL directly.

---

# 16. File System Operations

Workers MAY:

* scan folders
* read files
* create folders
* move files

Workers MUST validate paths before use.

Use pathlib.Path for all file operations.

---

# 17-22. 任务注册示例（Task Registration Examples）

> ⚠ §5 已说明 Workers 层是通用执行器框架（`QtWorkerExecutor` + `task`/`application_tasks` + `events`），**不存在名为 `FaceRecognitionWorker`/`ImportWorker`/`ExportWorker`/`FolderScanWorker`/`ThumbnailWorker`/`CacheWorker` 的具体 Worker 类**。本节原描述的 6 个幻影类已在 2026-07-24 SSOT 收敛轮删除，避免与 §5 自相矛盾。

新长耗时操作通过 `application_tasks.py` 注册为任务函数（复刻 ArchivePhotosTask 信号模板），而非新建具名 Worker 子类。实际已注册的任务见 `src/photo_archiver/workers/application_tasks.py` 与 `src/photo_archiver/presentation/controllers/` 各 controller 的接入点。架构审查要求新建具名 Worker 类前先裁决——默认路径是任务注册。

业务决策（如归档分配）始终在 Application Services，Workers 仅执行。

---

# 23. Performance Guidelines

Workers SHOULD:

* avoid unnecessary allocations
* reuse expensive objects
* batch file operations
* minimize repeated database access

---

# 24. Concurrency Rules

Workers MUST operate independently.

Workers MUST NOT share mutable state without synchronization.

Shared resources should be coordinated by the Application layer.

---

# 25. Retry Policy

Recoverable failures MAY be retried.

Examples:

* temporary file lock
* transient I/O error

Infinite retries are prohibited.

Retry count SHOULD be configurable.

---

# 26. Completion Rules

When a Worker finishes successfully it SHOULD:

1. emit finished
2. release resources
3. log completion
4. provide execution summary if appropriate

---

# 27. Review Checklist

> **总表权威**：`.ai/rules/review-rules.md` §22。本节是 §22 在 Worker 层的细化，不重复总表。

Before merging Worker code verify:

* [ ] Runs outside UI thread
* [ ] Uses approved Qt threading model
* [ ] No UI manipulation
* [ ] Uses Signals for communication
* [ ] Supports cancellation
* [ ] Handles exceptions
* [ ] Uses Loguru
* [ ] Releases resources
* [ ] Uses pathlib.Path
* [ ] Business logic remains in Application layer
* [ ] SQL isolated from Worker
* [ ] Progress reporting implemented

---

# 28. Summary

Workers provide safe, responsive, and maintainable background execution for PhotoArchiver.

Every Worker implementation must:

* remain independent of the UI
* communicate through Signals
* cooperate with Application Services
* isolate infrastructure operations
* preserve application responsiveness

Following these rules ensures predictable behavior and a consistent user experience across all background tasks.

---

End of Document
