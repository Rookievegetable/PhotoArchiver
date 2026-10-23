"""S-B Prediction Producer（``sb-member-max-cosine-v1``）— OG-3 开发侧实现.

依据《S-B-6 Producer 实施任务书 v0.3》与 Owner 批准的 D-1..D-7：

* 输入 = 冻结 Target Manifest + 冻结 Reference Snapshot + 钉定世代的 DB 只读
  读数；输出 = ``PredictionRecordV2`` 内存列表（零业务写入、零文件写入——
  工件构建与发布属既有 ``build_artifact_v2`` 与独立发布授权）。
* 候选 Person = 快照 entries 去重 ``person_id``（D-3），仅使用通过 D-4 可用性
  检查且 ``enabled`` 的参考项；每 Person 分数 = 其全部可用参考向量与目标向量
  的 kernel cosine **最大值**（D-3；禁 centroid/均值/投票）。
* 排名与并列（D-1）：量化分数降序；严格相等时按 ``person_id`` 规范化字符串
  升序稳定决胜——同一输入恒定同一结果。top1/top2 为权威字段；Producer 不
  派生 ``prediction_id/rank/margin``（builder 职责；K.5：Producer 侧先满足
  S-B source contract，逐条 ``validate_prediction_record_v2``）。
* 数值（D-7）：复用 ``infrastructure/cosine_kernel.py``——L2 归一化、全阵
  6 位小数量化、零向量相似度 ``0.0``、混维 fail-closed；Producer 不二次舍入；
  排名、并列与落盘使用同一量化分数（无第二数值事实源）。
* 异常（D-4）：身份矛盾（观测存在但照片/run 归属与冻结身份不符）→ 整批失败
  ——含**跨照片身份搜索**补强（F-1 整改）：在声称的 (run, photo) 下找不到
  参考观测时，先经 ``PhotoRepository.list_all`` × ``list_by_run/list_by_photo``
  全库按 id 搜索：找到他处 ⇒ ``ERR-IDENTITY-MISMATCH`` 整批失败；全库未找到 ⇒
  真缺失降级；**搜索途中任何读取异常（身份完整性无法确认）⇒ ``ERR-UNPROVABLE``
  整批失败（Owner 整改令：fail-closed，不得继续产出）**。参考向量缺失/不可读/
  哈希漂移/disabled → 逐条降级（诊断仅含身份与原因，不含向量内容，不进入任何
  工件）；混维 → 整批失败；目标向量缺失/不可读 → 整批失败；全部候选 Person 被
  排除 → 整批失败（D-2：空候选集不得静默转为 no-candidate——``no-candidate``
  类型仅为 S-C 与消费侧防御性校验保留）。
* 边界（NL-1）：Manifest 契约不含目标 embedding 哈希——目标向量取运行时
  DB 状态，目标向量**内容漂移不可检测**；确定性以相同输入与相同 DB 观测
  状态为前提。

有效输入下 Producer 恒产生 predicted（Owner 批准的 D-2 语义）；不接入
``app/services.py``/GUI/生产入口（D-5：测试可调用 ≠ 生产可用）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from photo_archiver.application.ports.similarity_kernel import SimilarityKernelFactory
from photo_archiver.application.services.reference_snapshot_service import (
    SnapshotDocument,
    ReferenceSnapshotService,
    embedding_sha256,
)
from photo_archiver.application.services.sb6_contract import (
    PREDICTION_SOURCE_SB,
    PredictionRecordV2,
    validate_prediction_record_v2,
)
from photo_archiver.application.services.target_manifest_service import (
    TargetManifestDocument,
    TargetManifestService,
)
from photo_archiver.domain import FaceEmbedding
from photo_archiver.domain.entities.face_observation import FaceObservation
from photo_archiver.domain.exceptions import ValidationError
from photo_archiver.domain.repositories.face_cluster_repository import (
    FaceClusterRepository,
)
from photo_archiver.domain.repositories.face_observation_repository import (
    FaceObservationRepository,
)
from photo_archiver.domain.repositories.photo_repository import PhotoRepository

# 逐条降级原因（D-4.2/4.3；诊断专用，不进入任何工件）
EXCLUSION_DISABLED = "disabled"
EXCLUSION_MISSING = "missing-observation"
EXCLUSION_UNREADABLE = "unreadable-embedding"
EXCLUSION_HASH_MISMATCH = "hash-mismatch"


@dataclass(frozen=True, slots=True)
class ProducerExclusion:
    """一条被降级排除的参考项（诊断专用；不产生任何工件级记录）."""

    person_id: UUID
    observation_id: UUID
    photo_id: UUID
    reason: str


@dataclass(frozen=True, slots=True)
class SbProducerResult:
    """Producer 输出（内存对象；零文件发布）。"""

    cluster_run_id: UUID
    manifest_document: TargetManifestDocument
    snapshot_document: SnapshotDocument
    manifest_sha256: str
    snapshot_sha256: str
    predictions: tuple[PredictionRecordV2, ...]
    exclusions: tuple[ProducerExclusion, ...]
    candidate_person_count: int
    target_member_count: int


class SbPredictionProducer:
    """按 D-1..D-7 为 Target Manifest 的每个成员产出 S-B 预测记录."""

    def __init__(
        self,
        *,
        manifest_service: TargetManifestService,
        snapshot_service: ReferenceSnapshotService,
        cluster_repository: FaceClusterRepository,
        observation_repository: FaceObservationRepository,
        photo_repository: PhotoRepository,
        similarity_factory: SimilarityKernelFactory,
    ) -> None:
        self._manifests = manifest_service
        self._snapshots = snapshot_service
        self._clusters = cluster_repository
        self._observations = observation_repository
        self._photos = photo_repository
        self._similarity = similarity_factory

    def produce(
        self, *, target_manifest_path: Path, reference_snapshot_path: Path
    ) -> SbProducerResult:
        """为 Manifest 的每个 Target Member 生成一条 S-B 预测记录.

        与 Manifest 逐项双射（每 entry 恰一记录）；整批失败类异常以
        ``ValidationError`` 上抛，零部分产出。
        """
        manifest_document = self._manifests.read_document(Path(target_manifest_path))
        snapshot_document = self._snapshots.read_document(Path(reference_snapshot_path))
        cluster_run_id = UUID(str(manifest_document.content["cluster_run_id"]))
        entries = manifest_document.content["entries"]
        if not entries:
            raise ValidationError("ERR-SET-EQUALITY: target manifest carries no entries")

        target_vectors = self._resolve_target_vectors(cluster_run_id, entries)
        candidates, exclusions = self._resolve_reference_candidates(snapshot_document)
        if not candidates:
            raise ValidationError(
                "ERR-UNPROVABLE: every reference candidate was excluded — the S-B "
                "prediction batch fails (D-2/D-4); an empty candidate set must not "
                "silently become no-candidate predictions"
            )
        self._reject_mixed_dimensions(target_vectors, candidates)

        records = tuple(self._score_manifest_entries(
            cluster_run_id, entries, target_vectors, candidates,
        ))
        return SbProducerResult(
            cluster_run_id=cluster_run_id,
            manifest_document=manifest_document,
            snapshot_document=snapshot_document,
            manifest_sha256=self._manifests.manifest_sha256(manifest_document),
            snapshot_sha256=snapshot_document.snapshot_sha256,
            predictions=records,
            exclusions=exclusions,
            candidate_person_count=len(candidates),
            target_member_count=len(records),
        )

    # ------------------------------------------------------- target 解析（整批失败类）

    def _resolve_target_vectors(
        self,
        cluster_run_id: UUID,
        entries: list[dict],
    ) -> dict[str, tuple[float, ...]]:
        """按钉定 cluster run 解析全部目标观测向量（D-4.1/4.5：异常整批失败）."""
        clusters = self._clusters.list_clusters(cluster_run_id)
        run_ids = sorted(
            {cluster.run_id for cluster in clusters if cluster.run_id is not None},
            key=str,
        )
        by_observation: dict[UUID, FaceObservation] = {}
        for run_id in run_ids:
            for observation in self._observations.list_by_run(run_id):
                by_observation[observation.id] = observation

        vectors: dict[str, tuple[float, ...]] = {}
        for entry in entries:
            observation_id = UUID(str(entry["observation_id"]))
            photo_id = UUID(str(entry["photo_id"]))
            matched = by_observation.get(observation_id)
            if matched is None:
                raise ValidationError(
                    f"ERR-MEMBER-CLASS: target observation {observation_id} (photo "
                    f"{photo_id}) is not resolvable in the pinned cluster run — "
                    "target data missing (D-4.5: batch failure)"
                )
            if str(matched.photo_id) != str(photo_id):
                raise ValidationError(
                    f"ERR-IDENTITY-MISMATCH: target observation {observation_id} "
                    f"belongs to photo {matched.photo_id} but the manifest entry "
                    f"claims {photo_id} — frozen identity contradiction "
                    "(D-4.1: batch failure)"
                )
            vector = matched.embedding.vector
            if not vector:
                raise ValidationError(
                    f"ERR-MEMBER-CLASS: target observation {observation_id} has an "
                    "unreadable/empty embedding (D-4.5: batch failure)"
                )
            vectors[str(observation_id)] = vector
        return vectors

    # ------------------------------------------------- reference 解析（逐条降级类）

    def _resolve_reference_candidates(
        self, snapshot_document: SnapshotDocument
    ) -> tuple[dict[str, list[tuple[float, ...]]], tuple[ProducerExclusion, ...]]:
        """解析快照 entries 为 Person → 可用参考向量（D-4.2/4.3 逐条降级）.

        读取分层（存储现实：损坏行会使 ``list_by_run`` 整体失败，不可按行隔离）：

        * **run 级快速路径**：``list_by_run`` 成功 ⇒ 全量映射，身份矛盾（观测存在
          但照片归属与冻结 entry 不符）可检测 → 整批失败（D-4.1）；
        * **回退路径**：run 级读取失败（run 内存在损坏行）⇒ 按 (run, photo) 粒度
          读取（``list_by_run_photo``），损坏照片的条目降级 ``unreadable``。

        **身份矛盾补强（F-1 整改，两条路径共用）**：在声称的 (run, photo) 下找
        不到参考观测时，先经全库跨照片身份搜索（``_reject_moved_or_missing``）
        区分"真缺失"与"被移动到他处"——后者整批失败（D-4.1）；搜索本身不可读
        ⇒ 整批失败（Owner 整改令：身份完整性无法确认时 fail-closed）。

        缺失/不可读/哈希漂移/disabled → 逐条降级；全部参考项失效的 Person 不
        进入候选集。
        """
        exclusions: list[ProducerExclusion] = []
        candidates: dict[str, list[tuple[float, ...]]] = {}
        run_cache: dict[str, tuple[bool, dict[UUID, FaceObservation]]] = {}
        photo_cache: dict[tuple[str, str], dict[UUID, FaceObservation] | None] = {}

        def load_run(run_id: str) -> tuple[bool, dict[UUID, FaceObservation]]:
            if run_id not in run_cache:
                try:
                    mapping = {
                        observation.id: observation
                        for observation in self._observations.list_by_run(UUID(run_id))
                    }
                    run_cache[run_id] = (True, mapping)
                except ValidationError:
                    # run 内存在损坏行（如不可反序列化的 embedding）——回退粒度读取
                    run_cache[run_id] = (False, {})
            return run_cache[run_id]

        def load_photo(run_id: str, photo_id: UUID) -> dict[UUID, FaceObservation] | None:
            key = (run_id, str(photo_id))
            if key not in photo_cache:
                try:
                    photo_cache[key] = {
                        observation.id: observation
                        for observation in self._observations.list_by_run_photo(
                            UUID(run_id), photo_id
                        )
                    }
                except ValidationError:
                    photo_cache[key] = None  # 该照片的行不可反序列化
            return photo_cache[key]

        for entry in snapshot_document.entries:
            person_id = UUID(str(entry["person_id"]))
            observation_id = UUID(str(entry["observation_id"]))
            photo_id = UUID(str(entry["photo_id"]))
            run_id = str(entry["provenance"]["recognition_run_id"])
            if entry.get("enabled") is None:
                # F-4 整改：必填键缺失/null → fail-closed（不再默认视为 enabled）
                raise ValidationError(
                    f"ERR-CONTRACT-FIELDS: snapshot entry (observation "
                    f"{observation_id}) is missing the required 'enabled' key "
                    "(fail-closed)"
                )
            if not entry["enabled"]:
                exclusions.append(ProducerExclusion(
                    person_id, observation_id, photo_id, EXCLUSION_DISABLED))
                continue
            readable, run_map = load_run(run_id)
            if readable:
                observation = run_map.get(observation_id)
                if observation is not None and str(observation.photo_id) != str(photo_id):
                    raise ValidationError(
                        f"ERR-IDENTITY-MISMATCH: reference observation {observation_id} "
                        f"belongs to photo {observation.photo_id} but the frozen snapshot "
                        f"entry claims {photo_id} — frozen identity contradiction "
                        "(D-4.1: batch failure)"
                    )
            photo_observations = load_photo(run_id, photo_id)
            if photo_observations is None:
                exclusions.append(ProducerExclusion(
                    person_id, observation_id, photo_id, EXCLUSION_UNREADABLE))
                continue
            observation = photo_observations.get(observation_id)
            if observation is None:
                # F-1 整改：MISSING 分类前先做跨照片身份搜索——真缺失才降级
                self._reject_moved_or_missing(
                    observation_id=observation_id,
                    claimed_photo_id=photo_id,
                    claimed_run_id=UUID(run_id),
                )
                exclusions.append(ProducerExclusion(
                    person_id, observation_id, photo_id, EXCLUSION_MISSING))
                continue
            vector = observation.embedding.vector
            if embedding_sha256(vector) != entry["embedding_sha256"]:
                exclusions.append(ProducerExclusion(
                    person_id, observation_id, photo_id, EXCLUSION_HASH_MISMATCH))
                continue
            candidates.setdefault(str(person_id), []).append(vector)
        candidates = {person: vectors for person, vectors in candidates.items() if vectors}
        return candidates, tuple(exclusions)

    def _reject_moved_or_missing(
        self,
        *,
        observation_id: UUID,
        claimed_photo_id: UUID,
        claimed_run_id: UUID,
    ) -> None:
        """D-4.1 补强（F-1 整改）：MISSING 分类前的全库跨照片身份搜索.

        "在声称的 (run, photo) 下找不到"存在两种可能：行被删除（真缺失，
        可降级）或行被移动到他处（身份矛盾，整批失败）。既有端口无按 id
        直读，故经 ``PhotoRepository.list_all`` × ``FaceObservationRepository.
        list_by_photo`` 全库搜索：

        * 找到且实际 (photo_id, run_id) 与冻结声明不符 → ``ERR-IDENTITY-MISMATCH``
          整批失败（D-4.1：不得继续产出）；
        * 全库未找到 → 真缺失（正常返回，调用方按 D-4.2 降级）；
        * **搜索途中任何读取异常（如不可反序列化行）→ ``ERR-UNPROVABLE`` 整批
          失败**——Owner 整改令：身份完整性无法确认时 fail-closed，不得继续
          产出预测。
        """
        found: FaceObservation | None = None
        try:
            for photo in self._photos.list_all():
                if photo.id is None:  # pragma: no cover - 持久化实体恒有 id
                    continue
                for observation in self._observations.list_by_photo(photo.id):
                    if observation.id == observation_id:
                        found = observation
                        break
                if found is not None:
                    break
        except ValidationError as exc:
            raise ValidationError(
                f"ERR-UNPROVABLE: identity search for observation {observation_id} "
                f"hit an unreadable source ({exc}) — identity integrity cannot be "
                "confirmed (D-4.1 补强: fail-closed, batch failure)"
            ) from exc
        if found is not None:
            raise ValidationError(
                f"ERR-IDENTITY-MISMATCH: reference observation {observation_id} "
                f"exists under (photo {found.photo_id}, run {found.run_id}) but the "
                f"frozen snapshot entry claims (photo {claimed_photo_id}, run "
                f"{claimed_run_id}) — frozen identity contradiction "
                "(D-4.1: batch failure)"
            )

    # ------------------------------------------------------------- 打分与排序

    @staticmethod
    def _reject_mixed_dimensions(
        target_vectors: dict[str, tuple[float, ...]],
        candidates: dict[str, list[tuple[float, ...]]],
    ) -> None:
        """D-4.4：混维整批失败（在 kernel 构建前显式检查，错误信息可诊断）."""
        dimensions = {len(vector) for vector in target_vectors.values()}
        for vectors in candidates.values():
            dimensions.update(len(vector) for vector in vectors)
        if len(dimensions) > 1:
            raise ValidationError(
                f"ERR-CONTRACT-FIELDS: mixed embedding dimensions {sorted(dimensions)} "
                "across target/reference vectors (D-4.4: batch failure)"
            )

    def _score_manifest_entries(
        self,
        cluster_run_id: UUID,
        entries: list[dict],
        target_vectors: dict[str, tuple[float, ...]],
        candidates: dict[str, list[tuple[float, ...]]],
    ) -> list[PredictionRecordV2]:
        """逐 entry 产出记录：max-cosine 聚合（D-3）+ 稳定排名（D-1）+ 量化落盘（D-7）."""
        # 参考向量扁平化：Person 按 person_id 规范化字符串序；Person 内按解析序
        #（max 与序无关——只取最大值，不记录获胜 entry）。
        reference_flat: list[tuple[float, ...]] = []
        indices_by_person: dict[str, list[int]] = {}
        for person_id in sorted(candidates):
            start = len(reference_flat)
            reference_flat.extend(candidates[person_id])
            indices_by_person[person_id] = list(
                range(start, start + len(candidates[person_id]))
            )
        # 目标向量去重扁平化（两个 entry 理论上可共享同一 observation_id）。
        target_index_by_obs: dict[str, int] = {}
        target_flat: list[tuple[float, ...]] = []
        for entry in entries:
            key = str(entry["observation_id"])
            if key not in target_index_by_obs:
                target_index_by_obs[key] = len(reference_flat) + len(target_flat)
                target_flat.append(target_vectors[key])

        lookup = self._similarity.build(
            [FaceEmbedding(vector=vector) for vector in reference_flat + target_flat]
        )
        ordered_persons = sorted(candidates)

        records: list[PredictionRecordV2] = []
        for entry in entries:
            target_index = target_index_by_obs[str(entry["observation_id"])]
            scores = {
                person_id: max(
                    lookup.similarity(ref_index, target_index)
                    for ref_index in indices_by_person[person_id]
                )
                for person_id in ordered_persons
            }
            ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
            top1_person, top1_score = ranked[0]
            top2_person, top2_score = ranked[1] if len(ranked) > 1 else (None, None)
            record = PredictionRecordV2(
                cluster_run_id=cluster_run_id,
                cluster_id=UUID(str(entry["cluster_id"])),
                observation_id=UUID(str(entry["observation_id"])),
                photo_id=UUID(str(entry["photo_id"])),
                top1_person_id=UUID(top1_person),
                top1_score=top1_score,
                top2_person_id=UUID(top2_person) if top2_person is not None else None,
                top2_score=top2_score,
            )
            # K.5：Producer 侧先满足 S-B source contract（消费侧另有防御性复验）。
            validate_prediction_record_v2(record, PREDICTION_SOURCE_SB)
            records.append(record)
        return records
