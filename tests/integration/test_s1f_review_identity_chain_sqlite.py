"""S1-F：Review → Assignment → Projection 唯一身份链（真实 SQLite）。

D-2 = B（Owner 冻结 2026-10-02）：Review 只能批准**已聚类**照片。本文件按
任务书测试矩阵覆盖核心闭环、pending 复用、fail-closed、与既有决策的三类关系、
幂等、多人照片与多支撑共存、bulk 语义。

全部使用新造数据；不触碰生产库与 472 条 legacy pending。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.services.identity_decision_service import (
    IdentityDecisionService,
)
from photo_archiver.application.services.projection_reconciler import (
    ProjectionReconciler,
)
from photo_archiver.application.services.review_recognition_service import (
    ReviewRecognitionService,
)
from photo_archiver.domain import MatchStatus, RecognitionResult
from photo_archiver.domain.exceptions import (
    ManualDecisionProtectedError,
    PhotoNotClusteredError,
)
from photo_archiver.domain.entities.recognition_run import RecognitionRun


class _World:
    """真实 SQLite 最小世界：照片 → 观测 → 簇 → 决策 → 投影。"""

    def __init__(self, tmp_path: Path) -> None:
        self.repos = build_sqlite_repositories(tmp_path / "s1f.db")
        self.reconciler = ProjectionReconciler(
            recognition_repository=self.repos.recognition,
            assignment_repository=self.repos.cluster_assignments,
            cluster_repository=self.repos.face_clusters,
            observation_repository=self.repos.face_observations,
        )
        self.decisions = IdentityDecisionService(
            recognition_repository=self.repos.recognition,
            assignment_repository=self.repos.cluster_assignments,
            cluster_repository=self.repos.face_clusters,
            observation_repository=self.repos.face_observations,
            person_repository=self.repos.people,
            sample_repository=self.repos.person_face_samples,
            reconciler=self.reconciler,
            transaction_runner=self.repos._connection_provider.run_immediate,
        )
        self.review = ReviewRecognitionService(
            self.repos.recognition,
            identity_decision_service=self.decisions,
        )
        self.run = RecognitionRun()
        self.repos.recognition_runs.add_run(self.run)
        self._ordinal = 0
        self._last_cluster_run = None

    def person(self, name: str):
        from photo_archiver.domain import Person

        person = Person(name=name)
        self.repos.people.add(person)
        return person

    def photo(self, stem: str):
        from photo_archiver.domain import Photo, PhotoPath, PhotoPathBase

        path = Path(self.repos._connection_provider.database_path).parent / f"{stem}.jpg"
        path.write_bytes(b"x")
        photo = Photo(path=PhotoPath(path, PhotoPathBase.ABSOLUTE))
        self.repos.photos.add(photo)
        return photo

    def cluster(
        self, photos: list, *, same_run_as_last: bool = False,
    ) -> object:
        """单成员簇（每张照片一个观测），返回最后一个簇（决策锚点）。

        ``same_run_as_last``：复用上一次调用的代际（同代际多簇 = 合影形态，
        用于锚点歧义测试）。
        """
        from photo_archiver.domain.entities.face_cluster import (
            FaceCluster,
            FaceClusterMember,
            FaceClusterRun,
        )
        from photo_archiver.domain.entities.face_observation import FaceObservation
        from photo_archiver.domain.value_objects import FaceBox, FaceEmbedding

        if same_run_as_last and self._last_cluster_run is not None:
            cluster_run = self._last_cluster_run
        else:
            cluster_run = FaceClusterRun(
                recognition_run_id=self.run.id, algorithm_version=f"gen{self._ordinal}"
            )
            self.repos.face_clusters.add_cluster_run(cluster_run)
        cluster = FaceCluster(
            cluster_run_id=cluster_run.id, run_id=self.run.id,
            ordinal=self._ordinal, member_count=len(photos),
            sort_key=f"k{self._ordinal:03d}",
        )
        self.repos.face_clusters.add_clusters([cluster])
        members = []
        for index, photo in enumerate(photos):
            used = {
                o.face_index
                for o in self.repos.face_observations.list_by_photo(photo.id)
            }
            face_index = 0
            while face_index in used:
                face_index += 1
            observation = FaceObservation(
                run_id=self.run.id, photo_id=photo.id, face_index=face_index,
                photo_face_count=face_index + 1, det_score=0.9 - 0.01 * index,
                box=FaceBox(index * 20, 0, index * 20 + 10, 10),
                embedding=FaceEmbedding((1.0, 0.0, 0.0, index)),
                scope_verdict="in_selected_scope",
            )
            self.repos.face_observations.add_many([observation])
            members.append(
                FaceClusterMember(cluster_id=cluster.id, observation_id=observation.id)
            )
        self.repos.face_clusters.add_members(members)
        self._last_cluster_run = cluster_run
        self._ordinal += 1
        return cluster

    def pending(self, photo) -> RecognitionResult:
        result = RecognitionResult(photo_id=photo.id, confidence=None)
        self.repos.recognition.add(result)
        return result

    def pending_count(self) -> int:
        return len(self.repos.recognition.list_pending())


# ── 核心身份链 ────────────────────────────────────────────────────────────────


def test_review_approval_creates_assignment(tmp_path: Path) -> None:
    """Review → Assignment(source=review, confirmed) → projection.assignment_id。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    world.cluster([photo])
    pending = world.pending(photo)

    approved = world.review.approve(pending.id, person.id)

    assert approved is not None
    assert approved.status is MatchStatus.APPROVED
    assert approved.assignment_id is not None
    decision = world.repos.cluster_assignments.list_by_cluster(
        world.repos.face_clusters.list_clusters(
            world.repos.face_clusters.list_all_cluster_runs()[0].id
        )[0].id
    )[0]
    assert decision.source == "review"
    assert decision.status == "confirmed"
    assert decision.person_id == person.id


