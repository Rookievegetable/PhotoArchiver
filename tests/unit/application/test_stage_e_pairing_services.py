"""Stage E application tests — suggestion generation + confirm/reject chain.

End-to-end over InMemory repositories with the real numpy kernel: cluster
data seeded like Stage D would produce, then suggestions generated, then
the identity decisions closed (confirm → samples + D3 compat results).
"""

import math
from datetime import datetime
from uuid import uuid4

import pytest

from photo_archiver.application.commands.pairing import (
    AssignClusterPersonCommand,
    ConfirmAssignmentCommand,
    RejectAssignmentCommand,
    SetClusterStateCommand,
    StartSuggestPairingsCommand,
    UnassignClusterCommand,
)
from photo_archiver.application.services import (
    ClusterResultsService,
    ListPersonsService,
    PairingWorkbenchService,
    SuggestPairingsService,
)
from photo_archiver.domain import (
    ClusterPersonAssignment,
    FaceBox,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    FaceEmbedding,
    FaceObservation,
    MatchStatus,
    Person,
    RecognitionRun,
    RunPhotoSnapshot,
    ValidationError,
)
from photo_archiver.infrastructure import (
    InMemoryClusterPersonAssignmentRepository,
    InMemoryFaceClusterRepository,
    InMemoryFaceObservationRepository,
    InMemoryPersonFaceSampleRepository,
    NumpyCosineSimilarityFactory,
)


class _RunRepoWithPhotos(InMemoryFaceClusterRepository):
    """Cluster run repo + recognition runs/photos via side channels."""

    def __init__(self):
        super().__init__()
        self._recognition_runs: dict = {}
        self._run_photos: dict = {}

    def add_recognition_run(self, run):
        self._recognition_runs[run.id] = run

    def get_run(self, run_id):
        return self._recognition_runs.get(run_id)

    def list_runs(self):
        return sorted(self._recognition_runs.values(),
                      key=lambda r: (r.created_at or r.id, str(r.id)), reverse=True)

    def add_run_photos(self, run_id, snapshots):
        self._run_photos.setdefault(run_id, []).extend(snapshots)

    def list_run_photos(self, run_id):
        return list(self._run_photos.get(run_id, []))


class _Harness:
    """One recognition run → one cluster generation with two person groups."""

    def __init__(self):
        self.clusters = _RunRepoWithPhotos()
        self.observations = InMemoryFaceObservationRepository()
        self.assignments = InMemoryClusterPersonAssignmentRepository(
            cluster_scope=self.clusters.list_clusters,
        )
        self.samples = InMemoryPersonFaceSampleRepository()
        self.persons = {}
        self.photo_ids: dict[str, object] = {}

        run = RecognitionRun(parameters={})
        self.clusters.add_recognition_run(run)
        self.recognition_run = run
        for key, path in (("a", "photos/a.jpg"), ("b", "photos/b.jpg")):
            from photo_archiver.domain import Photo, PhotoPath
            photo = Photo(path=PhotoPath(path))
            # PhotoRepository is not part of this harness — observations carry
            # the photo id directly and the compat path is asserted separately.
            self.photo_ids[key] = uuid4() if photo.id is None else photo.id
        self.runs = self.clusters

    def add_person(self, name: str, roster_order: int | None):
        person = Person(name=name, roster_order=roster_order)
        self.persons[person.id] = person
        return person

    def add_photo_snapshot(self, photo_id, path):
        self.clusters.add_run_photos(self.recognition_run.id, [
            RunPhotoSnapshot(self.recognition_run.id, photo_id, path, None),
        ])

    def add_observation(self, photo_id, index, angle, quality=0.9):
        radians = math.radians(angle)
        observation = FaceObservation(
            run_id=self.recognition_run.id,
            photo_id=photo_id,
            face_index=index,
            photo_face_count=index + 1,
            det_score=0.9,
            box=FaceBox(index, 0, index + 10, 10),
            embedding=FaceEmbedding((math.cos(radians), math.sin(radians))),
            scope_verdict="in_selected_scope",
            quality_score=quality,
        )
        self.observations.add_many([observation])
        return observation

    def add_generation(self, member_spec):
        """member_spec: [(cluster_sort_key, [(observation, ...)])]."""
        cluster_run = FaceClusterRun(
            recognition_run_id=self.recognition_run.id, algorithm_version="v1",
        )
        self.clusters.add_cluster_run(cluster_run)
        for ordinal, (sort_key, members) in enumerate(member_spec):
            cluster = FaceCluster(
                cluster_run_id=cluster_run.id, run_id=self.recognition_run.id,
                ordinal=ordinal, member_count=len(members), sort_key=sort_key,
                first_captured_at=datetime(2026, 1, 1),
            )
            self.clusters.add_clusters([cluster])
            for member in members:
                self.clusters.add_members([
                    FaceClusterMember(cluster_id=cluster.id,
                                      observation_id=member.id),
                ])
        cluster_run.start()
        cluster_run.complete(len(member_spec), sum(len(m) for _, m in member_spec), 0)
        return cluster_run

    def build_services(self):
        suggest = SuggestPairingsService(
            self.clusters, self.observations, _PersonRepo(self.persons),
            self.assignments, self.samples, NumpyCosineSimilarityFactory(),
        )
        workbench = PairingWorkbenchService(
            self.assignments, self.clusters, self.observations,
            _PersonRepo(self.persons), _RecognitionRepoStub(),
            self.samples,
        )
        results = ClusterResultsService(
            self.clusters, self.observations, self.clusters, self.assignments,
        )
        roster = ListPersonsService(_PersonRepo(self.persons))
        return suggest, workbench, results, roster


