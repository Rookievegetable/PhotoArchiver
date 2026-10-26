"""LOGIC-04 — 簇级 ignored/unknown 阻断自动建议与位置自动确认（真实 SQLite）.

Owner 决策：簇被标记 ``ignored``/``unknown`` 后，不得再进入相似度建议输入，
也不得进入位置自动确认候选（``evaluate_positional_auto_confirm`` 全仓唯一
调用点在 ``SuggestPairingsService`` 内，入口过滤即同时封住两条路径）。

照片级忽略（观测级排除）是独立语义，不在本文件范围。
全部使用 tmp_path 隔离数据库；不触碰生产库。
"""

from datetime import datetime
from pathlib import Path

from photo_archiver.application.commands.pairing import (
    SetClusterStateCommand,
    StartSuggestPairingsCommand,
)
from photo_archiver.application.services import PairingWorkbenchService
from photo_archiver.application.services import SuggestPairingsService
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.domain import (
    FaceBox,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    FaceEmbedding,
    FaceObservation,
    Person,
    Photo,
    PhotoPath,
    PhotoPathBase,
    RecognitionRun,
)
from photo_archiver.infrastructure.cosine_kernel import NumpyCosineSimilarityFactory

_BASE = datetime(2026, 1, 1, 8, 0, 0)


class _World:
    """真实 SQLite 世界：3 人 × 3 簇（每簇一照片一观测），位次可自动确认。"""

    def __init__(self, tmp_path: Path):
        self.repos = build_sqlite_repositories(tmp_path / "logic04.sqlite3")
        run = RecognitionRun(parameters={})
        self.repos.recognition_runs.add_run(run)
        self.run = run
        self._cluster_run = None
        self._photo_seq = 0

    def add_person(self, name: str, roster_order: int) -> Person:
        person = Person(name=name, roster_order=roster_order)
        self.repos.people.add(person)
        return person

    def add_photo(self, captured: datetime):
        self._photo_seq += 1
        path = Path(self.repos._connection_provider.database_path).parent / (
            f"photo_{self._photo_seq}.jpg"
        )
        photo = Photo(path=PhotoPath(path, PhotoPathBase.ABSOLUTE), captured_at=captured)
        self.repos.photos.add(photo)
        return photo

    def add_cluster(self, sort_key: str, photo, captured: datetime):
        observation = FaceObservation(
            run_id=self.run.id,
            photo_id=photo.id,
            face_index=0,
            photo_face_count=1,
            det_score=0.9,
            box=FaceBox(0, 0, 10, 10),
            embedding=FaceEmbedding((1.0, 0.0, 0.0)),
            scope_verdict="in_selected_scope",
            quality_score=0.9,
        )
        self.repos.face_observations.add_many([observation])
        if self._cluster_run is None:
            cluster_run = FaceClusterRun(
                recognition_run_id=self.run.id, algorithm_version="v1",
            )
            self.repos.face_clusters.add_cluster_run(cluster_run)
            self._cluster_run = cluster_run
        cluster = FaceCluster(
            cluster_run_id=self._cluster_run.id,
            run_id=self.run.id,
            ordinal=len(self.repos.face_clusters.list_clusters(self._cluster_run.id)),
            member_count=1,
            sort_key=sort_key,
            first_captured_at=captured,
        )
        self.repos.face_clusters.add_clusters([cluster])
        self.repos.face_clusters.add_members([
            FaceClusterMember(cluster_id=cluster.id, observation_id=observation.id),
        ])
        return cluster

    def seed_three_pairs(self):
        """3 簇 × 3 人（时间齐备、无拒绝对），返回 (persons, clusters)。"""
        persons = [self.add_person(f"人员{i}", i + 1) for i in range(3)]
        clusters = []
        for i in range(3):
            photo = self.add_photo(_BASE)
            clusters.append(self.add_cluster(f"k|g{i:02d}|00000{i}", photo, _BASE))
        return persons, clusters

    def build_suggest(self) -> SuggestPairingsService:
        return SuggestPairingsService(
            self.repos.face_clusters,
            self.repos.face_observations,
            self.repos.people,
            self.repos.cluster_assignments,
            self.repos.person_face_samples,
            NumpyCosineSimilarityFactory(),
            transaction_runner=self.repos._connection_provider.run_immediate,
        )

    def build_workbench(self) -> PairingWorkbenchService:
        return PairingWorkbenchService(
            self.repos.cluster_assignments,
            self.repos.face_clusters,
            self.repos.face_observations,
            self.repos.people,
            self.repos.recognition,
            self.repos.person_face_samples,
        )

    def assignment_rows(self):
        return self.repos.cluster_assignments.list_by_cluster_run(self._cluster_run.id)