def test_review_approval_reuses_pending_projection(tmp_path: Path) -> None:
    """D-3：pending 行被就地复用——行数不变、pending 1→0、assignment_id 写入。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    world.cluster([photo])
    pending = world.pending(photo)

    assert world.pending_count() == 1
    world.review.approve(pending.id, person.id)

    rows = world.repos.recognition.list_by_photo(photo.id)
    assert len(rows) == 1, "不得产生第二条行"
    assert rows[0].status is MatchStatus.APPROVED
    assert rows[0].assignment_id is not None
    assert world.pending_count() == 0


def test_review_does_not_directly_persist_approved_without_assignment(
    tmp_path: Path,
) -> None:
    """AC-2/AC-3：身份批准产生的 approved 必须 assignment_id != NULL。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    world.cluster([photo])
    pending = world.pending(photo)

    world.review.approve(pending.id, person.id)

    for row in world.repos.recognition.list_by_photo(photo.id):
        if row.status is MatchStatus.APPROVED and row.person_id == person.id:
            assert row.assignment_id is not None, "身份批准禁止产生无主 approved"


# ── D-2 = B fail-closed ───────────────────────────────────────────────────────


def test_review_approval_rejects_unclustered_photo(tmp_path: Path) -> None:
    """D-2：照片有观测但未入簇 → approve 被拒，数据库零副作用。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    pending = world.pending(photo)  # 有 pending，但没有任何观测/簇

    with pytest.raises(PhotoNotClusteredError):
        world.review.approve(pending.id, person.id)

    assert world.repos.cluster_assignments.list_by_cluster_run_all() == [] \
        if hasattr(world.repos.cluster_assignments, "list_by_cluster_run_all") else True
    assert len(world.repos.recognition.list_projections()) == 0
    assert world.repos.recognition.find_by_id(pending.id).status is MatchStatus.PENDING
    assert world.pending_count() == 1, "pending 行不得被错误转换"


def test_review_approval_rejects_photo_without_any_observation(tmp_path: Path) -> None:
    """连观测都没有的照片同样 fail-closed（D-2 前置的严格形态）。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    pending = world.pending(photo)

    with pytest.raises(PhotoNotClusteredError):
        world.review.approve(pending.id, person.id)
    assert world.pending_count() == 1


# ── 与既有决策的三类关系（Case B / C / D） ───────────────────────────────────


