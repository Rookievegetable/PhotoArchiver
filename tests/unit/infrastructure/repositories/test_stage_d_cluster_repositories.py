"""Stage D cluster repository + numpy kernel tests.

覆盖：SQLite 往返（parameters 快照不被 update 覆盖）、成员唯一性拒绝、
级联链（recognition run → cluster run → cluster → member；observation →
member；photo → observation → member）、InMemory 合同对齐、numpy kernel
与纯 python 参照的确定性一致。
"""

import math
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from photo_archiver.domain import (
    FaceBox,
    FaceCluster,
    FaceClusterMember,
    FaceClusterRun,
    FaceEmbedding,
    FaceObservation,
    Photo,
    PhotoPath,
    RecognitionRun,
    RunPhotoSnapshot,
)
from photo_archiver.infrastructure import (
    NumpyCosineSimilarityLookup,
    SQLiteConnectionProvider,
    SQLiteFaceClusterRepository,
    SQLiteFaceObservationRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRunRepository,
)


def _provider(tmp_path: Path) -> SQLiteConnectionProvider:
    provider = SQLiteConnectionProvider(tmp_path / "stage-d.sqlite3")
    provider.initialize_schema()
    return provider


def _unit(angle_degrees: float, dimension: int = 2) -> FaceEmbedding:
    radians = math.radians(angle_degrees)
    vector = [math.cos(radians), math.sin(radians)]
    vector += [0.0] * (dimension - len(vector))
    return FaceEmbedding(tuple(vector))


def _cluster_run(recognition_run_id) -> FaceClusterRun:
    return FaceClusterRun(
        recognition_run_id=recognition_run_id,
        algorithm_version="cosine-centroid-completelink-v1",
        parameters={"cluster_sim_threshold": 0.5, "scope_filter": "in_selected_scope"},
    )


def _cluster(cluster_run_id, run_id, ordinal: int = 0) -> FaceCluster:
    return FaceCluster(
        cluster_run_id=cluster_run_id,
        run_id=run_id,
        ordinal=ordinal,
        member_count=1,
        sort_key="2026-01-01T00:00:00|photos/a.jpg|000000",
    )


def _member(cluster_id, observation_id) -> FaceClusterMember:
    return FaceClusterMember(cluster_id=cluster_id, observation_id=observation_id)


def _seed_photo_with_observation(provider, *, path: str = "photos/a.jpg", angle: float = 0.0):
    """Create photo + run + observation rows; return (run_id, photo_id, observation)."""
    photos = SQLitePhotoRepository(provider)
    photo = Photo(path=PhotoPath(path))
    photos.add(photo)
    runs = SQLiteRecognitionRunRepository(provider)
    run = RecognitionRun(parameters={"detector": "test"})
    runs.add_run(run)
    assert run.id is not None
    runs.add_run_photos(run.id, [RunPhotoSnapshot(run.id, photo.id, path, datetime(2026, 1, 1))])
    observations = SQLiteFaceObservationRepository(provider)
    observation = FaceObservation(
        run_id=run.id,
        photo_id=photo.id,
        face_index=0,
        photo_face_count=1,
        det_score=0.9,
        box=FaceBox(0, 0, 10, 10),
        embedding=_unit(angle),
        scope_verdict="in_selected_scope",
    )
    observations.add_many([observation])
    return run.id, photo.id, observation


