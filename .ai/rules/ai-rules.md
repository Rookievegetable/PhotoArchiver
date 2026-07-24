# PhotoArchiver AI Rules

Version: 1.1.0

Status: Stable

Last Updated: 2026-07-19

---

# 1. Purpose

This document defines the mandatory behavior for all AI coding assistants participating in the PhotoArchiver project.

These rules apply to:

- Codex
- ChatGPT
- Claude
- Gemini
- Cursor
- Trae
- Any future AI coding assistant

All generated code MUST comply with these rules.

---

# 2. AI Responsibilities

AI is responsible for:

- Implementing approved features
- Fixing defects
- Refactoring existing code
- Writing unit tests
- Generating documentation
- Reviewing code
- Explaining implementation details

AI is NOT responsible for:

- Changing project goals
- Changing architecture
- Replacing approved frameworks
- Introducing new dependencies without approval

---

# 3. Technology Baseline

> **技术栈清单权威**：`.ai/rules/dependency-rules.md` §13（第三方库清单 + 层归属 + 延后批注）。本节不复制清单正文，详见该处。`requirements/base.txt` 与 `requirements/dev.txt` 是依赖版本 SSOT。

AI MUST NOT replace any approved technology unless explicitly instructed. AI MUST NOT introduce technologies outside the §13 list without project approval.

---

# 4. Project Understanding

Before generating code, AI MUST understand the project workflow.

> **业务工作流权威定义**：`.ai/business/roadmap.md` §2（15 步路线图）。本节不复制工作流正文，详见该处。其余承载处（`architecture-rules.md` §21、`ui-rules.md` §27）均为指针，不重复落正文。

All generated code must support the workflow defined there.

---

# 5. Architecture Protection

AI MUST preserve the existing architecture.

> **分层依赖图+矩阵权威**：`.ai/rules/dependency-rules.md` §2（依赖原则与方向图）+ §4（模块依赖矩阵）。本节不复制图与矩阵正文，详见该处。当 ARC §5 与 DEP §4 矩阵表述不同时，以 DEP §4 矩阵为准（ADR R 段已裁决）。

Cross-layer shortcuts are prohibited. Presentation MUST NOT directly access SQLite, OpenCV, or face recognition APIs.

---

# 6. File Modification Rules

AI MUST:

- Minimize changes.
- Modify only the files required.
- Preserve public APIs whenever possible.
- Preserve backward compatibility.

AI MUST NOT:

- Reformat unrelated files.
- Rename files without approval.
- Move directories without approval.
- Delete existing functionality.

---

# 7. New Module Rules

Before creating a new module, AI MUST verify:

- No existing implementation already exists.
- The module belongs to the correct layer.
- The naming follows project conventions.
- Dependencies are valid.

Duplicate functionality is prohibited.

---

# 8. Code Generation Rules

Generated code MUST:

- Be readable.
- Be maintainable.
- Include type hints.
- Include docstrings for public APIs.
- Follow Ruff recommendations.
- Pass MyPy checks.

Generated code MUST NOT contain:

- print()
- TODO placeholders
- pass statements in production code
- commented-out legacy code

---

# 9. Logging Rules

All runtime information MUST use Loguru.

Example:

Correct:

logger.info(...)

logger.warning(...)

logger.error(...)

Forbidden:

print(...)

---

# 10. Error Handling

AI MUST:

- Catch expected exceptions.
- Log unexpected exceptions.
- Raise meaningful exceptions.

AI MUST NOT:

- Use bare except.
- Swallow exceptions silently.
- Ignore return values.

---

# 11. Threading Rules

Long-running tasks MUST execute in Worker threads.

Examples:

Photo scanning

Face recognition

Large Excel import

Folder creation

Batch archive

UI MUST remain responsive.

---

# 12. UI Rules

Presentation layer is responsible only for:

Displaying information

Receiving user input

Sending commands

UI MUST NOT:

Contain business logic

Operate SQLite

Execute OpenCV

Call InsightFace directly

---

# 13. Domain Rules

Domain models MUST remain independent.

Domain layer MUST NOT import:

PySide6

OpenCV

SQLite

Pandas

InsightFace

Domain contains business rules only.

---

# 14. Infrastructure Rules

Infrastructure provides implementations for:

Repositories

File system access

SQLite

Image loading

Configuration

Logging

Infrastructure MUST NOT contain business decisions.

---

# 15. Naming Rules

Classes

PascalCase

Functions

snake_case

Variables

snake_case

Constants

UPPER_CASE

Private members

_prefix

Abbreviations should be avoided whenever possible.

---

# 16. Documentation Rules

Every public class MUST include:

Purpose

Parameters

Return value

Exceptions

Every public function SHOULD include examples when appropriate.

---

# 17. Testing Rules

New business logic MUST include tests.

Test categories:

Unit Test

Integration Test

Regression Test (when applicable)

Tests MUST NOT depend on GUI.

---

# 18. Performance Rules

Avoid repeated image loading.

Avoid repeated database connections.

Avoid unnecessary file scanning.

Reuse expensive resources whenever possible.

---

# 19. Cross-Platform Rules

The project targets:

Windows

macOS

AI MUST:

Use pathlib.Path.

Avoid Windows-only APIs.

Avoid hard-coded separators.

Avoid platform-specific assumptions.

---

# 20. Security Rules

Never execute arbitrary user input.

Validate imported files.

Validate image paths.

Avoid unsafe file deletion.

Never overwrite user files without confirmation.

---

# 21. Review Checklist

> **Review Checklist 总表权威**：`.ai/rules/review-rules.md` §22（11 项全覆盖清单）。本节不复制清单正文，详见该处。各专项规则文件末尾的 layer-specific checklist（coding/architecture/dependency/ui/worker/git）是 §22 在该层的细化，不重复 §22 总表。

Before completing a task, AI MUST run the §22 master checklist plus any layer-specific checklist applicable to the change.

---

# 22. Output Rules

Unless explicitly requested,

AI SHOULD provide:

Implementation summary

Files modified

Potential risks

Recommended next step

Large architectural explanations should be avoided during implementation.

---

# 23. Completion Criteria

A task is considered complete only when:

Feature implemented

Tests pass

Architecture respected

Rules satisfied

Documentation updated

No known blocking issues remain

---

# End of Document