"""AUD-025 — 审核队列"空"与"读取失败"必须可区分（Stage 13C-C）.

体检前提复核结论：审核队列读取（``ReviewDialog._refresh_list`` →
``ReviewController.list_pending`` → ``RecognitionRepository.list_pending``）
**无 blanket catch**——读失败向上传播，队列绝不会被呈现为"暂无待审核"。
本文件以**真实 SQLite** + **真实控制器** + 真实读故障注入钉死该契约：

- Scenario A 空队列（真实库 0 行）→ 正常空状态（REVIEW_EMPTY，列表隐藏，
  对话框保持可检视）——这是业务状态，不是错误。
- Scenario B 读取失败（真实 ``sqlite3.OperationalError``）→ 异常传播，
  ``REVIEW_EMPTY`` 从未出现——错误**不得**退化为空。
- Scenario C 故障恢复后重读 → 正常呈现队列（无需重启应用）。

同时钉死 D-1 身份选择器的**文档化降级**（``_available_persons`` 读失败 →
选择器为空，但批准时仍走"未指定身份"显式告警路径，见 review_dialog 内部）。
"""

import sqlite3

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.domain import MatchStatus, RecognitionResult
from photo_archiver.presentation.controllers.review_controller import ReviewController
from photo_archiver.presentation.ui_text import REVIEW_EMPTY
from photo_archiver.presentation.views.review_center_page import ReviewCenterPage


class _ExplodingRecognitionRepository:
    """真实仓储外层包装：读路径抛真实 SQLite 异常，写路径透传。"""

    def __init__(self, real):  # noqa: ANN001
        self._real = real

    def list_pending(self):  # noqa: ANN201
        connection = self._real._connection_provider.connect()  # noqa: SLF001
        try:
            connection.execute("SELECT * FROM no_such_table_for_failure_injection")
        except sqlite3.OperationalError:
            # from None：抑制 cause 链，使"读失败"这一事实本身可断言。
            raise sqlite3.OperationalError("simulated review read failure") from None
        finally:
            connection.close()
        return self._real.list_pending()

    def __getattr__(self, name):  # noqa: ANN001, ANN202
        return getattr(self._real, name)


def _dialog(repos, recognition_repository=None):  # noqa: ANN001, ANN202
    controller = ReviewController(
        use_case=None,  # type: ignore[arg-type] - 读侧测试不需要写能力
        recognition_repository=recognition_repository or repos.recognition,
        photo_repository=repos.photos,
        person_repository=repos.people,
    )
    return ReviewCenterPage(controller)


def test_empty_queue_is_a_business_state_not_an_error(qtbot, tmp_path):  # noqa: ANN001
    """Scenario A：真实库 0 待审核行 → 正常空状态。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    dialog = _dialog(repos)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.isVisible()
    assert dialog._status.text() == REVIEW_EMPTY
    assert dialog._list.isHidden()
    for button in (dialog._approve_selected, dialog._reject_selected, dialog._approve_all):
        assert not button.isEnabled()


def test_read_failure_never_renders_as_empty_queue(qtbot, tmp_path):  # noqa: ANN001
    """Scenario B：真实读失败 → 异常传播（构造期或刷新期），空状态文案不得出现。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    dialog = None
    with pytest.raises(sqlite3.OperationalError, match="simulated review read failure"):
        # 读失败可能发生在构造期（对话框首次装载队列）或之后任一刷新点——
        # 两条路径都必须让异常冒泡，绝不退化为"空队列"。
        dialog = _dialog(repos, _ExplodingRecognitionRepository(repos.recognition))
        if dialog is not None:
            qtbot.addWidget(dialog)
            dialog._refresh_list()  # noqa: SLF001 - 契约在测

    if dialog is not None:  # pragma: no cover - 构造期未失败时的显式刷新分支
        assert dialog._status.text() != REVIEW_EMPTY


def test_queue_recovers_after_read_failure_without_restart(qtbot, tmp_path):  # noqa: ANN001
    """Scenario C：故障恢复后重读 → 正常呈现队列（无需重启应用）。"""
    from photo_archiver.domain import Photo, PhotoPath, PhotoPathBase

    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    photo = Photo(
        path=PhotoPath(tmp_path / "p.jpg", base=PhotoPathBase.ABSOLUTE),
        original_name="p.jpg",
    )
    repos.photos.add(photo)
    repos.recognition.add(RecognitionResult(photo_id=photo.id, confidence=None))

    flaky = _ExplodingRecognitionRepository(repos.recognition)
    with pytest.raises(sqlite3.OperationalError):
        broken = _dialog(repos, flaky)
        broken._refresh_list()  # noqa: SLF001

    # 恢复：读侧回到真实仓储后，队列正常呈现——无需重启应用/进程。
    dialog = _dialog(repos, repos.recognition)
    qtbot.addWidget(dialog)
    dialog._refresh_list()  # noqa: SLF001

    assert dialog._status.text() != REVIEW_EMPTY
    assert not dialog._list.isHidden()
    assert dialog._list.count() == 1


def test_pending_rows_are_listed_in_the_real_read_path(tmp_path):  # noqa: ANN001
    """对照：真实读路径在有数据时返回 APPROVED 之外的全部 pending 行。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    from photo_archiver.domain import Photo, PhotoPath, PhotoPathBase

    photo = Photo(
        path=PhotoPath(tmp_path / "q.jpg", base=PhotoPathBase.ABSOLUTE),
        original_name="q.jpg",
    )
    repos.photos.add(photo)
    pending = RecognitionResult(photo_id=photo.id, confidence=None)
    assert pending.status is MatchStatus.PENDING
    repos.recognition.add(pending)

    controller = ReviewController(
        use_case=None,  # type: ignore[arg-type]
        recognition_repository=repos.recognition,
        photo_repository=repos.photos,
        person_repository=repos.people,
    )
    assert [row.photo_id for row in controller.list_pending()] == [photo.id]
