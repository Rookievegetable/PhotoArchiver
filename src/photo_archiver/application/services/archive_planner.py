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

# review M-2 fix: only "success" states block re-planning. PLANNED / DRY_RUN /
# FAILED allow retry — DRY_RUN is a preview not a commit, FAILED photos should
# be re-attemptable, PLANNED is an orphan from a crashed prior run.
_ALREADY_ARCHIVED_STATES = frozenset({
    ArchiveStatus.ARCHIVED,
    ArchiveStatus.SKIPPED,
    ArchiveStatus.RENAMED,
    ArchiveStatus.OVERWRITTEN,
})


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
        photo_ids: tuple[UUID, ...] = (),
    ) -> ArchivePlan:
        """Return the archive plan for the given persons (or all if empty).

        Args:
            archive_root: Root directory string, validated by the caller.
            person_ids: Persons to archive; empty tuple means "all persons
                with at least one APPROVED recognition result".
            photo_ids: Specific photos to archive (B3 批量归档); empty tuple
                means "use person_ids selection". When non-empty, the APPROVED
                recognition set is filtered to these photos only — letting the
                UI hand the user's multi-select straight through without
                rescanning. Backward compatible: legacy callers leave it unset.

        person_ids 与 photo_ids 组合语义（review Major-3 fix 显式文档化）：
            - person_ids=() + photo_ids=()  → 全部 persons 的全部 APPROVED 照片
            - person_ids=(pid,..) + photo_ids=() → 仅此 persons 的全部 APPROVED
            - person_ids=() + photo_ids=(pid,..) → 遍历全部 persons 的 APPROVED
              集合过滤到此 photo_ids（行为正确但 O(persons × approved) 遍历，
              性能可优化为按 photo_id 直查 recognition_repository 跳过 persons
              遍历——留后续轮；当前 O(persons × approved) 典型 <50ms 可受）
            - person_ids=(pid,..) + photo_ids=(pid2,..) → 仅此 persons 的
              APPROVED 集合过滤到此 photo_ids（最窄集）

        Each photo is planned at most once even if multiple persons were
        matched historically — we archive under the first APPROVED match's
        person name, mirroring the 1:N Top-1 strategy fixed in裁决 #5.
        """
        target_person_ids = self._resolve_target_persons(person_ids)
        # B3 批量归档：photo_ids 非空时把它转成 set 做 O(1) 过滤；空表走原路径。
        photo_id_filter: set[UUID] | None = set(photo_ids) if photo_ids else None

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
                if photo_id_filter is not None and photo_id not in photo_id_filter:
                    # B3 photo_ids 过滤：跳过不在用户选定集的 APPROVED 项。
                    continue
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
        if existing_record is not None and existing_record.status in _ALREADY_ARCHIVED_STATES:
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
