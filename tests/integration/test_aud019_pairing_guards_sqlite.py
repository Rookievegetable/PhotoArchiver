"""AUD-019 — 配对守卫与并发删除场景（真实 SQLite，Stage 12B）.

沿真实仓储/服务验证 pairing 决策层的守卫行为（此前仅 InMemory 散点）：

- 非法状态 → 正确拒绝：不存在对象 / 双重确认 / reject 后确认 / 非法簇状态。
- 并发竞争：两个 workbench 实例竞争同一建议 → 单胜者。
- stale / deleted entity：人员删除（真实级联服务）与簇删除（FK CASCADE）后，
  陈旧 assignment 的 confirm 被拒；update 受影响行数 = 0 的 TOCTOU 守卫
  （delete-then-update 竞争注入）触发 ValidationError。

冷启动业务规则（FaceCluster/sort_key/roster_order/ordered_suggestion）零改动——
本文件只验证守卫，不改变任何建议生成语义。
"""

import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from photo_archiver.ai.similarity_matcher import CosinePersonMatcher
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.commands.cluster_faces import StartClusteringRunCommand
from photo_archiver.application.commands.deletion import DeletePersonCommand
from photo_archiver.application.commands.import_draft import (
    ConfirmImportCommand,
    ParseImportDraftCommand,
)
from photo_archiver.application.commands.pairing import (
    ConfirmAssignmentCommand,
    RejectAssignmentCommand,
    SetClusterStateCommand,
    StartSuggestPairingsCommand,
)
from photo_archiver.application.commands.scan_and_register_photos import (
    ScanAndRegisterPhotosCommand,
)
from photo_archiver.application.commands.start_recognition_run import (
    StartRecognitionRunCommand,
)
from photo_archiver.application.services.cluster_faces_service import ClusterFacesService
from photo_archiver.application.services.confirm_import_service import ConfirmImportService
from photo_archiver.application.services.delete_person_service import DeletePersonService
from photo_archiver.application.services.parse_import_draft_service import (
    ParseImportDraftService,
)
from photo_archiver.application.services.pairing_workbench_service import (
    PairingWorkbenchService,
    clamp_unit,
)
from photo_archiver.application.services.run_recognition_service import (
    RunRecognitionService,
)
from photo_archiver.application.services.scan_and_register_photos_service import (
    ScanAndRegisterPhotosService,
)
from photo_archiver.application.services.suggest_pairings_service import (
    SuggestPairingsService,
)
from photo_archiver.domain import (
    FaceBox,
    FaceBoxEmbedding,
    FaceEmbedding,
    ValidationError,
)
from photo_archiver.infrastructure import LocalPhotoFileScanner
from photo_archiver.infrastructure.cosine_kernel import NumpyCosineSimilarityFactory
from photo_archiver.infrastructure.database.sqlite_cluster_assignment_repository import (
    SQLiteClusterPersonAssignmentRepository,
)
from photo_archiver.infrastructure.database.sqlite_unit_of_work import SQLiteUnitOfWork
from photo_archiver.infrastructure.filesystem.pillow_photo_metadata_reader import (
    PillowPhotoMetadataReader,
)
from photo_archiver.infrastructure.importers.roster_table_reader import (
    FileRosterTableReader,
)


class _Detector:
    """可控假检测器（仅替代 AI 模型；决策链全真实）。"""

    def __init__(self, vectors: dict[str, tuple[float, ...]]):
        self._vectors = vectors

    def detect(self, image):
        return self.detect_with_embeddings(image)

    def detect_with_embeddings(self, image):
        vector = self._vectors.get(image.name)
        if vector is None:
            return []
        return [FaceBoxEmbedding(
            box=FaceBox(x1=0, y1=0, x2=8, y2=8, confidence=0.9),
            embedding=FaceEmbedding(vector=tuple(vector)),
        )]


