"""Tests for Phase E E-4 deletion UI dialogs (ADR-034 确认流展示).

对话框是纯展示视图——持 DTO/UseCase 不持仓储。验证：
- 照片删除确认对话框渲染级联计数与 D3 磁盘不动警示文案；
- 人员删除对话框下拉选人 → 实时预览 → selected_person_id/name 抽取；
- 重复报告对话框注入 disposal 后出「按建议处置」确认。

用真实 E-3 服务 + SQLite 真库（级联计数唯一裁判）驱动对话框构造。
"""

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from pathlib import Path

from photo_archiver.application import (
    DeletePersonService,
    DeletePhotosService,
    DisposeDuplicatesService,
)
from photo_archiver.application.services import ListPersonsService
from photo_archiver.domain import (
    Person,
    PersonIdentity,
    Photo,
    PhotoMetadata,
    PhotoPath,
    PhotoPathBase,
)
from photo_archiver.infrastructure import (
    SQLiteArchiveRecordRepository,
    SQLiteConnectionProvider,
    SQLiteFaceEmbeddingRepository,
    SQLitePersonRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRepository,
)
from photo_archiver.presentation.views.duplicate_report_dialog import DuplicateReportDialog
from photo_archiver.presentation.views.person_deletion_dialog import PersonDeletionDialog
from photo_archiver.presentation.views.photo_deletion_confirm_dialog import (
    PhotoDeletionConfirmDialog,
)


def create_provider(tmp_path: Path) -> SQLiteConnectionProvider:
    """Create and initialize a temporary SQLite database provider."""
    provider = SQLiteConnectionProvider(tmp_path / "e4.sqlite3")
    provider.initialize_schema()
    return provider


def _add_photo(
    provider: SQLiteConnectionProvider,
    name: str,
    content_hash: str | None = None,
) -> Photo:
    """Register a photo with an absolute path and optional content hash."""
    photo = Photo(
        path=PhotoPath(raw_path=Path(f"/photos/{name}").resolve(), base=PhotoPathBase.ABSOLUTE),
        original_name=name,
        metadata=PhotoMetadata(content_hash=content_hash) if content_hash else None,
    )
    SQLitePhotoRepository(provider).add(photo)
    return photo


def _add_person(provider: SQLiteConnectionProvider, name: str) -> Person:
    """Register a person with a unique external identity."""
    from uuid import uuid4

    person = Person(name=name, identity=PersonIdentity(f"ID-{uuid4().hex[:8]}"))
    SQLitePersonRepository(provider).add(person)
    return person


def test_photo_deletion_confirm_dialog_renders_cascade_and_disclaimer(
    qtbot, tmp_path: Path,
) -> None:
    """确认对话框展示照片/识别/归档计数与 D3 磁盘不动警示。"""
    provider = create_provider(tmp_path)
    service = DeletePhotosService(
        SQLitePhotoRepository(provider),
        SQLiteRecognitionRepository(provider),
        SQLiteArchiveRecordRepository(provider),
    )
    photo = _add_photo(provider, "remove.jpg")
    preview = service.preview([photo.id])

    dialog = PhotoDeletionConfirmDialog(preview)
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "确认移除照片登记"
    assert "1 张照片的登记" in dialog._confirmation_text()
    assert "0 条识别结果" in dialog._confirmation_text()
    assert "不会删除磁盘上的任何文件" in dialog._confirmation_text()


def test_person_deletion_dialog_previews_live_cascade(qtbot, tmp_path: Path) -> None:
    """人员删除对话框下拉选人 → 预览显示嵌入删除/识别置空计数。"""
    provider = create_provider(tmp_path)
    person = _add_person(provider, "被删人员")
    delete_service = DeletePersonService(
        SQLitePersonRepository(provider),
        SQLitePhotoRepository(provider),
        SQLiteRecognitionRepository(provider),
        SQLiteFaceEmbeddingRepository(provider),
    )
    list_service = ListPersonsService(SQLitePersonRepository(provider))

    dialog = PersonDeletionDialog(list_service, delete_service)
    qtbot.addWidget(dialog)

    assert dialog.selected_person_id() == person.id
    assert dialog.selected_person_name() == "被删人员"
    preview = dialog.result_preview()
    assert preview is not None
    assert preview.person_count == 1
    assert "照片与磁盘文件均保留" in dialog._preview_label.text()


def test_person_deletion_dialog_empty_catalog_disables_delete(qtbot, tmp_path: Path) -> None:
    """无人员时对话框显示空态提示并禁用确认按钮。"""
    provider = create_provider(tmp_path)
    delete_service = DeletePersonService(
        SQLitePersonRepository(provider),
        SQLitePhotoRepository(provider),
        SQLiteRecognitionRepository(provider),
        SQLiteFaceEmbeddingRepository(provider),
    )
    list_service = ListPersonsService(SQLitePersonRepository(provider))

    dialog = PersonDeletionDialog(list_service, delete_service)
    qtbot.addWidget(dialog)

    assert "暂无人员" in dialog._preview_label.text()
    assert dialog.selected_person_id() is None
    from PySide6.QtWidgets import QDialogButtonBox

    assert dialog._buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled() is False


