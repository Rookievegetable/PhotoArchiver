"""Static dependency check for ExportController（阶段 1b，ISSUE-016 守护）.

架构审计——验 ``presentation/controllers/export_controller.py`` 不显式导入
``photo_archiver.infrastructure``（DEP-002 Presentation MUST NOT import infrastructure）。

ISSUE-016 修复后守护：format→Exporter 注册表迁 app 装配层（ui_assembly），
ExportController 仅依赖 Exporter Protocol + format_name 字符串。本测试防越界复发。
"""

from __future__ import annotations

from pathlib import Path

import pytest

FORBIDDEN_PREFIX = "photo_archiver.infrastructure"

EXPORT_CONTROLLER_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "src"
    / "photo_archiver"
    / "presentation"
    / "controllers"
    / "export_controller.py"
)


def _read_imports(module_path: Path) -> list[str]:
    """Return all import statements (from X import / import X) as text lines."""
    text = module_path.read_text(encoding="utf-8")
    imports: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            imports.append(stripped)
    return imports


def test_export_controller_does_not_import_infrastructure() -> None:
    """ExportController (Presentation) 不导入 infrastructure（DEP-002 守护）.

    ISSUE-016 修复后：format→Exporter 注册表迁 ui_assembly 装配层，
    ExportController 仅依赖 Exporter Protocol + 注入的 exporters dict。
    """
    assert EXPORT_CONTROLLER_PATH.exists(), f"ExportController source missing at {EXPORT_CONTROLLER_PATH}"
    imports = _read_imports(EXPORT_CONTROLLER_PATH)
    assert imports, "ExportController should have imports"
    for imp_line in imports:
        assert FORBIDDEN_PREFIX not in imp_line, (
            f"ExportController MUST NOT import infrastructure (DEP-002, ISSUE-016):\n"
            f"  forbidden prefix: {FORBIDDEN_PREFIX}\n"
            f"  offending import:  {imp_line}\n"
            f"  format→Exporter registry should live in app/ui_assembly.py (装配层)."
        )


def test_export_controller_does_not_hardcode_exporter_class_attribute() -> None:
    """ExportController 不持 `_EXPORTERS` 类属性硬编码实例化 Exporter（ISSUE-016 复发守护）.

    旧越界形态：``_EXPORTERS: dict[str, Exporter] = {"xlsx": ExcelExporter(), ...}``
    在类属性处实例化 Infrastructure Exporter——本测试守护此形态不复发。
    扫类属性实际代码行（跳 docstring/注释/字符串字面）。
    """
    import ast

    tree = ast.parse(EXPORT_CONTROLLER_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_EXPORTERS":
                    pytest.fail(
                        "ExportController MUST NOT hardcode _EXPORTERS class attribute "
                        "(ISSUE-016 recurrence guard)——format→Exporter 注册表应迁 app 装配层注入"
                    )


def test_export_controller_accepts_exporters_constructor_param() -> None:
    """ExportController 构造器持 `exporters` 参——装配层注入 format→Exporter dict（ISSUE-016 修复后契约）."""
    import inspect

    from photo_archiver.presentation.controllers.export_controller import ExportController

    sig = inspect.signature(ExportController.__init__)
    assert "exporters" in sig.parameters, (
        "ExportController.__init__ MUST accept `exporters` param (ISSUE-016 fix contract)——"
        "format→Exporter 注册表由 app 装配层注入"
    )