class _PersonRepo:
    def __init__(self, persons):
        self._persons = persons

    def list_all(self):
        return sorted(self._persons.values(),
                      key=lambda p: (p.roster_order is None,
                                     p.roster_order if p.roster_order is not None else 0,
                                     str(p.id)))

    def find_by_id(self, person_id):
        return self._persons.get(person_id)


class _RecognitionRepoStub:
    """RecognitionRepository stand-in recording compat APPROVED writes."""

    def __init__(self):
        self.rows: list = []

    def add(self, result):
        self.rows.append(result)

    def list_by_photo(self, photo_id):
        return [row for row in self.rows if row.photo_id == photo_id]

    def remove_results_for_person_photos(self, person_id, photo_ids):
        targets = set(photo_ids)
        before = len(self.rows)
        self.rows = [
            row for row in self.rows
            if not (row.person_id == person_id and row.photo_id in targets
                    and row.status == MatchStatus.APPROVED)
        ]
        return before - len(self.rows)

    def list_approved_by_person(self, person_id):
        return [row for row in self.rows
                if row.person_id == person_id and row.status == MatchStatus.APPROVED]


def _angle_pair(base: float, spread: float = 6.0):
    return base, base + spread


def test_suggestion_and_confirmation_end_to_end():
    harness = _Harness()
    photo_a = uuid4()
    harness.add_photo_snapshot(photo_a, "photos/a.jpg")
    harness.add_person("张三", 1)
    harness.add_person("李四", 2)  # 第二簇需要第二名人员（一对一）
    # 两人簇（0°/6° 跨照片同人）+ 单人簇（180°）。
    o1 = harness.add_observation(photo_a, 0, 0.0)
    o2 = harness.add_observation(uuid4(), 0, 6.0)
    o3 = harness.add_observation(uuid4(), 0, 180.0)
    generation = harness.add_generation([
        ("2026-01-01T00:00:00|photos/a.jpg|000000", [o1, o2]),
        ("2026-01-01T00:00:00|photos/b.jpg|000001", [o3]),
    ])
    suggest, workbench, results, roster = harness.build_services()

    summary = suggest.execute(StartSuggestPairingsCommand(generation.id))

    # 无样本库 → 全部走顺序配对：两簇两人都拿到 suggested。
    assert summary.suggestions == 2
    assert summary.ordered == 2 and summary.sample_matched == 0
    active = results.assignments_active(generation.id)
    assert len(active) == 2
    assert all(a.status == "suggested" for a in active)

    # 确认两人簇（member_count == 2）的建议 → samples + D3 兼容 APPROVED。
    by_cluster = {
        cluster.id: cluster
        for cluster in harness.clusters.list_clusters(generation.id)
    }
    target = next(
        a for a in active if by_cluster[a.cluster_id].member_count == 2
    )
    result = workbench.confirm(ConfirmAssignmentCommand(target.id))

    assert result.status == "confirmed"
    assert result.samples_written == 2  # 两成员观测沉淀为样本
    # D3 兼容适配：簇跨两张照片 → 每照片一条 APPROVED（确认即可归档）。
    assert result.compat_results_written == 2
    samples = harness.samples.list_by_person(target.person_id)
    assert {sample.observation_id for sample in samples} == {o1.id, o2.id}
    # 确认后：该簇行 confirmed，另一簇建议不受影响（顺序无关断言）。
    active_statuses = sorted(a.status for a in results.assignments_active(generation.id))
    assert active_statuses == ["confirmed", "suggested"]


