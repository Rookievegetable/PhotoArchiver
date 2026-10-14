"""S1 Phase C/E：Assignment 支撑 Projection 的生命周期（真实 SQLite）。

覆盖 S1 v5 设计的情景矩阵 C1–C5 与 rebuild 幂等。全部使用**新造**数据，
不复用任何生产库存量行（472 条 legacy pending 不参与本文件断言）。

设计要点（S0 冻结，不可弱化）：

- INV-1：当前身份 = 最新一条决策事件（与 status 无关地先取最新）
- INV-2：投影存在性 = ``active_supports(photo, person)`` 非空
- INV-4：legacy 人工决策不被 machine 活动触碰
- S0-5：同照片多观测可落同一簇 → 投影按 **photo** 去重
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.services.projection_reconciler import (
    ProjectionReconciler,
)
from photo_archiver.domain.entities import (
    ClusterPersonAssignment,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    FaceObservation,
    Person,
    Photo,
    RecognitionResult,
    RecognitionRun,
)
from photo_archiver.domain.entities.cluster_assignment import HUMAN_ACTOR
from photo_archiver.domain.entities.recognition import MatchStatus
from photo_archiver.domain.exceptions import ManualDecisionProtectedError
from photo_archiver.domain.value_objects import (
    FaceBox,
    FaceEmbedding,
    PhotoPath,
    PhotoPathBase,
)

_ORTHO = {
    "a": (1.0, 0.0),
    "b": (0.0, 1.0),
    "c": (0.0, 0.0, 1.0),
    "d": (0.0, 0.0, 0.0, 1.0),
}


class _World:
    """Minimal real-SQLite world: photos → observations → clusters → assignments."""

    def __init__(self, tmp_path: Path) -> None:
        self.repos = build_sqlite_repositories(tmp_path / "s1.db")
        self.reconciler = ProjectionReconciler(
            recognition_repository=self.repos.recognition,
            assignment_repository=self.repos.cluster_assignments,
            cluster_repository=self.repos.face_clusters,
            observation_repository=self.repos.face_observations,
        )
        self.run = RecognitionRun()
        self.repos.recognition_runs.add_run(self.run)
        self.cluster_run = FaceClusterRun(
            recognition_run_id=self.run.id, algorithm_version="s1-test",
        )
        self.repos.face_clusters.add_cluster_run(self.cluster_run)
        self._ordinal = 0

    def person(self, name: str) -> Person:
        person = Person(name=name)
        self.repos.people.add(person)
        return person

    def photo(self, stem: str) -> Photo:
        path = Path(self.repos._connection_provider.database_path).parent / f"{stem}.jpg"
        path.write_bytes(b"x")
        photo = Photo(path=PhotoPath(path, PhotoPathBase.ABSOLUTE))
        self.repos.photos.add(photo)
        return photo

    def cluster(self, faces: list[tuple[Photo, str]]) -> FaceCluster:
        """Create one cluster whose members are ``(photo, orthogonal key)`` pairs.

        ``face_index`` is unique per (run, photo) — a re-run of the same photo
        produces new observations but must not collide with the existing ones, so
        the face ordinal is allocated per photo across clusters.
        """
        cluster = FaceCluster(
            cluster_run_id=self.cluster_run.id,
            run_id=self.run.id,
            ordinal=self._ordinal,
            member_count=len(faces),
            sort_key=f"k{self._ordinal:02d}",
        )
        self._ordinal += 1
        self.repos.face_clusters.add_clusters([cluster])
        members = []
        for photo, key in faces:
            index = self._next_face_index(photo.id)
            observation = FaceObservation(
                run_id=self.run.id,
                photo_id=photo.id,
                face_index=index,
                photo_face_count=index + 1,
                det_score=0.9,
                box=FaceBox(index * 20, 0, index * 20 + 10, 10),
                embedding=FaceEmbedding(_ORTHO[key]),
                scope_verdict="in_selected_scope",
            )
            self.repos.face_observations.add_many([observation])
            members.append(
                FaceClusterMember(cluster_id=cluster.id, observation_id=observation.id)
            )
        self.repos.face_clusters.add_members(members)
        return cluster

    def _next_face_index(self, photo_id: UUID) -> int:
        """Allocate the next face ordinal for one photo within this run."""
        used = {
            observation.face_index
            for observation in self.repos.face_observations.list_by_photo(photo_id)
        }
        index = 0
        while index in used:
            index += 1
        return index

    def confirm(self, cluster: FaceCluster, person: Person,
                *, created_at=None, confirmed_at=None) -> ClusterPersonAssignment:
        """Install a *confirmed* decision — the only archive-eligible support.

        AUD-033-F2：可选显式注入 ``created_at``/``confirmed_at``（确定化时间序
        用，须严格递增；缺省保持真实时钟行为，其他调用点不受影响）。时间戳在
        持久化前写入实体，经正常仓储链保存。
        """
        assignment = ClusterPersonAssignment(
            cluster_id=cluster.id, person_id=person.id, source="manual",
            created_at=created_at,
        )
        assignment.confirm()
        if confirmed_at is not None:
            assignment.confirmed_at = confirmed_at
        self.repos.cluster_assignments.add_assignments([assignment])
        return assignment

    def suggest(self, cluster: FaceCluster, person: Person) -> ClusterPersonAssignment:
        assignment = ClusterPersonAssignment(
            cluster_id=cluster.id, person_id=person.id, source="ordered_suggestion",
        )
        self.repos.cluster_assignments.add_assignments([assignment])
        return assignment

    def retire(self, assignment: ClusterPersonAssignment) -> None:
        assignment.unassign()
        assert self.repos.cluster_assignments.update_assignment(assignment) == 1

    def legacy_approved(self, photo: Photo, person: Person) -> RecognitionResult:
        """A D-1 style manual approval row: no Assignment backs it."""
        row = RecognitionResult(
            photo_id=photo.id, person_id=person.id, confidence=None,
            status=MatchStatus.APPROVED,
        )
        self.repos.recognition.add(row)
        return row


# ── C1 / C2：多 Assignment 支撑同一 (photo, person) ─────────────────────────


def test_c1_retargets_to_remaining_support_instead_of_deleting(tmp_path: Path) -> None:
    """C1：A + B 同时支撑 (P,X)，owner=A；A 终态化后投影**保留**并改指 B。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster_a = world.cluster([(photo, "a")])
    cluster_b = world.cluster([(photo, "b")])
    # AUD-033-F2（C1）：显式确定化两次确认的时间序（双时间字段严格递增，消除
    # 同刻 UUID 字典序决胜歧义；模式与 C3 一致）。时间戳在持久化前写入实体，
    # 经正常仓储链保存。
    confirm_base = datetime(2026, 1, 1, 8, 0, 0)
    assignment_a = world.confirm(
        cluster_a, person,
        created_at=confirm_base, confirmed_at=confirm_base)
    assignment_b = world.confirm(
        cluster_b, person,
        created_at=confirm_base + timedelta(seconds=1),
        confirmed_at=confirm_base + timedelta(seconds=1))
    # 最小时间序断言：第二条决策的两个时间字段均严格大于第一条（经真实仓储
    # 读回，验证持久化值而非内存对象）。
    first_persisted = world.repos.cluster_assignments.get_assignment(assignment_a.id)
    second_persisted = world.repos.cluster_assignments.get_assignment(assignment_b.id)
    assert second_persisted.created_at > first_persisted.created_at
    assert second_persisted.confirmed_at > first_persisted.confirmed_at

    assert len(world.reconciler.active_supports(photo.id, person.id)) == 2
    outcome = world.reconciler.reconcile_pair(photo.id, person.id)
    assert outcome.action == "created"

    projection = world.repos.recognition.find_projection(photo.id, person.id)
    assert projection is not None
    assert projection.assignment_id == assignment_a.id  #最早确认者胜出

    world.retire(assignment_a)
    outcome = world.reconciler.reconcile_pair(photo.id, person.id)
    projection = world.repos.recognition.find_projection(photo.id, person.id)

    assert outcome.action in {"unchanged", "retargeted"}
    assert projection is not None, "撤掉一个支撑不得删除投影"
    assert projection.status is MatchStatus.APPROVED
    assert projection.assignment_id == assignment_b.id


