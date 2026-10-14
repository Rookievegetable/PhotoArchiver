"""S-B-6 共享 fixture 构建器（无测试函数；供四个 sb6 验收测试文件导入）.

Fixture 声明（R3 §4.8 / T-N）：本模块构建的全部照片 / 识别 run / 聚类 /
数据集 / Snapshot / Manifest / Attestation / Artifact 均为**测试 fixture**，
不等于真实生产预测或生产工件；生产库与运行时目录零接触。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID
import uuid as uuid_mod

from tests.integration.test_sb1_reference_intake import (
    _cluster,
    _evaluation_dataset_id,
    _import_people,
    _recognize,
    _scan,
)
from tests.integration.test_sb3_reference_eligibility import (
    _detector,
    _guard,
    _make_unique_image,
)
from tests.integration.test_sb4_reference_snapshot import (
    _build as _build_snapshot,
    _confirmed_reference,
    _snapshot_service,
)

from photo_archiver.app.repositories import build_sqlite_repositories
from photo_archiver.application.services.isolation_attestation_service import (
    IsolationAttestationService,
)
from photo_archiver.application.services.mechanical_scoring_service import (
    MechanicalScoringService,
)
from photo_archiver.application.services.prediction_artifact_v2_service import (
    PredictionArtifactV2Service,
)
from photo_archiver.application.services.sb6_contract import (
    PredictionRecordV2,
    SB_SCORER_VERSION,
)
from photo_archiver.application.services.target_manifest_service import (
    ManifestCreationResult,
    TargetManifestService,
)
from photo_archiver.domain.entities.calibration_annotation import (
    CalibrationDataset,
    CalibrationGroundTruth,
)
from photo_archiver.infrastructure.filesystem.snapshot_store import (
    FilesystemSnapshotStore,
)
from photo_archiver.infrastructure.image.content_hash_calculator import (
    ContentHashCalculator,
)

VERSION = "pilot-sb3"  # 与复用基建（test_sb3/test_sb4 助手）的冻结版本号一致

DEFAULT_EVAL_FACES = {
    "e1.jpg": [(0.9, (1.0, 0, 0, 0))],
    "e2.jpg": [(0.9, (0, 1.0, 0, 0))],
    "e3.jpg": [(0.9, (0, 0, 1.0, 0))],
}
DEFAULT_NAMES = ["张三", "李四", "王五"]


@dataclass(frozen=True, slots=True)
class EvalSide:
    run: object
    cluster_run: object
    clusters: list
    people: list
    dataset: CalibrationDataset


@dataclass(frozen=True, slots=True)
class FullSetup:
    """评估侧 + Manifest + 参考侧 Snapshot 的完整 fixture 集."""

    eval_side: EvalSide
    manifest_result: ManifestCreationResult
    snapshot_result: object
    snapshot_path: Path
    ref_person: object

    @property
    def dataset(self) -> CalibrationDataset:
        return self.eval_side.dataset

    @property
    def cluster_run(self):
        return self.eval_side.cluster_run

    @property
    def clusters(self) -> list:
        return self.eval_side.clusters

    @property
    def people(self) -> list:
        return self.eval_side.people


def make_repos(tmp_path: Path):
    return build_sqlite_repositories(tmp_path / "db.sqlite3")


def build_eval_side(
    repos,
    tmp_path: Path,
    faces_by_name=None,
    names=None,
    gt_verdicts=None,
    *,
    version: str = VERSION,
) -> EvalSide:
    """评估侧：独立目录 → 识别 run → 聚类 run → 数据集 + GT（按 ordinal 对齐）.

    ``gt_verdicts``：每簇一个 verdict（``None`` = 该簇不写入 GT）。
    """
    faces_by_name = faces_by_name or DEFAULT_EVAL_FACES
    names = names or DEFAULT_NAMES
    eval_dir = tmp_path / f"eval_{uuid_mod.uuid4().hex[:8]}"
    eval_dir.mkdir()
    for index, name in enumerate(faces_by_name):
        _make_unique_image(eval_dir, name, 1 + index)
    photos = _scan(repos, eval_dir)
    run = _recognize(repos, _detector(faces_by_name), photos)
    cluster_run = _cluster(repos, run)
    clusters = sorted(
        repos.face_clusters.list_clusters(cluster_run.id), key=lambda c: c.ordinal
    )
    people = _import_people(repos, tmp_path, names)
    dataset = CalibrationDataset(
        version=version,
        cluster_count=len(clusters),
        usable_count=len(clusters),
        excluded_count=0,
    )
    repos.calibration_annotations.add_dataset(dataset)
    for index, cluster in enumerate(clusters):
        verdict = gt_verdicts[index] if gt_verdicts is not None else "person"
        if verdict is None:
            continue
        person_id = None
        if verdict == "person" and people:
            person_id = people[index % len(people)].id
        repos.calibration_annotations.add_ground_truth(
            CalibrationGroundTruth(
                cluster_id=cluster.id,
                verdict=verdict,
                resolution="expert",
                source_annotation_ids=(uuid_mod.uuid4(),),
                annotator_count=1,
                person_id=person_id,
                difficulty_reason="other" if verdict == "undecidable" else None,
                dataset_id=dataset.id,
                dataset_version=version,
            )
        )
    return EvalSide(
        run=run, cluster_run=cluster_run, clusters=clusters, people=people,
        dataset=dataset,
    )


def manifest_service(repos) -> TargetManifestService:
    return TargetManifestService(
        repos.calibration_annotations,
        repos.face_clusters,
        repos.face_observations,
        repos.photos,
        FilesystemSnapshotStore(),
    )


def build_manifest(
    repos,
    tmp_path: Path,
    eval_side: EvalSide,
    *,
    name: str = "manifest.json",
    version: str = VERSION,
) -> tuple[ManifestCreationResult, TargetManifestService]:
    service = manifest_service(repos)
    result = service.build_manifest(
        eval_side.dataset.id,
        version,
        eval_side.cluster_run.id,
        tmp_path / "manifests" / name,
    )
    return result, service


def full_setup(
    repos, tmp_path: Path, *, gt_verdicts=None, version: str = VERSION
) -> FullSetup:
    """评估侧（默认 3 人）+ Manifest + 一条合法参考（张三）+ Snapshot."""
    eval_side = build_eval_side(repos, tmp_path, gt_verdicts=gt_verdicts, version=version)
    manifest_result, _service = build_manifest(
        repos, tmp_path, eval_side, version=version
    )
    ref_run, ref_cluster_run, _ref_clusters, ref_person = _confirmed_reference(
        repos, tmp_path, eval_side.people
    )
    snapshot_result, snapshot_path = _build_snapshot(
        repos, tmp_path, ref_run, ref_cluster_run
    )
    return FullSetup(
        eval_side=eval_side,
        manifest_result=manifest_result,
        snapshot_result=snapshot_result,
        snapshot_path=snapshot_path,
        ref_person=ref_person,
    )


def attestation_service(repos) -> IsolationAttestationService:
    return IsolationAttestationService(
        reference_intake=_guard(repos),
        manifest_service=manifest_service(repos),
        snapshot_service=_snapshot_service(repos),
        observation_repository=repos.face_observations,
        photo_repository=repos.photos,
        content_hasher=ContentHashCalculator(),
        attestation_store=FilesystemSnapshotStore(),
    )


def artifact_v2_service(repos) -> PredictionArtifactV2Service:
    from photo_archiver.infrastructure.cosine_kernel import NumpyCosineSimilarityFactory

    return PredictionArtifactV2Service(
        snapshot_service=_snapshot_service(repos),
        manifest_service=manifest_service(repos),
        artifact_store=FilesystemSnapshotStore(),
        observation_repository=repos.face_observations,
        similarity_factory=NumpyCosineSimilarityFactory(),
    )


def scoring_service(repos) -> MechanicalScoringService:
    return MechanicalScoringService(
        manifest_service=manifest_service(repos),
        snapshot_service=_snapshot_service(repos),
        artifact_service=artifact_v2_service(repos),
        attestation_service=attestation_service(repos),
        calibration_repository=repos.calibration_annotations,
        person_repository=repos.people,
    )


def build_attestation(
    repos,
    tmp_path: Path,
    setup: FullSetup,
    *,
    name: str = "attestation.json",
    reference_recognition_run_ids=None,
):
    service = attestation_service(repos)
    result = service.build_attestation(
        dataset_id=setup.dataset.id,
        dataset_version=VERSION,
        cluster_run_id=setup.cluster_run.id,
        target_manifest_path=setup.manifest_result.manifest_path,
        target_manifest_id=setup.manifest_result.manifest_id,
        target_manifest_sha256=setup.manifest_result.manifest_sha256,
        reference_snapshot_path=setup.snapshot_path,
        reference_snapshot_id=setup.snapshot_result.snapshot_id,
        reference_snapshot_sha256=setup.snapshot_result.snapshot_sha256,
        destination=tmp_path / "attestations" / name,
        reference_recognition_run_ids=reference_recognition_run_ids,
    )
    return result, service


def predictions_from_manifest(
    repos, setup: FullSetup, *, score: float | None = 0.9
) -> list[PredictionRecordV2]:
    """按冻结 GT 的真值人员为每个目标成员构造 S-B 预测（fixture）."""
    manifest_document = manifest_service(repos).read_document(
        setup.manifest_result.manifest_path
    )
    gt_rows = repos.calibration_annotations.list_ground_truth(
        dataset_id=setup.dataset.id, dataset_version=VERSION
    )
    person_by_cluster = {row.cluster_id: row.person_id for row in gt_rows}
    cluster_run_id = UUID(str(manifest_document.content["cluster_run_id"]))
    records = []
    for entry in manifest_document.content["entries"]:
        cluster_id = UUID(str(entry["cluster_id"]))
        person = person_by_cluster.get(cluster_id)
        records.append(
            PredictionRecordV2(
                cluster_run_id=cluster_run_id,
                cluster_id=cluster_id,
                observation_id=UUID(str(entry["observation_id"])),
                photo_id=UUID(str(entry["photo_id"])),
                top1_person_id=person,
                top1_score=score if person is not None else None,
            )
        )
    return records


def build_artifact_v2(
    repos,
    tmp_path: Path,
    setup: FullSetup,
    attestation_result,
    *,
    predictions=None,
    source: str = "S-B",
    scorer_version: str = SB_SCORER_VERSION,
    computed_at: str | None = "2026-10-09T00:00:00+00:00",
    git_commit: str | None = None,
    name: str = "artifact.json",
):
    service = artifact_v2_service(repos)
    if predictions is None:
        predictions = predictions_from_manifest(repos, setup)
    result = service.build_artifact_v2(
        prediction_source=source,
        scorer_version=scorer_version,
        predictions=predictions,
        reference_snapshot_path=setup.snapshot_path,
        reference_snapshot_id=setup.snapshot_result.snapshot_id,
        reference_snapshot_sha256=setup.snapshot_result.snapshot_sha256,
        target_manifest_path=setup.manifest_result.manifest_path,
        target_manifest_id=setup.manifest_result.manifest_id,
        target_manifest_sha256=setup.manifest_result.manifest_sha256,
        isolation_attestation_path=attestation_result.attestation_path,
        destination=tmp_path / "artifacts" / name,
        computed_at=computed_at,
        git_commit=git_commit,
    )
    return result, service


def read_json(path: Path) -> dict:
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def rewrite_with_rehash(path: Path, mutate) -> dict:
    """按 canonical 规则重写工件并重算 self-hash（模拟 rehash-consistent 篡改）."""
    import hashlib
    import json

    from photo_archiver.application.services.reference_snapshot_service import (
        canonical_json,
    )

    document = read_json(path)
    mutate(document)
    content = document["content"]
    recomputed = hashlib.sha256(canonical_json(content)).hexdigest()
    schema = document.get("schema_version")
    if schema == "target-manifest-v1":
        document["manifest_sha256"] = recomputed
    elif schema == "isolation-attestation-v1":
        document["isolation_invariant_sha256"] = recomputed
    else:
        document["artifact_sha256"] = recomputed
    Path(path).write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return document


def dataset_id_of(repos) -> UUID:
    return _evaluation_dataset_id(repos)
