# PhotoArchiver AI Rules

Version: 1.2.0

Status: Stable

Last Updated: 2026-07-24

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

Generated code MUST NOT contain `print()` / TODO placeholders / `pass` in production / commented-out legacy code——详见 `coding-rules.md` COD-051/072/073 与 `architecture-rules.md` 禁占位条款。

---

# 9. Logging Rules

> **print 禁令/日志权威**：`.ai/rules/coding-rules.md` COD-050（用 Loguru）+ COD-051（禁 `print()`）+ §7 Logging 小节。本节不复制正文，详见该处。ADR-008 已裁决统一 Loguru。

All runtime information MUST use Loguru (`logger.info/warning/error`). `print()` is prohibited in production code per COD-051.

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

> 详见 `coding-rules.md` §8 Exceptions（COD-060~062）。

---

# 11. Threading Rules

> **Worker/线程权威**：`.ai/rules/worker-rules.md` WRK-001~003（UI 线程外执行、Qt 线程原语、QWidget 子类禁长任务）。本节不复制正文。

Long-running tasks MUST execute in Worker threads per WRK-001；UI MUST remain responsive per WRK-003.

---

# 12. UI Rules

> **UI 规则权威**：`.ai/rules/ui-rules.md` UI-001/002（MainWindow 职责与禁令）+ `architecture-rules.md` §4 ARC-001（Presentation 职责）。本节不复制正文。

Presentation 只负责显示/输入/命令；禁含业务逻辑、禁操作 SQLite/OpenCV/InsightFace。

---

# 13. Domain Rules

> **Domain 规则权威**：`.ai/rules/dependency-rules.md` §7 DEP-020~023（Domain 零框架依赖）+ `architecture-rules.md` §4 ARC-003（Domain 职责）。本节不复制正文。

Domain MUST remain framework independent；禁导入 PySide6/OpenCV/SQLite/pandas/InsightFace。Domain contains business rules only.

---

# 14. Infrastructure Rules

> **Infrastructure 规则权威**：`architecture-rules.md` §4 ARC-004 + `dependency-rules.md` §8 DEP-030~033。本节不复制正文。

Infrastructure provides Repository/Filesystem/SQLite/Image/Config/Logging implementations；MUST NOT contain business decisions.

---

# 15. Naming Rules

> **命名/导入规范权威**：`.ai/rules/coding-rules.md` §4 Naming（COD-020~025）+ §3 Imports（COD-010~013）。本节不复制正文，详见该处。

AI MUST follow COD-020~025 for naming and COD-010~013 for import ordering. Abbreviations should be avoided whenever possible.

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