def _seed_full_chain(repos, tmp_path: Path, photo_count: int = 2):
    """真实链到 suggested 建议为止：导入→扫描→识别→聚类→建议。

    返回 persons/photos/run/cluster_run 与每个人的 suggested 建议行
    （照片按创建序取得确定性的 mtime → sort_key → 位次配对：a→张三、b→李四…）。
    """
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    vectors: dict[str, tuple[float, ...]] = {}
    names = []
    for index in range(photo_count):
        name = f"{chr(ord('a') + index)}.jpg"
        captured = datetime(2026, 1, 1 + index, 12, 0, 0)
        path = photos_dir / name
        Image.new("RGB", (8, 8), (50 + index * 40, 90, 140)).save(path)
        stamp = captured.timestamp()
        os.utime(path, (stamp, stamp))
        vectors[name] = tuple(1.0 if axis == index else 0.0 for axis in range(4))
        names.append(name)
    csv_path = tmp_path / "roster.csv"
    roster = [("张三", "E001", ""), ("李四", "E002", "")]
    if photo_count > 2:
        roster.append(("王五", "E003", ""))
    lines = ["姓名,工号,部门"]
    lines.extend(f"{name},{identity},{department}" for name, identity, department in roster)
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    draft = ParseImportDraftService(
        FileRosterTableReader(), repos.import_batches, repos.people,
    ).execute(ParseImportDraftCommand(source_path=csv_path))
    ConfirmImportService(
        repos.import_batches, repos.people,
        unit_of_work=SQLiteUnitOfWork(repos._connection_provider),
    ).execute(ConfirmImportCommand(batch_id=draft.batch.id))
    persons = {person.name: person for person in repos.people.list_all()}

    ScanAndRegisterPhotosService(
        LocalPhotoFileScanner(), repos.folders, repos.photos,
        metadata_reader=PillowPhotoMetadataReader(),
    ).execute(ScanAndRegisterPhotosCommand(folder_path=photos_dir))
    photos = repos.photos.list_all()
    run = RunRecognitionService(
        detector=_Detector(vectors),
        matcher=CosinePersonMatcher(threshold=0.40),
        face_embedding_repository=repos.face_embeddings,
        recognition_repository=repos.recognition,
        recognition_run_repository=repos.recognition_runs,
        face_observation_repository=repos.face_observations,
        photo_repository=repos.photos,
    ).execute(StartRecognitionRunCommand(
        photo_ids=tuple(photo.id for photo in photos),
        images=tuple(photo.path.raw_path for photo in photos),
    ))
    cluster_run = ClusterFacesService(
        repos.recognition_runs, repos.face_observations,
        repos.face_clusters, NumpyCosineSimilarityFactory(),
    ).execute(StartClusteringRunCommand(run.id))
    SuggestPairingsService(
        repos.face_clusters, repos.face_observations, repos.people,
        repos.cluster_assignments, repos.person_face_samples,
        NumpyCosineSimilarityFactory(),
    ).execute(StartSuggestPairingsCommand(cluster_run_id=cluster_run.id))

    name_by_photo = {photo.id: photo.original_name for photo in photos}
    observations = {o.id: o for o in repos.face_observations.list_by_run(run.id)}
    suggested_by_person: dict = {}
    photo_names_by_cluster: dict = {}
    for cluster in repos.face_clusters.list_clusters(cluster_run.id):
        member_names = [
            name_by_photo[observations[member.observation_id].photo_id]
            for member in repos.face_clusters.list_members(cluster_run.id)
            if member.cluster_id == cluster.id
        ]
        photo_names_by_cluster[cluster.id] = member_names
    for assignment in repos.cluster_assignments.list_active_by_cluster_run(cluster_run.id):
        if assignment.status == "suggested" and assignment.person_id is not None:
            suggested_by_person[name_by_pid_for(assignment.person_id, persons)] = assignment
    return {
        "persons": persons,
        "photos": {photo.original_name: photo for photo in photos},
        "run": run,
        "cluster_run": cluster_run,
        "clusters": {
            cluster.id: cluster
            for cluster in repos.face_clusters.list_clusters(cluster_run.id)
        },
        "photo_names_by_cluster": photo_names_by_cluster,
        "suggested_by_person": suggested_by_person,
    }


def name_by_pid_for(person_id, persons_by_name):
    for person in persons_by_name.values():
        if person.id == person_id:
            return person.name
    raise AssertionError(f"unknown person {person_id}")


def suggested_assignment(repos, cluster_id):
    rows = [
        row for row in repos.cluster_assignments.list_by_cluster(cluster_id)
        if row.status == "suggested"
    ]
    assert len(rows) == 1
    return rows[0]


