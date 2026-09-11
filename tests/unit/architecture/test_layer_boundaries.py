"""Architecture layer-boundary assertions — 体检 T-1 常驻自动化.

把 2026-09-10 体检 §3 的"分层边界人工 grep"固化为本套件内的常驻测试：
对 ``src/photo_archiver`` 逐文件做 AST 解析，断言依赖方向与分层禁令
（规则来源：``.ai/rules/dependency-rules.md`` §2/§4 矩阵 + 体检 §3 五项边界）。

规则速记（权威正文见 dependency-rules，此处只编码"机器可判定"的子集）：
    domain           零框架依赖（PySide6/numpy/PIL/...），只依赖 domain 自身
    application      无 GUI、无 SQL/图像栈，依赖 infrastructure 禁止（依赖倒置只经 ports）
    workers          PySide6 仅 QtCore（WRK-002），不触 infrastructure/presentation
    presentation     不触 infrastructure/sqlite3（DEP-002/003）
    infrastructure   不触 presentation/workers/app（组合根方向单向）
    ai               模型适配层，与 infrastructure 同级约束

``app/`` 是组合根（装配层），import 全开，不在断言范围。本测试零第三方依赖
（纯标准库 ast），在三平台 CI 随全量套件运行——分层回归从"人工审计"变为
"每次 push 自动拦截"。
"""

import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[3] / "src" / "photo_archiver"

# 第三方禁令：顶层模块名（domain 全禁；application/workers/presentation 按
# 层职责放行 Qt/loguru 等）。sqlalchemy/PIL/numpy 等运行栈只允许出现在
# infrastructure / ai。
_BANNED_THIRD_PARTY: dict[str, frozenset[str]] = {
    "domain": frozenset(
        {
            "PySide6", "numpy", "pandas", "openpyxl", "sqlalchemy",
            "PIL", "cv2", "loguru", "pytest", "sqlite3",
        }
    ),
    "application": frozenset(
        {"PySide6", "numpy", "pandas", "openpyxl", "sqlalchemy", "PIL", "cv2", "sqlite3", "pytest"}
    ),
    "workers": frozenset({"numpy", "pandas", "openpyxl", "sqlalchemy", "PIL", "cv2", "sqlite3", "pytest"}),
    "presentation": frozenset({"numpy", "pandas", "openpyxl", "sqlalchemy", "cv2", "sqlite3", "pytest"}),
    "infrastructure": frozenset({"pytest"}),
    "ai": frozenset({"pytest"}),
}

# 本地跨层禁令："photo_archiver.<pkg>" 前缀形式的 Import/ImportFrom。
_BANNED_LOCAL_PREFIXES: dict[str, frozenset[str]] = {
    "domain": frozenset(
        {
            "photo_archiver.application", "photo_archiver.infrastructure",
            "photo_archiver.presentation", "photo_archiver.workers",
            "photo_archiver.plugins", "photo_archiver.ai", "photo_archiver.common",
            "photo_archiver.app",
        }
    ),
    "application": frozenset(
        {
            "photo_archiver.infrastructure", "photo_archiver.presentation",
            "photo_archiver.workers", "photo_archiver.plugins",
            "photo_archiver.ai", "photo_archiver.app",
        }
    ),
    "workers": frozenset(
        {
            "photo_archiver.infrastructure", "photo_archiver.presentation",
            "photo_archiver.plugins", "photo_archiver.ai", "photo_archiver.app",
        }
    ),
    "presentation": frozenset(
        # 例外（既有设计，体检 §3 同口径放行）：MainWindow 作为插件宿主持有
        # photo_archiver.plugins.PluginRegistry（ADR-038 接线），并经
        # app.context.ApplicationContext 获得类型引用（views/__init__ 注释）。
        # infrastructure / ai / sqlite3 / Qt 之外的一切本地禁令维持不变。
        {"photo_archiver.infrastructure", "photo_archiver.ai"}
    ),
    "infrastructure": frozenset(
        {"photo_archiver.presentation", "photo_archiver.workers", "photo_archiver.plugins", "photo_archiver.app"}
    ),
    "ai": frozenset(
        {"photo_archiver.presentation", "photo_archiver.workers", "photo_archiver.plugins", "photo_archiver.app"}
    ),
}


def _iter_layer_files(layer: str) -> list[Path]:
    return sorted((_SRC / layer).rglob("*.py"))


def _imported_modules(tree: ast.AST) -> list[str]:
    """Return every module path referenced by Import / ImportFrom statements."""
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module)
    return modules


def _violations(layer: str, path: Path) -> list[str]:
    """Return human-readable boundary violations for one file."""
    found: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for module in _imported_modules(tree):
        top_level = module.split(".")[0]
        banned_local = next(
            (prefix for prefix in _BANNED_LOCAL_PREFIXES[layer] if module == prefix or module.startswith(prefix + ".")),
            None,
        )
        if banned_local is not None:
            found.append(f"{path.name}: imports {module} (banned: {banned_local})")
        elif top_level in _BANNED_THIRD_PARTY[layer]:
            found.append(f"{path.name}: imports {module} (banned third-party: {top_level})")
        elif layer == "workers" and top_level == "PySide6" and not module.startswith("PySide6.QtCore"):
            found.append(f"{path.name}: imports {module} (workers may only use PySide6.QtCore)")
        elif layer == "workers" and module == "PySide6":
            found.append(f"{path.name}: imports PySide6 without .QtCore (workers may only use PySide6.QtCore)")
    return found


@pytest.mark.parametrize("layer", sorted(_BANNED_LOCAL_PREFIXES))
def test_layer_boundaries_hold(layer: str) -> None:
    """Every file in ``layer`` respects its dependency-direction contract."""
    assert (_SRC / layer).is_dir(), f"layer package missing: {layer}"

    all_violations: list[str] = []
    for path in _iter_layer_files(layer):
        all_violations.extend(_violations(layer, path))

    assert not all_violations, (
        f"Layer boundary violations in '{layer}' "
        f"(see .ai/rules/dependency-rules.md §2/§4):\n  " + "\n  ".join(all_violations)
    )
