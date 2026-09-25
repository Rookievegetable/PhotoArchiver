"""Stage E remediation regression tests（E-P1-1 / E-P1-2 / E-P2-1）.

owner 裁决（E-SG-6 / E-SG-5）的常驻回归：多 Person attribution、
(person, photo) 幂等、改派/解除的兼容投影回收与样本停用、
ArchivePlanner 按 (person, photo) 消费。覆盖四层：
Assignment / RecognitionResult / person_face_embeddings / ArchivePlanner。
"""

import math
from pathlib import Path
from uuid import uuid4

from photo_archiver.application.commands.pairing import (
    AssignClusterPersonCommand,
    ConfirmAssignmentCommand,
    StartSuggestPairingsCommand,
    UnassignClusterCommand,
)
from photo_archiver.application.services import (
    ClusterResultsService,
    ListPersonsService,
    PairingWorkbenchService,
    SuggestPairingsService,
)
from photo_archiver.application.services.archive_planner import ArchivePlanner
from photo_archiver.domain import (
    PhotoPathBase,
    FaceBox,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    FaceEmbedding,
    FaceObservation,
    MatchStatus,
    Person,
    Photo,
    PhotoPath,
    RecognitionRun,
    RecognitionResult,
    RunPhotoSnapshot,
)
from photo_archiver.infrastructure import (
    InMemoryClusterPersonAssignmentRepository,
    InMemoryFaceClusterRepository,
    InMemoryFaceObservationRepository,
    InMemoryPersonFaceSampleRepository,
    NumpyCosineSimilarityFactory,
)
from tests.unit.application.test_archive_planner import (
    _FakeArchivePathBuilder,
    _FakeArchiveRecordRepository,
    _FakePersonRepository,
    _FakePhotoRepository,
    _FakeRecognitionRepository,
)


class _RunRepoWithPhotos(InMemoryFaceClusterRepository):
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


class _RecognitionRepo:
    """RecognitionRepository double recording all compat writes/removals."""

    def __init__(self):
        self.rows: list[RecognitionResult] = []

    def add(self, result):
        self.rows.append(result)

    def list_by_photo(self, photo_id):
        return [row for row in self.rows if row.photo_id == photo_id]

    def list_approved_by_person(self, person_id):
        return [row for row in self.rows
                if row.person_id == person_id and row.status == MatchStatus.APPROVED]

    def remove_results_for_person_photos(self, person_id, photo_ids):
        targets = set(photo_ids)
        before = len(self.rows)
        self.rows = [
            row for row in self.rows
            if not (row.person_id == person_id and row.photo_id in targets
                    and row.status == MatchStatus.APPROVED)
        ]
        return before - len(self.rows)


