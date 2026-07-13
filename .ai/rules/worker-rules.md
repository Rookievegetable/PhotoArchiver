# PhotoArchiver Worker Rules

Version: 1.0.1

Status: Stable

Last Updated: 2026-07-13

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

# 5. Approved Worker Types

The following Worker types are approved:

* FolderScanWorker
* ImageScanWorker
* FaceRecognitionWorker
* ImportWorker
* ExportWorker
* ArchiveWorker
* ThumbnailWorker
* CacheWorker
* DatabaseSyncWorker

New Worker types require architectural review.

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

Workers MUST use Loguru.

Example:

```python
logger.info("Scanning {}", directory)
```

Forbidden:

```python
print(...)
```

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

# 17. Face Recognition Workers

FaceRecognitionWorker is responsible for:

* image loading
* face detection
* feature extraction
* similarity calculation

Business decisions (e.g. archive assignment) remain in Application Services.

---

# 18. Import Workers

ImportWorker is responsible for:

* reading Excel/TXT
* validating data
* creating import commands

It MUST NOT update UI directly.

---

# 19. Export Workers

ExportWorker is responsible for:

* generating reports
* exporting Excel
* exporting CSV
* exporting archive metadata

---

# 20. FolderScanWorker

FolderScanWorker SHOULD:

* recursively scan directories
* validate image formats
* ignore unsupported files
* report progress periodically

---

# 21. ThumbnailWorker

ThumbnailWorker SHOULD:

* generate thumbnails
* cache results
* avoid regenerating existing thumbnails
* release image resources promptly

---

# 22. CacheWorker

CacheWorker MAY:

* clean expired cache
* preload metadata
* optimize cache structure

Cache operations MUST NOT interfere with active user tasks.

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
