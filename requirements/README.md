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

AI extension dependencies. As of roadmap Step 9, the core AI runtime
(`insightface`, `onnxruntime`) has been consolidated into `base.txt` (see
ADR-012 in `.ai/ARCHITECTURE_DECISIONS.md`). This file is retained as a
pure extension mount point for future AI-only auxiliary libraries that
should NOT be installed by default (e.g. extra model packs, benchmark
tooling). It includes `-r base.txt` so `pip install -r requirements/ai.txt`
still provisions the full AI-capable environment.

Do NOT duplicate any dependency already pinned in `base.txt` — version
conflicts here would override `base.txt` per pip `-r` semantics.

Install only when working on AI-related functionality:

```bash
pip install -r requirements/ai.txt
```

On Windows, `insightface` (now installed via `base.txt`) may need Microsoft
C++ Build Tools if pip cannot find a compatible prebuilt wheel for your
Python version.

### Windows toolchain notes (P2-010, per Phase 3 audit)

Reference environment: **Python 3.11 / x86_64 / Windows AMD64** (see
`docs/health-check/AUDIT_BASELINE.md` §3).

- `insightface==1.0.1` publishes **source distributions only** — there are no
  prebuilt Windows wheels. `pip install insightface` therefore always compiles
  locally and requires **Microsoft C++ Build Tools** (MSVC, C++17 workload)
  plus Cython. Windows ARM64 is not a supported build target for insightface
  1.0.1.
- `onnxruntime==1.27.0` ships official Windows wheels (x86_64); verify ARM64
  availability against the onnxruntime release matrix before targeting ARM64
  devices.
- `opencv-python==4.12.0.88` and `Pillow==11.3.0` ship prebuilt Windows
  wheels — no toolchain needed.

If the insightface build fails with linker/compiler errors, install the Build
Tools and re-run `pip install -r requirements/base.txt` inside the activated
venv.

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

## lock.txt

Full transitive-closure pin of the complete runtime environment (P2-001).
Generated automatically from the current environment with:

```bash
pip freeze > requirements/lock.txt
```

Refresh it after **any** change to `requirements/base.txt`. Layering:

- `base.txt` — direct runtime dependencies (curated, commented)
- `lock.txt` — `base.txt` + every transitive dependency, fully pinned

Reproducible install on a fresh environment:

```bash
pip install -r requirements/lock.txt
```
