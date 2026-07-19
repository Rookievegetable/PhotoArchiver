# PhotoArchiver Project Context

> ⚠️ **DEPRECATED — DO NOT READ**
>
> 本文档已废弃，仅保留作历史参考。**新 AI Session 请勿阅读本文。**
>
> **替代文档**：`.ai/AI_ONBOARDING.md` §1（项目定位）+ `.ai/ARCHITECTURE_DECISIONS.md`（架构决策）
>
> 废弃日期：2026-07-18 ｜ 废弃裁决：AI Runtime Context 体系建立（`.ai/rules/CONTEXT_HANDOFF_RULES.md`）
>
> 历史正文保留于下方，仅供追溯。

---

Version: 1.0.0

Status: Stable

Last Updated: 2026-07-01

---

# Purpose

This document provides the complete project context for AI coding assistants.

Unlike the development rules, this document explains **what the project is**, **why it exists**, **what problems it solves**, and **how every module contributes to the overall system**.

Every AI assistant should read this document after `START_HERE.md`.

---

# Project Identity

**Project Name**

PhotoArchiver

**Project Type**

Desktop Application

**Primary Language**

Python 3.11

**GUI Framework**

PySide6

**Architecture**

* Domain-Driven Design (DDD)
* Clean Architecture
* Layered Architecture

---

# Project Vision

PhotoArchiver is designed to become a professional photo archive management system.

The project focuses on:

* High maintainability
* Long-term evolution
* Modular architecture
* AI-assisted development
* Enterprise-quality code

The system should remain easy to extend even after years of development.

---

# Target Users

Primary users include:

* Schools
* Government organizations
* Enterprises
* Museums
* Libraries
* Archives
* Photography studios
* Individuals managing large historical photo collections

Users are not expected to have programming knowledge.

The application should provide an intuitive desktop experience.

---

# Core Business Problem

Organizations often possess thousands or tens of thousands of photographs stored in unorganized folders.

Typical problems include:

* Inconsistent folder structures
* Duplicate images
* Missing metadata
* Difficult searching
* Manual classification
* Time-consuming archive management

PhotoArchiver aims to automate these repetitive tasks.

---

# Project Goals

The application should eventually support:

* Importing personnel information
* Importing photo directories
* Automatic folder scanning
* Metadata extraction
* Face recognition
* Person matching
* Archive organization
* Duplicate detection
* Thumbnail generation
* Search and filtering
* Batch operations
* Export reports
* Configuration management
* Plugin extensions

---

# Business Workflow

The standard workflow is:

```text
Import Personnel Information
            │
            ▼
Select Photo Directory
            │
            ▼
Scan Directory Structure
            │
            ▼
Extract Image Metadata
            │
            ▼
Generate Thumbnails
            │
            ▼
Detect Faces
            │
            ▼
Recognize Persons
            │
            ▼
Match Recognition Results
            │
            ▼
User Review
            │
            ▼
Archive Organization
            │
            ▼
Export Results
```

Each step should be independently testable.

---

# Current Development Stage

Current project status:

* Project initialized
* Repository established
* Directory structure completed
* Development standards established
* AI knowledge base established

Most business modules are currently placeholders.

The next phase focuses on implementing functional modules while preserving the agreed architecture.

---

# Architecture Overview

The project follows a layered architecture.

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

Background tasks execute through the Worker layer.

---

# Source Structure

Application source code is located in:

```text
src/photo_archiver/
```

Primary modules:

```text
app/
presentation/
application/
domain/
infrastructure/
workers/
common/
plugins/
ai/
```

Each module has a clearly defined responsibility.

Cross-layer shortcuts are prohibited.

---

# Module Responsibilities

## app/

Application startup.

Responsible for:

* Application initialization
* Dependency configuration
* Window startup

---

## presentation/

Responsible for:

* Windows
* Dialogs
* Widgets
* Controllers
* User interaction

No business logic should appear here.

---

## application/

Coordinates business use cases.

Responsibilities:

* Application Services
* Workflow orchestration
* Transaction boundaries
* Use case execution

---

## domain/

Contains pure business logic.

Responsibilities:

* Entities
* Value Objects
* Domain Services
* Repository Interfaces
* Business Rules

This layer should remain independent of external libraries.

---

## infrastructure/

Implements technical details.

Examples:

* SQLite
* File system
* OpenCV
* InsightFace
* Configuration loading
* Repository implementations

---

## workers/

Executes long-running background tasks.

Examples:

* Folder scanning
* Face recognition
* Thumbnail generation
* Batch processing

Workers communicate with the UI through Qt Signals.

---

## plugins/

Reserved for future extension mechanisms.

The core application should not depend on plugins.

---

## common/

Shared utilities.

Examples:

* Constants
* Exceptions
* Logging
* Helper functions

Business logic should not accumulate here.

---

## ai/

Reserved for AI-related capabilities inside the application, such as prompt templates, model adapters, or future intelligent features.

It is distinct from the project-level `.ai/` knowledge base.

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

Additional dependencies require explicit approval.

---

# Design Principles

The project values:

* Single Responsibility
* Separation of Concerns
* Dependency Inversion
* Explicit Interfaces
* Loose Coupling
* High Cohesion

Code should remain understandable before it becomes clever.

---

# Development Philosophy

Every implementation should:

* Respect architecture
* Remain testable
* Be easy to refactor
* Avoid hidden dependencies
* Minimize technical debt

Temporary solutions should not become permanent architecture.

---

# AI Development Expectations

AI assistants should:

* Read documentation before coding.
* Reuse existing modules when appropriate.
* Avoid introducing duplicate implementations.
* Explain architectural impact before major changes.
* Keep modifications limited to the requested scope.

If requirements are unclear, seek clarification rather than making assumptions.

---

# Quality Standards

Code should be:

* Correct
* Readable
* Consistent
* Typed
* Logged
* Tested
* Documented

Quality is measured over the lifetime of the project, not by development speed.

---

# Future Evolution

The architecture is intentionally designed for expansion.

Potential future capabilities include:

* OCR support
* Facial clustering
* Duplicate image analysis
* AI-assisted metadata generation
* Cloud synchronization
* Multi-language interface
* Plugin marketplace
* Distributed processing

These features should integrate without requiring major architectural redesign.

---

# Relationship with the AI Knowledge Base

The `.ai/` directory is the project's knowledge base.

Recommended reading order:

```text
START_HERE.md
        │
        ▼
PROJECT_CONTEXT.md
        │
        ▼
rules/
        │
        ▼
architecture/
        │
        ▼
business/
        │
        ▼
docs/
        │
        ▼
Source Code
```

This order ensures that AI assistants understand the project before making changes.

---

# Success Criteria

A successful implementation is not simply one that works.

It should also:

* Follow the architecture
* Respect dependency rules
* Remain maintainable
* Be easy to test
* Be understandable by future contributors
* Integrate naturally with the rest of the project

---

# Final Reminder

PhotoArchiver is a long-term engineering project.

Every decision should support future maintainability rather than short-term convenience.

When in doubt:

**Prefer clarity over cleverness.**

**Prefer architecture over shortcuts.**

**Prefer consistency over novelty.**

---

End of Document
