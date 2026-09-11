"""ArchivePath Windows-name sanitization — ADR-036 D4 (Phase F F-1).

体检 F-10：人员名 ``con``、源文件 ``nul.jpg`` 等在 Windows 上会系统性归档
FAILED。本矩阵锁定净化规则：非法字符/控制字符 → ``_``、尾点尾空格去除、
保留设备名（首个点前词干，大小写不敏感）前缀 ``_``——全部纯字符串逻辑，
零文件系统调用（Domain 零依赖红线）。
"""

import pytest

from photo_archiver.domain import ArchivePath, ValidationError
from photo_archiver.domain.value_objects.archive_path import (
    WINDOWS_RESERVED_DEVICE_NAMES,
    sanitize_windows_filename,
)


def _path(person: str, original: str = "photo.jpg") -> ArchivePath:
    return ArchivePath(
        archive_root=str("D:/archive"),
        person_name=person,
        event_or_date="2024-05-01",
        original_name=original,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 普通安全名原样通过
        ("Alice", "Alice"),
        ("2024-05-01", "2024-05-01"),
        ("alice_portrait.jpg", "alice_portrait.jpg"),
        # 非法字符 → _
        ("a:b", "a_b"),
        ("star*name", "star_name"),
        ('quo"te', "quo_te"),
        ("less>than", "less_than"),
        ("a|b", "a_b"),
        ("q?x", "q_x"),
        # 控制字符 → _（TAB 与 \x01）
        ("a\tb", "a_b"),
        ("a\x01b", "a_b"),
        # 尾点 / 尾空格去除（Windows 静默拒绝）
        ("name.", "name"),
        ("name ", "name"),
        ("name. . ", "name"),
        # 保留设备名：大小写不敏感、带扩展名、点后多段
        ("con", "_con"),
        ("CON", "_CON"),
        ("con.jpg", "_con.jpg"),
        ("Nul.txt.bak", "_Nul.txt.bak"),
        ("com1", "_com1"),
        ("Lpt9", "_Lpt9"),
        ("aux.png", "_aux.png"),
        # 词干非精确匹配不受影响（包含关系不算保留名）
        ("console", "console"),
        ("contact.jpg", "contact.jpg"),
        ("nul_.txt", "nul_.txt"),
    ],
)
def test_sanitize_windows_filename_matrix(raw: str, expected: str) -> None:
    assert sanitize_windows_filename(raw) == expected


def test_reserved_device_name_table_is_complete() -> None:
    assert WINDOWS_RESERVED_DEVICE_NAMES == {
        "CON", "PRN", "AUX", "NUL",
        *{f"COM{i}" for i in range(1, 10)},
        *{f"LPT{i}" for i in range(1, 10)},
    }


def test_archive_path_stores_sanitized_segments() -> None:
    """构造后的段值即安全名——预览与归档记录展示的就是落盘结果。"""
    path = _path(person="con", original="nul.jpg")
    assert path.person_name == "_con"
    assert path.original_name == "_nul.jpg"


def test_archive_path_sanitization_does_not_touch_event_or_date() -> None:
    """builder 生成的 %Y-%m-%d 日期段天然安全——净化对其恒等。"""
    path = _path(person="Alice", original="x.jpg")
    assert path.event_or_date == "2024-05-01"


def test_archive_path_sanitizes_to_empty_raises() -> None:
    with pytest.raises(ValidationError):
        _path(person="...")


def test_archive_path_still_rejects_separators_and_dot_references() -> None:
    """分隔符与 ``..`` 仍是校验错误（raise），不属于净化范围。"""
    with pytest.raises(ValidationError):
        _path(person="a/b")
    with pytest.raises(ValidationError):
        _path(person="a\\b")
    with pytest.raises(ValidationError):
        _path(person="..")
