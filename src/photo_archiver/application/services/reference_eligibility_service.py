"""S-B-3 Reference Eligibility evaluator（只读判定，零写入）.

回答一个问题：一条现存 ``person_face_embeddings`` 行，凭什么资格进入未来的
Reference Snapshot（S-B-4）？

概念分层（本模块的结构性承诺）::

    Business PFE ≠ Reference-legal PFE ≠ Snapshot-eligible sample
    ≠ Frozen PERSON coverage ≠ Scorer candidate

判定模型（Owner 任务书 §3/§9）：

* **Reference-legal**（样本层合法性）= E-01 指定参考批次来源（observation
  的 recognition run ∈ 指定参考 recognition runs，且所属 cluster ∈ 指定参考
  cluster runs）+ E-02 人工身份支撑（confirmed 且 source ∈ {manual, review}、
  person 一致）+ E-03 embedding 结构有效（可解析、非空、维度一致）+
  E-04 observation 链完整 + E-05 隔离四查（photo_id ∉ EvalPhotoSet、非评估
  簇观察、cross-run、字节哈希——全部复用 S-B-2 守卫，不重造规则）+ 去重
  （同一 observation 不得被多个 person 重复主张）+ enabled=1。
* **决策四态**：ELIGIBLE（合法且 person ∈ Frozen PERSON）/ COVERAGE_ONLY
  （合法但 person ∉ Frozen PERSON）/ INELIGIBLE（有证据的违规）/
  OWNER-GATE（混合溯源：recognition run ∈ 指定集合但 cluster run ∉ 指定
  集合——证据不足，需 Owner 裁决）。
* **Coverage 与 Eligibility 严格分离**：Frozen PERSON coverage 是 person 级
  指标（36 人口中拥有 ≥1 条合法参考的人数），与样本层判定互不替代。
  业务人物持有合法参考只产生 COVERAGE_ONLY，不计入 Frozen PERSON coverage
  （当前 0/36）。
* **Provenance 边界（H-4，如实登记）**：写入路径级溯源
  （confirm_reference_cluster vs generic add_samples）在当前 schema 下不可
  数据区分（PFE 无 provenance 列）；本模块按 D-SB-1 的"指定参考批次"设计，
  以 batch 成员资格（runs）作 provenance 载体。当前 12 条生产样本的归属另由
  S-B-1/S-B-2 执行文档、两轮审计与全库总性（pfe=12 且全部出自 S-B-1）实锤。
  schema 级 provenance 列 = OWNER GATE 选项（已登记，未实施）。

本服务**只读**：不写任何表；不实现 scoring/snapshot/artifact/threshold。
embedding 已损坏的行（无法经仓储层解析）按 person 整组判 INELIGIBLE
（结构损坏证据），扫描不崩溃。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from photo_archiver.application.ports import PhotoContentHasher
from photo_archiver.application.services.reference_intake_service import (
    ReferenceIntakeService,
    _as_uuid,
)
from photo_archiver.domain import PhotoRepository
from photo_archiver.domain.entities.cluster_assignment import PersonFaceSample
from photo_archiver.domain.entities.face_cluster import FaceCluster
from photo_archiver.domain.entities.face_observation import FaceObservation
from photo_archiver.domain.entities.person import Person
from photo_archiver.domain.entities.photo import Photo
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.repositories.calibration_annotation_repository import (
    CalibrationAnnotationRepository,
)
from photo_archiver.domain.repositories.cluster_assignment_repository import (
    ClusterPersonAssignmentRepository,
    PersonFaceSampleRepository,
)
from photo_archiver.domain.repositories.face_cluster_repository import (
    FaceClusterRepository,
)
from photo_archiver.domain.repositories.face_observation_repository import (
    FaceObservationRepository,
)
from photo_archiver.domain.repositories.person_repository import PersonRepository
from photo_archiver.domain.repositories.recognition_run_repository import (
    RecognitionRunRepository,
)

ELIGIBILITY_MODEL_VERSION = "sb3-eligibility-v1"

DECISION_ELIGIBLE = "ELIGIBLE"
DECISION_INELIGIBLE = "INELIGIBLE"
DECISION_COVERAGE_ONLY = "COVERAGE_ONLY"
DECISION_OWNER_GATE = "OWNER-GATE"

HUMAN_ASSIGNMENT_SOURCES = ("manual", "review")

COVERAGE_NO_REFERENCE = "NO_REFERENCE"
COVERAGE_SINGLE_REFERENCE = "SINGLE_REFERENCE"
COVERAGE_MULTI_REFERENCE = "MULTI_REFERENCE"


@dataclass(frozen=True, slots=True)
class EligibilityCheck:
    """One named check with its evidence（E-06：每个结论可追溯）."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ReferenceSampleEligibility:
    """Per-sample decision + full evidence chain（不是黑盒 boolean）."""

    pfe_id: UUID
    person_id: UUID
    person_name: str | None
    observation_id: UUID
    photo_id: UUID | None
    decision: str
    checks: tuple[EligibilityCheck, ...]
    exclusion_reasons: tuple[str, ...]
    quality_observation: str
    recognition_run_id: UUID | None
    cluster_run_ids: tuple[UUID, ...]
    assignment_ids: tuple[UUID, ...]
    embedding: tuple[float, ...] | None = None
    quality_score: float | None = None


