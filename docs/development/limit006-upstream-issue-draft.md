# PySide6 6.11.1 macOS arm64 段错误 issue 草稿（供 owner 提交）

> 提交目标：https://bugreports.qt.io（项目：PYSIDE）或
> https://github.com/qtproject/pyside-pyside/issues
> 语言：建议英文（草稿正文已英文）；以下中英对照便于核对。

---

## Title

`Segmentation fault in worker thread performing filesystem enumeration (os.scandir / os.listdir) while the main thread runs the Qt event loop on macOS arm64 (PySide6 6.11.1)`

## Environment

- OS: macOS 14/15, arm64 (GitHub Actions `macos-latest` runners, M-series)
- Python: 3.11.9 (python.org framework build)
- PySide6: **reproduces on 6.11.1 and 6.8.3** (shiboken6 matching each)
- pytest-qt 4.5.0, pytest 8.4.1
- Other loaded extensions at crash time: numpy, scipy, PIL, sqlalchemy (cyextensions), charset_normalizer, google._upb._message (see full module list below)

## Summary

In a test process where the main thread runs the Qt event loop via
`qtbot.waitUntil` (which enters a nested `QEventLoop.exec`) while a
`QThreadPool` worker thread performs **plain Python filesystem enumeration**
(`os.scandir` / `pathlib.Path.glob` / `os.listdir` + `os.lstat` were all
tried — see "Enumeration-API independence"), the process intermittently
segfaults (SIGSEGV, exit 139). The worker thread is executing pure stdlib C
code when the crash occurs. The crash is **non-deterministic** (same binary
and inputs pass most runs) but recurs across CI runs.

## Minimal reproducing shape

Not a 2-line script yet (see "What we tried"); the reliable trigger in our
suite is:

1. Main thread: pytest-qt test waits with `qtbot.waitUntil(...)` for a
   worker signal (nested event loop, ~15 s timeout).
2. Worker thread (`QThreadPool`): pure-Python function performing a
   recursive directory scan over ~2000 files:
   - `os.scandir(dir)` + `entry.is_dir(follow_symlinks=False)` (PySide6
     6.11-era implementation), and
   - `os.listdir(dir)` + `os.lstat(path)` (an attempted workaround),
   both crash at the same rate.
3. The scan service runs under SQLAlchemy (WAL SQLite) and loguru, but the
   crashing frame is stdlib enumeration.

Faulthandler output (crash inside worker thread):

```
Fatal Python error: Segmentation fault

Thread 0x000000016fd33000 (most recent call first):
  File ".../local_photo_file_scanner.py", line 71 in scan
      (line 71 = `entries = list(os.scandir(current))`;
       with the listdir variant: inside the os.listdir/os.lstat loop)
  File ".../scan_and_register_photos_service.py", line 58 in execute
  File ".../workers/application_tasks.py", line 72 in execute
  File ".../workers/task.py", line 66 in run
  File ".../workers/qt_executor.py", line 79 in run

Current thread 0x00000001eff52180 (most recent call first):
  File ".../pytestqt/qt_compat.py", line 160 in exec
  File ".../pytestqt/wait_signal.py", line 58 in wait
  File ".../pytestqt/qtbot.py", line 503 in wait
  File ".../pytestqt/qtbot.py", line 600 in waitUntil
  File ".../test_scan_single_flight.py", line 159 in test_real_executor_refuses_second_scan_mid_flight_and_recovers
```

## What we tried (all still crash, same stack shape)

- Replaced `pathlib.Path.glob("**/*")` with iterative `os.scandir` → crash.
- Replaced `os.scandir` with `os.listdir` + `os.lstat` (no DirEntry
  machinery at all) → crash.
- The identical scan inside a `QThreadPool` worker **without** the main
  thread waiting in the Qt event loop (plain `threading.Event` + sleep
  polling) → **no crash in 10+ runs** → the concurrent event loop on the
  main thread appears to be a necessary ingredient.
- **Version-independent** (reproduces on PySide6 6.11.1 and 6.8.3): downgrading to **PySide6 6.8.3** (same
  code, same suite, crash tests re-enabled) has been green so far —
  observation ongoing.

## Frequency

Roughly 1-in-3 full-suite runs on `macos-latest` crashed with 6.11.1
across runs #71–#82 of our CI (intermittent; isolated re-runs of the
failing test always pass — full-suite context appears to matter, likely
due to accumulated QObjects/threads from earlier tests).

## Ask

1. Any known interaction between PySide6 6.11 and stdlib file-system C calls
   on secondary threads under macOS arm64?
2. Pointers for further isolation (we can build a smaller reproducer on
   request — the current one needs our full suite to trigger reliably).

## Full loaded-extension list at crash

```
shiboken6.Shiboken, PySide6.QtCore, PySide6.QtGui, PySide6.QtWidgets,
numpy._core._multiarray_umath, numpy.linalg._umath_linalg,
google._upb._message, charset_normalizer.md, charset_normalizer.cd,
requests.packages.charset_normalizer.md, requests.packages.chardet.md,
requests.packages.charset_normalizer.cd, requests.packages.chardet.cd,
PIL._imaging, sqlalchemy.cyextension.collections,
sqlalchemy.cyextension.immutabledict, sqlalchemy.cyextension.processors,
sqlalchemy.cyextension.resultproxy, sqlalchemy.cyextension.util,
markupsafe._speedups, PySide6.QtTest, _cyutility, scipy._cyutility,
scipy._lib._ccallback_c, numpy.random._common, numpy.random.bit_generator,
numpy.random._bounded_integers, numpy.random._mt19937,
numpy.random.mtrand, numpy.random._philox, numpy.random._pcg64,
numpy.random._sfc64, numpy.random._generator, scipy.sparse._sparsetools,
_csparsetools, scipy.sparse._csparsetools, scipy.spatial._ckdtree,
scipy._lib.messagestream, scipy.linalg._fblas, scipy.linalg._flapack,
scipy.linalg.cython_lapack, scipy.linalg._cythonized_array_utils,
scipy.linalg._solve_toeplitz, scipy.linalg._batched_linalg,
scipy.linalg._decomp_lu_cython, scipy.linalg._matfuncs_schur_sqrtm,
scipy.linalg._linalg_pythran, scipy.linalg.cython_blas,
scipy.linalg._decomp_update, scipy.spatial._qhull, scipy.special._ufuncs_cxx,
scipy.special._ellip_harm_2, scipy.special._special_ufuncs,
scipy.special._gufuncs, scipy.special._ufuncs, scipy.special._specfun,
scipy.special._comb, scipy.spatial._hausdorff, scipy.spatial._distance_wrap,
scipy.spatial.transform._rotation_cy, scipy.spatial.transform._rigid_transform_cy,
PIL._imagingmath, PIL._avif, PIL._webp
```

---

## 提交指引（owner 用）

1. 打开 https://bugreports.qt.io → Create → Project 选 **PYSIDE**，类型 Bug；
2. 粘贴以上 Title / Environment / Summary / What we tried / Ask 各段
   （英文正文直接用，"Full loaded-extension list" 可折叠为附件）；
3. 提交后把 issue 编号回填 `KNOWN_ISSUES.md` 的 LIMIT-006 条目；
4. 若 Qt 团队要求更小复现：回复"需要 1-2 周单独立项做最小复现"即可，不必承诺即时交付。
