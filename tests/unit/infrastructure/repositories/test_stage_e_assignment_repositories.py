"""Stage E SQLite repository tests — assignments, samples, cascade, migration."""

import sqlite3

import pytest

from photo_archiver.domain import (
    ClusterPersonAssignment,
    FaceBox,
    FaceEmbedding,
    FaceObservation,
    Person,
    PersonFaceSample,
    Photo,
    PhotoPath,
    RecognitionRun,
)
from photo_archiver.infrastructure import (
    SQLiteClusterPersonAssignmentRepository,
    SQLiteConnectionProvider,
    SQLiteFaceClusterRepository,
    SQLiteFaceObservationRepository,
    SQLitePersonFaceSampleRepository,
    SQLitePersonRepository,
    SQLitePhotoRepository,
    SQLiteRecognitionRunRepository,
)


def _provider(tmp_path):
    provider = SQLiteConnectionProvider(tmp_path / "stage-e.sqlite3")
    provider.initialize_schema()
    return provider


def _seed_cluster_with_person(provider):
    """Seed person + photo + recognition run + cluster; return ids."""
    people = SQLitePersonRepository(provider)
    person = Person(name="张三", roster_order=1)
    people.add(person)
    assert person.id is not None
    photos = SQLitePhotoRepository(provider)
    photo = Photo(path=PhotoPath("photos/a.jpg"))
    photos.add(photo)
    assert photo.id is not None
    runs = SQLiteRecognitionRunRepository(provider)
    recognition_run = RecognitionRun(parameters={})
    runs.add_run(recognition_run)
    assert recognition_run.id is not None
    observations = SQLiteFaceObservationRepository(provider)
    observation = FaceObservation(
        run_id=recognition_run.id,
        photo_id=photo.id,
        face_index=0,
        photo_face_count=1,
        det_score=0.9,
        box=FaceBox(0, 0, 10, 10),
        embedding=FaceEmbedding((1.0, 0.0)),
        scope_verdict="in_selected_scope",
    )
    observations.add_many([observation])
    clusters = SQLiteFaceClusterRepository(provider)
    from photo_archiver.domain import FaceCluster, FaceClusterMember, FaceClusterRun

    cluster_run = FaceClusterRun(recognition_run_id=recognition_run.id,
                                 algorithm_version="v1")
    clusters.add_cluster_run(cluster_run)
    cluster = FaceCluster(
        cluster_run_id=cluster_run.id, run_id=recognition_run.id,
        ordinal=0, member_count=1, sort_key="k",
    )
    clusters.add_clusters([cluster])
    clusters.add_members([
        FaceClusterMember(cluster_id=cluster.id, observation_id=observation.id),
    ])
    return cluster.id, person.id, observation.id, cluster_run.id


def test_assignment_round_trip_preserves_snapshot_and_score(tmp_path):
    provider = _provider(tmp_path)
    cluster_id, person_id, _, cluster_run_id = _seed_cluster_with_person(provider)
    repository = SQLiteClusterPersonAssignmentRepository(provider)
    assignment = ClusterPersonAssignment(
        cluster_id=cluster_id, person_id=person_id,
        source="sample_match", score=0.83,
        sort_snapshot={"sort_key": "k|a|000000"},
    )
    repository.add_assignments([assignment])

    loaded = repository.get_assignment(assignment.id)
    assert loaded.status == "suggested"
    assert loaded.source == "sample_match"
    assert loaded.score == 0.83
    assert loaded.sort_snapshot == {"sort_key": "k|a|000000"}

    assignment.confirm({"sort_key": "k|a|000000", "note": "confirmed"})
    repository.update_assignment(assignment)
    loaded = repository.get_assignment(assignment.id)
    assert loaded.status == "confirmed"
    assert loaded.confirmed_at is not None
    assert loaded.sort_snapshot["note"] == "confirmed"
    # 代际范围查询：该有效行能被工作台读取。
    assert [row.id for row in repository.list_active_by_cluster_run(cluster_run_id)] == [
        assignment.id,
    ]


def test_assignment_queries_by_cluster_and_rejected_pairs(tmp_path):
    provider = _provider(tmp_path)
    cluster_id, person_id, _, cluster_run_id = _seed_cluster_with_person(provider)
    repository = SQLiteClusterPersonAssignmentRepository(provider)
    person_b = Person(name="李四", roster_order=2)
    SQLitePersonRepository(provider).add(person_b)
    suggested = ClusterPersonAssignment(
        cluster_id=cluster_id, person_id=person_id,
        created_at=__import__("datetime").datetime(2026, 1, 1),
    )
    rejected = ClusterPersonAssignment(
        cluster_id=cluster_id, person_id=person_b.id,
        created_at=__import__("datetime").datetime(2026, 1, 2),
    )
    rejected.reject()
    repository.add_assignments([suggested, rejected])

    # created_at DESC：新行在前（同刻并列由 id 兜底，故种子显式错开）。
    assert [row.id for row in repository.list_by_cluster(cluster_id)] == [
        rejected.id, suggested.id,
    ]
    assert (cluster_id, person_b.id) in repository.list_rejected_pairs(cluster_run_id)
    # 同簇两行中只有 suggested 是有效行。
    assert [row.id for row in repository.list_active_by_cluster_run(cluster_run_id)] == [
        suggested.id,
    ]


def test_unassigned_row_allows_null_person(tmp_path):
    provider = _provider(tmp_path)
    cluster_id, _, _, _ = _seed_cluster_with_person(provider)
    repository = SQLiteClusterPersonAssignmentRepository(provider)
    row = ClusterPersonAssignment(
        cluster_id=cluster_id, person_id=None, status="unassigned",
    )
    repository.add_assignments([row])
    assert repository.get_assignment(row.id).person_id is None


def test_cluster_delete_cascades_assignments(tmp_path):
    provider = _provider(tmp_path)
    cluster_id, person_id, _, _ = _seed_cluster_with_person(provider)
    repository = SQLiteClusterPersonAssignmentRepository(provider)
    repository.add_assignments([
        ClusterPersonAssignment(cluster_id=cluster_id, person_id=person_id),
    ])

    with provider.connect() as connection:
        connection.execute("DELETE FROM face_clusters WHERE id = ?", (str(cluster_id),))

    assert repository.list_by_cluster(cluster_id) == []


def test_sample_round_trip_and_unique_pair(tmp_path):
    provider = _provider(tmp_path)
    _, person_id, observation_id, _ = _seed_cluster_with_person(provider)
    repository = SQLitePersonFaceSampleRepository(provider)
    sample = PersonFaceSample(
        person_id=person_id,
        observation_id=observation_id,
        embedding=FaceEmbedding((0.1, 0.9)),
        quality_score=0.8,
    )
    repository.add_samples([sample])

    assert [row.id for row in repository.list_enabled()] == [sample.id]
    assert [row.id for row in repository.list_by_person(person_id)] == [sample.id]
    with pytest.raises(sqlite3.IntegrityError):
        repository.add_samples([PersonFaceSample(
            person_id=person_id, observation_id=observation_id,
            embedding=FaceEmbedding((0.5, 0.5)),
        )])
