"""Startup failure presentation (Phase B P0-6, D-B4).

Corruption is surfaced in Chinese with concrete recovery steps; the application
never rebuilds or silently swaps the database. This module only accepts plain
primitives (``Path``/``str``) so the presentation layer stays clear of
infrastructure imports — the entry point (``main.py``) unwraps the typed error.
"""

from collections.abc import Sequence
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

CORRUPTED_DATABASE_TITLE = "数据库损坏，无法启动"


def corrupted_database_guidance(
    database_path: Path,
    backup_directory: Path,
    issues: Sequence[str],
) -> str:
    """Build the user-facing Chinese guidance for a corrupted database file."""
    issue_text = "；".join(issues) if issues else "quick_check 未通过"
    return (
        "照片数据库文件损坏，PhotoArchiver 无法继续启动。\n"
        "\n"
        f"数据库位置：\n    {database_path}\n"
        "\n"
        "保护与恢复步骤：\n"
        "1. 程序已立即停止写入，不会覆盖、重建或更换该文件。\n"
        f"2. 启动时自动创建的数据库备份位于：\n    {backup_directory}\n"
        "3. 恢复方法：关闭程序后，将备份目录中最近一份 "
        "photo_archiver_YYYYMMDD_HHMMSS.db 复制到上述数据库位置并改回原文件名"
        "（请先自行妥善保留当前损坏文件），再重新启动程序。\n"
        "4. 若备份目录不存在或没有可用备份，请勿反复重试启动；"
        "该数据库文件需要人工介入处理。\n"
        "\n"
        f"技术细节：{issue_text}"
    )


def show_corrupted_database_dialog(message: str) -> None:
    """Show the corruption dialog, creating a QApplication if none exists yet."""
    if QApplication.instance() is None:
        QApplication(list(sys.argv))
    QMessageBox.critical(None, CORRUPTED_DATABASE_TITLE, message)