class _Harness:
    """One shared photo carrying two single-face clusters + two persons."""

    def __init__(self):
        self.clusters = _RunRepoWithPhotos()
        self.observations = InMemoryFaceObservationRepository()
        self.assignments = InMemoryClusterPersonAssignmentRepository(
            cluster_scope=self.clusters.list_clusters,
        )
        self.samples = InMemoryPersonFaceSampleRepository()
        self.recognition = _RecognitionRepo()
        self.persons: list[Person] = []
        self.person_a = self._person("人物A", 1)
        self.person_b = self._person("人物B", 2)
        run = RecognitionRun(parameters={})
        self.clusters.add_recognition_run(run)
        self.recognition_run = run
        self.photo = uuid4()
        self.clusters.add_run_photos(run.id, [
            RunPhotoSnapshot(run.id, self.photo, "photos/合影.jpg", None),
        ])
        # 脸 A（0°）与脸 B（90°）→ 两个单脸簇（角度差 90° 不互聚）。
        self.o_a = self._observation(self.photo, 0, 0.0)
        self.o_b = self._observation(self.photo, 1, 90.0)
        self.generation = self._generation([
            ("k|a|000000", [self.o_a]),
            ("k|b|000001", [self.o_b]),
        ])
        self.suggest_service = SuggestPairingsService(
            self.clusters, self.observations, _PersonRepo(self.persons),
            self.assignments, self.samples, NumpyCosineSimilarityFactory(),
        )
        self.workbench = PairingWorkbenchService(
            self.assignments, self.clusters, self.observations,
            _PersonRepo(self.persons), self.recognition, self.samples,
        )
        self.results = ClusterResultsService(
            self.clusters, self.observations, self.clusters, self.assignments,
        )
        self.roster = ListPersonsService(_PersonRepo(self.persons))

    def _person(self, name, order):
        person = Person(name=name, roster_order=order)
        self.persons.append(person)
        return person

    def _observation(self, photo_id, index, angle):
        radians = math.radians(angle)
        observation = FaceObservation(
            run_id=self.recognition_run.id,
            photo_id=photo_id,
            face_index=index,
            photo_face_count=2,
            det_score=0.9,
            box=FaceBox(index, 0, index + 10, 10),
            embedding=FaceEmbedding((math.cos(radians), math.sin(radians))),
            scope_verdict="in_selected_scope",
        )
        self.observations.add_many([observation])
        return observation

    def _generation(self, member_spec):
        cluster_run = FaceClusterRun(
            recognition_run_id=self.recognition_run.id, algorithm_version="v1",
        )
        self.clusters.add_cluster_run(cluster_run)
        for ordinal, (sort_key, members) in enumerate(member_spec):
            cluster = FaceCluster(
                cluster_run_id=cluster_run.id, run_id=self.recognition_run.id,
                ordinal=ordinal, member_count=len(members), sort_key=sort_key,
            )
            self.clusters.add_clusters([cluster])
            self.clusters.add_members([
                FaceClusterMember(cluster_id=cluster.id, observation_id=o.id)
                for o in members
            ])
        cluster_run.start()
        cluster_run.complete(len(member_spec), sum(len(m) for _, m in member_spec), 0)
        return cluster_run

    def generate_suggestions(self):
        return self.suggest_service.execute(
            StartSuggestPairingsCommand(self.generation.id),
        )

    def active_for(self, cluster):
        return next(
            a for a in self.results.assignments_active(self.generation.id)
            if a.cluster_id == cluster.id
        )

    def cluster_by_ordinal(self, ordinal: int) -> FaceCluster:
        return next(
            c for c in self.clusters.list_clusters(self.generation.id)
            if c.ordinal == ordinal
        )

    def compat_for(self, person_id):
        return [
            row for row in self.recognition.rows
            if row.person_id == person_id and row.status == MatchStatus.APPROVED
        ]


class _PersonRepo:
    def __init__(self, persons):
        self._persons = persons

    def list_all(self):
        return list(self._persons)

    def find_by_id(self, person_id):
        return next((p for p in self._persons if p.id == person_id), None)


# ── E-P1-1：同照片多 Person attribution ─────────────────────────────────────


def test_case_a_double_confirm_preserves_both_identities_everywhere():
    """Case A/E：1 Photo / 2 Faces / 2 Clusters / 2 Persons → 双确认。

    Assignment：A ✅ B ✅；Compatibility：P→A ✅ P→B ✅；Samples：A ✅ B ✅。
    """
    harness = _Harness()
    harness.generate_suggestions()
    cluster_a = harness.cluster_by_ordinal(0)
    cluster_b = harness.cluster_by_ordinal(1)
    asg_a = harness.active_for(cluster_a)
    asg_b = harness.active_for(cluster_b)

    r_a = harness.workbench.confirm(ConfirmAssignmentCommand(asg_a.id))
    r_b = harness.workbench.confirm(ConfirmAssignmentCommand(asg_b.id))

    assert r_a.status == "confirmed" and r_b.status == "confirmed"
    assert r_a.compat_results_written == 1 and r_b.compat_results_written == 1
    # 兼容层：同一照片两条当前有效归属（每人一条）。
    assert len(harness.compat_for(harness.person_a.id)) == 1
    assert len(harness.compat_for(harness.person_b.id)) == 1
    # 样本库：两人各自的观测均沉淀。
    assert len(harness.samples.list_by_person(harness.person_a.id)) == 1
    assert len(harness.samples.list_by_person(harness.person_b.id)) == 1


