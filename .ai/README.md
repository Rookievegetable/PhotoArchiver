# PhotoArchiver AI Knowledge Base

> ⚠️ **DEPRECATED — DO NOT READ**
>
> 本文档已废弃，仅保留作历史参考。**新 AI Session 请勿阅读本文。**
>
> **替代文档**：`.ai/AI_ONBOARDING.md`（入口）+ `.ai/DOCUMENT_INDEX.md`（文档体系导航）+ `.ai/rules/README.md`（规则元规则）
>
> 废弃日期：2026-07-18 ｜ 废弃裁决：AI Runtime Context 体系建立（`.ai/rules/CONTEXT_HANDOFF_RULES.md`）
>
> 历史正文保留于下方，仅供追溯。

---

Version: 1.0.0

Status: Stable

Last Updated: 2026-07-01

---

# 1. Overview

This directory is the single source of truth (SSOT) for all AI-assisted development in the PhotoArchiver project.

All AI coding assistants (Codex, ChatGPT, Claude, Gemini, Trae, Cursor, etc.) MUST read this knowledge base before generating or modifying project code.

This directory defines:

- Project architecture
- Coding standards
- Business workflow
- Module responsibilities
- Prompt templates
- Review standards

The purpose is to ensure that all generated code follows the same engineering standards.

---

# 2. Project Information

Project Name

PhotoArchiver

Project Type

Cross-platform Desktop Application

Target Platforms

- Windows
- macOS

Language

Python 3.11

GUI Framework

PySide6

Architecture

Domain Driven Design (DDD)

Clean Architecture

AI Engine

InsightFace

Image Processing

OpenCV

Data Processing

Pandas

Excel

OpenPyXL

Database

SQLite

Logging

Loguru

Testing

pytest

Formatting

Ruff

Type Checking

MyPy

---

# 3. Directory Structure

.ai/

AI development knowledge base.

Contains all rules and project documentation.

docs/

Project documentation.

src/

Project source code.

tests/

Unit and integration tests.

resources/

Application resources.

config/

Configuration files.

scripts/

Development scripts.

---

# 4. Knowledge Base Structure

README.md

AI knowledge base entry.

rules/

Project rules.

Architecture constraints.

Coding standards.

Review rules.

architecture/

Project architecture.

Module relationships.

Dependency rules.

business/

Business workflow.

Business terminology.

Business requirements.

prompts/

Prompt templates.

templates/

Reusable templates.

context/

Current project status.

---

# 5. Reading Order

Every AI assistant MUST read the documents in the following order.

Step 1

README.md

↓

Step 2

rules/

↓

Step 3

architecture/

↓

Step 4

business/

↓

Step 5

context/

Only after completing the above steps may code generation begin.

---

# 6. Scope

This knowledge base only applies to the PhotoArchiver project.

It MUST NOT be used as a generic Python development guide.

All examples, rules, and architectural decisions are specific to this project.

---

# 7. Technology Stack

Programming Language

Python 3.11

GUI

PySide6

AI

InsightFace

Image Processing

OpenCV

Data Processing

Pandas

OpenPyXL

Storage

SQLite

Configuration

YAML

Logging

Loguru

Testing

pytest

Lint

Ruff

Type Checking

MyPy

Package Manager

pip

Version Control

Git

Hosting

GitHub

---

# 8. AI Development Principles

Every AI assistant MUST follow these principles.

## Project First

Always prioritize the requirements of PhotoArchiver.

Do not introduce unnecessary frameworks.

Do not redesign existing architecture.

---

## AI First

Rules must be explicit.

Avoid ambiguous language.

Use deterministic implementations.

---

## Stable First

Do not change project architecture without explicit approval.

Avoid introducing breaking changes.

---

## Single Source of Truth

Every rule has only one authoritative location.

Do not duplicate project rules across documents.

---

# 9. Development Workflow

Requirement

↓

Architecture

↓

Implementation

↓

Review

↓

Testing

↓

Documentation

↓

Git Commit

↓

Release

Every step is mandatory.

---

# 10. AI Responsibilities

AI assistants are responsible for:

✔ generating code

✔ reviewing code

✔ refactoring code

✔ explaining code

✔ generating tests

✔ generating documentation

AI assistants are NOT responsible for:

✘ changing architecture

✘ introducing new frameworks

✘ modifying project scope

✘ changing technology stack

without explicit approval.

---

# 11. Project Status

Current Phase

Phase 1

Project Initialization

Current Progress

Completed

- Project structure

- Git repository

- Python environment

- Dependency planning

- Handbook planning

Next Step

Complete AI Rules.

---

# 12. Versioning

Version Format

Major.Minor.Patch

Example

1.0.0

Major

Architecture changes.

Minor

Rule additions.

Patch

Documentation updates.

---

# 13. Maintainer

Project

PhotoArchiver

Architecture

Maintained by the project architect.

All AI-generated content must comply with this handbook.

End of Document