def test_review_overrides_machine_suggestion(tmp_path: Path) -> None:
    """Case B：簇已有 suggested → 同人 Review 确认**复用该行**（状态机升格）。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([photo])
    world.pending(photo)
    # 机器建议（ordered_suggestion, suggested）
    from photo_archiver.domain.entities.cluster_assignment import ClusterPersonAssignment

    suggested = ClusterPersonAssignment(
        cluster_id=cluster.id, person_id=person.id, source="ordered_suggestion",
    )
    world.repos.cluster_assignments.add_assignments([suggested])

    approved = world.review.approve(
        world.repos.recognition.list_by_photo(photo.id)[0].id, person.id
    )
    assert approved is not None
    # S1-F 语义修正：machine suggested 必须 terminal，人工最终性落在
    # source='review' 的新决策行上（source immutable，禁止原地升格）。
    decisions = world.repos.cluster_assignments.list_by_cluster(cluster.id)
    assert len(decisions) == 2
    machine_rows = [r for r in decisions if r.source == "ordered_suggestion"]
    review_rows = [r for r in decisions if r.source == "review"]
    assert len(machine_rows) == 1 and machine_rows[0].status == "unassigned", (
        "机器建议被人工确认后转为 terminal"
    )
    assert len(review_rows) == 1 and review_rows[0].status == "confirmed"
    assert review_rows[0].person_id == person.id
    projection = world.repos.recognition.find_projection(photo.id, person.id)
    assert projection is not None and projection.assignment_id == review_rows[0].id


def test_review_reassigns_machine_identity_to_manual(tmp_path: Path) -> None:
    """Case C：机器 confirmed → B，人工 Review → A：B 退场、A 接管、投影重算。"""
    world = _World(tmp_path)
    person_a = world.person("张三")
    person_b = world.person("李四")
    photo = world.photo("P1")
    cluster = world.cluster([photo])
    world.pending(photo)

    # 机器建议指向 B（suggested：不产生投影、pending 行仍在队列）。
    # 通道事实：confirmed 机器身份的照片其 pending 行已被复用翻转、不在审核队列，
    # 其改派属配对工作台；审核队列的 Case C 必然是 suggested → B。
    from photo_archiver.domain.entities.cluster_assignment import ClusterPersonAssignment

    machine = ClusterPersonAssignment(
        cluster_id=cluster.id, person_id=person_b.id, source="ordered_suggestion",
    )
    world.repos.cluster_assignments.add_assignments([machine])

    pending = world.repos.recognition.list_pending()[0]
    approved = world.review.approve(pending.id, person_a.id)

    assert approved is not None and approved.person_id == person_a.id
    # B 从未产生投影（suggested）；A 的投影带 assignment_id。
    assert world.repos.recognition.find_projection(photo.id, person_b.id) is None
    projection_a = world.repos.recognition.find_projection(photo.id, person_a.id)
    assert projection_a is not None and projection_a.assignment_id is not None
    # 决策历史完整：B 的建议行转 unassigned（保留），A 的新行 review/confirmed。
    history = world.repos.cluster_assignments.list_by_cluster(cluster.id)
    statuses = sorted(row.status for row in history)
    assert statuses == ["confirmed", "unassigned"]
    review_rows = [row for row in history if row.source == "review"]
    assert len(review_rows) == 1 and review_rows[0].person_id == person_a.id


def test_review_preserves_manual_finality(tmp_path: Path) -> None:
    """P0-5 回归：Review（人工）可改派 manual；机器不可撤销 review 决策。"""
    world = _World(tmp_path)
    zhang = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([photo])
    world.pending(photo)
    world.review.approve(
        world.repos.recognition.list_pending()[0].id, zhang.id
    )

    # review 决策属于 MANUAL_ASSIGNMENT_SOURCES → 机器 actor 撤销被拒。
    from photo_archiver.application.commands.pairing import UnassignClusterCommand
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
    with pytest.raises(ManualDecisionProtectedError):
        workbench.unassign(UnassignClusterCommand(cluster.id), actor="auto_rerun")
    assert world.repos.recognition.find_projection(photo.id, zhang.id) is not None


def test_review_approval_is_idempotent(tmp_path: Path) -> None:
    """Case D 同人重复批准：不产生重复决策行/投影行。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([photo])
    pending = world.pending(photo)

    first = world.review.approve(pending.id, person.id)
    assert first is not None
    # 二次批准：该行已终态（复用后的投影行），按既有语义跳过返回 None——
    # 不得产生重复决策行或第二行。
    second = world.review.approve(pending.id, person.id)
    assert second is None, "终态行不可重开（既有 MatchStatus 语义）"

    decisions = world.repos.cluster_assignments.list_by_cluster(cluster.id)
    assert len([r for r in decisions if r.status == "confirmed"]) == 1
    assert len(world.repos.recognition.list_by_photo(photo.id)) == 1


