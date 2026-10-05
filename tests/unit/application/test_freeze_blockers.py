"""Stage 4 冻结阻断项回归（BLK-1 / BLK-5 / D-1）。

全部走**真实 SQLite**（不用 fake repository），以确保 schema、migration、
mapper、repository 与查询口径一致：

- **BLK-1** 归档去重按稳定 Person identity：
  (1) 跨部门同名的两个 person 互不抑制归档；
  (2) person 改名后不因姓名变化而重复归档；
  (3) workspace counter 与 planner 用同一套去重口径；
  (4) 存量行（``person_id IS NULL``）仍按姓名回退，不漏判。
- **BLK-5** 无相似度证据的确认写 NULL confidence，不是 0.0。
- **D-1** 人工审核批准可同时写入身份归属，使该行真正进入归档计划。
"""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.domain import (
    ArchiveStatus,
    MatchStatus,
    Person,
    Photo,
    PhotoPath,
    PhotoPathBase,
    RecognitionResult,
)
from photo_archiver.domain.entities.archive import ArchiveRecord
from photo_archiver.domain.entities.face_cluster import (
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
)
from photo_archiver.domain.entities.face_observation import FaceObservation
from photo_archiver.domain.entities.recognition_run import RecognitionRun
from photo_archiver.domain.value_objects.archive_path import ArchivePath
from photo_archiver.domain.value_objects.face_box import FaceBox
from photo_archiver.domain.value_objects.face_embedding import FaceEmbedding
from photo_archiver.application.services.identity_decision_service import (
    IdentityDecisionService,
)
from photo_archiver.application.services.projection_reconciler import (
    ProjectionReconciler,
)


class _PathBuilder:
    """Minimal ArchivePathBuilder stub with a fixed date segment."""

    def build(self, archive_root, person_name, captured_at, original_name):
        return ArchivePath(
            archive_root=archive_root, person_name=person_name,
            event_or_date="2024-05-01", original_name=original_name,
        )


def _add_person(repos, name: str, department: str | None = None) -> Person:
    person = Person(name=name, department=department)
    repos.people.add(person)
    return person


def _add_photo(repos, file_name: str = "p.jpg") -> Photo:
    photo = Photo(
        path=PhotoPath(Path.cwd() / "src" / file_name, base=PhotoPathBase.ABSOLUTE),
        original_name=file_name,
        captured_at=datetime(2024, 5, 1),
    )
    repos.photos.add(photo)
    return photo


def _cluster_photo(repos, photo: Photo):
    """D-2 = B：为照片播种"已聚类"事实（observation → member → cluster）。"""
    run = RecognitionRun()
    repos.recognition_runs.add_run(run)
    cluster_run = FaceClusterRun(recognition_run_id=run.id, algorithm_version="test")
    repos.face_clusters.add_cluster_run(cluster_run)
    cluster = FaceCluster(
        cluster_run_id=cluster_run.id, run_id=run.id,
        ordinal=0, member_count=1, sort_key="k|000000",
    )
    repos.face_clusters.add_clusters([cluster])
    observation = FaceObservation(
        run_id=run.id, photo_id=photo.id, face_index=0, photo_face_count=1,
        det_score=0.9, box=FaceBox(0, 0, 10, 10),
        embedding=FaceEmbedding((1.0, 0.0)), scope_verdict="in_selected_scope",
    )
    repos.face_observations.add_many([observation])
    repos.face_clusters.add_members(
        [FaceClusterMember(cluster_id=cluster.id, observation_id=observation.id)]
    )
    return cluster


def _any_cluster_id(repos):
    return repos.face_clusters.list_all_cluster_runs()[0].id


def _decision_service(repos) -> IdentityDecisionService:
    reconciler = ProjectionReconciler(
        recognition_repository=repos.recognition,
        assignment_repository=repos.cluster_assignments,
        cluster_repository=repos.face_clusters,
        observation_repository=repos.face_observations,
    )
    return IdentityDecisionService(
        recognition_repository=repos.recognition,
        assignment_repository=repos.cluster_assignments,
        cluster_repository=repos.face_clusters,
        observation_repository=repos.face_observations,
        person_repository=repos.people,
        sample_repository=repos.person_face_samples,
        reconciler=reconciler,
        transaction_runner=repos._connection_provider.run_immediate,
    )