def test_confirm_nonexistent_assignment_rejected(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    with pytest.raises(ValidationError, match="does not exist"):
        _workbench(repos).confirm(ConfirmAssignmentCommand(assignment_id=uuid4()))


def test_stale_assignment_after_person_delete_rejected(tmp_path):
    """真实级联：人员删除 → assignment 级联消失 → 陈旧 confirm 被拒。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    context = _seed_full_chain(repos, tmp_path, photo_count=2)
    zhang = context["persons"]["张三"]
    row = context["suggested_by_person"]["张三"]

    DeletePersonService(
        repos.people, repos.photos, repos.recognition, repos.face_embeddings,
        unit_of_work=SQLiteUnitOfWork(repos._connection_provider),
    ).execute(DeletePersonCommand(person_ids=(zhang.id,)))

    assert repos.cluster_assignments.get_assignment(row.id) is None  # 级联删除
    with pytest.raises(ValidationError, match="does not exist"):
        _workbench(repos).confirm(ConfirmAssignmentCommand(assignment_id=row.id))


def test_stale_assignment_after_cluster_delete_rejected_and_scope_isolated(tmp_path):
    """簇删除（FK CASCADE）→ 该簇陈旧建议被拒；其他簇建议不受影响。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    context = _seed_full_chain(repos, tmp_path, photo_count=2)
    row_zhang = context["suggested_by_person"]["张三"]
    row_li = context["suggested_by_person"]["李四"]

    with repos._connection_provider.connect() as connection:
        connection.execute(
            "DELETE FROM face_clusters WHERE id = ?", (str(row_zhang.cluster_id),),
        )

    with pytest.raises(ValidationError, match="does not exist"):
        _workbench(repos).confirm(ConfirmAssignmentCommand(assignment_id=row_zhang.id))
    intact = suggested_assignment(repos, row_li.cluster_id)   # 其他簇建议不受影响
    result = _workbench(repos).confirm(
        ConfirmAssignmentCommand(assignment_id=intact.id),
    )
    assert result.status == "confirmed"


def test_update_assignment_affected_zero_guard_on_concurrent_delete(tmp_path):
    """TOCTOU 注入：读取后、写入前该行被并发删除 → 受影响行数 0 → ValidationError。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    context = _seed_full_chain(repos, tmp_path, photo_count=2)
    row = context["suggested_by_person"]["张三"]

    class _ConcurrentDeleteRepo(SQLiteClusterPersonAssignmentRepository):
        """在真实仓储写入前注入"并发删除"——精确复现 find→update 竞争窗口。"""

        def update_assignment(self, assignment):
            with self._connection_provider.connect() as connection:
                connection.execute(
                    "DELETE FROM cluster_person_assignments WHERE id = ?",
                    (str(assignment.id),),
                )
            return super().update_assignment(assignment)

    racing_workbench = PairingWorkbenchService(
        _ConcurrentDeleteRepo(repos._connection_provider),
        repos.face_clusters, repos.face_observations, repos.people,
        repos.recognition, repos.person_face_samples,
    )
    with pytest.raises(ValidationError, match="no longer exists"):
        racing_workbench.confirm(ConfirmAssignmentCommand(assignment_id=row.id))
    assert repos.cluster_assignments.get_assignment(row.id) is None


def test_double_confirm_rejected(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    context = _seed_full_chain(repos, tmp_path, photo_count=2)
    row = context["suggested_by_person"]["张三"]
    workbench = _workbench(repos)

    first = workbench.confirm(ConfirmAssignmentCommand(assignment_id=row.id))
    assert first.status == "confirmed"
    with pytest.raises(ValidationError, match="Only suggested assignments"):
        workbench.confirm(ConfirmAssignmentCommand(assignment_id=row.id))


def test_two_workbenches_single_winner_on_same_suggestion(tmp_path):
    """并发竞争：两个实例竞争同一建议 → 恰一胜者，败者被拒，无重复确认。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    context = _seed_full_chain(repos, tmp_path, photo_count=2)
    row = context["suggested_by_person"]["张三"]

    first = _workbench(repos).confirm(ConfirmAssignmentCommand(assignment_id=row.id))
    second_rejected = False
    try:
        _workbench(repos).confirm(ConfirmAssignmentCommand(assignment_id=row.id))
    except ValidationError:
        second_rejected = True
    assert first.status == "confirmed" and second_rejected
    confirmed_rows = [
        assignment for assignment in repos.cluster_assignments.list_by_cluster(row.cluster_id)
        if assignment.status == "confirmed"
    ]
    assert len(confirmed_rows) == 1                          # 恰一次身份确认


def test_reject_blocks_later_confirm(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    context = _seed_full_chain(repos, tmp_path, photo_count=2)
    row = context["suggested_by_person"]["张三"]
    workbench = _workbench(repos)

    rejected = workbench.reject(RejectAssignmentCommand(assignment_id=row.id))
    assert rejected.status == "rejected"
    with pytest.raises(ValidationError, match="Only suggested assignments"):
        workbench.confirm(ConfirmAssignmentCommand(assignment_id=row.id))


def test_set_cluster_state_guards(tmp_path):
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    context = _seed_full_chain(repos, tmp_path, photo_count=2)
    workbench = _workbench(repos)
    some_cluster = next(iter(context["clusters"].values()))

    with pytest.raises(ValidationError, match="Cluster state must be"):
        workbench.set_cluster_state(
            SetClusterStateCommand(cluster_id=some_cluster.id, state="split"),
        )
    with pytest.raises(ValidationError, match="does not exist"):
        workbench.set_cluster_state(
            SetClusterStateCommand(cluster_id=uuid4(), state="unknown"),
        )


def test_clamp_unit_bounds():
    assert clamp_unit(-0.5) == 0.0
    assert clamp_unit(0.5) == 0.5
    assert clamp_unit(1.7) == 1.0


def _workbench(repos):
    return PairingWorkbenchService(
        repos.cluster_assignments, repos.face_clusters, repos.face_observations,
        repos.people, repos.recognition, repos.person_face_samples,
    )
