"""Numpy cosine similarity kernel — Stage D 聚类的数值实现.

实现领域算法消费的 ``SimilarityLookup`` 端口：

- 向量 L2 归一化后一次成阵（``V @ V.T``），逐对查询 O(1)；
- **量化**：所有相似度 round 到 6 位小数——同输入同结果的可复现性不受
  BLAS 归约顺序的末位抖动影响（抖动 ~1e-15，量化边界命中概率可忽略）；
  这也是 confidence 落在 [0, 1] 实体约束内的保障；
- 零向量相似度定义为 0.0（对齐 ``CosinePersonMatcher`` 的零向量守卫），
  聚类中自然落入单例簇；
- 簇心 = 成员归一化向量的算术平均（固定成员序），与目标的余弦同乘量化。

纯确定性的浮点行为以固定输入为前提；跨平台/跨 BLAS 构建的末位差异由
量化吸收。
"""

from collections.abc import Sequence

import numpy as np

from photo_archiver.domain import FaceEmbedding, SimilarityLookup

_SIMILARITY_DECIMALS = 6


def _quantize(value: float) -> float:
    """Round to the shared quantization grid（6 位小数，吸收 BLAS 末位抖动）."""
    return round(float(value), _SIMILARITY_DECIMALS)


class NumpyCosineSimilarityLookup(SimilarityLookup):
    """Matrix-backed deterministic cosine lookup over an ordered embedding snapshot."""

    def __init__(self, embeddings: Sequence[FaceEmbedding]) -> None:
        """Normalize the vectors and precompute the full similarity matrix."""
        if not embeddings:
            raise ValueError("NumpyCosineSimilarityLookup requires at least one embedding")
        dimension = embeddings[0].dimension
        for embedding in embeddings:
            if embedding.dimension != dimension:
                raise ValueError("All embeddings must share the same dimension")
        matrix = np.asarray([embedding.vector for embedding in embeddings], dtype=np.float64)
        norms = np.linalg.norm(matrix, axis=1)
        norms[norms == 0.0] = 1.0  # zero vectors keep zero similarity, never NaN
        normalized = matrix / norms[:, None]
        self._matrix = np.round(normalized @ normalized.T, _SIMILARITY_DECIMALS)
        self._unit = normalized
        self._dimension = dimension

    def size(self) -> int:
        """Number of items in the snapshot."""
        return int(self._matrix.shape[0])

    def similarity(self, left: int, right: int) -> float:
        """Quantized cosine between two item indices."""
        return float(self._matrix[left, right])

    def centroid_similarity(self, members: Sequence[int], index: int) -> float:
        """Quantized cosine between the members' mean vector and item ``index``."""
        if not members:
            raise ValueError("centroid_similarity requires at least one member")
        centroid = self._unit[list(members)].mean(axis=0)
        centroid_norm = float(np.linalg.norm(centroid))
        if centroid_norm == 0.0:
            return 0.0
        target = self._unit[index]
        return _quantize(float(centroid @ target) / centroid_norm)


class NumpyCosineSimilarityFactory:
    """Factory adapter for the application ``SimilarityKernelFactory`` port."""

    def build(self, embeddings: Sequence[FaceEmbedding]) -> NumpyCosineSimilarityLookup:
        """Build the lookup; empty input is a caller error (service guards)."""
        return NumpyCosineSimilarityLookup(embeddings)