def test_same_person_photo_pair_is_idempotent_on_repeated_confirm():
    """E-SG-6 #3：同 (person, photo) 重复确认/指派不产生重复归属。"""
    harness = _Harness()
    harness.generate_suggestions()
    cluster_a = harness.cluster_by_ordinal(0)
    asg_a = harness.active_for(cluster_a)
    harness.workbench.confirm(ConfirmAssignmentCommand(asg_a.id))
    first_rows = harness.compat_for(harness.person_a.id)

    # 解除后重新确认同一人 → 幂等（不重复写行）。
    harness.workbench.unassign(UnassignClusterCommand(cluster_a.id))
    assert harness.compat_for(harness.person_a.id) == []  # 投影已回收
    harness.workbench.assign_person(AssignClusterPersonCommand(
        cluster_id=cluster_a.id, person_id=harness.person_a.id,
    ))

    assert len(harness.compat_for(harness.person_a.id)) == len(first_rows) == 1


# ── E-P1-2：改派 / 解除的投影回收 ───────────────────────────────────────────


def test_unassign_retracts_projection_other_identity_unaffected():
    """多身份场景：P→A、P→B 撤销 A 后 P→B 仍有效（E-SG-6 #7）。"""
    harness = _Harness()
    harness.generate_suggestions()
    asg_a = harness.active_for(harness.cluster_by_ordinal(0))
    asg_b = harness.active_for(harness.cluster_by_ordinal(1))
    harness.workbench.confirm(ConfirmAssignmentCommand(asg_a.id))
    harness.workbench.confirm(ConfirmAssignmentCommand(asg_b.id))

    harness.workbench.unassign(UnassignClusterCommand(asg_a.cluster_id))

    assert harness.compat_for(harness.person_a.id) == []      # A 投影回收
    assert len(harness.compat_for(harness.person_b.id)) == 1  # B 不受影响
    assert len(harness.samples.list_by_person(harness.person_a.id)) == 1  # 历史保留
    assert all(
        not sample.enabled
        for sample in harness.samples.list_by_person(harness.person_a.id)
    )  # E-SG-5：旧样本停用
    assert any(
        sample.enabled
        for sample in harness.samples.list_by_person(harness.person_b.id)
    )


def test_reassignment_chain_a_to_b_to_c_keeps_current_identity_consistent():
    """A→B→C 连续改派：Assignment/Compatibility/Archive 三层一致。"""
    harness = _Harness()
    person_c = harness._person("人物C", 3)
    harness.generate_suggestions()
    cluster_a = harness.cluster_by_ordinal(0)
    asg_a = harness.active_for(cluster_a)
    harness.workbench.confirm(ConfirmAssignmentCommand(asg_a.id))

    harness.workbench.assign_person(AssignClusterPersonCommand(
        cluster_id=cluster_a.id, person_id=harness.person_b.id,
    ))
    assert harness.compat_for(harness.person_a.id) == []
    assert len(harness.compat_for(harness.person_b.id)) == 1

    harness.workbench.assign_person(AssignClusterPersonCommand(
        cluster_id=cluster_a.id, person_id=person_c.id,
    ))
    assert harness.compat_for(harness.person_b.id) == []
    assert len(harness.compat_for(person_c.id)) == 1
    # 主事实：当前有效行 = C；历史行保留（suggested→unassigned + manual confirmed）。
    current = harness.assignments.list_by_cluster(cluster_a.id)
    # 同刻创建行按 id 并列——顺序无关断言：1 confirmed(C) + 2 unassigned。
    assert sorted(row.status for row in current) == [
        "confirmed", "unassigned", "unassigned",
    ]
    assert next(
        row.person_id for row in current if row.status == "confirmed"
    ) == person_c.id
    # 原始 Cluster/Observation 不变：成员关系与观测仍在。
    assert harness.clusters.list_members(harness.generation.id)
    # A 的样本已停用，C 的样本有效。
    assert all(not s.enabled for s in harness.samples.list_by_person(harness.person_a.id))
    assert all(s.enabled for s in harness.samples.list_by_person(person_c.id))