def test_sqlite_cluster_run_round_trip_and_parameters_immutable(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    run_id, _, _ = _seed_photo_with_observation(provider)
    repository = SQLiteFaceClusterRepository(provider)

    cluster_run = _cluster_run(run_id)
    assert cluster_run.id is not None
    repository.add_cluster_run(cluster_run)
    cluster_run.parameters = {"tampered": True}  # type: ignore[misc]  # MappingProxy blocks real mutation
    cluster_run.start()
    assert repository.update_cluster_run(cluster_run) == 1
    cluster_run.complete(3, 5, 1)
    repository.update_cluster_run(cluster_run)

    loaded = repository.get_cluster_run(cluster_run.id)
    assert loaded is not None
    assert loaded.status == "completed"
    assert loaded.cluster_count == 3 and loaded.member_count == 5 and loaded.excluded_count == 1
    assert loaded.parameters == {
        "cluster_sim_threshold": 0.5, "scope_filter": "in_selected_scope",
    }


def test_sqlite_clusters_and_members_round_trip(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    run_id, _, observation = _seed_photo_with_observation(provider)
    repository = SQLiteFaceClusterRepository(provider)
    cluster_run = _cluster_run(run_id)
    repository.add_cluster_run(cluster_run)
    first, second = _cluster(cluster_run.id, run_id, 0), _cluster(cluster_run.id, run_id, 1)
    repository.add_clusters([first, second])
    repository.add_members([_member(first.id, observation.id)])

    assert repository.list_clusters(cluster_run.id) == [first, second]
    members = repository.list_members(cluster_run.id)
    assert len(members) == 1
    assert members[0].observation_id == observation.id
    assert members[0].source == "auto"

    with pytest.raises(sqlite3.IntegrityError):
        repository.add_members([_member(first.id, observation.id)])


def test_recognition_run_delete_cascades_all_cluster_rows(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    run_id, _, observation = _seed_photo_with_observation(provider)
    repository = SQLiteFaceClusterRepository(provider)
    cluster_run = _cluster_run(run_id)
    repository.add_cluster_run(cluster_run)
    cluster = _cluster(cluster_run.id, run_id)
    repository.add_clusters([cluster])
    repository.add_members([_member(cluster.id, observation.id)])

    with provider.connect() as connection:
        connection.execute("DELETE FROM recognition_runs WHERE id = ?", (str(run_id),))

    assert repository.get_cluster_run(cluster_run.id) is None
    assert repository.list_clusters(cluster_run.id) == []
    assert repository.list_members(cluster_run.id) == []


def test_observation_delete_cascades_member_but_keeps_cluster(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    run_id, _, observation = _seed_photo_with_observation(provider)
    repository = SQLiteFaceClusterRepository(provider)
    cluster_run = _cluster_run(run_id)
    repository.add_cluster_run(cluster_run)
    cluster = _cluster(cluster_run.id, run_id)
    repository.add_clusters([cluster])
    repository.add_members([_member(cluster.id, observation.id)])

    with provider.connect() as connection:
        connection.execute("DELETE FROM face_observations WHERE id = ?", (str(observation.id),))

    assert repository.list_clusters(cluster_run.id) != []
    assert repository.list_members(cluster_run.id) == []


def test_in_memory_repository_shares_sqlite_contract() -> None:
    from photo_archiver.infrastructure import InMemoryFaceClusterRepository

    run_id = uuid4()
    repository = InMemoryFaceClusterRepository()
    cluster_run = _cluster_run(run_id)
    repository.add_cluster_run(cluster_run)
    cluster_run.start()
    cluster_run.complete(1, 1, 0)
    assert repository.update_cluster_run(cluster_run) == 1
    cluster = _cluster(cluster_run.id, run_id)
    repository.add_clusters([cluster])
    member = _member(cluster.id, uuid4())
    repository.add_members([member])

    assert repository.get_cluster_run(cluster_run.id) is not None
    assert repository.list_clusters(cluster_run.id) == [cluster]
    assert repository.list_members(cluster_run.id) == [member]
    with pytest.raises(ValueError):
        repository.add_members([member])
    assert repository.update_cluster_run(_cluster_run(run_id)) == 0


def test_numpy_kernel_matches_reference_and_quantizes() -> None:
    """numpy kernel 与纯 python 参照一致（6 位量化），零向量相似度为 0。"""
    lookup = NumpyCosineSimilarityLookup(
        [_unit(0.0), _unit(63.0), _unit(-20.0), FaceEmbedding((0.0, 0.0))],
    )
    assert lookup.size() == 4
    assert lookup.similarity(0, 1) == round(math.cos(math.radians(63)), 6)
    assert lookup.similarity(0, 1) == lookup.similarity(1, 0)
    assert lookup.similarity(0, 3) == 0.0  # 零向量
    centroid = lookup.centroid_similarity([0, 1], 2)
    expected = _reference_centroid([_unit(0.0).vector, _unit(63.0).vector], _unit(-20.0).vector)
    assert centroid == round(expected, 6)
    with pytest.raises(ValueError):
        NumpyCosineSimilarityLookup([])


def _reference_centroid(members, target) -> float:
    centroid = [sum(v[i] for v in members) / len(members) for i in range(len(target))]
    dot = sum(a * b for a, b in zip(centroid, target))
    norm = math.sqrt(sum(a * a for a in centroid))
    target_norm = math.sqrt(sum(b * b for b in target))
    return dot / (norm * target_norm)
