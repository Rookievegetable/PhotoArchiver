"""ArchivePlanner — 落裁决 #3 第一段：纯领域计算，零 IO 副作用。

输入：ArchivePhotosCommand + PersonRepository + PhotoRepository +
      RecognitionRepository + ArchivePathBuilder + history lookup
输出：ArchivePlan（tuple[ArchivePlanItem, ...]）+ skipped_count

CLI/UI/tests 调 plan() 得 ArchivePlan，可先展示预览再决定是否 execute。
本类不碰文件系统、不写 ArchiveRecord——record 落库归 ArchiveExecutor。
"""

from uuid import UUID

from loguru import logger

from photo_archiver.application.dtos import ArchivePlan, ArchivePlanItem
from photo_archiver.application.ports import ArchivePathBuilder
from photo_archiver.domain import (
    ArchiveRecordRepository,
    ArchiveStatus,
    PersonRepository,
    PhotoRepository,
    RecognitionRepository,
)


class ArchivePlanner:
    """Plan archive destinations for approved photos, without touching the filesystem.

    The planner is deliberately side-effect free so CLI dry-runs, UI previews,
    and tests can call it repeatedly without persisting anything. Persistence
    of ArchiveRecord aggregates happens in :class:`ArchiveExecutor`.
    """

    def __init__(
        self,
        path_builder: ArchivePathBuilder,
        person_repository: PersonRepository,
        photo_repository: PhotoRepository,
        recognition_repository: RecognitionRepository,
        archive_record_repository: ArchiveRecordRepository,
    ) -> None:
        """Initialize the planner with its repositories and path builder.

        Args:
            path_builder: Builds ArchivePath values per the裁决 #2 naming rule.
            person_repository: Source of person names for the path's person segment.
            photo_repository: Source of photo paths / captured_at / original_name.
            recognition_repository: Source of APPROVED matches per person.
            archive_record_repository: Used to detect already-archived photos so
                re-runs skip them rather than re-plan. Read-only at this stage.
        """
        self._path_builder = path_builder
        self._person_repository = person_repository
        self._photo_repository = photo_repository
        self._recognition_repository = recognition_repository
        self._archive_record_repository = archive_record_repository

    def plan(
        self,
        archive_root: str,
        person_ids: tuple[UUID, ...],
    ) -> ArchivePlan:
        """Return the archive plan for the given persons (or all if empty).

        Args:
            archive_root: Root directory string, validated by the caller.
            person_ids: Persons to archive; empty tuple means "all persons
                with at least one APPROVED recognition result".

        Each photo is planned at most once even if multiple persons were
        matched historically — we archive under the first APPROVED match's
        person name, mirroring the 1:N Top-1 strategy fixed in裁决 #5.
        """
        target_person_ids = self._resolve_target_persons(person_ids)

        items: list[ArchivePlanItem] = []
        skipped_count = 0
        seen_photo_ids: set[UUID] = set()

        for person_id in target_person_ids:
            person = self._person_repository.find_by_id(person_id)
            if person is None:
                logger.warning("Archive plan: person {} missing, skipping", person_id)
                skipped_count += 1
                continue
            approved = self._recognition_repository.list_approved_by_person(person_id)
            if not approved:
                logger.debug("Archive plan: person {} has no approved photos", person_id)
                continue

            for recognition in approved:
                photo_id = recognition.photo_id
                if photo_id in seen_photo_ids:
                    # 已经为另一个 person 规划了此 photo（1:N Top-1 落地）。
                    skipped_count += 1
                    continue
                seen_photo_ids.add(photo_id)

                item = self._plan_one(
                    archive_root,
                    person_id,
                    person.name,
                    photo_id,
                )
                if item is None:
                    skipped_count += 1
                    continue
                items.append(item)

        logger.info(
            "ArchivePlanner: planned {} item(s) across {} person(s), skipped {}",
            len(items),
            len(target_person_ids),
            skipped_count,
        )
        return ArchivePlan(items=tuple(items), skipped_count=skipped_count)

    def _resolve_target_persons(self, person_ids: tuple[UUID, ...]) -> tuple[UUID, ...]:
        """Return the person ids to plan for, expanding empty tuple to all with approvals.

        Empty ``person_ids`` 表示"所有有 APPROVED 照片的人"——查询所有 person
        然后过滤掉 list_approved_by_person 为空者。Person 数量当前小可接受；
        未来 Person 数千时应改为 SQL JOIN 一次性取（与 FaceEmbeddingRepository
        list_all 分页延后项同类，Step 12 处理）。
        """
        if person_ids:
            return person_ids
        all_persons = self._person_repository.list_all()
        return tuple(
            person.id  # type: ignore[misc]  # Person.__post_init__ guarantees id is set
            for person in all_persons
            if self._recognition_repository.list_approved_by_person(
                person.id  # type: ignore[arg-type]  # Person.__post_init__ guarantees id is set
            )
        )

    def _plan_one(
        self,
        archive_root: str,
        person_id: UUID,
        person_name: str,
        photo_id: UUID,
    ) -> ArchivePlanItem | None:
        """Build one ArchivePlanItem, or None when the photo should be skipped.

        Skip reasons:
            Photo missing from repository (concurrent delete between match and plan).
            Photo already archived (ArchiveRecord past PLANNED exists).
            Photo path base is not ABSOLUTE — relative paths require PHOTO_ROOT
            resolution which the archive executor does not perform (落 Step 12
            UI worker 范围；本轮 CLI archive 命令只接受已 resolved 的绝对路径).
        """
        photo = self._photo_repository.find_by_id(photo_id)
        if photo is None:
            logger.warning("Archive plan: photo {} missing, skipping", photo_id)
            return None
        if not photo.path.is_absolute:
            logger.warning(
                "Archive plan: photo {} has relative path; archive requires absolute, skipping",
                photo_id,
            )
            return None

        existing_record = self._archive_record_repository.find_by_photo(photo_id)
        if existing_record is not None and existing_record.status is not ArchiveStatus.PLANNED:
            logger.debug(
                "Archive plan: photo {} already archived as {}, skipping",
                photo_id,
                existing_record.status.value,
            )
            return None

        original_name = photo.original_name or photo.path.raw_path.name
        target = self._path_builder.build(
            archive_root=archive_root,
            person_name=person_name,
            captured_at=photo.captured_at,
            original_name=original_name,
        )
        return ArchivePlanItem(
            photo_id=photo_id,
            source_path=photo.path.raw_path,
            target_path=target,
            person_id=person_id,
            person_name=person_name,
        )