def test_c2_terminates_only_when_last_support_is_gone(tmp_path: Path) -> None:
    """C2：最后一个 supporting Assignment 失效后投影才终结（转 rejected，不 DELETE）。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster_a = world.cluster([(photo, "a")])
    cluster_b = world.cluster([(photo, "b")])
    assignment_a = world.confirm(cluster_a, person)
    assignment_b = world.confirm(cluster_b, person)
    world.reconciler.reconcile_pair(photo.id, person.id)
    original_id = world.repos.recognition.find_projection(photo.id, person.id).id

    world.retire(assignment_a)
    world.reconciler.reconcile_pair(photo.id, person.id)
    assert world.repos.recognition.find_projection(photo.id, person.id) is not None

    world.retire(assignment_b)
    outcome = world.reconciler.reconcile_pair(photo.id, person.id)
    assert outcome.action == "terminated"

    surviving = [
        row for row in world.repos.recognition.list_by_photo(photo.id)
        if row.id == original_id
    ]
    assert surviving, "终结必须是转 rejected，不得物理删除（审计痕迹）"
    assert surviving[0].status is MatchStatus.REJECTED


# ── C3：跨聚类代际的支撑 ──────────────────────────────────────────────────


def test_c3_cross_run_retraction_keeps_projection(tmp_path: Path) -> None:
    """C3：Run1 / Run2 各产生一个 Assignment 支撑同一 pair；撤 Run1 后投影仍在。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster_run_2 = FaceClusterRun(
        recognition_run_id=world.run.id, algorithm_version="s1-test-gen2",
    )
    world.repos.face_clusters.add_cluster_run(cluster_run_2)
    cluster_1 = world.cluster([(photo, "a")])
    cluster_2 = FaceCluster(
        cluster_run_id=cluster_run_2.id, run_id=world.run.id, ordinal=9,
        member_count=1, sort_key="gen2",
    )
    world.repos.face_clusters.add_clusters([cluster_2])
    index = world._next_face_index(photo.id)
    observation = FaceObservation(
        run_id=world.run.id, photo_id=photo.id, face_index=index,
        photo_face_count=index + 1, det_score=0.9,
        box=FaceBox(index * 20, 0, index * 20 + 10, 10),
        embedding=FaceEmbedding(_ORTHO["c"]),
        scope_verdict="in_selected_scope",
    )
    world.repos.face_observations.add_many([observation])
    world.repos.face_clusters.add_members(
        [FaceClusterMember(cluster_id=cluster_2.id, observation_id=observation.id)]
    )

    # AUD-033-F2：显式确定化两次确认的时间序（双时间字段严格递增，消除同刻
    # UUID 字典序决胜歧义）。时间戳在持久化前写入实体，经正常仓储链保存。
    confirm_base = datetime(2026, 1, 1, 8, 0, 0)
    assignment_1 = world.confirm(
        cluster_1, person,
        created_at=confirm_base, confirmed_at=confirm_base)
    assignment_2 = world.confirm(
        cluster_2, person,
        created_at=confirm_base + timedelta(seconds=1),
        confirmed_at=confirm_base + timedelta(seconds=1))
    # 最小时间序断言：第二条决策的两个时间字段均严格大于第一条（经真实仓储
    # 读回，验证持久化值而非内存对象）。
    first_persisted = world.repos.cluster_assignments.get_assignment(assignment_1.id)
    second_persisted = world.repos.cluster_assignments.get_assignment(assignment_2.id)
    assert second_persisted.created_at > first_persisted.created_at
    assert second_persisted.confirmed_at > first_persisted.confirmed_at
    world.reconciler.reconcile_pair(photo.id, person.id)
    assert len(world.repos.recognition.list_projections_of_assignment(assignment_1.id)) == 1

    world.retire(assignment_1)
    outcome = world.reconciler.reconcile_pair(photo.id, person.id)

    projection = world.repos.recognition.find_projection(photo.id, person.id)
    assert projection is not None, "跨 Run 撤回不得删除仍被 Run2 支撑的投影"
    assert projection.status is MatchStatus.APPROVED
    assert projection.assignment_id == assignment_2.id
    assert outcome.action in {"unchanged", "retargeted"}


