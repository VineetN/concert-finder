"""
UMAP 2-D projection for the taste map.

Takes a dict of {id: embedding_vector} and returns {id: (x, y)}.
Falls back to PCA if there are fewer than 10 points or if umap-learn is missing.
"""
from __future__ import annotations

import logging

import numpy as np
from sklearn.preprocessing import normalize

log = logging.getLogger(__name__)


def project_to_2d(
    embeddings: dict[str, np.ndarray],
    n_neighbors: int = 15,
    min_dist: float = 0.1,
) -> dict[str, tuple[float, float]]:
    """
    Project a dict of {id: embedding_vector} to 2-D coordinates.

    Uses UMAP when there are ≥10 points; PCA otherwise.
    Returns {id: (x, y)} — coordinates are NOT normalised to any fixed range
    so Plotly can handle axis scaling.
    """
    ids = list(embeddings.keys())
    n = len(ids)
    if n == 0:
        return {}

    matrix = normalize(np.stack([embeddings[i] for i in ids]).astype(np.float32))

    if n < 4:
        # Degenerate: return points on a unit circle
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
        return {ids[i]: (float(np.cos(angles[i])), float(np.sin(angles[i])))
                for i in range(n)}

    if n >= 10:
        try:
            import umap  # type: ignore[import-untyped]
            reducer = umap.UMAP(
                n_components=2,
                n_neighbors=min(n_neighbors, n - 1),
                min_dist=min_dist,
                random_state=42,
                low_memory=True,
                verbose=False,
            )
            coords = reducer.fit_transform(matrix)
            log.debug("UMAP projected %d vectors to 2-D", n)
            return {ids[i]: (float(coords[i, 0]), float(coords[i, 1])) for i in range(n)}
        except Exception as exc:
            log.warning("UMAP failed (%s); falling back to PCA", exc)

    # PCA fallback
    from sklearn.decomposition import PCA
    coords = PCA(n_components=min(2, n), random_state=42).fit_transform(matrix)
    if coords.shape[1] == 1:
        # Only 1 PC (degenerate): spread along x-axis
        coords = np.column_stack([coords[:, 0], np.zeros(n)])
    log.debug("PCA projected %d vectors to 2-D", n)
    return {ids[i]: (float(coords[i, 0]), float(coords[i, 1])) for i in range(n)}
