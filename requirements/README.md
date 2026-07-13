# Requirements

## base.txt

Runtime dependencies required to launch and manually verify the current
application without optional AI features.

Install:

```bash
pip install -r requirements/base.txt
```

---

## ai.txt

Optional AI dependencies for face detection and recognition features.

Install only when working on AI-related functionality:

```bash
pip install -r requirements/ai.txt
```

On Windows, `insightface` may need Microsoft C++ Build Tools if pip cannot find
a compatible prebuilt wheel for your Python version.

---

## dev.txt

Development dependencies for formatting, linting, type checking, and tests.
This file includes `base.txt`, but intentionally does not install optional AI
dependencies by default.

Install:

```bash
pip install -r requirements/dev.txt
```

---

Future:

lock.txt

Generated automatically by:

```bash
pip freeze > requirements/lock.txt
```