# ── C4：一个 Assignment 覆盖多张照片 ───────────────────────────────────────


def test_c4_one_assignment_many_photos_does_not_cross_photos(tmp_path: Path) -> None:
    """C4：一个 Assignment 跨两张照片 → 两条投影；定位必须带 photo 粒度。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo_1 = world.photo("P1")
    photo_2 = world.photo("P2")
    cluster = world.cluster([(photo_1, "a"), (photo_2, "b")])
    assignment = world.confirm(cluster, person)

    assert len(world.reconciler.photos_of_cluster(cluster)) == 2
    world.reconciler.reconcile_cluster(cluster)

    projection_1 = world.repos.recognition.find_projection(photo_1.id, person.id)
    projection_2 = world.repos.recognition.find_projection(photo_2.id, person.id)
    assert projection_1 is not None and projection_2 is not None
    assert projection_1.id != projection_2.id
    # 单行查询会返回 2 行——这正是禁止 find_projection_by_assignment 的原因。
    assert len(world.repos.recognition.list_projections_of_assignment(assignment.id)) == 2


# ── C4b：同照片多观测落同一簇（S0-5）→ 照片级去重 ──────────────────────────


def test_c4b_multi_face_same_cluster_yields_one_projection(tmp_path: Path) -> None:
    """S0-5：一张照片的两张脸落进同一簇 → 只产生一条投影（按 photo 去重）。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([(photo, "a"), (photo, "b")])
    world.confirm(cluster, person)

    assert len(world.reconciler.photos_of_cluster(cluster)) == 1
    world.reconciler.reconcile_cluster(cluster)
    assert len(world.repos.recognition.list_by_photo(photo.id)) == 1


