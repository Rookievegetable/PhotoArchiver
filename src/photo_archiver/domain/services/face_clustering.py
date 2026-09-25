"""Pure two-phase face clustering — Stage D 领域算法（owner 裁决 2026-09-25）.

owner 裁决的两段式（方案 §5.2『先按相似度形成候选，再以组内一致性约束
合并』的精确化，§D-5 链式反例必须不并）：

- **阶段① 候选（贪心）**：按调用方给定的确定性顺序逐个观测；与各候选簇
  **簇心**的余弦相似度 ≥ ``cluster_sim_threshold``（默认 0.5）者加入最高
  相似度的候选簇（同分取最早的候选簇），否则新建候选簇。
- **阶段② 一致性合并（完全链接）**：每轮取「跨簇两两最小相似度」最高的
  候选簇对；仅当该值 ≥ ``consistency_threshold``（默认 0.4）才合并，否则
  停止。min 的可结合性使并簇后跨簇值可增量维护（O(1) 字典合并）。
  A~B~C 链式反例：A~C < 0.4 时三者的跨簇最小相似度永远 < 0.4，不并。
- **低质量不驱动合并**：质量分 < ``low_quality_threshold``（默认 0.0，
  即禁用——quality 公式 F 阶段校准后改参数启用）的观测**不参与**跨簇
  最小相似度证据；仍可作为候选成员入簇。一个簇对若没有任何高质量证据
  对，不具合并资格。

确定性：输入顺序由调用方固定；所有相似度经 kernel 量化（6 位小数）；
阈值比较与平局裁决（同分取先出现者）全部确定。纯函数、零 I/O、零第三方
依赖——相似度由 :class:`SimilarityLookup` 端口注入（numpy 实现在
infrastructure 层）。
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from photo_archiver.domain.exceptions import PhotoArchiverDomainError

ALGORITHM_VERSION = "cosine-centroid-completelink-v1"

DEFAULT_CLUSTER_SIM_THRESHOLD = 0.5
DEFAULT_CONSISTENCY_THRESHOLD = 0.4
DEFAULT_LOW_QUALITY_THRESHOLD = 0.0

# 完全链接合并轮询的兜底负值：无高质量证据对的簇对不具合并资格。
_NO_EVIDENCE = float("-inf")


class ClusteringCancelled(PhotoArchiverDomainError):
    """Raised via ``should_cancel`` so long merges can stop cooperatively."""


class SimilarityLookup(Protocol):
    """Similarity port consumed by the pure algorithm; numpy impl lives in infra."""

    def size(self) -> int:
        """Number of items the lookup was built for."""

    def similarity(self, left: int, right: int) -> float:
        """Quantized cosine between the two item indices (symmetric, O(1))."""

    def centroid_similarity(self, members: Sequence[int], index: int) -> float:
        """Quantized cosine between the members' mean vector and item ``index``."""


@dataclass(frozen=True, slots=True)
class ClusteringItem:
    """One clustering input item: an observation's id and its quality evidence."""

    observation_id: UUID
    quality_score: float | None


@dataclass(frozen=True, slots=True)
class ClusterAssignment:
    """One output cluster: member item indices (input order) + evidence confidences."""

    members: tuple[int, ...]
    confidences: tuple[float, ...]