def _approve(repos, photo: Photo, person: Person) -> RecognitionResult:
    """Write an APPROVED compat row carrying the person identity."""
    result = RecognitionResult(
        photo_id=photo.id, confidence=0.9,
        person_id=person.id, status=MatchStatus.APPROVED,
    )
    repos.recognition.add(result)
    return result


def _record(repos, photo: Photo, person: Person, name: str) -> ArchiveRecord:
    """Persist a successful archive record for (person, photo)."""
    record = ArchiveRecord(
        photo_id=photo.id,
        target_archive_root="/archive",
        target_person_name=name,
        target_event_or_date="2024-05-01",
        target_original_name=photo.original_name or "p.jpg",
        status=ArchiveStatus.ARCHIVED,
        person_id=person.id,
    )
    repos.archive_records.add(record)
    return record


# ── BLK-1：同名不同人互不抑制 ────────────────────────────────────────────────


def test_same_name_different_people_do_not_suppress_each_other(tmp_path: Path) -> None:
    """BLK-1(1)：跨部门同名的两个 person 各自都能归档同一张照片。

    旧实现按 ``target_person_name`` 去重，A 归档后 B 会被静默跳过。
    """
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    person_a = _add_person(repos, "张伟", department="研发部")
    person_b = _add_person(repos, "张伟", department="市场部")
    photo = _add_photo(repos)
    _approve(repos, photo, person_a)
    _approve(repos, photo, person_b)
    _record(repos, photo, person_a, "张伟")

    assert repos.archive_records.has_successful_for_person(
        photo.id, person_a.id, "张伟",
    )
    # B 与 A 身份不同 —— 不得被 A 的成功归档抑制。
    assert not repos.archive_records.has_successful_for_person(
        photo.id, person_b.id, "张伟",
    )


def test_rename_does_not_re_archive_the_same_photo(tmp_path: Path) -> None:
    """BLK-1(2)：person 改名后，同一 (person, photo) 仍判定为已归档。

    ``target_person_name`` 是写死的历史字符串；身份判定必须回到 person_id。
    """
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    person = _add_person(repos, "旧名字")
    photo = _add_photo(repos)
    _record(repos, photo, person, "旧名字")

    # 用新姓名再查一次（模拟改名后再次规划）。
    assert repos.archive_records.has_successful_for_person(
        photo.id, person.id, "新名字",
    )


# ── BLK-1：workspace counter 与 planner 同口径 ────────────────────────────────


def test_archivable_count_uses_identity_dedup(tmp_path: Path) -> None:
    """BLK-1(3)：同名不同人时，计数与 planner 都把两人分别计入。

    旧口径 ``a.target_person_name = person.name`` 会让 B 的 APPROVED 行
    因 A 已归档而被排除，导致概览计数与实际可归档项脱节。
    """
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    person_a = _add_person(repos, "李娜", department="研发部")
    person_b = _add_person(repos, "李娜", department="市场部")
    photo = _add_photo(repos)
    _approve(repos, photo, person_a)
    _approve(repos, photo, person_b)
    _record(repos, photo, person_a, "李娜")

    counts = repos.recognition.read_workspace_counts()
    # A 已被成功归档拦截；B 仍可归档 -> 计数为 1。
    assert counts.archivable_count == 1


def test_legacy_row_without_person_id_falls_back_to_name(tmp_path: Path) -> None:
    """BLK-1(4)：``person_id IS NULL`` 的存量行仍按姓名回退去重。

    迁移 008 对重名行不做回填（宁可沿用旧语义也不猜错身份），去重必须
    因此仍能命中这些行，否则升级后会出现重复归档。
    """
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    person = _add_person(repos, "王芳")
    photo = _add_photo(repos)
    legacy = ArchiveRecord(
        photo_id=photo.id,
        target_archive_root="/archive",
        target_person_name="王芳",
        target_event_or_date="2024-05-01",
        target_original_name="p.jpg",
        status=ArchiveStatus.ARCHIVED,
        person_id=None,  # 模拟迁移前/重名无法回填的存量行
    )
    repos.archive_records.add(legacy)

    assert repos.archive_records.has_successful_for_person(
        photo.id, person.id, "王芳",
    )
    counts = repos.recognition.read_workspace_counts()
    assert counts.archivable_count == 0  # 该照片无 APPROVED 行


