# PhotoArchiver AI Task Workflow

Version: 1.0.0

Status: Stable

Last Updated: 2026-07-01

---

# Purpose

This document defines the standard workflow that every AI coding assistant must follow when completing development tasks for the PhotoArchiver project.

It complements:

* START_HERE.md
* PROJECT_CONTEXT.md
* .ai/rules/

This workflow ensures that every implementation follows the same engineering process regardless of the AI model being used.

---

# Core Principle

Never start coding immediately.

Every task must follow the complete workflow defined in this document.

Planning and understanding always come before implementation.

---

# Standard Workflow

Every development task follows the sequence below:

```text
Receive Task
      │
      ▼
Understand Requirements
      │
      ▼
Review Existing Code
      │
      ▼
Architecture Analysis
      │
      ▼
Implementation Plan
      │
      ▼
User Confirmation (if needed)
      │
      ▼
Implementation
      │
      ▼
Self Review
      │
      ▼
Testing Suggestions
      │
      ▼
Documentation Update
      │
      ▼
Task Complete
```

---

# Phase 1 - Understand the Task

Before writing code:

Understand:

* What is being requested?
* Why is it needed?
* Which business problem does it solve?

Do not infer requirements that were not stated.

If requirements are ambiguous:

* Explain the ambiguity.
* Present possible approaches.
* Recommend one option.
* Wait for clarification if the decision affects architecture or public APIs.

---

# Phase 2 - Identify the Scope

Determine:

* Which modules are affected?
* Which files require modification?
* Which files should remain unchanged?

Limit changes to the smallest reasonable scope.

Avoid unrelated refactoring.

---

# Phase 3 - Review Existing Implementation

Before adding new code:

Search for:

* Existing services
* Existing repositories
* Existing workers
* Existing utilities
* Existing models
* Existing interfaces

Prefer extending existing implementations over creating duplicates.

---

# Phase 4 - Architecture Review

Before implementation, verify:

* Which architecture layer owns the responsibility?
* Does the task belong in Presentation, Application, Domain, Infrastructure, or Workers?
* Are any dependency rules affected?

If a proposed implementation violates the architecture, redesign it before coding.

---

# Phase 5 - Implementation Plan

Before coding, prepare a concise plan including:

* Objective
* Files to modify
* New files (if any)
* Affected modules
* Expected interactions
* Potential risks

Do not begin implementation until the approach is clear.

---

# Phase 6 - User Confirmation

Confirmation is required when:

* Introducing a new dependency
* Changing the project structure
* Modifying public APIs
* Altering database schema
* Changing configuration formats
* Introducing breaking changes

Minor internal improvements do not require confirmation unless requested.

---

# Phase 7 - Implementation

During implementation:

Follow all project rules.

Always:

* Use type hints.
* Keep functions focused.
* Respect layer boundaries.
* Reuse existing abstractions.
* Add logging where appropriate.

Never:

* Introduce placeholder logic into production code.
* Mix business logic into UI classes.
* Add unrelated code changes.

---

# Phase 8 - Self Review

After implementation, perform a self-review.

Verify:

* Architecture respected
* Dependency rules respected
* Naming is consistent
* No unused imports
* No debug code
* No commented-out obsolete code
* Exceptions handled appropriately
* Logging included where necessary

---

# Phase 9 - Testing Suggestions

For every implementation, identify appropriate validation steps.

Examples:

* Unit tests
* Integration tests
* Manual UI verification
* Performance checks
* Edge-case scenarios

If automated tests are not created, explain how the feature should be verified manually.

---

# Phase 10 - Documentation Review

Determine whether documentation should be updated.

Potential files include:

* README.md
* docs/
* .ai/
* Configuration examples

Documentation should stay synchronized with implementation.

---

# AI Response Format

When responding to development requests, structure the response in the following order:

1. Task Understanding
2. Architecture Impact
3. Implementation Plan
4. Files to Modify
5. Implementation
6. Validation Suggestions
7. Documentation Impact

This structure improves clarity and traceability.

---

# Handling Existing Code

When modifying existing code:

* Preserve coding style.
* Preserve public behavior unless changes are requested.
* Minimize the size of the change.
* Avoid unnecessary renaming.

If significant refactoring is beneficial, explain it separately instead of combining it with the requested task.

---

# Error Handling Workflow

When an error occurs during development:

1. Identify the root cause.
2. Explain the issue.
3. Propose a fix.
4. Describe potential side effects.
5. Apply the smallest effective change.

Avoid speculative fixes.

---

# Refactoring Workflow

Before refactoring:

Confirm that:

* No behavior changes are introduced.
* Tests remain valid.
* Public interfaces remain stable.

Large refactoring should be divided into multiple logical steps.

---

# Performance Considerations

Before optimizing:

Confirm that:

* A measurable performance issue exists.
* The optimization does not reduce readability.
* The architecture remains intact.

Avoid premature optimization.

---

# Security Considerations

For features involving:

* File access
* User input
* Database operations
* External resources

Review:

* Input validation
* Error handling
* Resource cleanup
* Access restrictions

Security takes priority over convenience.

---

# Completion Checklist

A task is complete only if all of the following are satisfied:

* [ ] Requirements addressed
* [ ] Architecture respected
* [ ] Dependency rules followed
* [ ] Coding standards followed
* [ ] No unrelated changes
* [ ] Logging reviewed
* [ ] Validation steps identified
* [ ] Documentation reviewed

---

# Escalation Rules

Pause implementation and request guidance if:

* Requirements conflict with project rules.
* The architecture needs to change.
* Multiple valid approaches exist with significant trade-offs.
* A breaking change is unavoidable.

Do not make strategic architectural decisions without explicit approval.

---

# Workflow Summary

Every development task follows this sequence:

```text
Understand
    │
    ▼
Analyze
    │
    ▼
Plan
    │
    ▼
Implement
    │
    ▼
Review
    │
    ▼
Validate
    │
    ▼
Document
```

Skipping any step increases the risk of defects and architectural inconsistency.

---

# Final Principle

Every contribution should leave the project in a better state than before.

When uncertain:

* Read the documentation again.
* Reuse existing patterns.
* Prefer consistency over novelty.
* Keep the solution simple.
* Respect the project's long-term maintainability.

The goal is not only to deliver working code, but to strengthen the overall quality of PhotoArchiver.

---

End of Document
