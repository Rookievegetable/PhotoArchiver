# 🚀 START HERE - PhotoArchiver AI Development Guide

> **This is the first document every AI coding assistant must read before modifying the project.**

---

# Project Overview

**Project Name**

PhotoArchiver

**Project Type**

Enterprise Desktop Application

**Primary Language**

Python 3.11

**GUI Framework**

PySide6

**Architecture**

* Domain-Driven Design (DDD)
* Clean Architecture
* Layered Architecture

The goal of this project is to build a long-term maintainable, enterprise-grade desktop application.

Code quality, architecture consistency, and maintainability are always more important than development speed.

---

# AI Mission

Your role is **Software Engineer**, not merely a code generator.

Before writing any code, you must fully understand:

* the project architecture
* the coding conventions
* the dependency rules
* the business objectives

Never guess the project structure.

Never invent APIs or modules that do not exist.

---

# Mandatory Reading Order

Before making **any** code changes, read the following documents in order.

## Step 1

Read:

```text
.ai/rules/
```

Required files:

```text
ai-rules.md
coding-rules.md
architecture-rules.md
dependency-rules.md
worker-rules.md
ui-rules.md
git-rules.md
review-rules.md
```

Understand and follow every rule.

---

## Step 2

Read:

```text
README.md
```

Understand:

* Project purpose
* Technology stack
* Directory structure
* Development environment
* Startup instructions

---

## Step 3

Read:

```text
docs/
```

Focus on:

* architecture/
* development/
* roadmap/
* user-guide/

Understand the current development stage before writing code.

---

## Step 4

Read:

```text
src/photo_archiver/
```

Identify:

* Existing modules
* Existing interfaces
* Existing services
* Existing repositories
* Existing Workers

Do not duplicate existing implementations.

---

## Step 5

Summarize your understanding before coding.

Your summary should include:

1. Project objective
2. Architecture
3. Current implementation status
4. Development plan
5. Files likely to be modified

Only after completing this step should development begin.

---

# Development Principles

Always prioritize:

1. Correct architecture
2. Maintainability
3. Readability
4. Testability
5. Performance

Never sacrifice architecture for short-term convenience.

---

# Architecture Rules

Always respect the project layers.

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

Workers execute background tasks.

Presentation never contains business logic.

Domain never depends on frameworks.

Infrastructure implements interfaces.

---

# Project Structure

Source code lives in:

```text
src/photo_archiver/
```

Main modules:

```text
app/
presentation/
application/
domain/
infrastructure/
workers/
ai/
plugins/
common/
```

Do not introduce new top-level packages unless explicitly instructed.

---

# Technology Stack

Approved technologies:

* Python 3.11
* PySide6
* SQLite
* OpenCV
* InsightFace
* pandas
* openpyxl
* Loguru
* Ruff
* MyPy
* pytest

Do not introduce new dependencies without approval.

---

# Coding Rules

Always:

* Use type hints.
* Follow Ruff formatting.
* Write readable code.
* Prefer composition over inheritance.
* Use pathlib.Path for file operations.
* Use Loguru for logging.
* Keep functions focused on a single responsibility.

Never:

* Use `print()` for logging.
* Use wildcard imports.
* Write business logic inside UI classes.
* Access SQLite directly from Presentation.
* Ignore exceptions silently.

---

# Worker Rules

Long-running operations must execute in Workers.

Examples:

* Folder scanning
* Face recognition
* Excel import
* Thumbnail generation
* Export

Workers communicate through Qt Signals.

Workers must never update UI widgets directly.

---

# UI Rules

PySide6 is the only approved GUI framework.

The UI should:

* remain responsive
* display progress
* display user-friendly errors

The UI must not:

* execute SQL
* perform face recognition
* manipulate repositories directly

---

# Git Rules

Commit messages follow Conventional Commits.

Examples:

```text
feat: add import service

fix: resolve sqlite transaction issue

docs: update architecture handbook
```

Each commit should represent a single logical change.

---

# Review Checklist

Before considering a task complete, verify:

* Architecture respected
* Dependency rules followed
* No forbidden imports
* Type hints included
* Ruff compatible
* MyPy compatible
* Tests updated (when appropriate)
* Documentation updated (when required)

---

# When You Receive a Task

For every development request, follow this workflow:

```text
Understand the task
        │
        ▼
Identify affected modules
        │
        ▼
Check architecture impact
        │
        ▼
Plan implementation
        │
        ▼
Implement
        │
        ▼
Self-review
        │
        ▼
Suggest tests
```

Do not skip planning.

---

# If Requirements Are Unclear

Do not make assumptions.

Instead:

1. Explain the ambiguity.
2. Present reasonable implementation options.
3. Recommend one option with justification.
4. Wait for confirmation if the decision affects architecture or public APIs.

---

# AI Output Requirements

When generating code:

* Explain which files will be modified.
* Explain why those files are chosen.
* Keep changes limited to the requested scope.
* Preserve project structure.
* Avoid unrelated refactoring.

---

# Project Philosophy

PhotoArchiver is designed to be a long-term maintainable enterprise application.

Every change should improve one or more of the following:

* Maintainability
* Consistency
* Reliability
* Readability
* Scalability

Do not optimize for short-term speed at the expense of long-term quality.

---

# Final Instruction

Before writing your first line of code, ask yourself:

* Do I understand the architecture?
* Am I modifying the correct layer?
* Am I following the project rules?
* Will this change remain maintainable in two years?

If any answer is **No**, stop and review the documentation again.

**Read first. Think second. Code third.**
