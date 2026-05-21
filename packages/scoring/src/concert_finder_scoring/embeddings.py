from __future__ import annotations

import logging
from functools import lru_cache

import numpy as np

log = logging.getLogger(__name__)

# bge-small outperforms MiniLM on semantic similarity at similar size (130MB vs 80MB)
MODEL_ID = "BAAI/bge-small-en-v1.5"


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer
    log.info("Loading embedding model %s (first load only)...", MODEL_ID)
    return SentenceTransformer(MODEL_ID)


def embed_texts(texts: list[str]) -> np.ndarray:
    """Encode a list of strings → normalized float32 matrix of shape (n, dim)."""
    return _get_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)


def build_artist_vector(
    name: str,
    genres: list[str],
    audio_features: dict | None = None,
) -> np.ndarray:
    """
    Combine genre-text embedding (80%) + Spotify audio features (20%).
    Falls back to text-only for artists without audio features.
    """
    genre_str = ", ".join(genres) if genres else "unknown genre"
    text_vec = embed_texts([f"{name} — {genre_str}"])[0]

    keys = ["danceability", "energy", "valence", "acousticness", "instrumentalness", "speechiness", "tempo_norm"]
    if audio_features:
        audio_vec = np.array([audio_features.get(k, 0.0) for k in keys], dtype=np.float32)
        norm = np.linalg.norm(audio_vec)
        if norm > 0:
            audio_vec /= norm
    else:
        # Zero-pad so all vectors are the same dimension (384 text + 7 audio = 391)
        audio_vec = np.zeros(len(keys), dtype=np.float32)

    combined = np.concatenate([text_vec * 0.8, audio_vec * 0.2])
    return combined / (np.linalg.norm(combined) + 1e-8)
