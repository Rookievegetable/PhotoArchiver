"""Similarity kernel port — Stage D 聚类的数值计算边界.

领域算法（``domain.services.face_clustering``）只消费
``SimilarityLookup``（量化余弦查询），向量数学由 infrastructure 的 numpy
kernel 实现；本端口定义 application 装配其工厂的形状（application 层
自身不依赖 numpy，遵守分层矩阵）。
"""

from collections.abc import Sequence
from typing import Protocol

from photo_archiver.domain import FaceEmbedding, SimilarityLookup


class SimilarityKernelFactory(Protocol):
    """Build a :class:`SimilarityLookup` over an ordered embedding snapshot."""

    def build(self, embeddings: Sequence[FaceEmbedding]) -> SimilarityLookup:
        """Return the lookup; implementations must be deterministic and quantized."""
