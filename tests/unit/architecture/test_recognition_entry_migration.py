"""Recognition entry migration guard — 阶段 C Commit 3 旧路径收口的常驻回归.

把"新识别入口必须走 RecognitionRun、旧 MatchPersons 路径退出生产 UI"固化为
机器可判定的静态断言（AST 扫描，零第三方依赖，风格同 test_layer_boundaries）：

1. presentation 层不再 import ``MatchPersonsService`` / ``MatchPersonsController``
   （控制器类本身保留为兼容代码，但不得再被任何 UI 入口接线）；
2. ``MainWindow`` 装配的是 ``RecognitionRunController``，且识别入口 handler
   不再调用 ``start_match``；
3. application 层的 ``MatchPersonsService`` 仍保留（兼容/基线用途），只是
   不再被 presentation 引用——防误删。
"""

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src" / "photo_archiver"
_PRESENTATION = _SRC / "presentation"


def _iter_presentation_modules():
    for path in _PRESENTATION.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        # __init__.py 只做包级再导出（公共 API 兼容），不构成入口接线。
        if path.name == "__init__.py":
            continue
        yield path, ast.parse(path.read_text(encoding="utf-8"), str(path))


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.rsplit(".", 1)[-1])
    return names


def test_presentation_no_longer_imports_match_persons_path() -> None:
    """旧 MatchPersons 路径退出 presentation：无任何模块 import 它。"""
    offenders = [
        str(path.relative_to(_SRC))
        for path, tree in _iter_presentation_modules()
        if _imported_names(tree) & {"MatchPersonsService", "MatchPersonsController"}
    ]
    assert offenders == [], (
        "presentation must not wire the retired MatchPersons entry: "
        f"{offenders}"
    )


def test_main_window_wires_recognition_run_controller() -> None:
    """主窗口装配 RecognitionRunController，且入口不再调用 start_match。"""
    source = (_PRESENTATION / "views" / "main_window.py").read_text(encoding="utf-8")
    tree = ast.parse(source, "main_window.py")
    imported = _imported_names(tree)
    assert "RecognitionRunController" in imported

    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            called.add(node.attr)
    assert "start_run" in called
    assert "start_match" not in called
    assert "_match_controller" not in source


def test_match_persons_service_still_exists_for_compatibility() -> None:
    """收口≠删除：MatchPersonsService 仍在 application 层（兼容/基线路径）。"""
    assert (_SRC / "application" / "services" / "match_persons_service.py").exists()
