"""UI/UX 验收 Part A 自动化执行器（companion to ui-acceptance-automation-split.md）.

把《ui-acceptance-automation-split.md》中标注为"可脚本自动化"的验收项映射到
具体测试节点，单次 pytest 运行（junit-xml 解析）后按验收章节聚合判定，并
可选执行 A.10 质量门。Part B（真实缩放/主题/观感/端到端落盘等）仍须按
`ui-acceptance-script.md` 人工执行——本脚本的结论只覆盖 Part A。

用法：
    python scripts/ui_acceptance_automation.py                # Part A 全部章节
    python scripts/ui_acceptance_automation.py --full-pytest  # 追加 A.10 全量 pytest
    python scripts/ui_acceptance_automation.py --output report.md

退出码：0 = 全部章节 PASS 且质量门通过；1 = 存在 FAIL。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

U = "tests/unit/presentation"
G = "tests/integration"

# 章节 → 测试节点（(文件路径, 测试名或 None=整文件)）。与拆分文档 §Part A 对应。
SECTION_MAP: dict[str, list[tuple[str, str | None]]] = {
    "A.1 空库首次使用（概览/清单/CTA/空态）": [
        (f"{U}/test_main_window_navigation.py", None),
        (f"{U}/test_overview_presenter.py", None),
        (f"{U}/test_photo_library_page.py", None),
    ],
    "A.2 导入人员（就绪状态机 + 真实导入闭环）": [
        (f"{U}/test_overview_presenter.py", None),
        (f"{U}/test_workspace_controller.py", None),
        (f"{U}/test_main_window_workspace_state.py", None),
        (f"{G}/test_excel_import_ui_closed_loop.py", None),
    ],
    "A.3 扫描→识别（任务协调/取消/终态刷新/进度）": [
        (f"{U}/test_main_window_task_coordination.py", None),
        (f"{U}/test_task_coordinator.py", None),
        (f"{U}/test_main_window_navigation.py", None),
        (f"{U}/test_visual_system.py", None),
        (f"{U}/test_main_window_workspace_state.py", None),
        (f"{U}/test_scan_cancellation.py", None),
        (f"{G}/test_cancellation_and_ux.py", None),
        (f"{G}/test_task_terminal_refresh.py", None),
    ],
    "A.4 审核中心（角标/计数/确认/缩略图通道/同步刷新）": [
        (f"{U}/test_photo_thumbnail_rendering.py", None),
        (f"{U}/test_review_dialog_review_board.py", None),
        (f"{U}/test_review_dialog_empty_queue.py", None),
        (f"{U}/test_review_controller.py", None),
        (f"{U}/test_visual_system.py", None),
    ],
    "A.5 筛选与空态区分（时间模式/非法区间/三空态/批量栏）": [
        (f"{U}/test_filter_bar.py", None),
        (f"{U}/test_filter_bar_person_axis_layout.py", None),
        (f"{U}/test_photo_library_page.py", None),
    ],
    "A.6 归档安全表达（范围/示例/试运行/确认/直达设置/落盘）": [
        (f"{U}/test_archive_export_safety.py", None),
        (f"{U}/test_archive_controller.py", None),
        (f"{U}/test_visual_system.py", None),
        (f"{G}/test_archive_root_preference.py", None),
        (f"{G}/test_step11_archive_e2e.py", None),
    ],
    "A.7 渲染级视觉断言（AUDIT-UI-001 防线，3d2e71d 起已锁定）": [
        (f"{U}/test_visual_system.py", "test_production_stylesheet_parses_without_qt_warning"),
        (f"{U}/test_visual_system.py", "test_broken_palette_syntax_is_detected_by_warning_capture"),
        (f"{U}/test_visual_system.py", "test_stylesheet_uses_only_valid_palette_function_form"),
        (f"{U}/test_visual_system.py", "test_render_primary_differs_from_normal_button"),
        (f"{U}/test_visual_system.py", "test_render_danger_paints_the_danger_color"),
        (f"{U}/test_visual_system.py", "test_render_disabled_roles_keep_disabled_semantics"),
        (f"{U}/test_visual_system.py", "test_render_focus_ring_is_visible"),
        (f"{U}/test_visual_system.py", "test_render_empty_state_card_paints_background_border_radius"),
    ],
    "A.8 筛选导出（无当前批次/摘要计数/行数核对）": [
        (f"{U}/test_export_ui_wiring.py", None),
        (f"{G}/export/test_export_ui_closed_loop.py", None),
        (f"{G}/export/test_export_scope_integration.py", None),
        (f"{G}/export/test_filtered_export_combined_criteria.py", None),
    ],
    "A.9 危险操作确认（级联/无撤销/默认取消/只读查重）": [
        (f"{U}/test_deletion_ui_dialogs.py", None),
        (f"{U}/test_visual_system.py", None),
        (f"{U}/test_detect_duplicates_disposal.py", None),
    ],
}

PART_B_REMINDER = """
Part B（须人工执行，不可由本脚本替代）— 详见 ui-acceptance-script.md：
  - 100%/125%/150% 真实缩放与浅色/深色真实主题下的可读性抽查；
  - 主 CTA 高亮/危险红/焦点环在真实屏幕上的最终观感确认；
  - 扫描/识别进度的实时流畅性与真实取消时延（LIMIT-002）；
  - 审核缩略图真实渲染观感；真实目标盘归档落盘核对；
  - LIMIT-001 缺模型链路与 macOS 抽查（LIMIT-006）；
  - "非开发者能否独立走通"的可用性结论。