def cluster_items(
    items: Sequence[ClusteringItem],
    similarities: SimilarityLookup,
    *,
    cluster_sim_threshold: float = DEFAULT_CLUSTER_SIM_THRESHOLD,
    consistency_threshold: float = DEFAULT_CONSISTENCY_THRESHOLD,
    low_quality_threshold: float = DEFAULT_LOW_QUALITY_THRESHOLD,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[ClusterAssignment, ...]:
    """Cluster the items; empty input yields no clusters (caller handles 0-face runs)."""
    if similarities.size() != len(items):
        raise ValueError("similarity lookup size must match the item count")
    if not items:
        return ()
    if should_cancel is not None and should_cancel():
        raise ClusteringCancelled("cancelled before clustering started")

    low_quality = _low_quality_flags(items, low_quality_threshold)
    candidates = _form_candidates(similarities, cluster_sim_threshold, should_cancel)
    candidates = _merge_candidates(
        candidates, similarities, low_quality, consistency_threshold, should_cancel,
    )
    return tuple(
        ClusterAssignment(
            members=tuple(sorted(cluster.members)),
            confidences=tuple(cluster.confidences[index] for index in sorted(cluster.members)),
        )
        for cluster in candidates
    )


class _Candidate:
    """Mutable candidate cluster: member indices in join order + their confidences."""

    __slots__ = ("confidences", "members")

    def __init__(self, seed: int) -> None:
        self.members: list[int] = [seed]
        self.confidences: dict[int, float] = {seed: 1.0}

    def add(self, index: int, confidence: float) -> None:
        """Admit one member with its centroid-similarity evidence."""
        self.members.append(index)
        self.confidences[index] = confidence


def _low_quality_flags(
    items: Sequence[ClusteringItem], low_quality_threshold: float,
) -> list[bool]:
    """Flag items below the quality gate; ``None`` quality counts as evidence."""
    return [
        item.quality_score is not None and item.quality_score < low_quality_threshold
        for item in items
    ]


def _form_candidates(
    similarities: SimilarityLookup,
    cluster_sim_threshold: float,
    should_cancel: Callable[[], bool] | None,
) -> list[_Candidate]:
    """Phase ①: greedy candidates by quantized centroid similarity (deterministic).

    平局取**最早**的候选簇（严格大于才替换），保证同输入同结果。
    """
    candidates: list[_Candidate] = []
    for index in range(similarities.size()):
        if should_cancel is not None and should_cancel():
            raise ClusteringCancelled("cancelled during candidate formation")
        best: _Candidate | None = None
        best_similarity: float | None = None
        for candidate in candidates:
            similarity = similarities.centroid_similarity(candidate.members, index)
            if similarity < cluster_sim_threshold:
                continue
            if best_similarity is None or similarity > best_similarity:
                best, best_similarity = candidate, similarity
        if best is None or best_similarity is None:
            candidates.append(_Candidate(index))
        else:
            best.add(index, best_similarity)
    return candidates


def _merge_candidates(
    candidates: list[_Candidate],
    similarities: SimilarityLookup,
    low_quality: list[bool],
    consistency_threshold: float,
    should_cancel: Callable[[], bool] | None,
) -> list[_Candidate]:
    """Phase ②: complete-linkage merges with incremental cross-min maintenance.

    ``min(A ∪ B, W) = min(min(A, W), min(B, W))`` keeps the merged cross-min
    an O(1) dictionary combination, so rounds stay cheap without re-scans.
    """
    cross = _initial_cross_minima(candidates, similarities, low_quality)
    while True:
        if should_cancel is not None and should_cancel():
            raise ClusteringCancelled("cancelled during consistency merging")
        left, right, best = -1, -1, consistency_threshold
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                value = cross.get((i, j), _NO_EVIDENCE)
                if value > best:
                    left, right, best = i, j, value
        if left < 0:
            return candidates
        _merge_pair(candidates, cross, left, right, best)


def _initial_cross_minima(
    candidates: list[_Candidate],
    similarities: SimilarityLookup,
    low_quality: list[bool],
) -> dict[tuple[int, int], float]:
    """One-time cross-min for every candidate pair over high-quality evidence pairs."""
    cross: dict[tuple[int, int], float] = {}
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            value = _cross_min(candidates[i], candidates[j], similarities, low_quality)
            if value != _NO_EVIDENCE:
                cross[(i, j)] = value
    return cross


def _cross_min(
    first: _Candidate,
    second: _Candidate,
    similarities: SimilarityLookup,
    low_quality: list[bool],
) -> float:
    """Min pairwise similarity over pairs with at least one high-quality member."""
    minimum = float("inf")
    for left in first.members:
        if low_quality[left]:
            continue
        for right in second.members:
            if low_quality[right]:
                continue
            value = similarities.similarity(left, right)
            if value < minimum:
                minimum = value
    return _NO_EVIDENCE if minimum == float("inf") else minimum


def _merge_pair(
    candidates: list[_Candidate],
    cross: dict[tuple[int, int], float],
    left: int,
    right: int,
    merge_value: float,
) -> None:
    """Merge ``right`` into ``left``; absorbed members adopt the merge evidence."""
    absorbing, absorbed = candidates[left], candidates[right]
    for index in absorbed.members:
        absorbing.confidences[index] = merge_value
    absorbing.members.extend(absorbed.members)
    last = len(candidates) - 1

    for position in range(len(candidates)):
        if position in (left, right):
            continue
        combined = _combine(
            cross.pop(_key(left, position), None),
            cross.pop(_key(right, position), None),
        )
        if combined is not None:
            cross[_key(left, position)] = combined
    cross.pop(_key(left, right), None)

    if right != last:
        # Move the tail candidate into the freed slot, re-keying its cross entries.
        tail = candidates[last]
        for position in range(len(candidates)):
            if position == last:
                continue
            value = cross.pop(_key(last, position), None)
            if value is not None:
                cross[_key(right, position)] = value
        candidates[right] = tail
    candidates.pop()


def _key(first: int, second: int) -> tuple[int, int]:
    """Return the canonical (smaller, larger) cross-table key."""
    return (first, second) if first < second else (second, first)


def _combine(first: float | None, second: float | None) -> float | None:
    """Combine two optional cross values; missing evidence stays missing."""
    if first is None or second is None:
        return first if first is not None else second
    return min(first, second)


def order_cluster_keys(
    keys: Sequence[tuple[str | None, str, int]],
) -> tuple[int, ...]:
    """Return input positions ordered by the plan §D-3 sort key.

    ``keys[i]`` is ``(captured_at_iso, path_key, tiebreak)``; clusters without a
    capture time sort last (never substituted by registration time), then by
    stable path key, then by the caller's tiebreak (candidate creation order).
    ISO 文本序即时间序（同一序列化格式下），混合时区标注的极端情况仍确定。
    """
    return tuple(sorted(
        range(len(keys)),
        key=lambda position: (
            keys[position][0] is None,
            keys[position][0] or "",
            keys[position][1],
            keys[position][2],
        ),
    ))


def build_sort_key(captured_at_iso: str | None, path_key: str, tiebreak: int) -> str:
    """Serialize one cluster's §D-3 sort key as a lexicographically ordered text.

    Missing capture times use the ``~`` sentinel so text ordering matches
    "timed groups first, then the rest".
    """
    time_part = captured_at_iso if captured_at_iso is not None else "~"
    return f"{time_part}|{path_key}|{tiebreak:06d}"