@dataclass(frozen=True, slots=True)
class PersonCoverage:
    """Person-level coverage row（与样本层 Eligibility 严格分离）."""

    person_id: UUID
    person_name: str | None
    is_frozen_person: bool
    reference_count: int
    classification: str


@dataclass(frozen=True, slots=True)
class EligibilityReport:
    """Complete read-only scan result.

    ``unreadable_person_ids``：embedding 结构损坏、仓储层无法解析的样本，
    按 person 整组标记 INELIGIBLE 并排除出候选（行级证据结构性不可得，
    如实登记而非静默跳过）。"""

    samples: tuple[ReferenceSampleEligibility, ...]
    unreadable_person_ids: tuple[UUID, ...]
    coverage_rows: tuple[PersonCoverage, ...]
    frozen_person_count: int
    frozen_covered_count: int
    frozen_single_reference_count: int
    frozen_multi_reference_count: int
    frozen_no_reference_count: int
    coverage_only_person_count: int
    decision_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class _Context:
    """Per-scan immutable lookup context."""

    evaluation_photos: frozenset[UUID]
    eval_hashes: frozenset[str]
    eval_member_obs: frozenset[UUID]
    frozen_person_ids: frozenset[UUID]
    reference_run_ids: frozenset[UUID]
    reference_cluster_run_ids: frozenset[UUID]
    people: Mapping[UUID, Person]
    photos: Mapping[UUID, Photo]
    observations: Mapping[UUID, FaceObservation]
    obs_runs: Mapping[UUID, frozenset[UUID]]  # keyed by PHOTO id（cross-run 语义）
    obs_claim_counter: Counter[UUID]