# ── C5：legacy 与 projection 共存 ──────────────────────────────────────────


def test_c5_legacy_and_projection_coexist_and_both_archive(tmp_path: Path) -> None:
    """C5：legacy(P,张三) 与 projection(P,李四) 并存——重建不动legacy，归档各一份。"""
    from photo_archiver.application.services.archive_path_builder_service import (
        ArchivePathBuilderService,
    )
    from photo_archiver.application.services.archive_planner import ArchivePlanner

    world = _World(tmp_path)
    zhang = world.person("张三")
    li = world.person("李四")
    photo = world.photo("P1")
    world.legacy_approved(photo, zhang)

    cluster = world.cluster([(photo, "a")])
    world.confirm(cluster, li)
    world.reconciler.reconcile_pair(photo.id, li.id)

    rows = world.repos.recognition.list_by_photo(photo.id)
    assert len(rows) == 2
    legacy_rows = [r for r in rows if r.assignment_id is None]
    projection_rows = [r for r in rows if r.assignment_id is not None]
    assert len(legacy_rows) == 1 and len(projection_rows) == 1

    plan = ArchivePlanner(
        person_repository=world.repos.people,
        photo_repository=world.repos.photos,
        recognition_repository=world.repos.recognition,
        archive_record_repository=world.repos.archive_records,
        path_builder=ArchivePathBuilderService(),
    ).plan(str(tmp_path / "archive"), (zhang.id, li.id))
    assert plan.planned_count == 2
    assert {item.person_name for item in plan.items} == {"张三", "李四"}


def test_c5b_rebuild_never_touches_legacy_rows(tmp_path: Path) -> None:
    """AC-1：rebuild 前后 legacy 与 pending 集合完全不变。"""
    world = _World(tmp_path)
    zhang = world.person("张三")
    photo = world.photo("P1")
    world.legacy_approved(photo, zhang)

    pending = RecognitionResult(photo_id=photo.id, confidence=None)
    world.repos.recognition.add(pending)

    def snapshot() -> tuple[list[UUID], list[UUID], int]:
        approved = world.repos.recognition.list_all_approved()
        legacy = sorted(r.id for r in approved if r.assignment_id is None)
        pending_ids = sorted(r.id for r in world.repos.recognition.list_pending())
        return legacy, pending_ids, world.repos.recognition.read_workspace_counts().pending_review_count

    before = snapshot()
    report = world.reconciler.rebuild_all()
    after = snapshot()

    assert report.legacy_preserved == 1
    assert before == after, "rebuild 不得修改 legacy 或 pending"


# ── Phase E：rebuild 与增量语义一致 + 幂等 ─────────────────────────────────


def test_rebuild_is_idempotent_and_matches_incremental(tmp_path: Path) -> None:
    """AC-9：rebuild 复用 reconcile_pair，重复执行结果一致。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([(photo, "a")])
    world.confirm(cluster, person)

    first = world.reconciler.rebuild_all()
    assert first.created == 1

    second = world.reconciler.rebuild_all()
    assert second.created == 0
    assert second.terminated == 0
    assert world.repos.recognition.find_projection(photo.id, person.id) is not None


def test_rebuild_terminates_orphan_projection(tmp_path: Path) -> None:
    """支撑全部消失后，rebuild 终结（而非保留）该投影。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([(photo, "a")])
    assignment = world.confirm(cluster, person)
    world.reconciler.reconcile_pair(photo.id, person.id)

    world.retire(assignment)
    report = world.reconciler.rebuild_all()

    assert report.terminated == 1
    assert world.repos.recognition.find_projection(photo.id, person.id) is None


