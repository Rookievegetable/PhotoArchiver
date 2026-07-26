# PhotoArchiver AI Rules

Version: 1.1.0

Status: Stable

Last Updated: 2026-07-24

---

# 1. Purpose

The `rules` directory defines the mandatory engineering standards for the PhotoArchiver project.

These rules ensure that every AI coding assistant generates consistent, maintainable, and production-ready code.

Every rule in this directory is considered authoritative.

---

# 2. Scope

These rules apply to:

- New feature development
- Bug fixes
- Refactoring
- Code review
- Documentation generation
- Unit testing
- Integration testing

The rules apply equally to:

- Human developers
- AI coding assistants

---

# 3. Rule Priority

When multiple documents exist, AI MUST follow them in the following order.

Priority 1

Current user instructions

↓

Priority 2

.rules/

↓

Priority 3

.business/

↓

Priority 4

.architecture/

↓

Priority 5

.prompts/

↓

Priority 6

.templates/

注：`.ai/architecture/`、`.ai/prompts/`、`.ai/templates/` 目录已于 2026-07-24 裁决1物理删除，列表保留作预留占位层级框架。同级无实际文档时默认按约束最严格执行。

If conflicts occur, the higher priority document always wins.

---

# 4. Rule Categories

The rules are divided into eight categories.

## AI Rules

File

ai-rules.md

Defines the behavior of AI assistants.

> **模块职责 SSOT**：`.ai/rules/architecture-rules.md` §4（ARC-001~009）。本文件各 Category 仅声明规则文件主题归属，不重复模块职责正文。

---

## Coding Rules

File

coding-rules.md

Defines Python coding standards.

---

## Architecture Rules

File

architecture-rules.md

Defines Clean Architecture and DDD constraints.

---

## Dependency Rules

File

dependency-rules.md

Defines allowed module dependencies.

---

## UI Rules

File

ui-rules.md

Defines PySide6 UI standards.

---

## Worker Rules

File

worker-rules.md

Defines background task and threading standards.

---

## Git Rules

File

git-rules.md

Defines version control conventions.

---

## Review Rules

File

review-rules.md

Defines code review checklists and quality gates.

---

# 5. Rule Levels

Every rule belongs to one of four levels.

## MUST

Mandatory.

Violation is not allowed.

Example:

MUST use pathlib.Path.

---

## MUST NOT

Strictly prohibited.

Example:

MUST NOT use print().

---

## SHOULD

Strong recommendation.

May be overridden with justification.

---

## MAY

Optional.

Use only when appropriate.

---

# 6. Rule Numbering

> **现状承认（2026-07-24 SSOT 收敛）**：本目录 8 个规则文件中，**仅 `coding-rules.md`（COD）/`dependency-rules.md`（DEP）/`worker-rules.md`（WRK）/`architecture-rules.md` §4（ARC-001~009）实际使用编号 ID**。`ai-rules.md` /`ui-rules.md`/`git-rules.md`/`review-rules.md` 章节式但不带稳定 ID，编号体系降级为"按需引用"——引用统一用"文件+章节"格式（如 `ai-rules.md §9`），不强行补 AI-/UI-/GIT-/REV- ID（成本高收益低）。

Every stable rule that already has an identifier keeps it permanently.

Examples

COD-001

ARC-001

DEP-001

WRK-001

Rule identifiers are permanent.

Existing identifiers MUST NOT be reused.

> ⚠ 禁止"章节号冒充规则 ID"：`architecture-rules.md` 的章节号（§14 Database / §17 Configuration / §18 Logging 等）**不是 ARC-ID**。引用这些章节时统一写"文件 §章节"（如 `architecture-rules.md §14`），不得写"ARC-014/ARC-017/ARC-018"——后者会误导读者以为是稳定规则 ID。

---

# 6.1 Pointer Integrity（指针必须可解析）

> 元规则（2026-07-24 v2 第 0 期补入）：收敛轮出现"假指针"——引用不存在的锚点（如 `COD-072/073` 全 git 历史从未存在、"ADR R 段已裁决"R 表无此条目）。假指针比重复全文更危险，它制造"已收敛"的幻觉。

**MUST**：任何"权威：文件 §N"或"文件 §N"形式的指针引用，目标文件 + 章节/规则 ID 必须真实存在；新增或修改指针时**当场验证**目标可解析（读目标文件确认锚点存在）。

**MUST NOT**：不得凭记忆写指针——记错章节号或规则 ID 会引入假指针。

**SHOULD**：复审时抽查指针可解析性（按 `audit-methodology.md` 五维比对之一）。

违反信号：grep 检索某指针锚点在目标文件 0 命中。发现假指针立即当轮修——要么改指向真实存在的锚点，要么补录目标条目使指针成立。

---

# 7. Rule Format

Every rule MUST follow this structure.

Rule ID

Title

Requirement

Reason

Example

For example:

Rule ID

COD-001

Title

Use pathlib

Requirement

MUST use pathlib.Path instead of os.path.

Reason

Cross-platform compatibility.

Example

Wrong

os.path.join()

Correct

Path()

---

# 8. Rule Modification

Rules are considered stable.

Modification requires:

1. Clear technical justification

2. Backward compatibility analysis

3. Documentation update

4. Version update

Rules MUST NOT be modified casually.

---

# 9. Conflict Resolution

If two rules conflict:

Step 1

Follow the higher priority document.

Step 2

If priorities are equal,

choose the more restrictive rule.

Step 3

If ambiguity remains,

request clarification before implementation.

---

# 10. AI Compliance

Before generating code,

AI MUST verify:

- Relevant rules have been read.
- Architecture constraints are understood.
- Dependencies are valid.
- Naming conventions are followed.
- Technology stack is unchanged.

If any prerequisite is missing,

AI MUST stop and request clarification.

---

# 11. Technology Constraints

The following technologies are approved.

Python 3.11

PySide6

InsightFace

OpenCV

Pandas

OpenPyXL

SQLite

Loguru

pytest

Ruff

MyPy

pathlib

Introducing additional frameworks requires explicit approval.

---

# 12. Quality Objectives

All generated code should satisfy:

Correctness

Readability

Maintainability

Testability

Performance

Cross-platform compatibility

Low coupling

High cohesion

---

# 13. Rule Lifecycle

Draft

↓

Review

↓

Approved

↓

Stable

↓

Deprecated (if necessary)

Only Stable rules are mandatory.

---

# 14. Code Review

Every pull request SHOULD be reviewed against:

Coding Rules

Architecture Rules

Dependency Rules

Worker Rules

UI Rules

Review Rules

Review findings should reference rule IDs whenever possible.

Example

Violation:

COD-012

Violation:

DEP-004

Violation:

WRK-009

---

# 15. Relationship to Project Documents

Rules define **how** the project is implemented.

Architecture defines **where** code belongs.

Business defines **what** the application should do.

Prompts define **how AI should be instructed**.

Templates define **how common components are structured**.

Context records the current project state.

These responsibilities MUST remain separate.

---

# 16. Summary

The rules in this directory are the engineering standard for the PhotoArchiver project.

Every developer and every AI assistant MUST comply with these rules before contributing code.

End of Document