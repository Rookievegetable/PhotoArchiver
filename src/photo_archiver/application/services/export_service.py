"""ExportService — Step 14 核心编排服务。

责任范围：
    1. 从 Repository 收集导出数据（人员/照片/匹配/归档记录）
    2. 装配为 ExportData DTO
    3. 委托 Infrastructure Exporter 写文件
    4. 返回结果摘要

不负责：
    生成 Excel/CSV 文件（归 Infrastructure Exporters）；
    后台线程调度（归 ExportWorker）；
    UI 交互（归 ExportDialog + Controller）。
"""

from loguru import logger

from photo_archiver.application.dtos.export import (
    ExportArchiveRow,
    ExportData,
    ExportMatchRow,
    ExportPersonRow,
    ExportPhotoRow,
    ExportScope,
)
from photo_archiver.domain import PhotoSearchCriteria
from photo_archiver.domain.repositories import (
    ArchiveRecordRepository,
    PersonRepository,
    PhotoRepository,
    RecognitionRepository,
)
from photo_archiver.application.ports.exporter import ExportRow, Exporter


class ExportService:
    """Orchestrate data gathering + delegation to a concrete exporter.

    The service owns the "what data to export" logic (people with approved matches,
    photos with metadata, archive history) and passes a flat row list to whichever
    ``Exporter`` it receives.
    """

    def __init__(
        self,
        person_repository: PersonRepository,
        photo_repository: PhotoRepository,
        recognition_repository: RecognitionRepository,
        archive_record_repository: ArchiveRecordRepository,
    ) -> None:
        """Initialize with the repositories whose data is exported."""
        self._person_repo = person_repository
        self._photo_repo = photo_repository
        self._recognition_repo = recognition_repository
        self._archive_repo = archive_record_repository

    def export(
        self,
        exporter: Exporter,
        output_path: str,
        scope: ExportScope = ExportScope.ALL,
        criteria: PhotoSearchCriteria | None = None,
    ) -> str:
        """Gather data, flatten to rows, and delegate to the given exporter.

        Args:
            exporter: A concrete ``Exporter`` (Excel / CSV / …).
            output_path: Where the exporter should write the output file.
            scope: Which subset of data to export (default: everything).
            criteria: ``PhotoSearchCriteria`` snapshot reserved for the
                ``FILTERED`` scope. Threaded through to ``_gather_data``
                verbatim; ``ALL`` ignores it. Contract:
                ``docs/health-check/PHASE_7_SCOPE_CONTRACT_REVISION.md`` §3/F5.

        Returns:
            The summary message returned by the exporter.
        """
        data = self._gather_data(scope, criteria)
        rows = self._flatten(data)
        logger.info(
            "ExportService: scope={} people={} photos={} matches={} archive_records={} rows={}",
            scope.value,
            len(data.people),
            len(data.photos),
            len(data.matches),
            len(data.archive_records),
            len(rows),
        )
        return exporter.export(rows, output_path)

    def _gather_data(
        self,
        scope: ExportScope,
        criteria: PhotoSearchCriteria | None = None,
    ) -> ExportData:
        """Gather export data from repositories according to the chosen scope.

        ``CURRENT_BATCH`` and ``FILTERED`` scopes are stubbed for now; only
        ``ALL`` is fully implemented. ``criteria`` is accepted for the
        ``FILTERED`` contract (criteria snapshot re-query) and is not consumed
        until the per-scope dispatch lands — ``ALL`` output is identical
        whether or not a criteria is supplied.
        """
        people = self._person_repo.list_all()
        photos = self._photo_repo.list_all()
        archive_records = self._archive_repo.list_all()

        # Gather approved matches for each person-photo link
        all_recognition: list = []
        for person in people:
            if person.id is not None:
                all_recognition.extend(
                    self._recognition_repo.list_approved_by_person(person.id)
                )

        return ExportData(
            people=tuple(
                ExportPersonRow(
                    person_id=str(p.id) if p.id else "",
                    name=p.name,
                    department=p.department,
                    note=p.note,
                )
                for p in people
            ),
            photos=tuple(
                ExportPhotoRow(
                    photo_id=str(ph.id) if ph.id else "",
                    path=str(ph.path),
                    original_name=ph.original_name,
                    folder_name=str(ph.folder_id) if ph.folder_id else "",
                    captured_at=str(ph.captured_at) if ph.captured_at else "",
                    registered_at=str(ph.created_at) if ph.created_at else "",
                )
                for ph in photos
            ),
            matches=tuple(
                ExportMatchRow(
                    photo_id=str(r.photo_id),
                    person_id=str(r.person_id) if r.person_id else "",
                    person_name="",
                    confidence=r.confidence,
                    status=r.status.value,
                )
                for r in all_recognition
            ),
            archive_records=tuple(
                ExportArchiveRow(
                    photo_id=str(ar.photo_id),
                    person_name=ar.target_person_name,
                    target_path=f"{ar.target_archive_root}/{ar.target_person_name}/{ar.target_event_or_date}/{ar.target_original_name}",
                    status=ar.status.value,
                    archived_at=str(ar.archived_at) if ar.archived_at else "",
                )
                for ar in archive_records
            ),
        )

    @staticmethod
    def _flatten(data: ExportData) -> list[ExportRow]:
        """Flatten the four-section ExportData into one ordered list of ExportRow.

        Rows are ordered: people first, then photos, then matches, then archive
        records. This is a simple approach — callers who need per-section sheets
        should use the ``ExportData`` directly.
        """
        rows: list[ExportRow] = []
        for p in data.people:
            rows.append(
                ExportRow(
                    person_name=p.name,
                    person_department=p.department,
                    person_note=p.note,
                )
            )
        for ph in data.photos:
            rows.append(
                ExportRow(
                    photo_path=ph.path,
                    photo_original_name=ph.original_name,
                    photo_folder=ph.folder_name,
                    photo_captured_at=ph.captured_at,
                )
            )
        for m in data.matches:
            rows.append(
                ExportRow(
                    person_name=m.person_name,
                    photo_path=m.photo_id,
                    match_confidence=m.confidence,
                    match_status=m.status,
                )
            )
        for a in data.archive_records:
            rows.append(
                ExportRow(
                    person_name=a.person_name,
                    archive_status=a.status,
                    archive_target=a.target_path,
                    archive_archived_at=a.archived_at,
                )
            )
        return rows
