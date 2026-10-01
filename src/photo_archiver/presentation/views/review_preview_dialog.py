"""Review preview dialog — HD 审片闭环（2026-10-01 功能完善）。

继承 :class:`PhotoDetailDialog` 的全部高清基建（受控解码、EXIF 转置、
DPR 归位、request_id/生命周期竞态防护），在其上叠加审核控制：

- 上一张/下一张：在待审核队列快照内移动游标并重启受控解码；
  ←/→ 键等价（D4-A）；
- 通过本条/拒绝本条：仅作用于**当前游标这一条结果**（D1-A——多脸照片
  逐脸独立审）；身份取页面当前选择器值、预览内只读展示（D2-A），
  未指定身份时复用既有确认告警；
- 审核后**停留原地**（D3-B）：按钮转为已处理态防重复提交，由人工点
  侧边按钮继续。

页面经回调执行 controller 调用并发 ``review_changed``（照片墙即时刷新
与页面按钮同一路径）；本对话框不直接触碰 ReviewController。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable
from uuid import UUID

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from photo_archiver.domain import Photo, RecognitionResult
from photo_archiver.presentation import ui_text as text
from photo_archiver.presentation.views.photo_detail_dialog import PhotoDetailDialog

if TYPE_CHECKING:
    from PySide6.QtGui import QImage
    from PySide6.QtCore import QSize
    from pathlib import Path


class ReviewPreviewDialog(PhotoDetailDialog):
    """审核高清预览：队列导航 + 当前结果直接通过/拒绝。"""

    def __init__(
        self,
        entries: list[RecognitionResult],
        index: int,
        photo_for: Callable[[RecognitionResult], Photo | None],
        identity: UUID | None,
        identity_text: str,
        on_approve: Callable[[RecognitionResult, UUID | None], None],
        on_reject: Callable[[RecognitionResult], None],
        parent: QWidget | None = None,
        decoder: Callable[[Path, QSize, float], QImage] | None = None,
    ) -> None:
        first_photo = photo_for(entries[index])
        if first_photo is None:
            # 页面入口已守卫双击行可解析；此处兜底 fail-fast（不该到达）。
            raise ValueError("review preview requires a resolvable photo for the opened row")
        super().__init__(
            first_photo,
            badge=None,
            thumbnail_path=None,
            parent=parent,
            decoder=decoder,
            auto_load_hd=True,
        )
        self._entries = list(entries)
        self._cursor = index
        self._photo_for = photo_for
        self._identity = identity
        self._identity_text = identity_text
        self._on_approve = on_approve
        self._on_reject = on_reject
        self._acted: dict[int, str] = {}
        self._build_review_controls()

    def _build_review_controls(self) -> None:
        """Insert the navigation + action rows between preview and metadata."""
        self._position_label = QLabel(self)
        self._prev_button = QPushButton(text.REVIEW_PREVIEW_PREVIOUS, self)
        self._prev_button.clicked.connect(self._on_previous)
        self._next_button = QPushButton(text.REVIEW_PREVIEW_NEXT, self)
        self._next_button.clicked.connect(self._on_next)
        nav_row = QHBoxLayout()
        nav_row.addWidget(self._prev_button)
        nav_row.addWidget(self._position_label, 1)
        nav_row.addWidget(self._next_button)

        self._identity_label = QLabel(
            text.REVIEW_PREVIEW_IDENTITY_PREFIX + self._identity_text, self,
        )
        self._approve_button = QPushButton(text.REVIEW_PREVIEW_APPROVE, self)
        self._approve_button.clicked.connect(self._on_approve_current)
        self._reject_button = QPushButton(text.REVIEW_PREVIEW_REJECT, self)
        self._reject_button.clicked.connect(self._on_reject_current)
        action_row = QHBoxLayout()
        action_row.addWidget(self._identity_label, 1)
        action_row.addWidget(self._approve_button)
        action_row.addWidget(self._reject_button)

        self._acted_hint = QLabel(self)
        self._acted_hint.setVisible(False)

        layout = self.layout()
        assert isinstance(layout, QVBoxLayout)
        layout.insertLayout(2, nav_row)
        layout.insertLayout(3, action_row)
        layout.insertWidget(4, self._acted_hint)
        self._refresh_controls()

    def _current(self) -> RecognitionResult:
        return self._entries[self._cursor]

    def _refresh_controls(self) -> None:
        """Sync position indicator, bounds and the acted state of the row."""
        self._position_label.setText(text.REVIEW_PREVIEW_POSITION.format(
            index=self._cursor + 1, total=len(self._entries),
        ))
        self._prev_button.setEnabled(self._cursor > 0)
        self._next_button.setEnabled(self._cursor < len(self._entries) - 1)
        acted = self._acted.get(self._cursor)
        if acted is None:
            self._acted_hint.setVisible(False)
            self._approve_button.setEnabled(True)
            self._reject_button.setEnabled(True)
            return
        self._acted_hint.setText(
            text.REVIEW_PREVIEW_DONE_APPROVED
            if acted == "approved"
            else text.REVIEW_PREVIEW_DONE_REJECTED
        )
        self._acted_hint.setVisible(True)
        self._approve_button.setEnabled(False)
        self._reject_button.setEnabled(False)

    @Slot()
    def _on_previous(self) -> None:
        if self._cursor > 0:
            self._cursor -= 1
            self._navigate()

    @Slot()
    def _on_next(self) -> None:
        if self._cursor < len(self._entries) - 1:
            self._cursor += 1
            self._navigate()

    def _navigate(self) -> None:
        photo = self._photo_for(self._current())
        if photo is None:
            # 实体缺失（会话中被删除等）：游标保持原地并明示原因，不阻塞导航。
            self._acted_hint.setText(text.REVIEW_PREVIEW_PHOTO_MISSING)
            self._acted_hint.setVisible(True)
            self._approve_button.setEnabled(False)
            self._reject_button.setEnabled(False)
            return
        self.replace_photo(photo)
        self._refresh_controls()

    def _on_approve_current(self) -> None:
        result = self._current()
        if self._identity is None and not self._confirm_without_identity():
            return
        self._on_approve(result, self._identity)
        self._acted[self._cursor] = "approved"
        self._refresh_controls()

    def _on_reject_current(self) -> None:
        result = self._current()
        self._on_reject(result)
        self._acted[self._cursor] = "rejected"
        self._refresh_controls()

    def _confirm_without_identity(self) -> bool:
        """Ask before approving without an identity (same wording as the page).

        D-1: the human decision is never silently blocked, but approving
        without an identity yields a row the archive planner cannot select.
        """
        answer = QMessageBox.question(
            self,
            text.REVIEW_APPROVE_ALL_CONFIRM_TITLE,
            text.REVIEW_NO_IDENTITY_WARNING,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def keyPressEvent(self, event) -> None:  # noqa: ANN001 - PySide6 event type
        """←/→ 等价侧边导航按钮（D4-A）；其余按键交还父类。"""
        key = event.key()
        if key == Qt.Key.Key_Left and self._prev_button.isEnabled():
            self._on_previous()
            return
        if key == Qt.Key.Key_Right and self._next_button.isEnabled():
            self._on_next()
            return
        super().keyPressEvent(event)
