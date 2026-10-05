"""S1-G：跨越 **import → scan → detect → cluster → Review → projection → archive**
的真实业务链端到端测试（Checkpoint 3 缺口补齐）。

为什么需要这条链：既有覆盖是**分裂**的——

* ``test_aud004_full_chain_regression.py`` 走 import→scan→detect→cluster→
  suggest→**工作台 confirm**→archive，但**零 Review 触及**（grep Review/IdentityDecision/
  reconcile = 0）；
* ``test_s1_projection_ownership_sqlite.py`` 与 ``test_s1f_review_identity_chain_
  sqlite.py`` 覆盖 Assignment/Projection/Review 语义，但**零 import/scan/archive**
  （grep ScanAndRegister/ConfirmImport/ArchivePhotos = 0）。

因此**没有任何测试证明**"真实扫描入库的照片，经审核身份确认后，文件真的落进
正确的人员目录"。本文件用**真实服务**（仅人脸检测器替身，与 AUD-004 同一约定）
把两段链缝合，验证业务闭环而非组件拼装。

冻结语义复核（任一被破坏即测试失败）：
INV-1 最新决策 / INV-2 active supports / INV-3 身份必经 Assignment /
INV-4 人工最终性 / INV-5 多人照片 / D-2=B 未聚类 fail-closed。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from photo_archiver.application.commands.archive import ArchivePhotosCommand
from photo_archiver.application.commands.cluster_faces import StartClusteringRunCommand
from photo_archiver.application.commands.import_draft import (
    ConfirmImportCommand,
    ParseImportDraftCommand,
)
from photo_archiver.application.commands.scan_and_register_photos import (
    ScanAndRegisterPhotosCommand,
)
from photo_archiver.application.commands.start_recognition_run import (
    StartRecognitionRunCommand,
)
from photo_archiver.application.commands.pairing import StartSuggestPairingsCommand
from photo_archiver.application.services.archive_executor import ArchiveExecutor
from photo_archiver.application.services.archive_path_builder_service import (
    ArchivePathBuilderService,
)
from photo_archiver.application.services.archive_photos_service import (
    ArchivePhotosService,
)
from photo_archiver.application.services.cluster_faces_service import (
    ClusterFacesService,
)
from photo_archiver.application.services.confirm_import_service import (
    ConfirmImportService,
)
from photo_archiver.application.services.identity_decision_service import (
    IdentityDecisionService,
)
from photo_archiver.application.services.pairing_workbench_service import (
    PairingWorkbenchService,
)
from photo_archiver.application.services.parse_import_draft_service import (
    ParseImportDraftService,
)
from photo_archiver.application.services.projection_reconciler import (
    ProjectionReconciler,
)
from photo_archiver.application.services.review_recognition_service import (
    ReviewRecognitionService,
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
from photo_archiver.ai.similarity_matcher import CosinePersonMatcher
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.domain import MatchStatus
from photo_archiver.domain.exceptions import (
    ManualDecisionProtectedError,
    PhotoNotClusteredError,
    ReviewAnchorAmbiguousError,
)
from photo_archiver.domain import FaceBox, FaceBoxEmbedding, FaceEmbedding
from photo_archiver.infrastructure.cosine_kernel import NumpyCosineSimilarityFactory
from photo_archiver.infrastructure.database.sqlite_unit_of_work import (
    SQLiteUnitOfWork,
)
from photo_archiver.infrastructure.filesystem.archive_file_store import (
    FilesystemArchiveFileStore,
)
from photo_archiver.infrastructure import LocalPhotoFileScanner as LocalScanner
from photo_archiver.infrastructure.filesystem.pillow_photo_metadata_reader import (
    PillowPhotoMetadataReader,
)
from photo_archiver.infrastructure.importers.roster_table_reader import (
    FileRosterTableReader,
)

_BASE = datetime(2024, 5, 1, 9, 0, 0)


class ScriptedDetector:
    """可控假检测器（仅替代 InsightFace 模型；业务链全部真实连接）。

    与 ``test_aud004_full_chain_regression._FakeDetector`` 同一约定。
    """

    def __init__(self, faces_by_name: dict[str, list[tuple[float, tuple[float, ...]]]]):
        self._faces_by_name = faces_by_name

    def detect(self, image: Path) -> list[FaceBoxEmbedding]:
        return self.detect_with_embeddings(image)

    def detect_with_embeddings(self, image: Path) -> list[FaceBoxEmbedding]:
        return [
            FaceBoxEmbedding(
                box=FaceBox(x1=0, y1=0, x2=8, y2=8, confidence=confidence),
                embedding=FaceEmbedding(vector=tuple(vector)),
            )
            for confidence, vector in self._faces_by_name.get(image.name, [])
        ]
VECTORS = {
    "a": (1.0, 0.0, 0.0, 0.0),
    "b": (0.0, 1.0, 0.0, 0.0),
    "c": (0.0, 0.0, 1.0, 0.0),
    "d": (0.0, 0.0, 0.0, 1.0),
}


def _photo_file(directory: Path, name: str, minutes: int) -> Path:
    """真实图片文件，mtime 决定 captured_at（与 AUD-004 同一约定）。"""
    path = directory / name
    Image.new("RGB", (8, 8), (len(name) * 30 % 255, 60, 120)).save(path)
    stamp = (_BASE + timedelta(minutes=minutes)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def _import_roster(repos, tmp_path: Path, rows: list[tuple[str, str]]):
    """真实两段式名单导入（CSV → 草稿 → 确认，写 people + roster_order）。"""
    csv_path = tmp_path / "roster.csv"
    lines = ["姓名,工号"]
    lines.extend(f"{name},{identity}" for name, identity in rows)
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    draft = ParseImportDraftService(
        FileRosterTableReader(), repos.import_batches, repos.people,
    ).execute(ParseImportDraftCommand(source_path=csv_path))
    result = ConfirmImportService(
        repos.import_batches, repos.people,
        unit_of_work=SQLiteUnitOfWork(repos._connection_provider),
    ).execute(ConfirmImportCommand(batch_id=draft.batch.id))
    assert result.errors == ()
    return [repos.people.find_by_id(pid) for pid in result.person_ids]


def _scan(repos, photos_dir: Path):
    return ScanAndRegisterPhotosService(
        LocalScanner(), repos.folders, repos.photos,
        metadata_reader=PillowPhotoMetadataReader(),
    ).execute(
        ScanAndRegisterPhotosCommand(folder_path=photos_dir)
    )


def _recognize(repos, detector, photos):
    return RunRecognitionService(
        detector=detector,
        # 真实 matcher：它读恒空的 person_embeddings → 不产生身份，
        # 身份只经 Assignment（S0 INV-3）。用 None 会破坏服务契约。
        matcher=CosinePersonMatcher(threshold=0.40),
        face_embedding_repository=repos.face_embeddings,
        recognition_repository=repos.recognition,
        recognition_run_repository=repos.recognition_runs,
        face_observation_repository=repos.face_observations,
        photo_repository=repos.photos,
    ).execute(
        StartRecognitionRunCommand(
            photo_ids=tuple(p.id for p in photos),
            images=tuple(p.path.raw_path for p in photos),
        )
    )


def _cluster(repos, run):
    return ClusterFacesService(
        repos.recognition_runs, repos.face_observations,
        repos.face_clusters, NumpyCosineSimilarityFactory(),
    ).execute(StartClusteringRunCommand(run.id))


def _suggest(repos, cluster_run):
    return SuggestPairingsService(
        repos.face_clusters, repos.face_observations, repos.people,
        repos.cluster_assignments, repos.person_face_samples,
        NumpyCosineSimilarityFactory(),
    ).execute(StartSuggestPairingsCommand(cluster_run_id=cluster_run.id))


def _reconciler(repos) -> ProjectionReconciler:
    return ProjectionReconciler(
        recognition_repository=repos.recognition,
        assignment_repository=repos.cluster_assignments,
        cluster_repository=repos.face_clusters,
        observation_repository=repos.face_observations,
    )


def _decisions(repos) -> IdentityDecisionService:
    return IdentityDecisionService(
        recognition_repository=repos.recognition,
        assignment_repository=repos.cluster_assignments,
        cluster_repository=repos.face_clusters,
        observation_repository=repos.face_observations,
        person_repository=repos.people,
        sample_repository=repos.person_face_samples,
        reconciler=_reconciler(repos),
        transaction_runner=repos._connection_provider.run_immediate,
    )


def _review(repos) -> ReviewRecognitionService:
    return ReviewRecognitionService(
        repos.recognition, identity_decision_service=_decisions(repos)
    )


def _workbench(repos) -> PairingWorkbenchService:
    return PairingWorkbenchService(
        repos.cluster_assignments, repos.face_clusters, repos.face_observations,
        repos.people, repos.recognition, repos.person_face_samples,
        reconciler=_reconciler(repos),
    )


def _archive(repos, archive_root: Path):
    return ArchivePhotosService(
        planner=ArchivePlannerStubbed(repos),
        executor=ArchiveExecutor(
            repos.archive_records,
            file_store=FilesystemArchiveFileStore(),
            unit_of_work=SQLiteUnitOfWork(repos._connection_provider),
        ),
        default_conflict_strategy="skip",
    ).execute(ArchivePhotosCommand(archive_root=Path(archive_root)))


def ArchivePlannerStubbed(repos):
    """真实 ArchivePlanner（归档是本链的最终消费端，不得替身）。"""
    from photo_archiver.application.services.archive_planner import ArchivePlanner

    return ArchivePlanner(
        path_builder=ArchivePathBuilderService(),
        person_repository=repos.people,
        photo_repository=repos.photos,
        recognition_repository=repos.recognition,
        archive_record_repository=repos.archive_records,
    )


def _cluster_of_photo(repos, photo_id) -> object:
    """照片在其所在代际的簇（单人照片场景 = 唯一簇）。"""
    for observation in repos.face_observations.list_by_photo(photo_id):
        clusters = repos.face_clusters.list_clusters_of_observation(observation.id)
        if clusters:
            return clusters[0]
    raise AssertionError("photo is not clustered")


def test_import_to_review_to_archive_single_person(tmp_path: Path) -> None:
    """主闭环：真实导入 → 扫描 → 识别 → 聚类 → 审核批准 → 投影 → 归档落盘。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    (zhang,) = _import_roster(repos, tmp_path, [("张三", "E001")])

    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    _photo_file(photos_dir, "portrait.jpg", 0)
    scan = _scan(repos, photos_dir)
    assert scan.registered_count == 1
    photos = repos.photos.list_all()
    assert len(photos) == 1

    detector = ScriptedDetector({photos[0].original_name: [(0.9, VECTORS["a"])]})
    run = _recognize(repos, detector, photos)
    assert run.status == "completed" and run.face_count == 1

    cluster_run = _cluster(repos, run)
    assert cluster_run.cluster_count == 1
    assert len(repos.recognition.list_pending()) == 1, "识别期产出 pending 占位行"

    # 审核批准：带身份 → Assignment(review) → Projection
    pending = repos.recognition.list_pending()[0]
    approved = _review(repos).approve(pending.id, zhang.id)
    assert approved is not None
    assert approved.assignment_id is not None, "S1：新 approved 必须带支撑引用"
    assert repos.recognition.list_pending() == [], "pending 被复用出队"

    # 样本沉淀（S0 §7.4：人工确认 → 可靠样本）
    assert len(repos.person_face_samples.list_by_person(zhang.id)) == 1

    # 归档：文件真实落进 张三/ 日期/ 目录
    result = _archive(repos, tmp_path / "archive")
    assert result.archived_count == 1
    archived = repos.archive_records.list_all()
    assert len(archived) == 1
    assert archived[0].person_id == zhang.id
    target = Path(str(archived[0].target_archive_root)) / str(
        archived[0].target_person_name
    ) / str(archived[0].target_event_or_date) / str(archived[0].target_original_name)
    assert target.exists(), "归档文件必须真实落盘"


