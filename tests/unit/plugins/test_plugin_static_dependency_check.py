"""Static dependency check for examples/plugins/（阶段 1，ADR-026 §7）.

架构审计——验 ``examples/plugins/`` 不显式导入：
    photo_archiver.domain
    photo_archiver.infrastructure
    photo_archiver.presentation
    photo_archiver.workers
    photo_archiver.ai

这不是安全沙箱——是分层契约审计（DEP-060 Plugins → Application only）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from photo_archiver.application.dtos.plugin_action_result import noop  # noqa: F401  # 验测试环境可导入

FORBIDDEN_PREFIXES = (
    "photo_archiver.domain",
    "photo_archiver.infrastructure",
    "photo_archiver.presentation",
    "photo_archiver.workers",
    "photo_archiver.ai",
)


def _list_plugin_modules() -> list[Path]:
    """Return all .py files in examples/plugins/ (excluding __init__ dunder)."""
    plugins_dir = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "examples"
        / "plugins"
    )
    return [p for p in sorted(plugins_dir.iterdir()) if p.suffix == ".py" and not p.name.startswith("_")]


def _read_imports(module_path: Path) -> list[str]:
    """Return all import statements (from X import / import X) as text lines."""
    text = module_path.read_text(encoding="utf-8")
    imports: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            imports.append(stripped)
    return imports


@pytest.mark.parametrize("module_path", _list_plugin_modules(), ids=lambda p: p.name)
def test_plugin_module_does_not_import_forbidden_layers(module_path: Path) -> None:
    """examples/plugins/ 任一模块不导入 domain/infrastructure/presentation/workers/ai.

    ADR-026 完成标准：插件不直接访问 UI、Infrastructure、Worker、Repository、UoW
    或 ApplicationContext。本测试是架构审计，非安全沙箱。
    """
    imports = _read_imports(module_path)
    for imp_line in imports:
        for prefix in FORBIDDEN_PREFIXES:
            # 匹配 "from photo_archiver.domain" 或 "import photo_archiver.domain"
            if f"photo_archiver.{prefix.split('.', 1)[1]}" in imp_line.replace(
                f"photo_archiver.{prefix.split('.', 1)[1]}.",
                "",
            ):
                # 更稳的检测：直接字面子串匹配
                pass
        # 直接字面子串匹配——更清晰
        for forbidden in (
            "photo_archiver.domain",
            "photo_archiver.infrastructure",
            "photo_archiver.presentation",
            "photo_archiver.workers",
            "photo_archiver.ai",
        ):
            if forbidden in imp_line:
                pytest.fail(
                    f"{module_path.name} imports forbidden layer:\n  {imp_line}\n"
                    f"  forbidden prefix: {forbidden}\n"
                    f"  plugins MUST depend only on photo_archiver.application (DEP-060).",
                )


def test_stats_report_plugin_only_imports_application_layer() -> None:
    """stats_report_plugin.py 只导 application 层（ADR-026 端到端验收插件）."""
    stats_path = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "examples"
        / "plugins"
        / "stats_report_plugin.py"
    )
    imports = _read_imports(stats_path)
    assert imports, "stats_report_plugin should have imports"
    for imp_line in imports:
        # application 层导入合规
        if "photo_archiver." in imp_line:
            assert "photo_archiver.application" in imp_line, (
                f"stats_report_plugin must only import application layer, got:\n  {imp_line}"
            )


def test_hello_plugin_only_imports_application_layer() -> None:
    """hello_plugin.py 只导 application 层."""
    hello_path = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "examples"
        / "plugins"
        / "hello_plugin.py"
    )
    imports = _read_imports(hello_path)
    for imp_line in imports:
        if "photo_archiver." in imp_line:
            assert "photo_archiver.application" in imp_line, (
                f"hello_plugin must only import application layer, got:\n  {imp_line}"
            )
