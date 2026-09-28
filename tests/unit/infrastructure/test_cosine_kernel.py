"""NumpyCosineSimilarityLookup — Stage 11B（AUD-017 Option C）数值边界钉定.

样本建议路径的真实 kernel：量化 6 位使恰等于阈值（0.40）的余弦可精确判定
（D-2 边界）；维度不一致 fail-closed（模型身份的现行守卫——全系统单模型
buffalo_l，无 model_version 列，维度校验即异物拦截，见 ADR-047）。
"""

import math

import pytest

from photo_archiver.domain import FaceEmbedding
from photo_archiver.infrastructure.cosine_kernel import NumpyCosineSimilarityFactory


def _emb(*components) -> FaceEmbedding:
    return FaceEmbedding(vector=tuple(components))


def test_dimension_mismatch_fails_closed():
    with pytest.raises(ValueError, match="same dimension"):
        NumpyCosineSimilarityFactory().build([_emb(1.0, 0.0), _emb(1.0, 0.0, 0.0)])


def test_quantized_cosine_reproduces_threshold_grid():
    x_axis = _emb(1.0, 0.0)
    at_threshold = _emb(0.4, math.sqrt(1.0 - 0.4**2))
    above = _emb(0.6, math.sqrt(1.0 - 0.6**2))
    lookup = NumpyCosineSimilarityFactory().build([x_axis, at_threshold, above])
    assert lookup.similarity(0, 1) == 0.4   # 恰等阈值可精确判定（D-2 >= 语义）
    assert lookup.similarity(0, 2) == 0.6