def test_review_rejects_unclustered_photo_end_to_end(tmp_path: Path) -> None:
    """D-2=B 在真实链上：照片已扫描入库但未聚类 → 审核 fail-closed、零副作用。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    (zhang,) = _import_roster(repos, tmp_path, [("张三", "E001")])
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    _photo_file(photos_dir, "pending.jpg", 0)
    _scan(repos, photos_dir)
    photos = repos.photos.list_all()
    # 遗留链产物：pending 行存在（模拟 D-1/识别期占位），但**不聚类**
    from photo_archiver.domain import RecognitionResult

    pending_row = RecognitionResult(photo_id=photos[0].id, confidence=None)
    repos.recognition.add(pending_row)

    with pytest.raises(PhotoNotClusteredError):
        _review(repos).approve(pending_row.id, zhang.id)

    assert repos.recognition.find_by_id(pending_row.id).status is MatchStatus.PENDING
    assert repos.recognition.list_projections() == []
    assert repos.person_face_samples.list_by_person(zhang.id) == []


def test_multi_person_photo_archives_to_both_person_dirs(tmp_path: Path) -> None:
    """多人照片闭环：一张合影经审核分别人工确认 → 两个人员目录各一份。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    zhang, li = _import_roster(
        repos, tmp_path, [("张三", "E001"), ("李四", "E002")]
    )
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    _photo_file(photos_dir, "group.jpg", 0)
    _scan(repos, photos_dir)
    photos = repos.photos.list_all()

    detector = ScriptedDetector({
        photos[0].original_name: [(0.9, VECTORS["a"]), (0.8, VECTORS["b"])]
    })
    run = _recognize(repos, detector, photos)
    assert run.face_count == 2
    cluster_run = _cluster(repos, run)
    assert cluster_run.cluster_count == 2, "合影两脸分落两簇"

    # 同代际双簇 → Review 必须显式给锚点（禁止 Top-1 推断）
    pending_row = repos.recognition.list_pending()[0]
    review = _review(repos)
    with pytest.raises(ReviewAnchorAmbiguousError):
        review.approve(pending_row.id, zhang.id)

    from photo_archiver.domain import RecognitionResult

    second_row = RecognitionResult(photo_id=photos[0].id, confidence=None)
    repos.recognition.add(second_row)

    cluster_a = _cluster_of_photo(repos, photos[0].id)
    cluster_b = next(
        c for c in repos.face_clusters.list_clusters(cluster_run.id) if c.id != cluster_a.id
    )
    review.approve(pending_row.id, zhang.id, cluster_id=cluster_a.id)
    review.approve(second_row.id, li.id, cluster_id=cluster_b.id)

    # 两个投影共存（不同 pair）
    assert repos.recognition.find_projection(photos[0].id, zhang.id) is not None
    assert repos.recognition.find_projection(photos[0].id, li.id) is not None

    # 归档：同一文件在两个人员目录各一份
    result = _archive(repos, tmp_path / "archive")
    assert result.archived_count == 2
    records = repos.archive_records.list_all()
    assert {r.person_id for r in records} == {zhang.id, li.id}
    assert {r.target_person_name for r in records} == {"张三", "李四"}
    for record in records:
        target = (
            Path(str(record.target_archive_root))
            / str(record.target_person_name)
            / str(record.target_event_or_date)
            / str(record.target_original_name)
        )
        assert target.exists()


