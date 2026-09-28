"""AUD-004 — 全链贯通回归（Stage 12A）.

一条真实、可重复的核心业务链测试（真实 SQLite + 真实仓储 + 真实应用服务，
仅 AI 模型按任务书允许以可控假检测器替代——检测嵌入由测试给定、逐照片映射）：

    两段式名单导入（Parse→Confirm，真实 CSV）
    → 扫描登记（真实图片文件 + Pillow 元数据 + 内容哈希）
    → 识别运行（逐脸观测 + 兼容 PENDING 行，person_id=NULL）
    → FaceCluster（真实两段式聚类 + sort_key）
    → 建议（冷启动 ordered_suggestion；无样本时不产生 similarity_suggestion）
    → 人工确认（confirmed + (person, photo) 兼容投影 + 样本沉淀）
    → ArchivePlanner（身份来自人工确认结果）
    → ArchiveExecutor（真实文件复制 + 归档记录）

接缝验证优先于模块内部逻辑（各模块内部已有专项覆盖）：
- 数据接缝：导入产出 roster_order → 配对排序；扫描产出 photo/raw_path → 识别输入；
  观测嵌入 → 聚类成员；兼容 APPROVED → 归档计划。
- 状态接缝：suggested → confirmed → archivable → archived；FAILED 可重试。
- 身份接缝：FaceCluster → Person → Photo → ArchiveRecord 不错位（含 person_id）。
- 幂等接缝：重复 execute 不重复归档；全批重跑不覆盖人工决定、不重复建兼容行。
"""