def test_confirm_requires_suggested_state():
    harness = _Harness()
    person = harness.add_person("李四", 1)
    o1 = harness.add_observation(uuid4(), 0, 0.0)
    generation = harness.add_generation([("k|a|000000", [o1])])
    _, workbench, _, _ = harness.build_services()
    assignment = ClusterPersonAssignment(
        cluster_id=generation.id, person_id=person.id,
    )
    assignment.confirm()
    harness.assignments.add_assignments([assignment])

    with pytest.raises(ValidationError, match="suggested"):
        workbench.confirm(ConfirmAssignmentCommand(assignment.id))


def test_reject_then_unassign_lifecycle():
    harness = _Harness()
    harness.add_person("王五", 1)
    o1 = harness.add_observation(uuid4(), 0, 0.0)
    generation = harness.add_generation([("k|a|000000", [o1])])
    suggest, workbench, results, _ = harness.build_services()
    suggest.execute(StartSuggestPairingsCommand(generation.id))
    assignment = results.assignments_active(generation.id)[0]

    workbench.reject(RejectAssignmentCommand(assignment.id))
    assert harness.assignments.get_assignment(assignment.id).status == "rejected"
    assert results.assignments_active(generation.id) == []  # rejected 不是有效行

    workbench.unassign(UnassignClusterCommand(assignment.cluster_id))
    # unassign 复用同一条决策行（suggested→rejected→unassigned），
    # 历史以行内状态迁移表达，不新增行。
    history = harness.assignments.list_by_cluster(assignment.cluster_id)
    assert [row.status for row in history] == ["unassigned"]


def test_manual_assignment_replaces_active_and_confirms_immediately():
    harness = _Harness()
    harness.add_person("赵六", 1)
    p2 = harness.add_person("钱七", 2)
    o1 = harness.add_observation(uuid4(), 0, 0.0)
    generation = harness.add_generation([("k|a|000000", [o1])])
    suggest, workbench, results, _ = harness.build_services()
    suggest.execute(StartSuggestPairingsCommand(generation.id))
    original = results.assignments_active(generation.id)[0]

    result = workbench.assign_person(
        AssignClusterPersonCommand(cluster_id=original.cluster_id, person_id=p2.id),
    )

    assert result.status == "confirmed"
    assert result.assignment_id != original.id
    history_statuses = sorted(
        row.status for row in harness.assignments.list_by_cluster(original.cluster_id)
    )
    assert history_statuses == ["confirmed", "unassigned"]  # 同刻创建，顺序无关
    assert harness.samples.list_by_person(p2.id)  # 人工指派同样沉淀样本


def test_mark_unknown_and_ignore_use_cluster_status_vocabulary():
    harness = _Harness()
    harness.add_person("孙八", 1)
    o1 = harness.add_observation(uuid4(), 0, 0.0)
    generation = harness.add_generation([("k|a|000000", [o1])])
    cluster = harness.clusters.list_clusters(generation.id)[0]
    _, workbench, _, _ = harness.build_services()

    workbench.set_cluster_state(SetClusterStateCommand(cluster.id, "unknown"))
    assert harness.clusters.get_cluster(cluster.id).status == "unknown"
    workbench.set_cluster_state(SetClusterStateCommand(cluster.id, "ignored"))
    assert harness.clusters.get_cluster(cluster.id).status == "ignored"
    with pytest.raises(ValidationError):
        workbench.set_cluster_state(SetClusterStateCommand(cluster.id, "confirmed"))
    # 原始成员关系不被破坏。
    assert harness.clusters.list_members(generation.id)


def test_suggestions_skip_clusters_with_active_assignment():
    harness = _Harness()
    harness.add_person("周九", 1)
    o1 = harness.add_observation(uuid4(), 0, 0.0)
    generation = harness.add_generation([("k|a|000000", [o1])])
    suggest, workbench, results, _ = harness.build_services()
    suggest.execute(StartSuggestPairingsCommand(generation.id))
    first = results.assignments_active(generation.id)[0]

    summary = suggest.execute(StartSuggestPairingsCommand(generation.id))

    assert summary.suggestions == 0  # 已有有效指派 → 幂等，不重复建议
    assert first.id == results.assignments_active(generation.id)[0].id