def test_review_overrides_cold_start_suggestion_end_to_end(tmp_path: Path) -> None:
    """冷启动建议 → 人工改判：机器建议 terminal、review 接管、归档到新人员。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    zhang, li = _import_roster(
        repos, tmp_path, [("张三", "E001"), ("李四", "E002")]
    )
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    _photo_file(photos_dir, "portrait.jpg", 0)
    _scan(repos, photos_dir)
    photos = repos.photos.list_all()
    run = _recognize(repos, ScriptedDetector(
        {photos[0].original_name: [(0.9, VECTORS["a"])]}
    ), photos)
    cluster_run = _cluster(repos, run)

    # 冷启动位次建议：照片排第 1 → 张三
    summary = _suggest(repos, cluster_run)
    assert summary.ordered == 1
    suggestion = repos.cluster_assignments.list_active_by_cluster_run(cluster_run.id)[0]
    assert suggestion.status == "suggested"
    assert suggestion.source == "ordered_suggestion"
    assert suggestion.person_id == zhang.id

    # 人工审核改判给李四
    pending_row = repos.recognition.list_pending()[0]
    approved = _review(repos).approve(pending_row.id, li.id)
    assert approved is not None and approved.person_id == li.id

    cluster = _cluster_of_photo(repos, photos[0].id)
    decisions = repos.cluster_assignments.list_by_cluster(cluster.id)
    machine_rows = [d for d in decisions if d.source == "ordered_suggestion"]
    review_rows = [d for d in decisions if d.source == "review"]
    assert len(machine_rows) == 1 and machine_rows[0].status == "unassigned", (
        "机器建议被人工确认后必须 terminal"
    )
    assert len(review_rows) == 1 and review_rows[0].status == "confirmed"
    assert review_rows[0].person_id == li.id

    result = _archive(repos, tmp_path / "archive")
    assert result.archived_count == 1
    record = repos.archive_records.list_all()[0]
    assert record.target_person_name == "李四", "归档必须落到人工改判后的人员"
    assert repos.recognition.find_projection(photos[0].id, zhang.id) is None


def test_review_creates_samples_enabling_second_batch_suggestion(
    tmp_path: Path,
) -> None:
    """业务闭环：审核 → 样本 → 第二批新照片的样本匹配建议可用。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    (zhang,) = _import_roster(repos, tmp_path, [("张三", "E001")])

    first_dir = tmp_path / "batch1"
    first_dir.mkdir()
    _photo_file(first_dir, "p1.jpg", 0)
    _scan(repos, first_dir)
    photos = repos.photos.list_all()
    run = _recognize(repos, ScriptedDetector(
        {photos[0].original_name: [(0.9, VECTORS["a"])]}
    ), photos)
    _cluster(repos, run)

    pending_row = repos.recognition.list_pending()[0]
    _review(repos).approve(pending_row.id, zhang.id)
    assert len(repos.person_face_samples.list_by_person(zhang.id)) == 1, (
        "人工确认沉淀可靠样本（冷启动样本来源）"
    )

    # 第二批：全新照片，同一张脸 → 样本匹配应命中（不再靠名单顺序）
    second_dir = tmp_path / "batch2"
    second_dir.mkdir()
    _photo_file(second_dir, "p2.jpg", 60)
    _scan(repos, second_dir)
    new_photo = [p for p in repos.photos.list_all() if p.original_name == "p2.jpg"][0]

    run2 = _recognize(repos, ScriptedDetector(
        {new_photo.original_name: [(0.9, VECTORS["a"])]}
    ), [new_photo])
    cluster_run2 = _cluster(repos, run2)
    summary = _suggest(repos, cluster_run2)

    assert summary.sample_matched == 1, "第二批应命中样本匹配（有真实证据）"
    suggestion = repos.cluster_assignments.list_active_by_cluster_run(cluster_run2.id)[0]
    assert suggestion.source == "sample_match"
    assert suggestion.person_id == zhang.id
    assert suggestion.score is not None and suggestion.score > 0.9