import os
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from photo_archiver.ai.similarity_matcher import CosinePersonMatcher
from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.commands.archive import ArchivePhotosCommand
from photo_archiver.application.commands.cluster_faces import StartClusteringRunCommand
from photo_archiver.application.commands.import_draft import (
    ConfirmImportCommand,
    ParseImportDraftCommand,
)
from photo_archiver.application.commands.pairing import (
    ConfirmAssignmentCommand,
    StartSuggestPairingsCommand,
)
from photo_archiver.application.commands.scan_and_register_photos import (
    ScanAndRegisterPhotosCommand,
)
from photo_archiver.application.commands.start_recognition_run import (
    StartRecognitionRunCommand,
)
from photo_archiver.application.services.archive_photos_service import (
    ArchivePhotosService,
)
from photo_archiver.application.services.archive_planner import ArchivePlanner
from photo_archiver.application.services.cluster_faces_service import ClusterFacesService
from photo_archiver.application.services.confirm_import_service import ConfirmImportService
from photo_archiver.application.services.parse_import_draft_service import (
    ParseImportDraftService,
)
from photo_archiver.application.services.pairing_workbench_service import (
    PairingWorkbenchService,
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
from photo_archiver.application.services.archive_executor import ArchiveExecutor
from photo_archiver.application.services.archive_path_builder_service import (
    ArchivePathBuilderService,
)
from photo_archiver.domain import (
    ArchiveStatus,
    FaceBox,
    FaceBoxEmbedding,
    FaceEmbedding,
)
from photo_archiver.infrastructure import LocalPhotoFileScanner
from photo_archiver.infrastructure.filesystem.pillow_photo_metadata_reader import (
    PillowPhotoMetadataReader,
)
from photo_archiver.infrastructure.cosine_kernel import NumpyCosineSimilarityFactory
from photo_archiver.infrastructure.database.sqlite_unit_of_work import SQLiteUnitOfWork
from photo_archiver.infrastructure.importers.roster_table_reader import (
    FileRosterTableReader,
)

# 四个相互正交的 4 维向量：同向量聚为一簇，异向量互不合并。
V_A = (1.0, 0.0, 0.0, 0.0)
V_B = (0.0, 1.0, 0.0, 0.0)
V_C = (0.0, 0.0, 1.0, 0.0)


class _FakeDetector:
    """可控假检测器（替代 InsightFace）：按图片文件名返回预定人脸嵌入。

    仅替代重量级 AI 模型本身；识别/聚类/配对/归档业务链全部真实连接。
    """

    def __init__(self, faces_by_name: dict[str, list[tuple[float, tuple[float, ...]]]]):
        self._faces_by_name = faces_by_name

    def detect(self, image: Path) -> list[FaceBoxEmbedding]:
        return self.detect_with_embeddings(image)

    def detect_with_embeddings(self, image: Path) -> list[FaceBoxEmbedding]:
        faces = self._faces_by_name.get(image.name, [])
        return [
            FaceBoxEmbedding(
                box=FaceBox(x1=0, y1=0, x2=8, y2=8, confidence=confidence),
                embedding=FaceEmbedding(vector=tuple(vector)),
            )
            for confidence, vector in faces
        ]


def _make_image(directory: Path, name: str, captured: datetime) -> Path:
    """Create a real image file whose mtime (captured_at 兜底) is deterministic."""
    path = directory / name
    Image.new("RGB", (8, 8), (len(name) * 30 % 255, 60, 120)).save(path)
    stamp = captured.timestamp()
    os.utime(path, (stamp, stamp))
    return path


def _import_roster(repos, tmp_path: Path, rows: list[tuple[str, str, str]]):
    """真实两段式导入：解析草稿 → 确认（单事务写 people + roster_order）。"""
    csv_path = tmp_path / "roster.csv"
    lines = ["姓名,工号,部门"]
    lines.extend(f"{name},{identity},{department}" for name, identity, department in rows)
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    parse = ParseImportDraftService(
        FileRosterTableReader(), repos.import_batches, repos.people,
    )
    draft = parse.execute(ParseImportDraftCommand(source_path=csv_path))
    confirm = ConfirmImportService(
        repos.import_batches, repos.people,
        unit_of_work=SQLiteUnitOfWork(repos._connection_provider),
    )
    result = confirm.execute(ConfirmImportCommand(batch_id=draft.batch.id))
    assert result.errors == ()
    return [repos.people.find_by_id(pid) for pid in result.person_ids]


def _scan(repos, photos_dir: Path):
    service = ScanAndRegisterPhotosService(
        LocalPhotoFileScanner(), repos.folders, repos.photos,
        metadata_reader=PillowPhotoMetadataReader(),
    )
    result = service.execute(ScanAndRegisterPhotosCommand(folder_path=photos_dir))
    photos = repos.photos.list_all()
    return result, photos


def _recognize(repos, detector, photos):
    service = RunRecognitionService(
        detector=detector,
        matcher=CosinePersonMatcher(threshold=0.40),
        face_embedding_repository=repos.face_embeddings,
        recognition_repository=repos.recognition,
        recognition_run_repository=repos.recognition_runs,
        face_observation_repository=repos.face_observations,
        photo_repository=repos.photos,
    )
    return service.execute(StartRecognitionRunCommand(
        photo_ids=tuple(photo.id for photo in photos),
        images=tuple(photo.path.raw_path for photo in photos),
    ))


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


def _workbench(repos):
    return PairingWorkbenchService(
        repos.cluster_assignments, repos.face_clusters, repos.face_observations,
        repos.people, repos.recognition, repos.person_face_samples,
    )


def _confirm_all(repos, cluster_run):
    workbench = _workbench(repos)
    return [
        workbench.confirm(ConfirmAssignmentCommand(assignment_id=assignment.id))
        for assignment in repos.cluster_assignments.list_active_by_cluster_run(
            cluster_run.id,
        )
        if assignment.status == "suggested"
    ]


def _archive(repos, archive_root: Path):
    service = ArchivePhotosService(
        planner=ArchivePlanner(
            path_builder=ArchivePathBuilderService(),
            person_repository=repos.people,
            photo_repository=repos.photos,
            recognition_repository=repos.recognition,
            archive_record_repository=repos.archive_records,
        ),
        executor=ArchiveExecutor(
            repos.archive_records,
            unit_of_work=SQLiteUnitOfWork(repos._connection_provider),
        ),
        default_conflict_strategy="skip",
    )
    return service.execute(ArchivePhotosCommand(archive_root=Path(archive_root)))


def _cluster_photo_names(repos, run, cluster_run) -> dict:
    """identity seam 辅助：cluster_id → 成员观测所属照片的文件名。"""
    observations = {o.id: o for o in repos.face_observations.list_by_run(run.id)}
    members = repos.face_clusters.list_members(cluster_run.id)
    photo_by_observation = {}
    photos = repos.photos.list_all()
    name_by_photo_id = {photo.id: photo.original_name for photo in photos}
    for member in members:
        observation = observations[member.observation_id]
        photo_by_observation[member.cluster_id] = name_by_photo_id[observation.photo_id]
    return photo_by_observation


def test_cold_start_full_chain_import_to_archive_with_idempotent_rerun(tmp_path):
    """Scenario A + D：标准冷启动全链 + 重复执行/全批重跑的幂等行为。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    _make_image(photos_dir, "alpha.jpg", datetime(2026, 1, 1, 12, 0, 0))
    _make_image(photos_dir, "beta.jpg", datetime(2026, 2, 1, 12, 0, 0))
    detector = _FakeDetector({
        "alpha.jpg": [(0.9, V_A)],
        "beta.jpg": [(0.9, V_B)],
    })

    # 1. 两段式名单导入（真实 CSV → 草稿 → 确认）
    persons = _import_roster(
        repos, tmp_path, [("张三", "E001", "研发部"), ("李四", "E002", "市场部")],
    )
    zhang, li = persons
    assert [person.roster_order for person in persons] == [1, 2]

    # 2. 扫描登记（真实文件）
    scan_result, photos = _scan(repos, photos_dir)
    assert scan_result.registered_count == 2 and len(photos) == 2

    # 3. 识别运行：逐脸观测 + 兼容 PENDING 行（person_id=NULL——新链语义）
    run = _recognize(repos, detector, photos)
    assert run.face_count == 2
    # 数据接缝：run 快照携带照片 captured_at（聚类时间排序的数据源，AUD-004 修复）
    snapshots = repos.recognition_runs.list_run_photos(run.id)
    assert all(snapshot.captured_at is not None for snapshot in snapshots)
    pending = repos.recognition.list_pending()
    assert len(pending) == 2
    assert all(row.person_id is None for row in pending)

    # 4. 聚类：两个正交向量 → 两个簇
    cluster_run = _cluster(repos, run)
    clusters = repos.face_clusters.list_clusters(cluster_run.id)
    assert len(clusters) == 2

    # 5. 冷启动建议：无样本 → 仅 ordered_suggestion（sort_key/roster_order 仅排序）
    summary = _suggest(repos, cluster_run)
    assert (summary.suggestions, summary.sample_matched, summary.ordered) == (2, 0, 2)
    cluster_photo = _cluster_photo_names(repos, run, cluster_run)
    expected_identity = {"alpha.jpg": zhang.id, "beta.jpg": li.id}
    for cluster in clusters:
        row = [
            assignment for assignment in repos.cluster_assignments.list_by_cluster(cluster.id)
            if assignment.status == "suggested"
        ][0]
        assert row.source == "ordered_suggestion"
        assert row.score is None                          # 位次不是相似度证据
        assert row.person_id == expected_identity[cluster_photo[cluster.id]]

    # 6. 人工确认 → confirmed + 兼容 APPROVED（身份来自人工决定）
    confirm_results = _confirm_all(repos, cluster_run)
    assert len(confirm_results) == 2
    assert all(result.compat_results_written == 1 for result in confirm_results)
    approved_zhang = repos.recognition.list_approved_by_person(zhang.id)
    assert len(approved_zhang) == 1
    counts = repos.recognition.read_workspace_counts()
    assert counts.archivable_count == 2

    # 7. 归档规划 + 执行（真实 executor，真实文件落盘）
    archive_root = tmp_path / "archive"
    result = _archive(repos, archive_root)
    assert (result.planned_count, result.archived_count, result.failed_count) == (2, 2, 0)
    assert next(archive_root.rglob("alpha.jpg"), None) is not None
    assert next(archive_root.rglob("beta.jpg"), None) is not None
    assert (archive_root / "张三").is_dir() and (archive_root / "李四").is_dir()

    # 身份接缝：归档记录的 person_id/target_person_name 与人工确认一致
    records = repos.archive_records.list_all()
    assert len(records) == 2
    by_name = {record.target_original_name: record for record in records}
    assert by_name["alpha.jpg"].status is ArchiveStatus.ARCHIVED
    assert by_name["alpha.jpg"].person_id == zhang.id
    assert by_name["alpha.jpg"].target_person_name == "张三"
    assert by_name["beta.jpg"].person_id == li.id
    counts = repos.recognition.read_workspace_counts()
    assert counts.archivable_count == 0                   # 已归档 → 计数清零

    # 8. Scenario D-1：重复 execute → planner 去重，零重复归档
    result_again = _archive(repos, archive_root)
    assert result_again.planned_count == 0
    assert len(repos.archive_records.list_all()) == 2

    # 9. Scenario D-2：全批重跑（新识别代际）不覆盖人工决定、不重复归档
    run2 = _recognize(repos, detector, photos)            # 新观测（新 id）
    cluster_run2 = _cluster(repos, run2)
    summary2 = _suggest(repos, cluster_run2)
    # 首批确认已沉淀样本 → 第二代建议自动切换到样本相似度路径（AUD-017 Option C 语义）：
    # 同嵌入余弦 1.0 >= 0.40 → sample_match，冷启动位次不再参与（存在真证据时不退回位次）
    assert (summary2.suggestions, summary2.sample_matched, summary2.ordered) == (2, 2, 0)
    for cluster in repos.face_clusters.list_clusters(cluster_run2.id):
        row = [
            assignment for assignment in repos.cluster_assignments.list_by_cluster(cluster.id)
            if assignment.status == "suggested"
        ][0]
        assert row.source == "sample_match" and row.score == pytest.approx(1.0)
    confirm_results2 = _confirm_all(repos, cluster_run2)
    assert len(confirm_results2) == 2
    assert all(result.samples_written == 1 for result in confirm_results2)  # 新观测合法沉淀
    assert len(repos.recognition.list_approved_by_person(zhang.id)) == 1  # 兼容 (person,photo) 幂等
    result3 = _archive(repos, archive_root)
    assert result3.planned_count == 0
    assert len(repos.archive_records.list_all()) == 2     # 归档零重复
    assert len(repos.people.list_all()) == 2              # 名单未被重跑改动


def test_clusters_fewer_than_persons_no_forced_identity(tmp_path):
    """Scenario B：簇 < 人 → 不强制制造身份，未配对人员保留人工处置。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    _make_image(photos_dir, "twin.jpg", datetime(2026, 1, 1, 12, 0, 0))
    detector = _FakeDetector({"twin.jpg": [(0.9, V_A), (0.9, V_A)]})  # 同人两脸

    persons = _import_roster(
        repos, tmp_path, [("张三", "E001", "研发部"), ("李四", "E002", "市场部")],
    )
    zhang, li = persons
    scan_result, photos = _scan(repos, photos_dir)
    assert scan_result.registered_count == 1
    run = _recognize(repos, detector, photos)
    assert run.face_count == 2
    cluster_run = _cluster(repos, run)
    clusters = repos.face_clusters.list_clusters(cluster_run.id)
    assert len(clusters) == 1                             # 同向量 → 一簇两成员

    summary = _suggest(repos, cluster_run)
    assert (summary.suggestions, summary.ordered) == (1, 1)
    assert summary.persons_without_cluster == 1           # 李四无簇，不强配

    confirm_results = _confirm_all(repos, cluster_run)
    assert len(confirm_results) == 1
    assert confirm_results[0].samples_written == 2        # 整簇两成员沉淀
    assert len(repos.recognition.list_approved_by_person(zhang.id)) == 1
    assert len(repos.recognition.list_approved_by_person(li.id)) == 0

    archive_root = tmp_path / "archive"
    result = _archive(repos, archive_root)
    assert result.archived_count == 1
    records = repos.archive_records.list_all()
    assert len(records) == 1
    assert records[0].person_id == zhang.id               # 只有被确认者归档
    assert len(repos.people.list_all()) == 2              # 李四仍在名单待人工处置


def test_clusters_more_than_persons_unmatched_cluster_not_claimed(tmp_path):
    """Scenario C：簇 > 人 → 多余簇不被错误归属，已确认部分照常归档。"""
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    _make_image(photos_dir, "a.jpg", datetime(2026, 1, 1, 12, 0, 0))
    _make_image(photos_dir, "b.jpg", datetime(2026, 2, 1, 12, 0, 0))
    _make_image(photos_dir, "c.jpg", datetime(2026, 3, 1, 12, 0, 0))
    detector = _FakeDetector({
        "a.jpg": [(0.9, V_A)],
        "b.jpg": [(0.9, V_B)],
        "c.jpg": [(0.9, V_C)],
    })

    persons = _import_roster(repos, tmp_path, [("张三", "E001", ""), ("李四", "E002", "")])
    zhang, li = persons
    scan_result, photos = _scan(repos, photos_dir)
    assert scan_result.registered_count == 3
    run = _recognize(repos, detector, photos)
    cluster_run = _cluster(repos, run)
    assert len(repos.face_clusters.list_clusters(cluster_run.id)) == 3

    summary = _suggest(repos, cluster_run)
    assert (summary.suggestions, summary.ordered) == (2, 2)
    assert summary.unmatched_clusters == 1                # 第三簇无人可配

    confirm_results = _confirm_all(repos, cluster_run)
    assert len(confirm_results) == 2

    archive_root = tmp_path / "archive"
    result = _archive(repos, archive_root)
    assert result.archived_count == 2
    records = repos.archive_records.list_all()
    assert {record.person_id for record in records} == {zhang.id, li.id}
    # 未确认的第三张照片：识别期 PENDING 兼容行保留待人工审核，且无 APPROVED 归属
    pending_rows = repos.recognition.list_pending()
    assert len(pending_rows) == 3          # 确认不改写识别期 PENDING 行（新增 APPROVED 行）
    approved_photo_ids = {
        row.photo_id
        for person in (zhang, li)
        for row in repos.recognition.list_approved_by_person(person.id)
    }
    unclaimed = [photo for photo in repos.photos.list_all() if photo.original_name == "c.jpg"]
    assert unclaimed[0].id not in approved_photo_ids   # 未确认簇未被错误归属


def test_execution_partial_failure_is_isolated_and_retryable(tmp_path):
    """§9 中间失败点：逐项 OSError 隔离（当前语义），FAILED 不阻断重试。

    注意：本用例钉定的是"单项失败隔离 + 重试"语义；批级事务与文件复制的
    部分失败不一致属 AUD-015（不在本阶段修复，语义以本测试记录为准）。
    """
    repos = build_sqlite_repositories(tmp_path / "db.sqlite3")
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    _make_image(photos_dir, "alpha.jpg", datetime(2026, 1, 1, 12, 0, 0))
    beta_path = _make_image(photos_dir, "beta.jpg", datetime(2026, 2, 1, 12, 0, 0))
    detector = _FakeDetector({
        "alpha.jpg": [(0.9, V_A)],
        "beta.jpg": [(0.9, V_B)],
    })

    persons = _import_roster(repos, tmp_path, [("张三", "E001", ""), ("李四", "E002", "")])
    zhang, li = persons
    scan_result, photos = _scan(repos, photos_dir)
    assert scan_result.registered_count == 2
    run = _recognize(repos, detector, photos)
    cluster_run = _cluster(repos, run)
    _suggest(repos, cluster_run)
    _confirm_all(repos, cluster_run)

    # 中间失败：beta 源文件缺失 → 该项 FAILED，批内其余项照常归档
    beta_path.unlink()
    archive_root = tmp_path / "archive"
    result = _archive(repos, archive_root)
    assert (result.archived_count, result.failed_count) == (1, 1)
    records = {record.target_original_name: record for record in repos.archive_records.list_all()}
    assert records["alpha.jpg"].status is ArchiveStatus.ARCHIVED
    assert records["beta.jpg"].status is ArchiveStatus.FAILED
    assert records["beta.jpg"].error                      # 失败原因可读
    assert next(archive_root.rglob("alpha.jpg"), None) is not None

    # 恢复后重试：FAILED 不拦截重试，成功项被去重
    _make_image(photos_dir, "beta.jpg", datetime(2026, 2, 1, 12, 0, 0))
    result_retry = _archive(repos, archive_root)
    assert result_retry.archived_count == 1               # 仅 beta 重试成功
    assert next(archive_root.rglob("beta.jpg"), None) is not None
    statuses = [
        record.status for record in repos.archive_records.list_all()
        if record.target_original_name == "beta.jpg"
    ]
    assert statuses.count(ArchiveStatus.FAILED) == 1 and statuses.count(ArchiveStatus.ARCHIVED) == 1
    assert repos.recognition.list_approved_by_person(zhang.id)[0].photo_id is not None
