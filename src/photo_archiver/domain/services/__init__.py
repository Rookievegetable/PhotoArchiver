"""Pure domain services (no I/O, no third-party dependencies)."""

from photo_archiver.domain.services.pairing import (
    PairingCluster,
    PairingPerson,
    SAMPLE_MATCH_THRESHOLD_DEFAULT,
    SuggestionOutcome,
    suggest_pairings,
)
from photo_archiver.domain.services.face_clustering import (
    ALGORITHM_VERSION,
    ClusterAssignment,
    ClusteringCancelled,
    ClusteringItem,
    DEFAULT_CLUSTER_SIM_THRESHOLD,
    DEFAULT_CONSISTENCY_THRESHOLD,
    DEFAULT_LOW_QUALITY_THRESHOLD,
    SimilarityLookup,
    build_sort_key,
    cluster_items,
    order_cluster_keys,
)

__all__ = [
    "ALGORITHM_VERSION",
    "ClusterAssignment",
    "ClusteringCancelled",
    "ClusteringItem",
    "DEFAULT_CLUSTER_SIM_THRESHOLD",
    "DEFAULT_CONSISTENCY_THRESHOLD",
    "DEFAULT_LOW_QUALITY_THRESHOLD",
    "SimilarityLookup",
    "build_sort_key",
    "PairingCluster",
    "PairingPerson",
    "SAMPLE_MATCH_THRESHOLD_DEFAULT",
    "SuggestionOutcome",
    "suggest_pairings",
    "cluster_items",
    "order_cluster_keys",
]
