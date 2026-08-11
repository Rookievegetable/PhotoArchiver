"""Tests for ActionResult + PluginReport 类型边界（阶段 1，ADR-026）.

覆盖：
- ActionResult 三态（success/failure/noop）+ report 字段
- PluginReport 单元格 str | int | float 混合类型边界
- failure 不带任意对象，success 可带 PluginReport，noop 不带内容
- frozen + slots 不可变
- 禁止 Any（payload 废止，report 替之）
"""

from __future__ import annotations

import inspect

import pytest

from photo_archiver.application.dtos.plugin_action_result import (
    ActionResult,
    PluginReport,
    failure,
    noop,
    success,
)


# ── ActionResult 三态 ──────────────────────────────────────────────────────


def test_action_result_status_literal_three_states() -> None:
    """status Literal 三态——success/failure/noop（静态守护 typo）."""
    assert ActionResult.__dataclass_fields__["status"].type in (
        "Literal['success', 'failure', 'noop']",
        "ActionStatus",
    )


def test_success_factory_with_report() -> None:
    """success() 可带 PluginReport."""
    report = PluginReport(title="t", columns=("c",), rows=(("a", 1),))
    r = success(message="done", report=report)
    assert r.status == "success"
    assert r.report is report


def test_success_factory_without_report() -> None:
    """success() 无 report——宿主信息提示路径."""
    r = success(message="ok")
    assert r.report is None


def test_failure_factory_no_report_no_payload() -> None:
    """failure() 只带 message——不带任意对象（ADR-026 收紧）."""
    r = failure(message="boom")
    assert r.status == "failure"
    assert r.report is None
    # failure() 不收 report参——验证签名
    sig = inspect.signature(failure)
    assert "report" not in sig.parameters, "failure() MUST NOT accept report param"
    assert "payload" not in sig.parameters, "failure() MUST NOT accept legacy payload param"


def test_noop_factory_no_content() -> None:
    """noop() 不带内容——action_id 不属本插件."""
    r = noop()
    assert r.status == "noop"
    assert r.message == ""
    assert r.report is None


# ── ActionResult 废止 payload:Any ──────────────────────────────────────────


def test_action_result_no_payload_field() -> None:
    """ActionResult 废止 payload:Any 字段（ADR-026 收紧）."""
    fields = ActionResult.__dataclass_fields__
    assert "payload" not in fields, "ActionResult MUST NOT have payload field (ADR-026)"
    assert "report" in fields, "ActionResult MUST have report field (ADR-026)"


def test_action_result_report_typed_plugin_report_or_none() -> None:
    """report 字段类型是 PluginReport | None（非 Any）."""
    fields = ActionResult.__dataclass_fields__
    report_type = fields["report"].type
    assert "PluginReport" in report_type, f"report field MUST be typed PluginReport, got: {report_type}"


# ── PluginReport 单元格混合类型 ────────────────────────────────────────────


def test_plugin_report_cell_str_int_float_mixed() -> None:
    """单元格 str | int | float 混合（ADR-026 裁决点 4=A）."""
    report = PluginReport(
        title="mixed",
        columns=("Str", "Int", "Float"),
        rows=(
            ("label", 42, 3.14),
            ("other", 0, -1.5),
        ),
    )
    assert isinstance(report.rows[0][0], str)
    assert isinstance(report.rows[0][1], int)
    assert isinstance(report.rows[0][2], float)


def test_plugin_report_frozen_slots_immutable() -> None:
    """PluginReport 不可变（frozen + slots）."""
    report = PluginReport(title="t", columns=("c",), rows=(("a", 1),))
    with pytest.raises(Exception):
        report.title = "other"  # type: ignore[misc]


def test_plugin_report_columns_and_rows_tuples() -> None:
    """columns/rows 是 tuple（不可变序列）."""
    report = PluginReport(title="t", columns=("a", "b"), rows=(("x", 1), ("y", 2)))
    assert isinstance(report.columns, tuple)
    assert isinstance(report.rows, tuple)
    assert isinstance(report.rows[0], tuple)