def _mark(world, cluster, state: str) -> None:
    world.build_workbench().set_cluster_state(
        SetClusterStateCommand(cluster_id=cluster.id, state=state),
    )


def test_ignored_cluster_is_excluded_from_suggestions_and_auto_confirm(tmp_path):
    """ignored 簇：不生成建议、不参与位置自动确认；其余簇仍获建议。

    3 簇 3 人中忽略 1 簇后剩余 2 簇对 3 人——C-2 位次准入的数目相等条件不
    满足，整批按既有 fail-closed 语义维持 suggested（auto_confirmed=0）。
    被忽略簇的排除以最终落库零行为证（建议输入与自动确认候选同源过滤）。
    """
    world = _World(tmp_path)
    _persons, clusters = world.seed_three_pairs()
    _mark(world, clusters[1], "ignored")

    summary = world.build_suggest().execute(
        StartSuggestPairingsCommand(world._cluster_run.id),
    )

    rows = world.assignment_rows()
    assert all(row.cluster_id != clusters[1].id for row in rows)  # 零建议零确认
    assert {row.cluster_id for row in rows} == {clusters[0].id, clusters[2].id}
    assert summary.auto_confirmed == 0  # 2 簇 vs 3 人：既有 C-2 准入 fail-closed
    assert summary.suggestions == 2  # 其余两簇仍正常获得建议
    # 新口径：unmatched_clusters = 有效簇数 − 获建议簇数，被忽略簇不计入
    # "未匹配"（2 个有效簇均获 ordered 建议 → 0）。
    assert summary.unmatched_clusters == 0


def test_unknown_cluster_is_excluded_from_suggestions_and_auto_confirm(tmp_path):
    """unknown（陌生人）簇：与 ignored 同口径排除。"""
    world = _World(tmp_path)
    _persons, clusters = world.seed_three_pairs()
    _mark(world, clusters[2], "unknown")

    summary = world.build_suggest().execute(
        StartSuggestPairingsCommand(world._cluster_run.id),
    )

    rows = world.assignment_rows()
    assert all(row.cluster_id != clusters[2].id for row in rows)
    assert {row.cluster_id for row in rows} == {clusters[0].id, clusters[1].id}
    assert summary.auto_confirmed == 0  # 2 簇 vs 3 人：既有 C-2 准入 fail-closed
    assert summary.suggestions == 2
    assert summary.unmatched_clusters == 0  # 被忽略簇不计入"未匹配"


def test_unmarked_clusters_keep_full_auto_confirm_baseline(tmp_path):
    """无忽略标记：3 簇 × 3 人全部位置自动确认（基线行为不回归）。"""
    world = _World(tmp_path)
    _persons, clusters = world.seed_three_pairs()

    summary = world.build_suggest().execute(
        StartSuggestPairingsCommand(world._cluster_run.id),
    )

    assert summary.auto_confirmed == 3
    assert {row.cluster_id for row in world.assignment_rows()} == {
        cluster.id for cluster in clusters
    }


def test_repeat_suggest_after_ignoring_stays_idempotent(tmp_path):
    """忽略后重复生成建议：幂等零新增（被忽略簇不复活、已确认簇不重排）。"""
    world = _World(tmp_path)
    _persons, clusters = world.seed_three_pairs()
    _mark(world, clusters[0], "ignored")
    suggest = world.build_suggest()
    suggest.execute(StartSuggestPairingsCommand(world._cluster_run.id))
    first_rows = world.assignment_rows()

    second = suggest.execute(StartSuggestPairingsCommand(world._cluster_run.id))

    assert second.auto_confirmed == 0  # 已 auto_confirmed 的两簇不再进入候选
    assert len(world.assignment_rows()) == len(first_rows)
    assert all(row.cluster_id != clusters[0].id for row in world.assignment_rows())