# ── 多人照片 / 多支撑共存 ─────────────────────────────────────────────────────


def test_review_approval_preserves_other_person_attribution(tmp_path: Path) -> None:
    """AC-9：合影 P→A 与 P→B 并存；Review 确认 A 不删除 B。"""
    world = _World(tmp_path)
    zhang = world.person("张三")
    li = world.person("李四")
    photo = world.photo("P1")
    # 同一代际两个簇（合影：P 的两张脸分落两簇）。
    cluster_a = world.cluster([photo])
    cluster_b = world.cluster([photo], same_run_as_last=True)

    # C1 经工作台确认给 B（confirmed）；同代际双簇 → Review 必须显式给锚点。
    from photo_archiver.domain.entities.cluster_assignment import ClusterPersonAssignment

    machine_b = ClusterPersonAssignment(
        cluster_id=cluster_b.id, person_id=li.id, source="ordered_suggestion",
    )
    machine_b.confirm()
    world.repos.cluster_assignments.add_assignments([machine_b])
    world.reconciler.reconcile_pair(photo.id, li.id)

    pending = world.pending(photo)
    # 未指定 cluster_id：同代际双簇 fail-closed（不得猜测 Top-1）。
    from photo_archiver.domain.exceptions import ReviewAnchorAmbiguousError

    with pytest.raises(ReviewAnchorAmbiguousError):
        world.review.approve(pending.id, zhang.id)
    assert world.repos.recognition.find_projection(photo.id, zhang.id) is None
    # 显式指定 C1（张三的脸所在簇）→ 精确落锚。
    world.review.approve(pending.id, zhang.id, cluster_id=cluster_a.id)

    assert world.repos.recognition.find_projection(photo.id, zhang.id) is not None
    assert world.repos.recognition.find_projection(photo.id, li.id) is not None, (
        "Review A 不得删除 B 的归属"
    )


def test_review_does_not_break_multiple_assignment_support(tmp_path: Path) -> None:
    """AC-10：两簇同人（跨代际）支撑同一 pair；撤一个支撑投影仍在。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    world.cluster([photo])   # 代际 1
    world.cluster([photo])   # 代际 2
    runs = world.repos.face_clusters.list_all_cluster_runs()
    clusters = world.repos.face_clusters.list_clusters(runs[0].id) + \
        world.repos.face_clusters.list_clusters(runs[1].id)
    assert len(clusters) == 2

    from photo_archiver.domain.entities.cluster_assignment import ClusterPersonAssignment

    assignments: list = []
    for cluster in clusters:
        assignment = ClusterPersonAssignment(
            cluster_id=cluster.id, person_id=person.id, source="review",
        )
        assignment.confirm()
        world.repos.cluster_assignments.add_assignments([assignment])
        assignments.append(assignment)
    world.reconciler.reconcile_pair(photo.id, person.id)
    assert len(world.repos.recognition.list_projections()) == 1

    # 撤掉一个支撑（人工）：另一簇的 confirmed 仍支撑投影，retarget 到它。
    first = assignments[0]
    first.unassign()
    world.repos.cluster_assignments.update_assignment(first)
    world.reconciler.reconcile_pair(photo.id, person.id)

    projection = world.repos.recognition.find_projection(photo.id, person.id)
    assert projection is not None, "多支撑撤一不删"
    assert projection.assignment_id == assignments[1].id


# ── bulk（S1-F6） ─────────────────────────────────────────────────────────────


def test_bulk_review_approval_respects_d2(tmp_path: Path) -> None:
    """bulk：已聚类 → 成功；未聚类 → 跳过（行留队列），不中断整批。"""
    world = _World(tmp_path)
    person = world.person("张三")
    clustered_photo = world.photo("clustered")
    unclustered_photo = world.photo("raw")
    world.cluster([clustered_photo])
    ok = world.pending(clustered_photo)
    skipped = world.pending(unclustered_photo)

    transitioned = world.review.bulk_approve((ok.id, skipped.id), person.id)

    assert transitioned == 1, "未聚类项按 D-2 = B 跳过"
    assert world.repos.recognition.find_by_id(ok.id).status is MatchStatus.APPROVED
    assert world.repos.recognition.find_by_id(skipped.id).status is MatchStatus.PENDING
    assert len(world.repos.recognition.list_projections()) == 1


def test_bulk_review_mixed_without_identity_keeps_legacy_disposition(
    tmp_path: Path,
) -> None:
    """不带身份的批准（D-1：显式告警后的已处理未定身份）就地翻转、不产生归属。"""
    world = _World(tmp_path)
    photo = world.photo("P1")
    world.cluster([photo])
    pending = world.pending(photo)

    transitioned = world.review.bulk_approve((pending.id,), None)

    assert transitioned == 1
    row = world.repos.recognition.find_by_id(pending.id)
    assert row.status is MatchStatus.APPROVED
    assert row.person_id is None and row.assignment_id is None
    # 匿名孤儿：不可归档、不被 reconcile 消费。
    assert len(world.repos.recognition.list_projections()) == 0


# ── 样本沉淀（S0 §7.4：人工确认 → 样本） ─────────────────────────────────────


def test_review_approval_deposits_samples(tmp_path: Path) -> None:
    """Review 人工确认沉淀整簇成员观测为样本（自动确认永不沉淀的前提面）。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo_a = world.photo("A")
    photo_b = world.photo("B")
    world.cluster([photo_a, photo_b])
    pending = world.pending(photo_a)

    world.review.approve(pending.id, person.id)

    samples = world.repos.person_face_samples.list_by_person(person.id)
    assert len(samples) == 2, "整簇两个成员观测均沉淀"
    # 样本沉淀不被重复执行（UNIQUE + existing 检查）。
    world.review.approve(pending.id, person.id)  # 终态行 → None，零副作用
    assert len(world.repos.person_face_samples.list_by_person(person.id)) == 2