def test_disabled_samples_never_enter_future_suggestions():
    """E-SG-5 #3：停用样本不参与候选建议计算。"""
    harness = _Harness()
    person_c = harness._person("人物C", 3)
    harness.generate_suggestions()
    cluster_a = harness.cluster_by_ordinal(0)
    asg_a = harness.active_for(cluster_a)
    harness.workbench.confirm(ConfirmAssignmentCommand(asg_a.id))  # 沉淀 A 样本

    # 重新聚类生成新代际（同样的脸），A 的样本已被改派停用。
    harness.workbench.assign_person(AssignClusterPersonCommand(
        cluster_id=cluster_a.id, person_id=person_c.id,
    ))
    new_generation = harness._generation([
        ("k|a2|000000", [harness.o_a]),
    ])
    harness.suggest_service.execute(StartSuggestPairingsCommand(new_generation.id))

    # 停用样本（A）不参与建议计算：新代际的样本匹配命中的是 C（有效样本）。
    sample_matched = {
        row.person_id
        for row in harness.assignments.list_active_by_cluster_run(new_generation.id)
        if row.source == "sample_match"
    }
    assert harness.person_a.id not in sample_matched
    assert person_c.id in sample_matched


# ── ArchivePlanner 闭环（E-SG-6 #5/#6/#8） ──────────────────────────────────


def test_archive_planner_consumes_every_person_attribution():
    """多 Person attribution → ArchivePlanner → 每人合法归档结果均保留。"""
    harness = _Harness()
    harness.generate_suggestions()
    asg_a = harness.active_for(harness.cluster_by_ordinal(0))
    asg_b = harness.active_for(harness.cluster_by_ordinal(1))
    harness.workbench.confirm(ConfirmAssignmentCommand(asg_a.id))
    harness.workbench.confirm(ConfirmAssignmentCommand(asg_b.id))

    person_repo = _FakePersonRepository(list(harness.persons))
    photo_repo = _FakePhotoRepository([
        Photo(path=PhotoPath(Path.cwd() / "photos" / "合影.jpg", base=PhotoPathBase.ABSOLUTE), id=harness.photo),
    ])
    recognition_repo = _FakeRecognitionRepository({
        harness.person_a.id: harness.compat_for(harness.person_a.id),
        harness.person_b.id: harness.compat_for(harness.person_b.id),
    })
    planner = ArchivePlanner(
        path_builder=_FakeArchivePathBuilder(),
        person_repository=person_repo,
        photo_repository=photo_repo,
        recognition_repository=recognition_repo,
        archive_record_repository=_FakeArchiveRecordRepository(),
    )
    plan = planner.plan("/archive", (harness.person_a.id, harness.person_b.id))

    # E-SG-6 #6：A 与 B 均进入各自的归档结果（同照片两条计划项）。
    assert plan.planned_count == 2
    assert {(item.person_name, item.photo_id)
            for item in plan.items} == {
        ("人物A", harness.photo), ("人物B", harness.photo),
    }


def test_archive_planner_reflects_reassignment_current_identity():
    """改派后：ArchivePlanner 消费的兼容结果与当前 Assignment 一致。"""
    harness = _Harness()
    person_c = harness._person("人物C", 3)
    harness.generate_suggestions()
    cluster_a = harness.cluster_by_ordinal(0)
    asg_a = harness.active_for(cluster_a)
    harness.workbench.confirm(ConfirmAssignmentCommand(asg_a.id))
    harness.workbench.unassign(UnassignClusterCommand(cluster_a.id))
    harness.workbench.assign_person(AssignClusterPersonCommand(
        cluster_id=cluster_a.id, person_id=person_c.id,
    ))

    person_repo = _FakePersonRepository(list(harness.persons))
    photo_repo = _FakePhotoRepository([
        Photo(path=PhotoPath(Path.cwd() / "photos" / "合影.jpg", base=PhotoPathBase.ABSOLUTE), id=harness.photo),
    ])
    recognition_by_person = {
        person.id: harness.compat_for(person.id) for person in harness.persons
    }
    planner = ArchivePlanner(
        path_builder=_FakeArchivePathBuilder(),
        person_repository=person_repo,
        photo_repository=photo_repo,
        recognition_repository=_FakeRecognitionRepository(recognition_by_person),
        archive_record_repository=_FakeArchiveRecordRepository(),
    )
    plan = planner.plan(
        "/archive",
        tuple(person.id for person in harness.persons),
    )

    planned_persons = {item.person_name for item in plan.items}
    assert planned_persons == {"人物C"}  # 当前身份 = C；A 的投影已回收
    assert plan.planned_count == 1