class ReferenceEligibilityService:
    """Read-only evaluator: which PFE rows qualify for the future snapshot?"""

    def __init__(
        self,
        reference_intake: ReferenceIntakeService,
        calibration_repository: CalibrationAnnotationRepository,
        assignment_repository: ClusterPersonAssignmentRepository,
        cluster_repository: FaceClusterRepository,
        observation_repository: FaceObservationRepository,
        photo_repository: PhotoRepository,
        person_repository: PersonRepository,
        sample_repository: PersonFaceSampleRepository,
        run_repository: RecognitionRunRepository,
        content_hasher: PhotoContentHasher,
    ) -> None:
        """Store read-only dependencies; the S-B-2 guard is reused, not copied."""
        self._reference_intake = reference_intake
        self._calibration = calibration_repository
        self._assignments = assignment_repository
        self._clusters = cluster_repository
        self._observations = observation_repository
        self._photos = photo_repository
        self._people = person_repository
        self._samples = sample_repository
        self._runs = run_repository
        self._hasher = content_hasher

    def evaluate_samples(
        self,
        dataset_id: UUID,
        dataset_version: str,
        reference_run_ids: frozenset[UUID] | set[UUID],
        reference_cluster_run_ids: frozenset[UUID] | set[UUID],
    ) -> tuple[tuple[ReferenceSampleEligibility, ...], tuple[UUID, ...]]:
        """Classify every existing PFE row with a full evidence chain."""
        dataset_uuid = _as_uuid(dataset_id)
        run_ids_f = frozenset(_as_uuid(r) for r in reference_run_ids)
        cluster_run_ids_f = frozenset(_as_uuid(r) for r in reference_cluster_run_ids)
        evaluation_photos = self._reference_intake.build_evaluation_photo_set(
            dataset_uuid, dataset_version
        )
        eval_hashes = self._reference_intake.evaluation_content_hashes(
            dataset_uuid, dataset_version
        )
        eval_member_obs = self._reference_intake.evaluation_member_observations(
            dataset_uuid, dataset_version
        )
        frozen_person_ids = frozenset(
            r.person_id for r in self._calibration.list_ground_truth(
                dataset_id=dataset_uuid, dataset_version=dataset_version
            )
            if r.verdict == "person" and r.person_id is not None
        )
        people = {p.id: p for p in self._people.list_all() if p.id is not None}
        photos = {p.id: p for p in self._photos.list_all() if p.id is not None}
        observations: dict[UUID, FaceObservation] = {}
        obs_runs: dict[UUID, set[UUID]] = {}
        for run in self._runs.list_runs():
            if run.id is None:
                continue
            for observation in self._observations.list_by_run(run.id):
                observations[observation.id] = observation
                obs_runs.setdefault(observation.photo_id, set()).add(run.id)
        rows: list[PersonFaceSample] = []
        unreadable: list[UUID] = []
        for person in self._people.list_all():
            if person.id is None:
                continue
            try:
                rows.extend(self._samples.list_by_person(person.id))
            except (ValidationError, ValueError):
                # 结构损坏的 embedding 行无法经仓储层解析——该 person 整组
                # 判 INELIGIBLE 并排除出候选（E-03 结构损坏证据；扫描不
                # 崩溃，行级细节如实缺失，不静默跳过）。
                unreadable.append(person.id)
        obs_claim_counter = Counter(row.observation_id for row in rows)
        context = _Context(
            evaluation_photos=evaluation_photos,
            eval_hashes=eval_hashes,
            eval_member_obs=eval_member_obs,
            frozen_person_ids=frozen_person_ids,
            reference_run_ids=run_ids_f,
            reference_cluster_run_ids=cluster_run_ids_f,
            people=people,
            photos=photos,
            observations=observations,
            obs_runs={k: frozenset(v) for k, v in obs_runs.items()},
            obs_claim_counter=obs_claim_counter,
        )
        samples = tuple(self._evaluate_one(row, context) for row in rows)
        return samples, tuple(unreadable)

    def evaluate_person_coverage(
        self,
        dataset_id: UUID,
        dataset_version: str,
        reference_run_ids: frozenset[UUID] | set[UUID],
        reference_cluster_run_ids: frozenset[UUID] | set[UUID],
    ) -> EligibilityReport:
        """Sample scan + Frozen PERSON coverage（两个维度，一次产出）."""
        samples, unreadable_person_ids = self.evaluate_samples(
            dataset_id, dataset_version, reference_run_ids, reference_cluster_run_ids
        )
        frozen_person_ids = {
            r.person_id for r in self._calibration.list_ground_truth(
                dataset_id=dataset_id, dataset_version=dataset_version
            )
            if r.verdict == "person" and r.person_id is not None
        }
        people = {p.id: p for p in self._people.list_all()}
        legal_by_person: dict[UUID, int] = {}
        for sample in samples:
            if sample.decision in (DECISION_ELIGIBLE, DECISION_COVERAGE_ONLY):
                legal_by_person[sample.person_id] = (
                    legal_by_person.get(sample.person_id, 0) + 1
                )
        coverage_rows = []
        covered = single = multi = 0
        for person_id in sorted(frozen_person_ids, key=str):
            n = legal_by_person.get(person_id, 0)
            if n >= 2:
                classification = "COVERED/" + COVERAGE_MULTI_REFERENCE
                multi += 1
            elif n == 1:
                classification = "COVERED/" + COVERAGE_SINGLE_REFERENCE
                single += 1
            else:
                classification = COVERAGE_NO_REFERENCE
            if n >= 1:
                covered += 1
            coverage_rows.append(PersonCoverage(
                person_id=person_id,
                person_name=(
                    people[person_id].name if person_id in people else None
                ),
                is_frozen_person=True,
                reference_count=n,
                classification=classification,
            ))
        for person_id in sorted(legal_by_person):
            if person_id in frozen_person_ids:
                continue
            coverage_rows.append(PersonCoverage(
                person_id=person_id,
                person_name=(
                    people[person_id].name if person_id in people else None
                ),
                is_frozen_person=False,
                reference_count=legal_by_person[person_id],
                classification="COVERAGE_ONLY",
            ))
        return EligibilityReport(
            samples=samples,
            unreadable_person_ids=tuple(unreadable_person_ids),
            coverage_rows=tuple(coverage_rows),
            frozen_person_count=len(frozen_person_ids),
            frozen_covered_count=covered,
            frozen_single_reference_count=single,
            frozen_multi_reference_count=multi,
            frozen_no_reference_count=len(frozen_person_ids) - covered,
            coverage_only_person_count=sum(
                1 for pid in legal_by_person
                if pid not in frozen_person_ids
            ),
            decision_counts=dict(Counter(s.decision for s in samples)),
        )

    def _evaluate_one(
        self, sample: PersonFaceSample, context: _Context
    ) -> ReferenceSampleEligibility:
        checks: list[EligibilityCheck] = []
        reasons: list[str] = []

        def add(name: str, passed: bool, detail: str) -> None:
            checks.append(EligibilityCheck(name=name, passed=passed, detail=detail))
            if not passed:
                reasons.append(f"{name}: {detail}")

        observation = context.observations.get(sample.observation_id)
        photo = (
            context.photos.get(observation.photo_id)
            if observation is not None
            else None
        )
        person = context.people.get(sample.person_id)
        obs_clusters: list[FaceCluster] = (
            self._clusters.list_clusters_of_observation(sample.observation_id)
        )
        cluster_run_ids = tuple(sorted(
            (c.cluster_run_id for c in obs_clusters if c.cluster_run_id is not None),
            key=str,
        ))
        run_ok = observation is not None and observation.run_id in context.reference_run_ids
        cluster_ok = bool(context.reference_cluster_run_ids & set(cluster_run_ids))

        # E-01 reference-source（指定批次成员资格；混合溯源 → OWNER-GATE）
        if run_ok and cluster_ok:
            add("E-01-reference-source", True,
                "observation recognition run and cluster runs both inside the "
                "designated reference batch")
        elif run_ok:
            add("E-01-reference-source", False,
                "mixed provenance: recognition run designated but cluster run(s) "
                f"{cluster_run_ids} outside the designated set")
        else:
            add("E-01-reference-source", False,
                "observation recognition run "
                f"{observation.run_id if observation is not None else None} "
                "outside the designated reference batch")

        # E-02 human identity（confirmed + 人工来源 + person 一致）
        assignment_ids: list[UUID] = []
        human_ok = False
        human_detail = "no confirmed human assignment on the observation clusters"
        for cluster in obs_clusters:
            if cluster.id is None:
                continue
            latest = self._assignments.list_latest_decision(cluster.id)
            if latest is None:
                continue
            if latest.id is not None:
                assignment_ids.append(latest.id)
            if (latest.status == "confirmed"
                    and latest.source in HUMAN_ASSIGNMENT_SOURCES
                    and latest.person_id == sample.person_id):
                human_ok = True
                human_detail = f"assignment {latest.id} confirmed/{latest.source}"
        add("E-02-human-identity", human_ok, human_detail)

        # person / observation 链（E-04）
        person = context.people.get(sample.person_id)
        person_name = getattr(person, "name", None)
        add("C-person-valid", person is not None,
            "person resolvable" if person is not None else "person NOT resolvable")
        add("E-04-observation-valid",
            observation is not None and photo is not None,
            "observation/photo resolvable"
            if observation is not None and photo is not None
            else "dangling observation or photo")

        # E-03 embedding structure（仓储层已解析；损坏行走整组 INELIGIBLE 分支）
        dimension = len(sample.embedding.vector)
        add("E-03-embedding-valid", dimension > 0,
            f"parsed, non-empty, dimension {dimension}")

        # enabled（禁用样本不得进入 snapshot）
        add("C-enabled", sample.enabled,
            "enabled=1" if sample.enabled else "sample disabled (enabled=0)")

        # E-05 isolation（复用 S-B-2 规则）
        photo_id = observation.photo_id if observation is not None else None
        add("E-05-eval-photo-isolation",
            photo_id is not None and photo_id not in context.evaluation_photos,
            "photo outside EvalPhotoSet"
            if photo_id is not None and photo_id not in context.evaluation_photos
            else "photo inside EvalPhotoSet")
        add("E-05-same-cluster",
            sample.observation_id not in context.eval_member_obs,
            "observation outside evaluation clusters"
            if sample.observation_id not in context.eval_member_obs
            else "observation belongs to an evaluation cluster")
        photo_run_ids = (
            context.obs_runs.get(photo_id, frozenset())
            if photo_id is not None
            else frozenset()
        )
        add("E-05-cross-run", photo_run_ids <= context.reference_run_ids,
            "all observations of this photo live in reference runs"
            if photo_run_ids <= context.reference_run_ids
            else "photo has observations in non-reference runs")
        if photo is not None:
            live_hash = self._hasher.calculate(photo.path.raw_path)
            add("E-05-content-hash", live_hash not in context.eval_hashes,
                "byte content outside evaluation content hashes"
                if live_hash not in context.eval_hashes
                else "photo bytes match an evaluation photo")
        else:
            add("E-05-content-hash", False, "photo missing — cannot hash")

        # duplicate / reuse（§7：同一 observation 不得被多个 person 主张）
        claims = context.obs_claim_counter.get(sample.observation_id, 0)
        add("C-duplicate-reuse", claims <= 1,
            "observation claimed by exactly one person row"
            if claims <= 1 else
            f"observation claimed by {claims} person rows — reuse violation")

        # §6 quality observation（D-SB-10：只记录，不判定）
        quality_observation = (
            f"quality_score="
            f"{'present' if sample.quality_score is not None else 'absent'}"
            f" value={sample.quality_score!r}; no acceptance threshold defined"
            " (D-SB-10 OPEN PARAMETER)"
        )

        hard_fail = any(not c.passed for c in checks)
        mixed_provenance = any(
            c.name == "E-01-reference-source" and not c.passed
            and "mixed provenance" in c.detail
            for c in checks
        )
        if hard_fail:
            # 混合溯源（识别 run 指定 + 聚类 run 未指定）= 证据不足 → OWNER-GATE；
            # 其余硬失败（越界/重复/损坏）= 有证据的 INELIGIBLE。
            decision = (DECISION_OWNER_GATE if mixed_provenance
                        else DECISION_INELIGIBLE)
        elif sample.person_id in context.frozen_person_ids:
            decision = DECISION_ELIGIBLE
        else:
            decision = DECISION_COVERAGE_ONLY

        return ReferenceSampleEligibility(
            pfe_id=sample.id,
            person_id=sample.person_id,
            person_name=person_name,
            observation_id=sample.observation_id,
            photo_id=photo_id,
            decision=decision,
            checks=tuple(checks),
            exclusion_reasons=tuple(reasons),
            quality_observation=quality_observation,
            recognition_run_id=observation.run_id if observation is not None else None,
            cluster_run_ids=cluster_run_ids,
            assignment_ids=tuple(assignment_ids),
            embedding=tuple(sample.embedding.vector),
            quality_score=sample.quality_score,
        )