# ── INV-1：最新决策与终态 ─────────────────────────────────────────────────


def test_latest_decision_ignores_status_and_prevents_reactivation(tmp_path: Path) -> None:
    """S0 INV-1：confirmed → unassigned 后当前身份是「无人」，旧 confirmed 不复活。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([(photo, "a")])
    assignment = world.confirm(cluster, person)
    world.reconciler.reconcile_pair(photo.id, person.id)
    assert world.repos.recognition.find_projection(photo.id, person.id) is not None

    world.retire(assignment)

    latest = world.repos.cluster_assignments.list_latest_decision(cluster.id)
    assert latest is not None
    assert latest.status == "unassigned", "最新决策必须是终态行，而非旧的 confirmed"
    assert world.reconciler.active_supports(photo.id, person.id) == ()
    world.reconciler.reconcile_pair(photo.id, person.id)
    assert world.repos.recognition.find_projection(photo.id, person.id) is None


def test_suggested_decision_does_not_support_a_projection(tmp_path: Path) -> None:
    """机器建议（suggested）不得产生可归档投影——基线 CORE-05 / BA-01。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([(photo, "a")])
    world.suggest(cluster, person)

    assert world.reconciler.active_supports(photo.id, person.id) == ()
    assert world.reconciler.reconcile_pair(photo.id, person.id).action == "noop"
    assert world.repos.recognition.find_projection(photo.id, person.id) is None


# ── 查询粒度：禁止按 assignment_id 单行定位 ───────────────────────────────


def test_find_projection_is_scoped_by_photo_and_person(tmp_path: Path) -> None:
    """S1 §R5：投影查询必须带 (photo, person) 粒度，不得只按 assignment_id。"""
    world = _World(tmp_path)
    person_a = world.person("张三")
    person_b = world.person("李四")
    photo_1 = world.photo("P1")
    photo_2 = world.photo("P2")
    cluster = world.cluster([(photo_1, "a"), (photo_2, "b")])
    world.confirm(cluster, person_a)
    world.reconciler.reconcile_cluster(cluster)

    # 同 person 两照片：find_projection 各自命中不同行。
    projection_1 = world.repos.recognition.find_projection(photo_1.id, person_a.id)
    projection_2 = world.repos.recognition.find_projection(photo_2.id, person_a.id)
    assert projection_1.id != projection_2.id
    # 别人的身份不会串到该pair 上。
    assert world.repos.recognition.find_projection(photo_1.id, person_b.id) is None