def test_duplicate_report_dialog_offers_disposal_when_wired(qtbot, tmp_path: Path) -> None:
    """注入 disposal 且有重复组时对话框出「按建议处置」按钮。"""
    provider = create_provider(tmp_path)
    _add_photo(provider, "a.jpg", content_hash="dup")  # noqa: F841  # 注册即可
    _add_photo(provider, "b.jpg", content_hash="dup")
    from photo_archiver.application import DetectDuplicatesService

    detect = DetectDuplicatesService(SQLitePhotoRepository(provider))
    dispose = DisposeDuplicatesService(
        SQLitePhotoRepository(provider),
        SQLiteRecognitionRepository(provider),
        SQLiteArchiveRecordRepository(provider),
    )
    report = detect.execute()

    dialog = DuplicateReportDialog(report, disposal=dispose)
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "重复照片报告"
    assert dialog._disposal is not None
    assert "按建议处置" in dialog._summary_text()


def test_duplicate_report_dialog_readonly_without_disposal(qtbot, tmp_path: Path) -> None:
    """未注入 disposal 时对话框保持只读（首版行为不回归）。"""
    provider = create_provider(tmp_path)
    from photo_archiver.application import DetectDuplicatesService

    detect = DetectDuplicatesService(SQLitePhotoRepository(provider))
    report = detect.execute()

    dialog = DuplicateReportDialog(report)
    qtbot.addWidget(dialog)

    assert dialog._disposal is None

# ── 界面优化 §4.3：按批次删除 / 清空全部人员对话框 ──────────────────────────


def _batch_world(tmp_path: Path):
    """一个批次 + 两名归属人员 + 一名手工人员 + 批次草稿两行。"""
    from photo_archiver.application.services.manage_people_service import (
        ManagePeopleService,
    )
    from photo_archiver.domain import ImportBatch, ImportDraftRow
    from photo_archiver.infrastructure.database.sqlite_import_batch_repository import (
        SQLiteImportBatchRepository,
    )
    from photo_archiver.infrastructure.database.sqlite_unit_of_work import (
        SQLiteUnitOfWork,
    )

    provider = create_provider(tmp_path)
    batches = SQLiteImportBatchRepository(provider)
    people_repo = SQLitePersonRepository(provider)
    batch = ImportBatch(
        file_name="名单A.txt", file_hash="hash-a", source_type="txt",
    )
    batches.add_batch(batch)
    batches.replace_draft_rows(batch.id, [
        ImportDraftRow(batch_id=batch.id, source_row=0, raw_values=["r0"],
                       parsed_name="张三", order_index=0),
        ImportDraftRow(batch_id=batch.id, source_row=1, raw_values=["r1"],
                       parsed_name="李四", order_index=1),
    ])
    person_a = _add_person(provider, "张三")
    person_a.source_batch_id = batch.id
    people_repo.add(person_a)
    person_b = _add_person(provider, "李四")
    person_b.source_batch_id = batch.id
    people_repo.add(person_b)
    _add_person(provider, "王五")
    manage = ManagePeopleService(people_repo, batches)
    from photo_archiver.infrastructure.database.sqlite_recognition_repository import (
        SQLiteRecognitionRepository,
    )
    from photo_archiver.infrastructure.database.sqlite_photo_repository import (
        SQLitePhotoRepository,
    )

    service = DeletePersonService(
        people_repo, SQLitePhotoRepository(provider),
        SQLiteRecognitionRepository(provider),
        SQLiteFaceEmbeddingRepository(provider),
        unit_of_work=SQLiteUnitOfWork(provider), import_batch_repository=batches,
    )
    return manage, service, batch, provider


def test_batch_person_deletion_dialog_previews_and_executes(qtbot, tmp_path: Path):
    """批次选择 → 成员清单与影响摘要 → 执行（默认保留批次记录）。"""
    manage, service, batch, provider = _batch_world(tmp_path)
    from photo_archiver.presentation.views.batch_person_deletion_dialog import (
        BatchPersonDeletionDialog,
    )

    dialog = BatchPersonDeletionDialog(manage, service)
    qtbot.addWidget(dialog)

    assert dialog._impact_label.text().startswith("将删除 2 名人员")
    assert dialog._members_list.count() == 2
    assert not dialog._cleanup_checkbox.isChecked()
    assert dialog._cleanup_warning.isHidden()

    dialog._cleanup_checkbox.setChecked(True)
    assert not dialog._cleanup_warning.isHidden()
    assert "2 条导入草稿" in dialog._cleanup_warning.text()

    dialog._on_confirm()
    assert dialog.result() == dialog.DialogCode.Accepted
    from photo_archiver.infrastructure.database.sqlite_import_batch_repository import (
        SQLiteImportBatchRepository,
    )
    batches = SQLiteImportBatchRepository(provider)
    assert batches.get_batch(batch.id) is None
    assert "草稿" in dialog.last_message() or "已删除批次" in dialog.last_message()


def test_clear_all_people_dialog_requires_explicit_awareness(qtbot, tmp_path: Path):
    """清空对话框：未勾选知悉时确认按钮禁用；勾选后可执行。"""
    manage, service, _batch, _provider = _batch_world(tmp_path)
    from photo_archiver.presentation.views.batch_person_deletion_dialog import (
        ClearAllPeopleDialog,
    )

    dialog = ClearAllPeopleDialog(manage, service)
    qtbot.addWidget(dialog)

    assert "全部 3 名人员" in dialog._impact_label.text()
    assert not dialog._buttons.button(
        dialog._buttons.StandardButton.Ok
    ).isEnabled()

    dialog._aware_checkbox.setChecked(True)
    assert dialog._buttons.button(dialog._buttons.StandardButton.Ok).isEnabled()
    dialog._on_confirm()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert "已清空全部人员" in dialog.last_message()
