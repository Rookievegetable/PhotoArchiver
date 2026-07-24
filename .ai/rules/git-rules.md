# PhotoArchiver Git Rules

Version: 1.0.1

Status: Stable

Last Updated: 2026-07-24

---

# 1. Purpose

This document defines the Git workflow, commit conventions, branch strategy, and version management rules for the PhotoArchiver project.

All contributors, including AI coding assistants, MUST comply with these rules.

---

# 2. Repository

Official Repository

```text
https://github.com/Rookievegetable/PhotoArchiver
```

The Git repository is the only source of truth for project code.

Generated code MUST eventually be committed to Git.

---

# 3. Branch Strategy

The project uses a simplified Git workflow.

Permanent branch:

```text
main
```

Optional short-lived branches:

```text
feature/<feature-name>

fix/<issue-name>

refactor/<module-name>

docs/<topic>

test/<module>

release/<version>
```

Feature branches SHOULD be merged and deleted after completion.

---

# 4. Main Branch Rules

## GIT-001

The `main` branch MUST always remain buildable.

---

## GIT-002

Broken code MUST NOT be committed to `main`.

---

## GIT-003

Every commit to `main` SHOULD pass:

* Ruff
* MyPy
* pytest

---

# 5. Branch Naming

Use lowercase letters.

Words are separated by hyphens.

Correct:

```text
feature/import-excel

feature/face-recognition

fix/sqlite-lock

docs/architecture

refactor/archive-service
```

Wrong:

```text
NewFeature

TEST

myBranch

update1
```

---

# 6. Commit Message Format

Use Conventional Commits.

Format:

```text
<type>: <summary>
```

Examples:

```text
feat: add excel import service

fix: resolve sqlite transaction issue

docs: update architecture handbook

refactor: simplify folder scanner

test: add repository unit tests

style: apply ruff formatting

chore: update dependencies
```

---

# 7. Approved Commit Types

| Type     | Purpose                 |
| -------- | ----------------------- |
| feat     | New feature             |
| fix      | Bug fix                 |
| refactor | Internal improvement    |
| docs     | Documentation           |
| test     | Tests                   |
| style    | Formatting only         |
| perf     | Performance improvement |
| build    | Build configuration     |
| ci       | CI configuration        |
| chore    | Maintenance             |

Only approved commit types should be used.

---

# 8. Commit Size

## GIT-010

Each commit SHOULD represent one logical change.

Avoid mixing:

* new features
* bug fixes
* formatting
* refactoring

in a single commit.

---

# 9. Commit Quality

Every commit SHOULD:

* compile successfully
* pass tests
* include documentation updates (when needed)

Do not commit incomplete implementations.

---

# 10. Generated Files

Do NOT commit:

```text
__pycache__/

.pytest_cache/

.mypy_cache/

.ruff_cache/

.venv/

*.pyc

*.pyo

*.log
```

These files belong in `.gitignore`.

---

# 11. Dependency Updates

Dependency changes SHOULD be isolated.

Example:

```text
chore: upgrade PySide6 to 6.11.1
```

Do not mix dependency upgrades with feature development.

---

# 12. Documentation Updates

When architecture changes:

Update:

* docs/
* .ai/
* README.md (if necessary)

Documentation SHOULD remain synchronized with implementation.

---

# 13. Version Tags

Stable releases SHOULD use semantic versioning.

Examples:

```text
v1.0.0

v1.1.0

v1.2.3

v2.0.0
```

Tag names MUST begin with "v".

---

# 14. Release Checklist

Before creating a release:

* All tests pass
* Documentation updated
* Version updated
* No known critical defects
* Dependencies verified

---

# 15. Merge Rules

Before merging:

* Resolve conflicts
* Run tests
* Review architecture
* Verify coding rules
* Update documentation if necessary

Merge commits SHOULD represent completed work.

---

# 16. AI Commit Rules

AI-generated commits SHOULD:

* modify only relevant files
* avoid unrelated formatting
* preserve project structure
* follow architecture rules

AI MUST NOT rename or move files unless explicitly requested.

---

# 17. File Rename Policy

Renaming public modules requires approval.

Renaming should preserve:

* import paths
* public APIs
* documentation references

---

# 18. Large Refactoring

Large refactoring SHOULD be split into multiple commits.

Recommended sequence:

```text
Commit 1

Refactor structure

↓

Commit 2

Update imports

↓

Commit 3

Update tests

↓

Commit 4

Update documentation
```

---

# 19. Pull Request Checklist

> **总表权威**：`.ai/rules/review-rules.md` §22。本节是 §22 在 Git/PR 层的细化，不重复总表。

Before opening a Pull Request verify:

* [ ] Ruff passes
* [ ] MyPy passes
* [ ] pytest passes
* [ ] Architecture respected
* [ ] Documentation updated
* [ ] No debug code
* [ ] No print()
* [ ] Commit messages follow conventions

---

# 20. Repository Hygiene

The repository SHOULD remain clean.

Avoid committing:

* temporary scripts
* experimental code
* generated cache
* local configuration
* IDE-specific files

---

# 21. Recovery Rules

If a mistaken commit is made:

* Prefer `git revert` for published commits.
* Use `git reset` only for local, unpublished history.

Avoid force-pushing to shared branches unless absolutely necessary and approved.

---

# 22. Git Ignore Policy

The project `.gitignore` is the authoritative list of ignored files.

Do not manually delete tracked files that should instead be ignored through configuration.

---

# 23. Review Integration

Every code review SHOULD reference applicable rule IDs when possible.

Examples:

```text
COD-051
print() detected

DEP-021
Domain imports OpenCV

ARC-004
Repository placed in wrong layer
```

This keeps reviews objective and traceable.

---

# 24. Development Workflow

Recommended workflow:

```text
Pull latest main

↓

Create feature branch (optional)

↓

Implement feature

↓

Run Ruff

↓

Run MyPy

↓

Run pytest

↓

Update documentation

↓

Commit

↓

Push

↓

Open Pull Request (if using feature branch)

↓

Merge into main
```

For solo development, commits may be made directly to `main` after completing the same validation steps.

---

# 25. Summary

Git is the project's historical record.

Every commit should be:

* Small
* Clear
* Reproducible
* Reviewable
* Buildable

Following these rules ensures that the repository remains reliable throughout the lifecycle of the PhotoArchiver project.

---

End of Document
