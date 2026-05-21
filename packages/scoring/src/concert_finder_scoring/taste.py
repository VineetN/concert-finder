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
    artist_embeddings: dict[str, np.ndarray],
    top_artist_ids: list[str],
    artist_weights: dict[str, float] | None = None,
    max_clusters: int = 4,
) -> dict[str, dict]:
    """
    Cluster a user's top artists into 2–4 taste modes.

    Args:
        artist_embeddings: {artist_id: embedding_vector}
        top_artist_ids:    ordered list of artist IDs to cluster
        artist_weights:    optional recency weights {artist_id: float}.
                           Typical values: short_term=1.0, medium_term=0.6,
                           long_term=0.3. Affects centroid position and which
                           mode is marked dominant — recent artists pull more.
                           Defaults to uniform weight if not provided.
        max_clusters:      upper bound on k for KMeans fallback

    Returns:
        {cluster_id: {centroid, label, artist_ids, is_dominant}}
    """
    ids = [aid for aid in top_artist_ids if aid in artist_embeddings]
    if not ids:
        return {}

    matrix = normalize(np.stack([artist_embeddings[aid] for aid in ids]))
    weights = np.array(
        [artist_weights.get(aid, 1.0) for aid in ids] if artist_weights
        else [1.0] * len(ids),
        dtype=np.float32,
    )

    labels = _cluster(matrix, max_clusters)

    valid_labels = [l for l in set(labels) if l >= 0]
    if len(valid_labels) < 2:
        log.info("Clustering returned %d cluster(s); collapsing to single taste mode", len(valid_labels))
        return {
            "0": {
                "centroid": _weighted_centroid(matrix, weights).tolist(),
                "label": "all",
                "artist_ids": ids,
                "is_dominant": True,
            }
        }

    # Build modes; use weighted centroids so recent artists anchor the mode
    # more strongly than artists played 6 months ago.
    modes: dict[str, dict] = {}
    cluster_weight_totals: dict[int, float] = {}

    for label in valid_labels:
        mask = labels == label
        cluster_ids = [ids[i] for i, m in enumerate(mask) if m]
        cluster_w = weights[mask]
        centroid = _weighted_centroid(matrix[mask], cluster_w)
        # Dominance is determined by total recency weight, not raw count.
        # A 10-artist recent phase outweighs a 15-artist older habit.
        cluster_weight_totals[label] = float(cluster_w.sum())
        modes[str(label)] = {
            "centroid": centroid.tolist(),
            "label": f"mode_{label}",
            "artist_ids": cluster_ids,
            "is_dominant": False,  # resolved below
        }

    dominant = max(cluster_weight_totals, key=cluster_weight_totals.__getitem__)
    modes[str(dominant)]["is_dominant"] = True
    return modes


def _weighted_centroid(vecs: np.ndarray, weights: np.ndarray) -> np.ndarray:
    centroid = np.average(vecs, weights=weights, axis=0)
    return centroid / (np.linalg.norm(centroid) + 1e-8)


def _cluster(matrix: np.ndarray, max_k: int) -> np.ndarray:
    if _HAS_HDBSCAN and len(matrix) >= 10:
        clusterer = _hdbscan.HDBSCAN(
            min_cluster_size=4,               # was 3; reduces noise micro-clusters
            min_samples=2,                    # controls outlier sensitivity
            metric="euclidean",
            cluster_selection_method="leaf",  # finer-grained than default "eom";
                                              # finds tighter sub-clusters rather
                                              # than aggressively merging them
        )
        labels = clusterer.fit_predict(matrix)
        n_valid = len(set(l for l in labels if l >= 0))
        if n_valid >= 2:
            return labels
        log.debug("HDBSCAN found %d valid cluster(s); falling back to KMeans", n_valid)

    from sklearn.cluster import KMeans
    k = min(max_k, len(matrix))
    return KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(matrix)