"""


def run_mapped_tests(paths: list[str]) -> tuple[dict[str, str], str]:
    """Run one pytest pass over the mapped files; return per-node results."""
    junit_fd, junit_path = tempfile.mkstemp(suffix=".xml")
    junit = Path(junit_path)
    cmd = [sys.executable, "-m", "pytest", "--junitxml", str(junit), "-q", "--tb=short",
           *sorted(set(paths))]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, encoding="utf-8",
                          errors="replace")
    output = (proc.stdout or "") + (proc.stderr or "")
    results: dict[str, str] = {}
    try:
        if not junit.exists():
            return {}, output
        try:
            tree = ET.parse(junit)
        except ET.ParseError:
            return {}, output
        for case in tree.iter("testcase"):
            name = case.get("name", "")
            # junitxml 只带点分 classname（无 file 属性、无 .py 后缀）——
            # 还原为与映射表一致的"tests/.../test_x.py::test_name"形态。
            module_path = case.get("classname", "").replace(".", "/") + ".py"
            if case.find("failure") is not None or case.find("error") is not None:
                status = "FAILED"
            elif case.find("skipped") is not None:
                status = "SKIPPED"
            else:
                status = "PASSED"
            results[f"{module_path}::{name}"] = status
    finally:
        import os
        os.close(junit_fd)
        junit.unlink(missing_ok=True)
    return results, output


def run_gate(cmd: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, encoding="utf-8",
                          errors="replace")
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
    return proc.returncode == 0, tail[-1] if tail else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None,
                        help="把报告写入 Markdown 文件（建议 logs/ 下）")
    parser.add_argument("--full-pytest", action="store_true",
                        help="追加 A.10 全量 pytest（CI 日常已承担，验收可显式触发）")
    args = parser.parse_args()

    all_paths = sorted({path for nodes in SECTION_MAP.values() for path, _ in nodes})
    missing = [p for p in all_paths if not (REPO_ROOT / p).exists()]
    if missing:
        print("映射的测试文件不存在，映射表已过期：")
        for p in missing:
            print(f"  {p}")
        return 1

    print(f"运行 Part A 映射测试（{len(all_paths)} 个文件，单次 pytest）……")
    results, output = run_mapped_tests(all_paths)
    if not results:
        print("pytest 未能产出 junit 结果，原始输出尾部：")
        print(output[-2000:])
        return 1

    report: list[str] = [
        f"# UI/UX 验收 Part A 自动化报告（{datetime.now():%Y-%m-%d %H:%M}）",
        "",
        "依据：docs/development/ui-acceptance-automation-split.md；",
        "渲染级视觉断言自 `3d2e71d`（AUDIT-UI-001/002 修复）起由渲染探针锁定。",
        "",
    ]
    failed_sections: list[str] = []
    for section, nodes in SECTION_MAP.items():
        node_results = []
        for path, name in nodes:
            for key, status in results.items():
                norm_key = key.replace("\\", "/")
                matched = norm_key == path or norm_key.startswith(path + "::")
                if matched and (name is None or norm_key.endswith(f"::{name}")):
                    node_results.append(status)
        passed = sum(1 for s in node_results if s == "PASSED")
        failed = sum(1 for s in node_results if s == "FAILED")
        skipped = sum(1 for s in node_results if s == "SKIPPED")
        verdict = "PASS" if failed == 0 and passed > 0 else "FAIL"
        if verdict == "FAIL":
            failed_sections.append(section)
        line = (f"| {section} | {passed} passed / {failed} failed / {skipped} skipped "
                f"| {verdict} |")
        report.append(line)
        print(line)

    # A.10 质量门
    gates_ok = True
    report += ["", "## A.10 质量门", ""]
    for label, cmd in (
        ("ruff check src tests", [sys.executable, "-m", "ruff", "check", "src", "tests"]),
        ("mypy src", [sys.executable, "-m", "mypy", "src"]),
    ):
        ok, tail = run_gate(cmd)
        gates_ok = gates_ok and ok
        line = f"- {label}: {'PASS' if ok else 'FAIL'}（{tail}）"
        report.append(line)
        print(line)
    if args.full_pytest:
        ok, tail = run_gate([sys.executable, "-m", "pytest", "-q"])
        gates_ok = gates_ok and ok
        line = f"- pytest 全量: {'PASS' if ok else 'FAIL'}（{tail}）"
        report.append(line)
        print(line)
    else:
        report.append("- pytest 全量：未运行（CI 已承担；可用 --full-pytest 显式触发）")
        print("- pytest 全量：未运行（CI 已承担；可用 --full-pytest 显式触发）")

    report += ["", "## 结论", ""]
    overall = "PASS" if not failed_sections and gates_ok else "FAIL"
    if failed_sections:
        report.append(f"失败章节：{'; '.join(failed_sections)}")
        print("失败章节：", "; ".join(failed_sections))
    report.append(f"Part A 自动化验收整体：**{overall}**")
    report.append(PART_B_REMINDER)
    print(f"\nPart A 自动化验收整体：{overall}")

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(report), encoding="utf-8")
        print(f"报告已写入 {args.output}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
