# PhotoArchiver Coding Rules

Version: 1.0.1

Status: Stable

Last Updated: 2026-07-13

---

# 1. Purpose

This document defines the Python coding standards for the PhotoArchiver project.

All source code under `src/photo_archiver/` MUST comply with these rules.

---

# 2. General Principles

## COD-001

**MUST** target Python 3.11.

Do not write compatibility code for older Python versions.

---

## COD-002

**MUST** prioritize readability over clever implementations.

Prefer explicit code to implicit behavior.

---

## COD-003

Every source file MUST use UTF-8 encoding.

---

## COD-004

Every source file MUST end with a newline.

---

## COD-005

Maximum line length is **100 characters**.

Use Ruff formatting defaults (line-length = 100, aligned with `pyproject.toml`).

---

# 3. Imports

## COD-010

Imports MUST be grouped in this order:

1. Standard Library
2. Third-party Libraries
3. Project Modules

Example:

```python
from pathlib import Path

from loguru import logger

from photo_archiver.domain.entities import Person
```

---

## COD-011

Wildcard imports are prohibited.

Wrong

```python
from pathlib import *
```

Correct

```python
from pathlib import Path
```

---

## COD-012

Unused imports MUST be removed.

---

## COD-013

Circular imports are prohibited.

If circular dependencies appear,

refactor the module structure.

---

# 4. Naming

## COD-020

Classes MUST use PascalCase.

Correct

```python
PhotoScanner
```

---

## COD-021

Functions MUST use snake_case.

Correct

```python
scan_directory()
```

---

## COD-022

Variables MUST use snake_case.

---

## COD-023

Constants MUST use UPPER_CASE.

Correct

```python
DEFAULT_TIMEOUT
```

---

## COD-024

Private members MUST start with "_".

---

## COD-025

Boolean variables SHOULD start with:

```text
is_
has_
can_
should_
```

Example

```python
is_valid
has_face
```

---

# 5. Type Hints

## COD-030

Public functions MUST include type hints.

Wrong

```python
def load(path):
```

Correct

```python
def load(path: Path) -> Image:
```

---

## COD-031

Avoid using Any unless necessary.

---

## COD-032

Use built-in generic types.

Correct

```python
list[str]

dict[str, int]
```

Avoid

```python
List[str]

Dict[str, int]
```

unless required for compatibility.

---

# 6. Docstrings

## COD-040

Every public class MUST include a docstring.

---

## COD-041

Every public function MUST include a docstring.

---

## COD-042

Docstrings SHOULD follow Google Style.

Example

```python
def scan() -> None:
    """Scan image files."""
```

---

# 7. Logging

## COD-050

Use Loguru.

Correct

```python
logger.info(...)
```

---

## COD-051

print() is prohibited.

---

## COD-052

Log messages SHOULD describe business actions.

Example

```python
logger.info("Scanning directory {}", directory)
```

---

# 8. Exceptions

## COD-060

Never use bare except.

Wrong

```python
except:
```

Correct

```python
except FileNotFoundError:
```

---

## COD-061

Expected exceptions SHOULD be handled explicitly.

---

## COD-062

Unexpected exceptions SHOULD be logged.

---

# 9. Paths

## COD-070

Always use pathlib.Path.

Wrong

```python
os.path.join(...)
```

Correct

```python
Path(...)
```

---

## COD-071

Never concatenate file paths manually.

Wrong

```python
folder + "/" + filename
```

Correct

```python
folder / filename
```

---

# 10. Constants

## COD-080

Magic numbers are prohibited.

Numeric literals MUST NOT be embedded directly in business logic,
UI setup, algorithms, configuration decisions, or function calls.

Use named constants that describe the meaning of the value.

Wrong

```python
timeout = 30
```

Correct

```python
DEFAULT_TIMEOUT = 30
timeout = DEFAULT_TIMEOUT
```

---

# 11. Data Models

## COD-090

Simple immutable models SHOULD use dataclass.

---

## COD-091

Enumerations MUST use Enum.

---

# 12. Functions

## COD-100

Functions SHOULD perform one responsibility.

---

## COD-101

Avoid functions longer than 50 lines.

Consider refactoring if exceeded.

---

## COD-102

Avoid nesting deeper than three levels.

---

# 13. Resource Management

## COD-110

Files MUST be opened using context managers.

Correct

```python
with path.open("r", encoding="utf-8") as f:
    ...
```

---

## COD-111

Database connections MUST be properly closed.

---

# 14. Project-Specific Rules

## COD-120

Face recognition code MUST remain inside the AI module.

---

## COD-121

Image processing code MUST remain inside Infrastructure.

---

## COD-122

UI widgets MUST NOT implement business logic.

---

## COD-123

Application services coordinate workflows.

They MUST NOT contain UI code.

---

# 15. Review Checklist

> **总表权威**：`.ai/rules/review-rules.md` §22。本节是 §22 在编码层的细化，不重复总表。

Before submitting code, verify:

- [ ] Imports ordered correctly
- [ ] No wildcard imports
- [ ] Type hints complete
- [ ] Public docstrings added
- [ ] Loguru used
- [ ] No print()
- [ ] pathlib.Path used
- [ ] No magic numbers
- [ ] Exceptions handled
- [ ] Function responsibilities are clear
- [ ] Project layer respected

---

# End of Document