def test_machine_cannot_retract_review_assignment_end_to_end(tmp_path: Path) -> None:
    """INV-4 端到端回归：真实链产出的 review 决策，机器 actor 撤不掉。"""
    from photo_archiver.application.commands.pairing import UnassignClusterCommand
    from photo_archiver.domain.entities.cluster_assignment import MACHINE_ACTOR

    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    (zhang,) = _import_roster(repos, tmp_path, [("张三", "E001")])
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    _photo_file(photos_dir, "portrait.jpg", 0)
    _scan(repos, photos_dir)
    photos = repos.photos.list_all()
    run = _recognize(repos, ScriptedDetector(
        {photos[0].original_name: [(0.9, VECTORS["a"])]}
    ), photos)
    _cluster(repos, run)

    pending_row = repos.recognition.list_pending()[0]
    _review(repos).approve(pending_row.id, zhang.id)
    cluster = _cluster_of_photo(repos, photos[0].id)

    with pytest.raises(ManualDecisionProtectedError):
        _workbench(repos).unassign(
            UnassignClusterCommand(cluster.id), actor=MACHINE_ACTOR
        )

    latest = repos.cluster_assignments.list_latest_decision(cluster.id)
    assert latest.status == "confirmed" and latest.source == "review"
    assert repos.recognition.find_projection(photos[0].id, zhang.id) is not None