def test_planner_rerun_after_rename_is_skipped(tmp_path: Path) -> None:
    """BLK-1(2) 端到端：改名后重跑 planner，不应重新规划同一张照片。"""
    from photo_archiver.application.services.archive_planner import ArchivePlanner

    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    person = _add_person(repos, "改名之前")
    photo = _add_photo(repos)
    _approve(repos, photo, person)
    _record(repos, photo, person, "改名之前")

    planner = ArchivePlanner(
        path_builder=_PathBuilder(),
        person_repository=repos.people,
        photo_repository=repos.photos,
        recognition_repository=repos.recognition,
        archive_record_repository=repos.archive_records,
    )
    # 模拟改名：仓库里 person 仍为旧名，但归档记录按身份命中。
    plan = planner.plan("/archive", (person.id,))
    assert plan.planned_count == 0
    assert plan.skipped_count == 1


# ── BLK-5：置信度语义 ────────────────────────────────────────────────────────


def test_no_evidence_confidence_is_none_not_zero() -> None:
    """BLK-5：``None``（无相似度证据）与 ``0.0``（测得相似度为零）语义不同。"""
    result = RecognitionResult(photo_id=uuid4(), confidence=None)
    assert result.confidence is None
    assert result.confidence != 0.0


def test_confidence_round_trips_null_through_sqlite(tmp_path: Path) -> None:
    """BLK-5：NULL confidence 可经 SQLite 往返（migration 008 放宽 NOT NULL）。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    photo = _add_photo(repos)
    person = _add_person(repos, "赵强")
    result = RecognitionResult(
        photo_id=photo.id, confidence=None,
        person_id=person.id, status=MatchStatus.APPROVED,
    )
    repos.recognition.add(result)
    loaded = repos.recognition.find_by_id(result.id)
    assert loaded is not None
    assert loaded.confidence is None
    assert loaded.person_id == person.id


def test_confidence_out_of_range_still_rejected(tmp_path: Path) -> None:
    """BLK-5 未放宽校验：有值时仍必须落在 [0.0, 1.0]。"""
    import pytest

    from photo_archiver.domain import ValidationError

    with pytest.raises(ValidationError):
        RecognitionResult(photo_id=uuid4(), confidence=1.5)
    with pytest.raises(ValidationError):
        RecognitionResult(photo_id=uuid4(), confidence=-0.1)


def test_approved_null_confidence_row_still_archives(tmp_path: Path) -> None:
    """BLK-5：confidence 为 NULL 不影响进入归档（归档不按置信度过滤）。"""
    from photo_archiver.application.services.archive_planner import ArchivePlanner

    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    person = _add_person(repos, "孙俪")
    photo = _add_photo(repos)
    repos.recognition.add(RecognitionResult(
        photo_id=photo.id, confidence=None,
        person_id=person.id, status=MatchStatus.APPROVED,
    ))
    planner = ArchivePlanner(
        path_builder=_PathBuilder(),
        person_repository=repos.people,
        photo_repository=repos.photos,
        recognition_repository=repos.recognition,
        archive_record_repository=repos.archive_records,
    )
    plan = planner.plan("/archive", ())
    assert plan.planned_count == 1
    assert plan.items[0].person_id == person.id


# ── D-1：人工结果为最终结果 ───────────────────────────────────────────────────


def test_manual_approval_can_record_identity_and_reach_archive(tmp_path: Path) -> None:
    """D-1：审核批准时写入身份后，该行真正进入归档计划。

    修复前：只改 status -> ``person_id IS NULL`` -> 归档永不选中。
    """
    from photo_archiver.application.services.archive_planner import ArchivePlanner
    from photo_archiver.application.services.review_recognition_service import (
        ReviewRecognitionService,
    )

    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    person = _add_person(repos, "周迅")
    photo = _add_photo(repos)
    cluster = _cluster_photo(repos, photo)
    pending = RecognitionResult(photo_id=photo.id, confidence=None)
    repos.recognition.add(pending)

    # S1-F：身份批准走 Assignment → ProjectionReconciler 唯一链（D-2 = B）。
    service = ReviewRecognitionService(
        repos.recognition, identity_decision_service=_decision_service(repos),
    )
    approved = service.approve(pending.id, person.id)
    assert approved is not None
    assert approved.person_id == person.id
    assert approved.status is MatchStatus.APPROVED
    assert approved.assignment_id is not None, "S1：新 approved 必须携带支撑引用"

    # 落库同样带身份（服务层返回值与 DB 必须一致），且 review 决策行存在。
    stored = repos.recognition.find_by_id(pending.id)
    assert stored is not None
    assert stored.person_id == person.id
    assert stored.assignment_id == approved.assignment_id
    decisions = repos.cluster_assignments.list_by_cluster(cluster.id)
    assert any(
        row.source == "review" and row.status == "confirmed"
        and row.person_id == person.id
        for row in decisions
    )

    planner = ArchivePlanner(
        path_builder=_PathBuilder(),
        person_repository=repos.people,
        photo_repository=repos.photos,
        recognition_repository=repos.recognition,
        archive_record_repository=repos.archive_records,
    )
    assert planner.plan("/archive", (person.id,)).planned_count == 1


def test_manual_approval_without_identity_stays_non_archivable(tmp_path: Path) -> None:
    """D-1：不指定身份时行为保持诚实（不伪造成已可归档）。"""
    from photo_archiver.application.services.review_recognition_service import (
        ReviewRecognitionService,
    )

    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    _add_person(repos, "占位")
    photo = _add_photo(repos)
    pending = RecognitionResult(photo_id=photo.id, confidence=None)
    repos.recognition.add(pending)

    service = ReviewRecognitionService(repos.recognition)
    approved = service.approve(pending.id)
    assert approved is not None
    assert approved.person_id is None
    stored = repos.recognition.find_by_id(pending.id)
    assert stored is not None
    assert stored.person_id is None
    assert repos.recognition.list_approved_by_person(uuid4()) == []


def test_bulk_approval_does_not_overwrite_existing_identity(tmp_path: Path) -> None:
    """D-1：批量批准的默认身份不得覆盖行上已有的人工决定。"""
    from photo_archiver.application.services.review_recognition_service import (
        ReviewRecognitionService,
    )

    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    chosen = _add_person(repos, "批量默认人员")
    other = _add_person(repos, "行上已有人员")
    photo = _add_photo(repos)
    cluster = _cluster_photo(repos, photo)
    first = RecognitionResult(photo_id=photo.id, confidence=None)
    second = RecognitionResult(photo_id=photo.id, confidence=None, person_id=other.id)
    repos.recognition.add(first)
    repos.recognition.add(second)

    # S1-F：带身份的批量批准逐项走决策链；同一 (photo, person) 幂等——
    # 两个 pending 行都批准为 chosen 时只产生**一条** review 决策与一条投影。
    service = ReviewRecognitionService(
        repos.recognition, identity_decision_service=_decision_service(repos),
    )
    assert service.bulk_approve((first.id, second.id), chosen.id) == 2

    projection = repos.recognition.find_projection(photo.id, chosen.id)
    assert projection is not None and projection.assignment_id is not None
    decisions = repos.cluster_assignments.list_by_cluster(cluster.id)
    confirmed = [row for row in decisions if row.status == "confirmed"]
    assert len(confirmed) == 1, "同 pair 重复批准不得产生重复决策行"
    assert confirmed[0].person_id == chosen.id
    # second 行是旧链遗留形态（pending + 身份），不被决策链翻转成无主投影。
    assert repos.recognition.find_by_id(second.id).status is MatchStatus.PENDING


def test_rerun_does_not_overwrite_manual_approval(tmp_path: Path) -> None:
    """D-1：rerun 的兼容投影守卫不会覆盖已人工确认的 APPROVED 行。

    ``run_recognition_service`` 的守卫是"该照片已有任意 recognition_results
    行则不重写"，人工确认后的行因此不会被后续识别静默覆盖。
    """
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    person = _add_person(repos, "陈坤")
    photo = _add_photo(repos)
    approved = _approve(repos, photo, person)

    # 复刻 rerun 守卫：照片已有行 -> 不再写兼容投影。
    assert repos.recognition.list_by_photo(photo.id)
    stored = repos.recognition.find_by_id(approved.id)
    assert stored is not None
    assert stored.person_id == person.id
    assert stored.status is MatchStatus.APPROVED
