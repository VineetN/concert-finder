from __future__ import annotations

import logging

import numpy as np
from sklearn.preprocessing import normalize

log = logging.getLogger(__name__)

try:
    import hdbscan as _hdbscan
    _HAS_HDBSCAN = True
except ImportError:
    _HAS_HDBSCAN = False
    log.warning("hdbscan not installed — using KMeans fallback for taste clustering")


def compute_taste_modes(
    artist_embeddings: dict[str, np.ndarray],   # {artist_id: vector}
    top_artist_ids: list[str],
    max_clusters: int = 4,
) -> dict[str, dict]:
    """
    Cluster a user's top artists into 2–4 taste modes.

    Returns:
        {cluster_id: {centroid, label, artist_ids, is_dominant}}

    The dominant mode is the largest cluster (by artist count).
    Falls back to a single "all" mode if clustering produces < 2 clusters.
    """
    ids = [aid for aid in top_artist_ids if aid in artist_embeddings]
    if not ids:
        return {}

    matrix = normalize(np.stack([artist_embeddings[aid] for aid in ids]))
    labels = _cluster(matrix, max_clusters)

    valid_labels = [l for l in set(labels) if l >= 0]
    if len(valid_labels) < 2:
        log.info("Clustering returned %d cluster(s); collapsing to single taste mode", len(valid_labels))
        return {
            "0": {
                "centroid": matrix.mean(axis=0).tolist(),
                "label": "all",
                "artist_ids": ids,
                "is_dominant": True,
            }
        }

    cluster_sizes = {l: int((labels == l).sum()) for l in valid_labels}
    dominant = max(cluster_sizes, key=cluster_sizes.__getitem__)

    modes = {}
    for label in valid_labels:
        mask = labels == label
        modes[str(label)] = {
            "centroid": matrix[mask].mean(axis=0).tolist(),
            "label": f"mode_{label}",
            "artist_ids": [ids[i] for i, m in enumerate(mask) if m],
            "is_dominant": label == dominant,
        }
    return modes


def _cluster(matrix: np.ndarray, max_k: int) -> np.ndarray:
    if _HAS_HDBSCAN and len(matrix) >= 10:
        clusterer = _hdbscan.HDBSCAN(min_cluster_size=3, metric="euclidean")
        labels = clusterer.fit_predict(matrix)
        n_valid = len(set(l for l in labels if l >= 0))
        if n_valid >= 2:
            return labels
        log.debug("HDBSCAN found %d clusters; falling back to KMeans", n_valid)

    from sklearn.cluster import KMeans
    k = min(max_k, len(matrix))
    return KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(matrix)