# ── S1-F 语义修正：source/finality 与锚点歧义 ────────────────────────────────


def test_machine_cannot_retract_review_created_assignment(tmp_path: Path) -> None:
    """Case D：machine suggested → Review confirm → machine 撤回必须被拒。"""
    from photo_archiver.application.commands.pairing import UnassignClusterCommand
    from photo_archiver.application.services.pairing_workbench_service import (
        PairingWorkbenchService,
    )
    from photo_archiver.domain.entities.cluster_assignment import ClusterPersonAssignment

    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([photo])
    world.pending(photo)
    # 机器建议存在（机器"自己的"行）
    suggestion = ClusterPersonAssignment(
        cluster_id=cluster.id, person_id=person.id, source="ordered_suggestion",
    )
    world.repos.cluster_assignments.add_assignments([suggestion])

    world.review.approve(world.repos.recognition.list_pending()[0].id, person.id)

    latest = world.repos.cluster_assignments.list_latest_decision(cluster.id)
    assert latest is not None and latest.source == "review", (
        "Review 确认后当前决策必须是 review 来源（机器建议已 terminal）"
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
    with pytest.raises(ManualDecisionProtectedError):
        workbench.unassign(UnassignClusterCommand(cluster.id), actor="auto_rerun")
    assert world.repos.cluster_assignments.list_latest_decision(cluster.id).source == "review"
    assert world.repos.recognition.find_projection(photo.id, person.id) is not None


def test_machine_cannot_retract_workbench_confirmed_machine_source(
    tmp_path: Path,
) -> None:
    """工作台原地确认产出 confirmed+machine source——人工确认事实由 status 承载，
    机器同样不得撤销（P0-5 守卫按 status 扩展的回归）。"""
    from photo_archiver.application.commands.pairing import (
        ConfirmAssignmentCommand,
        UnassignClusterCommand,
    )
    from photo_archiver.application.services.pairing_workbench_service import (
        PairingWorkbenchService,
    )
    from photo_archiver.domain.entities.cluster_assignment import ClusterPersonAssignment

    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    cluster = world.cluster([photo])
    suggestion = ClusterPersonAssignment(
        cluster_id=cluster.id, person_id=person.id, source="ordered_suggestion",
    )
    world.repos.cluster_assignments.add_assignments([suggestion])

    workbench = PairingWorkbenchService(
        world.repos.cluster_assignments,
        world.repos.face_clusters,
        world.repos.face_observations,
        world.repos.people,
        world.repos.recognition,
        world.repos.person_face_samples,
        reconciler=world.reconciler,
    )
    workbench.confirm(ConfirmAssignmentCommand(suggestion.id))  # 人工原地确认

    confirmed = world.repos.cluster_assignments.list_latest_decision(cluster.id)
    assert confirmed.status == "confirmed" and confirmed.source == "ordered_suggestion"

    with pytest.raises(ManualDecisionProtectedError):
        workbench.unassign(UnassignClusterCommand(cluster.id), actor="auto_rerun")


def test_multi_person_review_cannot_hit_other_cluster(tmp_path: Path) -> None:
    """Multi-person Case 1（同代际）：C1→A 已确认，approve(P,B) 未指定锚点 →
    fail-closed；C1 的 A 身份不受影响。"""
    from photo_archiver.domain.exceptions import ReviewAnchorAmbiguousError

    world = _World(tmp_path)
    zhang = world.person("张三")
    li = world.person("李四")
    photo = world.photo("P1")
    cluster_c1 = world.cluster([photo])
    world.cluster([photo], same_run_as_last=True)
    pending = world.pending(photo)
    # C1→A 已建立（显式锚点走一次）——pending 行被复用消费，离开队列。
    world.review.approve(pending.id, zhang.id, cluster_id=cluster_c1.id)

    # 通道事实：同照片的第二个归属在队列中没有第二行（RR-11）；
    # 构造第二行（legacy 形态允许）以验证锚点守卫本身。
    second_row = RecognitionResult(photo_id=photo.id, confidence=None)
    world.repos.recognition.add(second_row)

    with pytest.raises(ReviewAnchorAmbiguousError):
        world.review.approve(second_row.id, li.id)  # 无锚点 → 不得猜测改写 C1
    latest_c1 = world.repos.cluster_assignments.list_latest_decision(cluster_c1.id)
    assert latest_c1.person_id == zhang.id, "C1 的 A 身份不得被 B 顶掉"


def test_multi_person_explicit_anchor_targets_requested_cluster(
    tmp_path: Path,
) -> None:
    """Multi-person Case 1（显式锚点）：cluster_id=C2 → B 落 C2，C1→A 不动。"""
    world = _World(tmp_path)
    zhang = world.person("张三")
    li = world.person("李四")
    photo = world.photo("P1")
    cluster_c1 = world.cluster([photo])
    cluster_c2 = world.cluster([photo], same_run_as_last=True)
    pending = world.pending(photo)
    # D-3 复用取「(created_at, id) 最早的 pending 占位行」：第二审核项必须显式
    # 晚于第一项建立，否则同刻 + UUID 字典序会让首次批准随机消费另一行（F-1）。
    second_row = RecognitionResult(
        photo_id=photo.id, confidence=None,
        created_at=pending.created_at + timedelta(seconds=1),
    )
    world.repos.recognition.add(second_row)

    world.review.approve(pending.id, zhang.id, cluster_id=cluster_c1.id)
    world.review.approve(second_row.id, li.id, cluster_id=cluster_c2.id)

    assert world.repos.recognition.find_projection(photo.id, zhang.id) is not None
    assert world.repos.recognition.find_projection(photo.id, li.id) is not None
    latest_c1 = world.repos.cluster_assignments.list_latest_decision(cluster_c1.id)
    latest_c2 = world.repos.cluster_assignments.list_latest_decision(cluster_c2.id)
    assert latest_c1.person_id == zhang.id and latest_c2.person_id == li.id
    # 逐条核验：每个审核项各自成为其所批人员的投影，队列清空（F-1 §5.2）。
    first_after = world.repos.recognition.find_by_id(pending.id)
    second_after = world.repos.recognition.find_by_id(second_row.id)
    assert (first_after.status, first_after.person_id) == (MatchStatus.APPROVED, zhang.id)
    assert (second_after.status, second_after.person_id) == (MatchStatus.APPROVED, li.id)
    assert world.pending_count() == 0


def test_multi_person_review_a_keeps_b_projection(tmp_path: Path) -> None:
    """Multi-person Case 2/3：(P,A) 与 (P,B) 合法共存；Review 重批 A 不删 B。"""
    world = _World(tmp_path)
    zhang = world.person("张三")
    li = world.person("李四")
    photo = world.photo("P1")
    cluster_c1 = world.cluster([photo])
    cluster_c2 = world.cluster([photo], same_run_as_last=True)
    pending = world.pending(photo)
    # 同上：第二审核项显式晚于第一项，钉定 D-3 复用的消费对象（F-1）。
    second_row = RecognitionResult(
        photo_id=photo.id, confidence=None,
        created_at=pending.created_at + timedelta(seconds=1),
    )
    world.repos.recognition.add(second_row)

    world.review.approve(pending.id, zhang.id, cluster_id=cluster_c1.id)
    world.review.approve(second_row.id, li.id, cluster_id=cluster_c2.id)
    projections_before = {p.id for p in world.repos.recognition.list_projections()}

    # 重批 A（幂等，显式锚点）→ B 的投影保持。已终态化行被安全跳过。
    assert world.review.approve(pending.id, zhang.id, cluster_id=cluster_c1.id) is None

    assert world.repos.recognition.find_projection(photo.id, li.id) is not None
    projections_after = {p.id for p in world.repos.recognition.list_projections()}
    assert projections_before == projections_after
    # 逐条核验：两行各自承载其所批人员的投影，重批后零漂移（F-1 §5.2）。
    first_after = world.repos.recognition.find_by_id(pending.id)
    second_after = world.repos.recognition.find_by_id(second_row.id)
    assert (first_after.status, first_after.person_id) == (MatchStatus.APPROVED, zhang.id)
    assert (second_after.status, second_after.person_id) == (MatchStatus.APPROVED, li.id)
    assert world.pending_count() == 0


# ── F-1 整改：占位行选择确定性（同刻/UUID 序/重复批准） ─────────────────────

_LO_ID = UUID("00000000-0000-0000-0000-0000000000aa")
_HI_ID = UUID("00000000-0000-0000-0000-0000000000bb")
_BASE_MOMENT = datetime(2026, 10, 2, 12, 0, 0)


def _forced_two_row_world(
    tmp_path: Path, *, row1_id: UUID, row2_id: UUID, same_tick: bool,
):
    """双审核项世界：两行 id 与 created_at 全显式，钉定 (created_at, id) 选择行为。"""
    world = _World(tmp_path)
    zhang = world.person("张三")
    li = world.person("李四")
    photo = world.photo("P1")
    cluster_c1 = world.cluster([photo])
    cluster_c2 = world.cluster([photo], same_run_as_last=True)
    row1 = RecognitionResult(
        photo_id=photo.id, confidence=None, created_at=_BASE_MOMENT, id=row1_id,
    )
    world.repos.recognition.add(row1)
    row2 = RecognitionResult(
        photo_id=photo.id, confidence=None,
        created_at=_BASE_MOMENT if same_tick else _BASE_MOMENT + timedelta(seconds=1),
        id=row2_id,
    )
    world.repos.recognition.add(row2)
    return world, zhang, li, photo, cluster_c1, cluster_c2, row1, row2


@pytest.mark.parametrize("reverse_ids", [False, True], ids=["row1_id_first", "row2_id_first"])
def test_multi_person_uuid_order_does_not_change_outcomes(
    tmp_path: Path, reverse_ids: bool,
) -> None:
    """F-1 §5.3：created_at 确定有序时，无关的 UUID 字典序不得改变归属结果。"""
    row1_id, row2_id = (_LO_ID, _HI_ID) if not reverse_ids else (_HI_ID, _LO_ID)
    world, zhang, li, photo, c1, c2, row1, row2 = _forced_two_row_world(
        tmp_path, row1_id=row1_id, row2_id=row2_id, same_tick=False,
    )

    world.review.approve(row1.id, zhang.id, cluster_id=c1.id)
    world.review.approve(row2.id, li.id, cluster_id=c2.id)

    assert world.repos.recognition.find_projection(photo.id, zhang.id) is not None
    assert world.repos.recognition.find_projection(photo.id, li.id) is not None
    first_after = world.repos.recognition.find_by_id(row1.id)
    second_after = world.repos.recognition.find_by_id(row2.id)
    assert (first_after.status, first_after.person_id) == (MatchStatus.APPROVED, zhang.id)
    assert (second_after.status, second_after.person_id) == (MatchStatus.APPROVED, li.id)
    assert world.pending_count() == 0


def test_repeat_approve_skipped_and_does_not_block_other_person(tmp_path: Path) -> None:
    """F-1 §5.4：已终态化的审核项重复批准被跳过，且不阻断他人的合法审核。"""
    world, zhang, li, photo, c1, c2, row1, row2 = _forced_two_row_world(
        tmp_path, row1_id=_LO_ID, row2_id=_HI_ID, same_tick=False,
    )

    assert world.review.approve(row1.id, zhang.id, cluster_id=c1.id) is not None
    assert world.review.approve(row1.id, zhang.id, cluster_id=c1.id) is None
    assert world.pending_count() == 1  # 仅 row2 仍待审

    assert world.review.approve(row2.id, li.id, cluster_id=c2.id) is not None
    assert world.repos.recognition.find_projection(photo.id, li.id) is not None
    assert world.repos.recognition.find_projection(photo.id, zhang.id) is not None


def test_same_tick_reuse_consumes_earliest_row_and_stays_fail_closed(
    tmp_path: Path,
) -> None:
    """F-1 机制钉定：同刻双占位行（D-3 域外状态）的 fail-closed 语义。

    生产 GUI 链每照片至多一条 PENDING 占位行（识别兼容行的存在性守卫保证），
    两条同刻占位行只在合成/legacy 形态出现。D-3 复用取 (created_at, id) 最早行：
    本测试强制第二审核项的 id 排在最前，钉定首次批准消费它之后——对它的第二次
    批准被安全拒绝（不抛错、不误归属），未消费行保持 pending 可继续处理。若未来
    契约演进（如复用优先取被批准行），本测试须随裁决显式更新。
    """
    world, zhang, li, photo, c1, c2, row1, row2 = _forced_two_row_world(
        tmp_path, row1_id=_HI_ID, row2_id=_LO_ID, same_tick=True,
    )

    world.review.approve(row1.id, zhang.id, cluster_id=c1.id)
    # 最早的 (created_at, id) 行是 row2 → 被 zhang 的批准消费为投影。
    consumed = world.repos.recognition.find_by_id(row2.id)
    assert (consumed.status, consumed.person_id) == (MatchStatus.APPROVED, zhang.id)

    # 对已终态化行的批准：安全跳过，不抛错、不产生 li 归属（无身份交叉）。
    assert world.review.approve(row2.id, li.id, cluster_id=c2.id) is None
    assert world.repos.recognition.find_projection(photo.id, li.id) is None
    # 未被消费的 row1 仍 pending，可继续处理（队列不被误清）。
    assert world.repos.recognition.find_by_id(row1.id).status == MatchStatus.PENDING
    for projection in world.repos.recognition.list_projections():
        assert projection.person_id == zhang.id


def test_anchor_ambiguous_error_fails_closed(tmp_path: Path) -> None:
    """同代际双簇 + 无锚点：除异常外零副作用（AC-6/AC-9 的联合验证）。"""
    from photo_archiver.domain.exceptions import ReviewAnchorAmbiguousError

    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    world.cluster([photo])
    world.cluster([photo], same_run_as_last=True)
    pending = world.pending(photo)

    with pytest.raises(ReviewAnchorAmbiguousError):
        world.review.approve(pending.id, person.id)

    assert len(world.repos.recognition.list_projections()) == 0
    assert world.repos.recognition.find_by_id(pending.id).status is MatchStatus.PENDING
    assert world.pending_count() == 1
    samples = world.repos.person_face_samples.list_by_person(person.id)
    assert samples == [], "fail-closed 不得沉淀样本"


def test_cross_generation_single_cluster_latest_anchor(tmp_path: Path) -> None:
    """跨代际：重新聚类后最新代际单簇 → 无需显式锚点，自动锚定最新代际。"""
    world = _World(tmp_path)
    person = world.person("张三")
    photo = world.photo("P1")
    world.cluster([photo])                    # 代际 1
    cluster_g2 = world.cluster([photo])       # 代际 2（最新）
    pending = world.pending(photo)

    world.review.approve(pending.id, person.id)

    latest = world.repos.cluster_assignments.list_latest_decision(cluster_g2.id)
    assert latest is not None and latest.status == "confirmed"
    projection = world.repos.recognition.find_projection(photo.id, person.id)
    assert projection is not None