@pytest.mark.parametrize("photo_stem", ["P1"])
def test_create_projection_reuses_pending_row(tmp_path: Path, photo_stem: str) -> None:
    """S1 D-3：pending 占位行被就地复用，不产生第二条行、不遗留 pending。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo(photo_stem)
    world.repos.recognition.add(
        RecognitionResult(photo_id=photo.id, confidence=None)
    )
    assert world.repos.recognition.read_workspace_counts().pending_review_count == 1

    cluster = world.cluster([(photo, "a")])
    world.confirm(cluster, person)
    world.reconciler.reconcile_pair(photo.id, person.id)

    rows = world.repos.recognition.list_by_photo(photo.id)
    assert len(rows) == 1
    assert rows[0].status is MatchStatus.APPROVED
    assert rows[0].assignment_id is not None
    assert world.repos.recognition.read_workspace_counts().pending_review_count == 0

# ── P0-5：manual finality 的 mutation 层守卫 ────────────────────────────────


def test_machine_actor_cannot_unassign_manual_assignment(tmp_path: Path) -> None:
    """S0 INV-4：机器 actor 解除 manual 决策必须在 mutation 层被拒。"""
    from photo_archiver.application.commands.pairing import UnassignClusterCommand
    from photo_archiver.domain import ManualDecisionProtectedError

    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([(photo, "a")])
    world.confirm(cluster, person)  # source="manual"

    with pytest.raises(ManualDecisionProtectedError, match="human-final"):
        world.repos  # noqa: B018 - readability: service built below from repos
        from photo_archiver.application.services.pairing_workbench_service import (
            PairingWorkbenchService,
        )
        workbench = PairingWorkbenchService(
            world.repos.cluster_assignments,
            world.repos.face_clusters,
            world.repos.face_observations,
            world.repos.people,
            world.repos.recognition,
            world.repos.person_face_samples,
            reconciler=world.reconciler,
        )
        workbench.unassign(UnassignClusterCommand(cluster.id), actor="auto_rerun")

    latest = world.repos.cluster_assignments.list_latest_decision(cluster.id)
    assert latest is not None and latest.status == "confirmed", (
        "被拒的守卫不得改动决策历史"
    )


def test_machine_actor_can_retire_own_machine_sourced_assignment(tmp_path: Path) -> None:
    """机器→机器 允许：machine actor 可终态化机器来源（ordered_suggestion）的行。"""
    from photo_archiver.application.commands.pairing import UnassignClusterCommand
    from photo_archiver.application.services.pairing_workbench_service import (
        PairingWorkbenchService,
    )

    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([(photo, "a")])
    world.suggest(cluster, person)  # source="ordered_suggestion"

    workbench = PairingWorkbenchService(
        world.repos.cluster_assignments,
        world.repos.face_clusters,
        world.repos.face_observations,
        world.repos.people,
        world.repos.recognition,
        world.repos.person_face_samples,
        reconciler=world.reconciler,
    )
    result = workbench.unassign(UnassignClusterCommand(cluster.id), actor="auto_rerun")
    assert result.status == "unassigned"


def test_machine_actor_cannot_reassign_away_manual_assignment(tmp_path: Path) -> None:
    """改派会终态化现行——machine actor 遇 manual 现行同样必须被拒。"""
    from photo_archiver.application.commands.pairing import AssignClusterPersonCommand
    from photo_archiver.domain import ManualDecisionProtectedError
    from photo_archiver.application.services.pairing_workbench_service import (
        PairingWorkbenchService,
    )

    world = _World(tmp_path)
    zhang = world.person("张三")
    li = world.person("李四")
    photo = world.photo("P1")
    cluster = world.cluster([(photo, "a")])
    world.confirm(cluster, zhang)

    workbench = PairingWorkbenchService(
        world.repos.cluster_assignments,
        world.repos.face_clusters,
        world.repos.face_observations,
        world.repos.people,
        world.repos.recognition,
        world.repos.person_face_samples,
        reconciler=world.reconciler,
    )
    with pytest.raises(ManualDecisionProtectedError, match="human-final"):
        workbench.assign_person(
            AssignClusterPersonCommand(cluster_id=cluster.id, person_id=li.id),
            actor="auto_rerun",
        )

    latest = world.repos.cluster_assignments.list_latest_decision(cluster.id)
    assert latest is not None and latest.person_id == zhang.id, (
        "被拒的改派不得改动决策历史"
    )


def test_human_actor_still_reassigns_manual_assignment(tmp_path: Path) -> None:
    """人工再修改不受限（INV-4 允许的唯一覆盖路径）——既有行为保持。"""
    from photo_archiver.application.commands.pairing import AssignClusterPersonCommand
    from photo_archiver.application.services.pairing_workbench_service import (
        PairingWorkbenchService,
    )

    world = _World(tmp_path)
    zhang = world.person("张三")
    li = world.person("李四")
    photo = world.photo("P1")
    cluster = world.cluster([(photo, "a")])
    world.confirm(cluster, zhang)

    workbench = PairingWorkbenchService(
        world.repos.cluster_assignments,
        world.repos.face_clusters,
        world.repos.face_observations,
        world.repos.people,
        world.repos.recognition,
        world.repos.person_face_samples,
        reconciler=world.reconciler,
    )
    result = workbench.assign_person(
        AssignClusterPersonCommand(cluster_id=cluster.id, person_id=li.id),
        actor=HUMAN_ACTOR,
    )
    assert result.status == "confirmed"
    latest = world.repos.cluster_assignments.list_latest_decision(cluster.id)
    assert latest is not None and latest.person_id == li.id


# ── Actor 边界（S0 INV-4）：fail-closed 而非 fail-open ─────────────────────────


def _workbench(world):
    from photo_archiver.application.services.pairing_workbench_service import (
        PairingWorkbenchService,
    )

    return PairingWorkbenchService(
        world.repos.cluster_assignments,
        world.repos.face_clusters,
        world.repos.face_observations,
        world.repos.people,
        world.repos.recognition,
        world.repos.person_face_samples,
        reconciler=world.reconciler,
    )


def test_machine_actor_cannot_retract_confirmed_row(tmp_path: Path) -> None:
    """规则1：machine retract confirmed → reject（无论 source）。"""
    from photo_archiver.application.commands.pairing import UnassignClusterCommand
    from photo_archiver.domain.entities.cluster_assignment import MACHINE_ACTOR

    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([(photo, "a")])
    world.confirm(cluster, person)  # confirmed + manual

    with pytest.raises(ManualDecisionProtectedError):
        _workbench(world).unassign(
            UnassignClusterCommand(cluster.id), actor=MACHINE_ACTOR
        )
    latest = world.repos.cluster_assignments.list_latest_decision(cluster.id)
    assert latest.status == "confirmed"


def test_machine_actor_can_retract_own_suggested_row(tmp_path: Path) -> None:
    """规则2：machine retract suggested → allowed（机器可撤回自己的建议）。"""
    from photo_archiver.application.commands.pairing import UnassignClusterCommand
    from photo_archiver.domain.entities.cluster_assignment import MACHINE_ACTOR

    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([(photo, "a")])
    world.suggest(cluster, person)  # suggested + ordered_suggestion

    result = _workbench(world).unassign(
        UnassignClusterCommand(cluster.id), actor=MACHINE_ACTOR
    )
    assert result.status == "unassigned"


def test_machine_actor_cannot_retarget_confirmed_row(tmp_path: Path) -> None:
    """规则3：machine retarget confirmed → reject（改派是人工专属）。"""
    from photo_archiver.application.commands.pairing import (
        AssignClusterPersonCommand,
    )
    from photo_archiver.domain.entities.cluster_assignment import MACHINE_ACTOR

    world = _World(tmp_path)
    zhang = world.person("张三")
    li = world.person("李四")
    photo = world.photo("P1")
    cluster = world.cluster([(photo, "a")])
    world.confirm(cluster, zhang)

    with pytest.raises(ManualDecisionProtectedError):
        _workbench(world).assign_person(
            AssignClusterPersonCommand(cluster_id=cluster.id, person_id=li.id),
            actor=MACHINE_ACTOR,
        )
    latest = world.repos.cluster_assignments.list_latest_decision(cluster.id)
    assert latest.person_id == zhang.id


def test_human_actor_can_retarget_confirmed_row(tmp_path: Path) -> None:
    """规则4：human retarget confirmed → allowed（人工再修改是唯一覆盖路径）。"""
    from photo_archiver.application.commands.pairing import (
        AssignClusterPersonCommand,
    )
    from photo_archiver.domain.entities.cluster_assignment import HUMAN_ACTOR

    world = _World(tmp_path)
    zhang = world.person("张三")
    li = world.person("李四")
    photo = world.photo("P1")
    cluster = world.cluster([(photo, "a")])
    world.confirm(cluster, zhang)

    result = _workbench(world).assign_person(
        AssignClusterPersonCommand(cluster_id=cluster.id, person_id=li.id),
        actor=HUMAN_ACTOR,
    )
    assert result.status == "confirmed"
    latest = world.repos.cluster_assignments.list_latest_decision(cluster.id)
    assert latest.person_id == li.id


def test_unknown_actor_is_treated_as_machine(tmp_path: Path) -> None:
    """fail-closed：拼错/未登记的 actor 一律按机器处理，不得获得人工权限。"""
    from photo_archiver.application.commands.pairing import UnassignClusterCommand

    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([(photo, "a")])
    world.confirm(cluster, person)

    for bogus_actor in ("autoconfirm", "AutoRerun", "", "system", "HUMAN"):
        with pytest.raises(ManualDecisionProtectedError):
            _workbench(world).unassign(
                UnassignClusterCommand(cluster.id), actor=bogus_actor
            )
    latest = world.repos.cluster_assignments.list_latest_decision(cluster.id)
    assert latest.status == "confirmed"


def test_machine_actor_constant_is_distinct_from_human(tmp_path: Path) -> None:
    """``MACHINE_ACTOR`` 存在且与 ``HUMAN_ACTOR`` 不同——S4 机器入口的书写契约。"""
    from photo_archiver.domain.entities.cluster_assignment import (
        HUMAN_ACTOR,
        MACHINE_ACTOR,
    )

    assert MACHINE_ACTOR != HUMAN_ACTOR
    assert MACHINE_ACTOR  # 非空
